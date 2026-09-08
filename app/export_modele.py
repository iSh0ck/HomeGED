"""
L'export par modèle d'arborescence et de nommage (§21.13).

L'export de secours (§17.30) sort **tout** le foyer, une fois, sous mot de passe
administrateur : il répond à « je ne me sers plus de la GED ». Celui-ci répond à
l'autre besoin, quotidien — sortir **une sélection** rangée comme on la veut,
pour la donner au comptable, à l'assurance, au notaire.

Le rangement se décrit par deux modèles à trous : un pour les dossiers,
`{annee}/{type}` ; un pour le nom, `{champ:emetteur} - {date}`. Les trous sont
**les champs du document** — il n'y a pas de vocabulaire de plus à apprendre, et
tout champ attendu par un type peut servir de nom de fichier.

Ce module ne fait que construire : la demande vient de l'API, l'écriture est
faite par le serveur de travaux. Cinq cents PDF à copier et compresser tiennent
une connexion ouverte plusieurs minutes, et l'API n'a pas les archives en
écriture.
"""
import logging
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from . import config
from .db import Document

log = logging.getLogger(__name__)

MODELE_DOSSIER_DEFAUT = "{annee}/{type}"
MODELE_NOM_DEFAUT = "{nom_fichier}"

# Ce qu'un modèle sait remplir. Documenté ici et rendu par l'API : un modèle à
# trous ne sert à rien si l'on doit deviner les trous.
TROUS = {
    "annee": "Année du document (celle de l'import à défaut)",
    "mois": "Mois sur deux chiffres",
    "jour": "Jour sur deux chiffres",
    "date": "Date du document (AAAA-MM-JJ)",
    "type": "Type de document",
    "dossier": "Dossier parent du type",
    "nom_fichier": "Nom du fichier tel qu'il a été déposé",
    "id": "Numéro du document",
    "champ:<clé>": "N'importe quelle valeur du document (ex. {champ:emetteur})",
}

# Interdits dans un nom de fichier, sur les systèmes qui liront l'archive. On
# remplace plutôt que de refuser : un émetteur qui s'appelle « Eau / Ville » ne
# doit pas faire échouer un export.
INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def libelles_des_references(session: Session, documents: list[Document]) -> dict:
    """
    `{document_id: {clé: libellé}}` pour les valeurs qui pointent une table du
    foyer.

    Sans cela, un nom de fichier bâti sur `{champ:emetteur}` sortait
    « usr_emetteurs-5 - 2026-03.pdf » : la référence brute, pour une archive lue
    par un comptable. Résolu en un aller-retour par table, pas un par document.
    """
    from . import base_donnees

    besoins: dict[str, set] = {}
    valeurs: dict[int, dict] = {}
    for document in documents:
        for meta in document.metadonnees:
            brute = (meta.valeur or "").strip()
            if base_donnees.SEPARATEUR_SOURCE not in brute:
                continue
            table, identifiant = brute.split(base_donnees.SEPARATEUR_SOURCE, 1)
            if not table.startswith(("usr_", "sys_")) or not identifiant.isdigit():
                continue
            besoins.setdefault(table, set()).add(identifiant)
            valeurs.setdefault(document.id, {})[meta.cle] = (table, identifiant)

    resolus = {}
    for table, identifiants in besoins.items():
        try:
            resolus[table] = base_donnees.libelles_par_id(session, table, identifiants)
        except Exception:
            log.warning("Table « %s » illisible : ses références resteront brutes", table)

    return {
        document_id: {cle: resolus.get(table, {}).get(str(identifiant))
                      for cle, (table, identifiant) in champs.items()
                      if resolus.get(table, {}).get(str(identifiant))}
        for document_id, champs in valeurs.items()
    }


def _valeur(document: Document, trou: str, metadonnees: dict) -> str:
    if trou.startswith("champ:"):
        return str(metadonnees.get(trou[len("champ:"):], "") or "")
    date = document.date_document or (
        document.date_import.date() if document.date_import else None)
    if trou == "annee":
        return f"{date.year}" if date else "sans date"
    if trou == "mois":
        return f"{date.month:02d}" if date else "00"
    if trou == "jour":
        return f"{date.day:02d}" if date else "00"
    if trou == "date":
        return date.isoformat() if date else "sans-date"
    if trou == "type":
        return document.categorie.nom if document.categorie else "sans classement"
    if trou == "dossier":
        parent = document.categorie.parent if document.categorie else None
        return parent.nom if parent else ""
    if trou == "nom_fichier":
        return os.path.splitext(document.nom_fichier or "")[0]
    if trou == "id":
        return str(document.id)
    return ""


def remplir(modele: str, document: Document, metadonnees: dict) -> str:
    """
    Remplit un modèle pour ce document. Un trou inconnu ou vide **disparaît**
    plutôt que de laisser « {champ:garantie} » dans un nom de fichier : l'archive
    est lue par quelqu'un qui n'a jamais vu nos modèles.
    """
    def remplacer(trouve):
        return _propre(_valeur(document, trouve.group(1).strip(), metadonnees))

    rendu = re.sub(r"\{([^}]+)\}", remplacer, modele or "")
    # Un trou vide laisse des séparateurs orphelins : « - 2026-03.pdf » se lit
    # mal, et deux dossiers « / » de suite créent un niveau sans nom.
    rendu = re.sub(r"\s*[-–—]\s*(?=[-–—/]|$)", "", rendu)
    rendu = re.sub(r"/{2,}", "/", rendu).strip(" /-")
    return rendu


def _propre(valeur: str) -> str:
    return INTERDITS.sub("-", valeur).strip()


def chemin_dans_archive(document: Document, metadonnees: dict,
                        modele_dossier: str, modele_nom: str, pris: set) -> str:
    """Le chemin complet d'un document dans l'archive, sans écraser un homonyme."""
    dossier = remplir(modele_dossier or MODELE_DOSSIER_DEFAUT, document, metadonnees)
    nom = remplir(modele_nom or MODELE_NOM_DEFAUT, document, metadonnees) or str(document.id)
    extension = os.path.splitext(document.chemin_stockage or ".pdf")[1] or ".pdf"
    chemin = f"{dossier}/{nom}{extension}" if dossier else f"{nom}{extension}"

    if chemin in pris:
        racine, ext = os.path.splitext(chemin)
        suite = 2
        while f"{racine} ({suite}){ext}" in pris:
            suite += 1
        chemin = f"{racine} ({suite}){ext}"
    pris.add(chemin)
    return chemin


def construire(session: Session, documents: list[Document], destination: str,
               modele_dossier: Optional[str], modele_nom: Optional[str]) -> dict:
    """
    Écrit l'archive et rend `{documents, absents, taille_octets}`.

    **Toutes les pièces** d'un document y sont (§22.2) : une facture sans sa
    garantie n'est pas la facture qu'on voulait donner. La principale porte le
    nom du modèle, les autres le leur à côté.

    Un fichier introuvable n'interrompt rien : il est compté et signalé dans
    l'archive. Refuser de tout exporter parce qu'un PDF manque serait le plus sûr
    moyen de n'avoir aucune sortie le jour où l'on en a besoin.
    """
    from . import pieces as module_pieces

    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    absents, pris, ecrits = [], set(), 0

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        libelles = libelles_des_references(session, documents)
        for document in documents:
            # Le libellé quand la valeur pointe une table du foyer, la valeur
            # brute sinon : « Orange - 2026-03.pdf » se lit, « usr_emetteurs-5 »
            # non — et c'est un tiers qui ouvrira cette archive.
            metadonnees = {m.cle: m.valeur for m in document.metadonnees}
            metadonnees.update(libelles.get(document.id, {}))
            chemin = chemin_dans_archive(document, metadonnees, modele_dossier,
                                         modele_nom, pris)
            racine, extension = os.path.splitext(chemin)
            morceaux = module_pieces.lister(session, document)
            if not morceaux and not document.chemin_stockage:
                continue     # entrée sans fichier (§22.7) : rien à écrire, rien à signaler
            for piece in (morceaux or [None]):
                source = piece.chemin_stockage if piece else document.chemin_stockage
                if piece is None or piece.principale:
                    cible = chemin
                else:
                    nom_piece = _propre(os.path.splitext(piece.nom_fichier or "piece")[0])
                    cible = f"{racine} — {nom_piece}{extension}"
                if not source or not os.path.exists(source):
                    absents.append(cible)
                    continue
                archive.write(source, cible)
                ecrits += 1
        if absents:
            archive.writestr(
                "FICHIERS_MANQUANTS.txt",
                "Ces fichiers figurent au registre mais sont introuvables sur le "
                "disque :\n\n" + "\n".join(absents) + "\n")

    return {"documents": len(documents), "fichiers": ecrits, "absents": len(absents),
            "taille_octets": os.path.getsize(destination)}


def nom_archive(demande_id: int) -> str:
    """Un nom qui dit ce que c'est et quand — l'archive vit dans les
    téléchargements de quelqu'un, souvent longtemps."""
    horodatage = datetime.now().strftime("%Y%m%d-%H%M")
    return str(Path(config.EXPORT_FOLDER) / f"selection-{horodatage}-{demande_id}.zip")


def documents_de(session: Session, criteres: list, categorie_id: Optional[int],
                 base_query) -> list[Document]:
    """
    Les documents visés par la demande, dans l'ordre du registre.

    `base_query` vient de l'appelant **déjà filtrée par les droits** : un export
    ne doit pas sortir ce que son demandeur n'a pas le droit de voir, et c'est le
    genre de contrôle qu'on n'écrit pas deux fois.
    """
    from . import filtres as moteur_filtres
    from .db import ids_categorie_et_descendants

    query = base_query.options(joinedload(Document.categorie),
                               joinedload(Document.metadonnees))
    if categorie_id:
        query = query.filter(
            Document.categorie_id.in_(ids_categorie_et_descendants(session, categorie_id)))
    if criteres:
        query = moteur_filtres.appliquer(
            query, session, [moteur_filtres.Filtre(**c) for c in criteres])
    return query.order_by(Document.id).all()
