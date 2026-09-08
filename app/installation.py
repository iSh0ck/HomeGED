"""
Première installation (§18.23).

Le projet vise plusieurs foyers. Or le premier compte naissait de
`ADMIN_EMAIL`/`ADMIN_PASSWORD` dans `.env` : pour ouvrir HomeGED chez soi, il
fallait éditer un fichier sur le serveur, et le mot de passe du foyer restait
écrit en clair sur le disque, souvent pour toujours.

Ce module permet de créer ce premier compte **depuis l'écran**, à la seule
condition qu'aucun compte n'existe encore. C'est ce qui rend l'ouverture sûre :
la porte ne s'ouvre que sur une base vierge, et se referme définitivement dès le
premier compte créé. Un serveur exposé sur Internet n'offre donc pas de fenêtre
d'entrée — sauf à ce que personne ne s'y soit jamais connecté, auquel cas il n'y
a rien à protéger.

L'assistant fait aussi le reste du premier réglage : nom du foyer, fuseau,
classement de départ. C'est là que se joue l'adaptation à un autre foyer que
celui pour lequel le projet a été écrit.
"""
import logging

from sqlalchemy.orm import Session

from . import auth, configuration, modeles, reglages
from .db import (
    Categorie,
    Document,
    RegleChampCategorie,
    ProfilExtraction,
    RegleExtraction,
    Utilisateur,
    VueEnregistree,
)

log = logging.getLogger(__name__)


class InstallationRefusee(Exception):
    pass


def est_requise(session: Session) -> bool:
    """Vrai tant qu'aucun compte n'existe : c'est la seule condition d'ouverture."""
    return session.query(Utilisateur).count() == 0


def etat(session: Session) -> dict:
    """
    Ce que l'écran d'accueil a besoin de savoir avant de se dessiner. Ne révèle
    rien d'exploitable : le nombre de catégories semées et l'existence ou non
    d'un compte — ce dernier point étant de toute façon visible en tentant de
    se connecter.
    """
    requise = est_requise(session)
    return {
        "requise": requise,
        "classement_seme": session.query(Categorie).count() if requise else 0,
        "regles_semees": session.query(RegleExtraction).count() if requise else 0,
        "fuseaux": reglages.fuseaux_proposables(),
        "modeles": modeles.lister(),
    }


def _documents_classes(session: Session) -> int:
    """Combien de documents la base porte. Isolé pour être observable."""
    return session.query(Document).count()


def _vider_le_classement(session: Session) -> dict:
    """
    Retire ce que l'installation a semé : catégories, regex de classement, champs
    attendus, vues enregistrées.

    **Refusé s'il existe le moindre document.** Le classement n'est pas
    décoratif : des documents y sont rattachés, et les effacer d'un revers
    laisserait des fiches sans catégorie et des champs sans règle. Sur une base
    vierge, la question ne se pose pas.
    """
    if _documents_classes(session) > 0:
        raise InstallationRefusee(
            "Des documents sont déjà classés : le classement ne peut plus être vidé d'un bloc.")

    compte = {
        "vues": session.query(VueEnregistree).delete(synchronize_session=False),
        "champs_attendus": session.query(RegleChampCategorie).delete(synchronize_session=False),
        # Les règles partent avec leur jeu (cascade) : les compter à part
        # donnerait deux fois le même ménage dans le bilan.
        "jeux_extraction": session.query(ProfilExtraction).delete(synchronize_session=False),
        "categories": session.query(Categorie).delete(synchronize_session=False),
    }
    session.commit()
    return {cle: int(valeur or 0) for cle, valeur in compte.items()}


def installer(session: Session, email: str, mot_de_passe: str, nom: str = "",
              prenom: str = "", nom_foyer: str = "", fuseau: str = "",
              classement: str = "conserver") -> dict:
    """
    Crée le premier compte et pose les réglages de départ.

    L'ordre compte : on valide **tout** avant d'écrire quoi que ce soit. Un
    assistant qui créerait le compte puis échouerait sur le fuseau laisserait une
    installation à moitié faite, et sa deuxième tentative se heurterait à la
    porte désormais fermée.
    """
    if not est_requise(session):
        raise InstallationRefusee("HomeGED est déjà installé : cette page n'a plus d'objet.")

    email = (email or "").strip().lower()
    if "@" not in email or len(email) < 5:
        raise InstallationRefusee("L'adresse e-mail ne ressemble pas à une adresse.")

    minimum = reglages.entier(session, "longueur_min_mot_de_passe") or 10
    if len(mot_de_passe or "") < minimum:
        raise InstallationRefusee(
            f"Le mot de passe doit faire au moins {minimum} caractères.")

    if classement not in ("conserver", "vierge") and classement not in modeles.MODELES:
        raise InstallationRefusee("Choix de classement inattendu.")

    a_poser = {}
    if nom_foyer:
        a_poser["nom_foyer"] = nom_foyer
    if fuseau:
        a_poser["fuseau_horaire"] = fuseau
    for cle, valeur in a_poser.items():
        reglages.valider(cle, valeur)      # lève avant toute écriture

    vide = _vider_le_classement(session) if classement == "vierge" else {}

    administrateur = Utilisateur(
        email=email,
        nom=(nom or "").strip() or "Administrateur",
        prenom=(prenom or "").strip() or None,
        mot_de_passe_hash=auth.hash_mot_de_passe(mot_de_passe),
        est_admin=True,
        actif=True,
    )
    session.add(administrateur)
    session.commit()

    if a_poser:
        reglages.enregistrer(session, a_poser)

    # Un modèle demandé s'applique **par-dessus** ce que l'installation a semé :
    # les noms se recoupent, seul ce qui manque est ajouté. Le foyer part donc
    # d'un classement complet, à élaguer — plus facile que d'inventer ce qui
    # manque.
    applique = {}
    if classement in modeles.MODELES:
        applique = configuration.importer(session, modeles.charger(classement))

    log.info("Installation terminée : compte administrateur %s créé", email)
    return {
        "ok": True,
        "email": administrateur.email,
        "classement_vide": vide,
        "modele_applique": applique,
        "reglages": reglages.tous(session),
    }
