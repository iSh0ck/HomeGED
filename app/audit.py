"""
Journal d'audit des actions importantes (§14).

Volontairement générique : une action est identifiée par deux chaînes libres
(`action` et `objet_type`), de nouveaux types d'événements s'ajoutent donc sans
migration ni modification de ce module.

Les entrées sont ajoutées à la session en cours **sans commit** : la trace est
ainsi validée dans la même transaction que l'action auditée. Une opération
annulée ne laisse pas de trace mensongère, et une opération réussie ne peut pas
passer inaperçue.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .db import JournalAudit, Utilisateur

log = logging.getLogger(__name__)

# Actions connues à ce jour. La colonne reste une chaîne libre : cette liste
# sert de référence de nommage, pas de contrainte.
DOCUMENT_SUPPRESSION = "document.suppression"
DOCUMENT_MODIFICATION = "document.modification"


CONSULTATION = "document.consultation"

# Une consultation par personne, par document et par quart d'heure : ouvrir une
# fiche, la refermer, la rouvrir pour vérifier une ligne est un seul geste. Sans
# cette fenêtre, l'historique d'un document se remplirait de vingt lignes
# identiques pour une seule lecture, et l'information qu'il porte — qui a vu ce
# papier, et quand — s'y noierait.
FENETRE_CONSULTATION = timedelta(minutes=15)


def consultation(session: Session, utilisateur: Optional[Utilisateur],
                 document_id: int, details: Optional[dict] = None) -> bool:
    """
    Trace la **lecture** d'un document (§21.16), au plus une fois par fenêtre.

    Savoir qui a ouvert un papier est le propre d'une GED : nous ne consignions
    que le dépôt, la modification et la suppression — c'est-à-dire ce qui change
    le document, jamais ce qui le regarde. Or dans une maison, c'est souvent la
    lecture qui compte : qui a consulté l'acte notarié, et quand.

    Rend `True` si une trace a été écrite. Ne commite pas : l'appelant décide.
    """
    if utilisateur is None or not document_id:
        return False
    depuis = datetime.now() - FENETRE_CONSULTATION
    deja = (session.query(JournalAudit.id)
            .filter(JournalAudit.action == CONSULTATION,
                    JournalAudit.objet_type == "document",
                    JournalAudit.objet_id == document_id,
                    JournalAudit.utilisateur_id == utilisateur.id,
                    JournalAudit.date_evenement >= depuis)
            .first())
    if deja:
        return False
    journaliser(session, utilisateur, CONSULTATION, "document", document_id, details)
    return True


def journaliser(
    session: Session,
    utilisateur: Optional[Utilisateur],
    action: str,
    objet_type: str,
    objet_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> None:
    """
    Enregistre un événement d'audit dans la session courante (sans commit).

    `details` accueille tout ce qui aide à comprendre après coup : état avant /
    après pour une modification, instantané de l'objet pour une suppression.
    """
    try:
        session.add(JournalAudit(
            utilisateur_id=utilisateur.id if utilisateur else None,
            utilisateur_email=utilisateur.email if utilisateur else None,
            action=action,
            objet_type=objet_type,
            objet_id=objet_id,
            details=json.dumps(details, ensure_ascii=False, default=str) if details else None,
        ))
    except Exception:
        # Une trace d'audit ne doit jamais faire échouer l'action métier
        # elle-même ; en revanche l'incident doit être visible dans les logs.
        log.exception(f"Impossible de journaliser l'action {action} sur {objet_type}#{objet_id}")
