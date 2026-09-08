"""
Dossiers et types de document (§19.1).

L'arborescence confondait deux choses qui n'ont pas le même usage. Un **dossier**
organise — « Maison », « Impôts » — et ne porte aucun document ; un **type de
document** est une feuille — « Factures » — et porte tout ce qui décrit un
document de cette sorte : ses colonnes, ses champs attendus, ses règles.

Régler les colonnes de « Maison » n'a jamais rien voulu dire. En nommant la
chose, chaque écran sait à quoi il s'adresse.

Ce module tient les règles de cohérence, en un seul endroit : elles sont
appelées depuis l'API d'administration comme depuis le registre, et une règle
écrite deux fois est une règle qui divergera. Chacune refuse en français, avec
la raison — un refus qu'on ne comprend pas se contourne mal.
"""
from typing import Optional

from sqlalchemy.orm import Session

from .db import Categorie, Document

DOSSIER = "dossier"
TYPE = "type"
# Fiche simple (§22.1). Elle porte des documents comme un type, à une différence
# près : **rien n'y entre tout seul**. Pas de dossier sous `ocr_wait`, donc pas de
# dépôt automatique — on y glisse un fichier à la main, et l'on remplit ses
# valeurs. C'est ce qui convient à ce qu'on reçoit rarement et qu'aucune règle ne
# saurait lire : un acte notarié, une carte grise, un contrat signé.
#
# Elle remplace la « fiche de liaison » du §19.17, qui s'adossait à une table du
# foyer et n'a jamais rien rassemblé : trois réglages avant le premier document,
# et un écran qui montrait des lignes vides.
FICHE = "fiche"
NATURES = (DOSSIER, TYPE, FICHE)

LIBELLES = {
    DOSSIER: "dossier",
    TYPE: "type de document",
    FICHE: "fiche simple",
}


class NatureRefusee(Exception):
    """Ce que la distinction dossier / type interdit. Le message est destiné à l'écran."""


def nature_de(categorie: Optional[Categorie]) -> str:
    return (categorie.nature or TYPE) if categorie is not None else TYPE


def est_dossier(categorie: Optional[Categorie]) -> bool:
    return categorie is not None and nature_de(categorie) == DOSSIER


def est_fiche(categorie: Optional[Categorie]) -> bool:
    return categorie is not None and nature_de(categorie) == FICHE


def porte_des_documents(categorie: Optional[Categorie]) -> bool:
    """
    Un type **et** une fiche simple portent des documents ; un dossier organise.

    La différence entre les deux n'est pas ce qu'elles contiennent, c'est **par où
    cela entre** : un type a son dossier de dépôt, une fiche n'en a pas (§22.1).
    """
    return categorie is not None and nature_de(categorie) in (TYPE, FICHE)


def recoit_des_depots(categorie: Optional[Categorie]) -> bool:
    """Seul un type de document a un dossier sous `ocr_wait` : on n'y dépose pas
    à la main, et rien n'entre tout seul dans une fiche simple (§22.1)."""
    return categorie is not None and nature_de(categorie) == TYPE


def valider_nature(nature: Optional[str]) -> str:
    valeur = (nature or TYPE).strip().lower()
    if valeur not in NATURES:
        raise NatureRefusee(
            f"Nature inconnue : « {nature} ». Une catégorie est un dossier, un type de "
            f"document ou une fiche simple.")
    return valeur


def exiger_type(session: Session, categorie_id: Optional[int], quoi: str) -> None:
    """
    Refuse d'attacher à un dossier ce qui n'a de sens que sur un type.

    `quoi` complète la phrase : « Un dossier ne porte pas <quoi> ». C'est le
    même refus pour les colonnes, les champs attendus et le classement d'un
    document — trois écrans, une seule règle.
    """
    if categorie_id is None:
        return
    categorie = session.get(Categorie, categorie_id)
    if porte_des_documents(categorie) or categorie is None:
        return
    raise NatureRefusee(
        f"« {categorie.nom} » est {LIBELLES[nature_de(categorie)]} : il organise le "
        f"classement mais ne porte pas {quoi}. Choisissez un type de document ou une "
        f"fiche simple.")


def verifier_changement(session: Session, categorie: Categorie, nature: str) -> None:
    """
    Un changement de nature ne doit pas laisser l'arborescence dans un état que
    rien d'autre ne sait lire.

    Les deux refus disent quoi faire d'abord, plutôt que de constater l'échec :
    c'est ce qui distingue un garde-fou d'un mur.
    """
    if nature == (categorie.nature or TYPE):
        return

    if nature != DOSSIER:
        enfants = session.query(Categorie).filter_by(parent_id=categorie.id).count()
        if enfants:
            raise NatureRefusee(
                f"« {categorie.nom} » contient {enfants} sous-catégorie(s) : "
                f"{LIBELLES[nature]} est une feuille. Déplacez-les ailleurs, ou "
                f"laissez-le dossier.")
    # Un type et une fiche portent tous deux des documents : passer de l'un à
    # l'autre ne dérange rien, seule la porte d'entrée change (§22.1). Devenir un
    # dossier, en revanche, laisserait des documents là où plus rien ne les lit.
    if nature == DOSSIER:
        documents = session.query(Document).filter_by(categorie_id=categorie.id).count()
        if documents:
            raise NatureRefusee(
                f"« {categorie.nom} » porte {documents} document(s) : {LIBELLES[nature]} "
                f"n'en contient aucun en propre. Reclassez-les dans un type de document "
                f"d'abord.")


def verifier_parent(session: Session, parent_id: Optional[int]) -> None:
    """
    Un type de document est une feuille : il n'accueille pas de sous-catégorie.
    Sans cette règle, on retrouverait des documents à mi-chemin de l'arbre, dans
    une catégorie qui en contient d'autres — exactement ce que la distinction
    cherche à supprimer.
    """
    if parent_id is None:
        return
    parent = session.get(Categorie, parent_id)
    if parent is not None and not est_dossier(parent):
        raise NatureRefusee(
            f"« {parent.nom} » est {LIBELLES[nature_de(parent)]} : il ne peut pas "
            f"contenir de sous-catégorie. Choisissez un dossier.")
