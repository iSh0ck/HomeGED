"""
Les automatisations « quand… alors… » (§21.8).

Le workflow d'EzGED enchaîne des étapes, des conditions évaluées dans l'ordre et
des tâches, dont une seule intervention humaine par étape. Pour une maison, la
même idée tient en une phrase : **quand** un document arrive et **que** telle
condition est vraie, **alors** faire ceci.

Trois exigences, toutes tenues du même geste :

  * **générique** — demande explicite de l'utilisateur : « ça doit être générique
    et pas spécifique à des factures ». Rien n'est codé pour un type de document
    en particulier ; tout se règle depuis l'administration ;
  * **un seul langage** — les conditions sont la liste `{champ, operateur,
    valeur}` des filtres, des vues et des tableaux de bord. Tout ce qui se filtre
    se teste, il n'y a pas de second vocabulaire à apprendre ;
  * **rien de silencieux** — chaque examen laisse une trace : ce qui s'est
    déclenché, sur quel document, et ce qui a été fait. Une automatisation qu'on
    ne peut pas expliquer devient une source de mystères, et l'on finit par tout
    désactiver « au cas où ».

Les catalogues (déclencheurs, actions) sont **déclarés ici** et lus par l'écran,
comme ceux des droits ou des fonctions d'extraction : une liste tenue à l'écran
finirait par proposer une action que le moteur ne sait pas exécuter.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from . import filtres as moteur_filtres
from .db import (Automatisation, Categorie, Document, ExecutionAutomatisation,
                 Metadonnee)

log = logging.getLogger("homeged.automatisations")

DEPOT = "document_depose"
MODIFICATION = "document_modifie"
DATE = "date_atteinte"

DECLENCHEURS = {
    DEPOT: {
        "libelle": "Quand un document est déposé",
        "description": "Après l'extraction, quand le document vient d'entrer au registre. "
                       "C'est le moment où l'on connaît enfin ses champs.",
    },
    MODIFICATION: {
        "libelle": "Quand un document est modifié",
        "description": "Après une correction faite à la main ou depuis le Centre d'analyse.",
    },
    DATE: {
        "libelle": "Quand une date est atteinte",
        "description": "Examiné une fois par jour sur tous les documents. Chaque document "
                       "n'est traité qu'une fois : la date, elle, revient tous les jours.",
    },
}

# Chaque action dit ce qu'elle attend : l'écran construit son formulaire à partir
# de là, et le moteur refuse ce qu'il ne saurait pas faire.
ACTIONS = {
    "affecter_champ": {
        "libelle": "Renseigner un champ",
        "description": "Écrit une valeur dans une métadonnée du document. Par défaut, ne "
                       "touche pas à ce qui est déjà rempli — une valeur saisie à la main "
                       "vaut mieux que la nôtre.",
        "parametres": [
            {"cle": "champ", "libelle": "Champ", "exemple": "meta:a_payer"},
            {"cle": "valeur", "libelle": "Valeur", "exemple": "oui"},
            {"cle": "ecraser", "libelle": "Écraser si déjà rempli", "type": "booleen"},
        ],
    },
    "reclasser": {
        "libelle": "Changer le classement",
        "description": "Déplace le document vers un autre type. À manier avec soin : le "
                       "classement commande les colonnes, les champs attendus et les droits.",
        "parametres": [
            {"cle": "categorie_id", "libelle": "Type de document", "type": "categorie"},
        ],
    },
    "rappeler": {
        "libelle": "Poser un rappel",
        "description": "Ajoute une notification pour le foyer, avec un lien vers le "
                       "document. Le même rappel n'est jamais posé deux fois pour un même "
                       "document : on cesserait de les lire.",
        "parametres": [
            {"cle": "titre", "libelle": "Titre", "exemple": "Facture à payer"},
            {"cle": "message", "libelle": "Message", "exemple": "Vérifier avant l'échéance"},
        ],
    },
    "journaliser": {
        "libelle": "Écrire une note dans le journal",
        "description": "N'agit pas sur le document : sert à repérer une situation sans rien "
                       "changer. C'est la façon d'essayer une règle avant de lui donner des "
                       "actions.",
        "parametres": [
            {"cle": "message", "libelle": "Message", "exemple": "Facture à vérifier"},
        ],
    },
}


class AutomatisationInvalide(ValueError):
    """Refus destiné à l'écran : il dit ce qui manque."""


def valider(session: Session, declencheur: str, conditions: list, actions: list) -> None:
    """Refuse à l'enregistrement ce qui ne pourrait jamais s'exécuter."""
    if declencheur not in DECLENCHEURS:
        raise AutomatisationInvalide(
            f"Déclencheur inconnu (attendu : {', '.join(DECLENCHEURS)}).")
    for condition in conditions or []:
        try:
            moteur_filtres.valider_champ(session, condition.get("champ", ""))
        except moteur_filtres.FiltreInvalide as erreur:
            raise AutomatisationInvalide(str(erreur))
    if not actions:
        raise AutomatisationInvalide(
            "Une automatisation sans action ne ferait rien : ajoutez-en une, ou "
            "servez-vous de « Écrire une note dans le journal » pour l'essayer.")
    for action in actions:
        type_action = action.get("type")
        if type_action not in ACTIONS:
            raise AutomatisationInvalide(
                f"Action inconnue : « {type_action} » (attendu : {', '.join(ACTIONS)}).")
        if type_action == "affecter_champ" and not (action.get("champ") or "").strip():
            raise AutomatisationInvalide("Dites quel champ renseigner.")
        if type_action == "reclasser" and not action.get("categorie_id"):
            raise AutomatisationInvalide("Dites vers quel type de document déplacer.")
        if type_action == "rappeler" and not (action.get("titre") or "").strip():
            raise AutomatisationInvalide("Un rappel sans titre ne dirait rien.")


def _lire(brut: Optional[str]) -> list:
    try:
        valeur = json.loads(brut or "[]")
        return valeur if isinstance(valeur, list) else []
    except (ValueError, TypeError):
        return []


def _conditions_reunies(session: Session, automatisation, document: Document) -> bool:
    """
    Les conditions sont testées **par le moteur de filtres**, sur ce document
    seul. Écrire ici une seconde évaluation aurait fait diverger ce que l'écran
    de filtrage montre et ce que l'automatisation croit.
    """
    conditions = _lire(automatisation.conditions)
    if not conditions:
        return True
    try:
        criteres = [moteur_filtres.Filtre(**c) for c in conditions]
        query = moteur_filtres.appliquer(
            session.query(Document.id).filter(Document.id == document.id), session, criteres)
        return query.first() is not None
    except (moteur_filtres.FiltreInvalide, TypeError) as erreur:
        log.warning("Automatisation « %s » : condition illisible (%s)",
                    automatisation.nom, erreur)
        return False


def _appliquer(session: Session, action: dict, document: Document) -> Optional[str]:
    """Exécute une action et rend ce qu'elle a fait, ou rien si elle n'a rien fait."""
    type_action = action.get("type")

    if type_action == "affecter_champ":
        champ = (action.get("champ") or "").strip()
        valeur = str(action.get("valeur") or "")
        cle = champ[len(moteur_filtres.PREFIXE_META):] \
            if champ.startswith(moteur_filtres.PREFIXE_META) else champ
        existante = next((m for m in document.metadonnees if m.cle == cle), None)
        if existante and (existante.valeur or "").strip() and not action.get("ecraser"):
            return None      # une valeur saisie à la main vaut mieux que la nôtre
        if existante:
            existante.valeur = valeur
        else:
            # Attachée au document, et pas seulement à son identifiant : sa
            # collection est déjà chargée, et un `flush` ne l'y ferait pas
            # entrer — ce qui suit dans la même session lirait un document
            # incomplet (voir `references_auto.remplir`).
            document.metadonnees.append(Metadonnee(cle=cle, valeur=valeur))
        return f"{cle} = {valeur}"

    if type_action == "reclasser":
        cible = session.get(Categorie, action.get("categorie_id"))
        if cible is None or document.categorie_id == cible.id:
            return None
        avant = document.categorie.nom if document.categorie else "sans classement"
        document.categorie_id = cible.id
        return f"reclassé de « {avant} » vers « {cible.nom} »"

    if type_action == "rappeler":
        from . import notifications

        titre = str(action.get("titre") or "").strip() or "Rappel"
        posee = notifications.creer(
            session, titre=titre, message=str(action.get("message") or "").strip() or None,
            document_id=document.id, source="automatisation",
            # Une automatisation qui repasse ne doit pas empiler dix fois le même
            # rappel sur le même document.
            empreinte=f"auto:{document.id}:{titre[:60]}")
        return f"rappel « {titre} »" if posee is not None else None

    if type_action == "journaliser":
        return str(action.get("message") or "").strip() or "note"

    return None


def _deja_agi(session: Session, automatisation, document: Document) -> bool:
    """
    A-t-on déjà agi sur ce document pour cette automatisation ?

    Ne concerne que le déclencheur de date : il repasse tous les jours, et sans
    cette mémoire il referait son action chaque nuit. Un dépôt ou une
    modification, eux, sont des événements — ils ne se répètent pas d'eux-mêmes.
    """
    return (session.query(ExecutionAutomatisation)
            .filter_by(automatisation_id=automatisation.id, document_id=document.id,
                       agi=True)
            .first() is not None)


def executer(session: Session, declencheur: str, document: Document) -> list[dict]:
    """
    Passe les automatisations de ce déclencheur sur ce document.

    Rend la liste de ce qui a été fait. Ne commet pas : l'appelant décide, ce qui
    permet d'agir dans la même transaction que le dépôt ou la modification —
    sinon un document pourrait être enregistré sans les valeurs que
    l'automatisation vient d'y poser.
    """
    if document is None or document.date_suppression is not None:
        return []

    regles = (session.query(Automatisation)
              .filter(Automatisation.declencheur == declencheur,
                      Automatisation.actif.is_(True))
              .order_by(Automatisation.ordre, Automatisation.id).all())

    bilan = []
    for automatisation in regles:
        if automatisation.categorie_id and automatisation.categorie_id != document.categorie_id:
            continue
        if declencheur == DATE and _deja_agi(session, automatisation, document):
            continue

        reunies = _conditions_reunies(session, automatisation, document)
        faits = []
        if reunies:
            for action in _lire(automatisation.actions):
                try:
                    fait = _appliquer(session, action, document)
                except Exception:
                    log.exception("Automatisation « %s » : action en échec", automatisation.nom)
                    fait = None
                if fait:
                    faits.append(fait)

        # On trace **aussi** les examens sans suite : « pourquoi cette règle n'a
        # rien fait » est la question qu'on se pose le plus souvent.
        session.add(ExecutionAutomatisation(
            automatisation_id=automatisation.id, document_id=document.id,
            declencheur=declencheur, agi=bool(reunies and faits),
            detail=json.dumps({"conditions_reunies": reunies, "faits": faits},
                              ensure_ascii=False)))
        if reunies and faits:
            bilan.append({"automatisation": automatisation.nom, "faits": faits})

    return bilan


def passer_en_revue(session: Session, limite: int = 500) -> dict:
    """
    Le déclencheur de date, examiné une fois par cycle sur les documents vivants.

    Une seule passe pour toutes les automatisations de ce type : parcourir
    l'archive une fois par règle coûterait autant de balayages que de règles.
    """
    regles = (session.query(Automatisation)
              .filter(Automatisation.declencheur == DATE, Automatisation.actif.is_(True))
              .count())
    if not regles:
        return {"examines": 0, "agis": 0}

    documents = (session.query(Document)
                 .filter(Document.date_suppression.is_(None))
                 .order_by(Document.id).limit(limite).all())
    agis = 0
    for document in documents:
        if executer(session, DATE, document):
            agis += 1
    return {"examines": len(documents), "agis": agis}


def journal(session: Session, limite: int = 100, automatisation_id: Optional[int] = None,
            document_id: Optional[int] = None) -> list[dict]:
    """Ce qui s'est déclenché, du plus récent au plus ancien."""
    query = session.query(ExecutionAutomatisation)
    if automatisation_id:
        query = query.filter(ExecutionAutomatisation.automatisation_id == automatisation_id)
    if document_id:
        query = query.filter(ExecutionAutomatisation.document_id == document_id)
    lignes = query.order_by(ExecutionAutomatisation.id.desc()).limit(limite).all()
    return [{
        "id": ligne.id,
        "automatisation_id": ligne.automatisation_id,
        "automatisation": ligne.automatisation.nom if ligne.automatisation else None,
        "document_id": ligne.document_id,
        "declencheur": ligne.declencheur,
        "libelle_declencheur": DECLENCHEURS.get(ligne.declencheur, {}).get(
            "libelle", ligne.declencheur),
        "agi": bool(ligne.agi),
        "date": ligne.date_execution.isoformat(timespec="seconds")
        if ligne.date_execution else None,
        "detail": json.loads(ligne.detail) if ligne.detail else {},
    } for ligne in lignes]


def decrire() -> dict:
    """Les catalogues, tels que l'écran d'administration les lit."""
    return {
        "declencheurs": [{"cle": cle, **details} for cle, details in DECLENCHEURS.items()],
        "actions": [{"cle": cle, **details} for cle, details in ACTIONS.items()],
    }
