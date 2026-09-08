"""
Supervision : ce que la machine a dans le ventre (§18.18).

Un tableau de bord d'exploitation, en lecture seule. Il répond à trois questions
qu'on se pose toujours trop tard : **reste-t-il de la place**, **la machine
tient-elle la charge**, et **le traitement des documents suit-il** ?

Mesuré sans accès au démon Docker, et c'est délibéré : monter
`/var/run/docker.sock` dans l'API donnerait à celle-ci le pouvoir de créer un
conteneur privilégié, c'est-à-dire l'équivalent de root sur l'hôte — un prix
déraisonnable pour afficher des pourcentages. On lit donc ce que le noyau expose
déjà :

* `/proc/meminfo` et `/proc/stat` décrivent **l'hôte entier** vu depuis le
  conteneur, ce qui donne bien la charge globale de la machine ;
* les fichiers cgroup v2 décrivent **ce conteneur-ci** ;
* le reste vient de la base et du disque.

La conséquence à connaître : le détail par conteneur (worker, base, nginx)
n'est pas accessible. Ce qui les concerne est donc mesuré autrement — file de
travaux pour le worker, taille des tables pour la base.
"""
import os
import shutil
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import config
from .db import Document, Job, JournalAudit, SessionOuverte, Utilisateur

# Dernier relevé du compteur CPU de l'hôte : un pourcentage d'utilisation n'a de
# sens qu'entre deux instants, jamais dans l'absolu.
_dernier_cpu: Optional[tuple] = None


def _lire_proc(chemin: str) -> str:
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            return fichier.read()
    except OSError:
        return ""


def _memoire_hote() -> dict:
    """Mémoire de la machine. `MemAvailable` plutôt que `MemFree` : le cache
    disque est de la mémoire réutilisable, la compter comme occupée ferait
    paraître saturée une machine qui respire."""
    valeurs = {}
    for ligne in _lire_proc("/proc/meminfo").splitlines():
        cle, _, reste = ligne.partition(":")
        morceaux = reste.split()
        if morceaux and morceaux[0].isdigit():
            valeurs[cle] = int(morceaux[0]) * 1024
    total = valeurs.get("MemTotal")
    disponible = valeurs.get("MemAvailable", valeurs.get("MemFree"))
    if not total or disponible is None:
        return {}
    return {
        "total": total,
        "disponible": disponible,
        "utilisee": total - disponible,
        "pourcentage": round((total - disponible) / total * 100, 1),
    }


def _cpu_hote() -> dict:
    """
    Part du temps CPU passée à travailler depuis le relevé précédent.

    Au tout premier appel, aucune comparaison n'est possible : on prend deux
    relevés espacés d'un dixième de seconde plutôt que de rendre une valeur
    fausse ou vide.
    """
    global _dernier_cpu

    def relever():
        ligne = _lire_proc("/proc/stat").splitlines()
        if not ligne or not ligne[0].startswith("cpu "):
            return None
        champs = [int(v) for v in ligne[0].split()[1:]]
        total = sum(champs)
        oisif = champs[3] + (champs[4] if len(champs) > 4 else 0)
        return total, oisif

    courant = relever()
    if not courant:
        return {}
    if not _dernier_cpu:
        time.sleep(0.1)
        precedent, courant = courant, relever()
        if not courant:
            return {}
    else:
        precedent = _dernier_cpu
    _dernier_cpu = courant

    delta_total = courant[0] - precedent[0]
    delta_oisif = courant[1] - precedent[1]
    if delta_total <= 0:
        return {}
    charge = _lire_proc("/proc/loadavg").split()
    return {
        "pourcentage": round(max(0.0, (delta_total - delta_oisif) / delta_total * 100), 1),
        "coeurs": os.cpu_count(),
        "charge": [float(c) for c in charge[:3]] if len(charge) >= 3 else None,
    }


def _memoire_conteneur() -> dict:
    """Mémoire de l'API elle-même (cgroup v2). `max` vaut « max » sans limite."""
    courante = _lire_proc("/sys/fs/cgroup/memory.current").strip()
    limite = _lire_proc("/sys/fs/cgroup/memory.max").strip()
    if not courante.isdigit():
        return {}
    resultat = {"utilisee": int(courante)}
    if limite.isdigit():
        resultat["limite"] = int(limite)
        resultat["pourcentage"] = round(int(courante) / int(limite) * 100, 1)
    return resultat


def _disque(chemin: str) -> dict:
    try:
        usage = shutil.disk_usage(chemin)
    except OSError:
        return {}
    return {
        "total": usage.total,
        "utilise": usage.used,
        "libre": usage.free,
        "pourcentage": round(usage.used / usage.total * 100, 1) if usage.total else None,
    }


def _poids_dossier(chemin: str) -> Optional[int]:
    """Poids d'un dossier. Les liens ne sont pas suivis : un lien vers l'extérieur
    gonflerait un total qui n'a plus alors aucun sens."""
    if not os.path.isdir(chemin):
        return None
    total = 0
    for racine, _, fichiers in os.walk(chemin):
        for nom in fichiers:
            chemin_fichier = os.path.join(racine, nom)
            try:
                if not os.path.islink(chemin_fichier):
                    total += os.path.getsize(chemin_fichier)
            except OSError:
                continue
    return total


def _base(session: Session) -> dict:
    """Poids de la base, et ses cinq plus grosses tables."""
    try:
        lignes = session.execute(text(
            "SELECT table_name AS nom, "
            "       COALESCE(data_length, 0) + COALESCE(index_length, 0) AS octets, "
            "       COALESCE(table_rows, 0) AS lignes "
            "  FROM information_schema.tables "
            " WHERE table_schema = DATABASE() "
            " ORDER BY octets DESC"
        )).mappings().all()
    except Exception:
        return {}
    return {
        "octets": sum(int(l["octets"]) for l in lignes),
        "tables": [
            {"nom": l["nom"], "octets": int(l["octets"]), "lignes": int(l["lignes"])}
            for l in lignes[:5]
        ],
    }


def _travaux(session: Session) -> dict:
    """
    État du serveur de travaux, vu depuis la base : c'est la seule façon d'en
    dire quelque chose sans accès à son conteneur — et c'est de toute façon ce
    qui compte, un worker en bonne santé dont la file s'allonge est un problème.
    """
    par_statut = dict(session.query(Job.statut, func.count(Job.id)).group_by(Job.statut).all())
    dernier = session.query(func.max(Job.date_fin)).scalar()
    return {
        "par_statut": {str(k): int(v) for k, v in par_statut.items()},
        "en_attente": int(par_statut.get("en_attente", 0)),
        "en_erreur": int(par_statut.get("erreur", 0)),
        "dernier_traitement": dernier.isoformat() if dernier else None,
    }


def _documents(session: Session) -> dict:
    total = session.query(func.count(Document.id)).scalar() or 0
    poids = session.query(func.coalesce(func.sum(Document.taille_octets), 0)).scalar() or 0
    depuis = datetime.now() - timedelta(days=30)
    return {
        "total": int(total),
        "octets": int(poids),
        "sans_categorie": int(session.query(func.count(Document.id))
                              .filter(Document.categorie_id.is_(None)).scalar() or 0),
        "recents": int(session.query(func.count(Document.id))
                       .filter(Document.date_import >= depuis).scalar() or 0),
        "a_comprimer": int(session.query(func.count(Document.id))
                           .filter(Document.date_compression.is_(None)).scalar() or 0),
    }


def _activite(session: Session) -> dict:
    ouvertes = session.query(func.count(SessionOuverte.id)).filter(
        SessionOuverte.date_revocation.is_(None),
        SessionOuverte.date_expiration > datetime.now(),
    ).scalar() or 0
    return {
        "sessions_ouvertes": int(ouvertes),
        "comptes_actifs": int(session.query(func.count(Utilisateur.id))
                              .filter(Utilisateur.actif.is_(True)).scalar() or 0),
        "evenements_journal": int(session.query(func.count(JournalAudit.id)).scalar() or 0),
    }


def _depuis_quand() -> Optional[float]:
    """Depuis combien de temps ce processus tourne, en secondes."""
    try:
        return time.time() - os.path.getmtime("/proc/self")
    except OSError:
        return None


def etat(session: Session) -> dict:
    """Relevé complet, tel que l'écran de supervision l'affiche."""
    import platform

    version_base = None
    try:
        version_base = session.execute(text("SELECT VERSION()")).scalar()
    except Exception:
        pass

    return {
        "instant": datetime.now().isoformat(),
        "machine": {
            "memoire": _memoire_hote(),
            "cpu": _cpu_hote(),
            "uptime_secondes": _depuis_quand(),
        },
        "api": {
            "memoire": _memoire_conteneur(),
            "python": platform.python_version(),
        },
        "disques": {
            "archives": {**_disque(config.STORAGE_FOLDER),
                         "chemin": config.STORAGE_FOLDER,
                         "poids": _poids_dossier(config.STORAGE_FOLDER)},
            "exports": {**_disque(config.EXPORT_FOLDER),
                        "chemin": config.EXPORT_FOLDER,
                        "poids": _poids_dossier(config.EXPORT_FOLDER)},
        },
        "base": {**_base(session), "version": version_base},
        "documents": _documents(session),
        "travaux": _travaux(session),
        "activite": _activite(session),
    }
