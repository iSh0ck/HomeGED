"""
Serveur de travaux : surveille en continu OCR_WAIT_FOLDER et traite chaque
nouveau fichier déposé par le scanner :
  1. calcul du hash (anti-doublon)
  2. OCR -> PDF cherchable
  3. extraction du texte
  4. enregistrement en base (documents)
  5. application des règles regex -> remplissage auto des métadonnées
  6. déplacement du fichier vers le stockage définitif

Lancement : python -m app.worker
"""
import json
import hashlib
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import Optional
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from . import apercus
from . import audit
from . import compression
from . import automatisations
from . import courriel
from . import echeances
from . import integrite
from . import versions, conformite, config, depots, pieces, references_auto
from sqlalchemy import func

from .db import (SessionLocal, Categorie, Document, Job, PieceDocument, SessionOuverte,
                 VerrouDocument, attendre_base)
from .migrations import appliquer_migrations
from .ocr import ocr_to_searchable_pdf, extraire_texte
from .regex_engine import appliquer_regles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
log = logging.getLogger(__name__)

# Purge des fichiers de `storage/` que plus aucun document ne référence.
INTERVALLE_PURGE = float(os.getenv("INTERVALLE_PURGE", "300"))       # toutes les 5 min
INTERVALLE_REJEU = float(os.getenv("INTERVALLE_REJEU", "5"))          # relève des demandes de rejeu

# La rétention du suivi se règle depuis l'administration (§19.11), comme celles
# du journal et de la corbeille : un foyer n'a pas à éditer un fichier `.env` et
# à redémarrer un conteneur pour changer un nombre de jours.
# Ce qu'une purge peut emporter : des travaux qui n'ont plus rien à raconter.
# « a_classer » n'en est pas — comme « bloque » et « erreur », il appelle une
# action, et le purger ferait disparaître un fichier que personne n'a classé.
STATUTS_PURGEABLES = ("termine", "ignore")

# Étapes du traitement, dans l'ordre. Un rejeu peut repartir de n'importe
# laquelle : reprendre à « regles » réapplique les expressions régulières sur le
# texte déjà océrisé (immédiat), là où « ocr » refait tout le travail coûteux.
ETAPE_EMPREINTE = "empreinte"
ETAPE_OCR = "ocr"
ETAPE_EXTRACTION = "extraction"
ETAPE_INDEXATION = "indexation"
ETAPE_REGLES = "regles"
ETAPE_CONFORMITE = "conformite"
ETAPES = (ETAPE_EMPREINTE, ETAPE_OCR, ETAPE_EXTRACTION, ETAPE_INDEXATION,
          ETAPE_REGLES, ETAPE_CONFORMITE)
DELAI_GRACE_PURGE = float(os.getenv("DELAI_GRACE_PURGE", "300"))     # épargne les fichiers récents


def _attendre_fichier_stable(path: Path, essais: int = 30, delai: float = 1.0) -> bool:
    """
    Attend que la taille du fichier cesse de changer avant de le traiter.
    Un scanner qui dépose un gros PDF l'écrit progressivement : sans cette
    attente, l'OCR démarre sur un fichier tronqué et le document est indexé
    incomplet (ou l'OCR échoue). Renvoie False si le fichier n'est jamais
    stabilisé ou a disparu.
    """
    taille_precedente = -1
    for _ in range(essais):
        if not path.exists():
            return False
        taille = path.stat().st_size
        if taille == taille_precedente and taille > 0:
            return True
        taille_precedente = taille
        time.sleep(delai)
    log.warning(f"Fichier toujours en cours d'écriture après {essais * delai:.0f}s : {path.name}")
    return False


def dossier_du_travail(job_id: int) -> Path:
    """Où vit le fichier d'origine d'un travail : un dossier par travail."""
    return Path(config.TRAVAUX_FOLDER) / str(job_id)


def _origine_du_depot(path: Path) -> bool | None:
    """
    `True` déposé à la main, `False` venu du dossier surveillé, `None` inconnu
    (§22.72).

    Seul le chemin **en cours de traitement** répond : l'API pose ce qu'on lui
    glisse dans son dossier de dépôts, le dossier surveillé apporte le reste. Un
    rejeu, lui, repart du fichier rangé à côté du travail — il ne dit plus rien
    de l'origine, et l'on préfère alors se taire.
    """
    for dossier, manuel in ((config.DEPOTS_MANUELS_FOLDER, True),
                            (config.OCR_WAIT_FOLDER, False)):
        try:
            if Path(path).resolve().is_relative_to(Path(dossier).resolve()):
                return manuel
        except OSError:
            continue
    return None


def _conserver_original(job_id: int, path: Path) -> str | None:
    """
    Range le fichier reçu à côté de son travail, et l'y laisse tant que le
    travail existe (§18.53).

    Il était jusqu'ici supprimé dès que le traitement réussissait, et seuls les
    échecs étaient mis de côté dans `watch/erreurs/`. Deux conséquences :

    * **le fichier reçu n'existait plus nulle part.** Le PDF archivé n'en est pas
      une copie : l'océrisation lui ajoute une couche de texte, la compression le
      réécrit. Ce qui a été déposé était donc perdu dès le premier succès ;
    * **rejouer un travail n'était possible qu'en cas d'échec**, puisque c'était
      le seul cas où un fichier subsistait.

    Le fichier suit maintenant son travail : il disparaît avec lui, à la purge.
    Et le dossier `erreurs/` disparaît du dossier de dépôt — ce qui devient une
    nécessité avec la phase 19, où ce dossier n'appartient qu'à la GED.
    """
    try:
        dossier = dossier_du_travail(job_id)
        if path.parent == dossier:
            return str(path)          # déjà conservé : un rejeu ne le déplace pas
        dossier.mkdir(parents=True, exist_ok=True)
        destination = dossier / path.name
        if destination.exists():
            destination = dossier / f"{path.stem}_{int(time.time())}{path.suffix}"
        shutil.move(str(path), str(destination))
        return str(destination)
    except Exception:
        log.exception(f"Impossible de conserver le fichier d'origine de {path.name}")
        return None


def _effacer_originaux(job_ids) -> int:
    """Efface les fichiers conservés de travaux qui n'existent plus."""
    efface = 0
    for job_id in job_ids:
        dossier = dossier_du_travail(job_id)
        try:
            if dossier.is_dir():
                shutil.rmtree(dossier)
                efface += 1
        except Exception:
            log.exception(f"Impossible d'effacer les fichiers du travail {job_id}")
    return efface


def _etape_extraction(document: Document) -> None:
    """Relit le texte du PDF archivé. Utile sans refaire l'OCR (couche texte déjà posée)."""
    document.texte_ocr = extraire_texte(document.chemin_stockage)


def _etape_regles(session, document: Document) -> None:
    """
    Réapplique les règles d'identification et d'extraction sur le texte du
    document, puis rattache ce qui peut l'être aux tables du foyer (§17.18) —
    le titulaire d'une facture, le véhicule d'un contrôle technique, dès lors
    que le document les nomme.
    """
    appliquer_regles(document, session)
    session.flush()          # les métadonnées des règles doivent être visibles ici
    rattaches = references_auto.remplir(session, document)
    if rattaches:
        log.info(f"{document.nom_fichier} : rattaché à "
                 + ", ".join(f"{cle} = {libelle}" for cle, libelle in rattaches.items()))


def _etape_conformite(session, document: Document) -> list[dict]:
    """
    Contrôle les champs exigés par la catégorie et positionne le statut du
    document. Un document auquel il manque un champ obligatoire n'est pas
    « correctement traité » (§16) : il passe en `incomplet`.
    """
    # `ranger` relit les métadonnées depuis la base, calcule ce qui manque et
    # **écrit la réponse sur le document** (§22.41) : c'est ici qu'elle est vraie
    # pour la première fois, et le registre la lira sans la recalculer.
    manquants = conformite.ranger(session, document)
    document.statut = "incomplet" if manquants else "traite"
    return manquants


def _reocr_sur_place(document: Document) -> None:
    """
    Réocérise le PDF déjà archivé. ocrmypdf refusant d'écrire sur son propre
    fichier d'entrée, on passe par un fichier temporaire que l'on met en place
    une fois l'opération réussie — le document reste consultable en cas d'échec.
    """
    source = Path(document.chemin_stockage)
    if not source.exists():
        raise FileNotFoundError(f"PDF archivé introuvable : {source}")
    temporaire = source.with_name(f"{source.stem}.reocr{source.suffix}")
    try:
        ocr_to_searchable_pdf(str(source), str(temporaire), **reglages_traitement())
        shutil.move(str(temporaire), str(source))
    finally:
        if temporaire.exists():
            temporaire.unlink(missing_ok=True)


def _ouvrir_job(session, path: Path, job_id: int | None) -> Job:
    """
    Ouvre (ou rouvre) le travail correspondant à un fichier. Un rejeu réutilise
    le travail d'origine et incrémente son compteur de tentatives, pour que
    l'historique d'un fichier reste sur une seule ligne.

    Le travail est rechargé depuis son identifiant, et non repris tel quel : il
    provient d'une session déjà refermée, l'objet y serait détaché.
    """
    job = session.get(Job, job_id) if job_id else None
    if job is None:
        # Le fichier qu'un travail réclame déjà lui revient : c'est le cas d'un
        # classement à la main (§19.4), où le fichier réapparaît dans le dossier
        # de dépôt de son type. En ouvrir un second raconterait deux fois la même
        # histoire, et laisserait le premier sans fin.
        job = (session.query(Job)
               .filter(Job.chemin_source == str(path),
                       Job.statut.in_(("a_classer", "en_attente")))
               .order_by(Job.id.desc()).first())
    if job is None:
        job = Job(nom_fichier=path.name)
        session.add(job)
    job.chemin_source = str(path)
    job.statut = "en_cours"
    job.tentatives = (job.tentatives or 0) + 1
    job.message_erreur = None
    job.diagnostic = None
    job.rejouer_demande = False
    job.date_debut = datetime.now()
    job.date_fin = None
    session.commit()
    return job


def _palier_atteint(session, compteur: Optional[int]) -> bool:
    """
    Le compteur a-t-il atteint le palier réglé (§21.15) ?

    0 veut dire « on n'abandonne jamais » : c'était le comportement d'avant, et
    il reste disponible pour qui préfère qu'un travail réessaie sans fin.
    """
    from . import reglages

    try:
        palier = reglages.entier(session, "travaux_tentatives_max")
    except Exception:
        palier = 5
    return palier > 0 and (compteur or 0) >= palier


def _cloturer_job(session, job: Job, statut: str, document_id: int | None = None,
                  message: str | None = None, diagnostic: str | None = None,
                  chemin_source: str | None = None) -> None:
    """Termine un travail dans l'état indiqué. Ne doit jamais faire échouer le traitement."""
    try:
        job.statut = statut
        job.document_id = document_id
        job.message_erreur = message
        job.diagnostic = diagnostic
        job.date_fin = datetime.now()
        if chemin_source is not None:
            job.chemin_source = chemin_source
        session.commit()
    except Exception:
        session.rollback()
        log.exception(f"Impossible d'enregistrer l'état « {statut} » du travail {job.id}")


def traiter_depots_manuels() -> int:
    """
    Reprend ce que l'on a glissé à la main dans une fiche simple (§22.1).

    Ces fichiers n'entrent pas par `ocr_wait` : l'API les pose dans son dossier
    et crée le travail avec **le type déjà connu** — il a été dit au dépôt, pas
    déduit d'un dossier. Le traitement est ensuite le même que pour tout le
    reste : archivage, océrisation, règles du type. C'est ce qui fait qu'un
    document déposé à la main se cherche et se lit comme les autres.
    """
    session = SessionLocal()
    try:
        racine = Path(config.DEPOTS_MANUELS_FOLDER).resolve()
        attente = (session.query(Job)
                   .filter(Job.statut == "en_attente", Job.chemin_source.isnot(None))
                   .order_by(Job.id).limit(20).all())
        a_traiter = []
        for job in attente:
            try:
                chemin = Path(job.chemin_source).resolve()
            except OSError:
                continue
            if chemin.is_relative_to(racine) and chemin.is_file():
                a_traiter.append((job.id, chemin))
    except Exception:
        log.exception("Relève des dépôts manuels impossible")
        return 0
    finally:
        session.close()

    def reprendre(job_id: int, chemin: Path) -> None:
        log.info("Dépôt manuel repris : %s (travail %s)", chemin.name, job_id)
        traiter_fichier(chemin, job_id=job_id)
        # Le fichier a été archivé : son dossier de dépôt n'a plus de raison
        # d'être. Il ne disparaît que vide — un échec de traitement laisse le
        # fichier en place, et l'on retentera au prochain passage.
        try:
            if chemin.parent != racine and not any(chemin.parent.iterdir()):
                chemin.parent.rmdir()
        except OSError:
            log.debug("Dossier de dépôt %s non retiré", chemin.parent)

    for job_id, chemin in a_traiter:
        confier(reprendre, job_id, chemin)
    return len(a_traiter)


def construire_exports_modele() -> int:
    """
    Construit les archives demandées par l'écran d'export par modèle (§21.13).

    L'API pose la demande, le serveur de travaux écrit : cinq cents PDF à copier
    et compresser tiennent une connexion ouverte plusieurs minutes, et l'API n'a
    pas les archives en écriture.

    Les droits du **demandeur** sont réappliqués ici, et non ceux du serveur : une
    demande posée hier ne doit pas sortir aujourd'hui ce que son auteur a cessé
    de pouvoir voir.
    """
    from . import droits as module_droits, export_modele
    from .db import ExportModele, Utilisateur

    session = SessionLocal()
    faits = 0
    try:
        demandes = (session.query(ExportModele)
                    .filter(ExportModele.statut == "en_attente")
                    .order_by(ExportModele.id).limit(3).all())
        for demande in demandes:
            demande.statut = "en_cours"
            session.commit()
            try:
                demandeur = (session.get(Utilisateur, demande.utilisateur_id)
                             if demande.utilisateur_id else None)
                if demandeur is None:
                    raise RuntimeError("Le compte qui a demandé cette archive n'existe plus.")

                base = module_droits.filtrer_documents(
                    session.query(Document), session, demandeur, module_droits.TELECHARGER)
                criteres = json.loads(demande.criteres) if demande.criteres else []
                documents = export_modele.documents_de(
                    session, criteres, demande.categorie_id, base)

                chemin = export_modele.nom_archive(demande.id)
                bilan = export_modele.construire(session, documents, chemin,
                                                 demande.modele_dossier, demande.modele_nom)
                demande.chemin = chemin
                demande.nb_documents = bilan["documents"]
                demande.statut = "pret"
                demande.message = (f"{bilan['fichiers']} fichier(s) pour "
                                   f"{bilan['documents']} document(s)"
                                   + (f", {bilan['absents']} introuvable(s)"
                                      if bilan["absents"] else ""))
                log.info("Export par modèle %s prêt : %s", demande.id, demande.message)
            except Exception as erreur:
                session.rollback()
                demande = session.get(ExportModele, demande.id)
                demande.statut = "erreur"
                demande.message = str(erreur) or erreur.__class__.__name__
                log.exception("Export par modèle %s impossible", demande.id)
            demande.date_fin = datetime.now()
            session.commit()
            faits += 1
        return faits
    except Exception:
        session.rollback()
        log.exception("Relève des demandes d'export impossible")
        return faits
    finally:
        session.close()


def traiter_rejets() -> int:
    """
    Relève les dépôts **écartés** depuis le Centre d'analyse (§21.14).

    L'API pose la consigne, le serveur de travaux efface le fichier reçu : elle
    seule a les fichiers reçus en écriture. Le travail passe en « ignoré » avec
    son diagnostic — il reste visible dans le suivi, où l'on voit ce qui a été
    écarté et par qui, jusqu'à la purge.
    """
    session = SessionLocal()
    try:
        demandes = session.query(Job).filter(Job.rejet_demande.is_(True)).all()
        if not demandes:
            return 0
        for job in demandes:
            chemin_source = job.chemin_source
            if chemin_source:
                try:
                    fichier = Path(chemin_source)
                    if fichier.is_file():
                        fichier.unlink()
                except OSError:
                    log.exception("Le dépôt écarté %s n'a pas pu être effacé", chemin_source)
            job.chemin_source = None
            job.rejet_demande = False
            job.statut = "ignore"
            job.date_fin = datetime.now()
        session.commit()
        log.info("%d dépôt(s) écarté(s) depuis le Centre d'analyse", len(demandes))
        return len(demandes)
    except Exception:
        session.rollback()
        log.exception("Échec du traitement des dépôts écartés")
        return 0
    finally:
        session.close()


def traiter_rejeux() -> int:
    """
    Relève les demandes de rejeu posées par l'administration (§13).

    Deux cas, selon ce que le travail a produit :
      - un document existe déjà (travail bloqué, ou terminé) : inutile de
        refaire l'OCR, on réapplique les règles d'extraction sur le texte
        conservé puis on recontrôle les champs attendus. C'est ce qu'on veut
        après avoir corrigé une regex ou une règle de champ ;
      - aucun document (échec technique) : le fichier est ramené du dossier de
        quarantaine vers le dossier surveillé, pour un traitement complet.
    """
    session = SessionLocal()
    try:
        demandes = session.query(Job).filter(Job.rejouer_demande.is_(True)).all()
        if not demandes:
            return 0
        a_retraiter = []
        for job in demandes:
            depuis = job.etape_demandee or ETAPE_REGLES
            # sans document produit, seule une reprise complète depuis le
            # fichier source a un sens : il n'y a rien à réanalyser
            if job.document_id and depuis != ETAPE_EMPREINTE:
                _rejouer_analyse(session, job, depuis)
            else:
                a_retraiter.append((job.id, job.chemin_source))
        session.commit()
    except Exception:
        session.rollback()
        log.exception("Échec du relevé des demandes de rejeu")
        return 0
    finally:
        session.close()

    # le retraitement complet ouvre sa propre session, hors de la précédente
    for job_id, chemin in a_retraiter:
        # Un classement demandé depuis le Centre d'analyse (§19.4) déplace
        # d'abord le fichier : le traitement qui suit est celui d'un dépôt
        # ordinaire dans le dossier de son type.
        _rejouer_fichier(job_id, _ranger_avant_rejeu(job_id) or chemin)
    return len(demandes)


def _rejouer_analyse(session, job: Job, depuis: str) -> None:
    """
    Reprend le traitement d'un document existant à partir de l'étape demandée.

    Les étapes situées avant `depuis` ne sont pas rejouées : leur résultat est
    déjà en base ou sur le disque. Reprendre à « regles » suffit après avoir
    corrigé une expression régulière ; il faut remonter à « ocr » seulement si
    le texte reconnu est lui-même mauvais.
    """
    document = session.get(Document, job.document_id)
    job.rejouer_demande = False
    job.etape_demandee = None
    job.tentatives = (job.tentatives or 0) + 1
    job.date_fin = datetime.now()
    if not document:
        job.statut = "erreur"
        job.etape = depuis
        job.message_erreur = "Le document associé n'existe plus."
        return

    depart = ETAPES.index(depuis) if depuis in ETAPES else ETAPES.index(ETAPE_REGLES)
    try:
        if depart <= ETAPES.index(ETAPE_OCR):
            job.etape = ETAPE_OCR
            _reocr_sur_place(document)
        if depart <= ETAPES.index(ETAPE_EXTRACTION):
            job.etape = ETAPE_EXTRACTION
            _etape_extraction(document)
        if depart <= ETAPES.index(ETAPE_REGLES):
            job.etape = ETAPE_REGLES
            _etape_regles(session, document)
        job.etape = ETAPE_CONFORMITE
        manquants = _etape_conformite(session, document)
    except Exception as erreur:
        job.statut = "erreur"
        job.message_erreur = str(erreur) or erreur.__class__.__name__
        job.diagnostic = traceback.format_exc(limit=6)
        log.exception(f"Travail {job.id} : échec de la reprise à l'étape « {job.etape} »")
        return

    job.document_id = document.id
    if manquants:
        libelles = ", ".join(c["libelle"] for c in manquants)
        job.statut = "bloque"
        job.message_erreur = f"Champs attendus manquants : {libelles}"
    else:
        job.statut = "termine"
        job.message_erreur = None
        job.diagnostic = None
    log.info(f"Travail {job.id} repris depuis « {depuis} » -> {job.statut}")


def _ranger_avant_rejeu(job_id: int) -> str | None:
    """
    Exécute la consigne de classement posée par le Centre d'analyse (§19.4).

    Le fichier rejoint le dossier de dépôt du type demandé, et c'est tout : le
    traitement qui suit est celui d'un dépôt ordinaire, au même endroit, par le
    même chemin. C'est ce qui garantit qu'un document classé à la main vaut un
    document bien déposé — il n'y a pas deux façons d'entrer dans le registre.

    Rend le nouveau chemin, ou l'ancien s'il n'y avait rien à faire.
    """
    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        if not job or not job.categorie_demandee or not job.chemin_source:
            return job.chemin_source if job else None

        categorie = session.get(Categorie, job.categorie_demandee)
        source = Path(job.chemin_source)
        if not categorie or not categorie.dossier_depot or not source.is_file():
            # La consigne ne peut plus s'appliquer — type supprimé, fichier
            # disparu. On la retire plutôt que de la relever indéfiniment.
            job.categorie_demandee = None
            session.commit()
            return job.chemin_source

        depots.creer(categorie.dossier_depot)
        destination = depots.chemin(categorie.dossier_depot) / source.name
        if destination.exists():
            destination = destination.with_name(
                f"{destination.stem}_{job.id}{destination.suffix}")
        # `shutil.move` et non `os.rename` : les fichiers reçus et le dépôt sont
        # deux volumes distincts, un renommage y échoue.
        shutil.move(str(source), str(destination))
        job.chemin_source = str(destination)
        job.categorie_demandee = None
        session.commit()
        log.info(f"Travail {job_id} rangé dans « {categorie.nom} » ({destination})")
        return str(destination)
    except Exception:
        session.rollback()
        log.exception(f"Le classement demandé pour le travail {job_id} a échoué")
        return None
    finally:
        session.close()


def _rejouer_fichier(job_id: int, chemin_source: str | None) -> None:
    """
    Retraite un fichier mis en quarantaine.

    Le fichier est traité **sur place**, sans repasser par le dossier surveillé :
    l'y remettre déclencherait aussi l'observateur, et le même fichier serait
    traité deux fois en parallèle.
    """
    source = Path(chemin_source) if chemin_source else None
    if not source or not source.exists():
        session = SessionLocal()
        try:
            job = session.get(Job, job_id)
            if job:
                job.rejouer_demande = False
                job.etape_demandee = None
                job.statut = "erreur"
                job.message_erreur = "Le fichier source est introuvable, le rejeu est impossible."
                job.date_fin = datetime.now()
                session.commit()
        except Exception:
            session.rollback()
            log.exception(f"Échec de la mise à jour du travail {job_id}")
        finally:
            session.close()
        return

    log.info(f"Travail {job_id} remis en traitement ({source.name})")
    traiter_fichier(source, job_id=job_id)


def _destination_libre(dossier: Path, radical: str) -> Path:
    """
    Choisit un chemin de stockage encore libre.

    Deux fichiers homonymes déposés le même mois — un même document rescanné,
    par exemple — visaient jusqu'ici le même PDF de destination : le second
    écrasait silencieusement le premier, et les deux enregistrements pointaient
    vers le même fichier (ce qui rendait aussi leur suppression dangereuse).
    Les doublons réels sont déjà écartés en amont par le hash du fichier.
    """
    candidat = dossier / f"{radical}.pdf"
    suffixe = 2
    while candidat.exists():
        candidat = dossier / f"{radical}_{suffixe}.pdf"
        suffixe += 1
    return candidat


def _hash_fichier(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# Fichiers en cours de traitement, par chemin. Deux chemins mènent au même
# fichier : la surveillance du dossier, et le rejeu demandé depuis l'interface —
# un classement à la main (§19.4) déclenche les deux à quelques secondes d'écart.
# Sans ce garde-fou, le même dépôt produisait deux travaux, dont l'un finissait
# « doublon » sans que personne comprenne pourquoi.
_en_traitement: set[str] = set()
_verrou_traitement = threading.Lock()

# Combien de documents océrisés **en même temps** (§22.41).
#
# Le traitement d'un document dure sept secondes, presque entièrement passées
# dans tesseract et ghostscript — soit cinq cents documents à l'heure, et
# quarante heures pour reprendre l'existant d'un foyer de vingt mille. Or ce
# travail se fait dans des sous-processus : le GIL de Python n'y est pour rien,
# et quelques fils suffisent à occuper plusieurs cœurs.
#
# Des **fils** et non des processus, et c'est ce qui rend la chose sûre : le
# garde-fou qui empêche de traiter deux fois le même fichier (`_en_traitement`)
# est en mémoire de ce processus-ci, et chaque fichier ouvre déjà sa propre
# session de base. Lancer plusieurs conteneurs `worker` sur le même dossier, en
# revanche, ferait prendre le même fichier par deux d'entre eux.
#
# La moitié des cœurs, quatre au plus : au-delà, les océrisations se disputent
# le processeur et le débit cesse d'augmenter. `OMP_THREAD_LIMIT=1` (posé dans
# docker-compose.yml) empêche chaque tesseract d'en réclamer autant à lui seul.
#
# Le nombre se règle **depuis l'administration** (« Documents traités en même
# temps ») : c'est un arbitrage entre la vitesse de reprise et la charge de la
# machine, et il dépend du matériel du foyer — personne d'autre que celui qui
# l'administre ne peut le trancher. `.env` garde la main comme repli, et zéro
# veut dire « décide pour moi ».
def parallelisme_par_defaut() -> int:
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def parallelisme_voulu(session=None) -> int:
    """Le nombre réglé par le foyer, celui de `.env`, ou celui de la machine."""
    from . import reglages

    fermer = session is None
    if fermer:
        session = SessionLocal()
    try:
        regle = reglages.entier(session, "traitements_simultanes")
    except Exception:
        log.debug("Réglage des traitements simultanés illisible", exc_info=True)
        regle = 0
    finally:
        if fermer:
            session.close()
    if regle <= 0:
        regle = int(os.getenv("TRAVAUX_PARALLELES", "0") or 0)
    return max(1, min(8, regle)) if regle > 0 else parallelisme_par_defaut()


_executeur: Optional[ThreadPoolExecutor] = None
_taille_pool = 0


def confier(fonction, *arguments) -> None:
    """
    Confie un traitement au pool, ou l'exécute ici s'il n'y en a pas.

    Le repli n'est pas théorique : les tests appellent `traiter_fichier`
    directement, sans passer par `main()`, et doivent voir le travail fait quand
    la fonction rend la main.
    """
    if _executeur is None:
        fonction(*arguments)
        return
    _executeur.submit(_sans_bruit, fonction, *arguments)


def _sans_bruit(fonction, *arguments) -> None:
    """Un fil qui meurt en silence emporte le travail avec lui : on journalise."""
    try:
        fonction(*arguments)
    except Exception:      # noqa: BLE001 — le pool avale les exceptions
        log.exception("Traitement interrompu par une erreur")


def type_du_travail(session, path: Path, job=None):
    """
    De quel type de document s'agit-il ?

    **L'emplacement du dépôt le dit, et lui seul** (§19.3) : rien n'est deviné sur
    le texte, on ne saurait pas le justifier.

    Sauf qu'au **rejeu**, le fichier n'est plus dans le dossier où on l'avait mis :
    il vit dans `travaux/`, où le serveur l'avait conservé. L'emplacement s'est tu,
    et le travail retombait « à classer » — on redemandait une réponse déjà donnée
    (§21.15). Le travail garde donc le type reconnu au dépôt, et l'on s'en sert
    **uniquement quand l'emplacement ne dit rien** : c'est un souvenir, pas une
    consigne, et le dossier reste maître quand on y a remis le fichier.
    """
    type_document = depots.type_du_chemin(session, path)
    if type_document is not None:
        return type_document
    if job is not None and getattr(job, "categorie_id", None):
        retrouve = session.get(Categorie, job.categorie_id)
        if retrouve is not None:
            log.info("Travail %s : type « %s » retrouvé sur le travail (rejeu)",
                     job.id, retrouve.nom)
        return retrouve
    return None


def traiter_fichier(path: Path, job_id: int | None = None) -> None:
    if path.suffix.lower() not in config.SUPPORTED_EXTENSIONS:
        log.warning(f"Extension non supportée, ignoré : {path.name} (attendu : {sorted(config.SUPPORTED_EXTENSIONS)})")
        return

    empreinte_chemin = str(path)
    with _verrou_traitement:
        if empreinte_chemin in _en_traitement:
            log.debug(f"{path.name} est déjà en cours de traitement : ignoré")
            return
        _en_traitement.add(empreinte_chemin)
    try:
        _traiter_fichier(path, job_id)
    finally:
        with _verrou_traitement:
            _en_traitement.discard(empreinte_chemin)


def _traiter_piece(session, job: Job, path: Path, hash_fichier: str) -> None:
    """
    Le fichier déposé rejoint un document existant comme **pièce** (§22.2).

    Une facture, sa garantie et le bon de livraison sont un seul dossier : les
    réunir sous une seule fiche évite de remplir trois fois les mêmes champs et
    de décider trois fois du même classement. Le fichier suit malgré tout le
    chemin ordinaire — océrisation, archivage —, car une pièce se cherche et se
    lit comme le reste : son texte rejoint celui du document.

    Ce qui **ne se passe pas** ici : ni règles d'extraction, ni conformité. Les
    champs du document ont été remplis quand il est entré ; une pièce jointe ne
    les rejoue pas, sans quoi la garantie écraserait la date de la facture.
    """
    document = session.get(Document, job.piece_pour_document_id)
    if document is None or document.date_suppression is not None:
        _cloturer_job(
            session, job, "erreur", chemin_source=_conserver_original(job.id, path),
            message="Le document auquel joindre cette pièce n'existe plus.",
            diagnostic="Il a été supprimé entre le dépôt et la reprise du travail. "
                       "Redéposez la pièce depuis le document voulu.")
        return

    connu = _document_portant(session, hash_fichier)
    if connu:
        _cloturer_job(
            session, job, "ignore", document_id=connu,
            chemin_source=_conserver_original(job.id, path),
            diagnostic=f"Fichier identique à une pièce ou une version du document "
                       f"nº{connu} : rien à ajouter.")
        return

    remplacee = (session.get(PieceDocument, job.version_pour_piece_id)
                 if job.version_pour_piece_id else None)
    if job.version_pour_piece_id and (remplacee is None
                                      or remplacee.document_id != document.id):
        _cloturer_job(
            session, job, "erreur", document_id=document.id,
            chemin_source=_conserver_original(job.id, path),
            message="La pièce à remplacer n'existe plus.",
            diagnostic="Elle a été détachée entre le dépôt et la reprise du travail. "
                       "Redéposez le fichier en choisissant ce qu'il doit devenir.")
        return

    job.etape = ETAPE_OCR
    dossier_dest = Path(config.STORAGE_FOLDER) / time.strftime("%Y/%m")
    dossier_dest.mkdir(parents=True, exist_ok=True)
    chemin_pdf = _destination_libre(dossier_dest, path.stem)
    ocr_to_searchable_pdf(str(path), str(chemin_pdf), **reglages_traitement(session))

    job.etape = ETAPE_EXTRACTION
    texte = extraire_texte(str(chemin_pdf))

    job.etape = ETAPE_INDEXATION
    if remplacee is not None:
        # Le même papier rescanné (§22.3) : il prend la place de celui qu'il
        # remplace, **là où il était**, et l'ancien reste consultable dans
        # l'historique de cette pièce-là.
        remplacee.texte_ocr = texte
        version = versions.enregistrer_depot(
            session, document, str(chemin_pdf), path.name, hash_fichier,
            taille=os.path.getsize(chemin_pdf), piece=remplacee)
        session.commit()
        log.info(f"Pièce {remplacee.id} du document {document.id} rescannée "
                 f"(version {version.id})")
        _cloturer_job(session, job, "termine", document_id=document.id,
                      chemin_source=_conserver_original(job.id, path),
                      diagnostic=f"Enregistré comme nouvelle version de la pièce "
                                 f"« {remplacee.nom_fichier} » du document "
                                 f"nº{document.id}.")
        return

    piece = pieces.ajouter(session, document, str(chemin_pdf), path.name, hash_fichier,
                           texte=texte, taille=os.path.getsize(chemin_pdf))
    integrite.poser(piece, str(chemin_pdf))
    session.commit()
    log.info(f"Pièce {piece.id} ajoutée au document {document.id} ({path.name})")
    _cloturer_job(session, job, "termine", document_id=document.id,
                  chemin_source=_conserver_original(job.id, path),
                  diagnostic=f"Ajouté comme pièce nº{piece.ordre} du document "
                             f"nº{document.id}.")


def _document_portant(session, empreinte: str) -> int | None:
    """
    Le document qui porte déjà ce fichier — comme document, comme version ou
    comme pièce. Un fichier identique au bit près ne raconte rien de neuf, et en
    faire une pièce de plus n'ajouterait qu'une ligne.
    """
    doublon = session.query(Document).filter_by(hash_sha256=empreinte).first()
    if doublon:
        return doublon.id
    version = versions.version_par_empreinte(session, empreinte)
    if version:
        return version.document_id
    piece = session.query(PieceDocument).filter_by(hash_sha256=empreinte).first()
    return piece.document_id if piece else None


def _traiter_fichier(path: Path, job_id: int | None = None) -> None:
    log.info(f"Nouveau fichier détecté : {path.name}")
    if not _attendre_fichier_stable(path):
        return  # dépôt incomplet ou fichier disparu : on retentera au prochain passage

    session = SessionLocal()
    job = _ouvrir_job(session, path, job_id)
    try:
        job.etape = ETAPE_EMPREINTE
        hash_fichier = _hash_fichier(path)
        job.hash_sha256 = hash_fichier

        # 0 bis. Ce fichier rejoint-il un document existant comme **pièce** ?
        #
        # Avant le classement par l'emplacement : un dépôt de pièce ne vise pas
        # un type, il vise un document — qui a déjà le sien. Le fichier vient du
        # dossier des dépôts manuels, où l'emplacement ne dit rien de toute façon.
        if job.piece_pour_document_id:
            _traiter_piece(session, job, path, hash_fichier)
            return

        # 0. De quel type de document s'agit-il ? (§19.3)
        #
        # C'est l'emplacement du dépôt qui le dit, et lui seul. Rien n'est deviné
        # sur le texte : on ne saurait pas le justifier, et un document rangé
        # ailleurs que là où on l'a mis est une surprise qu'on découvre trop tard.
        #
        # Sans réponse, le traitement s'arrête **avant l'océrisation** : le texte
        # reconnu ne servirait à rien tant qu'on ignore de quoi il s'agit, et
        # l'étape la plus coûteuse n'a pas à être faite deux fois.
        type_document = type_du_travail(session, path, job)
        if type_document is None:
            log.warning(f"Déposé hors d'un dossier de type : {path}")
            _cloturer_job(
                session, job, "a_classer",
                chemin_source=_conserver_original(job.id, path),
                message="Déposé à un endroit qu'aucun type de document ne réclame.",
                diagnostic="Le classement se fait par l'emplacement du dépôt : chaque "
                           "type de document a son dossier sous ocr_wait/. Ce fichier "
                           "était à la racine ou dans un dossier inconnu. Indiquez son "
                           "type depuis le Centre d'analyse, ou redéposez-le dans le "
                           "bon dossier.")
            return

        # Le travail retient le type : c'est ce qui permettra de le rejouer plus
        # tard, quand le fichier ne sera plus dans le dossier qui l'a dit (§21.15).
        job.categorie_id = type_document.id

        # Fichier déjà connu — comme document, ou comme version d'un document
        # (§18.36). Rien à ajouter : un fichier identique au bit près ne raconte
        # rien de neuf, et en faire une « version » n'apporterait qu'une ligne.
        identifiant = _document_portant(session, hash_fichier)
        if identifiant:
            log.info(f"Dépôt déjà connu, ignoré : {path.name}")
            # Le même fichier redéposé alors que le document est à la corbeille :
            # le refuser comme un simple doublon laisserait croire à une panne —
            # on l'a supprimé, on le redépose, et « rien à ajouter » n'explique
            # rien. On dit où il est (§21.1).
            jete = session.get(Document, identifiant)
            if jete is not None and jete.date_suppression is not None:
                diagnostic = (f"Ce fichier est déjà le document nº{identifiant}, "
                              f"actuellement à la corbeille. Restaurez-le depuis la "
                              f"corbeille plutôt que de le redéposer.")
            else:
                diagnostic = (f"Fichier identique à une version ou à une pièce du "
                              f"document nº{identifiant} : rien à ajouter.")
            _cloturer_job(session, job, "ignore", document_id=identifiant,
                          chemin_source=_conserver_original(job.id, path),
                          diagnostic=diagnostic)
            return

        # destination finale : storage/AAAA/MM/nom_fichier.pdf
        annee_mois = time.strftime("%Y/%m")
        dossier_dest = Path(config.STORAGE_FOLDER) / annee_mois
        dossier_dest.mkdir(parents=True, exist_ok=True)
        chemin_pdf = _destination_libre(dossier_dest, path.stem)

        # 1. OCR -> PDF cherchable
        job.etape = ETAPE_OCR
        traitement = reglages_traitement(session)
        ocr_to_searchable_pdf(str(path), str(chemin_pdf), **traitement)

        # 2. extraction texte
        job.etape = ETAPE_EXTRACTION
        texte = extraire_texte(str(chemin_pdf))

        # 3. création de l'entrée en base
        job.etape = ETAPE_INDEXATION
        document = Document(
            nom_fichier=path.name,
            chemin_stockage=str(chemin_pdf),
            hash_sha256=hash_fichier,
            texte_ocr=texte,
            statut="traite",
            # déjà compressé par l'océrisation (§17.8) : inutile que la reprise
            # des archives le reprenne au passage suivant
            taille_octets=os.path.getsize(chemin_pdf),
            date_compression=datetime.now() if traitement["optimisation"] > 0 else None,
            # Le classement vient du dossier de dépôt, pas du texte (§19.3).
            categorie_id=type_document.id,
            # D'où il vient (§22.68, corrigé au §22.72). C'est le fichier **en
            # cours de traitement** qui le dit, et lui seul : `job.chemin_source`
            # finit toujours dans le dossier des travaux, où le fichier reçu est
            # rangé à la fin du traitement, quelle que soit son origine. S'y
            # fier marquait tout comme déposé à la main.
            depot_manuel=_origine_du_depot(path),
        )
        # L'empreinte de l'archive telle qu'elle vient d'être écrite (§21.3) :
        # c'est elle que le contrôle d'intégrité relira, et non celle du fichier
        # reçu — l'océrisation vient justement de le réécrire.
        integrite.poser(document, str(chemin_pdf))
        session.add(document)
        session.flush()  # pour obtenir document.id avant l'étape suivante

        # Le fichier archivé est la **première pièce** du document (§22.2) : les
        # suivantes s'ajouteront à côté d'elle, et non à sa place. Un document
        # sans pièce n'existe pas — celle-ci naît avec lui.
        premiere = pieces.ajouter(session, document, str(chemin_pdf), path.name,
                                  hash_fichier, texte=texte,
                                  taille=document.taille_octets, principale_=True)
        integrite.poser(premiere, str(chemin_pdf))

        # 4. remplissage auto des colonnes/métadonnées via regex
        job.etape = ETAPE_REGLES
        _etape_regles(session, document)

        # 4 bis. les automatisations du foyer (§21.8), dans la même transaction :
        # ce qu'elles posent fait partie du document tel qu'il entre au registre,
        # pas d'une correction d'après coup.
        automatisations.executer(session, automatisations.DEPOT, document)

        # 5. le document redouble-t-il une fiche déjà là ? (§18.36)
        #
        # Après les règles, et pas avant : c'est l'extraction qui donne les
        # valeurs identifiantes — un numéro de facture, une période — donc de quoi
        # reconnaître la même pièce rescannée.
        jumeau = versions.document_jumeau(session, document)
        if jumeau:
            # La fiche fraîchement créée s'efface **avant** que la fiche d'origine
            # ne reprenne l'empreinte du nouveau fichier : les deux la porteraient
            # sinon en même temps, et l'unicité de `hash_sha256` s'y oppose. Ses
            # valeurs ne sont pas perdues — la fiche d'origine garde les siennes,
            # avec ses corrections manuelles et ses rattachements, ce qui est tout
            # l'intérêt de rapprocher plutôt que de dupliquer.
            session.delete(document)
            session.flush()
            version = versions.enregistrer_depot(
                session, jumeau, str(chemin_pdf), path.name, hash_fichier,
                taille=os.path.getsize(chemin_pdf))
            session.commit()
            log.info(f"Nouvelle version du document {jumeau.id} ({path.name})")
            _cloturer_job(session, job, "termine", document_id=jumeau.id,
                          chemin_source=_conserver_original(job.id, path),
                          diagnostic=f"Enregistré comme nouvelle version du document "
                                     f"nº{jumeau.id} (version {version.id}).")
            return

        # 6. contrôle des champs attendus par la catégorie (§15/§16)
        job.etape = ETAPE_CONFORMITE
        manquants = _etape_conformite(session, document)

        # Première version de cette fiche : l'historique commence ici.
        versions.enregistrer_depot(session, document, str(chemin_pdf), path.name,
                                   hash_fichier, taille=os.path.getsize(chemin_pdf))

        session.commit()
        log.info(f"Document {document.id} traité et indexé ({path.name})")

        # 7. le fichier reçu quitte le dossier de dépôt pour celui de son
        # travail, où il reste consultable jusqu'à la purge (§18.53).
        origine = _conserver_original(job.id, path)

        if manquants:
            libelles = ", ".join(c["libelle"] for c in manquants)
            log.warning(f"Document {document.id} incomplet — champs attendus manquants : {libelles}")
            _cloturer_job(session, job, "bloque", document_id=document.id,
                          chemin_source=origine,
                          message=f"Champs attendus manquants : {libelles}",
                          diagnostic="Le document est indexé mais ne respecte pas les champs "
                                     "exigés par sa catégorie. Complète-les depuis sa fiche, "
                                     "puis relance le travail.")
        else:
            _cloturer_job(session, job, "termine", document_id=document.id,
                          chemin_source=origine)

    except Exception as erreur:
        session.rollback()
        log.exception(f"Erreur lors du traitement de {path.name}")
        destination = _conserver_original(job.id, path)
        # Récupérable, ou définitive ? (§21.15) Un fichier illisible ne le
        # deviendra pas en le retentant : passé le palier, le travail sort de
        # toute reprise et le dit — un document irrécupérable ne doit pas tourner
        # pour toujours, et l'écran doit distinguer « la machine essaie encore »
        # de « la machine a renoncé ».
        definitif = _palier_atteint(session, job.tentatives)
        _cloturer_job(session, job, "echec" if definitif else "erreur",
                      message=str(erreur) or erreur.__class__.__name__,
                      diagnostic=(traceback.format_exc(limit=6) + (
                          f"\n\nAbandonné après {job.tentatives} tentative(s) : ce travail "
                          f"ne sera plus repris tout seul. Corrigez ce qui doit l'être, "
                          f"puis demandez un rejeu — il repartira de zéro."
                          if definitif else "")),
                      chemin_source=destination)
    finally:
        session.close()


def reglages_traitement(session=None) -> dict:
    """
    Réglages du foyer qui pèsent sur le traitement d'un document (§18.22) :
    langue de l'océrisation, résolution cible, compression.

    Relus à chaque document plutôt que mémorisés au démarrage : les changer
    depuis l'interface doit valoir pour le dépôt suivant, pas au prochain
    redémarrage du serveur de travaux. Une base qui bronche renvoie les valeurs
    de `.env` — un dépôt ne doit pas rester en plan parce qu'un réglage manque.
    """
    from . import reglages

    fermer = session is None
    if fermer:
        session = SessionLocal()
    try:
        return {
            "langue": reglages.lire(session, "langue_ocr") or "fra",
            "resolution": reglages.entier(session, "resolution_ocr"),
            "optimisation": reglages.entier(session, "compression_niveau"),
        }
    except Exception:
        log.debug("Réglages de traitement illisibles : on garde ceux de la configuration",
                  exc_info=True)
        return {
            "langue": "fra",
            "resolution": config.RESOLUTION_CIBLE,
            "optimisation": config.PDF_OPTIMISATION,
        }
    finally:
        if fermer:
            session.close()


def purger_originaux_orphelins() -> int:
    """
    Efface les fichiers conservés dont plus aucun travail ne répond.

    Même raison que pour les archives d'export (§17.30) : un fichier que rien ne
    réclame plus ne s'efface jamais tout seul, et c'est ce genre d'oubli qui
    finit par occuper un disque — ou par laisser traîner un document que l'on
    croyait supprimé.
    """
    dossier = Path(config.TRAVAUX_FOLDER)
    if not dossier.is_dir():
        return 0
    session = SessionLocal()
    try:
        connus = {str(identifiant) for (identifiant,) in session.query(Job.id).all()}
    finally:
        session.close()

    orphelins = [d.name for d in dossier.iterdir() if d.is_dir() and d.name not in connus]
    if not orphelins:
        return 0
    efface = _effacer_originaux(orphelins)
    if efface:
        log.info(f"{efface} dossier(s) de travail sans travail correspondant effacé(s)")
    return efface


def purger_exports_modele() -> int:
    """
    Efface les archives par modèle expirées (§21.13).

    Même raison que pour l'export de secours : une archive oubliée est une copie
    de documents du foyer qui traîne sur le disque, et personne ne pense au
    ménage. Le délai est celui déjà réglé pour les exports
    (`expiration_export_minutes`) — un second réglage pour la même idée serait un
    réglage de trop.
    """
    from . import reglages
    from .db import ExportModele

    session = SessionLocal()
    try:
        minutes = reglages.entier(session, "expiration_export_minutes")
        if minutes <= 0:
            return 0
        limite = datetime.now() - timedelta(minutes=minutes)
        expirees = (session.query(ExportModele)
                    .filter(ExportModele.date_demande < limite).all())
        efface = 0
        for demande in expirees:
            if demande.chemin:
                try:
                    Path(demande.chemin).unlink(missing_ok=True)
                except OSError:
                    log.warning("Archive %s non effacée", demande.chemin)
            session.delete(demande)
            efface += 1
        if efface:
            session.commit()
            log.info("%s archive(s) par modèle expirée(s) effacée(s)", efface)
        return efface
    except Exception:
        session.rollback()
        log.exception("Purge des archives par modèle impossible")
        return 0
    finally:
        session.close()


def purger_apercus_orphelins() -> int:
    """
    Efface les miniatures dont plus aucun document ne répond (§19.20).

    La perte est nulle — une miniature se refait en une seconde — mais ce qui ne
    s'efface jamais tout seul finit par occuper un disque.
    """
    session = SessionLocal()
    try:
        connus = {identifiant for (identifiant,) in session.query(Document.id)}
    except Exception:
        log.exception("Documents illisibles : miniatures non purgées")
        return 0
    finally:
        session.close()
    efface = apercus.purger(connus)
    if efface:
        log.info(f"{efface} miniature(s) sans document effacée(s)")
    return efface


DUREE_EXEMPLE_APPRENTISSAGE = 2 * 3600     # secondes


def ajuster_le_pool() -> int:
    """
    Reprend le nombre de traitements simultanés si l'administration l'a changé
    (§22.41).

    Un `ThreadPoolExecutor` ne se redimensionne pas : on en installe un neuf et
    l'on **rend la main** à l'ancien sans l'attendre — ses documents en cours
    vont au bout, et le nouveau prend la suite. C'est ce qui permet de régler ce
    nombre depuis l'écran sans redémarrer le serveur de travaux.
    """
    global _executeur, _taille_pool

    voulu = parallelisme_voulu()
    if _executeur is None or voulu == _taille_pool:
        return _taille_pool
    ancien = _executeur
    _executeur = ThreadPoolExecutor(max_workers=voulu, thread_name_prefix="traitement")
    log.info("Traitements simultanés : %s -> %s", _taille_pool, voulu)
    _taille_pool = voulu
    # `wait=False` : on n'arrête pas la boucle d'entretien pour attendre une
    # océrisation. L'ancien pool se ferme quand son dernier document est fini.
    ancien.shutdown(wait=False)
    return voulu


# Quand la dernière sauvegarde a eu lieu, en mémoire du processus : la boucle
# d'entretien passe toutes les cinq minutes, la sauvegarde toutes les vingt-quatre
# heures. Le repère durable, lui, est le dossier lui-même — un redémarrage relit
# donc la vraie dernière date, et ne resauvegarde pas pour rien.
_derniere_sauvegarde = 0.0


def sauvegarder_si_besoin() -> Optional[dict]:
    """
    Fait la copie de secours quand l'heure est venue (§22.49).

    Tout est réglé par le foyer et rien n'est imposé : la sauvegarde est éteinte
    par défaut, et son rythme, sa destination, ce qu'elle emporte et le nombre
    qu'on en garde se décident depuis l'administration.

    L'échec est **journalisé** et non silencieux : une sauvegarde qui a cessé
    sans que personne ne le sache est pire que pas de sauvegarde du tout.
    """
    global _derniere_sauvegarde
    from . import audit, reglages, sauvegarde

    session = SessionLocal()
    try:
        if not reglages.booleen(session, "sauvegarde_active"):
            return None
        heures = max(1, reglages.entier(session, "sauvegarde_heures") or 24)
        dossier = reglages.lire(session, "sauvegarde_dossier") or "/data/sauvegardes"
        garder = max(1, reglages.entier(session, "sauvegarde_garder") or 7)
        archives = reglages.booleen(session, "sauvegarde_archives")

        # Au démarrage, la dernière date vient du disque : c'est elle qui fait
        # foi, sans quoi chaque redémarrage déclencherait une sauvegarde.
        if not _derniere_sauvegarde:
            faites = [s for s in sauvegarde.lister(dossier) if s["complete"]]
            if faites:
                _derniere_sauvegarde = datetime.fromisoformat(faites[0]["date"]).timestamp()
        if _derniere_sauvegarde and time.time() - _derniere_sauvegarde < heures * 3600:
            return None

        try:
            bilan = sauvegarde.executer(
                dossier, avec_archives=archives,
                mot_de_passe=reglages.lire(session, "sauvegarde_mot_de_passe") or None)
        except sauvegarde.SauvegardeImpossible as erreur:
            log.error("Sauvegarde impossible : %s", erreur)
            audit.journaliser(session, None, "sauvegarde.echec", "sauvegarde", None,
                              details={"erreur": str(erreur)[:300], "dossier": dossier})
            session.commit()
            # On ne réessaie pas en boucle : la prochaine tentative aura lieu au
            # rythme réglé, et l'écran d'administration dit que rien ne passe.
            _derniere_sauvegarde = time.time()
            return None

        _derniere_sauvegarde = time.time()
        efface = sauvegarde.purger(dossier, garder)
        log.info("Sauvegarde faite dans %s (%s Ko de base, %s fichier(s) archivé(s))",
                 bilan["dossier"], bilan["octets_base"] // 1024, bilan["fichiers_archives"])
        audit.journaliser(session, None, "sauvegarde.faite", "sauvegarde", None,
                          details={**bilan, "anciennes_effacees": efface})
        session.commit()
        return bilan
    except Exception:
        session.rollback()
        log.exception("Cycle de sauvegarde interrompu")
        return None
    finally:
        session.close()


def verifier_conformite_rangee() -> int:
    """
    Vérifie que l'état rangé dit la même chose que le calcul (§22.41).

    C'est le filet du dispositif : l'état est écrit aux deux moments où il
    change, mais un chemin oublié aujourd'hui ou ajouté demain le ferait mentir —
    et un drapeau qui ment fait disparaître un document du registre sans que
    personne ne sache pourquoi. On repose donc la question à la source, ici, dans
    la boucle d'entretien, et l'on corrige les écarts en les journalisant : un
    écart n'est pas grave, un écart **silencieux** le serait.

    La définition employée est `conformite.clause_incomplet` — celle du code,
    la même que la migration a jouée à l'installation.
    """
    from . import conformite

    session = SessionLocal()
    try:
        ecarts = conformite.recalculer(session)
        if ecarts:
            session.commit()
            log.warning("Conformité : %s document(s) remis d'accord avec les règles", ecarts)
        return ecarts
    except Exception:
        session.rollback()
        log.exception("Vérification de la conformité impossible")
        return 0
    finally:
        session.close()


def purger_exemples_apprentissage() -> int:
    """
    Efface les documents importés pour apprendre une règle (§22.35).

    Ces fichiers n'entrent jamais au registre : ils servent le temps d'écrire une
    expression régulière, puis ne valent plus rien. Ce sont pourtant de vrais
    papiers du foyer posés sur le disque — les laisser serait garder des factures
    hors de la GED, sans corbeille ni journal pour en rendre compte.

    Deux heures : assez pour écrire une règle sans se presser, assez court pour
    qu'un onglet oublié ne laisse pas traîner un relevé bancaire.
    """
    racine = Path(config.DEPOTS_MANUELS_FOLDER) / "apprentissage"
    if not racine.is_dir():
        return 0
    limite = time.time() - DUREE_EXEMPLE_APPRENTISSAGE
    efface = 0
    for dossier in racine.iterdir():
        try:
            if not dossier.is_dir() or dossier.stat().st_mtime > limite:
                continue
            shutil.rmtree(dossier)
            efface += 1
        except OSError:
            log.warning("Exemple d'apprentissage %s non effacé", dossier)
    if efface:
        log.info("%s exemple(s) d'apprentissage expiré(s) effacé(s)", efface)
    return efface


def envoyer_les_resumes() -> dict:
    """
    Le résumé par courriel de ce que personne n'a lu (§21.10).

    Ne fait rien tant que le foyer n'a pas activé le courriel : un rappel qui part
    sans qu'on l'ait demandé est pire qu'un rappel qui manque.
    """
    session = SessionLocal()
    try:
        bilan = courriel.resumer(session)
        session.commit()
        if bilan.get("envoyes"):
            log.info("%d résumé(s) envoyé(s) par courriel", bilan["envoyes"])
        return bilan
    except Exception:
        session.rollback()
        log.exception("Échec de l'envoi des résumés")
        return {"envoyes": 0}
    finally:
        session.close()


def poser_les_rappels() -> int:
    """
    Les rappels d'échéance (§21.9), posés une fois par échéance.

    Le contrôle a lieu à chaque cycle et non une fois par jour : une échéance
    n'entre dans sa fenêtre qu'une seule fois, et l'empreinte de la notification
    empêche de la reposer — c'est elle qui fait la fréquence, pas l'horloge.
    """
    session = SessionLocal()
    try:
        poses = echeances.generer_rappels(session)
        session.commit()
        if poses:
            log.info("%d rappel(s) d'échéance posé(s)", poses)
        return poses
    except Exception:
        session.rollback()
        log.exception("Échec de la pose des rappels d'échéance")
        return 0
    finally:
        session.close()


def revoir_automatisations() -> dict:
    """
    Le déclencheur « quand une date est atteinte » (§21.8).

    Une seule passe pour toutes les règles de ce type, et chaque document n'est
    traité qu'une fois : la date, elle, revient tous les jours.
    """
    session = SessionLocal()
    try:
        bilan = automatisations.passer_en_revue(session)
        session.commit()
        if bilan["agis"]:
            log.info("Automatisations : %d document(s) traité(s) sur %d examiné(s)",
                     bilan["agis"], bilan["examines"])
        return bilan
    except Exception:
        session.rollback()
        log.exception("Échec de la revue des automatisations")
        return {"examines": 0, "agis": 0}
    finally:
        session.close()


def controler_integrite() -> dict:
    """
    Relit quelques archives et vérifie qu'elles n'ont pas bougé (§21.3).

    Le lot se règle depuis l'administration ; zéro l'arrête. Seules les anomalies
    sont journalisées : consigner « tout va bien » à chaque passage noierait le
    journal, et c'est le journal qu'on vient lire le jour où quelque chose cloche.
    """
    from . import reglages

    session = SessionLocal()
    try:
        lot = reglages.entier(session, "integrite_lot_par_passage")
        if lot <= 0:
            return {"controles": 0, "adoptees": 0, "anomalies": []}
        bilan = integrite.controler(session, lot)
        if bilan["anomalies"]:
            audit.journaliser(session, None, "integrite.anomalie", "document",
                              details={"documents": bilan["anomalies"][:50]})
            log.warning("Intégrité : %d archive(s) ne correspondent plus à leur empreinte",
                        len(bilan["anomalies"]))
        session.commit()
        return bilan
    except Exception:
        session.rollback()
        log.exception("Échec du contrôle d'intégrité")
        return {"controles": 0, "adoptees": 0, "anomalies": []}
    finally:
        session.close()


def purger_documents_supprimes() -> int:
    """
    Efface pour de bon les documents en corbeille depuis plus longtemps que la
    rétention réglée (§21.1). Zéro : jamais — c'est le réglage livré.

    Seule la **ligne** est supprimée ici. Le fichier suit tout seul : plus aucun
    document ne le référence, `purger_fichiers_orphelins()` le déplacera au
    passage suivant dans `storage/.corbeille/`, d'où il faut encore une décision
    humaine pour le perdre. Deux filets valent mieux qu'un quand la purge est
    automatique.
    """
    from . import reglages

    session = SessionLocal()
    try:
        jours = reglages.entier(session, "retention_documents_supprimes_jours")
        if jours <= 0:
            return 0
        limite = datetime.now() - timedelta(days=jours)
        anciens = (session.query(Document)
                   .filter(Document.date_suppression.isnot(None),
                           Document.date_suppression < limite)
                   .all())
        if not anciens:
            return 0
        details = [{"id": d.id, "nom_fichier": d.nom_fichier} for d in anciens]
        for document in anciens:
            session.delete(document)
        # Nommés un par un : après coup, c'est la seule trace de ce qui a existé.
        audit.journaliser(session, None, "documents.purge_corbeille", "document",
                          details={"nombre": len(anciens), "retention_jours": jours,
                                   "documents": details[:50]})
        session.commit()
        log.info(f"{len(anciens)} document(s) de la corbeille effacé(s) "
                 f"(plus de {jours} jours)")
        return len(anciens)
    except Exception:
        session.rollback()
        log.exception("Échec de la purge des documents supprimés")
        return 0
    finally:
        session.close()


def purger_jobs_anciens() -> int:
    """
    Supprime les travaux achevés depuis plus longtemps que la rétention réglée.

    Seuls les travaux terminés ou ignorés (doublons) sont concernés : ils n'ont
    plus rien à raconter. Un travail à classer, en erreur ou bloqué appelle une
    action et reste donc affiché tant qu'il n'a pas été traité — le purger
    reviendrait à faire disparaître un problème sans l'avoir résolu.

    Le délai se règle depuis l'administration (§19.11). Zéro : rien n'est purgé.
    """
    from . import reglages

    session = SessionLocal()
    try:
        jours = reglages.entier(session, "retention_jobs_jours")
        if jours <= 0:
            return 0
        limite = datetime.now() - timedelta(days=jours)
        anciens = (
            session.query(Job)
            .filter(Job.statut.in_(STATUTS_PURGEABLES))
            .filter(func.coalesce(Job.date_fin, Job.date_creation) < limite)
            .all()
        )
        if not anciens:
            return 0
        identifiants = [job.id for job in anciens]
        for job in anciens:
            session.delete(job)
        # Le fichier d'origine vivait le temps du travail : il part avec lui (§18.53).
        _effacer_originaux(identifiants)
        audit.journaliser(session, None, "jobs.purge_automatique", "job",
                          details={"nombre": len(anciens), "retention_jours": jours})
        session.commit()
        log.info(f"{len(anciens)} travail(aux) achevé(s) purgé(s) (plus de {jours} jours)")
        return len(anciens)
    except Exception:
        session.rollback()
        log.exception("Échec de la purge des travaux anciens")
        return 0
    finally:
        session.close()


def purger_verrous_expires() -> int:
    """
    Efface les verrous d'édition périmés (§17.21).

    L'API ignore déjà un verrou expiré : ce ménage ne change donc rien au
    comportement, il évite seulement que la table accumule des lignes mortes —
    une par fenêtre de modification jamais refermée proprement.
    """
    session = SessionLocal()
    try:
        supprimes = (
            session.query(VerrouDocument)
            .filter(VerrouDocument.date_expiration < datetime.now())
            .delete(synchronize_session=False)
        )
        session.commit()
        return supprimes
    except Exception:
        session.rollback()
        log.exception("Échec de la purge des verrous")
        return 0
    finally:
        session.close()


def purger_sessions_expirees() -> int:
    """
    Efface les sessions expirées ou fermées depuis plus d'une semaine (§17.2).

    La table garde une ligne par jeton délivré : sans ménage, elle grossirait
    indéfiniment. On laisse malgré tout une semaine de recul aux sessions
    fermées — c'est le délai pendant lequel on est susceptible de se demander
    « qui s'est connecté, et d'où ? » après un incident.
    """
    limite = datetime.now() - timedelta(days=7)
    session = SessionLocal()
    try:
        supprimees = (
            session.query(SessionOuverte)
            .filter(
                (SessionOuverte.date_expiration < limite)
                | (SessionOuverte.date_revocation.isnot(None)
                   & (SessionOuverte.date_revocation < limite))
            )
            .delete(synchronize_session=False)
        )
        session.commit()
        if supprimees:
            log.info(f"{supprimees} session(s) close(s) purgée(s)")
        return supprimees
    except Exception:
        session.rollback()
        log.exception("Échec de la purge des sessions")
        return 0
    finally:
        session.close()


def compresser_archives(lot: Optional[int] = None) -> dict:
    """
    Reprend, par petits lots, les documents archivés avant la mise en place de
    la compression (§17.8).

    Passer d'un coup sur toute une archive immobiliserait le serveur de travaux
    pendant des minutes et ferait travailler le disque au pire moment. On en
    traite quelques-uns à chaque cycle de maintenance : l'archive se tasse
    d'elle-même, sans que personne ne s'en aperçoive.

    `date_compression` marque ce qui a été examiné — succès **comme** refus. Un
    fichier que l'optimiseur n'a pas su réduire ne sera pas repris au passage
    suivant : il l'a déjà été, la réponse était non.
    """
    lot = config.COMPRESSION_LOT if lot is None else lot
    niveau = reglages_traitement()["optimisation"]
    if lot <= 0 or niveau <= 0:
        return {"traites": 0, "gagnes": 0}

    session = SessionLocal()
    try:
        candidats = (
            session.query(Document)
            .filter(Document.date_compression.is_(None),
                    # inutile de recompresser un fichier que la purge peut
                    # emporter demain (§21.1)
                    Document.date_suppression.is_(None))
            .order_by(Document.id)
            .limit(lot)
            .all()
        )
        traites, gagnes = 0, 0
        for document in candidats:
            chemin = document.chemin_stockage
            if not chemin or not os.path.exists(chemin):
                # fichier absent : inutile d'y revenir à chaque passage, mais on
                # ne prétend pas l'avoir compressé
                document.date_compression = datetime.now()
                continue
            try:
                bilan = compression.optimiser(chemin, niveau)
            except Exception:
                log.exception(f"Compression impossible pour {chemin}")
                document.date_compression = datetime.now()
                document.taille_octets = os.path.getsize(chemin)
                continue

            document.date_compression = datetime.now()
            document.taille_octets = bilan["apres"]
            # Le fichier vient d'être réécrit : sans cette ligne, le contrôle
            # d'intégrité signalerait comme altéré ce que nous avons nous-mêmes
            # modifié (§21.3).
            if bilan["remplace"]:
                integrite.poser(document, chemin)
            traites += 1
            if bilan["remplace"]:
                gagnes += bilan["avant"] - bilan["apres"]
                log.info(f"{Path(chemin).name} : {bilan['motif']} "
                         f"({bilan['avant'] // 1024} Ko → {bilan['apres'] // 1024} Ko)")

        if traites:
            audit.journaliser(session, None, "stockage.compression", "fichier",
                              details={"documents": traites,
                                       "octets_gagnes": gagnes,
                                       "niveau": niveau})
        session.commit()
        return {"traites": traites, "gagnes": gagnes}
    except Exception:
        session.rollback()
        log.exception("Échec de la reprise des archives")
        return {"traites": 0, "gagnes": 0}
    finally:
        session.close()


# Au-delà, une passe de reprise prendrait plus de temps qu'elle n'en fait gagner.
# Les suivants attendront la passe d'après : rien ne presse, ces documents sont
# déjà indexés.
MAX_REPRISES_PAR_PASSE = 50


def relancer_travaux_bloques() -> dict:
    """
    Reprend les travaux bloqués, sans qu'on ait à le demander (§18.45).

    Un travail bloqué signale un document auquel il manque un champ exigé par sa
    catégorie. Jusqu'ici il attendait un rejeu manuel — ce qui obligeait, après
    avoir corrigé une expression régulière, à retourner cliquer travail par
    travail. La correction est faite pour ces documents-là : c'est au serveur de
    repasser.

    **Sans océrisation** : le texte reconnu ne change pas, seules les règles
    changent. Une passe coûte donc quelques expressions régulières sur un texte
    déjà en base.

    **Sans défaire ce qui a été fait à la main** : une valeur saisie depuis la
    fiche est laissée en place (`app/regex_engine.py` ne retouche pas une
    métadonnée sans règle d'origine), et le classement ne bouge pas — il vient
    du dossier de dépôt (§19.3), pas des règles.

    **Sans rien écrire quand rien ne change** : un travail qui reste bloqué n'est
    pas touché — ni son compteur de tentatives, ni sa date. Sans cela, le journal
    et l'écran de suivi se rempliraient toutes les cinq minutes d'un événement
    qui ne raconte rien.
    """
    session = SessionLocal()
    bilan = {"examines": 0, "debloques": 0, "abandonnes": 0}
    try:
        bloques = (session.query(Job)
                   .filter(Job.statut == "bloque", Job.document_id.isnot(None))
                   .order_by(Job.id.asc())
                   .limit(MAX_REPRISES_PAR_PASSE)
                   .all())
        for job in bloques:
            document = session.get(Document, job.document_id)
            if not document:
                continue
            # La machine a-t-elle déjà cherché en vain assez de fois ? (§21.15)
            # Le travail reste bloqué — il appelle une action humaine — mais on
            # cesse de refaire toutes les cinq minutes un calcul dont on sait
            # qu'il ne donnera rien tant que rien n'aura changé. Corriger une
            # règle ou rejouer le travail remet le compteur à zéro.
            if _palier_atteint(session, job.reprises_auto):
                bilan["abandonnes"] = bilan.get("abandonnes", 0) + 1
                continue
            job.reprises_auto = (job.reprises_auto or 0) + 1
            bilan["examines"] += 1
            try:
                # `appliquer_regles` ne touche plus au classement depuis le
                # §19.3 : il vient du dossier de dépôt, et rien ne le contredit
                # après coup. Le garde-fou qui remettait la catégorie en place
                # après chaque reprise n'a donc plus lieu d'être.
                appliquer_regles(document, session)
                references_auto.remplir(session, document)
                session.flush()
                session.refresh(document)
                manquants = _etape_conformite(session, document)
            except Exception:
                session.rollback()
                log.exception("Reprise impossible pour le travail %s", job.id)
                continue

            if manquants:
                # Toujours incomplet : le travail reste affiché tel quel, ce qui
                # est le but — il appelle une action humaine. Seul son compteur
                # de reprises avance, pour que la machine sache s'arrêter.
                if _palier_atteint(session, job.reprises_auto):
                    job.diagnostic = (
                        "La reprise automatique a cessé : les règles ne trouvent pas ce "
                        "qui manque. Complétez les champs depuis la fiche, ou corrigez "
                        "une règle et demandez un rejeu — la reprise repartira alors.")
                    audit.journaliser(session, None, "job.reprise_abandonnee", "job", job.id,
                                      details={"document_id": document.id,
                                               "reprises": job.reprises_auto})
                    log.info("Travail %s : la reprise automatique renonce après %s passes",
                             job.id, job.reprises_auto)
                session.commit()
                continue

            job.statut = "termine"
            job.etape = ETAPE_CONFORMITE
            job.message_erreur = None
            job.diagnostic = ("Complété par une reprise automatique : les règles "
                              "d'extraction ont trouvé ce qui manquait.")
            job.date_fin = datetime.now()
            bilan["debloques"] += 1
            audit.journaliser(session, None, "job.reprise_automatique", "job", job.id,
                              details={"document_id": document.id,
                                       "nom_fichier": job.nom_fichier})
            session.commit()
            log.info("Travail %s débloqué par une reprise automatique (document %s)",
                     job.id, document.id)
        return bilan
    except Exception:
        session.rollback()
        log.exception("Échec de la reprise des travaux bloqués")
        return bilan
    finally:
        session.close()


def purger_journal_ancien() -> int:
    """
    Efface les entrées d'audit plus anciennes que la rétention réglée (§18.22).
    Zéro : rien n'est purgé — la purge reste alors une décision prise à la main,
    depuis le journal lui-même.

    **L'historique des documents n'est jamais touché** : ces entrées racontent la
    vie d'une fiche, et se relisent des années plus tard sur la fiche même. C'est
    la règle posée au §17.24, et elle vaut aussi pour une purge automatique.
    """
    from . import reglages
    from .db import JournalAudit

    session = SessionLocal()
    try:
        nombre = 0
        # Les consultations (§21.16) ont leur propre rétention : elles sont
        # nombreuses, vieillissent vite, et n'ont pas la même valeur que le reste
        # de l'histoire d'un document — qui, lui, n'est jamais purgé.
        jours_lectures = reglages.entier(session, "retention_consultations_jours")
        if jours_lectures > 0:
            nombre += (session.query(JournalAudit)
                       .filter(JournalAudit.date_evenement
                               < datetime.now() - timedelta(days=jours_lectures),
                               JournalAudit.action == audit.CONSULTATION)
                       .delete(synchronize_session=False))

        jours = reglages.entier(session, "retention_journal_jours")
        if jours <= 0:
            if nombre:
                session.commit()
            return int(nombre)
        limite = datetime.now() - timedelta(days=jours)
        nombre += (session.query(JournalAudit)
                   .filter(JournalAudit.date_evenement < limite,
                           JournalAudit.objet_type != "document")
                   .delete(synchronize_session=False))
        if nombre:
            audit.journaliser(session, None, "audit.purge_automatique", "journal", None,
                              details={"entrees_supprimees": int(nombre),
                                       "retention_jours": jours})
            session.commit()
            log.info(f"{nombre} entrée(s) de journal purgée(s) (plus de {jours} jours)")
        return int(nombre)
    except Exception:
        session.rollback()
        log.exception("Échec de la purge du journal")
        return 0
    finally:
        session.close()


def purger_corbeille_ancienne() -> int:
    """
    Détruit les fichiers en corbeille depuis plus longtemps que la rétention
    réglée. Zéro : jamais — la corbeille est le dernier filet avant la perte
    définitive, et l'automatiser sans qu'on l'ait demandé serait le retirer.
    """
    from . import reglages

    session = SessionLocal()
    try:
        jours = reglages.entier(session, "retention_corbeille_jours")
    except Exception:
        log.exception("Rétention de corbeille illisible")
        return 0
    finally:
        session.close()

    if jours <= 0 or not os.path.isdir(config.CORBEILLE_FOLDER):
        return 0

    limite = time.time() - jours * 86400
    detruits = 0
    for nom in os.listdir(config.CORBEILLE_FOLDER):
        chemin = os.path.join(config.CORBEILLE_FOLDER, nom)
        try:
            if os.path.isfile(chemin) and os.path.getmtime(chemin) < limite:
                os.remove(chemin)
                detruits += 1
        except OSError:
            log.exception(f"Impossible de détruire {chemin}")

    if detruits:
        session = SessionLocal()
        try:
            audit.journaliser(session, None, "corbeille.purge_automatique", "corbeille", None,
                              details={"fichiers_detruits": detruits, "retention_jours": jours})
            session.commit()
        finally:
            session.close()
        log.info(f"{detruits} fichier(s) détruit(s) de la corbeille (plus de {jours} jours)")
    return detruits


def purger_fichiers_orphelins() -> int:
    """
    Déplace en corbeille les PDF de `storage/` que plus aucun document ne
    référence. Supprimer un document dans l'interface retire l'entrée
    immédiatement, et son fichier au passage suivant d'ici.

    C'est le worker qui s'en charge, et non l'API : celle-ci monte `storage/`
    en lecture seule, pour qu'aucune faille côté API ne puisse toucher aux
    archives.

    Les fichiers ne sont **pas effacés** mais déplacés dans
    `storage/.corbeille/AAAA-MM-JJ/`. Un balayage qui se tromperait — base
    restaurée depuis une sauvegarde plus ancienne, fichiers déposés à la main
    dans `storage/` — détruirait sinon des archives de façon irrémédiable.
    Vider la corbeille reste une décision humaine.

    Deux précautions supplémentaires :
      - les fichiers récents (moins de DELAI_GRACE_PURGE secondes) sont
        épargnés : le worker écrit le PDF *avant* d'insérer la ligne en base,
        un balayage tombant entre les deux emporterait un import en cours ;
      - chaque déplacement est journalisé, sans quoi la disparition d'un
        fichier serait intraçable.
    """
    corbeille = Path(config.CORBEILLE_FOLDER)
    session = SessionLocal()
    try:
        references = {
            chemin for (chemin,) in session.query(Document.chemin_stockage).all() if chemin
        }
        limite = time.time() - DELAI_GRACE_PURGE
        deplaces = 0
        for fichier in Path(config.STORAGE_FOLDER).rglob("*"):
            if not fichier.is_file() or str(fichier) in references:
                continue
            if corbeille in fichier.parents:
                continue  # déjà en corbeille
            try:
                if fichier.stat().st_mtime > limite:
                    continue  # trop récent : sans doute un import en cours
                dossier = corbeille / time.strftime("%Y-%m-%d")
                dossier.mkdir(parents=True, exist_ok=True)
                destination = dossier / fichier.name
                if destination.exists():
                    destination = dossier / f"{fichier.stem}_{int(time.time())}{fichier.suffix}"
                shutil.move(str(fichier), str(destination))
            except OSError:
                log.exception(f"Impossible de mettre en corbeille le fichier orphelin {fichier}")
                continue
            deplaces += 1
            log.info(f"Fichier orphelin mis en corbeille : {fichier} -> {destination}")
            audit.journaliser(
                session, None, "stockage.orphelin_en_corbeille", "fichier",
                details={"chemin_origine": str(fichier), "chemin_corbeille": str(destination)},
            )
        if deplaces:
            session.commit()
        return deplaces
    except Exception:
        session.rollback()
        log.exception("Échec du balayage des fichiers orphelins")
        return 0
    finally:
        session.close()


def synchroniser_depots() -> dict:
    """Met les dossiers de dépôt en accord avec les types déclarés (§19.2)."""
    session = SessionLocal()
    try:
        return depots.synchroniser(session)
    except Exception:
        session.rollback()
        log.exception("Les dossiers de dépôt n'ont pas pu être mis en place")
        return {"crees": 0, "attribues": 0}
    finally:
        session.close()


def fichiers_en_attente() -> list[Path]:
    """
    Tout ce qui attend d'être traité, à la racine comme dans les dossiers de
    dépôt. Ordonné pour que le résultat ne dépende pas du système de fichiers.
    """
    racine = Path(config.OCR_WAIT_FOLDER)
    if not racine.is_dir():
        return []
    return sorted((f for f in racine.rglob("*") if f.is_file()), key=str)


class ScanHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        # l'attente de fin d'écriture est gérée par _attendre_fichier_stable()
        confier(traiter_fichier, Path(event.src_path))


def main():
    log.info("Vérification de la disponibilité de la base de données...")
    attendre_base()
    # Pas de `Base.metadata.create_all()` ici : il s'exécutait avant les migrations
    # et créait les tables d'après le modèle Python, sans les clauses DEFAULT du
    # schéma SQL — le `CREATE TABLE IF NOT EXISTS` de la migration devenait alors un
    # no-op, et des colonnes se retrouvaient à NULL (cf. migration 012).
    # `db/schema.sql` (base vierge) et `db/migrations/` (base existante) sont
    # désormais l'unique source de vérité du schéma.
    appliquer_migrations()
    Path(config.OCR_WAIT_FOLDER).mkdir(parents=True, exist_ok=True)
    Path(config.STORAGE_FOLDER).mkdir(parents=True, exist_ok=True)

    # Un dossier de dépôt par type de document (§19.2), remis en place à chaque
    # démarrage : c'est le filet qui rattrape un dossier effacé à la main, une
    # base restaurée, ou un type créé pendant que le serveur était arrêté.
    bilan = synchroniser_depots()
    log.info(f"Dossiers de dépôt : {bilan['crees']} créé(s), "
             f"{bilan['attribues']} attribué(s)")

    attente = fichiers_en_attente()
    log.info(f"Dossier surveillé : {config.OCR_WAIT_FOLDER} "
             f"({len(attente)} fichier(s) déjà présent(s))")

    # Traite les fichiers déjà présents au démarrage. C'est le cas qui pèse le
    # plus lourd — la reprise de l'existant d'un foyer — et donc celui qui
    # profite le plus du pool.
    global _executeur, _taille_pool
    _taille_pool = parallelisme_voulu()
    _executeur = ThreadPoolExecutor(max_workers=_taille_pool,
                                    thread_name_prefix="traitement")
    log.info(f"Traitements simultanés : {_taille_pool}")
    for f in attente:
        confier(traiter_fichier, f)

    # PollingObserver (plutôt que l'Observer basé sur inotify) : plus lent de
    # quelques secondes, mais fonctionne de façon fiable à travers les bind
    # mounts Docker sur macOS/Windows et les partages réseau (SMB/NFS), là où
    # inotify ne propage pas toujours les événements du système de fichiers.
    observer = PollingObserver(timeout=2)
    # Récursive depuis le §19.2 : les fichiers arrivent maintenant dans le
    # dossier de leur type, pas à la racine.
    observer.schedule(ScanHandler(), config.OCR_WAIT_FOLDER, recursive=True)
    observer.start()
    log.info(f"Surveillance de {config.OCR_WAIT_FOLDER} démarrée...")

    prochaine_purge = time.time() + INTERVALLE_PURGE
    prochain_rejeu = time.time() + INTERVALLE_REJEU
    try:
        while True:
            time.sleep(2)
            if time.time() >= prochain_rejeu:
                prochain_rejeu = time.time() + INTERVALLE_REJEU
                traiter_rejeux()
                traiter_rejets()
                traiter_depots_manuels()
                construire_exports_modele()
                # Relu ici et non à la purge : régler ce nombre depuis l'écran
                # doit valoir tout de suite, pas au prochain quart d'heure.
                ajuster_le_pool()
            if time.time() >= prochaine_purge:
                prochaine_purge = time.time() + INTERVALLE_PURGE
                purger_fichiers_orphelins()
                purger_jobs_anciens()
                purger_originaux_orphelins()
                purger_apercus_orphelins()
                purger_exports_modele()
                purger_exemples_apprentissage()
                verifier_conformite_rangee()
                sauvegarder_si_besoin()
                purger_sessions_expirees()
                purger_verrous_expires()
                purger_journal_ancien()
                purger_corbeille_ancienne()
                purger_documents_supprimes()
                controler_integrite()
                revoir_automatisations()
                poser_les_rappels()
                envoyer_les_resumes()
                relancer_travaux_bloques()
                synchroniser_depots()
                compresser_archives()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
