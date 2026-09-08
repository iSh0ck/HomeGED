"""
Les pièces d'un document (§22.2).

Un document **était** un fichier. Pour réunir une facture, sa garantie et le bon
de livraison, il fallait donc trois documents et un lien entre eux : trois fiches
à remplir, trois classements à décider, pour un seul achat. C'est ce détour
qu'EzGED n'a pas — sa fiche descriptive porte ses champs **et N fichiers**.

Une pièce n'est pas une version : la version est le **même papier redéposé**
(§18.36) — on rescanne la facture, elle remplace la précédente ; la pièce est un
**autre papier du même dossier** — la garantie, qui ne remplace rien.

Deux règles tiennent tout le reste :

* **une pièce principale, toujours exactement une.** C'est elle que le registre
  ouvre, que la miniature montre, que l'export emporte. Les colonnes du document
  en sont le reflet, et ce module est le seul endroit qui les écrit ;
* **le texte du document est celui de ses pièces**, concaténé dans l'ordre. Sans
  cela, chercher « garantie » ne ramènerait pas la facture à laquelle elle est
  jointe — et c'est pourtant la question qu'on se pose.
"""
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from .db import Document, PieceDocument

log = logging.getLogger(__name__)

# Ce qui sépare le texte de deux pièces dans celui du document. Deux sauts de
# ligne : l'index plein texte ne doit pas coller le dernier mot de l'une au
# premier de l'autre et inventer un mot qui n'existe nulle part.
SEPARATEUR_TEXTE = "\n\n"


class PieceRefusee(Exception):
    """Ce que le modèle interdit. Le message est destiné à l'écran."""


def lister(session: Session, document: Document) -> list[PieceDocument]:
    """Les pièces d'un document, dans leur ordre d'affichage."""
    return (session.query(PieceDocument)
            .filter(PieceDocument.document_id == document.id)
            .order_by(PieceDocument.ordre, PieceDocument.id)
            .all())


def principale(session: Session, document: Document) -> Optional[PieceDocument]:
    """
    La pièce principale, ou la première à défaut.

    Le repli n'est pas de la coquetterie : un document d'avant le §22.2 dont la
    migration n'aurait pas abouti n'a aucune pièce marquée, et le registre doit
    continuer de s'ouvrir.
    """
    toutes = lister(session, document)
    for piece in toutes:
        if piece.principale:
            return piece
    return toutes[0] if toutes else None


def _prochain_ordre(session: Session, document: Document) -> int:
    return len(lister(session, document)) + 1


def ajouter(session: Session, document: Document, chemin: str, nom_fichier: str,
            empreinte: str, texte: Optional[str] = None,
            taille: Optional[int] = None, utilisateur_id: Optional[int] = None,
            principale_: bool = False) -> PieceDocument:
    """
    Attache un fichier archivé à ce document.

    Le fichier est déjà archivé et océrisé quand on arrive ici : ce module ne
    touche pas au disque, il tient le modèle. C'est le serveur de travaux qui
    archive — il est le seul à avoir les archives en écriture, et il n'y a pas
    deux chemins d'entrée à tenir.
    """
    # Regardé **avant** d'ajouter : une fois la pièce en place, elle serait
    # elle-même la « première », et un document qui n'en avait aucune (une entrée
    # saisie à la main, §22.7) n'aurait jamais de pièce principale — donc rien à
    # ouvrir, alors qu'on vient de lui donner un fichier.
    orpheline = principale(session, document) is None

    piece = PieceDocument(
        document_id=document.id, nom_fichier=nom_fichier, chemin_stockage=chemin,
        hash_sha256=empreinte, texte_ocr=texte,
        taille_octets=taille if taille is not None else _taille(chemin),
        ordre=_prochain_ordre(session, document), principale=False,
        utilisateur_id=utilisateur_id)
    document.pieces.append(piece)
    session.flush()
    # Une pièce ajoutée à un document qui n'en avait aucune devient la
    # principale : sans cela, le document n'aurait pas de fichier à ouvrir.
    if principale_ or orpheline:
        definir_principale(session, document, piece)
    rafraichir_texte(session, document)
    return piece


def definir_principale(session: Session, document: Document,
                       piece: PieceDocument) -> PieceDocument:
    """
    Désigne la pièce que l'on voit partout ailleurs, et met le document à jour.

    Le document garde ses colonnes de fichier — chemin, empreinte, nom, taille —
    parce que tout ce qui les lit aujourd'hui (registre, aperçu, export,
    intégrité, versions) continue de fonctionner sans rien savoir des pièces. Ce
    sont un reflet, et c'est ici qu'il est tenu.
    """
    if piece.document_id != document.id:
        raise PieceRefusee("Cette pièce appartient à un autre document.")

    for autre in lister(session, document):
        autre.principale = (autre.id == piece.id)
    document.nom_fichier = piece.nom_fichier
    document.chemin_stockage = piece.chemin_stockage
    document.hash_sha256 = piece.hash_sha256
    document.taille_octets = piece.taille_octets
    session.flush()
    return piece


def retirer(session: Session, document: Document, piece: PieceDocument) -> None:
    """
    Détache une pièce. Le fichier archivé n'est pas effacé ici : c'est la purge
    du serveur de travaux qui reprend ce que plus aucun document ne réclame
    (§17.30) — l'API n'a pas les archives en écriture, et c'est très bien ainsi.

    La dernière pièce ne se retire pas : un document sans fichier n'est plus un
    document. Pour s'en défaire, on jette le document — la corbeille est faite
    pour ça, et elle se restaure.
    """
    if piece.document_id != document.id:
        raise PieceRefusee("Cette pièce appartient à un autre document.")
    toutes = lister(session, document)
    if len(toutes) <= 1:
        raise PieceRefusee(
            "C'est la seule pièce de ce document : le retirer ne laisserait rien à "
            "ouvrir. Mettez le document à la corbeille si vous voulez vous en défaire.")

    etait_principale = piece.principale
    session.delete(piece)
    session.flush()
    restantes = lister(session, document)
    for rang, restante in enumerate(restantes, start=1):
        restante.ordre = rang
    if etait_principale and restantes:
        definir_principale(session, document, restantes[0])
    rafraichir_texte(session, document)


def reordonner(session: Session, document: Document, ordre_ids: list[int]) -> list[PieceDocument]:
    """
    Range les pièces dans l'ordre donné. Les pièces omises suivent, dans leur
    ordre actuel : une liste partielle ne doit pas en faire disparaître.
    """
    par_id = {piece.id: piece for piece in lister(session, document)}
    inconnues = [i for i in ordre_ids if i not in par_id]
    if inconnues:
        raise PieceRefusee(f"Pièce(s) inconnue(s) pour ce document : {inconnues}")

    rang = 0
    for identifiant in ordre_ids:
        rang += 1
        par_id.pop(identifiant).ordre = rang
    for restante in par_id.values():
        rang += 1
        restante.ordre = rang
    session.flush()
    rafraichir_texte(session, document)
    return lister(session, document)


def rafraichir_texte(session: Session, document: Document) -> None:
    """
    Le texte du document est celui de ses pièces, dans l'ordre.

    C'est ce texte que porte l'index plein texte : sans lui, chercher un mot qui
    ne figure que sur la garantie ne ramènerait pas la facture à laquelle elle
    est jointe. Le texte de chaque pièce reste chez elle — celui du document en
    est dérivé, et se refait à chaque ajout, retrait ou changement d'ordre.
    """
    morceaux = [(piece.texte_ocr or "").strip() for piece in lister(session, document)]
    retenus = [m for m in morceaux if m]
    if retenus:
        document.texte_ocr = SEPARATEUR_TEXTE.join(retenus)
    session.flush()


def _taille(chemin: str) -> Optional[int]:
    try:
        return os.path.getsize(chemin)
    except OSError:
        return None
