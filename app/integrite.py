"""
Le contrôle d'intégrité des archives (§21.3).

Nous posions une empreinte à l'import, et **personne ne la revérifiait jamais**.
Une archive familiale est pourtant censée durer vingt ans : un disque se dégrade,
une synchronisation se trompe de sens, un programme écrit là où il ne devait pas.
Rien de cela ne prévient, et sans contrôle on ne s'en aperçoit que le jour où
l'on ouvre le document — c'est-à-dire le jour où l'on en a besoin.

Trois choix de conception, tous dictés par le même souci de ne pas mentir :

  * **l'empreinte contrôlée est celle de l'archive**, pas celle du fichier reçu.
    `hash_sha256` porte le fichier tel qu'il est arrivé ; l'océrisation et la
    compression le réécrivent. Les comparer signalerait une altération sur chaque
    document, ce qui revient à n'en signaler aucune.
  * **le travail s'étale**. On contrôle quelques documents par passage, les moins
    récemment vérifiés d'abord : l'archive tourne d'elle-même sans jamais être
    relue d'un bloc. EzGED renonce au-delà de 10 Mo ; nous lisons tout, mais
    lentement — le volume d'un foyer le permet, et un gros fichier est justement
    celui qu'on aimerait ne pas perdre.
  * **une première rencontre n'est pas une vérification**. Un document archivé
    avant ce contrôle n'a pas d'empreinte de référence : on la pose, et on le dit
    (`adoptees`). Prétendre l'avoir vérifié serait faux — le fichier peut avoir
    été abîmé la veille.
"""
import hashlib
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .db import Document, PieceDocument

log = logging.getLogger("homeged.integrite")

OK = "ok"
ALTEREE = "alteree"
ABSENT = "absent"

LIBELLES = {
    OK: "conforme",
    ALTEREE: "altérée",
    ABSENT: "fichier absent",
}

# Lu par blocs : un PDF de 200 Mo ne doit pas passer par la mémoire d'un coup.
TAILLE_BLOC = 1024 * 1024


def empreinte(chemin: str) -> Optional[str]:
    """SHA-256 du fichier, ou None s'il est illisible."""
    try:
        calcul = hashlib.sha256()
        with open(chemin, "rb") as fichier:
            for bloc in iter(lambda: fichier.read(TAILLE_BLOC), b""):
                calcul.update(bloc)
        return calcul.hexdigest()
    except OSError:
        return None


def poser(porteur, chemin: Optional[str] = None) -> Optional[str]:
    """
    Enregistre l'empreinte de l'archive telle qu'elle vient d'être écrite.

    `porteur` est un document ou une pièce : les deux portent un fichier archivé
    et les trois mêmes colonnes de contrôle. Écrire deux fois la même fonction
    aurait garanti qu'une des deux finisse par oublier quelque chose.

    Appelée à chaque fois que le fichier change de contenu — import, compression,
    nouvelle version. L'oublier quelque part ne casse rien : le contrôle
    adopterait l'empreinte au premier passage, mais il aurait perdu sa raison
    d'être pour ce fichier-là, puisqu'il validerait un fichier déjà altéré.
    """
    valeur = empreinte(chemin or porteur.chemin_stockage)
    if valeur:
        porteur.empreinte_archive = valeur
        porteur.date_controle = datetime.now()
        porteur.integrite = OK
    return valeur


def controler(session: Session, lot: int = 25) -> dict:
    """
    Contrôle un lot de **pièces**, les moins récemment vérifiées d'abord.

    Une pièce jointe est un fichier comme un autre : elle s'abîme sur le disque
    comme une facture, et personne ne l'ouvre pendant des années — c'est
    exactement le cas que ce contrôle existe pour attraper. Contrôler les
    documents seuls laissait ces fichiers-là sans surveillance (§22.2 bis).

    Le résultat de la pièce **principale** est recopié sur son document : les
    écrans, les compteurs et les alertes le lisent là depuis le §21.3, et rien ne
    gagnerait à ce qu'ils apprennent d'où il vient.

    Rend le bilan du passage. Rien n'est journalisé ici : c'est l'appelant qui
    décide, car une anomalie mérite une trace, mais consigner « tout va bien » à
    chaque passage noierait le journal.
    """
    if lot <= 0:
        return {"controles": 0, "adoptees": 0, "anomalies": []}

    candidats = (session.query(PieceDocument)
                 .join(Document, Document.id == PieceDocument.document_id)
                 .filter(Document.date_suppression.is_(None))
                 # NULL d'abord : ce qu'on n'a jamais regardé passe avant ce
                 # qu'on a vu hier.
                 .order_by(case((PieceDocument.date_controle.is_(None), 0), else_=1),
                           PieceDocument.date_controle)
                 .limit(lot).all())

    bilan = {"controles": 0, "adoptees": 0, "anomalies": []}
    for piece in candidats:
        chemin = piece.chemin_stockage
        piece.date_controle = datetime.now()

        if not chemin or not os.path.exists(chemin):
            _etat(piece, ABSENT)
            bilan["anomalies"].append(_anomalie(piece, ABSENT, chemin))
            continue

        valeur = empreinte(chemin)
        if valeur is None:
            _etat(piece, ABSENT)
            bilan["anomalies"].append(_anomalie(piece, ABSENT, chemin))
            continue

        if not piece.empreinte_archive:
            # Première rencontre : on pose la référence sans prétendre avoir
            # vérifié quoi que ce soit.
            piece.empreinte_archive = valeur
            _etat(piece, OK)
            bilan["adoptees"] += 1
            continue

        if valeur == piece.empreinte_archive:
            _etat(piece, OK)
            bilan["controles"] += 1
        else:
            _etat(piece, ALTEREE)
            bilan["anomalies"].append({
                **_anomalie(piece, ALTEREE, chemin),
                "attendu": piece.empreinte_archive, "trouve": valeur,
            })
    return bilan


def _etat(piece: PieceDocument, etat: str) -> None:
    """Pose l'état sur la pièce, et sur son document si elle est la principale."""
    piece.integrite = etat
    document = piece.document
    if document is not None and piece.principale:
        document.integrite = etat
        document.date_controle = piece.date_controle
        if piece.empreinte_archive:
            document.empreinte_archive = piece.empreinte_archive


def _anomalie(piece: PieceDocument, etat: str, chemin: Optional[str]) -> dict:
    """
    Une anomalie se nomme par le **document** — c'est lui qu'on ouvrira pour
    aller voir —, en disant quelle pièce est en cause quand ce n'est pas la
    principale. « Facture EDF » suffit rarement quand trois fichiers y sont
    joints.
    """
    return {
        "id": piece.document_id,
        "nom_fichier": piece.nom_fichier,
        "piece_id": piece.id,
        "principale": bool(piece.principale),
        "etat": etat,
        "chemin": chemin,
    }


def resume(session: Session) -> dict:
    """
    L'état de l'archive, pour l'écran d'administration.

    On compte les **fichiers** et non les documents : une facture à trois pièces
    représente trois choses à surveiller, et annoncer « 1 document conforme »
    quand deux de ses pièces manquent serait faux.

    Les anomalies sont nommées une par une : un compteur d'altérations sans les
    fichiers concernés n'apprend rien qu'on puisse suivre.
    """
    vivantes = (session.query(PieceDocument)
                .join(Document, Document.id == PieceDocument.document_id)
                .filter(Document.date_suppression.is_(None)))

    par_etat = dict(
        session.query(func.coalesce(PieceDocument.integrite, "jamais"),
                      func.count(PieceDocument.id))
        .join(Document, Document.id == PieceDocument.document_id)
        .filter(Document.date_suppression.is_(None))
        .group_by(func.coalesce(PieceDocument.integrite, "jamais")).all())

    anomalies = (vivantes.filter(PieceDocument.integrite.in_([ALTEREE, ABSENT]))
                 .order_by(PieceDocument.date_controle.desc()).limit(200).all())
    dernier = session.query(func.max(PieceDocument.date_controle)).scalar()

    return {
        "total": sum(par_etat.values()),
        "conformes": par_etat.get(OK, 0),
        "jamais_controles": par_etat.get("jamais", 0),
        "alterees": par_etat.get(ALTEREE, 0),
        "absents": par_etat.get(ABSENT, 0),
        "dernier_controle": dernier.isoformat(timespec="seconds") if dernier else None,
        "anomalies": [{
            "id": p.document_id,
            "nom_fichier": p.nom_fichier,
            "piece": None if p.principale else p.nom_fichier,
            "categorie": p.document.categorie.nom
            if p.document is not None and p.document.categorie else None,
            "chemin": p.chemin_stockage,
            "etat": p.integrite,
            "libelle_etat": LIBELLES.get(p.integrite, p.integrite),
            "date_controle": p.date_controle.isoformat(timespec="seconds")
            if p.date_controle else None,
        } for p in anomalies],
    }
