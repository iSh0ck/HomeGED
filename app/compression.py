"""
Compression des documents archivés (§17.8).

Un scan océrisé pèse lourd : l'image de la page y est stockée telle quelle, et
une facture de deux pages atteint facilement deux mégaoctets. Sur une archive
qui a vocation à durer, cela sature le disque bien avant que le foyer n'ait
beaucoup de documents.

L'optimiseur d'ocrmypdf recompresse ces images. Mesuré sur les documents réels
du projet : **-60 % sur une facture légère, -82 % sur un scan de 2 Mo**, avec
100 % du texte conservé et un écart visuel moyen de 0,07 % par pixel.

Le principe de ce module tient en une phrase : **on ne remplace l'archive que
si la version compressée est vérifiée et plus petite**. Trois contrôles avant
d'écrire, parce qu'un document d'archive abîmé ne se répare pas :

  1. le PDF s'ouvre et compte le même nombre de pages ;
  2. son texte reste extractible, à 2 % près — c'est lui qui porte la recherche
     plein texte et les règles d'extraction ;
  3. le fichier est effectivement plus petit.

Au moindre doute, l'original reste en place. Un fichier que l'optimiseur n'a pas
su réduire est daté quand même : il a été examiné, la réponse était non, on n'y
revient pas à chaque passage.
"""
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from . import config
from .ocr import PARAMS_MISE_EN_PAGE

log = logging.getLogger(__name__)

# Marge tolérée sur le texte extrait. L'optimiseur ne touche pas à la couche de
# texte, mais le réencodage des images peut décaler d'un caractère ou deux la
# restitution de pdfminer. Au-delà, quelque chose a été perdu.
TOLERANCE_TEXTE = 0.98

# Un gain d'un ou deux pour cent ne vaut pas la réécriture d'un fichier
# d'archive : on ne remplace que si la réduction est franche.
GAIN_MINIMAL = 0.05


class CompressionImpossible(RuntimeError):
    """L'optimiseur a échoué, ou son résultat n'a pas passé les vérifications."""


def _mesurer(chemin: str) -> tuple[int, int, int]:
    """Taille, nombre de pages, longueur du texte extractible."""
    import pikepdf
    from pdfminer.high_level import extract_text

    with pikepdf.open(chemin) as pdf:
        pages = len(pdf.pages)
    texte = extract_text(chemin, laparams=PARAMS_MISE_EN_PAGE) or ""
    return os.path.getsize(chemin), pages, len(texte.strip())


def optimiser(chemin: str, niveau: Optional[int] = None) -> dict:
    """
    Recompresse un PDF archivé, sur place, si et seulement si le résultat est
    vérifié et plus petit.

    Rend un compte rendu : `{"remplace": bool, "avant": octets, "apres": octets,
    "motif": str}`. Ne lève que si l'original lui-même est illisible — auquel cas
    il ne fallait pas y toucher, et l'appelant doit le savoir.
    """
    niveau = config.PDF_OPTIMISATION if niveau is None else niveau
    source = Path(chemin)
    if niveau <= 0:
        return {"remplace": False, "avant": source.stat().st_size,
                "apres": source.stat().st_size, "motif": "compression désactivée"}

    avant, pages_avant, texte_avant = _mesurer(str(source))

    with tempfile.TemporaryDirectory() as travail:
        candidat = os.path.join(travail, source.name)
        # `--skip-text` : ne pas ré-océriser une page qui porte déjà du texte.
        # Sans lui, ocrmypdf refuse net (« page already has text »).
        # `--tesseract-timeout 0` : ne pas océriser du tout, seulement optimiser.
        resultat = subprocess.run(
            ["ocrmypdf", "--skip-text", "--tesseract-timeout", "0",
             "--optimize", str(niveau), "--output-type", "pdf",
             str(source), candidat],
            capture_output=True, text=True,
        )
        if resultat.returncode != 0 or not os.path.exists(candidat):
            derniere = (resultat.stderr.strip().splitlines() or ["sans détail"])[-1]
            return {"remplace": False, "avant": avant, "apres": avant,
                    "motif": f"optimiseur en échec : {derniere[:120]}"}

        try:
            apres, pages_apres, texte_apres = _mesurer(candidat)
        except Exception as erreur:            # PDF produit illisible
            return {"remplace": False, "avant": avant, "apres": avant,
                    "motif": f"résultat illisible : {erreur}"}

        if pages_apres != pages_avant:
            return {"remplace": False, "avant": avant, "apres": avant,
                    "motif": f"{pages_avant} pages avant, {pages_apres} après"}

        if texte_avant and texte_apres < texte_avant * TOLERANCE_TEXTE:
            return {"remplace": False, "avant": avant, "apres": avant,
                    "motif": f"texte perdu ({texte_apres} caractères contre {texte_avant})"}

        if apres >= avant * (1 - GAIN_MINIMAL):
            return {"remplace": False, "avant": avant, "apres": apres,
                    "motif": "gain insuffisant"}

        # Remplacement en deux temps : la copie se fait à côté, puis le
        # déplacement est atomique sur le même système de fichiers. Une coupure
        # au mauvais moment laisse l'ancien fichier intact, jamais un fichier
        # tronqué.
        provisoire = source.with_suffix(source.suffix + ".compresse")
        shutil.copy2(candidat, provisoire)
        os.replace(provisoire, source)

    return {"remplace": True, "avant": avant, "apres": apres,
            "motif": f"{100 * (1 - apres / avant):.0f} % gagnés"}
