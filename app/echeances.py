"""
Les échéances (§21.9).

C'est le besoin le plus concret d'une maison : contrôle technique, assurance,
garantie, échéance de facture. Le document porte la date — encore faut-il que
quelqu'un la regarde avant qu'elle ne passe.

Rien de spécifique aux factures : un **champ** d'un type est déclaré
« échéance », et c'est tout. Le foyer décide duquel il s'agit — `date_echeance`
pour une facture, `fin_de_validite` pour une carte d'identité — et de combien de
jours à l'avance il veut être prévenu. C'est le même principe qu'au §18.47 pour
la déduction : rien n'arrive tant qu'un administrateur ne l'a pas déclaré, parce
qu'un rappel que personne n'a demandé se lit comme un bruit.

Le rappel se pose **une fois par échéance** (l'empreinte d'une notification, cf.
`app/notifications.py`) : sans quoi la même date reviendrait chaque nuit, et l'on
cesserait de lire les rappels — le seul vrai risque d'un système de rappels.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from . import notifications
from .db import Document, Metadonnee, RegleChampCategorie
from .filtres import PREFIXE_META

log = logging.getLogger("homeged.echeances")

# À défaut de réglage sur le champ. Trente jours : le temps de s'occuper d'une
# assurance ou d'un contrôle technique sans que le rappel ne devienne du bruit.
RAPPEL_PAR_DEFAUT = 30


def champs_echeance(session: Session) -> dict:
    """`{categorie_id: [(cle, libelle, rappel_jours)]}` — ce que chaque type déclare."""
    par_categorie: dict = {}
    for regle in (session.query(RegleChampCategorie)
                  .filter(RegleChampCategorie.echeance.is_(True))):
        if not regle.champ.startswith(PREFIXE_META):
            continue
        par_categorie.setdefault(regle.categorie_id, []).append((
            regle.champ[len(PREFIXE_META):],
            regle.libelle or regle.champ[len(PREFIXE_META):],
            regle.rappel_jours or RAPPEL_PAR_DEFAUT,
        ))
    return par_categorie


def _date(valeur: Optional[str]) -> Optional[date]:
    """Une valeur de métadonnée lue comme date, ou rien."""
    texte = (valeur or "").strip()
    if not texte:
        return None
    for format_ in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texte, format_).date()
        except ValueError:
            continue
    return None


def prochaines(session: Session, base, horizon: int = 90) -> list[dict]:
    """
    Les échéances à venir (et celles déjà passées) des documents de `base`.

    `base` est une requête d'identifiants déjà restreinte aux droits : une
    échéance est une information sur un document, elle se cache comme lui.
    """
    declares = champs_echeance(session)
    if not declares:
        return []

    ids = base.scalar_subquery()
    documents = (session.query(Document)
                 .filter(Document.id.in_(ids),
                         Document.categorie_id.in_(list(declares)),
                         Document.date_suppression.is_(None))
                 .all())
    aujourdhui = date.today()
    limite = aujourdhui + timedelta(days=max(1, horizon))

    lignes = []
    for document in documents:
        valeurs = {m.cle: m.valeur for m in document.metadonnees}
        for cle, libelle, rappel in declares.get(document.categorie_id, []):
            echeance = _date(valeurs.get(cle))
            if echeance is None or echeance > limite:
                continue
            lignes.append({
                "document_id": document.id,
                "nom_fichier": document.nom_fichier,
                "categorie": document.categorie.nom if document.categorie else None,
                "champ": cle,
                "libelle_champ": libelle,
                "date": echeance.isoformat(),
                "jours": (echeance - aujourdhui).days,
                "passee": echeance < aujourdhui,
                "rappel_jours": rappel,
            })
    # La plus urgente d'abord — dépassée en tête : c'est celle dont on a le plus
    # besoin d'entendre parler.
    return sorted(lignes, key=lambda l: l["jours"])


def generer_rappels(session: Session) -> int:
    """
    Pose les rappels dont la date est arrivée dans la fenêtre déclarée.

    Une notification par document et par échéance, jamais deux : l'empreinte
    porte la date, donc une échéance repoussée (document corrigé, nouvelle
    version) redonne bien un rappel — c'est une autre échéance.
    """
    declares = champs_echeance(session)
    if not declares:
        return 0

    documents = (session.query(Document)
                 .filter(Document.categorie_id.in_(list(declares)),
                         Document.date_suppression.is_(None))
                 .all())
    aujourdhui = date.today()
    poses = 0

    for document in documents:
        valeurs = {m.cle: m.valeur for m in document.metadonnees}
        for cle, libelle, rappel in declares.get(document.categorie_id, []):
            echeance = _date(valeurs.get(cle))
            if echeance is None:
                continue
            jours = (echeance - aujourdhui).days
            if jours > rappel:
                continue    # trop tôt pour en parler

            titre = (f"{libelle} dépassée de {abs(jours)} jour(s)" if jours < 0
                     else f"{libelle} dans {jours} jour(s)" if jours > 0
                     else f"{libelle} aujourd'hui")
            nom = document.categorie.nom if document.categorie else "Document"
            posee = notifications.creer(
                session,
                titre=f"{nom} — {titre}",
                message=f"Document nº{document.id} ({document.nom_fichier}) : "
                        f"{libelle} au {echeance.isoformat()}.",
                document_id=document.id,
                source="rappel",
                empreinte=f"echeance:{document.id}:{cle}:{echeance.isoformat()}")
            if posee is not None:
                poses += 1
    return poses
