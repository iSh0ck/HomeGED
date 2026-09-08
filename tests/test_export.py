"""
Export de l'archive (§17.30).

C'est le fichier le plus sensible que l'application puisse produire : tous les
documents du foyer, dans un fichier qui échappe ensuite à tout contrôle. Ces
tests portent donc autant sur ce que l'archive contient que sur ce qui en
protège l'accès — identité revérifiée, téléchargement unique, effacement.
"""
import io
import zipfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import otp
from app.api import app
from app.db import Categorie, Document, ExportArchive, SessionLocal

MDP = "motdepasse-de-test-1234"      # celui du compte d'administration des tests


@pytest.fixture
def archive_a_exporter(base_de_test, tmp_path):
    """Deux documents, dont un dans une sous-catégorie, et un PDF sur le disque."""
    fichier = tmp_path / "facture.pdf"
    fichier.write_bytes(b"%PDF-1.7\n" + b"x" * 500)

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_export%")).delete(
            synchronize_session=False)
        parent = session.query(Categorie).filter_by(nom="_ExportParent").one_or_none()
        if not parent:
            parent = Categorie(nom="_ExportParent", ordre=990)
            session.add(parent)
            session.flush()
            session.add(Categorie(nom="_ExportEnfant", parent_id=parent.id,
                                  ordre=991))
            session.flush()
        enfant = session.query(Categorie).filter_by(nom="_ExportEnfant").one()

        session.add(Document(nom_fichier="_export_classe.pdf", chemin_stockage=str(fichier),
                             hash_sha256="export1".ljust(64, "e"), texte_ocr="x",
                             statut="traite", categorie_id=enfant.id))
        session.add(Document(nom_fichier="_export_orphelin.pdf",
                             chemin_stockage="/introuvable/nulle-part.pdf",
                             hash_sha256="export2".ljust(64, "e"), texte_ocr="x",
                             statut="traite"))
        session.commit()
    finally:
        session.close()

    yield

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_export%")).delete(
            synchronize_session=False)
        session.query(ExportArchive).delete()
        session.commit()
    finally:
        session.close()


def _demander(client, **corps):
    return client.post("/admin/export", json={"mot_de_passe": MDP, **corps})


def test_le_mot_de_passe_est_redemande(client, archive_a_exporter):
    """
    Une session ouverte sur un poste laissé sans surveillance ne doit pas suffire
    à sortir toute l'archive.
    """
    refus = client.post("/admin/export", json={"mot_de_passe": "pas-le-bon"})
    assert refus.status_code == 400
    assert "mot de passe" in refus.json()["detail"].lower()


def test_larchive_conserve_larborescence_du_classement(client, archive_a_exporter):
    demande = _demander(client)
    assert demande.status_code == 200, demande.text

    telechargement = client.get(f"/admin/export/{demande.json()['jeton']}")
    assert telechargement.status_code == 200
    assert telechargement.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(telechargement.content)) as archive:
        noms = archive.namelist()
        assert any(n.startswith("_ExportParent/_ExportEnfant/") for n in noms), \
            "le chemin doit refléter la hiérarchie des catégories"
        assert "index.csv" in noms, "les données d'indexation partent avec les fichiers"
        # le PDF manquant ne fait pas échouer l'export, il est signalé
        assert "FICHIERS_MANQUANTS.txt" in noms
        index = archive.read("index.csv").decode("utf-8")
        # L'en-tête décrit exactement ce que les lignes écrivent : « emetteur »
        # y traînait après le retrait de l'émetteur codé en dur, et décalait
        # toutes les colonnes d'un cran dans le tableur.
        entete = index.splitlines()[0].lstrip("\ufeff")
        premiere = index.splitlines()[1]
        assert entete.startswith("fichier_archive;nom_origine;categorie;date_document")
        assert entete.split(";").__len__() == premiere.split(";").__len__(), \
            "autant de colonnes que de valeurs, sinon l'index se lit de travers"


def test_larchive_ne_se_telecharge_quune_fois(client, archive_a_exporter):
    jeton = _demander(client).json()["jeton"]
    assert client.get(f"/admin/export/{jeton}").status_code == 200

    second = client.get(f"/admin/export/{jeton}")
    assert second.status_code == 404, "un lien qui resterait valable serait une copie du foyer"


def test_une_archive_expiree_est_refusee(client, archive_a_exporter):
    jeton = _demander(client).json()["jeton"]
    session = SessionLocal()
    try:
        export = session.query(ExportArchive).filter_by(jeton=jeton).one()
        export.date_expiration = datetime.now() - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    assert client.get(f"/admin/export/{jeton}").status_code == 410


def test_un_compte_ordinaire_ne_peut_pas_exporter(client):
    email = "_t_export@homeged.local"
    for u in client.get("/admin/utilisateurs").json():
        if u["email"] == email:
            client.delete(f"/admin/utilisateurs/{u['id']}")
    cree = client.post("/admin/utilisateurs", json={
        "email": email, "nom": "Sans", "prenom": "Droits", "mot_de_passe": "MotDePasse!42",
        "est_admin": False, "actif": True, "role_ids": [],
    })
    assert cree.status_code == 200, cree.text

    ordinaire = TestClient(app)
    jeton = ordinaire.post("/auth/login", data={"username": email, "password": "MotDePasse!42"})
    ordinaire.headers["Authorization"] = f"Bearer {jeton.json()['access_token']}"

    assert ordinaire.post("/admin/export", json={"mot_de_passe": "MotDePasse!42"}).status_code == 403
    client.delete(f"/admin/utilisateurs/{cree.json()['id']}")


def test_le_second_facteur_est_exige_quand_il_est_actif(client, archive_a_exporter):
    """
    L'export sort tout : si le compte est protégé par un second facteur, il doit
    l'être ici aussi. Le contraire ferait de cet écran le maillon faible.
    """
    preparation = client.post("/moi/otp/preparer")
    secret = preparation.json()["secret"]
    assert client.post("/moi/otp/activer", json={"code": otp.code(secret)}).status_code == 200

    try:
        sans_code = client.post("/admin/export", json={"mot_de_passe": MDP})
        assert sans_code.status_code == 400
        assert "double authentification" in sans_code.json()["detail"].lower()

        mauvais = client.post("/admin/export", json={"mot_de_passe": MDP, "code_otp": "000000"})
        assert mauvais.status_code == 400

        bon = client.post("/admin/export",
                          json={"mot_de_passe": MDP, "code_otp": otp.code(secret)})
        assert bon.status_code == 200, bon.text
    finally:
        client.post("/moi/otp/desactiver", json={"mot_de_passe": MDP})


def test_les_archives_orphelines_sont_balayees(client, archive_a_exporter, monkeypatch, tmp_path):
    """
    Un fichier que plus aucune ligne ne réclame — base restaurée, ligne effacée à
    la main — resterait sur le disque indéfiniment. C'est le cas qui produit les
    vraies fuites : celui dont personne ne sait qu'il existe.
    """
    import os
    import time
    from app import export

    dossier = tmp_path / "exports"
    dossier.mkdir()
    orphelin = dossier / "homeged-oublie.zip"
    orphelin.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    vieux = time.time() - 7200        # au-delà du répit d'une heure
    os.utime(orphelin, (vieux, vieux))

    recent = dossier / "homeged-en-cours.zip"
    recent.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    session = SessionLocal()
    try:
        export.purger(session, str(dossier))
    finally:
        session.close()

    assert not orphelin.exists(), "l'archive oubliée doit disparaître"
    assert recent.exists(), "une archive en cours d'écriture n'a pas encore sa ligne : on l'épargne"


def test_larchive_emporte_les_pieces_jointes(client, archive_a_exporter, tmp_path):
    """
    L'archive est ce qui reste le jour où l'on quitte la GED : y oublier la
    garantie jointe à une facture perdrait un fichier que rien d'autre ne
    conserve (§22.2).
    """
    from app import pieces

    garantie = tmp_path / "garantie.pdf"
    garantie.write_bytes(b"%PDF-1.7\n" + b"g" * 200)

    session = SessionLocal()
    try:
        document = session.query(Document).filter_by(nom_fichier="_export_classe.pdf").one()
        pieces.ajouter(session, document, document.chemin_stockage, document.nom_fichier,
                       document.hash_sha256, texte="facture", principale_=True)
        pieces.ajouter(session, document, str(garantie), "garantie.pdf",
                       "exportg".ljust(64, "g"), texte="garantie")
        session.commit()
    finally:
        session.close()

    demande = _demander(client)
    assert demande.status_code == 200, demande.text
    telechargement = client.get(f"/admin/export/{demande.json()['jeton']}")

    with zipfile.ZipFile(io.BytesIO(telechargement.content)) as archive:
        noms = archive.namelist()
        jointes = [n for n in noms if "garantie" in n]
        assert jointes, f"la pièce jointe doit figurer dans l'archive : {noms}"
        assert archive.read(jointes[0]).startswith(b"%PDF-1.7"), \
            "c'est bien le fichier de la pièce, pas une copie de la facture"
        # l'index dit où la retrouver, sans avoir à parcourir les dossiers
        index = archive.read("index.csv").decode("utf-8")
        assert "garantie" in index
