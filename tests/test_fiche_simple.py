"""
La fiche simple (§22.1).

Elle remplace la « fiche de liaison », qui s'adossait à une table du foyer et
demandait trois réglages avant de montrer quoi que ce soit. Une fiche simple ne
s'adosse à rien : elle porte des documents comme un type de document, à une
différence près — **rien n'y entre tout seul**. Pas de dossier sous `ocr_wait`,
donc pas de dépôt automatique : on y glisse un fichier à la main et l'on remplit
ses valeurs.

C'est ce qui convient à ce qu'un foyer reçoit rarement et qu'aucune règle ne
saurait lire : un acte notarié, une carte grise, un contrat signé.
"""
from pathlib import Path

import pytest

from app import config, depots, worker
from app.db import Categorie, Job, SessionLocal

# Un PDF minimal : la route ne lit pas le contenu — c'est le serveur de travaux
# qui l'ouvrira —, mais elle doit recevoir de vrais octets.
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture
def fiche(client, base_de_test):
    """Une fiche simple « _FsActes », et un type pour comparer."""
    creee = client.post("/admin/categories", json={
        "nom": "_FsActes", "nature": "fiche", "ordre": 950})
    assert creee.status_code == 200, creee.text
    identifiant = creee.json()["id"]
    yield identifiant

    session = SessionLocal()
    try:
        session.query(Job).filter(Job.categorie_id == identifiant).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.id == identifiant).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_une_fiche_na_pas_de_dossier_de_depot(fiche):
    """
    Le cœur de la nature : `ocr_wait` ne la connaît pas. Un dossier ferait entrer
    des documents sans qu'on les ait posés là, et l'on retrouverait dans une
    fiche ce qu'aucune règle ne sait décrire.
    """
    session = SessionLocal()
    try:
        categorie = session.get(Categorie, fiche)
        assert categorie.dossier_depot is None
        assert depots.attribuer(session, categorie) is None
        assert categorie.dossier_depot not in depots.dossiers_declares(session)
    finally:
        session.rollback()
        session.close()


def test_un_fichier_glisse_dans_une_fiche_devient_un_travail(client, fiche):
    """
    Le geste attendu : on glisse, l'API pose le fichier et passe la main. Elle
    n'archive pas elle-même — les archives sont hors de sa portée, et il n'y a
    pas deux chemins d'entrée à tenir.
    """
    reponse = client.post(f"/fiches/{fiche}/documents",
                          files={"fichier": ("acte notarié.pdf", PDF, "application/pdf")})
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["categorie"] == "_FsActes"

    session = SessionLocal()
    try:
        travail = session.get(Job, corps["job_id"])
        assert travail.statut == "en_attente"
        assert travail.categorie_id == fiche, \
            "le type est dit au dépôt, pas déduit de l'endroit où le fichier est posé"
        depose = Path(travail.chemin_source)
        assert depose.is_file()
        assert depose.read_bytes() == PDF
        assert depose.is_relative_to(Path(config.DEPOTS_MANUELS_FOLDER))
        assert depose.name == "acte_notarie.pdf", \
            "le document portera ce nom : il doit rester lisible"
    finally:
        session.close()


def test_le_serveur_de_travaux_retrouve_le_type(client, fiche):
    """
    Le fichier n'est nulle part sous `ocr_wait` : l'emplacement ne dit rien de
    son type. C'est le travail qui s'en souvient (§21.15) — sans quoi un dépôt à
    la main retomberait « à classer », et l'on redemanderait une réponse déjà
    donnée au moment du dépôt.
    """
    reponse = client.post(f"/fiches/{fiche}/documents",
                          files={"fichier": ("carte_grise.pdf", PDF, "application/pdf")})
    identifiant = reponse.json()["job_id"]

    session = SessionLocal()
    try:
        travail = session.get(Job, identifiant)
        chemin = Path(travail.chemin_source)
        assert depots.type_du_chemin(session, chemin) is None, \
            "aucun dossier de dépôt ne réclame ce fichier"
        retrouve = worker.type_du_travail(session, chemin, travail)
        assert retrouve is not None and retrouve.id == fiche
    finally:
        session.close()


def test_deux_depots_du_meme_fichier_ne_secrasent_pas(client, fiche):
    """Deux gestes distincts : le second ne doit pas remplacer le premier avant
    que le serveur de travaux n'ait repris le premier."""
    chemins = []
    for _ in range(2):
        reponse = client.post(f"/fiches/{fiche}/documents",
                              files={"fichier": ("acte.pdf", PDF, "application/pdf")})
        assert reponse.status_code == 200, reponse.text
        session = SessionLocal()
        try:
            chemins.append(session.get(Job, reponse.json()["job_id"]).chemin_source)
        finally:
            session.close()

    assert chemins[0] != chemins[1]
    assert all(Path(c).is_file() for c in chemins)


def test_on_ne_depose_pas_dans_un_type_par_ce_chemin(client, fiche):
    """
    Un type a son dossier sous `ocr_wait` : c'est là qu'on dépose, et le refus le
    dit plutôt que d'ouvrir une seconde porte d'entrée pour la même chose.
    """
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        identifiant = type_doc.id
    finally:
        session.close()

    refus = client.post(f"/fiches/{identifiant}/documents",
                        files={"fichier": ("facture.pdf", PDF, "application/pdf")})
    assert refus.status_code == 400
    assert "dossier de dépôt" in refus.json()["detail"]


def test_un_format_non_pris_en_charge_est_refuse(client, fiche):
    refus = client.post(f"/fiches/{fiche}/documents",
                        files={"fichier": ("notes.txt", b"bonjour", "text/plain")})
    assert refus.status_code == 422
    assert ".pdf" in refus.json()["detail"]

    # rien ne traîne dans la file : un refus ne doit pas laisser de fichier
    session = SessionLocal()
    try:
        assert not session.query(Job).filter(
            Job.nom_fichier == "notes.txt").count()
    finally:
        session.close()


def test_une_categorie_inconnue_est_refusee(client):
    refus = client.post("/fiches/999999/documents",
                        files={"fichier": ("acte.pdf", PDF, "application/pdf")})
    assert refus.status_code == 404
