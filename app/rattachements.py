"""
Rattacher deux documents à la main (§22.4).

Le rapprochement par valeur partagée (§19.19, §22) réunit ce qui **désigne la
même chose** : deux papiers qui nomment le même véhicule se retrouvent sans
qu'on ait rien à faire. C'est le cas le plus fréquent, et il ne demande aucun
geste — c'est pourquoi il est resté le mécanisme principal.

Reste ce qui ne partage rien et se répond quand même : un contrat et son
avenant, une facture et son litige, une ordonnance et son remboursement. Aucune
valeur commune ne les relie ; seul quelqu'un qui les a lus le sait. D'où ce lien
posé à la main, et **symétrique** — un avenant sans son contrat n'a pas plus de
sens que l'inverse.

Deux règles tiennent le module :

* **le couple est rangé à l'écriture** (`document_a` porte le plus petit
  identifiant). L'unicité est ainsi vraie dans les deux sens sans qu'aucune
  lecture ait à y penser ;
* **tant que l'administration n'a rien déclaré, tout est permis.** Un réglage
  vide ne doit pas interdire une fonction : personne ne comprendrait pourquoi le
  bouton refuse. Dès qu'une paire de types est déclarée, elles seules le sont.
"""
import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .db import Categorie, Document, Rattachement, RattachementType

log = logging.getLogger(__name__)


class RattachementRefuse(Exception):
    """Ce que le modèle interdit. Le message est destiné à l'écran."""


def _couple(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def paires_declarees(session: Session) -> list[RattachementType]:
    return session.query(RattachementType).all()


def autorise(session: Session, un: Document, autre: Document) -> bool:
    """
    Ces deux types-là peuvent-ils se rattacher ?

    Aucune déclaration : oui — voir l'en-tête du module. Sinon, il faut que la
    paire figure, dans un sens ou dans l'autre : la déclaration est un fait sur
    deux types, pas une direction.
    """
    declarees = paires_declarees(session)
    if not declarees:
        return True
    couple = _couple(un.categorie_id or 0, autre.categorie_id or 0)
    return any(_couple(p.categorie_a, p.categorie_b) == couple for p in declarees)


def rattacher(session: Session, un: Document, autre: Document,
              libelle: Optional[str] = None,
              utilisateur_id: Optional[int] = None) -> Rattachement:
    """Pose le lien, ou rend celui qui existe déjà — le geste est idempotent."""
    if un.id == autre.id:
        raise RattachementRefuse("Un document ne se rattache pas à lui-même.")
    if not autorise(session, un, autre):
        noms = [c.nom if c else "sans classement"
                for c in (un.categorie, autre.categorie)]
        raise RattachementRefuse(
            f"L'administration n'autorise pas à rattacher un document de « {noms[0]} » "
            f"à un document de « {noms[1]} ».")

    a, b = _couple(un.id, autre.id)
    existant = (session.query(Rattachement)
                .filter(Rattachement.document_a == a, Rattachement.document_b == b)
                .first())
    if existant:
        if libelle and not existant.libelle:
            existant.libelle = libelle
        return existant

    lien = Rattachement(document_a=a, document_b=b,
                        libelle=(libelle or "").strip() or None,
                        utilisateur_id=utilisateur_id)
    session.add(lien)
    session.flush()
    return lien


def detacher(session: Session, un: Document, autre_id: int) -> bool:
    """Retire le lien s'il existe. Rend `True` si quelque chose a été retiré."""
    a, b = _couple(un.id, autre_id)
    nombre = (session.query(Rattachement)
              .filter(Rattachement.document_a == a, Rattachement.document_b == b)
              .delete(synchronize_session=False))
    return bool(nombre)


def voisins(session: Session, document_id: int) -> list[tuple[int, Rattachement]]:
    """
    `(identifiant du voisin, lien)` pour tout ce qui est rattaché à ce document,
    des deux côtés — c'est le propre d'un lien symétrique.
    """
    liens = (session.query(Rattachement)
             .filter(or_(Rattachement.document_a == document_id,
                         Rattachement.document_b == document_id))
             .order_by(Rattachement.id)
             .all())
    return [(lien.document_b if lien.document_a == document_id else lien.document_a, lien)
            for lien in liens]


def declarer(session: Session, categorie_a: int, categorie_b: int,
             libelle: Optional[str] = None) -> RattachementType:
    """Déclare qu'un type peut se rattacher à un autre."""
    for identifiant in (categorie_a, categorie_b):
        if session.get(Categorie, identifiant) is None:
            raise RattachementRefuse(f"Catégorie nº{identifiant} introuvable.")
    a, b = _couple(categorie_a, categorie_b)
    existante = (session.query(RattachementType)
                 .filter(RattachementType.categorie_a == a,
                         RattachementType.categorie_b == b).first())
    if existante:
        if libelle:
            existante.libelle = libelle
        return existante
    paire = RattachementType(categorie_a=a, categorie_b=b,
                             libelle=(libelle or "").strip() or None)
    session.add(paire)
    session.flush()
    return paire
