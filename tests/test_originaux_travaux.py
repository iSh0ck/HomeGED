"""
Conservation du fichier reçu, le temps que vit son travail (§18.53).

Le PDF archivé n'est pas une copie du fichier déposé : l'océrisation lui ajoute
une couche de texte, la compression le réécrit. Jusqu'ici le fichier reçu était
supprimé dès que le traitement réussissait, et seuls les échecs étaient mis de
côté. Ce qui a été déposé n'existait donc plus nulle part.
"""
import os

import pytest

from app import config, worker
from app.db import Job, SessionLocal


@pytest.fixture
def dossier_travaux(tmp_path, monkeypatch):
    """Un dossier de conservation à soi : les tests n'écrivent pas dans /data."""
    dossier = tmp_path / "travaux"
    monkeypatch.setattr(config, "TRAVAUX_FOLDER", str(dossier))
    return dossier


@pytest.fixture
def travail(base_de_test):
    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_orig%")).delete(
            synchronize_session=False)
        job = Job(nom_fichier="_orig_facture.pdf", statut="termine")
        session.add(job)
        session.commit()
        identifiant = job.id
    finally:
        session.close()

    yield identifiant

    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_orig%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_le_fichier_recu_rejoint_son_travail(travail, dossier_travaux, tmp_path):
    depot = tmp_path / "_orig_facture.pdf"
    depot.write_bytes(b"%PDF-1.7 recu")

    conserve = worker._conserver_original(travail, depot)

    assert conserve is not None
    assert not depot.exists(), "le fichier quitte le dossier de dépôt"
    assert os.path.isfile(conserve)
    from pathlib import Path
    assert Path(conserve).read_bytes() == b"%PDF-1.7 recu", \
        "c'est bien l'octet reçu qui est gardé, pas une version retraitée"
    assert str(dossier_travaux / str(travail)) in conserve


def test_un_rejeu_ne_deplace_pas_ce_qui_est_deja_conserve(travail, dossier_travaux, tmp_path):
    depot = tmp_path / "_orig_facture.pdf"
    depot.write_bytes(b"%PDF")
    premier = worker._conserver_original(travail, depot)

    from pathlib import Path
    second = worker._conserver_original(travail, Path(premier))
    assert second == premier, "un rejeu retraite le fichier sur place"


def test_deux_fichiers_homonymes_ne_secrasent_pas(travail, dossier_travaux, tmp_path):
    for contenu in (b"premier", b"second"):
        depot = tmp_path / "_orig_facture.pdf"
        depot.write_bytes(contenu)
        worker._conserver_original(travail, depot)

    gardes = list((dossier_travaux / str(travail)).iterdir())
    assert len(gardes) == 2, "un homonyme ne doit pas remplacer ce qui était là"


def test_le_fichier_part_avec_la_purge_du_travail(travail, dossier_travaux, tmp_path):
    """
    C'est la règle voulue : « tant que la tâche n'est pas purgée, on conserve le
    document original ». La réciproque compte autant — un fichier que plus rien
    ne réclame ne doit pas rester sur le disque.
    """
    depot = tmp_path / "_orig_facture.pdf"
    depot.write_bytes(b"%PDF")
    worker._conserver_original(travail, depot)
    assert (dossier_travaux / str(travail)).is_dir()

    worker._effacer_originaux([travail])
    assert not (dossier_travaux / str(travail)).exists()


def test_les_dossiers_sans_travail_sont_balayes(travail, dossier_travaux, tmp_path):
    """
    Base restaurée, travail effacé à la main : un dossier que plus aucun travail
    ne réclame ne s'effacerait jamais tout seul. C'est ce genre d'oubli qui
    laisse traîner un document qu'on croyait supprimé.
    """
    depot = tmp_path / "_orig_facture.pdf"
    depot.write_bytes(b"%PDF")
    worker._conserver_original(travail, depot)

    orphelin = dossier_travaux / "999999"
    orphelin.mkdir(parents=True)
    (orphelin / "oublie.pdf").write_bytes(b"%PDF")

    assert worker.purger_originaux_orphelins() == 1
    assert not orphelin.exists()
    assert (dossier_travaux / str(travail)).is_dir(), \
        "le dossier d'un travail encore suivi ne doit pas être balayé"


# ------------------------------------------------------------------
# Le fichier reçu se **regarde** (§18.53)
#
# Défaut signalé en service : « Examiner » téléchargeait un fichier sans
# extension au lieu d'afficher la page. Le fichier était servi en
# `application/octet-stream` et en pièce jointe ; le navigateur, à qui l'on
# demandait de l'afficher, faisait la seule chose qu'on lui permettait — le
# télécharger, et depuis une URL d'objet, donc sans nom ni extension.
# ------------------------------------------------------------------

def _travail_avec_fichier(nom, contenu, tmp_path):
    """Un travail dont le fichier reçu est encore là, sous le nom donné."""
    fichier = tmp_path / nom
    fichier.write_bytes(contenu)
    session = SessionLocal()
    try:
        job = Job(nom_fichier=nom, statut="termine", chemin_source=str(fichier))
        session.add(job)
        session.commit()
        return job.id
    finally:
        session.close()


def test_le_fichier_recu_sannonce_comme_un_pdf(client, base_de_test, tmp_path):
    identifiant = _travail_avec_fichier("_orig_a_voir.pdf", b"%PDF-1.4 ...", tmp_path)
    reponse = client.get(f"/admin/jobs/{identifiant}/fichier")

    assert reponse.status_code == 200, reponse.text
    assert reponse.headers["content-type"] == "application/pdf"
    assert reponse.headers["content-disposition"].startswith("inline"), \
        "en pièce jointe, le navigateur télécharge au lieu d'afficher"


def test_une_image_recue_garde_son_type(client, base_de_test, tmp_path):
    """Tout ce qui arrive n'est pas un PDF : un scan est souvent un JPEG, et lui
    annoncer « application/pdf » le renverrait aussi aux téléchargements."""
    identifiant = _travail_avec_fichier("_orig_scan.JPG", b"\xff\xd8\xff", tmp_path)
    reponse = client.get(f"/admin/jobs/{identifiant}/fichier")

    assert reponse.status_code == 200, reponse.text
    assert reponse.headers["content-type"] == "image/jpeg"


def test_un_nom_accentue_ne_casse_pas_la_reponse(client, base_de_test, tmp_path):
    """Les en-têtes HTTP sont en latin-1 : « reçu.pdf » y casserait la réponse
    entière si on l'y écrivait tel quel."""
    identifiant = _travail_avec_fichier("_orig_reçu_été.pdf", b"%PDF-1.4", tmp_path)
    reponse = client.get(f"/admin/jobs/{identifiant}/fichier")

    assert reponse.status_code == 200, reponse.text
    reponse.headers["content-disposition"].encode("latin-1")   # ne doit pas lever


def test_le_fichier_a_classer_sannonce_aussi(client, base_de_test, tmp_path):
    """Le Centre d'analyse montre le même fichier par la même mécanique : ce qui
    valait pour le serveur de travaux vaut pour lui."""
    fichier = tmp_path / "_orig_a_classer.pdf"
    fichier.write_bytes(b"%PDF-1.4")
    session = SessionLocal()
    try:
        job = Job(nom_fichier="_orig_a_classer.pdf", statut="a_classer",
                  chemin_source=str(fichier))
        session.add(job)
        session.commit()
        identifiant = job.id
    finally:
        session.close()

    reponse = client.get(f"/a-classer/{identifiant}/fichier")
    assert reponse.status_code == 200, reponse.text
    assert reponse.headers["content-type"] == "application/pdf"
    assert reponse.headers["content-disposition"].startswith("inline")


def test_supprimer_un_travail_emporte_son_fichier(client, base_de_test, dossier_travaux):
    """
    La fenêtre de confirmation l'annonce — « le fichier reçu part avec la
    tâche » —, mais la suppression ne retirait que la ligne : le fichier
    attendait le balayage des orphelins, jusqu'à cinq minutes plus tard. Une
    promesse tenue en différé ne se vérifie pas.
    """
    session = SessionLocal()
    try:
        job = Job(nom_fichier="_orig_a_effacer.pdf", statut="termine")
        session.add(job)
        session.commit()
        identifiant = job.id
    finally:
        session.close()

    dossier = dossier_travaux / str(identifiant)
    dossier.mkdir(parents=True)
    (dossier / "_orig_a_effacer.pdf").write_bytes(b"%PDF-1.4")

    reponse = client.delete(f"/admin/jobs/{identifiant}")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["fichier_recu_efface"] is True
    assert not dossier.exists(), "le fichier reçu part avec la tâche"


def test_la_suppression_groupee_emporte_aussi_les_fichiers(client, base_de_test,
                                                           dossier_travaux):
    """Deux chemins de suppression à l'écran, une seule règle : le second ne doit
    pas être celui qui oublie."""
    identifiants = []
    session = SessionLocal()
    try:
        for suffixe in ("un", "deux"):
            job = Job(nom_fichier=f"_orig_groupe_{suffixe}.pdf", statut="termine")
            session.add(job)
            session.flush()
            identifiants.append(job.id)
        session.commit()
    finally:
        session.close()

    for identifiant in identifiants:
        dossier = dossier_travaux / str(identifiant)
        dossier.mkdir(parents=True)
        (dossier / "recu.pdf").write_bytes(b"%PDF-1.4")

    reponse = client.post("/admin/jobs/actions",
                          json={"ids": identifiants, "action": "supprimer"})
    assert reponse.status_code == 200, reponse.text
    assert sorted(reponse.json()["traites"]) == sorted(identifiants)
    for identifiant in identifiants:
        assert not (dossier_travaux / str(identifiant)).exists()


def test_un_travail_sans_fichier_conserve_se_supprime_quand_meme(client, base_de_test,
                                                                 dossier_travaux):
    """Les travaux d'avant le §18.53 n'en ont pas : l'absence n'est pas une erreur."""
    session = SessionLocal()
    try:
        job = Job(nom_fichier="_orig_sans_fichier.pdf", statut="termine")
        session.add(job)
        session.commit()
        identifiant = job.id
    finally:
        session.close()

    reponse = client.delete(f"/admin/jobs/{identifiant}")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["fichier_recu_efface"] is False
