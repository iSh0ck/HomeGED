"""
Le repli du registre en arborescence (§21.6).

Le registre est un tableau plat : on choisit un type, et l'on obtient trois cents
lignes qu'il faut filtrer colonne par colonne. Replier sur un critère — l'année,
l'émetteur, le véhicule concerné — rend la liste parcourable sans écrire un seul
filtre : on descend « 2026 », puis « EDF », et l'on est arrivé.

C'est un classement **calculé à partir des données**, distinct de l'arborescence
des dossiers que l'administration règle. La même vue se groupe par titulaire
aujourd'hui et par véhicule demain, sans que rien ne change au classement.

Deux principes :

  * **une branche n'est qu'un filtre**. Descendre dans « 2026 » revient à poser
    le critère correspondant sur la liste. Rien de neuf côté requêtes, et les
    droits, la recherche et la pagination continuent de fonctionner tels quels.
  * **les dates se replient par année**. Grouper sur une date au jour près
    donnerait autant de branches que de documents, ce qui n'est plus un
    classement mais la liste elle-même, en plus lent.
"""
from typing import Optional

from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session

from . import base_donnees, filtres as moteur_filtres
from .db import Categorie, Document, Metadonnee

# Au-delà, ce n'est plus une arborescence : un écran ne se parcourt pas avec
# trois cents branches, et l'on cherchera plutôt.
PLAFOND_BRANCHES = 200

CHAMPS_DATE = ("date_document", "date_import")


def champ_valide(session: Session, champ: str) -> str:
    """Un champ groupable est un champ filtrable : le vocabulaire est le même."""
    champ = (champ or "").strip()
    moteur_filtres.valider_champ(session, champ)   # lève FiltreInvalide
    if champ == "texte":
        raise moteur_filtres.FiltreInvalide(
            "Le texte du document ne se groupe pas : il n'a pas de valeur commune.")
    return champ


def branches(session: Session, base, champ: str) -> list[dict]:
    """
    Les branches du niveau, avec le nombre de documents de chacune.

    `base` est une requête d'identifiants **déjà restreinte aux droits** et au
    périmètre courant : le décompte ne montre donc que ce que l'appelant a le
    droit de voir — un chiffre est déjà un renseignement.
    """
    champ = champ.strip()
    ids = base.scalar_subquery()

    if champ in CHAMPS_DATE:
        colonne = moteur_filtres.CHAMPS_DATE[champ]
        lignes = (session.query(func.year(colonne), func.count(Document.id))
                  .filter(Document.id.in_(ids), colonne.isnot(None))
                  .group_by(func.year(colonne))
                  .order_by(func.year(colonne).desc())
                  .limit(PLAFOND_BRANCHES).all())
        return [{"valeur": str(int(annee)), "libelle": str(int(annee)), "nombre": nombre}
                for annee, nombre in lignes if annee]

    if champ == "categorie":
        modele, colonne = Categorie, Document.categorie_id
        lignes = (session.query(modele.id, modele.nom, func.count(Document.id))
                  .join(Document, colonne == modele.id)
                  .filter(Document.id.in_(ids))
                  .group_by(modele.id, modele.nom)
                  .order_by(modele.nom)
                  .limit(PLAFOND_BRANCHES).all())
        return [{"valeur": str(identifiant), "libelle": nom, "nombre": nombre}
                for identifiant, nom, nombre in lignes]

    if champ == "statut":
        lignes = (session.query(Document.statut, func.count(Document.id))
                  .filter(Document.id.in_(ids))
                  .group_by(Document.statut).all())
        return [{"valeur": statut, "libelle": statut, "nombre": nombre}
                for statut, nombre in lignes if statut]

    if champ.startswith(moteur_filtres.PREFIXE_LIEN):
        table = champ[len(moteur_filtres.PREFIXE_LIEN):]
        prefixe = f"{table}{base_donnees.SEPARATEUR_SOURCE}"
        lignes = (session.query(Metadonnee.valeur,
                                func.count(func.distinct(Metadonnee.document_id)))
                  .filter(Metadonnee.document_id.in_(ids),
                          Metadonnee.valeur.like(f"{prefixe}%"))
                  .group_by(Metadonnee.valeur)
                  .limit(PLAFOND_BRANCHES).all())
        libelles = base_donnees.libelles_par_id(
            session, table, {v[len(prefixe):] for v, _ in lignes})
        return sorted(
            ({"valeur": valeur, "libelle": libelles.get(valeur[len(prefixe):], valeur),
              "nombre": nombre} for valeur, nombre in lignes),
            key=lambda b: b["libelle"].lower())

    if champ.startswith(moteur_filtres.PREFIXE_META):
        cle = champ[len(moteur_filtres.PREFIXE_META):]
        lignes = (session.query(Metadonnee.valeur,
                                func.count(func.distinct(Metadonnee.document_id)))
                  .filter(Metadonnee.document_id.in_(ids), Metadonnee.cle == cle,
                          Metadonnee.valeur.isnot(None), Metadonnee.valeur != "")
                  .group_by(Metadonnee.valeur)
                  .order_by(func.count(func.distinct(Metadonnee.document_id)).desc())
                  .limit(PLAFOND_BRANCHES).all())
        # Une métadonnée peut porter une référence (« usr_membres:4 ») : on la
        # rend lisible, comme partout ailleurs.
        libelles = moteur_filtres._libelles_metadonnee(session, cle, [v for v, _ in lignes])
        return [{"valeur": valeur, "libelle": libelles.get(valeur, valeur), "nombre": nombre}
                for valeur, nombre in lignes]

    colonne = moteur_filtres.CHAMPS_TEXTE.get(champ)
    if colonne is None:
        raise moteur_filtres.FiltreInvalide(f"Le champ « {champ} » ne se groupe pas.")
    lignes = (session.query(cast(colonne, String), func.count(Document.id))
              .filter(Document.id.in_(ids), colonne.isnot(None))
              .group_by(colonne).order_by(colonne).limit(PLAFOND_BRANCHES).all())
    return [{"valeur": valeur, "libelle": valeur, "nombre": nombre}
            for valeur, nombre in lignes if valeur]


def critere(champ: str, valeur: str) -> dict:
    """
    Le filtre que pose le choix d'une branche.

    Une année n'est pas une date : elle se traduit en intervalle, sans quoi le
    critère ne trouverait que les documents datés du 1er janvier.
    """
    champ = (champ or "").strip()
    if champ in CHAMPS_DATE:
        return {"champ": champ, "operateur": "entre",
                "valeur": [f"{valeur}-01-01", f"{valeur}-12-31"]}
    return {"champ": champ, "operateur": "egal", "valeur": valeur}


def declares(vue) -> list[str]:
    """Les champs de repli déclarés par une vue, dans l'ordre."""
    return [c.strip() for c in ((vue.groupement if vue is not None else "") or "").split(",")
            if c.strip()]


def valider_declaration(session: Session, champs: Optional[list]) -> Optional[str]:
    """Vérifie et sérialise les champs de repli d'une vue."""
    propres = [champ_valide(session, c) for c in (champs or []) if (c or "").strip()]
    return ",".join(propres) or None
