"""
Le rapprochement déclaré sur le type de document (§22.8).

L'exemple vient de l'utilisateur, et il vaut pour une maison comme pour un
bureau : un dossier porte un numéro, et ce numéro est repris sur le devis, le bon
de commande, le bon de livraison. Ouvrir l'un doit montrer les autres.

Trois traits, et chacun répond à un défaut de ce qui existait avant :

* **c'est déclaré, jamais deviné.** Le rapprochement automatique par valeur
  partagée (§19.19) remplissait le panneau de liens que personne n'avait voulus ;
  il a été retiré de l'écran au §22.7. Ici, deux documents ne se retrouvent côte
  à côte que parce qu'un administrateur a dit que ce champ-là les relie ;
* **c'est posé sur le type**, et non sur la vue (§22.5) : un devis appartient au
  dossier nº1234 quel que soit l'écran par lequel on l'ouvre. Les vues montrent
  donc ces liens sans avoir à les redéclarer ;
* **c'est symétrique.** Déclarer « le numéro de dossier relie ce type au reste »
  suffit : ouvrir le dossier montre ses pièces, ouvrir une pièce montre son
  dossier. Sans cela il faudrait six déclarations pour trois types, et l'on en
  oublierait toujours une.
"""
import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import filtres as moteur_filtres
from .db import Categorie, Document, LienType

log = logging.getLogger(__name__)

# Ce qu'on montre d'un rapprochement : au-delà, on ne lit plus une fiche, on
# parcourt une liste — et c'est le registre qui est fait pour ça.
MAX_VOISINS = 12


class LienRefuse(Exception):
    """Ce que la déclaration interdit. Le message est destiné à l'écran."""


def declares(session: Session, categorie_id: Optional[int]) -> list[LienType]:
    """
    Les déclarations qui concernent ce type, **des deux côtés** : celles qu'il
    porte, et celles qui le désignent comme cible.
    """
    if not categorie_id:
        return []
    return (session.query(LienType)
            .filter(or_(LienType.categorie_id == categorie_id,
                        LienType.categorie_cible_id == categorie_id))
            .order_by(LienType.id)
            .all())


def _sens(lien: LienType, categorie_id: int) -> tuple[str, str, Optional[int]]:
    """
    `(champ lu ici, champ cherché ailleurs, type d'en face)` selon le côté d'où
    l'on regarde. C'est tout ce que la symétrie demande.
    """
    if lien.categorie_id == categorie_id:
        return lien.champ_source, lien.champ_cible, lien.categorie_cible_id
    return lien.champ_cible, lien.champ_source, lien.categorie_id


def _valeur(document: Document, champ: str) -> Optional[str]:
    if champ.startswith(moteur_filtres.PREFIXE_META):
        cle = champ[len(moteur_filtres.PREFIXE_META):]
        for meta in document.metadonnees:
            if meta.cle == cle and (meta.valeur or "").strip():
                return meta.valeur
        return None
    valeur = getattr(document, champ, None)
    return str(valeur) if valeur not in (None, "") else None


def rapprochements(session: Session, document: Document, base_query) -> list[dict]:
    """
    Ce que les déclarations rapprochent de ce document.

    `base_query` vient de l'appelant **déjà filtrée par les droits** : un
    rapprochement ne doit pas montrer l'existence d'un document que celui qui
    regarde n'a pas le droit de voir.
    """
    groupes = []
    for lien in declares(session, document.categorie_id):
        champ_ici, champ_ailleurs, type_face = _sens(lien, document.categorie_id)
        valeur = _valeur(document, champ_ici)
        if not valeur:
            continue     # ce document-ci ne porte pas la valeur : rien à rapprocher

        query = base_query.filter(Document.id != document.id)
        if type_face:
            query = query.filter(Document.categorie_id == type_face)
        try:
            critere = moteur_filtres.Filtre(champ=champ_ailleurs, operateur="egal",
                                            valeur=valeur)
            query = moteur_filtres.appliquer(query, session, [critere])
        except moteur_filtres.FiltreInvalide:
            log.warning("Lien de type %s illisible : %s", lien.id, champ_ailleurs)
            continue

        voisins = query.order_by(Document.date_document.desc(), Document.id.desc()) \
                       .limit(MAX_VOISINS).all()
        if not voisins:
            continue
        groupes.append({
            "lien_id": lien.id,
            "libelle": lien.libelle or f"Même {_intitule(champ_ici)}",
            "champ": champ_ailleurs,
            "valeur": valeur,
            "documents": voisins,
        })
    return groupes


def _intitule(champ: str) -> str:
    """« meta:numero_dossier » se lit mal ; « numéro dossier » se lit."""
    if champ.startswith(moteur_filtres.PREFIXE_META):
        champ = champ[len(moteur_filtres.PREFIXE_META):]
    return champ.replace("_", " ")


def declarer(session: Session, categorie_id: int, champ_source: str, champ_cible: str,
             categorie_cible_id: Optional[int] = None,
             libelle: Optional[str] = None) -> LienType:
    """
    Enregistre une déclaration, après avoir vérifié qu'elle est applicable.

    Un champ mal écrit ne se manifesterait jamais : le rapprochement ne
    ramènerait rien, et l'on chercherait longtemps pourquoi deux documents qui
    portent le même numéro ne se voient pas.
    """
    if session.get(Categorie, categorie_id) is None:
        raise LienRefuse(f"Catégorie nº{categorie_id} introuvable.")
    if categorie_cible_id and session.get(Categorie, categorie_cible_id) is None:
        raise LienRefuse(f"Catégorie nº{categorie_cible_id} introuvable.")

    for champ in (champ_source, champ_cible):
        if not champ:
            raise LienRefuse("Il faut dire quel champ se compare à quel autre.")
        try:
            moteur_filtres.valider_champ(session, champ)
        except moteur_filtres.FiltreInvalide as erreur:
            raise LienRefuse(str(erreur))

    existante = (session.query(LienType)
                 .filter(LienType.categorie_id == categorie_id,
                         LienType.categorie_cible_id == categorie_cible_id,
                         LienType.champ_source == champ_source,
                         LienType.champ_cible == champ_cible)
                 .first())
    if existante:
        if libelle:
            existante.libelle = libelle
        return existante

    lien = LienType(categorie_id=categorie_id, categorie_cible_id=categorie_cible_id,
                    champ_source=champ_source, champ_cible=champ_cible,
                    libelle=(libelle or "").strip() or None)
    session.add(lien)
    session.flush()
    return lien
