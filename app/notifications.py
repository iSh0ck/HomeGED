"""
Les notifications du foyer (§21.9).

Un rappel d'échéance, une automatisation qui a quelque chose à dire : les deux
aboutissent ici. Une table, et non un compteur — un rappel doit pouvoir être lu,
relu, retrouvé, et le §21.10 les enverra par courriel depuis ce même endroit.

Deux choix qui viennent de l'usage d'une maison :

  * **une notification s'adresse au foyer**, pas à une personne. « Le contrôle
    technique arrive à terme » ne concerne pas un compte en particulier, et
    l'adresser à quelqu'un reviendrait à décider qui s'en occupe. Un destinataire
    reste possible, il n'est pas le cas ordinaire ;
  * **l'empreinte évite le harcèlement**. Sans elle, le même rappel reviendrait
    chaque nuit et l'on cesserait de les lire — ce qui est le seul vrai risque
    d'un système de rappels.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .db import Notification

log = logging.getLogger("homeged.notifications")


def creer(session: Session, titre: str, message: Optional[str] = None,
          document_id: Optional[int] = None, utilisateur_id: Optional[int] = None,
          source: str = "rappel", empreinte: Optional[str] = None) -> Optional[Notification]:
    """
    Pose une notification, sauf si son empreinte est déjà connue.

    Rend `None` quand rien n'a été créé : c'est ce qui permet à l'appelant de
    savoir qu'il n'a pas prévenu deux fois, et de ne pas le journaliser comme une
    action.
    """
    if empreinte:
        deja = session.query(Notification).filter_by(empreinte=empreinte).first()
        if deja is not None:
            return None

    notification = Notification(
        titre=titre.strip()[:200], message=(message or "").strip() or None,
        document_id=document_id, utilisateur_id=utilisateur_id,
        source=source, empreinte=empreinte)
    session.add(notification)
    return notification


def _visibles(session: Session, user):
    """Les siennes, plus celles du foyer."""
    return session.query(Notification).filter(
        or_(Notification.utilisateur_id.is_(None),
            Notification.utilisateur_id == user.id))


def lister(session: Session, user, limite: int = 100, non_lues: bool = False) -> list[dict]:
    query = _visibles(session, user)
    if non_lues:
        query = query.filter(Notification.date_lecture.is_(None))
    lignes = query.order_by(Notification.date_lecture.isnot(None),
                            Notification.date_creation.desc()).limit(limite).all()
    return [serialiser(n) for n in lignes]


def serialiser(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "titre": notification.titre,
        "message": notification.message,
        "document_id": notification.document_id,
        "source": notification.source,
        "pour_le_foyer": notification.utilisateur_id is None,
        "lue": notification.date_lecture is not None,
        "date": notification.date_creation.isoformat(timespec="seconds")
        if notification.date_creation else None,
    }


def compter_non_lues(session: Session, user) -> int:
    return _visibles(session, user).filter(Notification.date_lecture.is_(None)).count()


def marquer_lue(session: Session, user, notification_id: int) -> bool:
    """
    Marque une notification comme lue.

    Une notification du foyer lue par quelqu'un l'est pour tout le monde : c'est
    un tableau d'affichage, pas une boîte aux lettres. Deux personnes qui
    décochent la même échéance ne se contredisent pas.
    """
    notification = _visibles(session, user).filter(Notification.id == notification_id).first()
    if notification is None:
        return False
    if notification.date_lecture is None:
        notification.date_lecture = datetime.now()
    _reinitialiser_palier(session, user)
    return True


def tout_marquer_lu(session: Session, user) -> int:
    lignes = _visibles(session, user).filter(Notification.date_lecture.is_(None)).all()
    for notification in lignes:
        notification.date_lecture = datetime.now()
    _reinitialiser_palier(session, user)
    return len(lignes)


def _reinitialiser_palier(session: Session, user) -> None:
    """
    Quelqu'un a lu : on repart du premier palier.

    Sans cela, une personne qui traite ses rappels resterait punie du silence
    qu'elle a observé la semaine d'avant — le prochain rappel n'arriverait
    qu'après une semaine.
    """
    if getattr(user, "palier_courriel", 0):
        user.palier_courriel = 0


def resume_a_envoyer(session: Session, user) -> list:
    """
    Ce qui n'est pas lu, pas encore envoyé, et adressé à cette personne ou au
    foyer. L'ordre est celui de l'arrivée : un résumé se lit comme un journal.
    """
    return (_visibles(session, user)
            .filter(Notification.date_lecture.is_(None),
                    Notification.date_envoi.is_(None))
            .order_by(Notification.date_creation).all())


def marquer_envoyees(session: Session, lignes: list) -> None:
    maintenant = datetime.now()
    for notification in lignes:
        notification.date_envoi = maintenant


def purger_anciennes(session: Session, jours: int) -> int:
    """
    Les notifications lues depuis longtemps n'apprennent plus rien. Les non lues
    ne sont **jamais** purgées : ce serait faire disparaître un rappel que
    personne n'a vu, c'est-à-dire exactement ce qu'on cherchait à éviter.
    """
    if jours <= 0:
        return 0
    limite = datetime.now() - timedelta(days=jours)
    return (session.query(Notification)
            .filter(Notification.date_lecture.isnot(None),
                    Notification.date_lecture < limite)
            .delete(synchronize_session=False))
