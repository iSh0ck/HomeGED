"""
Versions d'un document (§18.36).

Un document du foyer n'est pas figé : on rescanne une facture mal cadrée, on
reçoit la version corrigée d'un avis, on redépose une pièce après l'avoir signée.
Chaque dépôt devient une **version** de la même fiche, au lieu d'une fiche de
plus qui n'aurait aucun lien avec la première.

**Reconnaître « le même document » est le point délicat.** Deux critères, du plus
sûr au plus utile :

1. l'**empreinte** du fichier — même fichier, au bit près : c'est le même dépôt,
   il n'y a rien à ajouter ;
2. la **coïncidence de ce qui identifie une pièce** : même catégorie, même
   émetteur, même date de document. Deux factures du même émetteur, émises le
   même jour, sont selon toute vraisemblance la même — rescannée.

Le second critère est une supposition, et elle peut se tromper. Elle est donc
**bornée** (les trois valeurs doivent être présentes, aucune ne suffit seule),
et le rapprochement est **réversible** : détacher une version en refait une fiche
à part entière.
"""
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .db import Document, VersionDocument

log = logging.getLogger(__name__)

# Vocabulaire du moteur de filtres : « meta:<cle> » désigne une métadonnée.
PREFIXE_META = "meta:"


def version_par_empreinte(session: Session, empreinte: str) -> Optional[VersionDocument]:
    """Ce fichier a-t-il déjà été déposé, sous quelque version que ce soit ?"""
    return session.query(VersionDocument).filter_by(hash_sha256=empreinte).one_or_none()


def champs_identifiants(session: Session, categorie_id: int) -> list[str]:
    """
    Les champs qui identifient un document de cette catégorie (§18.40).

    Déclarés avec les champs attendus, là où l'on décrit déjà ce qu'une catégorie
    exige : une facture par son numéro, un bulletin de paie par sa période. Le
    code n'en connaît aucun d'avance — un foyer qui range autrement déclare les
    siens.
    """
    from .db import RegleChampCategorie

    return [r.champ for r in session.query(RegleChampCategorie)
            .filter_by(categorie_id=categorie_id, identifiant=True)
            .order_by(RegleChampCategorie.ordre, RegleChampCategorie.champ)]


def _valeurs_identifiantes(document: Document, champs: list[str]) -> Optional[dict]:
    """
    Ce que porte ce document sur les champs identifiants de sa catégorie.

    Rend `None` dès qu'il en manque un : un identifiant à moitié rempli
    n'identifie rien, et rapprocher sur ce qui reste reviendrait à deviner.
    """
    valeurs = {}
    for champ in champs:
        if champ.startswith(PREFIXE_META):
            cle = champ[len(PREFIXE_META):]
            valeur = next((m.valeur for m in document.metadonnees
                           if m.cle == cle and (m.valeur or "").strip()), None)
        elif champ == "date_document":
            valeur = str(document.date_document) if document.date_document else None
        else:
            valeur = None
        if not valeur:
            return None
        valeurs[champ] = str(valeur).strip()
    return valeurs


def document_jumeau(session: Session, document: Document) -> Optional[Document]:
    """
    Cherche la fiche que ce document vient manifestement redoubler.

    **C'est la catégorie qui dit sur quoi se fonder** : les champs cochés comme
    identifiants dans ses champs attendus. Une facture se reconnaît à son numéro,
    un bulletin de paie à sa période. Rien n'est écrit dans le code — c'était le
    défaut de la première version, avec sa liste de clés françaises figées.

    Trois abstentions, et chacune vaut mieux qu'un rapprochement hasardeux :
    aucun champ identifiant déclaré, un champ identifiant vide sur ce document,
    ou aucune catégorie. Dans ces cas, le document reste une fiche à part — et
    l'utilisateur peut toujours déclarer l'identifiant pour que les dépôts
    suivants se rapprochent.
    """
    if not document.categorie_id:
        return None

    champs = champs_identifiants(session, document.categorie_id)
    if not champs:
        return None

    reference = _valeurs_identifiantes(document, champs)
    if reference is None:
        return None

    candidats = (session.query(Document)
                 .filter(Document.id != document.id,
                         Document.categorie_id == document.categorie_id,
                         # un document en corbeille n'accueille pas de nouvelle
                         # version : on le croirait revenu tout seul (§21.1)
                         Document.date_suppression.is_(None))
                 .order_by(Document.id.asc())
                 .all())
    for candidat in candidats:
        if _valeurs_identifiantes(candidat, champs) == reference:
            return candidat
    return None


def enregistrer_depot(session: Session, document: Document, chemin: str, nom_fichier: str,
                      empreinte: str, taille: Optional[int] = None,
                      utilisateur_id: Optional[int] = None,
                      piece=None) -> VersionDocument:
    """
    Inscrit un dépôt comme **version courante** d'une pièce.

    La pièce suit : son fichier, son empreinte et sa taille deviennent ceux de la
    nouvelle version. C'est ce qui fait qu'ouvrir un document montre toujours le
    dernier état — sans quoi il faudrait aller chercher la bonne version à chaque
    consultation.

    `piece` vide vaut « la principale » (§22.3) : c'est le cas de tous les appels
    d'avant les pièces, et c'est le bon défaut — rescanner un document sans rien
    préciser, c'est rescanner ce qu'il montre.
    """
    from . import pieces as module_pieces

    if piece is None:
        piece = module_pieces.principale(session, document)
    _assurer_version_initiale(session, document, piece)

    # Ce fichier est-il déjà inscrit pour cette fiche ? C'est le cas au tout
    # premier dépôt : `_assurer_version_initiale` vient d'inscrire le fichier de
    # la fiche, qui est précisément celui qu'on enregistre. Le réinscrire
    # violerait l'unicité de l'empreinte — et n'ajouterait rien.
    deja = (session.query(VersionDocument)
            .filter_by(document_id=document.id, hash_sha256=empreinte).first())
    if deja:
        deja.piece_id = piece.id if piece is not None else None
        _autres_ne_sont_plus_courantes(session, document, piece, sauf=deja.id)
        deja.courante = True
        deja.chemin_stockage = chemin
        deja.nom_fichier = nom_fichier
        if taille is not None:
            deja.taille_octets = taille
        _suivre_sur_la_piece(session, document, piece, chemin, nom_fichier, empreinte,
                             deja.taille_octets)
        session.flush()
        return deja

    _autres_ne_sont_plus_courantes(session, document, piece)

    version = VersionDocument(
        document_id=document.id,
        piece_id=piece.id if piece is not None else None,
        hash_sha256=empreinte,
        chemin_stockage=chemin,
        nom_fichier=nom_fichier,
        taille_octets=taille if taille is not None else _taille(chemin),
        date_depot=datetime.now(),
        courante=True,
        utilisateur_id=utilisateur_id,
    )
    session.add(version)

    _suivre_sur_la_piece(session, document, piece, chemin, nom_fichier, empreinte,
                         version.taille_octets)
    session.flush()
    return version


def _autres_ne_sont_plus_courantes(session: Session, document: Document, piece,
                                   sauf: Optional[int] = None) -> None:
    """
    Une seule version courante **par pièce** : rescanner la garantie ne doit pas
    décourroner la facture, chacune ayant son historique propre.
    """
    query = session.query(VersionDocument).filter(VersionDocument.document_id == document.id)
    if piece is not None:
        query = query.filter(VersionDocument.piece_id == piece.id)
    if sauf is not None:
        query = query.filter(VersionDocument.id != sauf)
    query.update({"courante": False}, synchronize_session=False)


def _suivre_sur_la_piece(session: Session, document: Document, piece, chemin: str,
                         nom_fichier: str, empreinte: str,
                         taille: Optional[int]) -> None:
    """
    Une version remplace le fichier de **sa** pièce (§22.2, §22.3).

    C'est le même papier rescanné : il prend la place de celui qu'il remplace, là
    où il était. Sans cette ligne, la pièce pointerait l'ancien fichier et la
    vignette montrerait le scan d'avant.

    Le document ne suit que si c'est sa pièce principale qui a changé : ses
    colonnes de fichier en sont le reflet (§22.2), et rescanner une pièce jointe
    n'a aucune raison de changer ce que le registre ouvre.
    """
    from . import integrite, pieces as module_pieces

    if piece is not None:
        piece.chemin_stockage = chemin
        piece.nom_fichier = nom_fichier
        piece.hash_sha256 = empreinte
        piece.taille_octets = taille
        # L'archive a changé de fichier : son empreinte de contrôle avec (§21.3),
        # sinon le prochain passage crierait à l'altération d'un dépôt qu'on vient
        # nous-mêmes d'accepter.
        integrite.poser(piece, chemin)
        module_pieces.rafraichir_texte(session, document)

    if piece is None or piece.principale:
        document.chemin_stockage = chemin
        document.hash_sha256 = empreinte
        document.taille_octets = taille
        integrite.poser(document, chemin)


def _assurer_version_initiale(session: Session, document: Document, piece=None) -> None:
    """
    Une pièce sans aucune version : son fichier actuel en devient une, datée de
    l'import du document. Sans cela, l'historique commencerait au deuxième dépôt
    et l'original ne serait nulle part.
    """
    query = session.query(VersionDocument).filter(VersionDocument.document_id == document.id)
    if piece is not None:
        query = query.filter(VersionDocument.piece_id == piece.id)
    if query.count():
        return
    source = piece if piece is not None else document
    session.add(VersionDocument(
        document_id=document.id,
        piece_id=piece.id if piece is not None else None,
        hash_sha256=source.hash_sha256,
        chemin_stockage=source.chemin_stockage,
        nom_fichier=source.nom_fichier,
        taille_octets=source.taille_octets or _taille(source.chemin_stockage),
        date_depot=document.date_import or datetime.now(),
        courante=True,
    ))
    session.flush()


def lister(session: Session, document_id: int, piece_id: Optional[int] = None) -> list[dict]:
    """
    Les versions d'un document, la plus récente d'abord ; celles d'une pièce
    seulement si `piece_id` est donné — c'est le fichier qu'on rescanne, et son
    historique ne concerne que lui (§22.3).
    """
    query = session.query(VersionDocument).filter(VersionDocument.document_id == document_id)
    if piece_id is not None:
        query = query.filter(VersionDocument.piece_id == piece_id)
    versions = (query
                .order_by(VersionDocument.date_depot.desc(), VersionDocument.id.desc())
                .all())
    return [{
        "id": v.id,
        "piece_id": v.piece_id,
        "nom_fichier": v.nom_fichier,
        "taille_octets": v.taille_octets,
        "date_depot": v.date_depot.isoformat(timespec="seconds") if v.date_depot else None,
        "courante": bool(v.courante),
        "par": v.utilisateur.nom_affiche if v.utilisateur else None,
        "fichier_present": bool(v.chemin_stockage and os.path.exists(v.chemin_stockage)),
    } for v in versions]


def compter(session: Session, documents: list[Document]) -> dict:
    """`{document_id: nombre de versions}`, en une requête pour toute une page."""
    from sqlalchemy import func

    identifiants = [d.id for d in documents if d.id]
    if not identifiants:
        return {}
    lignes = (session.query(VersionDocument.document_id, func.count(VersionDocument.id))
              .filter(VersionDocument.document_id.in_(identifiants))
              .group_by(VersionDocument.document_id)
              .all())
    return {int(document_id): int(nombre) for document_id, nombre in lignes}


class SuppressionRefusee(Exception):
    pass


def supprimer(session: Session, version_id: int, effacer_fichier: bool = True) -> dict:
    """
    Supprime une version, et son fichier avec elle.

    **Jamais la dernière** : une fiche sans fichier ne s'ouvre plus, et rien dans
    l'interface ne dirait pourquoi. Supprimer la version courante promeut la plus
    récente de celles qui restent — la fiche doit toujours montrer quelque chose.
    """
    version = session.get(VersionDocument, version_id)
    if not version:
        raise SuppressionRefusee("Cette version n'existe plus.")

    restantes = (session.query(VersionDocument)
                 .filter(VersionDocument.document_id == version.document_id,
                         VersionDocument.id != version.id)
                 .order_by(VersionDocument.date_depot.desc(), VersionDocument.id.desc())
                 .all())
    if not restantes:
        raise SuppressionRefusee(
            "C'est la seule version de ce document : la supprimer laisserait une fiche "
            "sans fichier. Supprimez le document lui-même si c'est ce que vous voulez.")

    document = session.get(Document, version.document_id)
    etait_courante = bool(version.courante)
    trace = {"nom_fichier": version.nom_fichier,
             "date_depot": version.date_depot.isoformat(timespec="seconds")
             if version.date_depot else None,
             "etait_courante": etait_courante}

    chemin = version.chemin_stockage
    session.delete(version)
    session.flush()

    if etait_courante:
        promue = restantes[0]
        promue.courante = True
        if document:
            document.chemin_stockage = promue.chemin_stockage
            document.hash_sha256 = promue.hash_sha256
            document.taille_octets = promue.taille_octets
        trace["promue"] = promue.nom_fichier

    if effacer_fichier and chemin and os.path.exists(chemin):
        # Le fichier d'une autre version ne doit jamais partir : deux versions
        # peuvent pointer le même chemin si un dépôt a été rejoué.
        encore_utilise = (session.query(VersionDocument)
                          .filter(VersionDocument.chemin_stockage == chemin).count())
        if not encore_utilise:
            try:
                os.remove(chemin)
                trace["fichier_efface"] = True
            except OSError:
                log.exception("Fichier de version non effacé : %s", chemin)
    return trace


def _taille(chemin: Optional[str]) -> Optional[int]:
    try:
        return os.path.getsize(chemin) if chemin and os.path.exists(chemin) else None
    except OSError:
        return None
