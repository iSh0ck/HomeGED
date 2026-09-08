"""
Authentification par JWT + résolution des droits d'un utilisateur sur les
catégories (via ses rôles). Un administrateur (est_admin=True) voit et
modifie tout, sans passer par les rôles.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
# PyJWT plutôt que python-jose : cette dernière n'a plus bougé depuis 2021 et
# appelle `datetime.utcnow()`, que Python supprimera. Le format des jetons ne
# change pas — même algorithme, même clé, mêmes revendications — donc les
# sessions ouvertes au moment de la bascule restent valables.
import jwt
from jwt import PyJWTError
from passlib.context import CryptContext
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as SessionBase

from . import config
from .db import get_session, SessionLocal, SessionOuverte, Utilisateur

log = logging.getLogger(__name__)

# bcrypt_sha256 pré-hache le mot de passe en SHA-256 avant de le passer à
# bcrypt : ça supprime complètement la limite de 72 octets de bcrypt (qui
# provoque un ValueError avec les versions récentes du paquet `bcrypt` au
# lieu de tronquer silencieusement comme avant), sans rien changer côté API.
pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto",
                           bcrypt_sha256__rounds=config.BCRYPT_ROUNDS)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# Le navigateur s'authentifie par un cookie `httpOnly` : un script injecté dans
# la page ne peut alors pas lire le jeton, là où un `localStorage` le lui
# offrait. Le jeton reste par ailleurs renvoyé dans le corps de la réponse, pour
# scripter l'API avec un en-tête `Authorization` — un script n'est pas soumis
# aux mêmes risques qu'une page.
NOM_COOKIE_SESSION = "homeged_session"

# Un cookie ne distingue pas les requêtes voulues par l'utilisateur de celles
# provoquées par un autre site : c'est la faille CSRF. `SameSite=Strict` la
# ferme déjà, mais on double d'un jeton anti-CSRF, lisible par le script de la
# page (donc non `httpOnly`) et exigé en en-tête sur toute écriture. Un site
# tiers ne peut lire ni ce cookie ni forger l'en-tête.
NOM_COOKIE_CSRF = "homeged_csrf"
ENTETE_CSRF = "X-CSRF-Token"
METHODES_SANS_EFFET = {"GET", "HEAD", "OPTIONS"}


def _otp_exige(session: SessionBase, utilisateur) -> bool:
    """La double authentification est-elle exigée de ce compte ?"""
    if utilisateur.otp_impose:
        return True
    try:
        from . import reglages
        return reglages.booleen(session, "otp_obligatoire")
    except SQLAlchemyError:
        return False


def duree_session_minutes(session: Optional[SessionBase] = None) -> int:
    """
    Durée d'une session, en minutes.

    Réglée par le foyer (§18.22) : courte sur un poste partagé, longue sur un
    ordinateur familial. `.env` garde la main comme valeur de repli — une base
    injoignable ne doit pas empêcher d'ouvrir une session.
    """
    from . import reglages

    fermer = session is None
    if fermer:
        session = SessionLocal()
    try:
        heures = reglages.entier(session, "duree_session_heures")
        return max(1, heures) * 60
    except SQLAlchemyError:
        return config.ACCESS_TOKEN_EXPIRE_MINUTES
    finally:
        if fermer:
            session.close()


def poser_cookies_session(reponse: Response, jeton: str) -> None:
    """Installe le cookie de session et son jeton anti-CSRF associé."""
    duree = duree_session_minutes() * 60
    reponse.set_cookie(
        NOM_COOKIE_SESSION, jeton, max_age=duree, httponly=True,
        samesite="strict", secure=config.COOKIE_SECURE, path="/",
    )
    reponse.set_cookie(
        NOM_COOKIE_CSRF, secrets.token_urlsafe(32), max_age=duree, httponly=False,
        samesite="strict", secure=config.COOKIE_SECURE, path="/",
    )


def retirer_cookies_session(reponse: Response) -> None:
    for nom in (NOM_COOKIE_SESSION, NOM_COOKIE_CSRF):
        reponse.delete_cookie(nom, path="/", samesite="strict", secure=config.COOKIE_SECURE)


def _verifier_csrf(request: Request) -> None:
    """
    Sur une écriture authentifiée par cookie, l'en-tête anti-CSRF doit répondre
    au cookie correspondant. La comparaison est faite en temps constant.
    """
    attendu = request.cookies.get(NOM_COOKIE_CSRF)
    fourni = request.headers.get(ENTETE_CSRF)
    if not attendu or not fourni or not secrets.compare_digest(attendu, fourni):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Jeton anti-CSRF absent ou invalide. Recharge la page et réessaie.",
        )


def hash_mot_de_passe(mot_de_passe: str) -> str:
    return pwd_context.hash(mot_de_passe)


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    return pwd_context.verify(mot_de_passe, hash_stocke)


def creer_token(email: str, version: int = 0, jti: Optional[str] = None) -> str:
    """
    Jeton de session.

    Il porte la version du compte : un changement de mot de passe l'incrémente,
    et tous les jetons déjà délivrés cessent d'être acceptés — y compris celui
    qu'un intrus aurait obtenu avant.

    Il porte aussi un `jti`, identifiant unique de la session, qui fait le lien
    avec la table `sys_sessions` (§17.2). C'est lui qui permet de dire à
    l'utilisateur quels appareils sont connectés, et de fermer l'un d'eux à
    distance — un JWT seul ne se révoque pas.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=duree_session_minutes())
    charge = {"sub": email, "v": version, "exp": expire}
    if jti:
        charge["jti"] = jti
    return jwt.encode(charge, config.SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def ouvrir_session(session: SessionBase, utilisateur, request=None) -> str:
    """
    Enregistre une session et rend le jeton qui la porte.

    L'adresse et le navigateur sont conservés pour que l'utilisateur reconnaisse
    ses propres connexions dans la liste — c'est le seul moyen de repérer celle
    qui n'est pas la sienne.
    """
    jti = secrets.token_hex(16)
    expiration = datetime.now() + timedelta(minutes=duree_session_minutes(session))
    agent = (request.headers.get("user-agent") if request else None) or None

    # Écrite dans sa **propre transaction**, pour la même raison que la trace
    # d'activité (§18.10) : la transaction de la requête a déjà lu `sys_sessions`
    # — c'est ainsi qu'on a reconnu l'appelant — et MariaDB refuse d'y écrire si
    # la table a bougé depuis (isolation par instantané, erreur 1020). Deux
    # personnes qui se connectent à la même minute suffisaient à faire échouer
    # l'une des deux ; la suite de tests l'a reproduit avant qu'un foyer ne le
    # rencontre.
    ecriture = SessionLocal()
    try:
        ecriture.add(SessionOuverte(
            utilisateur_id=utilisateur.id,
            jti=jti,
            date_expiration=expiration,
            date_activite=datetime.now(),
            adresse=_adresse(request),
            agent=agent[:255] if agent else None,
        ))
        ecriture.commit()
    finally:
        ecriture.close()
    return creer_token(utilisateur.email, utilisateur.jeton_version or 0, jti)


def _tracer_activite(session, ouverte) -> None:
    """
    Note que la session a servi, au plus une fois par minute — une écriture à
    chaque requête ferait travailler la base pour un affichage qui se contente
    de « il y a deux heures ».

    **Dans sa propre transaction, et l'écriture en premier.** C'est ce qui a
    causé un défaut réel : un écran de l'administration lance plusieurs requêtes
    d'un coup, toutes portées par la même session ouverte ; elles franchissaient
    ensemble le seuil de la minute et écrivaient toutes la même ligne. MariaDB
    12 applique par défaut l'isolation par instantané
    (`innodb_snapshot_isolation`, depuis 11.6) : une transaction qui a *lu*
    quelque chose, puis tente de modifier une ligne changée entre-temps, est
    refusée — « Record has changed since last read » — au lieu d'attendre son
    tour. La requête entière échouait alors en 500, pour une trace d'activité.

    Mesuré : en lisant d'abord, une écriture sur deux échoue quand six requêtes
    partent ensemble ; en ouvrant une transaction neuve dont l'UPDATE est la
    première instruction, aucune sur soixante. La condition sur la date suffit
    ensuite à ce que les retardataires n'écrivent rien.

    Le `try` reste, par principe : une trace d'activité ne vaut pas la peine de
    faire échouer la requête qui la produit.

    **On ne touche pas à l'objet de la requête.** Écrire `ouverte.date_activite`
    ici semblait économiser une écriture à la requête suivante ; en réalité cela
    salit l'objet suivi par la session de la requête, et l'ORM le réécrivait au
    prochain `commit` — depuis la transaction de la requête, celle-là même qu'on
    voulait tenir à l'écart. Le défaut revenait donc par la porte de derrière,
    sur la requête suivante qui enregistrait quelque chose. La ligne relue au
    prochain appel portera de toute façon la bonne date.
    """
    maintenant = datetime.now()
    if ouverte.date_activite and (maintenant - ouverte.date_activite).total_seconds() <= 60:
        return

    ecriture = SessionLocal()
    try:
        ecriture.query(SessionOuverte).filter(
            SessionOuverte.id == ouverte.id,
            or_(SessionOuverte.date_activite.is_(None),
                SessionOuverte.date_activite < maintenant - timedelta(seconds=60)),
        ).update({SessionOuverte.date_activite: maintenant}, synchronize_session=False)
        ecriture.commit()
    except SQLAlchemyError:
        # La session reste parfaitement utilisable : seule sa date de dernière
        # activité restera celle d'avant.
        ecriture.rollback()
        log.debug("Trace d'activité non écrite pour la session %s", ouverte.id, exc_info=True)
    finally:
        ecriture.close()


def _adresse(request) -> Optional[str]:
    """Adresse réelle de l'appelant, derrière le proxy (cf. app/limitation.py)."""
    if not request:
        return None
    from . import limitation
    return limitation.adresse_client(request)[:64]


def jti_du_jeton(jeton: str) -> Optional[str]:
    """Identifiant de session porté par un jeton, sans en vérifier l'expiration.

    La déconnexion doit fonctionner même sur un jeton tout juste expiré : on
    cherche seulement à savoir quelle ligne fermer.
    """
    try:
        charge = jwt.decode(jeton, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM],
                            options={"verify_exp": False})
    except PyJWTError:
        return None
    return charge.get("jti")


def revoquer_toutes_les_sessions(session: SessionBase, utilisateur_id: int,
                                 sauf_jti: Optional[str] = None) -> int:
    """Ferme toutes les sessions d'un compte. Rend le nombre de sessions fermées."""
    query = session.query(SessionOuverte).filter_by(
        utilisateur_id=utilisateur_id, date_revocation=None)
    if sauf_jti:
        query = query.filter(SessionOuverte.jti != sauf_jti)
    lignes = query.all()
    for ligne in lignes:
        ligne.date_revocation = datetime.now()
    return len(lignes)


def revoquer_session(session: SessionBase, jti: str) -> bool:
    """Ferme une session. Rend vrai si elle était encore ouverte."""
    ligne = session.query(SessionOuverte).filter_by(jti=jti, date_revocation=None).one_or_none()
    if not ligne:
        return False
    ligne.date_revocation = datetime.now()
    session.commit()
    return True


# Jeton intermédiaire de la double authentification : il atteste que le mot de
# passe est bon, rien de plus. Il ne donne accès à aucune route et vit deux
# minutes — le temps de lire un code sur un téléphone, pas davantage.
# ------------------------------------------------------------------
# Consultation du registre sous l'identité d'un autre compte (§18.50)
# ------------------------------------------------------------------
#
# À quoi cela sert : régler des droits sans pouvoir vérifier ce qu'ils donnent à
# voir, c'est régler à l'aveugle. Un administrateur doit pouvoir regarder le
# registre avec les yeux d'un autre compte — c'est le seul moyen honnête de
# s'assurer qu'une catégorie sensible ne s'affiche pas là où on ne l'attend pas.
#
# Trois garde-fous, parce que la fonction consiste à se faire passer pour
# quelqu'un d'autre :
#
#   * **lecture seule** : toute méthode autre que GET/HEAD/OPTIONS est refusée.
#     On regarde, on n'agit pas — sans quoi une action apparaîtrait au journal
#     sous le nom de quelqu'un qui ne l'a pas faite ;
#   * **jeton signé, court, et nominatif** : il porte l'administrateur qui l'a
#     demandé et ne vaut que pour lui. Il n'est pas une session : `usage`
#     l'empêche d'être présenté comme tel ;
#   * **tracé une fois, à l'ouverture** — le journal dit qui a consulté qui, et
#     quand. Le tracer à chaque requête noierait l'information.
USAGE_CONSULTATION = "consultation"
DUREE_CONSULTATION_MINUTES = 30
ENTETE_CONSULTATION = "X-Consulter-Comme"


def creer_token_consultation(email_cible: str, administrateur_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=DUREE_CONSULTATION_MINUTES)
    return jwt.encode(
        {"sub": email_cible, "usage": USAGE_CONSULTATION, "par": administrateur_id,
         "exp": expire},
        config.SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def _consultation_demandee(request: Request, session: SessionBase, administrateur):
    """
    Le compte sous l'identité duquel lire, quand l'appelant en présente un jeton
    valide. `None` si rien n'est demandé — le cas ordinaire.
    """
    jeton = request.headers.get(ENTETE_CONSULTATION)
    if not jeton:
        return None

    refus = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Consultation sous une autre identité refusée.")
    if not administrateur.est_admin:
        raise refus
    if request.method not in METHODES_SANS_EFFET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consultation en lecture seule : quittez-la pour modifier quoi que ce soit.")
    try:
        charge = jwt.decode(jeton, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consultation expirée : relancez-la depuis l'administration.")
    if charge.get("usage") != USAGE_CONSULTATION:
        raise refus
    # nominatif : le jeton d'un autre administrateur ne vaut rien ici
    if int(charge.get("par") or 0) != int(administrateur.id):
        raise refus

    cible = session.query(Utilisateur).filter_by(
        email=charge.get("sub"), actif=True).one_or_none()
    if not cible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le compte consulté n'existe plus ou a été désactivé.")

    request.state.consultation_par = administrateur.id
    return cible


USAGE_SECOND_FACTEUR = "second_facteur"
DUREE_SECOND_FACTEUR_SECONDES = 120


def creer_token_second_facteur(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=DUREE_SECOND_FACTEUR_SECONDES)
    return jwt.encode({"sub": email, "usage": USAGE_SECOND_FACTEUR, "exp": expire},
                      config.SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def lire_token_second_facteur(jeton: str) -> Optional[str]:
    """L'adresse attestée par un jeton intermédiaire valide, sinon `None`."""
    try:
        charge = jwt.decode(jeton, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except PyJWTError:
        return None
    if charge.get("usage") != USAGE_SECOND_FACTEUR:
        return None
    return charge.get("sub")


# Routes accessibles à un compte à qui la double authentification est imposée
# mais qui ne l'a pas encore configurée. Tout le reste lui est fermé : imposer
# sans contraindre ne serait qu'une suggestion.
#
# `/auth/me` en fait partie, et ce n'est pas un détail : c'est par lui que
# l'interface reconnaît une session au chargement. Le lui refuser laissait le
# compte devant l'écran de connexion après une connexion réussie — bloqué non
# pas hors de l'application, mais hors de la page censée le débloquer.
CHEMINS_CONFIGURATION_OTP = (
    "/auth/me", "/auth/logout",
    "/moi", "/moi/otp/preparer", "/moi/otp/activer",
)


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    session: SessionBase = Depends(get_session),
) -> Utilisateur:
    """
    Identifie l'appelant, par en-tête `Authorization` (scripts) ou par cookie de
    session (navigateur). Une écriture authentifiée par cookie doit en outre
    présenter le jeton anti-CSRF ; un en-tête `Authorization`, lui, n'est jamais
    envoyé automatiquement par un navigateur et n'a donc pas besoin de ce garde-fou.
    """
    exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides ou expirés",
        headers={"WWW-Authenticate": "Bearer"},
    )
    via_cookie = False
    if not token:
        token = request.cookies.get(NOM_COOKIE_SESSION)
        via_cookie = bool(token)
    if not token:
        raise exception
    if via_cookie and request.method not in METHODES_SANS_EFFET:
        _verifier_csrf(request)
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        email = payload.get("sub")
        if not email or payload.get("usage"):
            # un jeton portant un « usage » est intermédiaire (second facteur) :
            # il atteste un mot de passe, il n'ouvre pas de session
            raise exception
    except PyJWTError:
        raise exception

    user = session.query(Utilisateur).filter_by(email=email, actif=True).one_or_none()
    if not user:
        raise exception
    if int(payload.get("v", 0)) != int(user.jeton_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session close : le mot de passe du compte a changé.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    jti = payload.get("jti")
    if jti:
        ouverte = session.query(SessionOuverte).filter_by(jti=jti).one_or_none()
        if not ouverte or ouverte.date_revocation is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session fermée.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _tracer_activite(session, ouverte)
    elif config.EXIGER_SESSION_ENREGISTREE:
        # Jeton d'avant la mise en place du registre : il n'est rattaché à aucune
        # session connue, donc impossible à révoquer. On le refuse plutôt que de
        # laisser subsister des sessions invisibles et infermables.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session à renouveler : reconnectez-vous.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Exigée sur ce compte, ou sur tout le foyer (§18.22). Le réglage global
    # évite d'avoir à cocher la case compte par compte, et s'applique aux comptes
    # créés ensuite sans qu'on ait à y penser.
    if _otp_exige(session, user) and not user.otp_actif \
            and request.url.path not in CHEMINS_CONFIGURATION_OTP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La double authentification est exigée sur ce compte : "
                   "configurez-la depuis « Mon compte » pour retrouver l'accès.",
        )

    # Consultation sous une autre identité (§18.50) : contrôlée une fois que
    # l'appelant a prouvé la sienne, jamais avant.
    consulte = _consultation_demandee(request, session, user)
    return consulte if consulte is not None else user


def require_admin(user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
    if not user.est_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs")
    return user


# `categories_autorisees` a déménagé dans `app/droits.py` au §19.12, avec tout le
# reste des règles d'accès. Elle ne connaissait que deux actions — voir, modifier
# — et ignorait l'héritage entre un dossier et ses types ; surtout, elle était
# l'un des trois endroits où s'écrivaient les contrôles, et une règle écrite à
# trois endroits est une règle qui divergera.


# Mots de passe d'exemple : un `.env` recopié sans être relu ne doit pas ouvrir
# un compte administrateur avec un mot de passe que tout le monde connaît.
MOTS_DE_PASSE_D_EXEMPLE = {"changeme", "change-me", "admin", "motdepasse", "password", ""}


def creer_admin_si_absent(session: SessionBase) -> None:
    """
    Crée le compte administrateur initial au premier démarrage, **si `.env` porte
    un mot de passe délibéré**.

    Sinon, on ne crée rien : l'application propose alors son assistant de
    première installation (§18.23), et le foyer choisit son adresse et son mot de
    passe depuis l'écran, sans qu'ils restent écrits en clair sur le serveur.
    Les installations existantes ne bougent pas — elles ont déjà leur compte, et
    cette fonction s'arrête à la première ligne.
    """
    if session.query(Utilisateur).count() > 0:
        return
    if (config.ADMIN_PASSWORD or "").strip().lower() in MOTS_DE_PASSE_D_EXEMPLE:
        log.info("Aucun compte : l'assistant de première installation prendra la main.")
        return
    admin = Utilisateur(
        email=config.ADMIN_EMAIL,
        nom="Administrateur",
        mot_de_passe_hash=hash_mot_de_passe(config.ADMIN_PASSWORD),
        est_admin=True,
        actif=True,
    )
    session.add(admin)
    session.commit()
