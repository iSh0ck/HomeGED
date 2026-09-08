"""
La recherche globale (§21.2).

Jusqu'ici, chercher supposait de savoir **où** : on choisissait un type dans le
menu, puis on filtrait colonne par colonne. C'est le geste de quelqu'un qui sait
déjà ce qu'il range. Celui qui cherche, lui, n'a qu'un mot — « Clio », « Orange »,
« 2024 » — et ne sait pas dans quel classement il tombe.

Ce module répond à ce mot-là, en interrogeant tout ce qui peut le porter :
l'émetteur, le nom du fichier, les métadonnées extraites, le classement, le texte
océrisé, et **les choses désignées** — un document qui porte `usr_vehicules:3` ne
contient nulle part le mot « Clio », et doit pourtant sortir quand on le tape.

Trois principes de construction, parce qu'une recherche lente n'est pas utilisée :

  * **un nombre fixe de requêtes**, quel que soit le nombre de résultats. Chaque
    source répond par un lot d'identifiants ; le rapprochement se fait en mémoire.
  * **le texte océrisé passe par l'index FULLTEXT** (`MATCH ... AGAINST`) et jamais
    par un `LIKE` : un LONGTEXT parcouru document par document ne tient pas.
  * **tout est plafonné** — chaque source rend au plus `PLAFOND_SOURCE` documents,
    et la réponse `limite`. On préfère une réponse partielle et immédiate à une
    réponse exhaustive qu'on n'attend pas.

Le classement, enfin, n'est pas une note absolue mais un ordre : un mot trouvé
dans l'émetteur ou dans la chose concernée compte plus que le même mot croisé
dans le corps du texte, et une métadonnée que l'administrateur a jugée digne
d'être une colonne du tableau compte plus qu'une autre. Rien n'est à régler : ce
sont les décisions déjà prises ailleurs qui donnent le poids.
"""
import time
from typing import Optional

from sqlalchemy import String, cast, or_, text
from sqlalchemy.orm import Session

from . import base_donnees
from .db import (
    Categorie, ColonneCategorie, Document, Metadonnee, TableDonnees,
)

# Ce que rapporte une correspondance, par source. Les valeurs ne veulent rien
# dire seules : seul leur ordre relatif compte.
POIDS = {
    "chose": 6,       # une ligne d'une table du foyer : « Renault Clio »
    "metadonnee": 4,
    "nom_fichier": 3,
    "categorie": 3,
    "texte": 2,
}
# Une métadonnée qui est aussi une colonne du tableau de son type : c'est
# l'administrateur qui a dit qu'elle comptait, on le suit.
BONUS_COLONNE = 2

LIBELLES_SOURCE = {
    "chose": "Concerne",
    "metadonnee": "Champ",
    "nom_fichier": "Nom du fichier",
    "categorie": "Classement",
    "texte": "Texte du document",
}

# Au-delà, on ne cherche plus : on répond. Chaque source est bornée séparément
# pour qu'une seule d'entre elles ne mange pas toute la réponse.
PLAFOND_SOURCE = 300
# Nombre de tables du foyer fouillées pour retrouver « Clio ». Un foyer en a une
# poignée ; la borne existe pour que l'ajout d'une trentième ne ralentisse pas
# toutes les recherches sans qu'on s'en aperçoive.
PLAFOND_TABLES = 30

PERIMETRES = ("tout", "classement", "vue")


class Trouvaille:
    """Un document trouvé, et **pourquoi** il l'a été."""

    __slots__ = ("document_id", "score", "raisons")

    def __init__(self, document_id: int):
        self.document_id = document_id
        self.score = 0
        self.raisons: list[dict] = []

    def ajouter(self, source: str, extrait: Optional[str], poids: int) -> None:
        self.score += poids
        # Une seule raison par source : dix métadonnées qui contiennent le mot
        # ne font pas dix explications, elles font une explication et un score.
        if not any(r["source"] == source for r in self.raisons):
            self.raisons.append({"source": source,
                                 "libelle": LIBELLES_SOURCE.get(source, source),
                                 "extrait": extrait})


def _motif(terme: str) -> str:
    """Échappe ce que MariaDB lirait comme un joker dans un LIKE."""
    propre = terme.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{propre}%"


# Comment lire une table du foyer : sa colonne d'affichage, ses colonnes
# identifiantes. Ces réglages ne bougent que quand un administrateur les change,
# et les relire à chaque frappe coûtait l'essentiel du temps de la recherche —
# information_schema n'est pas gratuit. On les garde donc une minute : un
# réglage modifié se voit au pire au bout de ce délai, ce qui est sans
# conséquence pour un classement de résultats.
_DUREE_PLAN = 60
_plans_caches: dict = {"date": 0.0, "valeur": {}}


def _plans(session: Session) -> dict:
    if time.time() - _plans_caches["date"] < _DUREE_PLAN:
        return _plans_caches["valeur"]
    plans = {}
    for table in session.query(TableDonnees).order_by(TableDonnees.nom_table).limit(
            PLAFOND_TABLES):
        nom = table.nom_table
        try:
            if not base_donnees.table_connue(nom):
                continue
            libelle = base_donnees.colonne_libelle(session, nom)
            identifiantes = base_donnees.colonnes_identifiantes(session, nom)
            plans[nom] = {"libelle": libelle,
                          "cibles": identifiantes if len(identifiantes) > 1 else [libelle]}
        except Exception:
            continue   # une table illisible ne doit pas emporter la recherche
    _plans_caches.update(date=time.time(), valeur=plans)
    return plans


def _references_des_choses(session: Session, terme: str) -> dict:
    """
    Les lignes des tables du foyer dont le libellé contient le terme, rendues
    sous la forme `{« usr_vehicules:3 »: « Renault Clio »}`.

    C'est ce qui permet de trouver les documents d'un véhicule en tapant son
    nom : eux ne portent qu'une référence, jamais le mot lui-même.
    """
    trouvees = {}
    motif = _motif(terme)
    for nom, plan in _plans(session).items():
        # Une requête par table, sur ses seules colonnes identifiantes : c'est
        # ainsi qu'on reconnaît une ligne partout ailleurs (« Camille DURAND »),
        # et le résultat doit se relire à l'identique.
        colonnes_lues = sorted({plan["libelle"], *plan["cibles"]})
        selection = ", ".join(["`id`"] + [f"`{c}`" for c in colonnes_lues])
        ou = " OR ".join(f"CAST(`{c}` AS CHAR) LIKE :motif" for c in plan["cibles"])
        try:
            lignes = session.execute(
                text(f"SELECT {selection} FROM `{nom}` WHERE {ou} LIMIT 50"),
                {"motif": motif}).mappings().all()
        except Exception:
            continue   # une table illisible ne doit pas emporter la recherche
        for ligne in lignes:
            reference = f"{nom}{base_donnees.SEPARATEUR_SOURCE}{ligne['id']}"
            trouvees[reference] = base_donnees._libelle_ligne(
                ligne, plan["cibles"] if len(plan["cibles"]) > 1 else [], plan["libelle"])
    return trouvees


def chercher(session: Session, base, terme: str, limite: int = 50) -> list[dict]:
    """
    Cherche `terme` parmi les documents de `base` (une requête d'identifiants
    **déjà restreinte aux droits** et au périmètre demandé).

    Rend les documents classés, chacun accompagné de ce qui l'a fait sortir.
    """
    terme = (terme or "").strip()
    if len(terme) < 2:
        return []

    motif = _motif(terme)
    ids = base.scalar_subquery()
    trouvailles: dict[int, Trouvaille] = {}

    def retenir(document_id, source, extrait, poids):
        trouvaille = trouvailles.setdefault(document_id, Trouvaille(document_id))
        trouvaille.ajouter(source, extrait, poids)

    # 1. le classement : une jointure courte sur une table minuscule. L'émetteur
    #    n'a plus de branche à lui (§21.12) : c'est une **chose désignée** comme
    #    une autre, et la source « chose » plus bas s'en charge — mieux, puisqu'elle
    #    trouve aussi ce qui le désigne sans le nommer.
    lignes = (session.query(Document.id, Categorie.nom)
              .join(Categorie, Document.categorie_id == Categorie.id)
              .filter(Document.id.in_(ids), Categorie.nom.like(motif))
              .limit(PLAFOND_SOURCE).all())
    for document_id, nom in lignes:
        retenir(document_id, "categorie", nom, POIDS["categorie"])

    # 2. le nom du fichier
    for (document_id, nom) in (session.query(Document.id, Document.nom_fichier)
                               .filter(Document.id.in_(ids), Document.nom_fichier.like(motif))
                               .limit(PLAFOND_SOURCE).all()):
        retenir(document_id, "nom_fichier", nom, POIDS["nom_fichier"])

    # 3. les métadonnées, et les choses qu'elles désignent
    choses = _references_des_choses(session, terme)
    conditions = [cast(Metadonnee.valeur, String).like(motif)]
    if choses:
        conditions.append(Metadonnee.valeur.in_(list(choses)))
    lignes = (session.query(Metadonnee.document_id, Metadonnee.cle, Metadonnee.valeur)
              .filter(Metadonnee.document_id.in_(ids), or_(*conditions))
              .limit(PLAFOND_SOURCE * 2).all())
    # Les colonnes déclarées par les types : une métadonnée que l'administrateur
    # a mise dans un tableau compte davantage que celle qu'il n'a pas retenue.
    colonnes = {c.champ[len("meta:"):] for c in session.query(ColonneCategorie)
                .filter(ColonneCategorie.visible.is_(True),
                        ColonneCategorie.champ.like("meta:%"))}
    for document_id, cle, valeur in lignes:
        if valeur in choses:
            retenir(document_id, "chose", choses[valeur], POIDS["chose"])
        else:
            retenir(document_id, "metadonnee", f"{cle} : {valeur}",
                    POIDS["metadonnee"] + (BONUS_COLONNE if cle in colonnes else 0))

    # 4. le texte océrisé, par l'index FULLTEXT — jamais par un LIKE : un
    #    LONGTEXT parcouru ligne à ligne ne tient pas à l'échelle d'une archive.
    for (document_id,) in (session.query(Document.id)
                           .filter(Document.id.in_(ids), Document.texte_ocr.match(terme))
                           .limit(PLAFOND_SOURCE).all()):
        retenir(document_id, "texte", None, POIDS["texte"])

    # À score égal, le plus récent d'abord : sans second critère, l'ordre venait
    # du hasard des dictionnaires et deux recherches identiques ne rendaient pas
    # la même liste.
    classees = sorted(trouvailles.values(), key=lambda t: (-t.score, -t.document_id))
    return [{"document_id": t.document_id, "score": t.score, "raisons": t.raisons}
            for t in classees[:limite]]


def perimetre_valide(nom: Optional[str]) -> str:
    return nom if nom in PERIMETRES else "tout"
