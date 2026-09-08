"""
Miniatures de première page (§19.20).

Ouvrir une fiche chargeait le PDF entier — plusieurs mégaoctets pour lire un
numéro de facture, à chaque clic de ligne. Une image de la première page suffit
la plupart du temps : on reconnaît le document, on lit l'en-tête, et l'on ouvre
le PDF quand on veut vraiment le lire.

Le rendu passe par Ghostscript, déjà présent pour l'océrisation : pas de
dépendance de plus pour une fonction d'affichage.

Ce dossier est un **cache**, pas une archive. Le vider ne perd rien — il coûte
une seconde par document au prochain affichage. C'est ce qui autorise à le
regénérer sans précaution et à l'effacer sans cérémonie.
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from . import config

log = logging.getLogger(__name__)

DELAI_RENDU = 20        # secondes ; au-delà, le PDF est pathologique


class RenduImpossible(Exception):
    """Le PDF n'a pas pu être rendu. Le message est destiné au journal, pas à l'écran."""


def chemin(document_id: int, empreinte: str, page: int = 1) -> Path:
    """
    Le nom porte l'empreinte du fichier : un document rescanné (§18.36) change
    d'empreinte, donc de miniature. Sans cela, une nouvelle version s'afficherait
    avec l'image de l'ancienne, et l'on croirait le dépôt perdu.

    La première page garde son nom d'origine (§22.75) : elle est demandée partout,
    et les miniatures déjà rendues n'ont pas à l'être une seconde fois. Les
    suivantes portent leur numéro.
    """
    suffixe = "" if page <= 1 else f"-p{page}"
    return Path(config.APERCUS_FOLDER) / f"{document_id}-{(empreinte or '')[:16]}{suffixe}.png"


def obtenir(document_id: int, source: str, empreinte: str, page: int = 1) -> Optional[Path]:
    """
    La miniature de ce document, rendue au besoin. `None` si le rendu échoue —
    l'appelant se rabat alors sur le PDF, plutôt que d'afficher une erreur pour
    une commodité d'affichage.
    """
    cible = chemin(document_id, empreinte, page)
    if cible.is_file() and cible.stat().st_size > 0:
        return cible
    if not source or not os.path.isfile(source):
        return None

    return rendre(source, cible, page)


def rendre(source: str, cible: Path, page: int = 1) -> Optional[Path]:
    """
    Rend une page de `source` dans `cible`, la première par défaut. Séparé
    d'`obtenir` parce que tout n'est pas un document du registre : un exemple
    importé pour apprendre une règle (§22.35) a besoin de la même image, mais pas
    du cache indexé par identifiant — que la purge des miniatures effacerait
    aussitôt.
    """
    page = max(1, int(page or 1))
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        # Une seule page rendue à la fois : une facture de trente pages ne coûte
        # pas plus cher qu'une d'une seule.
        subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
             "-sDEVICE=png16m", f"-dFirstPage={page}", f"-dLastPage={page}",
             "-dDownScaleFactor=2", f"-dDEVICEWIDTHPOINTS={config.APERCU_LARGEUR}",
             "-dPDFFitPage", "-r144",
             f"-sOutputFile={cible}", str(source)],
            check=True, capture_output=True, timeout=DELAI_RENDU)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as erreur:
        log.warning(f"Miniature impossible pour {source} : {erreur}")
        cible.unlink(missing_ok=True)
        return None
    return cible if cible.is_file() else None


def purger(document_ids: set) -> int:
    """
    Efface les miniatures dont plus aucun document ne répond.

    Même raison qu'ailleurs : ce qui ne s'efface jamais tout seul finit par
    occuper un disque. Ici la perte est nulle — une miniature se refait.
    """
    dossier = Path(config.APERCUS_FOLDER)
    if not dossier.is_dir():
        return 0
    efface = 0
    for fichier in dossier.glob("*.png"):
        # « 12-abcdef-p3.png » : l'identifiant est toujours en tête, quel que
        # soit le nombre de morceaux qui suivent.
        identifiant = fichier.stem.split("-", 1)[0]
        if not identifiant.isdigit() or int(identifiant) not in document_ids:
            try:
                fichier.unlink()
                efface += 1
            except OSError:
                log.exception(f"Miniature {fichier} non effacée")
    return efface
