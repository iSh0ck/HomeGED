"""
Thèmes et traductions déposés par le foyer (§22.50, §22.51).

HomeGED est destiné à être repris : quelqu'un doit pouvoir proposer une palette
ou une traduction **sans lire le code, ni reconstruire l'application**. Le moyen
le plus simple qui existe : un fichier JSON dans un dossier.

    themes/mon-theme.json      -> une palette de plus dans les réglages
    langues/es.json            -> une langue de plus dans le menu

Ces dossiers sont montés depuis l'hôte : on y copie un fichier, on recharge la
page. Rien n'est compilé, rien n'est redémarré.

Ce module ne fait que **lire et vérifier**. Un fichier mal formé est ignoré avec
un avertissement au journal, jamais servi à moitié : une palette incomplète
donnerait une interface illisible, et une traduction tronquée vaut moins que la
langue d'origine.
"""
import json
import logging
import re
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

# Une clé de thème ou de langue : de quoi nommer un fichier et une option, sans
# rien qui puisse désigner un chemin.
CLE = re.compile(r"^[a-z0-9_-]{2,32}$")
TAILLE_MAX = 512 * 1024        # un fichier de langue complet pèse ~50 ko


def _lire_dossier(dossier: str, valider) -> list[dict]:
    racine = Path(dossier)
    if not racine.is_dir():
        return []
    trouves = []
    for chemin in sorted(racine.glob("*.json")):
        try:
            if chemin.stat().st_size > TAILLE_MAX:
                log.warning("%s ignoré : fichier trop volumineux", chemin.name)
                continue
            contenu = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erreur:
            log.warning("%s ignoré : %s", chemin.name, erreur)
            continue
        # La clé vient du **nom du fichier** quand elle manque : c'est ce qu'on
        # attend en déposant « es.json » sans rien lire d'autre.
        contenu.setdefault("cle", chemin.stem)
        motif = valider(contenu)
        if motif:
            log.warning("%s ignoré : %s", chemin.name, motif)
            continue
        trouves.append(contenu)
    return trouves


def _valider_theme(theme: dict):
    if not CLE.match(str(theme.get("cle", ""))):
        return "clé invalide (minuscules, chiffres, tiret ou souligné)"
    variables = theme.get("variables")
    if not isinstance(variables, dict) or not variables:
        return "aucune variable de couleur"
    for nom, valeur in variables.items():
        if not str(nom).startswith("--") or not isinstance(valeur, str):
            return f"variable « {nom} » invalide"
    return None


def _valider_langue(langue: dict):
    if not CLE.match(str(langue.get("cle", ""))):
        return "clé invalide (minuscules, chiffres, tiret ou souligné)"
    textes = langue.get("textes")
    if not isinstance(textes, dict) or not textes:
        return "aucun texte"
    if any(not isinstance(v, str) for v in textes.values()):
        return "un texte n'est pas une chaîne"
    return None


def themes() -> list[dict]:
    """Les thèmes déposés dans `themes/`. Ceux livrés avec l'interface n'ont pas
    besoin de passer par ici — ils sont embarqués."""
    return _lire_dossier(config.THEMES_FOLDER, _valider_theme)


def langues() -> list[dict]:
    """Les traductions déposées dans `langues/`."""
    return _lire_dossier(config.LANGUES_FOLDER, _valider_langue)
