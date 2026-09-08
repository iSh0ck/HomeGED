"""
Export de l'archive (§17.30).

Objectif : pouvoir sortir de HomeGED **sans rien y laisser**. L'archive produite
range chaque PDF selon son classement, de sorte qu'elle se dépose telle quelle
sur un serveur de fichiers et reste exploitable sans l'application :

    Factures/Banque/2026-03-12 - Orange - facture.pdf
    Impôts/2026-05-02 - avis.pdf
    _Non classés/scan-0042.pdf
    index.csv

`index.csv` porte ce qu'un dossier ne sait pas dire : catégorie, émetteur,
dates, statut, et toutes les métadonnées extraites. Un export qui ne rendrait
que des fichiers perdrait le travail d'indexation ; un export qui ne rendrait
qu'un fichier de données ne rendrait pas les documents.

Les noms de fichiers sont reconstruits pour être lisibles et valides partout —
Windows refuse `:` et `?`, tous les systèmes détestent les doublons — mais le
nom d'origine reste inscrit dans l'index, seul endroit où l'on peut le garder
intact.
"""
import csv
import io
import logging
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from .db import Document

log = logging.getLogger(__name__)

DOSSIER_SANS_CATEGORIE = "_Non classés"

# Caractères refusés par au moins un système de fichiers courant. On les
# remplace plutôt que de les retirer : « 12/03 » deviendrait « 1203 », ce qui
# se lit mal.
INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _nom_sur(texte: str, defaut: str = "sans-nom") -> str:
    """Un nom de fichier ou de dossier acceptable partout, et lisible."""
    propre = INTERDITS.sub("-", (texte or "").strip())
    propre = re.sub(r"\s+", " ", propre).strip(" .")
    # Les points en fin de nom disparaissent sous Windows ; les noms réservés
    # (CON, PRN…) y sont refusés tout court.
    if propre.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL"}:
        propre = f"_{propre}"
    return propre[:120] or defaut


def _chemin_categorie(document: Document) -> str:
    """Le classement du document, en chemin de dossiers."""
    if not document.categorie:
        return DOSSIER_SANS_CATEGORIE
    parties, categorie, garde = [], document.categorie, 0
    while categorie is not None and garde < 10:   # garde-fou : une boucle de parents
        parties.append(_nom_sur(categorie.nom, "categorie"))
        categorie = categorie.parent
        garde += 1
    return "/".join(reversed(parties))


def _nom_document(document: Document) -> str:
    """
    Nom lisible du PDF : date, émetteur, puis le nom d'origine.

    Trié alphabétiquement dans un dossier, cela donne un ordre chronologique —
    ce qu'on attend d'une archive de factures posée sur un disque.
    """
    morceaux = []
    if document.date_document:
        morceaux.append(str(document.date_document))
    base = Path(document.nom_fichier or f"document-{document.id}").stem
    morceaux.append(_nom_sur(base, f"document-{document.id}"))
    return " - ".join(morceaux) + ".pdf"


def _index_csv(documents: list, session: Session = None) -> bytes:
    """
    Index de l'archive. Séparateur `;` et BOM : c'est ce qu'attend un tableur
    français, et un index qu'on n'arrive pas à ouvrir ne sert à personne.
    """
    # « emetteur » figurait ici alors que la ligne ne l'écrivait plus depuis le
    # retrait de l'émetteur codé en dur : l'index décalait donc toutes les
    # colonnes d'un cran, et se lisait de travers dans un tableur.
    colonnes_document = ["fichier_archive", "nom_origine", "categorie",
                         "date_document", "date_import", "statut", "pieces_jointes"]
    cles = sorted({m.cle for d in documents for m in d.metadonnees})
    # Une métadonnée peut porter le nom d'une colonne du document — les règles
    # d'extraction écrivent volontiers une clé `date_document`. Deux colonnes
    # homonymes dans un tableur, c'est une colonne qu'on lira de travers.
    entetes = [cle if cle not in colonnes_document else f"{cle} (extrait)" for cle in cles]

    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow([*colonnes_document, *entetes])
    for document, chemin in documents_avec_chemin(documents):
        valeurs = {m.cle: m.valeur for m in document.metadonnees}
        # Les fichiers joints à ce document (§22.2), pour qu'on les retrouve dans
        # l'archive sans avoir à en parcourir les dossiers.
        jointes = ([cible for _, cible in _fichiers_du_document(session, document, chemin)
                    if cible != chemin] if session is not None else [])
        ecrivain.writerow([
            chemin,
            document.nom_fichier or "",
            document.categorie.nom if document.categorie else "",
            document.date_document or "",
            document.date_import or "",
            document.statut or "",
            " | ".join(jointes),
            *[valeurs.get(cle, "") for cle in cles],
        ])
    return "﻿".encode() + tampon.getvalue().encode("utf-8")


def documents_avec_chemin(documents: list) -> list:
    """
    Associe à chaque document son chemin dans l'archive, en écartant les
    doublons : deux factures du même émetteur le même jour porteraient le même
    nom, et la seconde écraserait la première sans un mot.
    """
    resultat, pris = [], set()
    for document in documents:
        dossier = _chemin_categorie(document)
        nom = _nom_document(document)
        chemin = f"{dossier}/{nom}"
        if chemin in pris:
            racine, extension = os.path.splitext(chemin)
            suite = 2
            while f"{racine} ({suite}){extension}" in pris:
                suite += 1
            chemin = f"{racine} ({suite}){extension}"
        pris.add(chemin)
        resultat.append((document, chemin))
    return resultat


def _fichiers_du_document(session: Session, document, chemin: str) -> list:
    """
    `(source sur le disque, chemin dans l'archive)` pour chaque fichier d'un
    document — sa pièce principale d'abord, ses pièces jointes ensuite.

    Un document d'avant le §22.2 dont la table des pièces serait vide rend
    simplement son fichier : l'export ne doit pas dépendre d'une migration.
    """
    from . import pieces as module_pieces

    toutes = module_pieces.lister(session, document)
    if not toutes:
        # Une entrée saisie à la main n'a pas de fichier (§22.7), et ce n'est pas
        # un fichier manquant : la signaler comme telle ferait douter d'une
        # archive parfaitement complète. Ses valeurs partent dans l'index.
        return [(document.chemin_stockage, chemin)] if document.chemin_stockage else []

    racine, extension = os.path.splitext(chemin)
    resultat, pris = [], set()
    for piece in toutes:
        if piece.principale:
            cible = chemin
        else:
            # Le nom de la pièce, à côté de celui du document : « Facture EDF —
            # garantie.pdf » dit à la fois de quel dossier elle vient et ce
            # qu'elle est.
            propre = os.path.splitext(os.path.basename(piece.nom_fichier or "piece"))[0]
            cible = f"{racine} — {propre}{os.path.splitext(piece.nom_fichier)[1] or extension}"
        suite = 2
        while cible in pris:
            base, ext = os.path.splitext(cible)
            cible = f"{base} ({suite}){ext}"
            suite += 1
        pris.add(cible)
        resultat.append((piece.chemin_stockage, cible))
    return resultat


def construire(session: Session, destination: str) -> dict:
    """
    Écrit l'archive complète et rend `{documents, absents, taille_octets}`.

    Un PDF introuvable sur le disque n'interrompt pas l'export : il est compté
    et signalé dans l'index. Refuser de tout exporter parce qu'un fichier manque
    serait le plus sûr moyen de n'avoir aucune sauvegarde le jour où l'on en a
    besoin.
    """
    documents = (
        session.query(Document)
        .options(joinedload(Document.categorie), joinedload(Document.metadonnees))
        # Ce qui est en corbeille n'est pas dans l'archive (§21.1) : l'export
        # emporte ce que le foyer possède, et un document jeté est en instance de
        # l'être. Le restaurer avant d'exporter est un geste, le retirer d'une
        # archive livrée n'en est pas un.
        .filter(Document.date_suppression.is_(None))
        .order_by(Document.id)
        .all()
    )

    absents = []
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for document, chemin in documents_avec_chemin(documents):
            # **Toutes** les pièces, pas seulement celle qu'on ouvre (§22.2).
            # Cette archive est ce qui reste le jour où l'on quitte la GED : y
            # oublier la garantie jointe à une facture perdrait un fichier que
            # rien d'autre ne conserve. La principale garde le nom du document,
            # les autres portent le leur à côté — on retrouve un dossier complet
            # en ouvrant le zip, sans avoir à deviner.
            for source, cible in _fichiers_du_document(session, document, chemin):
                if not source or not os.path.exists(source):
                    absents.append(cible)
                    continue
                archive.write(source, cible)
        archive.writestr("index.csv", _index_csv(documents, session))
        if absents:
            archive.writestr(
                "FICHIERS_MANQUANTS.txt",
                "Ces documents figurent au registre mais leur PDF est introuvable "
                "sur le disque :\n\n" + "\n".join(absents) + "\n",
            )

    return {
        "documents": len(documents) - len(absents),
        "absents": len(absents),
        "taille_octets": os.path.getsize(destination),
    }


def purger(session: Session, dossier: str) -> int:
    """
    Efface les archives expirées ou déjà téléchargées, en base et sur le disque.

    Appelé à chaque nouvelle demande : un export oublié est une copie complète
    du foyer qui traîne, et personne ne pense à faire le ménage.
    """
    from .db import ExportArchive

    perimes = (
        session.query(ExportArchive)
        .filter((ExportArchive.date_expiration < datetime.now())
                | (ExportArchive.date_telechargement.isnot(None)))
        .all()
    )
    for export in perimes:
        _effacer(export.chemin)
        session.delete(export)
    session.commit()

    # Fichiers que plus aucune ligne ne réclame : une base restaurée, une ligne
    # supprimée à la main, et l'archive resterait sur le disque indéfiniment.
    # C'est le cas qui produit les vraies fuites — celui dont personne ne sait
    # qu'il existe.
    connus = {e.chemin for e in session.query(ExportArchive).all()}
    orphelins = 0
    limite = datetime.now().timestamp() - 3600      # une heure de répit : une
    # archive en cours d'écriture n'a pas encore sa ligne validée
    for fichier in Path(dossier).glob("*.zip") if os.path.isdir(dossier) else []:
        if str(fichier) in connus or fichier.stat().st_mtime > limite:
            continue
        _effacer(str(fichier))
        orphelins += 1
    if orphelins:
        log.info(f"{orphelins} archive(s) orpheline(s) effacée(s) de {dossier}")

    return len(perimes) + orphelins


def _effacer(chemin: Optional[str]) -> None:
    try:
        if chemin and os.path.exists(chemin):
            os.remove(chemin)
    except OSError:
        log.exception(f"Impossible d'effacer l'archive {chemin}")
