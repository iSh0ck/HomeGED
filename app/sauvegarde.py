"""
Copie de secours de l'installation (§22.49).

L'application détient **l'unique exemplaire** des papiers du foyer : la base dit
comment ils sont rangés, `storage/` contient les PDF eux-mêmes. Le README
indiquait quoi copier ; personne ne le faisait, et rien ne le rappelait. C'est le
seul défaut de ce projet qui puisse coûter des années de documents.

Trois principes, et ils expliquent toutes les décisions de ce module :

  * **rien ne se déclenche sans qu'on l'ait demandé.** La sauvegarde est éteinte
    par défaut : remplir le disque de quelqu'un sans son accord serait une
    mauvaise façon de le protéger. Tout se règle depuis l'administration — le
    rythme, la destination, le nombre gardé, ce qu'on y met ;
  * **une sauvegarde qu'on ne peut pas relire n'en est pas une.** Le format est
    un simple dossier daté contenant un `mysqldump` en clair et une copie des
    archives : cela se restaure avec `mysql <` et `cp -r`, sans l'application,
    sans ce code, dans dix ans ;
  * **une sauvegarde silencieuse qui a cessé est pire que pas de sauvegarde** :
    on s'y fie. L'état est donc lisible depuis l'administration, avec la date de
    la dernière réussite et un avertissement passé le délai réglé.

Ce module n'est **pas** l'export d'archive (§17.30). Celui-là sort tout une fois,
sous mot de passe, pour quitter la GED ; celui-ci tourne en fond pour y revenir.

**Le chiffrement est facultatif** (§22.65). Une sauvegarde part souvent ailleurs
— un disque externe qu'on range dans un tiroir, un partage réseau, un disque
qu'on revendra un jour — et elle contient l'intégralité des papiers du foyer en
clair. Un mot de passe réglé dans l'administration fait produire, à la place du
dossier, un fichier unique chiffré en AES-256.

Le deuxième principe tient quand même : `openssl` est un outil standard, présent
partout, et la commande exacte pour déchiffrer est écrite en clair à côté de
l'archive. Rien de propre à ce code n'est nécessaire pour la relire.
"""
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config

log = logging.getLogger(__name__)

# Le nom dit la date et rien d'autre : c'est ce qu'on lit dans un `ls`.
FORMAT_NOM = "%Y-%m-%d_%Hh%M"
NOM_BASE = "base.sql"
NOM_ARCHIVES = "storage"
NOM_MARQUE = "sauvegarde.txt"
# Une sauvegarde chiffrée n'est plus un dossier mais deux fichiers côte à côte :
# l'archive, et la marque en clair qui dit comment la relire.
SUFFIXE_CHIFFRE = ".tar.gz.enc"
DELAI_CHIFFREMENT = 3600  # secondes ; au-delà, quelque chose ne va pas
DELAI_DUMP = 900          # secondes ; au-delà, la base est pathologique


class SauvegardeImpossible(Exception):
    """Échec rendu à l'appelant : il décide s'il alerte ou s'il retente."""


def dossier_racine(chemin: Optional[str] = None) -> Path:
    return Path(chemin or "/data/sauvegardes")


def _dump_base(destination: Path) -> int:
    """
    Écrit la base en SQL. `mariadb-dump` plutôt qu'une copie des fichiers : une
    copie à chaud d'InnoDB donne un état incohérent, et ne se relit qu'avec la
    même version du serveur.
    """
    commande = [
        "mariadb-dump", f"--host={config.DB_HOST}", f"--user={config.DB_USER}",
        f"--password={config.DB_PASSWORD}",
        # Une seule transaction : la base reste utilisable pendant la copie, et
        # l'instantané est cohérent. Sans cela, un dépôt en cours donnerait un
        # document sans ses métadonnées.
        "--single-transaction", "--quick",
        # **Ni routines ni événements** : HomeGED n'en déclare aucun, et les
        # demander oblige `mariadb-dump` à lire `mysql.proc` — table système que
        # le serveur refuse quand elle date d'une version antérieure et que
        # `mariadb-upgrade` n'a pas été passé. Ne pas réclamer ce qu'on n'a pas
        # évite de faire dépendre la sauvegarde du foyer d'un détail
        # d'administration du serveur.
        "--default-character-set=utf8mb4", config.DB_NAME,
    ]
    with open(destination, "wb") as sortie:
        termine = subprocess.run(commande, stdout=sortie, stderr=subprocess.PIPE,
                                 timeout=DELAI_DUMP)
    if termine.returncode != 0:
        destination.unlink(missing_ok=True)
        raise SauvegardeImpossible(
            (termine.stderr or b"").decode(errors="replace").strip()[:300]
            or "mariadb-dump a échoué sans message")
    return destination.stat().st_size


def _copier_archives(destination: Path) -> tuple[int, int]:
    """
    Copie `storage/` à côté du dump. La corbeille en est écartée : ce sont des
    fichiers que plus aucun document ne réclame, et les sauvegarder reviendrait à
    conserver ce qu'on a décidé de jeter.
    """
    source = Path(config.STORAGE_FOLDER)
    if not source.is_dir():
        return 0, 0
    fichiers = octets = 0
    for chemin in source.rglob("*"):
        if not chemin.is_file() or ".corbeille" in chemin.parts:
            continue
        cible = destination / chemin.relative_to(source)
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chemin, cible)
        fichiers += 1
        octets += cible.stat().st_size
    return fichiers, octets


def _chiffrer(source: Path, destination: Path, mot_de_passe: str) -> int:
    """
    Réduit le dossier de sauvegarde à un seul fichier chiffré (§22.65).

    `openssl enc -aes-256-cbc -pbkdf2` plutôt qu'une bibliothèque Python : c'est
    la commande qu'on retrouvera dans dix ans sur n'importe quelle machine, et
    c'est elle qu'on écrit dans la marque. Le mot de passe passe par un
    descripteur de fichier et non par la ligne de commande — `ps` la montre à
    quiconque est sur la machine.
    """
    lecture, ecriture = os.pipe()
    try:
        os.write(ecriture, (mot_de_passe + "\n").encode())
    finally:
        os.close(ecriture)

    tar = subprocess.Popen(
        ["tar", "-czf", "-", "-C", str(source.parent), source.name],
        stdout=subprocess.PIPE)
    try:
        with open(destination, "wb") as sortie:
            chiffrement = subprocess.run(
                ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
                 "-pass", f"fd:{lecture}"],
                stdin=tar.stdout, stdout=sortie, stderr=subprocess.PIPE,
                pass_fds=(lecture,), timeout=DELAI_CHIFFREMENT)
    finally:
        os.close(lecture)
        if tar.stdout:
            tar.stdout.close()
        tar.wait(timeout=DELAI_CHIFFREMENT)

    if tar.returncode != 0 or chiffrement.returncode != 0:
        destination.unlink(missing_ok=True)
        raise SauvegardeImpossible(
            "Le chiffrement de la sauvegarde a échoué : "
            + (chiffrement.stderr.decode(errors="replace").strip() or "tar a échoué"))
    return destination.stat().st_size


def executer(dossier: Optional[str] = None, avec_archives: bool = True,
             mot_de_passe: Optional[str] = None) -> dict:
    """
    Fait une sauvegarde et rend son bilan. Lève `SauvegardeImpossible` si elle
    n'a pas abouti — un demi-succès n'existe pas ici : le dossier incomplet est
    effacé plutôt que laissé en place, où il ferait croire à une copie valable.
    """
    racine = dossier_racine(dossier)
    racine.mkdir(parents=True, exist_ok=True)
    debut = time.monotonic()
    # Le nom se lit à la minute : deux sauvegardes rapprochées se disputeraient
    # le même. On regarde aussi l'archive chiffrée (§22.65) — le dossier, lui,
    # ne survit pas au chiffrement, et sa seule absence laissait la seconde
    # écraser la première en silence.
    def occupe(nom: str) -> bool:
        return (racine / nom).exists() or (racine / f"{nom}{SUFFIXE_CHIFFRE}").exists()

    nom = datetime.now().strftime(FORMAT_NOM)
    if occupe(nom):
        nom = f"{nom}-{int(time.time()) % 1000}"
    cible = racine / nom
    cible.mkdir(parents=True)

    try:
        octets_base = _dump_base(cible / NOM_BASE)
        fichiers, octets_archives = (
            _copier_archives(cible / NOM_ARCHIVES) if avec_archives else (0, 0))
    except Exception as erreur:
        shutil.rmtree(cible, ignore_errors=True)
        raise SauvegardeImpossible(str(erreur)) from erreur

    duree = int((time.monotonic() - debut) * 1000)
    bilan = {"dossier": str(cible), "date": datetime.now().isoformat(timespec="seconds"),
             "octets_base": octets_base, "fichiers_archives": fichiers,
             "octets_archives": octets_archives, "duree_ms": duree,
             "avec_archives": bool(avec_archives)}
    # La marque est écrite en dernier : un dossier sans elle est une sauvegarde
    # interrompue, et c'est ainsi qu'on les reconnaît sans rien interroger.
    (cible / NOM_MARQUE).write_text(
        "Sauvegarde HomeGED\n"
        f"faite le : {bilan['date']}\n"
        f"base : {NOM_BASE} ({octets_base} octets)\n"
        f"archives : {'oui' if avec_archives else 'non'} "
        f"({fichiers} fichier(s), {octets_archives} octets)\n"
        f"durée : {duree} ms\n\n"
        "Pour restaurer :\n"
        f"  mariadb -u<compte> -p <base> < {NOM_BASE}\n"
        f"  cp -r {NOM_ARCHIVES}/* /data/storage/\n",
        encoding="utf-8")

    if mot_de_passe:
        # Le dossier disparaît au profit d'un fichier unique : le laisser à côté
        # rendrait le chiffrement inutile.
        archive = racine / f"{cible.name}{SUFFIXE_CHIFFRE}"
        try:
            octets_chiffres = _chiffrer(cible, archive, mot_de_passe)
        except Exception as erreur:
            shutil.rmtree(cible, ignore_errors=True)
            archive.unlink(missing_ok=True)
            raise SauvegardeImpossible(str(erreur)) from erreur
        shutil.rmtree(cible, ignore_errors=True)
        # La marque reste **en clair** à côté : une archive dont on a oublié
        # comment la lire ne vaut rien, et elle ne révèle que sa propre date.
        (racine / f"{cible.name}{SUFFIXE_CHIFFRE}.txt").write_text(
            "Sauvegarde HomeGED chiffrée\n"
            f"faite le : {bilan['date']}\n"
            f"taille : {octets_chiffres} octets\n\n"
            "Pour la relire, avec le mot de passe réglé dans l'administration :\n"
            f"  openssl enc -d -aes-256-cbc -pbkdf2 -in {archive.name} | tar -xzf -\n\n"
            "Puis, dans le dossier obtenu :\n"
            f"  mariadb -u<compte> -p <base> < {NOM_BASE}\n"
            f"  cp -r {NOM_ARCHIVES}/* /data/storage/\n",
            encoding="utf-8")
        bilan.update({"dossier": str(archive), "chiffree": True,
                      "octets_chiffres": octets_chiffres})
    else:
        bilan["chiffree"] = False
    return bilan


def lister(dossier: Optional[str] = None) -> list[dict]:
    """Les sauvegardes présentes, la plus récente d'abord."""
    racine = dossier_racine(dossier)
    if not racine.is_dir():
        return []
    trouvees = []
    for chemin in racine.iterdir():
        # Une sauvegarde chiffrée est un fichier, pas un dossier (§22.65). Sa
        # marque, elle, reste en clair à côté : c'est elle qui atteste qu'elle
        # est allée au bout.
        if chemin.is_file() and chemin.name.endswith(SUFFIXE_CHIFFRE):
            trouvees.append({
                "nom": chemin.name[:-len(SUFFIXE_CHIFFRE)],
                "chemin": str(chemin),
                "date": datetime.fromtimestamp(chemin.stat().st_mtime).isoformat(timespec="seconds"),
                "octets": chemin.stat().st_size,
                "complete": Path(f"{chemin}.txt").is_file(),
                "chiffree": True,
            })
            continue
        if not chemin.is_dir():
            continue
        marque = chemin / NOM_MARQUE
        taille = sum(f.stat().st_size for f in chemin.rglob("*") if f.is_file())
        trouvees.append({
            "nom": chemin.name,
            "chemin": str(chemin),
            "date": datetime.fromtimestamp(chemin.stat().st_mtime).isoformat(timespec="seconds"),
            "octets": taille,
            # Sans la marque finale, la sauvegarde a été interrompue : elle ne
            # doit pas être comptée comme valable.
            "complete": marque.is_file(),
            "chiffree": False,
        })
    return sorted(trouvees, key=lambda s: s["nom"], reverse=True)


def purger(dossier: Optional[str] = None, garder: int = 7) -> int:
    """Efface les plus anciennes au-delà du nombre voulu."""
    completes = [s for s in lister(dossier) if s["complete"]]
    a_effacer = completes[max(1, garder):] + [s for s in lister(dossier) if not s["complete"]][1:]
    efface = 0
    for sauvegarde in a_effacer:
        try:
            _effacer(Path(sauvegarde["chemin"]))
            efface += 1
        except OSError:
            log.warning("Sauvegarde %s non effacée", sauvegarde["chemin"])
    return efface


def _effacer(chemin: Path) -> None:
    """Efface une sauvegarde, dossier ou archive chiffrée avec sa marque."""
    if chemin.is_dir():
        shutil.rmtree(chemin)
        return
    chemin.unlink(missing_ok=True)
    Path(f"{chemin}.txt").unlink(missing_ok=True)


def etat(dossier: Optional[str] = None, alerte_jours: int = 3) -> dict:
    """
    Ce que l'administration affiche : la dernière réussite, et si elle est
    trop vieille. Une sauvegarde qui a cessé sans que personne ne le sache est
    pire que pas de sauvegarde — on s'y fie.
    """
    sauvegardes = [s for s in lister(dossier) if s["complete"]]
    derniere = sauvegardes[0] if sauvegardes else None
    retard = None
    if derniere:
        age = (datetime.now() - datetime.fromisoformat(derniere["date"])).total_seconds()
        retard = age > alerte_jours * 86400
    return {
        "derniere": derniere,
        "nombre": len(sauvegardes),
        "octets_total": sum(s["octets"] for s in sauvegardes),
        "espace_libre": shutil.disk_usage(dossier_racine(dossier)).free
        if dossier_racine(dossier).is_dir() else None,
        "en_retard": retard,
        "jamais_faite": derniere is None,
    }
