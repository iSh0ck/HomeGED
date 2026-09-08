"""
Le lien déclaré sur la vue (§22.5).

C'est la « correspondance de champs » d'EzGED, et le dernier morceau de son
modèle qui nous manquait : depuis une vue, ouvrir **une autre vue filtrée sur la
ligne qu'on regarde**. « Depuis les membres du foyer, voir ses factures » ;
« depuis les véhicules, voir leurs entretiens ».

Trois mécanismes se ressemblent et ne font pas la même chose ; les confondre
serait la meilleure façon de n'en comprendre aucun :

* le **rapprochement par valeur partagée** (§19.19) réunit deux documents qui
  désignent la même chose. Personne ne le déclare, il se voit ;
* le **rattachement à la main** (§22.4) relie deux documents précis qui ne
  partagent rien. Quelqu'un l'a dit, une fois, pour ces deux-là ;
* le **lien de vue**, ici, est un **chemin de navigation** : il ne relie aucun
  document en particulier, il dit comment passer d'une liste à une autre. Déclaré
  une fois par l'administration, il vaut ensuite pour toutes les lignes.

Une déclaration tient en trois choses : la vue d'arrivée, le champ que l'on lit
sur la ligne de départ, et le champ sur lequel on filtre à l'arrivée.
"""
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from . import filtres as moteur_filtres
from .db import VueEnregistree

log = logging.getLogger(__name__)


class LienRefuse(Exception):
    """Ce que la déclaration interdit. Le message est destiné à l'écran."""


def declares(vue: VueEnregistree) -> list[dict]:
    """Les liens portés par une vue, ou une liste vide si elle n'en a pas."""
    try:
        valeurs = json.loads(vue.liens) if vue.liens else []
    except (ValueError, TypeError):
        log.warning("Liens illisibles sur la vue %s", vue.id)
        return []
    return [v for v in valeurs if isinstance(v, dict)]


def valider(session: Session, declarations: Optional[list], vue_id: Optional[int] = None) -> str:
    """
    Vérifie une déclaration et rend le JSON à stocker.

    Chaque refus dit ce qui ne va pas : une correspondance fausse ne produit
    aucune erreur visible à l'usage — elle ouvre simplement une liste vide, et
    l'on cherche pendant une heure d'où vient le vide.
    """
    if not declarations:
        return json.dumps([])

    propres = []
    for declaration in declarations:
        if not isinstance(declaration, dict):
            raise LienRefuse("Un lien se décrit par un objet.")
        cible = declaration.get("vue_id")
        vue = session.get(VueEnregistree, cible) if cible else None
        if vue is None:
            raise LienRefuse(f"La vue nº{cible} n'existe pas.")
        if vue_id is not None and vue.id == vue_id:
            raise LienRefuse("Une vue ne se lie pas à elle-même : le lien ne mènerait "
                             "nulle part.")

        champ_source = (declaration.get("champ_source") or "").strip()
        champ_cible = (declaration.get("champ_cible") or "").strip()
        for champ in (champ_source, champ_cible):
            if not champ:
                raise LienRefuse("Il faut dire quel champ lire au départ et quel champ "
                                 "filtrer à l'arrivée.")
            try:
                moteur_filtres.valider_champ(session, champ)
            except moteur_filtres.FiltreInvalide as erreur:
                raise LienRefuse(str(erreur))

        propres.append({
            "vue_id": vue.id,
            "champ_source": champ_source,
            "champ_cible": champ_cible,
            "libelle": (declaration.get("libelle") or "").strip() or f"Ouvrir « {vue.nom} »",
        })
    return json.dumps(propres, ensure_ascii=False)


def critere(lien: dict, valeur) -> dict:
    """
    Le critère à poser dans la vue d'arrivée pour la valeur lue au départ.

    C'est tout ce que le lien produit : un filtre ordinaire, que le registre sait
    déjà appliquer. Rien de nouveau côté droits, pagination ou recherche — et
    c'est précisément pourquoi ce mécanisme tient en si peu de lignes.
    """
    return {"champ": lien["champ_cible"], "operateur": "egal", "valeur": valeur}
