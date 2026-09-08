"""
Erreur récupérable ou définitive (§21.15).

Nous reprenions les travaux indéfiniment : toutes les cinq minutes, pour
toujours, y compris ceux que rien ne débloquera jamais. Un palier sépare
désormais ce que la machine peut encore tenter de ce qu'elle a cessé de tenter —
et l'écran ne dit plus la même chose des deux.

Ces tests portent sur le palier lui-même : quand il s'applique, quand il ne
s'applique pas, et ce qui remet les compteurs à zéro.
"""
import pytest

from app import reglages, worker
from app.db import Categorie, Document, Job, SessionLocal


def _regler(palier):
    session = SessionLocal()
    try:
        reglages.enregistrer(session, {"travaux_tentatives_max": str(palier)})
        session.commit()
    finally:
        session.close()


@pytest.fixture
def palier_a_trois(base_de_test):
    _regler(3)
    yield 3
    _regler(5)


def test_le_palier_arrete_les_tentatives(palier_a_trois):
    session = SessionLocal()
    try:
        assert worker._palier_atteint(session, 2) is False
        assert worker._palier_atteint(session, 3) is True
        assert worker._palier_atteint(session, 9) is True
    finally:
        session.close()


def test_zero_veut_dire_quon_nabandonne_jamais(base_de_test):
    """C'était le comportement d'avant : il reste disponible pour qui le préfère."""
    _regler(0)
    session = SessionLocal()
    try:
        assert worker._palier_atteint(session, 1000) is False
    finally:
        session.close()
        _regler(5)


@pytest.fixture
def travail_bloque(base_de_test):
    """Un travail bloqué sur un document à qui il manque un champ exigé."""
    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_ec%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_ec%")).delete(
            synchronize_session=False)
        from app.db import RegleChampCategorie

        session.query(Categorie).filter(Categorie.nom == "_EcType").delete()
        type_doc = Categorie(nom="_EcType", nature="type", ordre=970)
        session.add(type_doc)
        session.flush()
        # Un champ que rien ne remplira jamais : c'est le cas que le palier vise —
        # la reprise peut repasser cent fois, elle ne le trouvera pas.
        session.add(RegleChampCategorie(categorie_id=type_doc.id,
                                        champ="meta:_ec_introuvable",
                                        libelle="Introuvable", obligatoire=True, ordre=10))
        document = Document(nom_fichier="_ec_doc.pdf", chemin_stockage="/tmp/_ec_doc.pdf",
                            hash_sha256="_ec".ljust(64, "e"), texte_ocr="rien d'utile",
                            statut="incomplet", categorie_id=type_doc.id)
        session.add(document)
        session.flush()
        job = Job(nom_fichier="_ec_doc.pdf", statut="bloque", document_id=document.id,
                  message_erreur="Champs attendus manquants : Montant TTC")
        session.add(job)
        session.commit()
        identifiants = (job.id, document.id)
    finally:
        session.close()

    yield identifiants

    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_ec%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_ec%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom == "_EcType").delete()
        session.commit()
    finally:
        session.close()


def test_la_reprise_automatique_finit_par_renoncer(travail_bloque, palier_a_trois):
    """
    Le travail reste bloqué — il appelle une action humaine — mais la machine
    cesse de refaire toutes les cinq minutes un calcul dont on sait qu'il ne
    donnera rien tant que rien n'aura changé.
    """
    job_id, _ = travail_bloque
    for _ in range(5):
        worker.relancer_travaux_bloques()

    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        assert job.statut == "bloque", "il reste affiché : c'est à un humain de jouer"
        assert job.reprises_auto == 3, "on s'arrête au palier, on ne compte pas au-delà"
        assert "cessé" in (job.diagnostic or ""), "et l'écran doit le dire"
    finally:
        session.close()


def test_un_rejeu_demande_remet_les_compteurs_a_zero(client, travail_bloque,
                                                     palier_a_trois):
    """C'est ce qui rouvre la porte : on a corrigé quelque chose, on redemande."""
    job_id, _ = travail_bloque
    for _ in range(5):
        worker.relancer_travaux_bloques()

    reponse = client.post(f"/admin/jobs/{job_id}/rejouer")
    assert reponse.status_code == 200, reponse.text

    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        assert job.reprises_auto == 0
        assert job.tentatives == 0
        assert job.rejouer_demande is True
    finally:
        session.close()


def test_un_travail_en_echec_reste_rejouable(client, base_de_test, tmp_path):
    """
    L'abandon est celui de la machine, pas celui de l'utilisateur : refuser le
    rejeu enfermerait un document sans autre issue que la base de données.
    """
    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_ec%")).delete(
            synchronize_session=False)
        recu = tmp_path / "_ec_perdu.pdf"
        recu.write_bytes(b"%PDF-1.4")
        job = Job(nom_fichier="_ec_perdu.pdf", statut="echec", tentatives=9,
                  chemin_source=str(recu), message_erreur="PDF illisible")
        session.add(job)
        session.commit()
        identifiant = job.id
    finally:
        session.close()

    try:
        reponse = client.post(f"/admin/jobs/{identifiant}/rejouer")
        assert reponse.status_code == 200, reponse.text
    finally:
        session = SessionLocal()
        session.query(Job).filter(Job.nom_fichier.like("_ec%")).delete(
            synchronize_session=False)
        session.commit()
        session.close()
