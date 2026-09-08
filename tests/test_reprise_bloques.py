"""
Reprise automatique des travaux bloqués (§18.45).

Un travail bloqué signale un document auquel il manque un champ exigé par sa
catégorie. Il attendait un rejeu demandé à la main : après avoir corrigé une
expression régulière, il fallait retourner cliquer travail par travail. La
correction est faite pour ces documents-là — c'est au serveur de repasser.

Ce que ces tests surveillent : que la reprise **débloque** quand la correction
suffit, qu'elle **ne touche à rien** quand elle ne suffit pas, et qu'elle
n'écrase jamais une valeur saisie par une personne.
"""
import pytest

from tests.conftest import jeu_generique

from app import worker
from app.db import (
    Categorie,
    Document,
    Job,
    Metadonnee,
    RegleChampCategorie,
    RegleExtraction,
    SessionLocal,
)

TEXTE = "FOURNISSEUR\nFacture no 2026-00931 du 04/09/2026\nTOTAL TTC : 74,20 EUR\n"


@pytest.fixture
def document_bloque(base_de_test):
    """Un document indexé auquel sa catégorie réclame un champ qu'aucune règle ne lit."""
    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_repr%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_repr%")).delete(
            synchronize_session=False)

        categorie = Categorie(nom="_RepriseTest", ordre=970)
        session.add(categorie)
        session.flush()
        session.add(RegleChampCategorie(
            categorie_id=categorie.id, champ="meta:reference_dossier",
            libelle="Référence du dossier", obligatoire=True, ordre=10))

        document = Document(nom_fichier="_repr_facture.pdf", chemin_stockage="/x.pdf",
                            hash_sha256="reprise".ljust(64, "r"), texte_ocr=TEXTE,
                            statut="incomplet", categorie_id=categorie.id)
        session.add(document)
        session.flush()
        job = Job(nom_fichier="_repr_facture.pdf", statut="bloque", etape="conformite",
                  document_id=document.id,
                  message_erreur="Champs attendus manquants : Référence du dossier")
        session.add(job)
        session.commit()
        contexte = {"categorie": categorie.id, "document": document.id, "job": job.id}
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(RegleExtraction).filter(
            RegleExtraction.nom.like("_repr%")).delete(synchronize_session=False)
        session.query(Job).filter(Job.nom_fichier.like("_repr%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_repr%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter_by(nom="_RepriseTest").delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_un_travail_qui_manque_toujours_dun_champ_nest_pas_touche(document_bloque):
    """
    Il reste affiché, et c'est le but : il appelle une action humaine. Y toucher
    à chaque passe remplirait le suivi d'un événement qui ne raconte rien.
    """
    session = SessionLocal()
    try:
        avant = session.get(Job, document_bloque["job"])
        tentatives, date_fin = avant.tentatives, avant.date_fin
    finally:
        session.close()

    bilan = worker.relancer_travaux_bloques()
    assert bilan["examines"] >= 1
    assert bilan["debloques"] == 0

    session = SessionLocal()
    try:
        apres = session.get(Job, document_bloque["job"])
        assert apres.statut == "bloque"
        assert apres.tentatives == tentatives
        assert apres.date_fin == date_fin
    finally:
        session.close()


def test_une_regle_corrigee_debloque_le_travail_sans_intervention(document_bloque):
    """
    Le service rendu : l'administrateur corrige l'expression, et le document
    rejoint le registre à la passe suivante — sans avoir à retrouver le travail
    et à cliquer dessus.
    """
    session = SessionLocal()
    try:
        # La règle vit dans le jeu générique du type du document (§19.6) : une
        # règle qui vaudrait pour tout n'existe plus.
        profil = jeu_generique(session, document_bloque["categorie"])
        session.add(RegleExtraction(
            profil_id=profil.id,
            nom="_repr reference", champ_cible="reference_dossier",
            pattern=r"(?i)facture\s+no\s+(\S+)", type_champ="texte",
            actif=True, priorite=1))
        session.commit()
    finally:
        session.close()

    bilan = worker.relancer_travaux_bloques()
    assert bilan["debloques"] == 1

    session = SessionLocal()
    try:
        job = session.get(Job, document_bloque["job"])
        assert job.statut == "termine"
        assert "reprise automatique" in (job.diagnostic or "")
        valeurs = {m.cle: m.valeur for m in session.query(Metadonnee).filter_by(
            document_id=document_bloque["document"])}
        assert valeurs.get("reference_dossier") == "2026-00931"
    finally:
        session.close()


def test_la_reprise_nefface_pas_une_correction_manuelle(document_bloque):
    """
    Le garde-fou : quelqu'un a corrigé la valeur depuis la fiche, la reprise
    passe toutes les cinq minutes. Elle ne doit pas défaire ce travail.
    """
    session = SessionLocal()
    try:
        # correction manuelle : `regle_id` nul, c'est ce qui la signale
        session.add(Metadonnee(document_id=document_bloque["document"],
                               cle="reference_dossier", valeur="corrigé à la main",
                               regle_id=None))
        # La règle vit dans le jeu générique du type du document (§19.6) : une
        # règle qui vaudrait pour tout n'existe plus.
        profil = jeu_generique(session, document_bloque["categorie"])
        session.add(RegleExtraction(
            profil_id=profil.id,
            nom="_repr reference", champ_cible="reference_dossier",
            pattern=r"(?i)facture\s+no\s+(\S+)", type_champ="texte",
            actif=True, priorite=1))
        session.commit()
    finally:
        session.close()

    worker.relancer_travaux_bloques()

    session = SessionLocal()
    try:
        valeur = (session.query(Metadonnee)
                  .filter_by(document_id=document_bloque["document"],
                             cle="reference_dossier").one().valeur)
        assert valeur == "corrigé à la main"
    finally:
        session.close()


def test_la_reprise_est_bornee(document_bloque):
    """
    Une passe ne doit pas devenir un travail en soi : au-delà d'un certain
    nombre, les suivants attendent la passe d'après — rien ne presse, ces
    documents sont déjà indexés.
    """
    assert worker.MAX_REPRISES_PAR_PASSE <= 200
    bilan = worker.relancer_travaux_bloques()
    assert bilan["examines"] <= worker.MAX_REPRISES_PAR_PASSE
