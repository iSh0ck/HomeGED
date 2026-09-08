"""
Conséquences réelles d'une suppression.

Une confirmation qui se contente de demander « Êtes-vous sûr ? » ne renseigne
sur rien : l'utilisateur ignore ce qu'il emporte. Ce module répond précisément —
combien de documents seront déclassés, quelles vues disparaîtront, quels droits
seront perdus — en lisant ce que le schéma prévoit réellement.

Trois natures de conséquence, distinguées parce qu'elles n'appellent pas la même
vigilance :

  `suppression`  ce qui disparaît avec l'objet (cascade en base) ;
  `detachement`  ce qui survit mais perd son lien (clé étrangère remise à nul) ;
  `avertissement` ce qui ne relève pas du schéma et resterait incohérent —
                 un indicateur de tableau de bord pointant une catégorie
                 supprimée, par exemple.
"""
import json
from typing import Optional

from sqlalchemy.orm import Session

from .db import (
    Categorie, Document, DroitCategorie, Metadonnee,
    RegleChampCategorie, RegleExtraction, Role, TableauDeBord, TableDonnees,
    Utilisateur, VueEnregistree,
)


class ObjetIntrouvable(ValueError):
    """Objet inexistant : rien à confirmer."""


def _ligne(nature: str, nombre: int, singulier: str, pluriel: str,
           precision: Optional[str] = None) -> Optional[dict]:
    """Une conséquence, ou rien du tout si elle ne concerne aucun élément."""
    if not nombre:
        return None
    return {
        "nature": nature,
        "nombre": nombre,
        "libelle": f"{nombre} {singulier if nombre == 1 else pluriel}",
        "precision": precision,
    }


def _widgets_citant(session: Session, motif: str) -> int:
    """Indicateurs de tableau de bord dont la description mentionne cette référence."""
    nombre = 0
    for tableau in session.query(TableauDeBord):
        try:
            widgets = json.loads(tableau.widgets or "[]")
        except (ValueError, TypeError):
            continue
        if motif in json.dumps(widgets, ensure_ascii=False):
            nombre += 1
    return nombre


def _categorie(session: Session, identifiant: int) -> dict:
    categorie = session.get(Categorie, identifiant)
    if not categorie:
        raise ObjetIntrouvable("Catégorie introuvable")

    enfants = session.query(Categorie).filter_by(parent_id=identifiant).count()
    documents = session.query(Document).filter_by(categorie_id=identifiant).count()
    vues = session.query(VueEnregistree).filter_by(categorie_id=identifiant).count()
    droits = session.query(DroitCategorie).filter_by(categorie_id=identifiant).count()
    champs = session.query(RegleChampCategorie).filter_by(categorie_id=identifiant).count()

    return {
        "objet": f"la catégorie « {categorie.nom} »",
        "consequences": [
            _ligne("suppression", vues, "vue enregistrée", "vues enregistrées",
                   "elles y étaient rattachées"),
            _ligne("suppression", champs, "champ attendu", "champs attendus",
                   "ce que cette catégorie exigeait de ses documents"),
            _ligne("suppression", droits, "droit de rôle", "droits de rôle",
                   "les autorisations accordées sur cette catégorie"),
            _ligne("detachement", documents, "document sera déclassé",
                   "documents seront déclassés", "ils sont conservés, sans catégorie"),
            _ligne("detachement", enfants, "sous-catégorie remontera à la racine",
                   "sous-catégories remonteront à la racine", "elles ne sont pas supprimées"),
            _ligne("avertissement", _widgets_citant(session, f'"valeur": "{identifiant}"'),
                   "tableau de bord la cite", "tableaux de bord la citent",
                   "leurs indicateurs porteront sur une catégorie disparue"),
        ],
    }


def _utilisateur(session: Session, identifiant: int) -> dict:
    utilisateur = session.get(Utilisateur, identifiant)
    if not utilisateur:
        raise ObjetIntrouvable("Utilisateur introuvable")
    return {
        "objet": f"le compte « {utilisateur.nom_affiche} » ({utilisateur.email})",
        "consequences": [
            _ligne("suppression", len(utilisateur.roles), "rôle attribué", "rôles attribués",
                   "l'attribution disparaît, pas le rôle lui-même"),
            _ligne("detachement",
                   session.query(VueEnregistree).filter_by(utilisateur_id=identifiant).count(),
                   "vue lui appartient", "vues lui appartiennent",
                   "elles sont conservées, sans propriétaire"),
            _ligne("detachement",
                   session.query(TableauDeBord).filter_by(utilisateur_id=identifiant).count(),
                   "tableau de bord lui appartient", "tableaux de bord lui appartiennent",
                   "ils sont conservés"),
            {"nature": "avertissement", "nombre": 0,
             "libelle": "Ses actions restent au journal d'audit",
             "precision": "son adresse y est conservée en clair, la trace reste lisible"},
        ],
    }


def _role(session: Session, identifiant: int) -> dict:
    role = session.get(Role, identifiant)
    if not role:
        raise ObjetIntrouvable("Rôle introuvable")
    return {
        "objet": f"le rôle « {role.nom} »",
        "consequences": [
            _ligne("suppression",
                   session.query(DroitCategorie).filter_by(role_id=identifiant).count(),
                   "droit par catégorie", "droits par catégorie",
                   "les autorisations que ce rôle accordait"),
            _ligne("detachement", len(role.utilisateurs), "compte le perdra",
                   "comptes le perdront",
                   "ils garderont leurs autres rôles, mais pas ces accès"),
        ],
    }


def _regle_extraction(session: Session, identifiant: int) -> dict:
    regle = session.get(RegleExtraction, identifiant)
    if not regle:
        raise ObjetIntrouvable("Règle introuvable")
    return {
        "objet": f"la règle d'extraction « {regle.nom} »",
        "consequences": [
            _ligne("detachement",
                   session.query(Metadonnee).filter_by(regle_id=identifiant).count(),
                   "valeur a été extraite par elle", "valeurs ont été extraites par elle",
                   "les valeurs sont conservées, mais on ne saura plus d'où elles viennent"),
            {"nature": "avertissement", "nombre": 0,
             "libelle": f"Le champ « {regle.champ_cible} » ne sera plus rempli automatiquement",
             "precision": "sur les prochains documents importés"},
        ],
    }


def _regle_champ(session: Session, identifiant: int) -> dict:
    regle = session.get(RegleChampCategorie, identifiant)
    if not regle:
        raise ObjetIntrouvable("Règle introuvable")
    categorie = session.get(Categorie, regle.categorie_id)
    concernes = session.query(Document).filter_by(categorie_id=regle.categorie_id).count()
    return {
        "objet": f"l'exigence « {regle.libelle or regle.champ} »"
                 + (f" sur « {categorie.nom} »" if categorie else ""),
        "consequences": [
            _ligne("avertissement", concernes, "document de cette catégorie",
                   "documents de cette catégorie",
                   "ce champ ne leur sera plus réclamé ; certains peuvent redevenir conformes"),
        ],
    }


def _vue(session: Session, identifiant: int) -> dict:
    vue = session.get(VueEnregistree, identifiant)
    if not vue:
        raise ObjetIntrouvable("Vue introuvable")
    return {
        "objet": f"la vue « {vue.nom} »",
        "consequences": [
            {"nature": "detachement", "nombre": 0,
             "libelle": "Aucun document n'est touché",
             "precision": "une vue n'est qu'une recherche mémorisée"},
        ],
    }


def _tableau(session: Session, identifiant: int) -> dict:
    tableau = session.get(TableauDeBord, identifiant)
    if not tableau:
        raise ObjetIntrouvable("Tableau de bord introuvable")
    try:
        widgets = json.loads(tableau.widgets or "[]")
    except (ValueError, TypeError):
        widgets = []
    return {
        "objet": f"le tableau de bord « {tableau.nom} »",
        "consequences": [
            _ligne("suppression", len(widgets), "indicateur", "indicateurs",
                   "leur description est perdue, les données restent intactes"),
        ],
    }


def _document(session: Session, identifiant: int) -> dict:
    document = session.get(Document, identifiant)
    if not document:
        raise ObjetIntrouvable("Document introuvable")
    partage = session.query(Document).filter(
        Document.chemin_stockage == document.chemin_stockage,
        Document.id != document.id,
    ).count()
    return {
        "objet": "ce document",
        "consequences": [
            _ligne("suppression", len(document.metadonnees), "métadonnée extraite",
                   "métadonnées extraites", "numéro, montant, date…"),
            {"nature": "suppression" if not partage else "avertissement", "nombre": 0,
             "libelle": ("Le PDF partira en corbeille" if not partage
                         else "Le PDF est conservé"),
             "precision": ("récupérable tant qu'elle n'est pas vidée" if not partage
                           else f"{partage} autre(s) enregistrement(s) le référencent encore")},
        ],
    }


def _table_donnees(session: Session, nom_table: str) -> dict:
    from sqlalchemy import text

    inscrite = session.query(TableDonnees).filter_by(nom_table=nom_table).first()
    if not inscrite:
        raise ObjetIntrouvable("Table de données introuvable")
    lignes = session.execute(text(f"SELECT COUNT(*) FROM `{nom_table}`")).scalar()
    champs = session.query(RegleChampCategorie).filter_by(source_table=nom_table).count()
    return {
        "objet": f"la table « {inscrite.libelle} » ({nom_table})",
        "consequences": [
            _ligne("suppression", lignes or 0, "ligne", "lignes",
                   "définitivement — cette table n'a pas de corbeille"),
            _ligne("avertissement", champs, "champ personnalisé y puise ses valeurs",
                   "champs personnalisés y puisent leurs valeurs",
                   "ils ne proposeront plus rien à la saisie"),
        ],
    }


CALCULS = {
    "categorie": _categorie,
    "utilisateur": _utilisateur,
    "role": _role,
    "regle_extraction": _regle_extraction,
    "regle_champ": _regle_champ,
    "vue": _vue,
    "tableau": _tableau,
    "document": _document,
}


def calculer(session: Session, type_objet: str, identifiant) -> dict:
    """
    Décrit ce qu'emporte réellement la suppression d'un objet.
    Lève `ObjetIntrouvable` si l'objet n'existe pas.
    """
    if type_objet == "table_donnees":
        resultat = _table_donnees(session, str(identifiant))
    else:
        calcul = CALCULS.get(type_objet)
        if not calcul:
            raise ObjetIntrouvable(f"Type « {type_objet} » inconnu")
        resultat = calcul(session, int(identifiant))
    resultat["consequences"] = [c for c in resultat["consequences"] if c]
    return resultat
