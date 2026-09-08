"""
La position des mots dans un document (§21.5).

Écrire une expression régulière à l'aveugle est le passage le plus rebutant de
l'administration : on décrit avec des symboles ce qu'on a sous les yeux, on
enregistre, on relance un traitement, et l'on découvre que le motif ne prend
rien. EzGED règle cela dans son « centre d'apprentissage » : on **montre** la
donnée sur le document, et le modèle se construit.

Pour montrer, il faut savoir où sont les mots. `pdftotext -bbox` les rend avec
leur rectangle, dans le système de coordonnées de la page (en points). Nos
archives portent toutes une couche de texte — c'est l'océrisation qui la pose —,
donc l'information existe déjà : il n'y a rien à recalculer, seulement à lire.

Les coordonnées sont rendues **rapportées à la page** (0 à 1) et non en points :
l'interface affiche une miniature dont elle seule connaît la taille, et lui
imposer une conversion serait lui demander de deviner la résolution du rendu.
"""
import logging
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

log = logging.getLogger("homeged.mots")

# Au-delà, ce n'est plus une page qu'on annote : c'est un livre. La limite
# protège l'interface, qui dessine un rectangle par mot.
PLAFOND_MOTS = 4000
DELAI = 20


def nombre_de_pages(chemin: str) -> int:
    """
    Combien de pages ce PDF porte (§22.75). `1` à défaut : mieux vaut proposer
    une page de moins que faire cliquer vers le vide.
    """
    fichier = Path(chemin or "")
    if not fichier.is_file():
        return 1
    try:
        rendu = subprocess.run(["pdfinfo", str(fichier)],
                               capture_output=True, timeout=DELAI, check=True)
    except (subprocess.SubprocessError, OSError):
        return 1
    for ligne in rendu.stdout.decode("utf-8", "replace").splitlines():
        if ligne.startswith("Pages:"):
            try:
                return max(1, int(ligne.split(":", 1)[1].strip()))
            except ValueError:
                return 1
    return 1


def lire(chemin: str, page: int = 1) -> Optional[dict]:
    """
    Les mots d'une page, avec leur rectangle rapporté à la page.

    Rend `None` si le fichier est illisible, et une liste vide s'il n'a pas de
    couche de texte — les deux cas se disent différemment à l'écran : « document
    introuvable » n'est pas « ce document n'a pas été océrisé ».
    """
    fichier = Path(chemin or "")
    if not fichier.is_file():
        return None
    try:
        rendu = subprocess.run(
            ["pdftotext", "-bbox", "-f", str(page), "-l", str(page), str(fichier), "-"],
            capture_output=True, timeout=DELAI, check=True)
    except (subprocess.SubprocessError, OSError):
        log.exception("Lecture des positions impossible : %s", fichier)
        return None

    try:
        return _analyser(rendu.stdout.decode("utf-8", "replace"))
    except ET.ParseError:
        log.warning("Sortie pdftotext illisible pour %s", fichier)
        return None


def _analyser(xhtml: str) -> dict:
    """
    Extrait les mots du XHTML de `pdftotext -bbox`.

    L'espace de noms varie selon les versions de poppler : on le retire plutôt
    que de le déclarer, sinon la lecture casserait à la première mise à jour de
    l'image — pour un attribut qui ne nous apprend rien.
    """
    sans_ns = re.sub(r'\sxmlns="[^"]+"', "", xhtml, count=1)
    racine = ET.fromstring(sans_ns)
    page = racine.find(".//page")
    if page is None:
        return {"largeur": 0, "hauteur": 0, "mots": []}

    largeur = float(page.get("width") or 0) or 1
    hauteur = float(page.get("height") or 0) or 1
    mots = []
    for mot in page.iter("word"):
        texte = (mot.text or "").strip()
        if not texte:
            continue
        gauche, haut = float(mot.get("xMin", 0)), float(mot.get("yMin", 0))
        droite, bas = float(mot.get("xMax", 0)), float(mot.get("yMax", 0))
        mots.append({
            "texte": texte,
            # rapportées à la page : l'interface multiplie par la taille qu'elle
            # affiche, et n'a rien à savoir de la résolution du rendu
            "x": round(gauche / largeur, 5),
            "y": round(haut / hauteur, 5),
            "l": round((droite - gauche) / largeur, 5),
            "h": round((bas - haut) / hauteur, 5),
        })
        if len(mots) >= PLAFOND_MOTS:
            break

    return {"largeur": largeur, "hauteur": hauteur, "mots": mots}
