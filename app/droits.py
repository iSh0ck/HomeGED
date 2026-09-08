"""
Droits : ce que chacun peut faire, et où (§19.12).

Un rôle disait deux choses par catégorie — voir, modifier — et tout le reste
tenait dans un unique interrupteur `est_admin` : soit on ne peut rien
administrer, soit on peut tout, y compris sortir l'archive entière du foyer.
Pour un foyer où quelqu'un doit pouvoir ranger les factures sans pouvoir
supprimer un contrat ni exporter l'archive, il n'y avait pas de réponse.

**Tout est ici, et nulle part ailleurs.** Les contrôles étaient dispersés —
`categories_autorisees` dans `auth.py`, `_exiger_administrateur` dans `api.py`,
une garde de routeur dans `admin.py` — et une règle écrite à trois endroits est
une règle qui divergera. Un contrôle oublié n'est pas une gêne, c'est un trou :
il faut donc qu'il n'y ait qu'un seul endroit où l'écrire.

Trois axes :

* **ce qu'on peut faire d'un document** : `voir`, `modifier`, `deposer`,
  `telecharger`, `supprimer`, `gerer_versions` ;
* **où** : sur un dossier, valable pour tous ses types ; ou sur un type, qui
  l'emporte alors sur son dossier. L'absence de ligne signifie « hérité » —
  c'est la présence d'une ligne qui fait l'exception, jamais un troisième état à
  renseigner ;
* **le reste** : les droits généraux, déclarés ci-dessous parce que ce sont des
  points d'entrée du logiciel, pas des données du foyer.

`est_admin` demeure — tout est permis — et reste la protection à ne pas perdre :
la sécurité du dernier administrateur (§18.44) s'y adosse.
"""
from typing import Optional

from sqlalchemy.orm import Session

from .db import Categorie, DroitCategorie, Utilisateur

# ------------------------------------------------------------------
# Ce qu'on peut faire d'un document, par emplacement
# ------------------------------------------------------------------

VOIR = "voir"
MODIFIER = "modifier"
DEPOSER = "deposer"
TELECHARGER = "telecharger"
SUPPRIMER = "supprimer"
GERER_VERSIONS = "gerer_versions"

# @traduit-a-la-lecture
ACTIONS = {
    VOIR: ("peut_voir", "Consulter la fiche"),
    MODIFIER: ("peut_modifier", "Modifier les champs"),
    DEPOSER: ("peut_deposer", "Déposer un document"),
    TELECHARGER: ("peut_telecharger", "Télécharger le fichier"),
    SUPPRIMER: ("peut_supprimer", "Mettre à la corbeille"),
    GERER_VERSIONS: ("peut_gerer_versions", "Gérer les versions"),
}

# ------------------------------------------------------------------
# Droits généraux, hors catégorie
# ------------------------------------------------------------------
#
# Déclarés en dur : ce sont des points d'entrée du logiciel, pas des données du
# foyer. Une liste en base se désynchroniserait au premier renommage, et l'on
# découvrirait l'écart par un droit devenu sans effet.

GENERAUX = {
    "analyser": "Centre d'analyse",
    "travaux": "Serveur de travaux et dépôt",
    "donnees": "Tables de données du foyer",
    "vues_partagees": "Vues enregistrées",
    "tableaux_partages": "Tableaux de bord partagés",
    "exporter_archive": "Export de l'archive",
    # Distinct du précédent (§21.13) : sortir une sélection rangée pour le
    # comptable n'est pas sortir tout le foyer. Le premier est une porte de
    # sortie définitive, le second un geste courant — les confondre obligerait à
    # donner l'un pour permettre l'autre.
    "exporter_selection": "Export d'une sélection",
    "journal": "Journal d'audit",
    "reglages": "Réglages et classement",
    "comptes": "Comptes, rôles et droits",
}


def branches_autorisees(session, user) -> dict:
    """
    Les branches auxquelles ce compte est restreint, par champ (§21.7).

    Rend `{champ: {valeurs}}`. Un champ absent du dictionnaire n'est pas
    restreint. Deux règles, et elles découlent l'une comme l'autre du principe
    posé au §19.12 — **les rôles s'additionnent** :

      * un rôle **sans aucune ligne** sur un champ n'y met pas de restriction ;
        si l'un des rôles de la personne est dans ce cas, le champ n'est donc
        restreint pour personne qui porte ce rôle. Une restriction que n'importe
        quel autre rôle lèverait serait un piège, pas un droit ;
      * sinon, les valeurs des rôles s'ajoutent.

    Un administrateur n'est jamais restreint : c'est lui qui pose ces lignes.
    """
    if getattr(user, "est_admin", False):
        return {}

    par_role = []
    for role in user.roles:
        valeurs = {}
        for ligne in role.droits_branche:
            valeurs.setdefault(ligne.champ, set()).add(ligne.valeur)
        par_role.append(valeurs)
    if not par_role:
        return {}

    # Un champ n'est restreint que si **tous** les rôles le restreignent.
    champs = set.intersection(*(set(v) for v in par_role)) if par_role else set()
    return {champ: set().union(*(v[champ] for v in par_role)) for champ in champs}


class DroitRefuse(Exception):
    """Refus destiné à l'écran : il dit ce qui manque, pas seulement que c'est non."""


# ------------------------------------------------------------------
# Résolution
# ------------------------------------------------------------------

def _lignes(user: Utilisateur) -> dict:
    """Droits déclarés par les rôles de cette personne, par catégorie."""
    par_categorie: dict[int, list[DroitCategorie]] = {}
    for role in user.roles:
        for droit in role.droits_categorie:
            par_categorie.setdefault(droit.categorie_id, []).append(droit)
    return par_categorie


def _chaine(session: Session, categorie_id: int) -> list[int]:
    """La catégorie, puis ses parents : l'ordre dans lequel on cherche un droit."""
    chaine, vus = [], set()
    courant = session.get(Categorie, categorie_id)
    while courant is not None and courant.id not in vus:
        chaine.append(courant.id)
        vus.add(courant.id)
        courant = session.get(Categorie, courant.parent_id) if courant.parent_id else None
    return chaine


def accorde(session: Session, user: Utilisateur, action: str,
            categorie_id: Optional[int]) -> bool:
    """
    Cette personne peut-elle faire cela, ici ?

    On descend la chaîne — le type d'abord, son dossier ensuite — et **la
    première catégorie qui porte un droit tranche**. Un droit posé sur un type
    l'emporte donc sur son dossier, ce qui est le sens même d'une exception :
    sans cela, ouvrir un dossier rouvrirait ce qu'on avait fermé en dessous.

    Plusieurs rôles sur la même catégorie s'additionnent : ce que l'un accorde,
    aucun autre ne le retire. C'est la règle habituelle, et la seule qui rende
    les rôles composables — sinon ajouter un rôle pourrait retirer un accès.
    """
    if user.est_admin:
        return True
    if categorie_id is None:
        # Document sans catégorie : personne ne sait encore ce qu'on en attend, et
        # il reste lisible et corrigeable par tout compte connecté (S10 du plan,
        # choix d'origine confirmé). Les deux actions **destructrices** font
        # exception : il n'y a aucun emplacement où accrocher le droit, et
        # laisser détruire une pièce que personne n'a classée serait ouvrir plus
        # que S10 n'a jamais dit. Elles restent aux administrateurs.
        #
        # Le cas est d'ailleurs résiduel depuis le §19.3 : un dépôt produit
        # toujours un document classé, ou s'arrête à « à classer » sans en
        # produire.
        return action not in (SUPPRIMER, GERER_VERSIONS)
    if action not in ACTIONS:
        raise ValueError(f"Action inconnue : {action}")

    attribut = ACTIONS[action][0]
    par_categorie = _lignes(user)
    for identifiant in _chaine(session, categorie_id):
        lignes = par_categorie.get(identifiant)
        if lignes:
            return any(getattr(ligne, attribut, False) for ligne in lignes)
    return False


def exiger(session: Session, user: Utilisateur, action: str,
           categorie_id: Optional[int]) -> None:
    """Même chose, mais lève un refus lisible plutôt que de rendre `False`."""
    if accorde(session, user, action, categorie_id):
        return
    categorie = session.get(Categorie, categorie_id) if categorie_id else None
    ou = f" sur « {categorie.nom} »" if categorie else ""
    raise DroitRefuse(f"Droit « {ACTIONS[action][1].lower()} » manquant{ou}.")


def categories_autorisees(session: Session, user: Utilisateur,
                          action: str = VOIR) -> Optional[set]:
    """
    Les catégories où cette action est permise. `None` : toutes (administrateur).

    Calculé en descendant l'arbre : une catégorie sans droit propre reprend celui
    de son dossier. Sans cette résolution, une requête filtrée ne verrait que les
    catégories explicitement cochées, et l'héritage ne servirait qu'aux contrôles
    unitaires — deux comportements pour une même règle.
    """
    if user.est_admin:
        return None
    if action not in ACTIONS:
        raise ValueError(f"Action inconnue : {action}")

    attribut = ACTIONS[action][0]
    par_categorie = _lignes(user)
    autorisees = set()
    for categorie in session.query(Categorie):
        for identifiant in _chaine(session, categorie.id):
            lignes = par_categorie.get(identifiant)
            if lignes:
                if any(getattr(ligne, attribut, False) for ligne in lignes):
                    autorisees.add(categorie.id)
                break
    return autorisees


# ------------------------------------------------------------------
# Droits généraux
# ------------------------------------------------------------------

def general(user: Utilisateur, droit: str) -> bool:
    """Cette personne a-t-elle ce droit hors catégorie ?"""
    if droit not in GENERAUX:
        raise ValueError(f"Droit général inconnu : {droit}")
    if user.est_admin:
        return True
    return any(d.droit == droit for role in user.roles for d in role.droits_generaux)


def exiger_general(user: Utilisateur, droit: str) -> None:
    if general(user, droit):
        return
    raise DroitRefuse(f"Droit « {GENERAUX[droit]} » manquant.")


# ------------------------------------------------------------------
# Vues enregistrées
# ------------------------------------------------------------------

def vue_visible(session: Session, user: Utilisateur, vue) -> bool:
    """
    Cette vue est-elle offerte à cette personne ? (§19.12)

    Une vue est une lecture préfiltrée du registre, et toutes n'ont pas à être
    offertes à tout le monde — « Factures impayées » n'intéresse pas qui ne s'en
    occupe pas, et « Documents médicaux » ne le regarde peut-être pas.

    Sans restriction déclarée, la vue suit `partagee` comme avant : pouvoir
    restreindre n'oblige pas chaque foyer à le faire. La sienne reste visible
    quoi qu'il arrive — on ne se cache pas ses propres recherches.
    """
    if user.est_admin or vue.utilisateur_id == user.id:
        return True
    reserves = {d.role_id for d in vue.droits}
    if not reserves:
        return bool(vue.partagee)
    return bool(reserves & {role.id for role in user.roles})


def resume(session: Session, user: Utilisateur) -> dict:
    """
    Ce que l'interface a besoin de savoir pour ne montrer que le faisable.

    Un écran qui propose une action refusée ensuite fait perdre deux fois : au
    clic, et à la lecture du message.
    """
    return {
        "est_admin": bool(user.est_admin),
        "generaux": sorted(d for d in GENERAUX if general(user, d)),
        "categories": {
            action: (None if user.est_admin
                     else sorted(categories_autorisees(session, user, action)))
            for action in ACTIONS
        },
    }


def filtrer_documents(query, session: Session, user: Utilisateur,
                      action: str = VOIR, corbeille: bool = False):
    """
    Restreint une requête Document aux catégories autorisées, plus les documents
    sans catégorie (choix d'origine assumé, S10 du plan).

    **Et aux documents vivants** (§21.1) : un document en corbeille n'apparaît
    dans aucune liste, aucun décompte, aucune recherche, aucun lien. Le passage
    obligé est ici — c'est ce qui garantit qu'aucun écran ne l'oubliera, y compris
    ceux qu'on écrira plus tard. `corbeille=True` pour les deux écrans qui, eux,
    ne montrent que cela.

    La session est celle de la requête en cours, et non une nouvelle : en ouvrir
    une seconde à chaque appel ferait fuir une connexion par page affichée.

    Les imports sont locaux : `filtres` et `groupes` s'appuient sur ce module,
    les remonter en tête créerait un cycle.
    """
    from sqlalchemy import false, or_

    from . import filtres, groupes
    from .db import Document
    if not corbeille:
        query = query.filter(Document.date_suppression.is_(None))

    # Les branches auxquelles ce compte est restreint (§21.7). Posées ici, elles
    # valent pour **tout** : la liste, la recherche globale, les liens, les
    # vignettes, les décomptes d'une fiche, les branches du repli. Les poser
    # ailleurs les aurait fait fuir par le premier écran écrit ensuite.
    for champ, valeurs in branches_autorisees(session, user).items():
        conditions = []
        for valeur in sorted(valeurs):
            try:
                conditions.append(filtres.condition(
                    session, filtres.Filtre(**groupes.critere(champ, valeur))))
            except filtres.FiltreInvalide:
                continue   # une branche devenue invalide ne doit pas tout ouvrir
        # Aucune condition lisible : on ferme, on n'ouvre pas. Une restriction
        # qu'on ne sait plus appliquer ne se transforme pas en autorisation.
        query = query.filter(or_(*conditions) if conditions else false())

    ids_autorises = categories_autorisees(session, user, action)
    if ids_autorises is None:  # admin
        return query
    if ids_autorises:
        return query.filter(
            (Document.categorie_id.is_(None)) | (Document.categorie_id.in_(ids_autorises))
        )
    return query.filter(Document.categorie_id.is_(None))
