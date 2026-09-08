"""
Dossiers de dépôt, tenus par la GED (§19.2).

Le classement cesse d'être deviné pour devenir déclaré : celui qui dépose choisit
le dossier, et c'est cet emplacement qui fait foi. Chaque **type de document** a
donc un dossier à lui sous `ocr_wait/`, **à plat** — un seul niveau, quel que soit
l'endroit du type dans l'arborescence. Chemins courts pour un scanner à
destinations préprogrammées ; contrepartie assumée, deux types de même nom dans
deux dossiers différents doivent porter des noms de dépôt distincts.

Trois principes, et chacun répond à une façon de perdre un fichier :

* **la GED est seule à créer ces dossiers.** Personne n'en ajoute à la main —
  un dossier qui ne correspond à aucun type ne serait lu par rien (§19.5 le
  signale) ;
* **renommer un dossier de dépôt emporte ce qui l'attendait.** Sans cela, le
  premier renommage laisserait des fichiers dans un dossier que plus personne
  ne regarde ;
* **supprimer un type ne supprime jamais son dossier.** Un dépôt en cours ne
  doit pas disparaître avec une décision d'administration ; le dossier reste, et
  il est signalé.
"""
import logging
import os
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from . import categories as natures, config
from .db import Categorie

log = logging.getLogger(__name__)

LONGUEUR_MAXIMALE = 64


class DepotRefuse(Exception):
    """Nom de dossier inutilisable. Le message est destiné à l'écran."""


def racine() -> Path:
    return Path(config.OCR_WAIT_FOLDER)


def chemin(dossier_depot: str) -> Path:
    return racine() / dossier_depot


def normaliser(nom: str) -> str:
    """
    « Relevés bancaires » → `releves_bancaires`.

    Sans accent ni majuscule, et rien d'autre que des lettres, des chiffres et
    des tirets bas : ce nom se tape dans un chemin, se programme dans un scanner,
    et voyage entre des systèmes de fichiers qui n'ont pas les mêmes idées sur
    les accents et la casse.
    """
    sans_accent = "".join(
        c for c in unicodedata.normalize("NFD", nom or "")
        if unicodedata.category(c) != "Mn"
    )
    epure = re.sub(r"[^a-z0-9]+", "_", sans_accent.casefold()).strip("_")
    return epure[:LONGUEUR_MAXIMALE].strip("_")


def valider(propose: str) -> str:
    """Vérifie qu'un nom saisi à la main reste un nom de dossier acceptable."""
    nom = normaliser(propose)
    if not nom:
        raise DepotRefuse(
            "Le dossier de dépôt doit contenir au moins une lettre ou un chiffre.")
    return nom


def nom_libre(session: Session, souhaite: str, sauf_id: Optional[int] = None) -> str:
    """
    Le nom demandé, ou le premier suffixé qui ne soit pas déjà pris.

    Deux types visant le même dossier rendraient le dépôt ambigu — c'est
    exactement ce que la phase supprime. Plutôt que de refuser un homonyme, on
    propose `factures_2` : à la création, un refus obligerait à trouver soi-même
    un nom libre sans savoir lesquels le sont.
    """
    pris = {
        c.dossier_depot for c in session.query(Categorie)
        if c.dossier_depot and c.id != sauf_id
    }
    if souhaite not in pris:
        return souhaite
    base = souhaite[:LONGUEUR_MAXIMALE - 3]
    rang = 2
    while f"{base}_{rang}" in pris:
        rang += 1
    return f"{base}_{rang}"


def creer(dossier_depot: str) -> bool:
    """
    Crée le dossier s'il manque, **avec ses droits**. Rend `True` s'il vient
    d'être créé.

    Les droits sont posés ici et pas seulement à la synchronisation (§21.11) : un
    dossier créé par l'API héritait du masque du processus — `0755`, propriété de
    root — et personne ne pouvait y déposer. Le dossier existait, on l'ouvrait, on
    y glissait un fichier, et le système refusait sans qu'on comprenne pourquoi ;
    il fallait attendre le passage d'entretien du serveur de travaux, jusqu'à cinq
    minutes plus tard, pour qu'il devienne utilisable. Un dossier de dépôt
    inutilisable ne vaut pas mieux qu'un dossier absent.
    """
    cible = chemin(dossier_depot)
    if cible.is_dir():
        _appliquer_droits([dossier_depot])
        return False
    cible.mkdir(parents=True, exist_ok=True)
    _appliquer_droits([dossier_depot])
    log.info(f"Dossier de dépôt créé : {cible}")
    return True


def retirer(dossier_depot: Optional[str]) -> str:
    """
    Retire le dossier de dépôt d'un type supprimé (§22.88). Rend ce qui a été
    fait : `"retire"`, `"garde"` ou `"absent"`.

    Le dossier restait en place, et c'est trompeur : il a l'air d'un point
    d'entrée vivant alors que plus aucun type ne le réclame. Ce qu'on y dépose
    finit au Centre d'analyse, sans classement, et l'on cherche pourquoi.

    **Mais on n'efface pas ce qui attend.** Un fichier posé la veille dans ce
    dossier n'a pas encore été lu ; le détruire avec le dossier perdrait un
    papier que personne n'a vu. Le dossier ne part donc que s'il est vide, et
    l'appelant dit ce qu'il en est.
    """
    if not dossier_depot:
        return "absent"
    cible = chemin(dossier_depot)
    if not cible.is_dir():
        return "absent"
    if any(cible.iterdir()):
        log.info("Dossier de dépôt %s gardé : il contient encore des fichiers", cible)
        return "garde"
    try:
        cible.rmdir()
    except OSError:
        log.warning("Dossier de dépôt %s non retiré", cible)
        return "garde"
    log.info(f"Dossier de dépôt retiré : {cible}")
    return "retire"


def renommer(ancien: Optional[str], nouveau: str) -> None:
    """
    Renomme un dossier de dépôt **et déplace ce qui l'attendait**.

    Le déplacement est le point important : un fichier déposé la veille dans
    l'ancien dossier ne serait plus jamais lu si on se contentait de créer le
    nouveau à côté.
    """
    if not nouveau:
        return
    destination = chemin(nouveau)
    if not ancien or ancien == nouveau:
        creer(nouveau)
        return

    source = chemin(ancien)
    if not source.is_dir():
        creer(nouveau)
        return

    destination.mkdir(parents=True, exist_ok=True)
    deplaces = 0
    for fichier in source.iterdir():
        if not fichier.is_file():
            continue
        arrivee = destination / fichier.name
        if arrivee.exists():
            arrivee = destination / f"{fichier.stem}_{int(os.path.getmtime(fichier))}{fichier.suffix}"
        shutil.move(str(fichier), str(arrivee))
        deplaces += 1
    try:
        # `rmdir` et non `rmtree` : s'il reste quoi que ce soit — un
        # sous-dossier créé à la main, par exemple — on préfère laisser en place
        # et le faire signaler plutôt que de détruire ce qu'on n'a pas mis là.
        source.rmdir()
    except OSError:
        log.warning(f"L'ancien dossier de dépôt {source} n'est pas vide : il est conservé")
    log.info(f"Dossier de dépôt renommé : {ancien} → {nouveau} ({deplaces} fichier(s) déplacé(s))")


def attribuer(session: Session, categorie: Categorie, souhaite: Optional[str] = None) -> Optional[str]:
    """
    Fixe le dossier de dépôt d'une catégorie, et rend le nom retenu.

    Un dossier de classement n'en a pas : il ne reçoit aucun document. Une fiche
    simple non plus : rien n'y entre tout seul, on y glisse un fichier à la main
    (§22.1). Un type qui n'en déclare pas en reçoit un, déduit de son nom — il en
    faut un pour qu'on puisse y déposer, et l'administrateur le changera s'il ne
    lui plaît pas.
    """
    # Seul un type de document reçoit des dépôts : un dossier organise, une fiche
    # simple se remplit à la main.
    if not natures.recoit_des_depots(categorie):
        categorie.dossier_depot = None
        return None

    base = valider(souhaite) if souhaite else (categorie.dossier_depot or normaliser(categorie.nom))
    if not base:
        base = f"type_{categorie.id or 'nouveau'}"
    retenu = nom_libre(session, base, sauf_id=categorie.id)
    categorie.dossier_depot = retenu
    return retenu


def synchroniser(session: Session) -> dict:
    """
    Met l'arborescence de dépôt en accord avec les types déclarés.

    Appelée au démarrage du serveur de travaux et à chaque passe d'entretien :
    c'est le filet qui rattrape un dossier effacé à la main, une base restaurée,
    ou un type créé pendant que le serveur était arrêté.

    Elle **crée** ce qui manque et ne **supprime** jamais rien : un dossier sans
    type correspondant peut contenir un dépôt en cours. Il est signalé (§19.5),
    pas effacé.
    """
    racine().mkdir(parents=True, exist_ok=True)
    bilan = {"crees": 0, "attribues": 0}

    types = [c for c in session.query(Categorie) if natures.recoit_des_depots(c)]
    for categorie in types:
        if not categorie.dossier_depot:
            attribuer(session, categorie)
            bilan["attribues"] += 1
    if bilan["attribues"]:
        session.commit()

    declares = [c.dossier_depot for c in types if c.dossier_depot]
    for nom in declares:
        if creer(nom):
            bilan["crees"] += 1
    # La GED est seule à tenir cette arborescence (§19.5) : on repose les droits
    # à chaque passage, un dossier ayant pu être recréé à la main entre-temps.
    _appliquer_droits(declares)
    return bilan


# Droits posés sur l'arborescence de dépôt (§19.5).
#
# La racine en lecture et traversée seules : personne n'y crée de fichier ni de
# dossier — pas même son propriétaire, qui devrait pour cela changer les droits
# délibérément. Le serveur, lui, tourne en root et n'est pas concerné : c'est
# ainsi que la GED reste seule à tenir cette arborescence.
#
# Les dossiers de type, eux, sont ouverts à tous, avec le bit collant : chacun y
# dépose ce qu'il veut, personne n'efface le dépôt d'un autre.
#
# Ce que cela ne couvre pas, et qu'aucune permission ne couvrira : un partage
# monté en écriture totale, ou un dépôt fait par root. D'où le signalement, qui
# n'est pas un repli mais l'autre moitié du dispositif.
DROITS_RACINE = 0o555
DROITS_DOSSIER = 0o1777


def _appliquer_droits(dossiers: list[str]) -> None:
    """Pose les droits sur la racine et les dossiers de dépôt, sans jamais échouer."""
    for chemin_cible, mode in [(racine(), DROITS_RACINE)] + [
            (chemin(nom), DROITS_DOSSIER) for nom in dossiers]:
        try:
            if chemin_cible.is_dir() and (chemin_cible.stat().st_mode & 0o7777) != mode:
                os.chmod(chemin_cible, mode)
        except OSError as erreur:
            # Un partage réseau peut refuser un changement de droits. Ce n'est pas
            # une raison d'arrêter : le signalement prend alors tout le relais.
            log.warning(f"Droits non appliqués sur {chemin_cible} : {erreur}")


def anomalies(session: Session) -> list[dict]:
    """
    Ce qui se trouve dans le dépôt sans y avoir sa place (§19.5).

    Trois cas, et chacun se produit pour une raison différente :

    * un **dossier qu'aucun type ne réclame** — créé à la main, ou laissé par un
      type supprimé. La GED ne les distingue pas et ne prétend pas le faire :
      elle n'en garde aucune trace, et deviner serait pire que de le dire ;
    * un **fichier que le serveur ne prendra jamais**, parce que son extension
      n'est pas traitée. Celui-là ne se voyait nulle part : il restait dans le
      dépôt indéfiniment, sans travail ni message ;
    * un **fichier en attente au mauvais endroit** — à la racine ou dans un
      dossier inconnu. En général transitoire : la surveillance l'attrape et en
      fait un travail « à classer ». S'il est là, c'est qu'elle ne l'a pas encore
      vu, ou qu'elle ne le verra pas.

    Rien n'est déplacé ni effacé ici : cette fonction regarde, elle ne décide pas.
    """
    base = racine()
    if not base.is_dir():
        return []

    connus = dossiers_declares(session)
    trouvees: list[dict] = []

    for entree in sorted(base.iterdir(), key=lambda p: p.name):
        if entree.is_dir():
            if entree.name in connus:
                # dossier légitime : on n'y cherche que les fichiers intraitables
                trouvees += _fichiers_intraitables(entree, base)
                continue
            fichiers = [f for f in entree.rglob("*") if f.is_file()]
            trouvees.append({
                "chemin": entree.name,
                "nom": entree.name,
                "dossier": True,
                "raison": "dossier_inconnu",
                "contient": len(fichiers),
                "taille_octets": sum(f.stat().st_size for f in fichiers),
                "date": _date(entree),
                "traitable": False,
            })
            trouvees += [_decrire(f, base, "hors_dossier_de_type") for f in fichiers]
        elif entree.is_file():
            trouvees.append(_decrire(entree, base, "racine"))

    return trouvees


def _fichiers_intraitables(dossier: Path, base: Path) -> list[dict]:
    """Fichiers qu'aucun traitement ne prendra, dans un dossier pourtant légitime."""
    from . import config as reglages_service

    return [
        _decrire(f, base, "extension_non_traitee")
        for f in sorted(dossier.rglob("*"), key=str)
        if f.is_file() and f.suffix.lower() not in reglages_service.SUPPORTED_EXTENSIONS
    ]


def _decrire(fichier: Path, base: Path, raison: str) -> dict:
    from . import config as reglages_service

    return {
        "chemin": str(fichier.relative_to(base)),
        "nom": fichier.name,
        "dossier": False,
        "raison": raison,
        "contient": None,
        "taille_octets": fichier.stat().st_size,
        "date": _date(fichier),
        # Le ranger n'a de sens que si le serveur sait le traiter : proposer
        # l'action sur un fichier qu'il ignorera reviendrait à le cacher ailleurs.
        "traitable": fichier.suffix.lower() in reglages_service.SUPPORTED_EXTENSIONS,
    }


def _date(chemin_cible: Path) -> Optional[str]:
    try:
        from datetime import datetime
        return datetime.fromtimestamp(chemin_cible.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


def chemin_sous_la_racine(relatif: str) -> Path:
    """
    Chemin absolu d'une entrée du dépôt, refusé s'il sort de l'arborescence.

    Ce contrôle n'est pas une formalité : le chemin vient de l'interface, et
    « ../../etc » y arriverait aussi bien qu'un nom de fichier.
    """
    base = racine().resolve()
    cible = (base / relatif).resolve()
    if cible != base and base not in cible.parents:
        raise DepotRefuse("Ce chemin ne fait pas partie du dépôt.")
    return cible


def dossiers_declares(session: Session) -> set:
    """Les dossiers qu'un type réclame — tout le reste est un emplacement non valide."""
    return {c.dossier_depot for c in session.query(Categorie) if c.dossier_depot}


def type_du_chemin(session: Session, fichier: Path) -> Optional[Categorie]:
    """
    Le type de document qui possède le dossier où se trouve ce fichier.

    `None` pour un fichier à la racine ou dans un dossier que personne ne
    réclame : c'est le cas que le §19.3 traitera comme « à classer ».
    """
    try:
        relatif = fichier.resolve().relative_to(racine().resolve())
    except (ValueError, OSError):
        return None
    if len(relatif.parts) < 2:
        return None      # à la racine : aucun type ne le revendique
    return session.query(Categorie).filter_by(dossier_depot=relatif.parts[0]).first()
