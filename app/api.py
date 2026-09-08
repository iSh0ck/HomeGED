"""
API de consultation. Lancement : uvicorn app.api:app --host 0.0.0.0 --port 8000
"""
import re
import json
import os
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Optional
from pathlib import Path

from fastapi import (FastAPI, Depends, File, Form, HTTPException, Request, Response,
                     UploadFile, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import false, func, or_
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, ConfigDict

from . import config
from .db import (
    get_session, SessionLocal, Document, Categorie, Utilisateur, SessionOuverte,
    attendre_base, ids_categorie_et_descendants, VueEnregistree, Metadonnee, Job,
    TableauDeBord, RegleChampCategorie, VerrouDocument, JournalAudit, VersionDocument,
    PieceDocument, ExportModele, DocumentAttache, AffichageValeur,
    ColonneCategorie,
)
from . import apercus
from . import audit
from . import automatisations
from . import echeances
from . import notifications as notifs
from . import auth
from . import base_donnees
from . import categories
from . import depots
from . import conformite
from . import droits
from . import groupes
from . import recherche as moteur_recherche
from . import reglages
from . import installation
from . import pieces
from . import export_modele
from . import liens_type
from . import liens_vue
from . import rattachements
from . import versions
from sqlalchemy.exc import SQLAlchemyError
from . import colonnes
from . import limitation
from . import impact
from . import otp
from . import statistiques
from . import filtres as moteur_filtres
from .migrations import appliquer_migrations
from .admin import router as admin_router

@asynccontextmanager
async def cycle_de_vie(application: FastAPI):
    """
    Préparation de l'application avant qu'elle ne réponde.

    Remplace `@app.on_event("startup")`, déprécié par FastAPI. Ce qui est fait
    ici doit l'être avant la première requête : attendre que la base réponde,
    appliquer les migrations en attente, garantir qu'un compte administrateur
    existe. Le code après `yield` s'exécuterait à l'arrêt — il n'y a rien à
    fermer, les sessions SQLAlchemy étant refermées à chaque requête.
    """
    for avertissement in config.verifier_secret_key():
        logging.getLogger(__name__).warning(avertissement)
    attendre_base()
    appliquer_migrations()
    session = SessionLocal()
    try:
        auth.creer_admin_si_absent(session)
    finally:
        session.close()
    yield


app = FastAPI(title="HomeGED API", lifespan=cycle_de_vie)

# CORS limité aux origines déclarées (CORS_ORIGINS). En production le frontend
# est servi par nginx sur la même origine que l'API : ce middleware ne sert
# qu'au serveur de développement Vite.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    # Le jeton anti-CSRF et l'en-tête de consultation voyagent sur toute écriture :
    # sans eux dans cette liste, le navigateur refuse la requête au vol préalable
    # et **aucune écriture ne passe** depuis le serveur de développement (§22.38).
    allow_headers=["Authorization", "Content-Type", auth.ENTETE_CSRF,
                   auth.ENTETE_CONSULTATION],
    # Sans cela, un navigateur en développement (Vite sur un autre port) ne peut
    # pas lire cet en-tête et la pagination perdrait son total. Servi par nginx,
    # tout est de même origine et la question ne se pose pas — mais elle se pose
    # en dev.
    expose_headers=["X-Total-Count"],
)

app.include_router(admin_router)


# ------------------------------------------------------------
# Authentification
# ------------------------------------------------------------

class TokenOut(BaseModel):
    """
    Réponse de connexion. Deux issues possibles :

    * la session est ouverte — `access_token` est rempli ;
    * un second facteur est attendu — `otp_requis` vaut vrai et
      `jeton_intermediaire` atteste que le mot de passe, lui, était bon.

    Un compte à qui la double authentification est imposée mais qui ne l'a pas
    encore configurée entre normalement, avec `otp_a_configurer` : l'API ne lui
    répondra que sur les routes de configuration (cf. app/auth.py).
    """
    access_token: Optional[str] = None
    token_type: str = "bearer"
    otp_requis: bool = False
    jeton_intermediaire: Optional[str] = None
    otp_a_configurer: bool = False


class MeOut(BaseModel):
    id: int
    email: str
    nom: str
    est_admin: bool
    roles: list[str]
    otp_actif: bool = False
    otp_impose: bool = False
    codes_secours_restants: int = 0
    date_mot_de_passe: Optional[str] = None
    # Mode d'ouverture d'un document (§19.20) : personnel, pas de foyer.
    mode_apercu: str = "miniature"
    # Lignes par page du registre (§22.44). `null` : on suit le réglage du foyer
    # — le nombre dépend de l'écran devant lequel on est assis, pas du foyer.
    lignes_par_page: Optional[int] = None
    # Palette et langue de ce compte (§22.50, §22.51). `null` : celles du foyer.
    theme: Optional[str] = None
    langue: Optional[str] = None
    # Recevoir les rappels par courriel (§21.10) : chacun décide d'être dérangé
    # ou non, sans perdre les rappels dans l'application.
    courriel_rappels: bool = True
    # Les droits hors catégorie de ce compte (§19.12). L'interface s'en sert pour
    # ne montrer que le faisable : un écran qui propose une action refusée
    # ensuite fait perdre deux fois, au clic et à la lecture du message.
    droits: list[str] = []


# Compteur des échecs de connexion, tenu en mémoire du processus (cf. app/limitation.py)
limiteur_connexion = limitation.LimiteurTentatives(
    max_tentatives=config.LOGIN_MAX_TENTATIVES,
    fenetre=config.LOGIN_FENETRE_SECONDES,
    verrouillage=config.LOGIN_VERROUILLAGE_SECONDES,
)


def _accorder_limiteur(session: Session) -> None:
    """
    Aligne le compteur d'échecs sur les réglages du foyer (§18.22).

    Le limiteur vit en mémoire du processus ; ses seuils sont relus à chaque
    tentative, ce qui permet de les changer depuis l'interface sans redémarrer.
    Trois lectures d'une petite table à chaque connexion : c'est le prix d'un
    réglage qui prend effet tout de suite, et il est modeste au regard d'un
    contrôle de mot de passe bcrypt.
    """
    try:
        limiteur_connexion.max_tentatives = reglages.entier(
            session, "tentatives_avant_verrouillage")
        limiteur_connexion.verrouillage = reglages.entier(
            session, "duree_verrouillage_minutes") * 60
    except SQLAlchemyError:
        # une base qui bronche ne doit pas empêcher la protection de fonctionner :
        # on garde alors les seuils de `.env`
        pass


@app.post("/auth/login", response_model=TokenOut)
def login(
    request: Request,
    reponse_http: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    """
    Délivre un jeton de session.

    Les tentatives infructueuses sont comptées : au-delà du seuil, la source est
    écartée temporairement. La réponse ne distingue jamais un compte inexistant
    d'un mot de passe erroné, pour ne pas révéler quelles adresses existent.
    """
    cles = limitation.cles(limitation.adresse_client(request), form.username)
    _accorder_limiteur(session)

    if limiteur_connexion.max_tentatives > 0:
        attente = limiteur_connexion.attente_requise(cles)
        if attente:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                # arrondi au plus proche : `attente` porte une seconde de marge,
                # annoncer « 16 minutes » pour un verrouillage de 15 serait faux
                detail=f"Trop de tentatives de connexion. Réessaie dans "
                       f"{max(1, round(attente / 60))} minute(s).",
                headers={"Retry-After": str(attente)},
            )

    user = session.query(Utilisateur).filter_by(email=form.username, actif=True).one_or_none()
    if not user or not auth.verifier_mot_de_passe(form.password, user.mot_de_passe_hash):
        adresse = limitation.adresse_client(request)
        if limiteur_connexion.max_tentatives > 0 and limiteur_connexion.echec(
            cles, adresse=adresse, identifiant=form.username
        ):
            # le verrouillage est journalisé : une série d'échecs mérite d'être
            # visible, c'est le signe d'une attaque ou d'un compte en difficulté
            audit.journaliser(
                session, None, "auth.verrouillage", "connexion",
                details={"identifiant_tente": form.username,
                         "adresse": adresse,
                         "verrouillage_secondes": limiteur_connexion.verrouillage},
            )
            session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect")

    limiteur_connexion.succes(cles)

    if user.otp_actif:
        # Le mot de passe est bon, la session ne s'ouvre pas pour autant : on
        # rend un jeton intermédiaire, valable deux minutes, qui n'autorise
        # qu'une chose — présenter un code à /auth/otp.
        return TokenOut(otp_requis=True,
                        jeton_intermediaire=auth.creer_token_second_facteur(user.email))

    jeton = auth.ouvrir_session(session, user, request)
    # cookie httpOnly pour le navigateur, jeton dans le corps pour les scripts
    auth.poser_cookies_session(reponse_http, jeton)
    return TokenOut(access_token=jeton,
                    otp_a_configurer=bool(auth._otp_exige(session, user) and not user.otp_actif))


class SecondFacteurIn(BaseModel):
    jeton_intermediaire: str
    code: str


@app.post("/auth/otp", response_model=TokenOut)
def verifier_second_facteur(
    payload: SecondFacteurIn,
    request: Request,
    reponse_http: Response,
    session: Session = Depends(get_session),
):
    """
    Deuxième étape de la connexion : le code du téléphone, ou un code de secours.

    Cette étape est comptée par le même limiteur que le mot de passe. Sans cela,
    le second facteur serait le maillon faible : six chiffres se devinent en
    quelques centaines de milliers d'essais, ce qui n'est rien pour une machine.
    """
    email = auth.lire_token_second_facteur(payload.jeton_intermediaire)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Étape expirée. Reprenez la connexion depuis le début.")

    adresse = limitation.adresse_client(request)
    cles = limitation.cles(adresse, email)
    if limiteur_connexion.max_tentatives > 0:
        attente = limiteur_connexion.attente_requise(cles)
        if attente:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Trop de tentatives. Réessaie dans {max(1, round(attente / 60))} minute(s).",
                headers={"Retry-After": str(attente)},
            )

    user = session.query(Utilisateur).filter_by(email=email, actif=True).one_or_none()
    if not user or not user.otp_actif:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code refusé")

    reste = otp.consommer_code_secours(user.otp_codes_secours, payload.code)
    par_secours = reste is not None
    if par_secours:
        user.otp_codes_secours = reste
    elif not otp.verifier(user.otp_secret, payload.code):
        if limiteur_connexion.max_tentatives > 0 and limiteur_connexion.echec(
            cles, adresse=adresse, identifiant=email
        ):
            audit.journaliser(session, None, "auth.verrouillage", "connexion",
                              details={"identifiant_tente": email, "adresse": adresse,
                                       "etape": "second facteur",
                                       "verrouillage_secondes": limiteur_connexion.verrouillage})
        session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code refusé")

    if par_secours:
        # Un code de secours consommé mérite d'être su : c'est le signe d'un
        # téléphone perdu, ou de quelqu'un d'autre qui entre.
        audit.journaliser(session, user, "auth.code_secours_utilise", "utilisateur", user.id,
                          details={"adresse": adresse,
                                   "codes_restants": otp.nombre_codes_secours(reste)})
    session.commit()

    limiteur_connexion.succes(cles)
    jeton = auth.ouvrir_session(session, user, request)
    auth.poser_cookies_session(reponse_http, jeton)
    return TokenOut(access_token=jeton)


@app.post("/auth/logout")
def logout(request: Request, reponse_http: Response, session: Session = Depends(get_session)):
    """
    Referme la session : cookies retirés côté navigateur, session révoquée côté
    serveur. Sans la seconde moitié, le jeton resterait valable jusqu'à son
    expiration pour qui l'aurait recopié.
    """
    jeton = request.cookies.get(auth.NOM_COOKIE_SESSION)
    entete = request.headers.get("authorization") or ""
    if not jeton and entete.lower().startswith("bearer "):
        jeton = entete.split(" ", 1)[1]
    identifiant = auth.jti_du_jeton(jeton) if jeton else None
    if identifiant:
        auth.revoquer_session(session, identifiant)
    auth.retirer_cookies_session(reponse_http)
    return {"ok": True}


def _profil(user: Utilisateur, session: Optional[Session] = None) -> MeOut:
    # `otp_impose` dit à l'interface qu'il faut configurer le second facteur : le
    # réglage du foyer compte donc autant que la case posée sur le compte (§18.22).
    impose = bool(user.otp_impose)
    if not impose and session is not None:
        impose = auth._otp_exige(session, user)
    return MeOut(
        id=user.id, email=user.email, nom=user.nom_affiche, est_admin=user.est_admin,
        roles=[r.nom for r in user.roles],
        otp_actif=bool(user.otp_actif), otp_impose=impose,
        codes_secours_restants=otp.nombre_codes_secours(user.otp_codes_secours),
        date_mot_de_passe=user.date_mot_de_passe.isoformat(timespec="seconds")
        if user.date_mot_de_passe else None,
        mode_apercu=user.mode_apercu or "miniature",
        lignes_par_page=user.lignes_par_page,
        theme=user.theme, langue=user.langue,
        courriel_rappels=bool(user.courriel_rappels),
        droits=sorted(d for d in droits.GENERAUX if droits.general(user, d)),
    )


@app.get("/auth/me", response_model=MeOut)
def me(user: Utilisateur = Depends(auth.get_current_user),
       session: Session = Depends(get_session)):
    return _profil(user, session)


# ------------------------------------------------------------
# Mon compte
#
# Ce que chacun règle pour lui-même, sans passer par un administrateur : son
# mot de passe et sa double authentification. Toutes ces routes exigent le mot
# de passe en cours dès qu'elles affaiblissent la sécurité du compte — un
# navigateur laissé ouvert ne doit pas suffire à retirer un second facteur.
# ------------------------------------------------------------

# Repli si le réglage du foyer est illisible : une exigence par défaut vaut mieux
# qu'aucune (§18.22).
LONGUEUR_MINIMALE_MOT_DE_PASSE = 10


class ChangementMotDePasseIn(BaseModel):
    ancien: str
    nouveau: str


@app.get("/moi", response_model=MeOut)
def mon_compte(user: Utilisateur = Depends(auth.get_current_user),
               session: Session = Depends(get_session)):
    return _profil(user, session)


MODES_APERCU = ("document", "miniature")


# Ce qu'on peut demander comme nombre de lignes. La même liste que la
# pagination et que le réglage du foyer : trois endroits, un seul vocabulaire.
LIGNES_PAR_PAGE = (25, 50, 100, 200)


class PreferencesIn(BaseModel):
    mode_apercu: Optional[str] = None
    courriel_rappels: Optional[bool] = None
    # 0 (ou vide) rend la main au réglage du foyer (§22.44) : il faut pouvoir
    # revenir au défaut sans deviner le nombre qu'il porte.
    lignes_par_page: Optional[int] = None
    # Chaîne vide : on revient au thème / à la langue du foyer (§22.50, §22.51).
    theme: Optional[str] = None
    langue: Optional[str] = None


@app.put("/moi/preferences", response_model=MeOut)
def changer_mes_preferences(
    payload: PreferencesIn,
    user: Utilisateur = Depends(auth.get_current_user),
    session: Session = Depends(get_session),
):
    """
    Le mode d'ouverture d'un document, pour **ce compte-ci** (§19.20).

    Elles ne sont pas des réglages de foyer : elles dépendent de la machine et de
    la liaison de celui qui regarde. Sur un portable en 4G, ouvrir la miniature
    plutôt que le PDF change tout ; sur un poste fixe, la question ne se pose pas.

    Chacun les règle donc pour lui, sans droit particulier — on ne demande pas la
    permission d'afficher son propre écran autrement.
    """
    if payload.mode_apercu is not None:
        if payload.mode_apercu not in MODES_APERCU:
            raise HTTPException(
                status_code=422,
                detail=f"Mode d'aperçu inconnu (attendu : {', '.join(MODES_APERCU)}).")
        user.mode_apercu = payload.mode_apercu
    if payload.lignes_par_page is not None:
        voulu = int(payload.lignes_par_page)
        if voulu and voulu not in LIGNES_PAR_PAGE:
            raise HTTPException(
                status_code=422,
                detail=f"Nombre de lignes inconnu (attendu : "
                       f"{', '.join(str(n) for n in LIGNES_PAR_PAGE)}, ou 0 pour "
                       f"suivre le réglage du foyer).")
        user.lignes_par_page = voulu or None
    for cle in ("theme", "langue"):
        demande = getattr(payload, cle)
        if demande is None:
            continue
        voulu = demande.strip()
        if voulu and not re.fullmatch(r"[a-z0-9_-]{2,32}", voulu):
            raise HTTPException(
                status_code=422,
                detail="Clé invalide : minuscules, chiffres, tiret ou souligné.")
        # Vide = revenir à ce que le foyer a choisi. L'existence de la clé n'est
        # pas vérifiée : le catalogue s'enrichit d'un fichier déposé (§22.50), et
        # une clé disparue retombe côté interface sur le thème d'origine.
        setattr(user, cle, voulu or None)
    if payload.courriel_rappels is not None:
        user.courriel_rappels = bool(payload.courriel_rappels)
        # On repart du premier palier : quelqu'un qui vient de rouvrir le canal
        # ne doit pas attendre une semaine le prochain résumé.
        user.palier_courriel = 0
    session.commit()
    session.refresh(user)
    return _profil(user, session)


@app.post("/moi/mot-de-passe", response_model=TokenOut)
def changer_mon_mot_de_passe(
    payload: ChangementMotDePasseIn,
    request: Request,
    reponse_http: Response,
    user: Utilisateur = Depends(auth.get_current_user),
    session: Session = Depends(get_session),
):
    """
    Change le mot de passe du compte connecté.

    L'ancien est exigé : sans lui, un navigateur laissé ouvert suffirait à
    prendre le compte. Le changement périme ensuite **toutes** les sessions du
    compte — c'est le but, un mot de passe qu'on change est souvent un mot de
    passe qu'on croit connu d'un autre. La session qui fait la demande reçoit un
    jeton neuf en retour, pour ne pas se retrouver dehors en changeant.
    """
    if not auth.verifier_mot_de_passe(payload.ancien, user.mot_de_passe_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Mot de passe actuel incorrect")
    nouveau = payload.nouveau or ""
    minimum = (reglages.entier(session, "longueur_min_mot_de_passe")
               or LONGUEUR_MINIMALE_MOT_DE_PASSE)
    if len(nouveau) < minimum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Le nouveau mot de passe doit faire au moins {minimum} caractères.",
        )
    if nouveau == payload.ancien:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Le nouveau mot de passe est identique à l'ancien.")

    user.mot_de_passe_hash = auth.hash_mot_de_passe(nouveau)
    user.jeton_version = (user.jeton_version or 0) + 1
    user.date_mot_de_passe = datetime.now()
    fermees = auth.revoquer_toutes_les_sessions(session, user.id)
    audit.journaliser(session, user, "compte.mot_de_passe_change", "utilisateur", user.id,
                      details={"sessions_fermees": fermees})
    session.commit()

    # La session qui demande le changement repart avec un jeton neuf : se mettre
    # dehors soi-même en changeant son mot de passe serait absurde.
    jeton = auth.ouvrir_session(session, user, request)
    auth.poser_cookies_session(reponse_http, jeton)
    return TokenOut(access_token=jeton)


class SessionOut(BaseModel):
    id: int
    courante: bool                      # celle qui pose la question
    date_creation: Optional[str] = None
    date_activite: Optional[str] = None
    adresse: Optional[str] = None
    appareil: str                       # lecture humaine de l'en-tête User-Agent


def _appareil(agent: Optional[str]) -> str:
    """
    Résume un en-tête `User-Agent` en une phrase lisible.

    Volontairement grossier : reconnaître exactement chaque navigateur
    demanderait une bibliothèque entretenue en permanence, alors que
    l'utilisateur n'a besoin que de reconnaître **ses** appareils. « Chrome sur
    Windows » suffit à distinguer le portable du salon du téléphone.
    """
    if not agent:
        return "Appareil inconnu"
    brut = agent.lower()
    navigateur = next(
        (nom for motif, nom in (
            ("edg/", "Edge"), ("opr/", "Opera"), ("firefox", "Firefox"),
            ("chrome", "Chrome"), ("safari", "Safari"), ("curl", "curl"),
            ("python", "script Python"),
        ) if motif in brut),
        None,
    )
    systeme = next(
        (nom for motif, nom in (
            ("windows", "Windows"), ("android", "Android"), ("iphone", "iPhone"),
            ("ipad", "iPad"), ("mac os", "macOS"), ("linux", "Linux"),
        ) if motif in brut),
        None,
    )
    if navigateur and systeme:
        return f"{navigateur} sur {systeme}"
    return navigateur or systeme or agent[:40]


def _jti_courant(request: Request) -> Optional[str]:
    jeton = request.cookies.get(auth.NOM_COOKIE_SESSION)
    entete = request.headers.get("authorization") or ""
    if not jeton and entete.lower().startswith("bearer "):
        jeton = entete.split(" ", 1)[1]
    return auth.jti_du_jeton(jeton) if jeton else None


@app.get("/moi/sessions", response_model=list[SessionOut])
def mes_sessions(request: Request, user: Utilisateur = Depends(auth.get_current_user),
                 session: Session = Depends(get_session)):
    """
    Les sessions ouvertes du compte, la plus récemment active en tête.

    Une session expirée n'est pas montrée : elle ne donne plus accès à rien, et
    l'afficher inquiéterait pour rien.
    """
    courant = _jti_courant(request)
    lignes = (
        session.query(SessionOuverte)
        .filter(SessionOuverte.utilisateur_id == user.id,
                SessionOuverte.date_revocation.is_(None),
                SessionOuverte.date_expiration > datetime.now())
        # `NULLS LAST` n'existe pas en MariaDB : on trie sur la dernière activité
        # en retombant sur la date d'ouverture, ce qui dit la même chose et se
        # traduit partout.
        .order_by(func.coalesce(SessionOuverte.date_activite,
                                SessionOuverte.date_creation).desc())
        .all()
    )
    return [
        SessionOut(
            id=ligne.id,
            courante=ligne.jti == courant,
            date_creation=ligne.date_creation.isoformat(timespec="seconds") if ligne.date_creation else None,
            date_activite=ligne.date_activite.isoformat(timespec="seconds") if ligne.date_activite else None,
            adresse=ligne.adresse,
            appareil=_appareil(ligne.agent),
        )
        for ligne in lignes
    ]


@app.delete("/moi/sessions/{session_id}")
def fermer_une_session(session_id: int, request: Request,
                       user: Utilisateur = Depends(auth.get_current_user),
                       session: Session = Depends(get_session)):
    """
    Ferme une session du compte — la sienne comprise, ce qui revient à se
    déconnecter de cet appareil-là.
    """
    ligne = session.query(SessionOuverte).filter_by(id=session_id,
                                                    utilisateur_id=user.id).one_or_none()
    if not ligne:
        raise HTTPException(status_code=404, detail="Session introuvable")
    if ligne.date_revocation is None:
        ligne.date_revocation = datetime.now()
        audit.journaliser(session, user, "compte.session_fermee", "utilisateur", user.id,
                          details={"appareil": _appareil(ligne.agent), "adresse": ligne.adresse,
                                   "elle_meme": ligne.jti == _jti_courant(request)})
        session.commit()
    return {"ok": True}


@app.post("/moi/sessions/fermer-les-autres")
def fermer_les_autres_sessions(request: Request,
                               user: Utilisateur = Depends(auth.get_current_user),
                               session: Session = Depends(get_session)):
    """
    Ferme toutes les sessions sauf celle qui le demande. C'est le geste à faire
    quand on a un doute : on reprend la main partout sans se déconnecter soi-même.
    """
    fermees = auth.revoquer_toutes_les_sessions(session, user.id, sauf_jti=_jti_courant(request))
    if fermees:
        audit.journaliser(session, user, "compte.sessions_fermees", "utilisateur", user.id,
                          details={"nombre": fermees})
    session.commit()
    return {"fermees": fermees}


class PreparationOtpOut(BaseModel):
    secret: str
    secret_lisible: str
    uri: str
    qr_svg: str      # image SVG en data URI, affichable telle quelle


@app.post("/moi/otp/preparer", response_model=PreparationOtpOut)
def preparer_ma_double_authentification(
    user: Utilisateur = Depends(auth.get_current_user),
    session: Session = Depends(get_session),
):
    """
    Tire un secret et rend de quoi l'appairer : un QR code, l'URI qu'il contient,
    et le secret en clair pour une saisie à la main.

    Le secret est enregistré tout de suite mais la double authentification reste
    inactive : tant que l'utilisateur n'a pas prouvé, par un code valide, que son
    application est bien appairée, l'exiger le mettrait dehors.
    """
    if user.otp_actif:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="La double authentification est déjà active sur ce compte.")
    secret = otp.nouveau_secret()
    user.otp_secret = secret
    session.commit()

    uri = otp.uri_provisionnement(secret, user.email)
    return PreparationOtpOut(secret=secret, secret_lisible=otp.secret_lisible(secret),
                             uri=uri, qr_svg=otp.qr_data_uri(uri))


class CodeOtpIn(BaseModel):
    code: str


class CodesSecoursOut(BaseModel):
    codes: list[str]


@app.post("/moi/otp/activer", response_model=CodesSecoursOut)
def activer_ma_double_authentification(
    payload: CodeOtpIn,
    user: Utilisateur = Depends(auth.get_current_user),
    session: Session = Depends(get_session),
):
    """
    Confirme l'appairage par un premier code, puis active.

    Les codes de secours sont rendus ici, et **une seule fois** : ils sont
    stockés hachés, personne ne pourra les réafficher — pas même un
    administrateur.
    """
    if user.otp_actif:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Déjà active.")
    if not user.otp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Commencez par préparer l'appairage.")
    if not otp.verifier(user.otp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Code refusé. Vérifiez l'heure de votre téléphone.")

    codes, stockables = otp.nouveaux_codes_secours()
    user.otp_actif = True
    user.otp_codes_secours = stockables
    audit.journaliser(session, user, "compte.otp_active", "utilisateur", user.id)
    session.commit()
    return CodesSecoursOut(codes=codes)


class MotDePasseIn(BaseModel):
    mot_de_passe: str


@app.post("/moi/otp/desactiver", response_model=MeOut)
def desactiver_ma_double_authentification(
    payload: MotDePasseIn,
    user: Utilisateur = Depends(auth.get_current_user),
    session: Session = Depends(get_session),
):
    """Retire le second facteur. Le mot de passe est exigé, et un compte à qui
    la double authentification est imposée — sur le compte ou sur tout le foyer —
    ne peut pas s'en défaire."""
    if auth._otp_exige(session, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un administrateur exige la double authentification sur ce compte.",
        )
    if not auth.verifier_mot_de_passe(payload.mot_de_passe, user.mot_de_passe_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Mot de passe incorrect")
    user.otp_actif = False
    user.otp_secret = None
    user.otp_codes_secours = None
    audit.journaliser(session, user, "compte.otp_desactive", "utilisateur", user.id)
    session.commit()
    return _profil(user)


@app.post("/moi/otp/codes-secours", response_model=CodesSecoursOut)
def regenerer_mes_codes_secours(
    payload: MotDePasseIn,
    user: Utilisateur = Depends(auth.get_current_user),
    session: Session = Depends(get_session),
):
    """
    Refait une série de codes de secours. Les anciens cessent d'être valables :
    on ne sait pas ce qu'ils sont devenus, c'est justement pourquoi on les refait.
    """
    if not user.otp_actif:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="La double authentification n'est pas active.")
    if not auth.verifier_mot_de_passe(payload.mot_de_passe, user.mot_de_passe_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Mot de passe incorrect")
    codes, stockables = otp.nouveaux_codes_secours()
    user.otp_codes_secours = stockables
    audit.journaliser(session, user, "compte.codes_secours_regeneres", "utilisateur", user.id)
    session.commit()
    return CodesSecoursOut(codes=codes)


# ------------------------------------------------------------
# Documents (filtrés par droits sur les catégories)
# ------------------------------------------------------------

class DocumentOut(BaseModel):
    id: int
    nom_fichier: str
    date_import: str
    date_document: Optional[str] = None
    statut: str
    categorie: Optional[str] = None
    categorie_id: Optional[int] = None
    metadonnees: dict
    # libellés des métadonnées qui pointent une ligne d'une table de données :
    # afficher « Renault » plutôt que « 1 » (§17)
    libelles_references: dict = {}
    # Les métadonnées à montrer sur la fiche, vides comprises (§19.20). Vide sur
    # la liste : ce détail-là ne sert qu'à la fiche ouverte.
    champs_fiche: list = []
    # champs obligatoires de la catégorie qui manquent encore (§15) : le
    # document est indexé, mais pas conforme à ce qu'attend son classement
    champs_manquants: list[dict] = []
    # tous les champs déclarés par la catégorie — remplis ou non — pour que la
    # fenêtre de modification sache quoi proposer, et sous quelle forme (§17.21)
    champs_attendus: list[dict] = []
    # dernière modification connue : quand, et par qui (§17.24). Se lit sur la
    # fiche avant d'ouvrir quoi que ce soit — savoir que quelqu'un est passé
    # avant soi change ce qu'on s'apprête à faire.
    derniere_modification: Optional[dict] = None
    # Nombre de dépôts de ce document (§18.36). Au-delà de un, le tableau et la
    # fiche proposent d'en consulter l'historique.
    nb_versions: int = 1
    # Ce que cette entrée retient de chaque valeur de table (§22.61) :
    # `{champ: [colonnes]}`. Vide : elle montre tout ce que le champ propose.
    affichages: dict = {}
    # Déposé à la main plutôt qu'arrivé seul par le dossier surveillé (§22.68).
    # `None` quand on ne sait pas : la tâche qui portait la trace a été purgée
    # avant qu'on la note, et l'inventer serait pire que se taire.
    depot_manuel: Optional[bool] = None
    # Une entrée de fiche simple peut n'avoir **aucun fichier** (§19.1) : elle
    # se saisit à la main, et rien ne l'oblige à porter un PDF. L'écran a besoin
    # de le savoir pour ne pas réclamer une vignette qui n'existe pas — il
    # affichait « Page non rendue » là où il ne fallait rien afficher (§22.58).
    # `pieces == []` ne suffit pas à le dire : un document d'avant le §22.2 n'a
    # pas de pièce déclarée et porte pourtant son fichier.
    a_un_fichier: bool = True

    model_config = ConfigDict(from_attributes=True)


def _ecrire_affichages(session: Session, doc: Document, demandes: dict) -> None:
    """
    Enregistre ce que cette entrée retient de chaque valeur de table (§22.61).

    Seul ce que le champ propose est retenu : un choix qui déborde la palette de
    l'administrateur serait un réglage qui ne fait rien. Retenir **tout** ce que
    le champ propose, ou rien, efface la ligne — on revient au champ, et la base
    ne garde pas un doublon de ce qu'elle sait déjà.
    """
    if not doc.categorie_id:
        return
    palettes = conformite.affichages_par_categorie(session, {doc.categorie_id})
    existantes = {a.champ: a for a in session.query(AffichageValeur)
                  .filter(AffichageValeur.document_id == doc.id)}

    for champ, colonnes in (demandes or {}).items():
        palette = palettes.get((doc.categorie_id, champ)) or []
        garde = [c for c in palette if c in (colonnes or [])]
        ligne = existantes.get(champ)
        if not palette or not garde or len(garde) == len(palette):
            if ligne:
                session.delete(ligne)
            continue
        if ligne:
            ligne.colonnes = ",".join(garde)
        else:
            session.add(AffichageValeur(document_id=doc.id, champ=champ,
                                        colonnes=",".join(garde)))


def _affichages_par_document(session: Session, documents: list[Document]) -> dict:
    """`{document_id: {champ: [colonnes]}}` — ce que l'écran de saisie relit (§22.61)."""
    par_document: dict = {}
    for (document_id, champ), colonnes in _affichages_des_entrees(
            session, [d.id for d in documents]).items():
        par_document.setdefault(document_id, {})[champ] = colonnes
    return par_document


def _affichages_des_entrees(session: Session, document_ids: list[int]) -> dict:
    """`{(document_id, champ): [colonnes]}` — ce que chaque entrée retient (§22.61)."""
    if not document_ids:
        return {}
    return {(a.document_id, a.champ): [c.strip() for c in a.colonnes.split(",") if c.strip()]
            for a in session.query(AffichageValeur)
            .filter(AffichageValeur.document_id.in_(document_ids))}


def _lecture_retenue(affichages: dict, par_entree: dict, document_id: int,
                     categorie_id: Optional[int], champ: str) -> tuple:
    """
    La composition qui s'applique, des trois niveaux au plus précis (§22.61).

    L'entrée d'abord — mais seulement pour ce que le champ propose : un
    administrateur qui retire une colonne de la palette la retire pour tout le
    monde, y compris pour les entrées qui l'avaient retenue. Le champ ensuite,
    la table à défaut.
    """
    du_champ = affichages.get((categorie_id, champ)) or []
    retenu = par_entree.get((document_id, champ))
    if retenu and du_champ:
        # L'ordre reste celui du champ : c'est lui qui compose, l'entrée ne fait
        # que retirer.
        garde = [c for c in du_champ if c in retenu]
        if garde:
            return tuple(garde)
    return tuple(du_champ)


def _libelles_references(session: Session, documents: list[Document]) -> dict:
    """
    Résout les métadonnées qui pointent une source de valeurs, en un aller-retour
    par source plutôt qu'un par document — une liste de 200 documents ne doit pas
    déclencher 200 requêtes.

    Une valeur porte sa source (`usr_membres:3`) depuis §17.28 ; celles écrites
    avant sont interprétées dans la première source déclarée pour le champ.
    """
    categories_lues = {d.categorie_id for d in documents if d.categorie_id is not None}
    sources = conformite.sources_par_categorie(session, categories_lues)
    if not sources:
        return {}
    # Ce que chaque champ veut lire de sa ligne (§22.59) : deux champs qui
    # puisent dans la même table peuvent en montrer deux choses différentes.
    affichages = conformite.affichages_par_categorie(session, categories_lues)
    # Et ce que **cette entrée-ci** en retient (§22.61) : c'est celui qui saisit
    # qui sait si le modèle apporte quelque chose à sa ligne.
    par_entree = _affichages_des_entrees(session, [d.id for d in documents])

    def valeur_du_champ(doc, champ):
        cle = champ[len(moteur_filtres.PREFIXE_META):]
        return cle, next((m.valeur for m in doc.metadonnees if m.cle == cle and m.valeur), None)

    # Groupés par (table, affichage retenu) : une table lue de deux façons
    # demande deux résolutions, et une seule requête par façon.
    besoins: dict[tuple, set] = {}
    for doc in documents:
        for (categorie_id, champ), tables in sources.items():
            if categorie_id != doc.categorie_id:
                continue
            _, valeur = valeur_du_champ(doc, champ)
            if not valeur:
                continue
            table, identifiant = base_donnees.decouper_valeur(valeur, tables[0])
            if table in tables:
                lecture = _lecture_retenue(affichages, par_entree, doc.id, categorie_id, champ)
                besoins.setdefault((table, lecture), set()).add(identifiant)

    resolus = {
        cle: base_donnees.libelles_par_id(session, cle[0], ids,
                                          affichage=list(cle[1]) or None)
        for cle, ids in besoins.items()
    }

    par_document: dict[int, dict] = {}
    for doc in documents:
        for (categorie_id, champ), tables in sources.items():
            if categorie_id != doc.categorie_id:
                continue
            cle, valeur = valeur_du_champ(doc, champ)
            if not valeur:
                continue
            table, identifiant = base_donnees.decouper_valeur(valeur, tables[0])
            lecture = _lecture_retenue(affichages, par_entree, doc.id, categorie_id, champ)
            libelle = resolus.get((table, lecture), {}).get(str(identifiant))
            if libelle:
                par_document.setdefault(doc.id, {})[cle] = libelle
    return par_document


def _etat_lisible(session: Session, doc: Document) -> dict:
    """
    État du document en valeurs lisibles, pour le journal d'audit.

    On y écrit « Factures », pas « 2 ». Une trace d'audit se relit des mois plus
    tard, parfois après qu'une catégorie a été renommée ou supprimée : consigner
    l'identifiant obligerait à retrouver ce qu'il désignait à l'époque, ce que
    plus rien ne permettrait. On garde donc ce que l'utilisateur voyait.
    """
    etat = {
        "categorie": doc.categorie.nom if doc.categorie else None,
        "date_document": str(doc.date_document) if doc.date_document else None,
    }
    libelles = _libelles_references(session, [doc]).get(doc.id, {})
    for metadonnee in doc.metadonnees:
        # Une métadonnée peut porter le nom d'un champ du document — les règles
        # d'extraction écrivent volontiers une clé `date_document`. Sans cette
        # précaution, elle écrasait la valeur du document dans le relevé, et la
        # différence calculée ensuite était fausse : une date changée passait
        # pour inchangée, et rien n'était journalisé.
        cle = metadonnee.cle if metadonnee.cle not in etat else f"{metadonnee.cle} (extrait)"
        # une métadonnée pointant une table s'écrit par son libellé : « Jean
        # Dupont » se relit, « 1 » ne se relit pas
        etat[cle] = libelles.get(metadonnee.cle) or metadonnee.valeur
    return etat


def _difference(avant: dict, apres: dict) -> dict:
    """Ce qui a réellement changé, des deux côtés. Vide si rien n'a bougé."""
    cles = [cle for cle in {**avant, **apres} if avant.get(cle) != apres.get(cle)]
    if not cles:
        return {}
    return {
        "avant": {cle: avant.get(cle) for cle in cles},
        "apres": {cle: apres.get(cle) for cle in cles},
    }


def _champs_attendus(session: Session, doc: Document) -> list[dict]:
    """
    Champs déclarés par la catégorie du document, remplis ou non.

    `champs_manquants` ne dit que ce qui manque : de quoi signaler un document
    incomplet, pas de quoi construire un formulaire. Pour modifier, il faut
    savoir **tout** ce que la catégorie attend, et comment chaque champ se
    saisit — liste adossée à une table, date, texte libre.
    """
    if not doc.categorie_id:
        return []
    regles = (
        session.query(RegleChampCategorie)
        .filter(RegleChampCategorie.categorie_id == doc.categorie_id)
        .order_by(RegleChampCategorie.ordre, RegleChampCategorie.champ)
        .all()
    )
    champs = [
        {
            "champ": regle.champ,
            # La catégorie voyage avec le champ (§22.59) : le sélecteur de
            # valeurs doit dire **pour quel champ** il demande une liste, et
            # c'est le couple (catégorie, champ) qui l'identifie.
            "categorie_id": regle.categorie_id,
            "libelle": regle.libelle or conformite.libelle_par_defaut(regle.champ),
            "obligatoire": bool(regle.obligatoire),
            "source_table": regle.source_table,
            # toutes les sources du champ, dans l'ordre déclaré (§17.28)
            "sources": conformite.sources_de(regle),
            # Ce que l'administrateur propose de lire d'une ligne (§22.59) :
            # l'écran de saisie en fait la palette où l'entrée puise (§22.61).
            "colonnes_affichees": [c.strip() for c in (regle.colonnes_affichees or "").split(",")
                                   if c.strip()],
            # Le champ contient des documents de la GED (§22.11) : l'écran offre
            # alors un choix parmi les documents, pas une saisie.
            "attache_documents": bool(regle.attache_documents),
            # Comment le champ se saisit (§22.12) : l'écran n'a plus à le deviner
            # d'après le nom de la clé.
            "type_champ": regle.type_champ or "texte",
            # Ce qu'un champ « documents » accepte (§22.14) : l'écran s'en sert
            # pour ne proposer que ce qui a le droit d'y entrer.
            "documents_categorie_id": regle.documents_categorie_id,
            "documents_champs": [c.strip() for c in (regle.documents_champs or "").split(",")
                                 if c.strip()],
            "extraction_attendue": bool(regle.extraction_attendue),
        }
        for regle in regles
    ]
    # `date_document` n'est pas une métadonnée mais une colonne du document. Elle
    # n'a sa place dans le formulaire que si ce type-ci la porte — déclarée comme
    # champ attendu, ou montrée comme colonne de son tableau (§22.62).
    #
    # Elle s'affichait jusqu'ici pour tout le monde, en dur. Sur une fiche simple
    # qui déclare sa propre date, cela faisait **deux** cases « date » dont une
    # qui n'apparaît nulle part dans le tableau. C'est le même travers que
    # « Émetteur » au §21.12 : un champ du document imposé à des types qui n'en
    # veulent pas.
    if not any(c["champ"] == "date_document" for c in champs):
        # Les colonnes **réglées**, pas les colonnes déduites : une déduction est
        # un repli, pas une déclaration. Un type qui n'a rien configuré verrait
        # sinon la date lui revenir par cette porte, et le §22.62 n'aurait rien
        # changé. Et le document qui en porte déjà une : une date extraite doit
        # rester corrigeable, même si le type ne l'a jamais réclamée.
        reglees = {c.champ for c in session.query(ColonneCategorie)
                   .filter(ColonneCategorie.categorie_id == doc.categorie_id)}
        if "date_document" in reglees or doc.date_document is not None:
            champs.append({
                "champ": "date_document",
                "categorie_id": doc.categorie_id,
                "libelle": conformite.libelle_par_defaut("date_document"),
                "obligatoire": False,
                "source_table": None, "sources": [], "colonnes_affichees": [],
                "attache_documents": False,
                "type_champ": "date",
                "documents_categorie_id": None, "documents_champs": [],
                "extraction_attendue": False,
            })
    return champs


def _derniere_modification(session: Session, doc: Document) -> Optional[dict]:
    """Quand ce document a été modifié pour la dernière fois, et par qui."""
    evenement = (
        session.query(JournalAudit)
        .filter(JournalAudit.objet_type == "document",
                JournalAudit.objet_id == doc.id,
                JournalAudit.action == audit.DOCUMENT_MODIFICATION)
        .order_by(JournalAudit.date_evenement.desc(), JournalAudit.id.desc())
        .first()
    )
    if not evenement:
        return None
    return {
        "date": evenement.date_evenement.isoformat(timespec="seconds")
        if evenement.date_evenement else None,
        "auteur": evenement.utilisateur_email,
    }


def _serialize(doc: Document, regles_par_cat: Optional[dict] = None,
               libelles_references: Optional[dict] = None,
               champs_attendus: Optional[list] = None,
               derniere_modification: Optional[dict] = None,
               nb_versions: Optional[dict] = None,
               affichages: Optional[dict] = None) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        nom_fichier=doc.nom_fichier,
        date_import=str(doc.date_import),
        date_document=str(doc.date_document) if doc.date_document else None,
        statut=doc.statut,
        categorie=doc.categorie.nom if doc.categorie else None,
        categorie_id=doc.categorie_id,
        metadonnees={m.cle: m.valeur for m in doc.metadonnees},
        libelles_references=(libelles_references or {}).get(doc.id, {}),
        champs_manquants=conformite.champs_manquants(doc, regles_par_cat or {}),
        champs_attendus=champs_attendus or [],
        derniere_modification=derniere_modification,
        nb_versions=(nb_versions or {}).get(doc.id, 1),
        affichages=(affichages or {}).get(doc.id, {}),
        depot_manuel=doc.depot_manuel,
        a_un_fichier=bool(doc.chemin_stockage),
    )


def _filtrer_par_droits(query, session: Session, user: Utilisateur,
                        action: str = droits.VOIR, corbeille: bool = False):
    """
    Le passage obligé de toute liste de documents. Le corps vit dans
    `app/droits.py` depuis le §21.13 : le serveur de travaux en a besoin lui
    aussi, pour construire une archive avec les droits de **celui qui l'a
    demandée** — et une règle d'accès écrite à deux endroits est une règle qui
    divergera.
    """
    return droits.filtrer_documents(query, session, user, action, corbeille)


def _verifier_acces(doc: Document, user: Utilisateur, ecriture: bool = False,
                    session: Optional[Session] = None,
                    action: Optional[str] = None, corbeille: bool = False) -> None:
    """
    Contrôle l'accès à un document, action par action (§19.12).

    `ecriture=True` reste accepté et vaut « modifier » : les appels antérieurs ne
    connaissaient que deux niveaux. `action` dit précisément lequel des six on
    exerce — c'est ce qui permet, par exemple, de laisser lire une fiche sans
    donner le PDF.
    """
    besoin = action or (droits.MODIFIER if ecriture else droits.VOIR)
    # Un document en corbeille n'est plus là (§21.1) : 404, et non 403 — le
    # distinguer d'un identifiant inexistant n'apprendrait rien d'utile et
    # laisserait croire à un refus de droits. Les écrans de corbeille passent
    # `corbeille=True` ; ce sont les seuls.
    if doc.date_suppression is not None and not corbeille:
        raise HTTPException(status_code=404, detail="Document introuvable")
    # Sans session fournie, on en ouvre une le temps du contrôle : quelques
    # appels anciens n'en passent pas encore, et les convertir en bloc ferait
    # dépendre un garde-fou d'un renommage réussi partout du premier coup.
    propre = session is None
    session = session or SessionLocal()
    try:
        droits.exiger(session, user, besoin, doc.categorie_id)
        # Les restrictions par branche (§21.7) valent aussi pour un document
        # ouvert directement par son adresse : sans ce contrôle, l'URL serait la
        # porte de derrière. On repasse par la requête filtrée plutôt que de
        # réécrire la règle ici — une règle écrite deux fois divergera.
        if droits.branches_autorisees(session, user):
            visible = (_filtrer_par_droits(session.query(Document.id), session, user,
                                           action=besoin, corbeille=corbeille)
                       .filter(Document.id == doc.id).first())
            if visible is None:
                raise HTTPException(status_code=404, detail="Document introuvable")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(refus))
    finally:
        if propre:
            session.close()


@app.get("/documents", response_model=list[DocumentOut])
def lister_documents(
    q: Optional[str] = None,
    categorie: Optional[str] = None,
    categorie_id: Optional[int] = None,
    filtres: Optional[str] = None,
    tri: Optional[str] = None,
    sens: Optional[str] = None,
    limite: int = 200,
    decalage: int = 0,
    reponse: Response = None,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Liste / recherche les documents, restreinte aux catégories autorisées pour l'utilisateur.
    - q : recherche plein texte sur texte_ocr (FULLTEXT MariaDB)
    - categorie_id / categorie : filtre par catégorie, **sous-catégories incluses**
      (sélectionner une section de la navigation ramène les documents de ses enfants)
    - filtres : liste JSON de `{champ, operateur, valeur}` combinés en ET
      (recherche par colonne et critères des vues enregistrées, cf. app/filtres.py)
    - tri / sens : tri effectué **par la base**, sur l'ensemble du registre et non
      sur la seule page renvoyée
    - limite / decalage : pagination. Le total correspondant aux filtres est
      renvoyé dans l'en-tête `X-Total-Count`, ce qui laisse la réponse être une
      simple liste de documents.
    """
    query = session.query(Document).options(
        joinedload(Document.categorie),
        joinedload(Document.metadonnees),
    )
    query = _filtrer_par_droits(query, session, user)

    if categorie_id is None and categorie:
        # compat : filtre historique par nom de catégorie
        trouvee = session.query(Categorie).filter_by(nom=categorie).first()
        categorie_id = trouvee.id if trouvee else -1
    if categorie_id is not None:
        query = query.filter(
            Document.categorie_id.in_(ids_categorie_et_descendants(session, categorie_id))
        )
    if q:
        # MATCH...AGAINST nécessite l'index FULLTEXT créé dans schema.sql
        query = query.filter(Document.texte_ocr.match(q))

    if filtres:
        try:
            criteres = json.loads(filtres)
            if not isinstance(criteres, list):
                raise ValueError("le paramètre `filtres` doit être une liste JSON")
            query = moteur_filtres.appliquer(
                query, session, [moteur_filtres.Filtre(**critere) for critere in criteres]
            )
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=422, detail=str(erreur))
        except (ValueError, TypeError) as erreur:
            raise HTTPException(status_code=422, detail=f"Paramètre `filtres` illisible : {erreur}")

    try:
        query = moteur_filtres.ordonner(query, tri, sens)
    except moteur_filtres.FiltreInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))

    # Documents incomplets : écartés du registre (§17.7). Leur nombre n'est plus
    # annoncé — l'interface ne l'affichait que dans un bandeau jugé inutile, et
    # le compter coûtait une requête de plus à chaque page. Le Centre d'analyse
    # reste la porte d'entrée vers ces documents.
    query = conformite.sans_les_fantomes(query)
    if reponse is not None:
        # compté avant pagination : c'est le total du filtre, pas de la page
        reponse.headers["X-Total-Count"] = str(query.order_by(None).count())

    limite = max(1, min(limite, 1000))
    documents = query.limit(limite).offset(max(0, decalage)).all()
    regles = conformite.regles_par_categorie(
        session, {d.categorie_id for d in documents if d.categorie_id is not None}
    )
    libelles = _libelles_references(session, documents)
    # Un décompte par page, pas un par document : une liste de 200 lignes ne doit
    # pas déclencher 200 requêtes.
    compte_versions = versions.compter(session, documents)
    choix = _affichages_par_document(session, documents)
    return [_serialize(d, regles, libelles, nb_versions=compte_versions, affichages=choix)
            for d in documents]


# Deux points d'entrée retirés au §18.56 : `/documents/champs-filtrables` et
# `/documents/tris`. Ils annonçaient ce sur quoi filtrer et trier, mais depuis le
# §18.1 l'interface tient cela des colonnes de la catégorie affichée
# (`/categories/colonnes`), qui les nomme en plus. Aucun écran ne les appelait.


@app.get("/documents/valeurs")
def lister_valeurs_colonne(
    champ: str,
    recherche: Optional[str] = None,
    filtres: Optional[str] = None,
    categorie_id: Optional[int] = None,
    q: Optional[str] = None,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Valeurs déjà présentes dans les documents pour une colonne : c'est ce que
    proposent les listes de recherche du tableau, plutôt qu'un catalogue de
    valeurs théoriques.

    Le périmètre est **exactement celui du registre affiché** : mêmes droits,
    même catégorie sélectionnée dans la navigation, même recherche plein texte,
    mêmes autres filtres de colonne, et sans les documents incomplets — qui
    n'apparaissent pas au registre (§17.7) et n'ont donc rien à suggérer.
    Proposer une valeur qui ne ramène aucune ligne serait une fausse piste.

    Seul le filtre portant sur la colonne demandée est ignoré : sinon la liste
    se réduirait à ce qui est déjà sélectionné, et l'on ne pourrait plus changer
    d'avis.
    """
    base = conformite.sans_les_fantomes(_filtrer_par_droits(session.query(Document.id), session, user))

    if categorie_id is not None:
        base = base.filter(
            Document.categorie_id.in_(ids_categorie_et_descendants(session, categorie_id))
        )
    if q:
        base = base.filter(Document.texte_ocr.match(q))

    if filtres:
        try:
            criteres = json.loads(filtres)
            if not isinstance(criteres, list):
                raise ValueError("le paramètre `filtres` doit être une liste JSON")
            autres = [
                moteur_filtres.Filtre(**critere)
                for critere in criteres
                if critere.get("champ") != champ
            ]
            base = moteur_filtres.appliquer(base, session, autres)
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=422, detail=str(erreur))
        except (ValueError, TypeError) as erreur:
            raise HTTPException(status_code=422, detail=f"Paramètre `filtres` illisible : {erreur}")

    try:
        return moteur_filtres.valeurs_distinctes(session, champ, base.scalar_subquery(), recherche)
    except moteur_filtres.FiltreInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))


@app.get("/documents/{document_id}", response_model=DocumentOut)
def obtenir_document(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    doc = session.get(
        Document,
        document_id,
        options=[
            joinedload(Document.categorie),
            joinedload(Document.metadonnees),
        ],
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)
    fiche = _serialize(
        doc,
        conformite.regles_par_categorie(session, {doc.categorie_id} if doc.categorie_id else set()),
        _libelles_references(session, [doc]),
        _champs_attendus(session, doc),
        _derniere_modification(session, doc),
        versions.compter(session, [doc]),
        _affichages_par_document(session, [doc]),
    )
    fiche.champs_fiche = _champs_de_la_fiche(session, doc)
    # Qui a ouvert ce papier, et quand (§21.16). Écrit au plus une fois par
    # quart d'heure et par personne : ouvrir une fiche, la refermer, la rouvrir
    # est un seul geste, et vingt lignes identiques ne diraient rien de plus.
    if audit.consultation(session, user, doc.id, {"nom_fichier": doc.nom_fichier}):
        session.commit()
    return fiche


def _champs_de_la_fiche(session: Session, doc: Document) -> list[dict]:
    """
    Les métadonnées à montrer sur la fiche, **y compris celles qui sont vides**
    (§19.20).

    N'afficher que ce qui est rempli répond à la mauvaise question : quand on
    ouvre une fiche, on cherche souvent ce qui **manque**. Une case vide se voit
    et se réclame ; une case absente laisse croire que le champ n'existe pas.

    La liste vient des **colonnes du type** — celles que l'administrateur a
    réglées, c'est-à-dire ce qu'un document de cette sorte porte —, complétée par
    ce que le document porte réellement : une valeur extraite par une règle
    n'ayant pas de colonne doit se voir quand même, sinon elle n'existe nulle part.

    `masquee` marque les colonnes retirées du tableau. Le type dit lui-même
    (`fiche_champs_masques`, §19.21) si elles se voient encore ici : masquer une
    colonne d'un tableau qu'on parcourt n'est pas la même décision que la cacher
    sur la fiche du document, mais c'est la même personne qui la prend — celle
    qui règle les colonnes, pour tout le foyer.
    """
    from .db import ColonneCategorie

    lignes = []
    vus = set()
    # Clés que le type a retirées du tableau sans vouloir les revoir ici : elles
    # ne doivent pas revenir par la porte de derrière, celle des métadonnées que
    # le document porte sans colonne déclarée.
    ecartees: set[str] = set()

    def ajouter(cle: str, libelle: str, masquee: bool = False):
        if cle in vus:
            return
        # `date_document` a une colonne sur le document ; la métadonnée du même
        # nom n'en est que l'ombre, écrite par la règle pour porter « corrigé à
        # la main » (§18.45, §22.79). Elle n'a pas à faire une seconde ligne.
        if cle == "date_document":
            return
        vus.add(cle)
        meta = next((m for m in doc.metadonnees if m.cle == cle), None)
        lignes.append({
            "cle": cle,
            "libelle": libelle,
            "valeur": (meta.valeur if meta else None) or None,
            "reference": (doc_libelles or {}).get(cle),
            "masquee": masquee,
            # une valeur sans règle d'origine a été saisie par quelqu'un (§18.45)
            "saisie": bool(meta and meta.regle_id is None and (meta.valeur or "").strip()),
        })

    doc_libelles = _libelles_references(session, [doc]).get(doc.id, {})

    if doc.categorie_id:
        configurees = {
            c.champ: c for c in session.query(ColonneCategorie)
            .filter(ColonneCategorie.categorie_id == doc.categorie_id)
            .order_by(ColonneCategorie.ordre, ColonneCategorie.id)
        }
        for champ in colonnes.pour_categorie(session, doc.categorie_id):
            if champ["champ"].startswith(moteur_filtres.PREFIXE_META):
                ajouter(champ["champ"][len(moteur_filtres.PREFIXE_META):], champ["libelle"])
        # les colonnes retirées du tableau : rendues si le type le veut, et
        # signalées pour qu'on sache qu'elles ne sont pas dans la liste
        categorie = session.get(Categorie, doc.categorie_id)
        montrer = bool(categorie is not None and categorie.fiche_champs_masques)
        for champ, ligne in configurees.items():
            if not champ.startswith(moteur_filtres.PREFIXE_META) or ligne.visible:
                continue
            cle = champ[len(moteur_filtres.PREFIXE_META):]
            if montrer:
                ajouter(cle, ligne.libelle or cle.replace("_", " ").capitalize(),
                        masquee=True)
            else:
                ecartees.add(cle)

    # ce que le document porte et qu'aucune colonne n'annonce
    for meta in sorted(doc.metadonnees, key=lambda m: m.cle):
        if meta.cle in ecartees:
            continue
        ajouter(meta.cle, meta.cle.replace("_", " ").capitalize())

    return lignes


@app.get("/documents/{document_id}/texte")
def lire_texte_ocr(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Le texte tel que l'océrisation l'a produit (§18.37).

    C'est la matière première des règles d'extraction : tant qu'on ne l'a pas
    sous les yeux, écrire une expression revient à deviner ce que la machine a
    lu — les espaces qu'elle a semés dans un numéro, le « O » qu'elle a mis pour
    un zéro, la ligne qu'elle a coupée en deux.

    Rendu avec ses lignes découpées et la position de chaque caractère dans le
    texte entier : c'est ce dont une expression parle, et l'écran peut alors
    l'afficher en grille.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)

    texte = doc.texte_ocr or ""
    lignes, position = [], 0
    for numero, contenu in enumerate(texte.split("\n"), start=1):
        lignes.append({"numero": numero, "debut": position, "texte": contenu})
        position += len(contenu) + 1      # +1 pour le saut de ligne

    return {
        "document_id": doc.id,
        "longueur": len(texte),
        "lignes": lignes,
        "vide": not texte.strip(),
    }


@app.post("/documents/{document_id}/tester-extraction")
def tester_extraction(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Rejoue les règles d'extraction sur ce document **sans rien enregistrer**
    (§18.41).

    Écrire une règle et devoir relancer un traitement complet pour savoir si elle
    attrape quelque chose est la boucle la plus décourageante du projet. Cette
    route dit, en une fois : ce que chaque règle trouve, ce que la catégorie
    attend, et ce qui manque encore.

    Rien n'est écrit — ni métadonnée, ni catégorie, ni journal. C'est un essai,
    et un essai qui modifierait la fiche ne serait plus un essai.
    """
    from .db import RegleExtraction
    from .regex_engine import _valeur_de_la_regle, _convertir_valeur, profil_applicable

    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)

    texte = doc.texte_ocr or ""
    # Le jeu qui s'applique à ce document (§19.6). L'essai doit le dire : sans
    # cela, on chercherait longtemps pourquoi une règle écrite dans un autre jeu
    # « ne marche pas » — elle marche, elle ne s'applique simplement pas ici.
    profil = profil_applicable(session, doc, texte)
    regles = [] if profil is None else (
        session.query(RegleExtraction)
        .filter(RegleExtraction.actif.is_(True),
                RegleExtraction.profil_id == profil.id)
        .order_by(RegleExtraction.priorite.asc())
        .all())

    resultats, retenues = [], {}
    for regle in regles:
        brute = _valeur_de_la_regle(regle, texte)
        valeur = _convertir_valeur(brute, regle.type_champ) if brute is not None else None
        # La priorité décide : la première règle à renseigner un champ l'emporte,
        # exactement comme au traitement réel.
        premiere = valeur is not None and regle.champ_cible not in retenues
        if premiere:
            retenues[regle.champ_cible] = valeur
        resultats.append({
            "regle": regle.nom,
            "champ": regle.champ_cible,
            "fonction": regle.fonction,
            "priorite": regle.priorite,
            "trouve": valeur is not None,
            "valeur": valeur,
            "brute": brute if brute != valeur else None,
            "retenue": premiere,
        })

    attendus = _champs_attendus(session, doc)
    manquants = []
    for champ in attendus:
        cle = champ["champ"]
        nom = cle[len("meta:"):] if cle.startswith("meta:") else cle
        present = (nom in retenues
                   or any(m.cle == nom and (m.valeur or "").strip() for m in doc.metadonnees)
                   or (cle == "date_document" and doc.date_document))
        if not present:
            manquants.append({"champ": cle, "libelle": champ.get("libelle") or nom,
                              "obligatoire": bool(champ.get("obligatoire"))})

    return {
        "document_id": doc.id,
        "texte_vide": not texte.strip(),
        "jeu": None if profil is None else {
            "id": profil.id, "nom": profil.nom, "generique": bool(profil.generique),
            "reconnu": bool((profil.reconnaissance or "").strip()),
        },
        "regles": resultats,
        "valeurs_retenues": retenues,
        "attendus": attendus,
        "manquants": manquants,
    }


@app.get("/documents/{document_id}/apercu")
def apercu_document(
    document_id: int,
    page: int = 1,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Une image d'une page du document — la première par défaut (§19.20).

    `page` sert à l'outil qui apprend une règle en la montrant (§22.75) : une
    facture porte parfois sa référence en deuxième page, et il n'y avait aucun
    moyen d'y arriver.

    Ouvrir une fiche chargeait le PDF entier — plusieurs mégaoctets pour
    reconnaître un document, à chaque clic de ligne. L'image suffit la plupart du
    temps ; le PDF reste à un clic pour qui veut vraiment lire.

    Même droit que le fichier : une image de la page **est** le document, en plus
    petit. La restreindre moins serait ouvrir une porte de derrière.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session, action=droits.TELECHARGER)

    image = (apercus.obtenir(doc.id, doc.chemin_stockage, doc.hash_sha256, max(1, page))
             if doc.chemin_stockage else None)
    if not image:
        raise HTTPException(
            status_code=404,
            detail="Aperçu indisponible pour ce document.")
    return FileResponse(str(image), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


class ResultatRechercheOut(BaseModel):
    document: DocumentOut
    score: int
    raisons: list[dict]


@app.get("/recherche")
def recherche_globale(
    q: str,
    perimetre: str = "tout",
    categorie_id: Optional[int] = None,
    filtres: Optional[str] = None,
    limite: int = 50,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Chercher sans savoir où (§21.2).

    Le registre demandait de choisir un type, puis de filtrer colonne par
    colonne : le geste de quelqu'un qui sait déjà où il range. Celui qui cherche
    n'a qu'un mot, et ne sait pas dans quel classement il tombe.

    **Le périmètre se choisit**, à la manière d'un client de messagerie :

      * `tout`        — toute la GED ;
      * `classement`  — le type ouvert, sous-dossiers compris ;
      * `vue`         — ce que les filtres en cours laissent voir.

    Le périmètre est appliqué **avant** la recherche, et les droits avant tout le
    reste : un score ne doit jamais révéler l'existence d'un document.
    """
    perimetre = moteur_recherche.perimetre_valide(perimetre)
    base = _filtrer_par_droits(session.query(Document.id), session, user)

    if perimetre in ("classement", "vue") and categorie_id is not None:
        base = base.filter(
            Document.categorie_id.in_(ids_categorie_et_descendants(session, categorie_id)))
    if perimetre == "vue" and filtres:
        try:
            criteres = [moteur_filtres.Filtre(**f) for f in json.loads(filtres)]
            base = moteur_filtres.appliquer(base, session, criteres)
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=422, detail=str(erreur))
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Filtres illisibles")

    trouvailles = moteur_recherche.chercher(session, base, q, limite=max(1, min(limite, 200)))
    if not trouvailles:
        return {"perimetre": perimetre, "resultats": []}

    identifiants = [t["document_id"] for t in trouvailles]
    documents = {
        d.id: d for d in session.query(Document)
        .options(joinedload(Document.categorie),
                 joinedload(Document.metadonnees))
        .filter(Document.id.in_(identifiants))
    }
    regles = conformite.regles_par_categorie(
        session, {d.categorie_id for d in documents.values() if d.categorie_id})
    libelles = _libelles_references(session, list(documents.values()))

    return {
        "perimetre": perimetre,
        "resultats": [{
            "document": _serialize(documents[t["document_id"]], regles, libelles),
            "score": t["score"],
            "raisons": t["raisons"],
        } for t in trouvailles if t["document_id"] in documents],
    }


async def _recevoir_fichier(fichier: UploadFile) -> tuple[Path, str]:
    """
    Écrit un fichier déposé à la main dans le dossier des dépôts manuels, et rend
    `(chemin, nom d'origine)`.

    C'est le **seul endroit** où l'API pose un fichier reçu : elle le dépose, le
    serveur de travaux le reprend, l'océrise et l'archive. Les archives restent
    hors de sa portée, et il n'y a pas deux chemins d'entrée à tenir — celui de
    la fiche simple (§22.1) et celui de la pièce jointe (§22.2) sont le même.

    Un sous-dossier par dépôt, et le fichier y garde **son** nom : c'est celui que
    portera le document, et « acte_notarie.pdf » se lit mieux que
    « 20260905231500_acte_notarie.pdf ». Deux dépôts du même fichier sont deux
    gestes distincts : chacun son dossier, aucun n'écrase l'autre avant que le
    serveur de travaux ne l'ait repris.
    """
    nom = os.path.basename(fichier.filename or "").strip()
    extension = os.path.splitext(nom)[1].lower()
    if extension not in config.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Format non pris en charge (attendu : "
                   f"{', '.join(sorted(config.SUPPORTED_EXTENSIONS))}).")

    dossier = Path(config.DEPOTS_MANUELS_FOLDER) / uuid.uuid4().hex
    dossier.mkdir(parents=True, exist_ok=True)
    destination = dossier / f"{depots.normaliser(Path(nom).stem)}{extension}"

    taille = 0
    try:
        with open(destination, "wb") as sortie:
            while morceau := await fichier.read(1024 * 1024):
                taille += len(morceau)
                if taille > config.TAILLE_MAX_DEPOT:
                    sortie.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux (limite : "
                               f"{config.TAILLE_MAX_DEPOT // (1024 * 1024)} Mo).")
                sortie.write(morceau)
    except HTTPException:
        raise
    except OSError as erreur:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Écriture impossible : {erreur}")
    finally:
        if not destination.is_file():
            shutil.rmtree(dossier, ignore_errors=True)
    return destination, nom


@app.post("/fiches/{categorie_id}/documents")
async def deposer_dans_une_fiche(
    categorie_id: int,
    fichier: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Glisser un fichier dans une fiche simple (§22.1).

    Une fiche n'a pas de dossier sous `ocr_wait` : rien n'y entre tout seul, et
    c'est le sens même de cette nature. Le fichier arrive donc par ici, et son
    **type est dit au dépôt** plutôt que déduit de l'endroit où on l'a posé.

    L'API écrit le fichier dans le seul dossier qu'elle ait en écriture, puis
    passe la main : c'est le serveur de travaux qui archive, océrise et crée le
    document — les archives restent hors de portée de l'API, et il n'y a pas deux
    chemins d'entrée à tenir. Le document apparaît dans la fiche quelques
    secondes plus tard, prêt à recevoir les valeurs qu'on saisira à la main.
    """
    fiche = session.get(Categorie, categorie_id)
    if not fiche:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    if not categories.est_fiche(fiche):
        raise HTTPException(
            status_code=400,
            detail=f"« {fiche.nom} » n'est pas une fiche simple : les documents d'un "
                   f"type de document entrent par son dossier de dépôt.")
    try:
        droits.exiger(session, user, droits.DEPOSER, fiche.id)
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))

    destination, nom = await _recevoir_fichier(fichier)
    travail = Job(nom_fichier=nom, chemin_source=str(destination), statut="en_attente",
                  categorie_id=fiche.id)
    session.add(travail)
    audit.journaliser(session, user, "document.depot_manuel", "job", None,
                      details={"nom_fichier": nom, "categorie": fiche.nom})
    session.commit()
    session.refresh(travail)
    return {"ok": True, "job_id": travail.id, "nom_fichier": nom,
            "categorie": fiche.nom}


# La navigation d'une fiche de liaison (§20) a disparu au §22.1 : une fiche
# simple porte ses documents comme un type, et le registre les affiche. Il n'y a
# plus de table à parcourir avant d'arriver aux documents — c'était précisément
# le détour qui rendait l'ensemble inutilisable.


# Chemin propre, et non `/documents/groupes` : `/documents/{id}` est déclaré plus
# haut, et FastAPI lirait « groupes » comme un identifiant de document. Faire
# dépendre une route de son ordre de déclaration dans un fichier de 3 000 lignes
# est une fragilité qu'on paie une fois, tard.
# ------------------------------------------------------------
# Rappels et échéances (§21.9)
#
# Le besoin le plus concret d'une maison : contrôle technique, assurance,
# garantie, échéance de facture. Le document porte la date ; ce qui manquait,
# c'est que quelqu'un la regarde avant qu'elle ne passe.
# ------------------------------------------------------------

@app.get("/notifications")
def mes_notifications(non_lues: bool = False, limite: int = 100,
                      session: Session = Depends(get_session),
                      user: Utilisateur = Depends(auth.get_current_user)):
    """
    Les rappels du foyer, plus ceux qui me sont adressés.

    Une notification s'adresse au **foyer** dans le cas ordinaire : « le contrôle
    technique arrive à terme » ne concerne pas un compte en particulier, et
    l'adresser à quelqu'un reviendrait à décider qui s'en occupe.
    """
    return {"non_lues": notifs.compter_non_lues(session, user),
            "notifications": notifs.lister(session, user, max(1, min(limite, 500)), non_lues)}


@app.post("/notifications/{notification_id}/lue")
def marquer_notification_lue(notification_id: int,
                             session: Session = Depends(get_session),
                             user: Utilisateur = Depends(auth.get_current_user)):
    """
    Une notification du foyer lue par quelqu'un l'est pour tout le monde : c'est
    un tableau d'affichage, pas une boîte aux lettres.
    """
    if not notifs.marquer_lue(session, user, notification_id):
        raise HTTPException(status_code=404, detail="Notification introuvable")
    session.commit()
    return {"ok": True, "non_lues": notifs.compter_non_lues(session, user)}


@app.post("/notifications/tout-lu")
def tout_marquer_lu(session: Session = Depends(get_session),
                    user: Utilisateur = Depends(auth.get_current_user)):
    nombre = notifs.tout_marquer_lu(session, user)
    session.commit()
    return {"ok": True, "marquees": nombre}


@app.get("/echeances")
def prochaines_echeances(horizon: int = 90, session: Session = Depends(get_session),
                         user: Utilisateur = Depends(auth.get_current_user)):
    """
    Ce qui arrive à terme, la plus urgente d'abord — dépassée en tête.

    Restreint aux documents visibles : une échéance est une information sur un
    document, elle se cache comme lui.
    """
    base = _filtrer_par_droits(session.query(Document.id), session, user)
    return {"echeances": echeances.prochaines(session, base, horizon)}


@app.get("/groupes")
def replier_le_registre(
    champ: str,
    categorie_id: Optional[int] = None,
    filtres: Optional[str] = None,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Les branches d'un niveau de repli, avec leur décompte (§21.6).

    Le registre est un tableau plat ; le replier sur un critère — l'année,
    l'émetteur, le véhicule concerné — le rend parcourable sans écrire un seul
    filtre. Une branche n'est **qu'un filtre** : le critère qu'elle pose est rendu
    avec elle, l'interface l'ajoute à la liste, et rien ne change côté droits,
    recherche ou pagination.

    Les décomptes ne portent que sur les documents que l'appelant a le droit de
    voir : un chiffre est déjà un renseignement.
    """
    base = _filtrer_par_droits(session.query(Document.id), session, user)
    if categorie_id is not None:
        base = base.filter(
            Document.categorie_id.in_(ids_categorie_et_descendants(session, categorie_id)))
    if filtres:
        try:
            criteres = [moteur_filtres.Filtre(**f) for f in json.loads(filtres)]
            base = moteur_filtres.appliquer(base, session, criteres)
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=422, detail=str(erreur))
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Filtres illisibles")

    try:
        champ = groupes.champ_valide(session, champ)
        trouvees = groupes.branches(session, base, champ)
    except moteur_filtres.FiltreInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))

    return {
        "champ": champ,
        "branches": [{**branche, "critere": groupes.critere(champ, branche["valeur"])}
                     for branche in trouvees],
    }


@app.get("/documents/{document_id}/mots")
def mots_du_document(
    document_id: int,
    page: int = 1,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Où sont les mots dans la page (§21.5, bêta).

    Sert à **désigner** une valeur sur l'image du document plutôt qu'à décrire sa
    position par une expression régulière écrite à l'aveugle. Les rectangles sont
    rapportés à la page (0 à 1) : l'interface affiche une miniature dont elle
    seule connaît la taille, et lui imposer une conversion reviendrait à lui
    faire deviner la résolution du rendu.

    Même droit que l'aperçu : lire les mots d'un document, c'est le lire.
    """
    from . import mots as positions

    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session, action=droits.TELECHARGER)

    lecture = positions.lire(doc.chemin_stockage, max(1, page))
    if lecture is not None:
        # Combien de pages en tout (§22.75) : sans quoi l'écran ne sait pas
        # jusqu'où on peut avancer, et fait cliquer vers le vide.
        lecture = {**lecture, "page": max(1, page),
                   "pages": positions.nombre_de_pages(doc.chemin_stockage)}
    if lecture is None:
        raise HTTPException(
            status_code=404,
            detail="Les positions ne sont pas lisibles pour ce document.")
    if not lecture["mots"]:
        # Un document sans couche de texte n'est pas une erreur : il n'a pas été
        # océrisé, et c'est une information utile à qui règle les règles.
        return {**lecture, "avertissement": "Ce document ne porte aucune couche de texte : "
                                            "il n'a pas été océrisé, ou l'océrisation n'a "
                                            "rien reconnu."}
    return lecture


class EntreeIn(BaseModel):
    """
    Une entrée saisie à la main : les valeurs des champs que sa fiche déclare.

    Pas d'intitulé ni de date en propre : **ce sont des champs comme les autres**,
    et s'ils comptent pour ce foyer-là, ils se déclarent (§22.10). Inventer deux
    cases universelles obligerait tout le monde à remplir ce qui n'a de sens que
    pour certains.
    """
    categorie_id: int
    valeurs: dict = {}
    # Ce que cette entrée retient de chaque valeur de table (§22.61) :
    # `{champ: [colonnes]}`. Absent, elle montre tout ce que le champ propose.
    affichages: dict = {}


@app.get("/categories/{categorie_id}/champs")
def champs_de_la_categorie(
    categorie_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Ce qu'un document de cette catégorie porte, rempli ou non (§22.7).

    `champs_manquants` ne dit que ce qui manque : de quoi signaler un document
    incomplet, pas de quoi construire un formulaire. Pour **créer** une entrée,
    il faut savoir tout ce que la catégorie attend, et comment chaque champ se
    saisit — liste adossée à une table, date, texte libre.
    """
    categorie = session.get(Categorie, categorie_id)
    if not categorie:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    if not droits.accorde(session, user, droits.VOIR, categorie.id):
        raise HTTPException(status_code=403, detail=f"Accès refusé à « {categorie.nom} ».")
    factice = Document(categorie_id=categorie.id)
    return {"categorie": {"id": categorie.id, "nom": categorie.nom,
                          "nature": categories.nature_de(categorie)},
            "champs": _champs_attendus(session, factice)}


def _libelle_reference(session: Session, brute: str, regle: dict) -> str:
    """
    « usr_vehicules:3 » → « Clio III - AA-123-BB ».

    La fonction manquait (§22.61) : `_nom_dune_entree` l'appelait sans qu'elle
    existe nulle part. Le défaut ne se voyait que si l'un des deux premiers
    champs remplis pointait une table — la création tombait alors en 500. Elle
    lit la ligne comme le reste de l'application, avec la composition choisie
    par le champ (§22.59), pour qu'une entrée porte le nom qu'on lui verra.
    """
    table, identifiant = base_donnees.decouper_valeur(
        brute, (regle.get("sources") or [None])[0])
    if not table:
        return brute
    try:
        libelles = base_donnees.libelles_par_id(
            session, table, {str(identifiant)},
            affichage=regle.get("colonnes_affichees") or None)
    except Exception:
        # Une source disparue ne doit pas empêcher de nommer l'entrée : la
        # valeur brute reste lisible, et c'est mieux que rien.
        return brute
    return libelles.get(str(identifiant)) or brute


def _nom_dune_entree(session: Session, regles: list[dict], valeurs: dict) -> str:
    """
    L'intitulé d'une entrée : les premières valeurs saisies, dans l'ordre déclaré.

    Rien n'est inventé — pas de case « Intitulé » ajoutée d'office. Ce qui nomme
    une entrée est ce que le foyer a déclaré en premier, et une référence à une
    table s'y écrit par son libellé : « Renault Clio », pas « usr_vehicules:3 ».
    """
    morceaux = []
    for regle in regles:
        brute = str(valeurs.get(regle["champ"], "") or "").strip()
        if not brute:
            continue
        morceaux.append(_libelle_reference(session, brute, regle)
                        if base_donnees.SEPARATEUR_SOURCE in brute else brute)
        if len(morceaux) == 2:
            break
    return " — ".join(morceaux)[:255] or f"Entrée du {date.today().isoformat()}"


@app.post("/documents", response_model=DocumentOut)
def creer_une_entree(
    corps: EntreeIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Crée une entrée à la main, **sans fichier obligatoire** (§22.7).

    Une fiche simple sert à noter ce qu'un foyer garde et qui n'a pas toujours de
    papier : un contrat verbal, une garantie annoncée au téléphone, le code d'un
    cadenas. Jusqu'ici il fallait un fichier pour créer une ligne — on n'avait
    donc nulle part où l'écrire.

    Le document devient l'unité de **ce que l'on sait** ; le fichier est une
    pièce parmi d'autres (§22.2), et l'on peut la glisser plus tard, ou jamais.

    Réservé aux **fiches simples** : un type de document décrit ce qui arrive par
    son dossier de dépôt, et y créer une ligne vide serait un moyen détourné de
    contourner le classement par l'emplacement (§19.3).
    """
    categorie = session.get(Categorie, corps.categorie_id)
    if not categorie:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    if not categories.est_fiche(categorie):
        raise HTTPException(
            status_code=400,
            detail=f"« {categorie.nom} » n'est pas une fiche simple : les documents d'un "
                   f"type de document entrent par son dossier de dépôt.")
    try:
        droits.exiger(session, user, droits.DEPOSER, categorie.id)
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))

    regles = _champs_attendus(session, Document(categorie_id=categorie.id))
    if not regles:
        raise HTTPException(
            status_code=400,
            detail=f"« {categorie.nom} » ne déclare aucun champ : il n'y a rien à saisir. "
                   f"Déclarez ce qu'une entrée doit porter dans Administration → Champs "
                   f"attendus.")

    valeurs = {cle: valeur for cle, valeur in (corps.valeurs or {}).items()
               if str(valeur or "").strip()}
    manquants_obligatoires = [
        regle["libelle"] for regle in regles
        if regle["obligatoire"] and not str(valeurs.get(regle["champ"], "")).strip()]
    if manquants_obligatoires:
        raise HTTPException(
            status_code=422,
            detail=f"Champs obligatoires non renseignés : "
                   f"{', '.join(manquants_obligatoires)}.")

    # Le nom vient de ce qui a été saisi : c'est ce que l'écran affichera, et
    # c'est au foyer de dire ce qui nomme une entrée — en déclarant ses champs
    # dans l'ordre où il les lit.
    nom = _nom_dune_entree(session, regles, valeurs)

    document = Document(nom_fichier=nom, categorie_id=categorie.id, statut="traite")
    date_saisie = valeurs.pop("date_document", None)
    if date_saisie:
        try:
            document.date_document = date.fromisoformat(str(date_saisie))
        except ValueError:
            raise HTTPException(status_code=422,
                                detail="Date illisible (attendu : AAAA-MM-JJ).")
    session.add(document)
    session.flush()

    _ecrire_metadonnees(session, document, {
        cle[len(moteur_filtres.PREFIXE_META):]: valeur
        for cle, valeur in valeurs.items() if cle.startswith(moteur_filtres.PREFIXE_META)})
    _ecrire_affichages(session, document, corps.affichages)
    manquants = _reevaluer_conformite(session, document)
    audit.journaliser(session, user, "document.creation_manuelle", "document", document.id,
                      details={"nom_fichier": nom, "categorie": categorie.nom})
    session.commit()
    session.refresh(document)

    fiche = _serialize(
        document,
        conformite.regles_par_categorie(session, {categorie.id}),
        _libelles_references(session, [document]),
        _champs_attendus(session, document),
        _derniere_modification(session, document),
        versions.compter(session, [document]),
        _affichages_par_document(session, [document]),
    )
    fiche.champs_fiche = _champs_de_la_fiche(session, document)
    fiche.champs_manquants = manquants
    return fiche


# ------------------------------------------------------------
# Les pièces d'un document (§22.2)
#
# Un document **était** un fichier : réunir une facture, sa garantie et le bon de
# livraison demandait trois documents et un lien entre eux — trois fiches à
# remplir, trois classements à décider, pour un seul achat. Une fiche porte
# désormais N fichiers, comme le « docpak » d'EzGED, et les champs sont remplis
# une fois.
#
# Une pièce n'est pas une version : la version est le **même papier redéposé**,
# la pièce est un **autre papier du même dossier**.
# ------------------------------------------------------------

class PieceOut(BaseModel):
    id: int
    nom_fichier: str
    ordre: int
    principale: bool
    taille_octets: Optional[int] = None
    date_ajout: Optional[datetime] = None


def _piece_de(session: Session, doc: Document, piece_id: int) -> PieceDocument:
    """La pièce demandée, si elle appartient bien à ce document."""
    piece = session.get(PieceDocument, piece_id)
    if piece is None or piece.document_id != doc.id:
        raise HTTPException(status_code=404, detail="Pièce introuvable")
    return piece


def _serialiser_piece(piece: PieceDocument) -> PieceOut:
    return PieceOut(id=piece.id, nom_fichier=piece.nom_fichier, ordre=piece.ordre,
                    principale=bool(piece.principale),
                    taille_octets=piece.taille_octets, date_ajout=piece.date_ajout)


@app.get("/documents/{document_id}/pieces", response_model=list[PieceOut])
def lister_pieces(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """Les fichiers que porte ce document, dans leur ordre d'affichage."""
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)
    return [_serialiser_piece(p) for p in pieces.lister(session, doc)]


@app.get("/documents/{document_id}/pieces/{piece_id}/fichier")
def telecharger_piece(
    document_id: int,
    piece_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Le fichier d'une pièce. Même droit que le document lui-même : une pièce en
    fait partie, et la restreindre moins ouvrirait une porte de derrière.

    Servi **pour être lu** — type réel, disposition « inline » : c'est une page
    qu'on regarde, pas un fichier qu'on collectionne.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session, action=droits.TELECHARGER)
    piece = _piece_de(session, doc, piece_id)
    if not os.path.isfile(piece.chemin_stockage):
        raise HTTPException(status_code=404, detail="Fichier archivé introuvable.")
    audit.journaliser(session, user, "document.telechargement", "document", doc.id,
                      details={"piece_id": piece.id, "nom_fichier": piece.nom_fichier})
    session.commit()
    return FileResponse(
        piece.chemin_stockage, media_type=config.type_mime(piece.chemin_stockage),
        headers={"Content-Disposition":
                 f'inline; filename="{config.nom_pour_entete(piece.nom_fichier)}"'})


@app.get("/documents/{document_id}/pieces/{piece_id}/apercu")
def apercu_piece(
    document_id: int,
    piece_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    L'image de première page d'une pièce, pour la reconnaître sans l'ouvrir.

    Le cache est indexé par l'empreinte, propre à chaque pièce : deux pièces d'un
    même document ne se marchent pas dessus, et une pièce rescannée change
    d'image sans qu'on ait à vider quoi que ce soit.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session, action=droits.TELECHARGER)
    piece = _piece_de(session, doc, piece_id)

    image = apercus.obtenir(doc.id, piece.chemin_stockage, piece.hash_sha256)
    if not image:
        raise HTTPException(status_code=404, detail="Aperçu indisponible pour cette pièce.")
    return FileResponse(str(image), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.post("/documents/{document_id}/pieces")
async def joindre_une_piece(
    document_id: int,
    fichier: UploadFile = File(...),
    remplace_piece_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Joindre un fichier à un document existant (§22.2), ou **rescanner l'une de
    ses pièces** (§22.3).

    C'est la seule question qu'on ne puisse pas deviner : le même PDF est une
    pièce de plus ou une nouvelle version d'une pièce existante selon ce qu'on
    vient de faire. On la pose donc au dépôt — `remplace_piece_id` vide veut dire
    « une pièce de plus », qui est le cas courant.

    Comme le dépôt dans une fiche simple (§22.1), l'API écrit le fichier dans le
    seul dossier qu'elle ait en écriture et passe la main : c'est le serveur de
    travaux qui océrise, archive et attache. Le travail porte la consigne — « au
    document nº12 », « en remplacement de la pièce nº7 » —, car ni le dossier ni
    le fichier ne la disent.

    Ce qui **ne se rejoue pas** : les règles d'extraction et le contrôle des
    champs attendus. Les valeurs du document ont été posées quand il est entré ;
    une garantie jointe à une facture n'a pas à en redécider la date.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session)
    remplacee = _piece_de(session, doc, remplace_piece_id) if remplace_piece_id else None

    destination, nom = await _recevoir_fichier(fichier)
    travail = Job(nom_fichier=nom, chemin_source=str(destination), statut="en_attente",
                  piece_pour_document_id=doc.id, categorie_id=doc.categorie_id,
                  version_pour_piece_id=remplacee.id if remplacee else None)
    session.add(travail)
    audit.journaliser(
        session, user,
        "document.piece_remplacee" if remplacee else "document.piece_ajoutee",
        "document", doc.id,
        details={"nom_fichier": nom,
                 **({"piece": remplacee.nom_fichier} if remplacee else {})})
    session.commit()
    session.refresh(travail)
    return {"ok": True, "job_id": travail.id, "nom_fichier": nom,
            "document_id": doc.id,
            "remplace_piece_id": remplacee.id if remplacee else None}


@app.put("/documents/{document_id}/pieces/{piece_id}/principale",
         response_model=list[PieceOut])
def rendre_piece_principale(
    document_id: int,
    piece_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Désigne la pièce que l'on voit partout ailleurs : celle que le registre
    ouvre, que la miniature montre, que l'export emporte.

    C'est le seul réglage qui compte vraiment sur un document à plusieurs
    pièces — savoir laquelle **est** le document quand on n'en montre qu'une.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session)
    piece = _piece_de(session, doc, piece_id)
    try:
        pieces.definir_principale(session, doc, piece)
    except pieces.PieceRefusee as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    audit.journaliser(session, user, "document.piece_principale", "document", doc.id,
                      details={"piece_id": piece.id, "nom_fichier": piece.nom_fichier})
    session.commit()
    return [_serialiser_piece(p) for p in pieces.lister(session, doc)]


@app.put("/documents/{document_id}/pieces/ordre", response_model=list[PieceOut])
def reordonner_pieces(
    document_id: int,
    ordre: list[int],
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """Range les pièces dans l'ordre donné ; celles qu'on omet suivent."""
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session)
    try:
        rangees = pieces.reordonner(session, doc, ordre)
    except pieces.PieceRefusee as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    session.commit()
    return [_serialiser_piece(p) for p in rangees]


@app.delete("/documents/{document_id}/pieces/{piece_id}")
def retirer_une_piece(
    document_id: int,
    piece_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Détache une pièce du document.

    Le fichier archivé n'est pas effacé dans la foulée : c'est la purge du
    serveur de travaux qui reprend ce que plus aucun document ne réclame — l'API
    n'a pas les archives en écriture, et c'est ce qui garantit qu'une erreur
    d'écran ne détruit rien.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session, action=droits.SUPPRIMER)
    piece = _piece_de(session, doc, piece_id)
    nom = piece.nom_fichier
    try:
        pieces.retirer(session, doc, piece)
    except pieces.PieceRefusee as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    audit.journaliser(session, user, "document.piece_retiree", "document", doc.id,
                      details={"nom_fichier": nom})
    session.commit()
    return {"ok": True, "pieces": [_serialiser_piece(p) for p in pieces.lister(session, doc)]}


# `GET /documents/{id}/lies` a disparu : il rendait le rapprochement automatique
# par valeur partagée (§19.19), retiré de l'écran à la demande de l'utilisateur —
# « c'est plus l'affichage côté frontend qui me dérange ». Il remplissait le
# panneau de liens que personne n'avait déclarés, et rendait illisible ce qui,
# lui, l'avait été : une pièce jointe, un lien de vue, un rattachement à la main.
#
# La **déduction** reste entière : les champs à source continuent de se remplir
# depuis le texte du document (`app/references_auto.py`), et le critère
# `lien:<table>` reste disponible aux filtres, aux vues et aux droits par
# branche. C'est l'affichage en réseau qui s'arrête, pas le rapprochement.


@app.get("/documents/{document_id}/rapprochements")
def rapprochements_du_document(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Ce que les **déclarations de type** rapprochent de ce document (§22.8).

    Un dossier porte un numéro, repris sur le devis, le bon de commande, le bon
    de livraison : ouvrir l'un montre les autres. Rien n'est deviné — c'est la
    différence avec le rapprochement automatique retiré au §22.7 : ce qui
    s'affiche ici a été paramétré, et l'on sait donc toujours pourquoi deux
    documents se retrouvent côte à côte.

    Restreint à ce que l'appelant peut voir : un rapprochement ne doit pas
    révéler l'existence d'un document hors de sa portée.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)

    base = _filtrer_par_droits(
        session.query(Document).options(joinedload(Document.categorie)), session, user)
    compte_versions = {}
    groupes = liens_type.rapprochements(session, doc, base)
    if groupes:
        compte_versions = versions.compter(
            session, [d for groupe in groupes for d in groupe["documents"]])

    return {"rapprochements": [{
        "libelle": groupe["libelle"],
        "champ": groupe["champ"],
        "valeur": groupe["valeur"],
        "documents": [{
            "id": d.id,
            "libelle": _libelle_document(d),
            "categorie": d.categorie.nom if d.categorie else None,
            "nom_fichier": d.nom_fichier,
            "date_document": str(d.date_document) if d.date_document else None,
            "nb_versions": compte_versions.get(d.id, 1),
        } for d in groupe["documents"]],
    } for groupe in groupes]}


# Ce qu'un sélecteur de documents montre sans qu'on ait rien tapé (§22.26), et à
# partir de quand il cherche. Deux nombres, et la raison est la même : un foyer
# accumule des milliers de documents, et une liste qu'on ne lit pas ne vaut pas
# la requête qu'elle coûte.
JOURS_RECENTS = 30
MIN_RECHERCHE_DOCUMENTS = 3


class AttachesIn(BaseModel):
    """Les documents attachés par un champ, dans l'ordre voulu."""
    documents: list[int] = []


@app.get("/documents/{document_id}/attaches")
def lister_attaches(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Les documents attachés à celui-ci **par un champ** (§22.11).

    Sous « Entretiens », ce sont les factures qu'on a choisies : ni des pièces de
    ce document (§22.2), ni un rapprochement déclaré (§22.8), mais le contenu
    d'un champ que le type déclare — avec son intitulé.

    Restreint à ce que l'appelant peut voir : un champ ne doit pas révéler
    l'existence d'un document hors de sa portée.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)
    return {"attaches": _attaches_du_document(session, doc, user)}


def _attaches_du_document(session: Session, doc: Document, user: Utilisateur) -> list[dict]:
    """`[{champ, libelle, documents}]` pour les champs qui attachent (§22.11)."""
    regles = {r.champ: r for r in session.query(RegleChampCategorie)
              .filter(RegleChampCategorie.categorie_id == doc.categorie_id,
                      RegleChampCategorie.attache_documents.is_(True))
              .order_by(RegleChampCategorie.ordre, RegleChampCategorie.champ)}
    if not regles:
        return []

    liens = (session.query(DocumentAttache)
             .filter(DocumentAttache.document_id == doc.id)
             .order_by(DocumentAttache.champ, DocumentAttache.ordre).all())
    # Les champs cochés en administration, pour que la fiche les montre comme le
    # sélecteur (§22.19) : « Orange · F-2026-777 » se lit, « Factures · mars » non.
    declares = {champ: [c.strip() for c in (r.documents_champs or "").split(",") if c.strip()]
                for champ, r in regles.items()}
    if not liens:
        return [{"champ": champ, "libelle": regle.libelle
                 or conformite.libelle_par_defaut(champ), "documents": []}
                for champ, regle in regles.items()]

    visibles = {d.id: d for d in _filtrer_par_droits(
        session.query(Document).options(joinedload(Document.categorie),
                                        joinedload(Document.metadonnees)), session, user)
        .filter(Document.id.in_([lien.document_attache_id for lien in liens]))}
    libelles = _libelles_references(session, list(visibles.values()))

    par_champ: dict[str, list] = {champ: [] for champ in regles}
    for lien in liens:
        cible = visibles.get(lien.document_attache_id)
        if cible is None or lien.champ not in par_champ:
            continue
        champs_montres = declares.get(lien.champ, [])
        par_champ[lien.champ].append({
            "id": cible.id,
            "libelle": _libelle_document(cible),
            "categorie": cible.categorie.nom if cible.categorie else None,
            "nom_fichier": cible.nom_fichier,
            "date_document": str(cible.date_document) if cible.date_document else None,
            "details": _details_du_document(
                cible, champs_montres,
                _intitules_des_champs(session, regles[lien.champ].documents_categorie_id,
                                      champs_montres),
                libelles.get(cible.id, {})),
        })
    return [{"champ": champ,
             "libelle": regle.libelle or conformite.libelle_par_defaut(champ),
             "documents": par_champ[champ]}
            for champ, regle in regles.items()]


@app.get("/categories/{categorie_id}/attachables")
def documents_attachables(
    categorie_id: int,
    champ: str,
    q: str = "",
    sauf: Optional[int] = None,
    limite: int = 20,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Ce qu'on peut attacher à ce champ-là (§22.14).

    La recherche est **bornée par la déclaration** : le type accepté, et les
    champs où chercher. Un champ qui propose toute la GED ne guide personne —
    « Factures liées » doit proposer des factures, cherchées par leur numéro ou
    leur émetteur, et non le mot « facture » dans le texte de tout le foyer.

    Interrogé par **catégorie** et non par document : on choisit aussi bien en
    créant une entrée, où le document n'existe pas encore. `sauf` écarte la fiche
    en cours d'édition — un document ne s'attache pas à lui-même.

    Sans champ déclaré, on retombe sur le nom du fichier et le texte reconnu :
    c'est le comportement d'avant, et il vaut mieux qu'un écran vide.

    **Ce qu'on montre sans rien taper** : les documents entrés dans le dernier
    mois, et eux seuls (§22.26). Un foyer en accumule des milliers ; les proposer
    tous coûterait une requête lourde à chaque ouverture de liste pour un
    résultat qu'on ne lit pas. Ce qu'on attache est presque toujours récent — et
    ce qui ne l'est pas se cherche.

    **Et la recherche attend trois caractères** : « fa » ramène la moitié de la
    GED, ce qui ne rend service à personne et fait travailler la base pour rien.
    En deçà, on rend la liste récente, en le disant.
    """
    categorie = session.get(Categorie, categorie_id)
    if not categorie:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    if not droits.accorde(session, user, droits.VOIR, categorie.id):
        raise HTTPException(status_code=403, detail=f"Accès refusé à « {categorie.nom} ».")

    regle = (session.query(RegleChampCategorie)
             .filter(RegleChampCategorie.categorie_id == categorie.id,
                     RegleChampCategorie.champ == champ,
                     RegleChampCategorie.attache_documents.is_(True)).first())
    if regle is None:
        raise HTTPException(status_code=404,
                            detail=f"« {champ} » n'attache pas de documents pour ce type.")

    query = _filtrer_par_droits(
        session.query(Document).options(joinedload(Document.categorie)), session, user)
    if sauf:
        query = query.filter(Document.id != sauf)
    if regle.documents_categorie_id:
        query = query.filter(Document.categorie_id.in_(
            ids_categorie_et_descendants(session, regle.documents_categorie_id)))

    champs = [c.strip() for c in (regle.documents_champs or "").split(",") if c.strip()]
    # Ce que les champs cherchés déclarent puiser : sans cela, chercher « Orange »
    # dans un champ « émetteur » ne trouvait rien — la métadonnée porte
    # `usr_emetteurs:5`, pas le nom (§22.19).
    sources_par_champ = _sources_des_champs(session, regle.documents_categorie_id, champs)

    terme = (q or "").strip()
    assez = len(terme) >= MIN_RECHERCHE_DOCUMENTS
    if not assez:
        # Rien de tapé (ou trop peu) : le dernier mois, et l'on dit que c'en est
        # un extrait — sans quoi on croirait la GED vide.
        query = query.filter(
            Document.date_import >= datetime.now() - timedelta(days=JOURS_RECENTS))
    if assez:
        conditions = []
        for cible in (champs or ["nom_fichier", "texte"]):
            try:
                conditions.append(moteur_filtres.condition(
                    session, moteur_filtres.Filtre(champ=cible, operateur="contient",
                                                   valeur=terme)))
            except moteur_filtres.FiltreInvalide:
                continue
            # Un champ adossé à une table se cherche par le **libellé** de sa
            # ligne : on traduit le mot en références, et l'on compare celles-ci.
            for source in sources_par_champ.get(cible, []):
                try:
                    lignes = base_donnees.options(session, source, terme, 25)
                except Exception:
                    continue
                for ligne in lignes:
                    reference = f"{source}{base_donnees.SEPARATEUR_SOURCE}{ligne['valeur']}"
                    try:
                        conditions.append(moteur_filtres.condition(
                            session, moteur_filtres.Filtre(champ=cible, operateur="egal",
                                                           valeur=reference)))
                    except moteur_filtres.FiltreInvalide:
                        continue
        if conditions:
            query = query.filter(or_(*conditions))

    trouves = (query.options(joinedload(Document.metadonnees))
               .order_by(Document.date_import.desc(), Document.id.desc())
               .limit(max(1, min(limite, 50))).all())

    # Ce que l'écran montre de chaque proposition : **les champs cochés**, et non
    # un intitulé générique. « Factures · 2026-03-23 » ne distingue pas deux
    # factures du même mois ; « Orange · F-2026-777 » les distingue (§22.19).
    libelles = _libelles_references(session, trouves)
    intitules = _intitules_des_champs(session, regle.documents_categorie_id, champs)
    return {
        # L'écran doit pouvoir dire **ce qu'il montre** : un extrait récent n'est
        # pas un résultat de recherche, et le confondre ferait croire que le
        # document cherché n'existe pas.
        "recents": not assez,
        "jours_recents": JOURS_RECENTS,
        "minimum_recherche": MIN_RECHERCHE_DOCUMENTS,
        "documents": [{
        "id": d.id,
        "libelle": _libelle_document(d),
        "categorie": d.categorie.nom if d.categorie else None,
        "nom_fichier": d.nom_fichier,
        "date_document": str(d.date_document) if d.date_document else None,
        "details": _details_du_document(d, champs, intitules, libelles.get(d.id, {})),
    } for d in trouves]}


def _sources_des_champs(session: Session, categorie_id: Optional[int],
                        champs: list[str]) -> dict:
    """`{champ: [tables]}` pour les champs du type cible qui puisent quelque part."""
    if not categorie_id or not champs:
        return {}
    regles = (session.query(RegleChampCategorie)
              .filter(RegleChampCategorie.categorie_id == categorie_id,
                      RegleChampCategorie.champ.in_(champs)))
    return {r.champ: conformite.sources_de(r) for r in regles if conformite.sources_de(r)}


def _intitules_des_champs(session: Session, categorie_id: Optional[int],
                          champs: list[str]) -> dict:
    """`{champ: intitulé}` — celui que l'administrateur a donné, à défaut le nom."""
    intitules = {}
    if categorie_id and champs:
        for regle in (session.query(RegleChampCategorie)
                      .filter(RegleChampCategorie.categorie_id == categorie_id,
                              RegleChampCategorie.champ.in_(champs))):
            intitules[regle.champ] = (regle.libelle
                                      or conformite.libelle_par_defaut(regle.champ))
    for champ in champs:
        intitules.setdefault(champ, conformite.libelle_par_defaut(champ))
    return intitules


def _details_du_document(doc: Document, champs: list[str], intitules: dict,
                         libelles: dict) -> list[dict]:
    """
    Les valeurs des champs cochés, telles qu'on les lit : une référence sort par
    son libellé — « Orange », pas « usr_emetteurs:5 ».
    """
    valeurs = {m.cle: m.valeur for m in doc.metadonnees}
    details = []
    for champ in champs:
        if champ.startswith(moteur_filtres.PREFIXE_META):
            cle = champ[len(moteur_filtres.PREFIXE_META):]
            valeur = libelles.get(cle) or valeurs.get(cle)
        elif champ == "nom_fichier":
            valeur = doc.nom_fichier
        elif champ == "date_document":
            valeur = str(doc.date_document) if doc.date_document else None
        else:
            valeur = getattr(doc, champ, None)
        if valeur:
            details.append({"libelle": intitules.get(champ, champ), "valeur": str(valeur)})
    return details


@app.put("/documents/{document_id}/attaches/{champ}")
def definir_attaches(
    document_id: int,
    champ: str,
    corps: AttachesIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Remplace le contenu d'un champ qui attache des documents.

    L'ordre donné est conservé : c'est celui dans lequel on les a choisis, et
    souvent celui dans lequel on veut les relire.

    On ne vérifie que le droit de **voir** les documents attachés : les attacher
    ne les modifie pas — c'est ce document-ci qu'on décrit.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session)

    regle = (session.query(RegleChampCategorie)
             .filter(RegleChampCategorie.categorie_id == doc.categorie_id,
                     RegleChampCategorie.champ == champ,
                     RegleChampCategorie.attache_documents.is_(True)).first())
    if regle is None:
        raise HTTPException(
            status_code=404,
            detail=f"« {champ} » n'attache pas de documents pour ce type. Déclarez-le "
                   f"dans Administration → Champs attendus.")

    demandes = [i for i in corps.documents if i != doc.id]
    if demandes:
        acceptables = _filtrer_par_droits(
            session.query(Document), session, user).filter(Document.id.in_(demandes))
        # Le type accepté est un contrôle, pas une aide à la saisie (§22.14) :
        # l'écran ne propose que ce qu'il faut, l'API refuse le reste.
        if regle.documents_categorie_id:
            acceptables = acceptables.filter(Document.categorie_id.in_(
                ids_categorie_et_descendants(session, regle.documents_categorie_id)))
        autorises = {d.id for d in acceptables}
        inconnus = [i for i in demandes if i not in autorises]
        if inconnus:
            raise HTTPException(
                status_code=404,
                detail=f"Document(s) introuvable(s) ou d'un type que ce champ n'accepte "
                       f"pas : {inconnus}")

    session.query(DocumentAttache).filter(
        DocumentAttache.document_id == doc.id,
        DocumentAttache.champ == champ).delete(synchronize_session=False)
    for rang, identifiant in enumerate(demandes, start=1):
        session.add(DocumentAttache(document_id=doc.id, champ=champ,
                                    document_attache_id=identifiant, ordre=rang,
                                    utilisateur_id=user.id))
    audit.journaliser(session, user, "document.attaches", "document", doc.id,
                      details={"champ": champ, "documents": demandes})
    session.commit()
    return {"ok": True, "attaches": _attaches_du_document(session, doc, user)}


# ------------------------------------------------------------
# Rattacher deux documents à la main (§22.4)
#
# Le rapprochement par valeur partagée réunit ce qui désigne la même chose, sans
# qu'on ait rien à faire. Reste ce qui ne partage rien et se répond quand même :
# un contrat et son avenant, une facture et son litige. Seul quelqu'un qui les a
# lus le sait — d'où ce lien posé à la main, et symétrique.
# ------------------------------------------------------------

class RattachementIn(BaseModel):
    document_id: int
    libelle: Optional[str] = None


@app.get("/documents/{document_id}/rattachements")
def lister_rattachements(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Ce qui a été rattaché à ce document, des deux côtés.

    Restreint à ce que l'appelant peut voir : un lien vers un document hors de sa
    portée ne lui apprendrait qu'une chose — qu'il existe —, ce qui est déjà un
    renseignement.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)

    couples = rattachements.voisins(session, doc.id)
    if not couples:
        return {"rattachements": []}

    visibles = {d.id: d for d in _filtrer_par_droits(
        session.query(Document).options(joinedload(Document.categorie)), session, user)
        .filter(Document.id.in_([identifiant for identifiant, _ in couples]))}

    return {"rattachements": [{
        "document_id": identifiant,
        "libelle": _libelle_document(visibles[identifiant]),
        "categorie": (visibles[identifiant].categorie.nom
                      if visibles[identifiant].categorie else None),
        "nom_fichier": visibles[identifiant].nom_fichier,
        "date_document": (str(visibles[identifiant].date_document)
                          if visibles[identifiant].date_document else None),
        "intitule": lien.libelle,
    } for identifiant, lien in couples if identifiant in visibles]}


@app.post("/documents/{document_id}/rattachements")
def rattacher_un_document(
    document_id: int,
    corps: RattachementIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Pose le lien entre deux documents. Il faut pouvoir **modifier les deux** :
    un lien se lit des deux côtés, le poser engage l'autre fiche autant que
    celle d'où l'on part.
    """
    doc = session.get(Document, document_id)
    autre = session.get(Document, corps.document_id)
    if not doc or not autre:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session)
    _verifier_acces(autre, user, ecriture=True, session=session)

    try:
        lien = rattachements.rattacher(session, doc, autre, corps.libelle, user.id)
    except rattachements.RattachementRefuse as refus:
        raise HTTPException(status_code=400, detail=str(refus))

    # Journalisé des deux côtés : l'historique d'une fiche doit dire ce qui lui
    # est arrivé, y compris quand c'est depuis l'autre qu'on a agi.
    for un, deux in ((doc, autre), (autre, doc)):
        audit.journaliser(session, user, "document.rattachement", "document", un.id,
                          details={"avec": deux.id, "nom_fichier": deux.nom_fichier,
                                   "intitule": lien.libelle})
    session.commit()
    return {"ok": True, "document_id": autre.id, "intitule": lien.libelle}


@app.delete("/documents/{document_id}/rattachements/{autre_id}")
def detacher_un_document(
    document_id: int,
    autre_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """Retire le lien. Détacher engage les deux fiches, comme le poser."""
    doc = session.get(Document, document_id)
    autre = session.get(Document, autre_id)
    if not doc or not autre:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session)
    _verifier_acces(autre, user, ecriture=True, session=session)

    if not rattachements.detacher(session, doc, autre.id):
        raise HTTPException(status_code=404, detail="Ces documents ne sont pas rattachés.")
    for un, deux in ((doc, autre), (autre, doc)):
        audit.journaliser(session, user, "document.detachement", "document", un.id,
                          details={"avec": deux.id, "nom_fichier": deux.nom_fichier})
    session.commit()
    return {"ok": True}


@app.get("/documents/{document_id}/versions")
def lister_versions_document(
    document_id: int,
    piece_id: Optional[int] = None,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Les dépôts successifs d'un document (§18.36), le plus récent d'abord —
    ceux d'une pièce seulement si on la nomme (§22.3).

    Ouvert à qui peut voir le document : consulter une ancienne version, c'est
    consulter le même document à une autre date.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)
    if piece_id:
        _piece_de(session, doc, piece_id)
    return versions.lister(session, document_id, piece_id)


@app.get("/documents/{document_id}/versions/{version_id}/fichier")
def telecharger_version(
    document_id: int,
    version_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """Le fichier d'une version donnée — une version qu'on ne peut pas ouvrir ne sert à rien."""
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session, action=droits.TELECHARGER)

    version = session.get(VersionDocument, version_id)
    if not version or version.document_id != document_id:
        raise HTTPException(status_code=404, detail="Version introuvable")
    if not version.chemin_stockage or not os.path.exists(version.chemin_stockage):
        raise HTTPException(
            status_code=410,
            detail="Le fichier de cette version n'est plus sur le disque.")
    return FileResponse(version.chemin_stockage, media_type="application/pdf",
                        filename=version.nom_fichier)


@app.delete("/documents/{document_id}/versions/{version_id}")
def supprimer_version(
    document_id: int,
    version_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Supprime une version et son fichier.

    Demande le droit « gérer les versions » sur le type du document (§19.12), et
    non plus le statut d'administrateur : c'est une destruction, mais elle porte
    sur une pièce précise — la restreindre par emplacement dit mieux qui doit
    pouvoir la faire qu'un interrupteur qui ouvre aussi l'export de l'archive.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session, action=droits.GERER_VERSIONS)
    version = session.get(VersionDocument, version_id)
    if not version or version.document_id != document_id:
        raise HTTPException(status_code=404, detail="Version introuvable")

    try:
        trace = versions.supprimer(session, version_id)
    except versions.SuppressionRefusee as erreur:
        raise HTTPException(status_code=409, detail=str(erreur))

    audit.journaliser(session, user, "document.version_supprimee", "document", document_id,
                      details=trace)
    session.commit()
    return {"ok": True, **trace}


class EvenementDocumentOut(BaseModel):
    id: int
    date_evenement: Optional[str] = None
    auteur: Optional[str] = None
    action: str
    details: Optional[dict] = None


class PageJournalDocumentOut(BaseModel):
    total: int
    evenements: list[EvenementDocumentOut]


@app.get("/documents/{document_id}/journal", response_model=PageJournalDocumentOut)
def journal_du_document(document_id: int, limite: int = 25, decalage: int = 0,
                        session: Session = Depends(get_session),
                        user: Utilisateur = Depends(auth.get_current_user)):
    """
    Ce qui est arrivé à **ce** document, pour qui a le droit de le consulter.

    Le journal général est réservé à l'administration ; celui-ci ne montre que
    les événements d'un document que l'on peut déjà voir, et n'apprend donc rien
    de plus à son lecteur — sinon qui a modifié quoi, et quand, ce qui est
    précisément l'utile quand on se demande d'où vient une valeur.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)

    # L'arrivée du document n'est pas un événement du journal : elle est inscrite
    # dans le document lui-même, par sa date d'import. On la restitue plutôt que
    # de la dupliquer en base — ainsi l'historique commence au dépôt, y compris
    # pour les documents archivés avant que ce journal n'existe.
    #
    # Elle compte dans le total et occupe la dernière place : la pagination doit
    # la traiter comme les autres, sinon elle réapparaîtrait sur chaque page ou
    # disparaîtrait de la dernière.
    query = (
        session.query(JournalAudit)
        .filter(JournalAudit.objet_type == "document", JournalAudit.objet_id == document_id)
    )
    total = query.count() + 1
    limite = max(1, min(limite, 200))
    decalage = max(0, decalage)

    evenements = (
        query.order_by(JournalAudit.date_evenement.desc(), JournalAudit.id.desc())
        .offset(decalage)
        .limit(limite)
        .all()
    )
    resultat = []

    arrivee = EvenementDocumentOut(
        id=0,
        date_evenement=doc.date_import.isoformat(timespec="seconds") if doc.date_import else None,
        auteur=None,
        action="document.depot",
        details={"nom_fichier": doc.nom_fichier},
    )
    for evenement in evenements:
        try:
            details = json.loads(evenement.details) if evenement.details else None
        except (ValueError, TypeError):
            details = {"brut": evenement.details}
        resultat.append(EvenementDocumentOut(
            id=evenement.id,
            date_evenement=evenement.date_evenement.isoformat(timespec="seconds")
            if evenement.date_evenement else None,
            auteur=evenement.utilisateur_email,
            action=evenement.action,
            details=details,
        ))
    if decalage + len(resultat) >= total - 1:
        resultat.append(arrivee)     # le dépôt ferme la dernière page
    return PageJournalDocumentOut(total=total, evenements=resultat)


@app.get("/documents/{document_id}/fichier")  # droit « télécharger » (§19.12)
def telecharger_fichier(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Sert le PDF océrisé pour aperçu/téléchargement côté frontend.

    Le droit est contrôlé **avant** l'existence du fichier : dans l'autre ordre,
    la réponse disait à qui n'y a pas droit si le fichier est là ou non. C'est
    peu, mais c'est déjà répondre à une question qu'on n'avait pas à lui laisser
    poser.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session, action=droits.TELECHARGER)
    # Une entrée saisie à la main n'a pas de fichier (§22.7) : le dire vaut mieux
    # qu'un aperçu gris qui tourne sans fin.
    if not doc.chemin_stockage:
        raise HTTPException(
            status_code=404,
            detail="Cette entrée n'a aucun fichier. Glissez-en un dans sa fiche pour "
                   "lui en joindre une pièce.")
    if not Path(doc.chemin_stockage).exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(
        doc.chemin_stockage,
        media_type="application/pdf",
        filename=doc.nom_fichier,
    )


# ------------------------------------------------------------
# Verrou d'édition (§17.21)
#
# Deux personnes du foyer peuvent ouvrir la même facture en même temps. Sans
# verrou, la dernière à enregistrer écrase l'autre sans que personne ne le
# sache. Le verrou est périssable : un onglet fermé sans un mot ne doit pas
# bloquer un document pour tout le monde.
# ------------------------------------------------------------

# Repli si la base ne répond pas : le verrou vaut mieux court que jamais.
DUREE_VERROU_MINUTES = 5


class VerrouOut(BaseModel):
    detenu: bool                      # par l'appelant
    par: Optional[str] = None         # qui le détient, si ce n'est pas lui
    expire_le: Optional[str] = None
    duree_minutes: int = DUREE_VERROU_MINUTES


def _verrou_actif(session: Session, document_id: int) -> Optional[VerrouDocument]:
    """Le verrou en cours, ou rien s'il n'existe pas ou qu'il a expiré."""
    verrou = session.query(VerrouDocument).filter_by(document_id=document_id).one_or_none()
    if not verrou:
        return None
    if verrou.date_expiration <= datetime.now():
        # Périmé : on le retire au passage plutôt que de le laisser traîner et
        # semer le doute la prochaine fois qu'on le lit.
        session.delete(verrou)
        session.commit()
        return None
    return verrou


@app.get("/documents/{document_id}/verrou", response_model=VerrouOut)
def etat_verrou(document_id: int, session: Session = Depends(get_session),
                user: Utilisateur = Depends(auth.get_current_user)):
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, session=session)
    verrou = _verrou_actif(session, document_id)
    if not verrou:
        return VerrouOut(detenu=False)
    return VerrouOut(
        detenu=verrou.utilisateur_id == user.id,
        par=None if verrou.utilisateur_id == user.id
        else (verrou.utilisateur.nom_affiche if verrou.utilisateur else "un autre compte"),
        expire_le=verrou.date_expiration.isoformat(timespec="seconds"),
    )


@app.post("/documents/{document_id}/verrou", response_model=VerrouOut)
def prendre_verrou(document_id: int, session: Session = Depends(get_session),
                   user: Utilisateur = Depends(auth.get_current_user)):
    """
    Prend le verrou, ou le prolonge s'il est déjà à soi.

    Un verrou détenu par quelqu'un d'autre et encore valide fait échouer la
    demande avec le nom du détenteur : mieux vaut dire « Marie modifie ce
    document » que laisser deux personnes travailler pour rien.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    _verifier_acces(doc, user, ecriture=True, session=session)

    verrou = _verrou_actif(session, document_id)
    if verrou and verrou.utilisateur_id != user.id:
        detenteur = verrou.utilisateur.nom_affiche if verrou.utilisateur else "un autre compte"
        raise HTTPException(
            status_code=409,
            detail=f"Document en cours de modification par {detenteur}. "
                   f"Réessayez dans quelques minutes.",
        )

    expiration = datetime.now() + timedelta(
        minutes=reglages.entier(session, "duree_verrou_edition_minutes") or DUREE_VERROU_MINUTES)
    if verrou:
        verrou.date_expiration = expiration
    else:
        session.add(VerrouDocument(document_id=document_id, utilisateur_id=user.id,
                                   date_expiration=expiration))
    session.commit()
    return VerrouOut(detenu=True, expire_le=expiration.isoformat(timespec="seconds"))


@app.delete("/documents/{document_id}/verrou")
def rendre_verrou(document_id: int, session: Session = Depends(get_session),
                  user: Utilisateur = Depends(auth.get_current_user)):
    """
    Rend le verrou. Un administrateur peut lever celui d'un autre : il faut bien
    quelqu'un pour débloquer un document laissé ouvert par un absent.
    """
    verrou = session.query(VerrouDocument).filter_by(document_id=document_id).one_or_none()
    if verrou and (user.est_admin or verrou.utilisateur_id == user.id):
        session.delete(verrou)
        session.commit()
    return {"ok": True}


class DocumentPatch(BaseModel):
    categorie_id: Optional[int] = None
    date_document: Optional[str] = None          # AAAA-MM-JJ, "" pour effacer
    metadonnees: Optional[dict] = None           # {cle: valeur} ; valeur vide = suppression
    # Ce que cette entrée retient de chaque valeur de table (§22.61) :
    # `{champ: [colonnes]}`. Une liste vide efface le choix — l'entrée revient à
    # ce que le champ propose.
    affichages: Optional[dict] = None


def _sources_par_cle(session: Session, categorie_id: Optional[int]) -> dict:
    """`{cle: [tables]}` — ce que chaque champ attendu de ce type déclare puiser."""
    if not categorie_id:
        return {}
    par_cle = {}
    for regle in (session.query(RegleChampCategorie)
                  .filter(RegleChampCategorie.categorie_id == categorie_id)):
        if regle.champ.startswith(moteur_filtres.PREFIXE_META):
            sources = conformite.sources_de(regle)
            if sources:
                par_cle[regle.champ[len(moteur_filtres.PREFIXE_META):]] = sources
    return par_cle


def _ecrire_metadonnees(session: Session, doc: Document, valeurs: dict) -> None:
    """
    Écrit des métadonnées saisies à la main. Une valeur vide supprime l'entrée,
    ce qui permet de corriger une extraction erronée aussi bien que d'en ajouter
    une manquante. `regle_id` reste nul : la valeur ne vient pas d'une règle.

    **Une valeur adossée à une table est préfixée de sa source** (§21.12) : un
    champ qui puise dans `usr_emetteurs` et qu'on remplit à la main doit ranger
    `usr_emetteurs:5`, pas `5`. Sans cela, la valeur ne se relit plus — ni son
    libellé, ni le rattachement, ni le repli, ni le filtre : le document affichait
    un numéro nu, et l'on cherchait pourquoi l'émetteur « n'était pas trouvé »
    alors qu'il avait bien été choisi.
    """
    sources = _sources_par_cle(session, doc.categorie_id)

    for cle, valeur in valeurs.items():
        cle = str(cle).strip()
        if not cle:
            continue
        existant = session.query(Metadonnee).filter_by(document_id=doc.id, cle=cle).one_or_none()
        texte = "" if valeur is None else str(valeur).strip()
        # Un identifiant nu sur un champ à source unique : on le préfixe. Avec
        # plusieurs sources, l'interface envoie déjà la référence complète — elle
        # seule sait laquelle a été choisie (§17.28).
        tables = sources.get(cle) or []
        if (texte.isdigit() and len(tables) == 1
                and base_donnees.SEPARATEUR_SOURCE not in texte):
            texte = f"{tables[0]}{base_donnees.SEPARATEUR_SOURCE}{texte}"
        if not texte:
            if existant:
                session.delete(existant)
            continue
        if existant:
            existant.valeur = texte[:500]
            existant.regle_id = None
        else:
            # attachée au document : la conformité est recontrôlée juste après,
            # dans la même session, et un `flush` ne remplit pas une collection
            # déjà chargée (voir `references_auto.remplir`)
            doc.metadonnees.append(Metadonnee(cle=cle, valeur=texte[:500], regle_id=None))


def _reevaluer_conformite(session: Session, doc: Document) -> list[dict]:
    """
    Recontrôle les champs exigés après une correction manuelle, et remet le
    document — ainsi que son travail — dans l'état correspondant (§16 : « après
    correction, le document doit pouvoir reprendre son traitement normal »).

    Le contrôle est fait ici plutôt que confié au serveur de travaux : il ne
    demande aucun accès aux fichiers, et l'utilisateur qui corrige doit voir le
    résultat immédiatement.
    """
    # Même geste qu'au serveur de travaux (§22.41) : on recalcule, et on **range**
    # la réponse sur le document. Une correction à la main est l'autre moment où
    # elle change.
    manquants = conformite.ranger(session, doc)
    if doc.statut in {"traite", "incomplet"}:
        doc.statut = "incomplet" if manquants else "traite"

    job = (
        session.query(Job)
        .filter(Job.document_id == doc.id, Job.statut.in_(("bloque", "termine")))
        .order_by(Job.id.desc())
        .first()
    )
    if job:
        if manquants:
            job.statut = "bloque"
            job.message_erreur = "Champs attendus manquants : " + ", ".join(
                c["libelle"] for c in manquants
            )
        else:
            job.statut = "termine"
            job.message_erreur = None
        job.etape = "conformite"
    return manquants


@app.patch("/documents/{document_id}", response_model=DocumentOut)
def modifier_document(
    document_id: int,
    patch: DocumentPatch,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Corrections manuelles depuis l'interface : classement, émetteur, date,
    métadonnées extraites. Sert aussi bien au panneau de détail qu'au
    Centre d'analyse, où l'on corrige un champ manquant sans quitter l'écran.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    # droit d'écriture sur la catégorie actuelle du document...
    _verifier_acces(doc, user, ecriture=True, session=session)

    # ... et personne d'autre en train de le modifier
    verrou = _verrou_actif(session, document_id)
    if verrou and verrou.utilisateur_id != user.id:
        detenteur = verrou.utilisateur.nom_affiche if verrou.utilisateur else "un autre compte"
        raise HTTPException(
            status_code=409,
            detail=f"Document en cours de modification par {detenteur}.",
        )

    # Relevé avant modification : c'est lui qui permettra de dire « Factures →
    # Impôts » plutôt que « catégorie modifiée ».
    avant = _etat_lisible(session, doc)

    if patch.categorie_id is not None:
        # ... et sur la nouvelle catégorie si elle change
        try:
            droits.exiger(session, user, droits.MODIFIER, patch.categorie_id)
        except droits.DroitRefuse as refus:
            raise HTTPException(status_code=403, detail=str(refus))
        # Un dossier organise, il ne contient pas de document (§19.1) : sans ce
        # refus, une fiche pourrait se retrouver à mi-chemin de l'arbre, dans une
        # catégorie qui en contient d'autres.
        try:
            categories.exiger_type(session, patch.categorie_id, "de document")
        except categories.NatureRefusee as refus:
            raise HTTPException(status_code=400, detail=str(refus))
        doc.categorie_id = patch.categorie_id


    if patch.date_document is not None:
        texte = patch.date_document.strip()
        if not texte:
            doc.date_document = None
        else:
            try:
                doc.date_document = datetime.strptime(texte, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=422, detail="Date attendue au format AAAA-MM-JJ")

    if patch.metadonnees is not None:
        _ecrire_metadonnees(session, doc, patch.metadonnees)

    if patch.affichages is not None:
        _ecrire_affichages(session, doc, patch.affichages)

    # Rafraîchir **avant** de recontrôler la conformité : les métadonnées qui
    # viennent d'être écrites ne sont pas visibles dans la collection déjà
    # chargée du document. Sans cela, la conformité se prononçait sur l'état
    # d'avant — un document corrigé restait « incomplet » alors que la fiche
    # renvoyée, elle, ne montrait plus aucun champ manquant.
    session.flush()
    session.refresh(doc)
    # Les automatisations avant le contrôle de conformité (§21.8) : ce qu'elles
    # renseignent doit compter dans les champs manquants, sinon un document
    # qu'une règle vient de compléter resterait annoncé « incomplet ».
    automatisations.executer(session, automatisations.MODIFICATION, doc)
    session.flush()
    session.refresh(doc)
    _reevaluer_conformite(session, doc)
    difference = _difference(avant, _etat_lisible(session, doc))
    if difference:
        # Une requête qui ne change rien ne mérite pas d'entrée au journal :
        # l'histoire du document doit se lire sans avoir à écarter le bruit.
        audit.journaliser(
            session, user, audit.DOCUMENT_MODIFICATION, "document", doc.id, details=difference,
        )
    session.commit()
    session.refresh(doc)
    return _serialize(doc, conformite.regles_par_categorie(
        session, {doc.categorie_id} if doc.categorie_id else set()
    ), _libelles_references(session, [doc]),
        affichages=_affichages_par_document(session, [doc]))


@app.delete("/documents/{document_id}")
def supprimer_document(
    document_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Met un document à la corbeille (§21.1).

    Il n'est plus effacé : il est **daté**. Il quitte le registre, toutes les
    listes et toutes les recherches, mais garde sa place, ses métadonnées, ses
    versions et son fichier — et se restaure exactement là où il était. Avant,
    la suppression était immédiate et définitive, dans une maison où chacun a le
    droit de supprimer : une fausse manœuvre ne se rattrapait pas.

    Il tombe dans **deux** corbeilles à la fois, celle de son auteur et celle de
    l'administration. Ce qui l'efface pour de bon est la purge, ou un
    administrateur — jamais ce geste-ci.

    L'opération est journalisée dans la même transaction.
    """
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    # Supprimer n'est pas modifier (§19.12) : corriger un champ se défait, mettre
    # une pièce à la corbeille demande d'aller la rechercher.
    _verifier_acces(doc, user, session=session, action=droits.SUPPRIMER)

    doc.date_suppression = datetime.now()
    doc.supprime_par_id = user.id
    doc.corbeille_masquee = False

    audit.journaliser(
        session, user, audit.DOCUMENT_SUPPRESSION, "document", doc.id,
        details={
            "nom_fichier": doc.nom_fichier,
            "chemin_stockage": doc.chemin_stockage,
            "hash_sha256": doc.hash_sha256,
            "categorie_id": doc.categorie_id,
            "date_document": doc.date_document,
            "date_import": doc.date_import,
            # ce qui a réellement eu lieu : rien n'est encore perdu
            "corbeille": True,
        },
    )
    session.commit()
    return {"ok": True, "corbeille": True}


# ------------------------------------------------------------
# La corbeille de chacun (§21.1)
#
# Deux corbeilles, comme chez EzGED : celle de la personne qui a supprimé, et
# celle de l'administration qui voit tout. Supprimer depuis la sienne ne détruit
# rien — cela retire le document de sa propre vue, où il encombrait, et le laisse
# à l'administration. Le geste de trop reste ainsi rattrapable.
# ------------------------------------------------------------

class DocumentCorbeilleOut(BaseModel):
    id: int
    nom_fichier: str
    libelle: Optional[str] = None
    categorie: Optional[str] = None
    date_document: Optional[str] = None
    date_suppression: str
    supprime_par: Optional[str] = None
    masquee: bool = False
    # Ce qui distingue ce document d'un autre du même type (§22.63) : émetteur,
    # numéro, montant. « Factures · supprimé il y a 3 min » ne dit pas laquelle
    # on s'apprête à perdre, et c'est pourtant la seule question qu'on se pose
    # devant une corbeille. Les colonnes du type, dans leur ordre.
    details: list[dict] = []


def _serialiser_corbeille(doc: Document, session: Optional[Session] = None,
                          libelles: Optional[dict] = None) -> DocumentCorbeilleOut:
    return DocumentCorbeilleOut(
        id=doc.id,
        nom_fichier=doc.nom_fichier,
        libelle=_libelle_document(doc),
        categorie=doc.categorie.nom if doc.categorie else None,
        date_document=str(doc.date_document) if doc.date_document else None,
        date_suppression=doc.date_suppression.isoformat(timespec="seconds"),
        supprime_par=doc.supprime_par.nom_affiche if doc.supprime_par else None,
        masquee=bool(doc.corbeille_masquee),
        details=_details_de_la_corbeille(session, doc, libelles) if session else [],
    )


def _details_de_la_corbeille(session: Session, doc: Document,
                             libelles: Optional[dict]) -> list[dict]:
    """
    De quoi reconnaître **ce** document-là parmi ses semblables (§22.63).

    Les colonnes de son type, dans l'ordre, avec leur valeur — c'est ce qu'on
    lit dans le registre, et c'est donc ce qu'on cherche des yeux. Trois au plus :
    une corbeille se parcourt, elle ne se lit pas ligne à ligne.
    """
    if not doc.categorie_id:
        return []
    valeurs = {m.cle: m.valeur for m in doc.metadonnees}
    montrees = (libelles or {}).get(doc.id, {})
    lignes = []
    for colonne in colonnes.pour_categorie(session, doc.categorie_id):
        champ = colonne["champ"]
        if champ.startswith(moteur_filtres.PREFIXE_META):
            cle = champ[len(moteur_filtres.PREFIXE_META):]
            valeur = montrees.get(cle) or valeurs.get(cle)
        elif champ == "date_document":
            valeur = str(doc.date_document) if doc.date_document else None
        else:
            continue
        if valeur:
            lignes.append({"libelle": colonne["libelle"], "valeur": str(valeur)})
        if len(lignes) == 3:
            break
    return lignes


class PageCorbeilleOut(BaseModel):
    """`total` porte sur la corbeille entière, pas sur la page (§22.90)."""
    total: int
    documents: list[DocumentCorbeilleOut]


@app.get("/corbeille", response_model=PageCorbeilleOut)
def ma_corbeille(limite: int = 25, decalage: int = 0,
                 session: Session = Depends(get_session),
                 user: Utilisateur = Depends(auth.get_current_user)):
    """
    Ce que **j'ai** supprimé et qui n'est pas encore perdu.

    Chacun la sienne : on cherche ce qu'on a jeté soi-même, il y a un instant, et
    une corbeille commune obligerait à fouiller les gestes des autres. Ce qu'on
    en a retiré (`corbeille_masquee`) n'y figure plus — c'est le sens du second
    geste ; l'administration, elle, le voit encore.

    Les droits s'appliquent quand même : perdre le droit de voir une catégorie
    ne doit pas laisser une porte ouverte par la corbeille.
    """
    query = _filtrer_par_droits(
        session.query(Document).options(joinedload(Document.categorie),
                                        joinedload(Document.supprime_par)),
        session, user, corbeille=True)
    # Un plafond dur à 500 rendait les plus anciens **invisibles et
    # irrécupérables** depuis cet écran, sans que rien ne le dise (§22.90). Le
    # décompte porte sur la corbeille entière : on sait toujours ce qui reste.
    query = query.filter(Document.date_suppression.isnot(None),
                         Document.corbeille_masquee.is_(False),
                         Document.supprime_par_id == user.id)
    total = query.count()
    documents = (query.order_by(Document.date_suppression.desc())
                 .offset(max(0, decalage))
                 .limit(max(1, min(limite, 200)))
                 .all())
    libelles = _libelles_references(session, documents)
    return PageCorbeilleOut(
        total=total,
        documents=[_serialiser_corbeille(d, session, libelles) for d in documents])


def _document_en_corbeille(session: Session, document_id: int) -> Document:
    doc = session.get(Document, document_id)
    if not doc or doc.date_suppression is None:
        raise HTTPException(status_code=404, detail="Document introuvable dans la corbeille")
    return doc


@app.post("/corbeille/vider")
def vider_ma_corbeille(session: Session = Depends(get_session),
                       user: Utilisateur = Depends(auth.get_current_user)):
    """
    Retire d'un coup tout ce qui attend dans **ma** corbeille (§21.14).

    Comme le geste unitaire, cela ne détruit rien : les documents passent en
    masqué et restent accessibles à l'administration. Vider sa corbeille est un
    geste de rangement — on ne veut plus les voir là —, pas une destruction ;
    celle-ci demande l'administration, et c'est ce qui rend le bouton sans danger.

    Ce qu'on n'a pas le droit de supprimer n'est pas touché : le décompte rendu
    dit ce qui a bougé, et non ce qu'on aurait voulu bouger.
    """
    query = _filtrer_par_droits(session.query(Document), session, user, corbeille=True)
    documents = query.filter(Document.date_suppression.isnot(None),
                             Document.corbeille_masquee.is_(False),
                             Document.supprime_par_id == user.id).all()

    retires = []
    for doc in documents:
        try:
            _verifier_acces(doc, user, session=session, action=droits.SUPPRIMER,
                            corbeille=True)
        except HTTPException:
            continue
        doc.corbeille_masquee = True
        retires.append(doc.id)

    if retires:
        audit.journaliser(session, user, "document.corbeille_videe", "document", None,
                          details={"documents": retires[:100], "nombre": len(retires)})
    session.commit()
    return {"ok": True, "retires": len(retires), "restants": len(documents) - len(retires)}


@app.post("/corbeille/{document_id}/restaurer")
def restaurer_document(document_id: int,
                       session: Session = Depends(get_session),
                       user: Utilisateur = Depends(auth.get_current_user)):
    """
    Remet un document à sa place — exactement celle qu'il avait.

    Le droit exigé est celui de supprimer : **qui a pu jeter peut reprendre**.
    Exiger davantage rendrait la corbeille inutile pour la personne même qui
    vient de se tromper.
    """
    doc = _document_en_corbeille(session, document_id)
    _verifier_acces(doc, user, session=session, action=droits.SUPPRIMER, corbeille=True)

    doc.date_suppression = None
    doc.supprime_par_id = None
    doc.corbeille_masquee = False
    audit.journaliser(session, user, "document.restauration", "document", doc.id,
                      details={"nom_fichier": doc.nom_fichier})
    session.commit()
    return {"ok": True, "id": doc.id}


@app.delete("/corbeille/{document_id}")
def retirer_de_ma_corbeille(document_id: int,
                            session: Session = Depends(get_session),
                            user: Utilisateur = Depends(auth.get_current_user)):
    """
    Retire un document de **sa propre** corbeille, sans rien détruire.

    C'est le second filet d'EzGED : le geste dit « je n'ai plus besoin de le voir
    ici », pas « qu'il disparaisse ». Le document passe en masqué et n'existe plus
    que pour l'administration, seule à pouvoir l'effacer pour de bon. Une
    corbeille qui détruit au second clic n'est plus un filet.
    """
    doc = _document_en_corbeille(session, document_id)
    _verifier_acces(doc, user, session=session, action=droits.SUPPRIMER, corbeille=True)

    doc.corbeille_masquee = True
    audit.journaliser(session, user, "document.corbeille_masquee", "document", doc.id,
                      details={"nom_fichier": doc.nom_fichier})
    session.commit()
    return {"ok": True, "masquee": True}


# ------------------------------------------------------------
# Sources de valeurs des champs personnalisés (§17)
# ------------------------------------------------------------

@app.get("/references/{nom_table}")
def lister_valeurs_reference(
    nom_table: str,
    recherche: Optional[str] = None,
    categorie_id: Optional[int] = None,
    champ: Optional[str] = None,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Valeurs proposées par une table de données pour un champ personnalisé.

    Ouvert à tout utilisateur connecté : c'est lui qui renseigne le champ depuis
    la fiche du document ou le Centre d'analyse. L'accès est strictement limité
    aux **tables de données** — jamais aux tables du système, dont la lecture
    reste réservée à l'administration.

    `categorie_id` et `champ` disent **pour quel champ** on demande ces valeurs
    (§22.59) : c'est lui qui décide de ce qui se lit d'une ligne. Le choix se lit
    ici, sur la règle, et non dans la requête — un appelant ne désigne pas les
    colonnes qu'il veut voir. Sans eux, la table décide, comme avant.
    """
    try:
        return base_donnees.options(
            session, nom_table, recherche,
            affichage=_affichage_du_champ(session, categorie_id, champ, nom_table))
    except base_donnees.OperationRefusee as erreur:
        raise HTTPException(status_code=404, detail=str(erreur))


def _affichage_du_champ(session: Session, categorie_id: Optional[int],
                        champ: Optional[str], nom_table: str) -> Optional[list[str]]:
    """Les colonnes que ce champ-ci veut lire de cette table (§22.59)."""
    if not categorie_id or not champ:
        return None
    regle = (session.query(RegleChampCategorie)
             .filter(RegleChampCategorie.categorie_id == categorie_id,
                     RegleChampCategorie.champ == champ)
             .first())
    if not regle or not regle.colonnes_affichees:
        return None
    # La table demandée doit bien être une des sources du champ : sans quoi les
    # colonnes d'une autre table serviraient à en lire une troisième.
    if nom_table not in conformite.sources_de(regle):
        return None
    return [c.strip() for c in regle.colonnes_affichees.split(",") if c.strip()]


# ------------------------------------------------------------
# Centre d'analyse (§16)
# ------------------------------------------------------------

class ChampAAnalyser(BaseModel):
    champ: str
    libelle: str
    type: str            # 'date' | 'categorie' | 'metadonnee' | 'reference' | 'texte'
    cle: Optional[str] = None          # clé de métadonnée, pour les champs `meta:<cle>`
    source_table: Optional[str] = None  # table de données servant de source de valeurs
    # Le couple (catégorie, champ) identifie la règle : c'est elle qui dit ce
    # qui se lit d'une ligne de la table source (§22.59).
    categorie_id: Optional[int] = None


class DocumentAAnalyser(BaseModel):
    id: int
    libelle: str
    categorie: Optional[str] = None
    categorie_id: Optional[int] = None
    date_document: Optional[str] = None
    date_import: str
    statut: str
    metadonnees: dict
    champs_manquants: list[ChampAAnalyser]
    job_id: Optional[int] = None
    message_job: Optional[str] = None


def _type_de_champ(champ: str) -> tuple[str, Optional[str]]:
    """Nature d'un champ attendu, pour que l'interface propose le bon contrôle de saisie."""
    if champ.startswith(moteur_filtres.PREFIXE_META):
        return "metadonnee", champ[len(moteur_filtres.PREFIXE_META):]
    if champ == "categorie":
        return champ, None
    if champ in {"date_document", "date_import"}:
        return "date", None
    return "texte", None


def _libelle_document(doc: Document) -> str:
    # L'émetteur n'est plus un champ du document (§21.12) : il est devenu une
    # métadonnée comme une autre, et le libellé se compose de ce que le document
    # est — sa sorte et sa date. L'émetteur, lui, se lit dans sa colonne.
    parties = [
        doc.categorie.nom if doc.categorie else None,
        str(doc.date_document) if doc.date_document else None,
    ]
    return " · ".join(p for p in parties if p) or f"Document nº{doc.id}"


class TravailAClasser(BaseModel):
    """Un fichier déposé à un endroit qu'aucun type de document ne réclame (§19.3)."""
    id: int
    nom_fichier: str
    date_creation: Optional[str] = None
    message: Optional[str] = None
    taille_octets: Optional[int] = None
    fichier_disponible: bool = False


def _fichier_du_travail(job: Job) -> Optional[Path]:
    """Le fichier reçu d'un travail, s'il est encore là (§18.53)."""
    if not job.chemin_source:
        return None
    chemin = Path(job.chemin_source)
    return chemin if chemin.is_file() else None


@app.get("/a-classer", response_model=list[TravailAClasser])
def lister_travaux_a_classer(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Ce qui attend qu'on dise de quel type il s'agit (§19.4).

    Ces travaux n'ont produit aucun document — ils se sont arrêtés avant
    l'océrisation, faute de savoir ce qu'ils contenaient. Ils n'ont donc ni
    catégorie ni champs à corriger : la seule question qui se pose est celle du
    type, et c'est la seule que l'écran doit poser.
    """
    # Ces fichiers n'ont **pas encore de catégorie** : aucun droit par branche ne
    # peut les protéger, et le filtrage par document ne s'y applique pas. C'est
    # donc le droit général « Centre d'analyse » qui tient la porte — celui-là
    # même qu'exigeait déjà l'action d'écarter (§22.38).
    try:
        droits.exiger_general(user, "analyser")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))

    travaux = (session.query(Job).filter(Job.statut == "a_classer")
               .order_by(Job.date_creation.asc(), Job.id.asc()).all())
    resultat = []
    for job in travaux:
        fichier = _fichier_du_travail(job)
        resultat.append(TravailAClasser(
            id=job.id, nom_fichier=job.nom_fichier,
            date_creation=job.date_creation.isoformat(timespec="seconds")
            if job.date_creation else None,
            message=job.message_erreur,
            taille_octets=fichier.stat().st_size if fichier else None,
            fichier_disponible=fichier is not None,
        ))
    return resultat


@app.get("/a-classer/{job_id}/fichier")
def telecharger_fichier_a_classer(
    job_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Le fichier reçu, pour qu'on puisse le regarder avant de dire ce que c'est.

    C'est le seul moyen de trancher : sans océrisation, il n'y a ni texte ni
    métadonnée — il reste la page telle qu'elle a été déposée.
    """
    # Ces fichiers n'ont **pas encore de catégorie** : aucun droit par branche ne
    # peut les protéger, et le filtrage par document ne s'y applique pas. C'est
    # donc le droit général « Centre d'analyse » qui tient la porte — celui-là
    # même qu'exigeait déjà l'action d'écarter (§22.38).
    try:
        droits.exiger_general(user, "analyser")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))

    job = session.get(Job, job_id)
    if not job or job.statut != "a_classer":
        raise HTTPException(status_code=404, detail="Travail introuvable")
    fichier = _fichier_du_travail(job)
    if not fichier:
        raise HTTPException(
            status_code=404,
            detail="Le fichier reçu n'est plus disponible.")
    # Affiché, et non téléchargé (voir `admin.telecharger_original`) : c'est en
    # regardant la page qu'on dit de quoi il s'agit.
    return FileResponse(
        str(fichier), media_type=config.type_mime(fichier),
        headers={"Content-Disposition":
                 f'inline; filename="{config.nom_pour_entete(job.nom_fichier or fichier.name)}"'})


class ClassementDemande(BaseModel):
    categorie_id: int


@app.delete("/a-classer/{job_id}")
def ecarter_travail(
    job_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Écarte un dépôt : ce fichier n'a rien à faire là (§21.14).

    Un double scan, une page de garde, un fichier déposé par erreur. On pouvait
    dire de quel type était un fichier, jamais qu'il n'en était aucun : il fallait
    aller le chercher sur le disque, ou le laisser encombrer l'écran — et le
    compteur continuait d'appeler à l'action.

    Comme pour le classement (§19.4), l'API **pose la consigne** et le serveur de
    travaux l'exécute : elle seule a les fichiers reçus en lecture seule. Le
    travail reste visible dans le suivi, avec la trace de qui l'a écarté.
    """
    try:
        droits.exiger_general(user, "analyser")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))

    job = session.get(Job, job_id)
    if not job or job.statut != "a_classer":
        raise HTTPException(status_code=404, detail="Ce travail n'attend pas de classement")

    job.rejet_demande = True
    job.diagnostic = (f"Écarté depuis le Centre d'analyse par {user.nom_affiche} : "
                      f"ce fichier n'avait pas à être classé.")
    audit.journaliser(session, user, "depot.ecarte", "job", job.id,
                      details={"nom_fichier": job.nom_fichier})
    session.commit()
    return {"ok": True, "id": job.id}


@app.post("/a-classer/{job_id}")
def classer_travail(
    job_id: int,
    demande: ClassementDemande,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Range le fichier dans le dossier de son type, et rend la main au serveur (§19.4).

    Le fichier est **déplacé** vers le dossier de dépôt du type choisi, puis le
    travail est remis en file. Ce n'est pas un chemin de traitement parallèle :
    le document suit exactement le même parcours que s'il avait été déposé au bon
    endroit — même océrisation, mêmes règles, mêmes contrôles. C'est ce qui
    garantit qu'un document classé à la main vaut un document bien déposé.
    """
    # Ces fichiers n'ont **pas encore de catégorie** : aucun droit par branche ne
    # peut les protéger, et le filtrage par document ne s'y applique pas. C'est
    # donc le droit général « Centre d'analyse » qui tient la porte — celui-là
    # même qu'exigeait déjà l'action d'écarter (§22.38).
    try:
        droits.exiger_general(user, "analyser")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))

    job = session.get(Job, job_id)
    if not job or job.statut != "a_classer":
        raise HTTPException(status_code=404, detail="Travail introuvable, ou déjà classé")

    categorie = session.get(Categorie, demande.categorie_id)
    if not categorie:
        raise HTTPException(status_code=404, detail="Type de document introuvable")
    try:
        categories.exiger_type(session, categorie.id, "de document")
    except categories.NatureRefusee as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    if not categorie.dossier_depot:
        raise HTTPException(
            status_code=400,
            detail=f"« {categorie.nom} » n'a pas encore de dossier de dépôt.")

    try:
        droits.exiger(session, user, droits.DEPOSER, categorie.id)
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))

    if not _fichier_du_travail(job):
        raise HTTPException(
            status_code=400,
            detail="Le fichier reçu n'est plus disponible : le classement est impossible.")

    # C'est le serveur de travaux qui déplace le fichier, pas l'API : les fichiers
    # reçus (§18.53) lui sont montés en lecture seule, et cette garantie-là vaut
    # mieux qu'une exception consentie pour un seul point d'entrée. On pose donc
    # la consigne, il la relève à son passage suivant — c'est déjà ainsi que
    # fonctionnent les demandes de rejeu.
    #
    # Le travail garde son identité : c'est le même fichier, la même histoire. Il
    # repart depuis le début — l'empreinte —, parce que rien n'a encore été fait
    # de ce fichier.
    job.categorie_demandee = categorie.id
    job.rejouer_demande = True
    job.etape_demandee = "empreinte"
    # Il quitte « à classer » : la question a reçu sa réponse, et le laisser dans
    # cet état permettrait de le classer une seconde fois — ce qui déplacerait le
    # fichier deux fois et en ferait un doublon.
    job.statut = "en_attente"
    job.message_erreur = None
    job.diagnostic = f"Classé à la main dans « {categorie.nom} » : traitement repris."
    audit.journaliser(session, user, "job.classe", "job", job.id,
                      details={"categorie": categorie.nom,
                               "dossier_depot": categorie.dossier_depot,
                               "nom_fichier": job.nom_fichier})
    session.commit()
    return {"ok": True, "categorie": categorie.nom, "dossier_depot": categorie.dossier_depot}


class CompteursOut(BaseModel):
    a_analyser: int
    a_classer: int
    corbeille: int
    rappels: int


@app.get("/compteurs", response_model=CompteursOut)
def compteurs_de_la_barre(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Les quatre chiffres de la barre d'outils, en une requête et sans rien charger
    (§22.39).

    L'écran les obtenait en **listant** : `/analyse` rendait tous les documents
    non conformes avec leurs métadonnées, `/corbeille` toute la corbeille, et
    l'on n'en gardait que la longueur. Sur neuf documents cela ne se voyait pas ;
    sur cinq mille, c'est le registre entier chargé quatre fois par minute pour
    afficher « 3 ». Ici, quatre `COUNT` qui s'appuient sur les index — le
    Python ne voit jamais une ligne.

    C'est ce qui permet de les relire **souvent** : un document qui arrive doit
    se voir en haut du registre sans recharger la page.
    """
    a_analyser = (_filtrer_par_droits(session.query(Document.id), session, user)
                  .filter(Document.categorie_id.isnot(None),
                          conformite.incomplet_range())
                  .count())
    # Les fichiers sans type ne sont comptés que pour qui a le droit de les voir
    # (§22.38) : annoncer « 4 à analyser » à qui n'en verra aucun serait un piège.
    a_classer = (session.query(Job).filter(Job.statut == "a_classer").count()
                 if droits.general(user, "analyser") else 0)
    # Mêmes conditions que l'écran de corbeille, à la ligne près : un compteur
    # qui annonce autre chose que ce qu'on trouve en cliquant est pire qu'absent.
    corbeille = (_filtrer_par_droits(session.query(Document.id), session, user, corbeille=True)
                 .filter(Document.date_suppression.isnot(None),
                         Document.corbeille_masquee.is_(False),
                         Document.supprime_par_id == user.id).count())
    rappels = notifs.compter_non_lues(session, user)
    return CompteursOut(a_analyser=a_analyser, a_classer=a_classer,
                        corbeille=corbeille, rappels=rappels)


@app.get("/analyse", response_model=list[DocumentAAnalyser])
def lister_documents_a_analyser(
    reponse: Response,
    limite: int = 50,
    decalage: int = 0,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Documents qui ne respectent pas les champs exigés par leur catégorie.

    **Par page** (§22.43) : un foyer de vingt mille documents peut en avoir mille
    huit cents à reprendre, et les rendre tous coûtait 825 ko et près d'une
    seconde à chaque ouverture — pour une liste qu'on traite ligne à ligne. Le
    total part dans `X-Total-Count`, comme au registre : la page dit combien il
    en reste sans avoir à tout charger.

    L'état de conformité est **lu** et non recalculé (§22.41) : il est posé à la
    fin de chaque traitement, reposé quand les champs attendus changent, et
    vérifié périodiquement par le serveur de travaux.
    """
    query = session.query(Document).options(
        joinedload(Document.categorie),
        joinedload(Document.metadonnees),
    )
    query = _filtrer_par_droits(query, session, user)
    # seuls les documents classés peuvent être non conformes : sans catégorie,
    # on ne sait pas encore ce qu'on attend d'eux.
    #
    # Et le tri se fait **en SQL** (§22.40) : cet écran chargeait tout le registre
    # avec ses métadonnées pour n'en garder qu'une poignée — deux secondes et
    # deux cents kilo-octets sur cinq mille documents, à chaque ouverture. La
    # clause existe déjà (`clause_incomplet`), elle est faite pour ça.
    query = query.filter(Document.categorie_id.isnot(None), conformite.incomplet_range())
    reponse.headers["X-Total-Count"] = str(query.order_by(None).count())
    # Les plus anciens d'abord : ce sont ceux qui attendent depuis le plus
    # longtemps, et une liste de travail se prend par le début.
    documents = (query.order_by(Document.date_import.asc(), Document.id.asc())
                 .limit(max(1, min(limite, 200))).offset(max(0, decalage)).all())

    regles = conformite.regles_par_categorie(
        session, {d.categorie_id for d in documents if d.categorie_id is not None}
    )
    jobs = {}
    if documents:
        # Les travaux de ces documents-là, et non tous ceux du registre.
        for job in (session.query(Job)
                    .filter(Job.document_id.in_([d.id for d in documents]))
                    .order_by(Job.id).all()):
            jobs[job.document_id] = job

    sources = {
        (r.categorie_id, r.champ): r.source_table
        for regles_categorie in regles.values() for r in regles_categorie if r.source_table
    }

    resultat = []
    for doc in documents:
        manquants = conformite.champs_manquants(doc, regles)
        if not manquants:
            continue
        job = jobs.get(doc.id)
        champs = []
        for manque in manquants:
            type_champ, cle = _type_de_champ(manque["champ"])
            source = sources.get((doc.categorie_id, manque["champ"]))
            champs.append(ChampAAnalyser(
                champ=manque["champ"], libelle=manque["libelle"],
                # une source de valeurs change la saisie : on choisit une ligne
                # existante au lieu de recopier du texte
                type="reference" if source else type_champ,
                cle=cle, source_table=source, categorie_id=doc.categorie_id,
            ))
        resultat.append(DocumentAAnalyser(
            id=doc.id,
            libelle=_libelle_document(doc),
            categorie=doc.categorie.nom if doc.categorie else None,
            categorie_id=doc.categorie_id,
            date_document=str(doc.date_document) if doc.date_document else None,
            date_import=str(doc.date_import),
            statut=doc.statut,
            metadonnees={m.cle: m.valeur for m in doc.metadonnees},
            champs_manquants=champs,
            job_id=job.id if job else None,
            message_job=job.message_erreur if job else None,
        ))
    resultat.sort(key=lambda d: d.date_import, reverse=True)
    return resultat


@app.get("/impact-suppression")
def impact_suppression_utilisateur(
    type_objet: str,
    identifiant: str,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Conséquences d'une suppression, pour les objets qu'un compte non
    administrateur peut supprimer : ses documents et ses vues.
    """
    if type_objet not in {"document", "vue"}:
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    if type_objet == "document":
        doc = session.get(Document, int(identifiant))
        if not doc:
            raise HTTPException(status_code=404, detail="Document introuvable")
        _verifier_acces(doc, user, ecriture=True, session=session)
    else:
        _vue_accessible(int(identifiant), user, session, ecriture=True)
    try:
        return impact.calculer(session, type_objet, identifiant)
    except impact.ObjetIntrouvable as erreur:
        raise HTTPException(status_code=404, detail=str(erreur))


# ------------------------------------------------------------
# Tableaux de bord
# ------------------------------------------------------------

class TableauOut(BaseModel):
    id: object                     # « accueil » pour le tableau livré, un entier sinon
    nom: str
    description: Optional[str] = None
    widgets: list[dict]
    modifiable: bool = False
    partage: bool = False
    proprietaire: Optional[str] = None
    ordre: int = 100


def _charger_widgets(tableau: TableauDeBord) -> list[dict]:
    try:
        widgets = json.loads(tableau.widgets)
        return widgets if isinstance(widgets, list) else []
    except (ValueError, TypeError):
        return []


def _serialize_tableau(tableau: TableauDeBord, user: Utilisateur) -> TableauOut:
    return TableauOut(
        id=tableau.id, nom=tableau.nom, description=tableau.description,
        widgets=_charger_widgets(tableau), partage=bool(tableau.partage),
        modifiable=user.est_admin, ordre=tableau.ordre or 100,
        proprietaire=tableau.utilisateur.nom_affiche if tableau.utilisateur else None,
    )


def _tableaux_visibles(session: Session, user: Utilisateur) -> list[TableauDeBord]:
    """Ses propres tableaux, plus ceux partagés. Un administrateur les voit tous."""
    query = session.query(TableauDeBord).options(joinedload(TableauDeBord.utilisateur))
    if not user.est_admin:
        query = query.filter(
            (TableauDeBord.partage.is_(True)) | (TableauDeBord.utilisateur_id == user.id)
        )
    return query.order_by(TableauDeBord.ordre, TableauDeBord.nom).all()


@app.get("/tableaux-de-bord", response_model=list[TableauOut])
def lister_tableaux(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """Le tableau d'accueil, puis les tableaux personnalisés visibles par l'utilisateur."""
    accueil = statistiques.tableau_accueil()
    return [TableauOut(**{**accueil, "ordre": 0})] + [
        _serialize_tableau(t, user) for t in _tableaux_visibles(session, user)
    ]


@app.get("/tableaux-de-bord/{tableau_id}/donnees")
def calculer_tableau(
    tableau_id: str,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Calcule les indicateurs d'un tableau.

    Chaque indicateur est calculé indépendamment : une description fautive
    n'affiche qu'une case en erreur, le reste du tableau reste lisible.
    """
    if tableau_id == "accueil":
        definition = statistiques.tableau_accueil()
        widgets = definition["widgets"]
        entete = {"id": "accueil", "nom": definition["nom"],
                  "description": definition["description"], "modifiable": False}
    else:
        tableau = session.get(TableauDeBord, int(tableau_id)) if tableau_id.isdigit() else None
        if not tableau:
            raise HTTPException(status_code=404, detail="Tableau de bord introuvable")
        if not (user.est_admin or tableau.partage or tableau.utilisateur_id == user.id):
            raise HTTPException(status_code=403, detail="Tableau de bord non accessible")
        widgets = _charger_widgets(tableau)
        entete = {"id": tableau.id, "nom": tableau.nom,
                  "description": tableau.description, "modifiable": user.est_admin}

    resultats = []
    for widget in widgets:
        # La restriction aux documents complets n'est plus appliquée ici mais par
        # l'indicateur lui-même (`portee`, cf. app/statistiques.py) : imposée à
        # tous, elle mettait « À reprendre » à zéro — le seul compteur qui parle
        # justement des documents incomplets.
        base = _filtrer_par_droits(session.query(Document.id), session, user)
        try:
            calcul = statistiques.calculer(session, base, widget)
            resultats.append({**widget, **calcul, "erreur": None})
        except statistiques.IndicateurInvalide as erreur:
            resultats.append({**widget, "erreur": str(erreur)})
        except Exception:
            logging.getLogger(__name__).exception(
                f"Indicateur « {widget.get('titre')} » : calcul impossible")
            resultats.append({**widget, "erreur": "Calcul impossible."})
    return {**entete, "widgets": resultats}


@app.get("/tableaux-de-bord/options")
def options_indicateurs(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    De quoi composer un indicateur depuis l'interface, sans rien coder en dur :
    types, périodes, champs de groupement et champs filtrables du moment.
    """
    return {
        "types": [
            {"type": "nombre", "libelle": "Nombre de documents"},
            {"type": "somme", "libelle": "Total d'un montant"},
            {"type": "repartition", "libelle": "Répartition"},
            {"type": "evolution", "libelle": "Évolution dans le temps"},
        ],
        "periodes": [{"type": t, "libelle": l} for t, l in statistiques.PERIODES.items()],
        "groupements": [{"champ": c, "libelle": l}
                        for c, l in statistiques.CHAMPS_GROUPEMENT.items()],
        "champs": moteur_filtres.champs_disponibles(session),
        "dates": [{"champ": "date_document", "libelle": "Date du document"},
                  {"champ": "date_import", "libelle": "Date d'import"}],
    }


# ------------------------------------------------------------
# Vues enregistrées (§9.B)
# ------------------------------------------------------------

class VueIn(BaseModel):
    nom: str
    categorie_id: Optional[int] = None
    criteres: list[dict] = []
    partagee: bool = False
    # Champs du repli en arborescence (§21.6), dans l'ordre où l'on descend.
    groupement: list[str] = []
    # Liens déclarés vers d'autres vues (§22.5) : la correspondance de champs
    # d'EzGED — « depuis celle-ci, ouvrir celle-là sur la ligne qu'on regarde ».
    liens: list[dict] = []
    ordre: int = 100


class VueOut(BaseModel):
    id: int
    nom: str
    categorie_id: Optional[int] = None
    criteres: list[dict]
    partagee: bool
    groupement: list[str] = []
    liens: list[dict] = []
    ordre: int
    modifiable: bool  # vrai pour un administrateur : lui seul crée et supprime les vues
    proprietaire: Optional[str] = None  # None = vue du système (auteur supprimé)


def _serialize_vue(vue: VueEnregistree, user: Utilisateur) -> VueOut:
    try:
        criteres = json.loads(vue.criteres)
    except (ValueError, TypeError):
        criteres = []
    return VueOut(
        id=vue.id, nom=vue.nom, categorie_id=vue.categorie_id, criteres=criteres,
        partagee=bool(vue.partagee), groupement=groupes.declares(vue),
        liens=liens_vue.declares(vue), ordre=vue.ordre,
        # Une vue ne se renomme ni ne se supprime hors de l'administration : ce
        # drapeau ne dépend donc plus du propriétaire, mais du seul rôle. Il
        # commande l'affichage du bouton de suppression dans la navigation.
        modifiable=bool(user.est_admin),
        proprietaire=vue.utilisateur.nom_affiche if vue.utilisateur else None,
    )


def _valider_groupement(champs: Optional[list], session: Session) -> Optional[str]:
    """Un repli sur un champ qui n'existe pas ne se manifesterait qu'à l'usage."""
    try:
        return groupes.valider_declaration(session, champs)
    except moteur_filtres.FiltreInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))


def _valider_liens(declarations: Optional[list], session: Session,
                   vue_id: Optional[int] = None) -> str:
    """
    Une correspondance fausse ne produit aucune erreur à l'usage : elle ouvre une
    liste vide, et l'on cherche pendant une heure d'où vient le vide.
    """
    try:
        return liens_vue.valider(session, declarations, vue_id)
    except liens_vue.LienRefuse as refus:
        raise HTTPException(status_code=422, detail=str(refus))


def _valider_criteres(criteres: list[dict], session: Session) -> str:
    """
    Refuse d'enregistrer une vue dont les critères ne sont pas applicables : une
    vue invalide ne se manifesterait sinon qu'au moment de l'utiliser. Renvoie
    les critères sérialisés, prêts à être stockés.
    """
    for critere in criteres:
        try:
            moteur_filtres.valider_champ(session, (critere or {}).get("champ"))
            moteur_filtres.condition(session, moteur_filtres.Filtre(**critere))
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=422, detail=str(erreur))
        except (TypeError, ValueError) as erreur:
            raise HTTPException(status_code=422, detail=f"Critère illisible : {erreur}")
    return json.dumps(criteres, ensure_ascii=False)


def _exiger_administrateur(user: Utilisateur, message: str) -> None:
    """Refuse l'action à un compte ordinaire. Le contrôle est ici, pas seulement
    dans l'interface : masquer un bouton ne protège de rien."""
    if not user.est_admin:
        raise HTTPException(status_code=403, detail=message)


def _vue_accessible(vue_id: int, user: Utilisateur, session: Session, ecriture: bool) -> VueEnregistree:
    vue = session.get(VueEnregistree, vue_id)
    if not vue:
        raise HTTPException(status_code=404, detail="Vue introuvable")
    if ecriture and not (user.est_admin or vue.utilisateur_id == user.id):
        raise HTTPException(status_code=403, detail="Cette vue ne vous appartient pas")
    if not ecriture and not (user.est_admin or vue.partagee or vue.utilisateur_id == user.id):
        raise HTTPException(status_code=403, detail="Vue non accessible")
    return vue


def _verifier_categorie_visible(categorie_id: Optional[int], user: Utilisateur,
                                session: Session) -> None:
    if categorie_id is None:
        return
    if not droits.accorde(session, user, droits.VOIR, categorie_id):
        raise HTTPException(status_code=403, detail="Catégorie de rattachement non autorisée")


# ------------------------------------------------------------
# Export par modèle (§21.13)
#
# L'export de secours (§17.30) sort tout le foyer, une fois, sous mot de passe :
# il répond à « je ne me sers plus de la GED ». Celui-ci répond au besoin
# quotidien — sortir une sélection rangée comme on la veut, pour la donner au
# comptable ou à l'assurance. Droit distinct : les confondre obligerait à donner
# la porte de sortie définitive pour permettre un geste courant.
# ------------------------------------------------------------

class DemandeExportIn(BaseModel):
    criteres: list[dict] = []
    categorie_id: Optional[int] = None
    modele_dossier: Optional[str] = None
    modele_nom: Optional[str] = None


def _serialiser_export(demande: ExportModele) -> dict:
    return {
        "id": demande.id,
        "statut": demande.statut,
        "nb_documents": demande.nb_documents,
        "message": demande.message,
        "modele_dossier": demande.modele_dossier,
        "modele_nom": demande.modele_nom,
        "date_demande": (demande.date_demande.isoformat(timespec="seconds")
                         if demande.date_demande else None),
        "date_fin": (demande.date_fin.isoformat(timespec="seconds")
                     if demande.date_fin else None),
        "par": demande.utilisateur.nom_affiche if demande.utilisateur else None,
        "pret": demande.statut == "pret" and bool(demande.chemin),
    }


@app.get("/exports-modele/trous")
def trous_disponibles(user: Utilisateur = Depends(auth.get_current_user)):
    """Ce qu'un modèle sait remplir : un modèle à trous ne sert à rien si l'on
    doit deviner les trous."""
    try:
        droits.exiger_general(user, "exporter_selection")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))
    return {"trous": export_modele.TROUS,
            "modele_dossier": export_modele.MODELE_DOSSIER_DEFAUT,
            "modele_nom": export_modele.MODELE_NOM_DEFAUT}


@app.post("/exports-modele")
def demander_export_modele(
    corps: DemandeExportIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Demande une archive rangée selon un modèle. Le serveur de travaux la
    construit ; on revient la chercher.

    Les critères sont validés ici, avant la file d'attente : une demande qui
    échouerait dans cinq minutes pour un champ mal écrit doit être refusée tout
    de suite, pendant que celui qui l'a posée est encore là.
    """
    try:
        droits.exiger_general(user, "exporter_selection")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))
    _valider_criteres(corps.criteres, session)

    demande = ExportModele(
        utilisateur_id=user.id, statut="en_attente",
        criteres=json.dumps(corps.criteres, ensure_ascii=False),
        categorie_id=corps.categorie_id,
        modele_dossier=(corps.modele_dossier or "").strip() or None,
        modele_nom=(corps.modele_nom or "").strip() or None)
    session.add(demande)
    audit.journaliser(session, user, "export.selection_demandee", "export", None,
                      details={"criteres": corps.criteres,
                               "categorie_id": corps.categorie_id})
    session.commit()
    session.refresh(demande)
    return _serialiser_export(demande)


@app.post("/exports-modele/apercu")
def apercu_export_modele(
    corps: DemandeExportIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Ce que l'archive contiendra, avant de la demander (§22.66).

    On écrivait un modèle à trous **à l'aveugle** et l'on découvrait le rangement
    une fois l'archive construite, quelques minutes plus tard. Trois documents
    de la sélection suffisent à voir ce qu'on obtient : c'est la même fonction de
    remplissage que celle du serveur de travaux, pas une imitation qui divergerait.

    Le nombre total vient avec : « exporter cette sélection » ne dit pas si l'on
    parle de trois documents ou de deux mille.
    """
    try:
        droits.exiger_general(user, "exporter_selection")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))
    _valider_criteres(corps.criteres, session)

    documents = export_modele.documents_de(
        session, corps.criteres, corps.categorie_id,
        _filtrer_par_droits(session.query(Document), session, user))
    echantillon = documents[:3]
    libelles = export_modele.libelles_des_references(session, echantillon)
    # `pris` est partagé entre les trois : c'est ainsi que le serveur construit
    # l'archive, et l'aperçu doit montrer le « (2) » d'un homonyme s'il y en a un.
    pris: set = set()
    exemples = []
    for document in echantillon:
        # Les valeurs du document, puis les libellés là où elles pointent une
        # table : exactement ce que fait `construire`. Une composition différente
        # ici et l'aperçu mentirait — c'est tout ce qu'on lui demande de ne pas
        # faire.
        metadonnees = {m.cle: m.valeur for m in document.metadonnees}
        metadonnees.update(libelles.get(document.id, {}))
        exemples.append(export_modele.chemin_dans_archive(
            document, metadonnees,
            (corps.modele_dossier or "").strip() or None,
            (corps.modele_nom or "").strip() or None, pris))
    return {"total": len(documents), "exemples": exemples}


@app.delete("/exports-modele/{demande_id}")
def supprimer_export_modele(
    demande_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Retire une demande, et l'archive avec (§22.66).

    On ne pouvait que les accumuler. Une archive est une **copie complète** d'une
    partie du foyer posée sur le disque : la laisser traîner parce que rien ne
    permet de l'enlever est le contraire de ce qu'on veut. La trace du geste
    reste au journal ; c'est le fichier qui part.
    """
    demande = session.get(ExportModele, demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if not user.est_admin and demande.utilisateur_id != user.id:
        raise HTTPException(status_code=403, detail="Cette archive ne vous appartient pas.")
    if demande.chemin and os.path.isfile(demande.chemin):
        try:
            os.remove(demande.chemin)
        except OSError:
            logging.getLogger(__name__).warning(
                "Archive %s non effacée", demande.chemin)
    audit.journaliser(session, user, "export.selection_supprimee", "export", demande.id,
                      details={"statut": demande.statut})
    session.delete(demande)
    session.commit()
    return {"ok": True}


@app.get("/exports-modele")
def lister_exports_modele(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Mes demandes — et toutes, pour un administrateur. Une archive est une copie
    de documents du foyer : savoir qui en a sorti une, et quand, fait partie de
    ce qu'un administrateur doit pouvoir regarder.
    """
    try:
        droits.exiger_general(user, "exporter_selection")
    except droits.DroitRefuse as refus:
        raise HTTPException(status_code=403, detail=str(refus))
    query = session.query(ExportModele).options(joinedload(ExportModele.utilisateur))
    if not user.est_admin:
        query = query.filter(ExportModele.utilisateur_id == user.id)
    return [_serialiser_export(d)
            for d in query.order_by(ExportModele.id.desc()).limit(50)]


@app.get("/exports-modele/{demande_id}/fichier")
def telecharger_export_modele(
    demande_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    L'archive, à celui qui l'a demandée.

    Pas de téléchargement unique ici, contrairement à l'export de secours : c'est
    une sélection qu'on donne à quelqu'un, on la retélécharge parce qu'un envoi a
    échoué. Elle est purgée avec les autres archives, à l'expiration réglée.
    """
    demande = session.get(ExportModele, demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if not user.est_admin and demande.utilisateur_id != user.id:
        raise HTTPException(status_code=403, detail="Cette archive ne vous appartient pas.")
    if demande.statut != "pret" or not demande.chemin or not os.path.isfile(demande.chemin):
        raise HTTPException(status_code=404, detail="Archive indisponible.")
    audit.journaliser(session, user, "export.selection_telechargee", "export", demande.id)
    session.commit()
    return FileResponse(demande.chemin, media_type="application/zip",
                        filename=os.path.basename(demande.chemin))


@app.get("/vues", response_model=list[VueOut])
def lister_vues(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Vues visibles : les siennes, et les vues partagées auxquelles elle a droit.

    Une vue est une lecture préfiltrée du registre (§19.12) : elle peut être
    réservée à certains rôles. Sans restriction déclarée, elle suit `partagee`
    comme avant — pouvoir restreindre n'oblige pas chaque foyer à le faire.

    Deux filtres se cumulent, et le second n'est pas redondant : une vue peut
    être offerte à tout le monde tout en pointant une catégorie que celui qui
    regarde n'a pas le droit de voir. Elle n'aurait alors rien à montrer.
    """
    query = session.query(VueEnregistree).options(joinedload(VueEnregistree.utilisateur))
    if not user.est_admin:
        query = query.filter(
            (VueEnregistree.partagee.is_(True)) | (VueEnregistree.utilisateur_id == user.id)
        )
        ids_autorises = droits.categories_autorisees(session, user)
        if ids_autorises is not None:
            query = query.filter(
                (VueEnregistree.categorie_id.is_(None))
                | (VueEnregistree.categorie_id.in_(ids_autorises))
            )
    vues = query.order_by(VueEnregistree.ordre, VueEnregistree.nom).all()
    if not user.est_admin:
        vues = [v for v in vues if droits.vue_visible(session, user, v)]
    return [_serialize_vue(v, user) for v in vues]


@app.post("/vues", response_model=VueOut)
def creer_vue(
    payload: VueIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Crée une vue enregistrée. **Réservé aux administrateurs.**

    Les vues sont un élément de navigation partagé, au même titre que les
    catégories : les laisser créer par chacun remplirait la barre latérale de
    recherches personnelles, et rendrait le classement du foyer illisible.
    Chacun garde évidemment la recherche libre et les filtres de colonne, qui ne
    laissent pas de trace dans la navigation.
    """
    _exiger_administrateur(user, "Seul un administrateur peut créer une vue.")
    _verifier_categorie_visible(payload.categorie_id, user, session)
    vue = VueEnregistree(
        nom=payload.nom.strip(),
        categorie_id=payload.categorie_id,
        criteres=_valider_criteres(payload.criteres, session),
        utilisateur_id=user.id,
        partagee=payload.partagee,
        groupement=_valider_groupement(payload.groupement, session),
        liens=_valider_liens(payload.liens, session),
        ordre=payload.ordre,
    )
    if not vue.nom:
        raise HTTPException(status_code=422, detail="Le nom de la vue est obligatoire")
    session.add(vue)
    session.commit()
    session.refresh(vue)
    return _serialize_vue(vue, user)


@app.put("/vues/{vue_id}", response_model=VueOut)
def modifier_vue(
    vue_id: int,
    payload: VueIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    vue = _vue_accessible(vue_id, user, session, ecriture=True)
    _verifier_categorie_visible(payload.categorie_id, user, session)
    if not payload.nom.strip():
        raise HTTPException(status_code=422, detail="Le nom de la vue est obligatoire")

    vue.nom = payload.nom.strip()
    vue.categorie_id = payload.categorie_id
    vue.criteres = _valider_criteres(payload.criteres, session)
    vue.groupement = _valider_groupement(payload.groupement, session)
    vue.liens = _valider_liens(payload.liens, session, vue.id)
    vue.partagee = payload.partagee
    vue.ordre = payload.ordre
    session.commit()
    session.refresh(vue)
    return _serialize_vue(vue, user)


@app.delete("/vues/{vue_id}")
def supprimer_vue(
    vue_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Supprime une vue. **Réservé aux administrateurs.**

    Une vue sert à tout le foyer ; qu'un compte puisse la faire disparaître pour
    les autres — ou pour lui-même, sans pouvoir la recréer — n'a pas de sens.
    """
    _exiger_administrateur(user, "Seul un administrateur peut supprimer une vue.")
    vue = _vue_accessible(vue_id, user, session, ecriture=True)
    session.delete(vue)
    session.commit()
    return {"ok": True}


# ------------------------------------------------------------
# Listes de référence (catégories visibles, fournisseurs)
# ------------------------------------------------------------

@app.get("/installation")
def etat_installation(session: Session = Depends(get_session)):
    """
    Y a-t-il quelqu'un ? Route ouverte, par nécessité : c'est elle qui dit à
    l'interface s'il faut proposer la création du premier compte. Elle ne révèle
    rien qu'une tentative de connexion ne révélerait déjà.
    """
    return installation.etat(session)


@app.post("/installation")
def premiere_installation(
    payload: dict,
    request: Request,
    reponse_http: Response,
    session: Session = Depends(get_session),
):
    """
    Crée le premier compte administrateur et pose les réglages de départ.

    Ouverte **uniquement tant qu'aucun compte n'existe** : la porte se referme
    définitivement à la première installation. C'est ce qui permet de l'exposer
    sans authentification — sur une base vierge, il n'y a rien à protéger, et
    dès qu'il y a quelque chose, l'entrée n'existe plus.
    """
    try:
        resultat = installation.installer(
            session,
            email=payload.get("email", ""),
            mot_de_passe=payload.get("mot_de_passe", ""),
            nom=payload.get("nom", ""),
            prenom=payload.get("prenom", ""),
            nom_foyer=payload.get("nom_foyer", ""),
            fuseau=payload.get("fuseau_horaire", ""),
            classement=payload.get("classement", "conserver"),
        )
    except installation.InstallationRefusee as erreur:
        raise HTTPException(status_code=400, detail=str(erreur))
    except reglages.ReglageInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))

    utilisateur = session.query(Utilisateur).filter_by(email=resultat["email"]).one()
    audit.journaliser(session, utilisateur, "installation.terminee", "installation", None,
                      details={"email": utilisateur.email,
                               "classement": payload.get("classement", "conserver")})
    session.commit()

    # On ouvre la session dans la foulée : demander de se reconnecter juste après
    # avoir choisi son mot de passe serait une formalité de plus, sans gain.
    jeton = auth.ouvrir_session(session, utilisateur, request)
    auth.poser_cookies_session(reponse_http, jeton)
    return {**resultat, "access_token": jeton, "token_type": "bearer"}


@app.get("/apparence")
def apparence_publique(session: Session = Depends(get_session)):
    """
    Le strict nécessaire pour dessiner l'écran de connexion : nom du foyer,
    thème, couleur d'accent. Route ouverte, par nécessité — personne n'est encore
    connecté quand cet écran s'affiche.

    **Ce que cela expose, et pourquoi c'est assumé** : le nom du foyer est
    visible de qui atteint la page de connexion. C'est le sens même du réglage —
    dire qu'on est chez soi — et un foyer qui préfère la discrétion le laisse
    vide. Rien d'autre ne sort par ici : ni compte, ni catégorie, ni comptage.
    """
    from . import personnalisation

    valeurs = reglages.tous(session)
    return {
        **{cle: valeurs.get(cle, "")
           for cle in ("nom_foyer", "theme", "couleur_accent", "langue")},
        # Palettes et traductions déposées par le foyer (§22.50, §22.51). Elles
        # partent d'ici parce que l'écran de connexion doit déjà être dans la
        # bonne langue et la bonne couleur : le demander après serait le voir
        # changer sous les yeux de qui se connecte.
        "themes": personnalisation.themes(),
        "langues": personnalisation.langues(),
    }


@app.get("/reglages")
def lire_reglages(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Réglages généraux, tels que l'interface en a besoin pour s'afficher — le
    fuseau horaire au premier chef. En lecture pour tout compte connecté : ils
    décrivent la présentation, pas le fonctionnement.
    """
    return reglages.tous(session)


@app.get("/categories/colonnes")
def lister_colonnes_categories(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Colonnes du tableau pour chaque catégorie (§18.1).

    Renvoyées toutes ensemble : passer d'une catégorie à l'autre ne doit pas
    coûter un aller-retour réseau, sans quoi le tableau clignote à chaque clic
    dans la navigation.
    """
    return colonnes.toutes(session)


@app.get("/categories")
def lister_categories(
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """Catégories visibles par l'utilisateur courant (toutes pour un admin)."""
    ids_autorises = droits.categories_autorisees(session, user)
    # l'ordre voulu par l'administrateur d'abord, l'alphabet ensuite pour départager
    query = session.query(Categorie).order_by(Categorie.ordre, Categorie.nom)
    if ids_autorises is not None:
        query = query.filter(Categorie.id.in_(ids_autorises))  # liste vide -> aucune catégorie
    return query.all()


