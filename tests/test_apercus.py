"""
Miniatures et préférences d'affichage (§19.20).

Ouvrir une fiche chargeait le PDF entier — plusieurs mégaoctets pour reconnaître
un document, à chaque clic de ligne. Une image de la première page suffit la
plupart du temps ; le PDF reste à un clic pour qui veut lire.
"""
import subprocess

import pytest

from app import apercus, config
from app.db import Categorie, Document, SessionLocal


@pytest.fixture
def document_pdf(base_de_test, tmp_path, monkeypatch):
    """Un vrai PDF sur le disque, et un cache de miniatures à soi."""
    monkeypatch.setattr(config, "APERCUS_FOLDER", str(tmp_path / "apercus"))

    postscript = tmp_path / "page.ps"
    postscript.write_text("%!PS\n/Helvetica findfont 12 scalefont setfont\n"
                          "72 700 moveto (PAGE UNE) show\nshowpage\n")
    pdf = tmp_path / "document.pdf"
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
                    f"-sOutputFile={pdf}", str(postscript)], check=True, capture_output=True)

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ap%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        document = Document(nom_fichier="_ap_document.pdf", chemin_stockage=str(pdf),
                            hash_sha256="apercu".ljust(64, "a"), texte_ocr="x",
                            statut="traite", categorie_id=type_doc.id)
        session.add(document)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    yield identifiant, str(pdf)

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ap%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_la_miniature_se_rend_et_se_garde(document_pdf):
    identifiant, source = document_pdf
    image = apercus.obtenir(identifiant, source, "apercu".ljust(64, "a"))
    assert image is not None and image.stat().st_size > 0
    assert image.read_bytes()[:4] == b"\x89PNG", "une image, pas un PDF"

    # une seconde demande ne refait pas le rendu : c'est un cache
    date = image.stat().st_mtime
    apercus.obtenir(identifiant, source, "apercu".ljust(64, "a"))
    assert image.stat().st_mtime == date


def test_une_nouvelle_version_change_de_miniature(document_pdf):
    """
    Le nom porte l'empreinte : sans cela, un document rescanné s'afficherait avec
    l'image de l'ancien dépôt, et l'on croirait le nouveau perdu.
    """
    identifiant, _ = document_pdf
    assert apercus.chemin(identifiant, "a" * 64) != apercus.chemin(identifiant, "b" * 64)


def test_un_fichier_absent_ne_fait_pas_echouer(document_pdf):
    """C'est une commodité d'affichage : elle se tait, l'appelant se rabat sur le PDF."""
    identifiant, _ = document_pdf
    assert apercus.obtenir(identifiant, "/introuvable.pdf", "x" * 64) is None


def test_les_miniatures_sans_document_sont_balayees(document_pdf):
    identifiant, source = document_pdf
    apercus.obtenir(identifiant, source, "apercu".ljust(64, "a"))
    orpheline = apercus.chemin(999999, "z" * 64)
    orpheline.write_bytes(b"\x89PNG")

    assert apercus.purger({identifiant}) == 1
    assert not orpheline.exists()
    assert apercus.chemin(identifiant, "apercu".ljust(64, "a")).exists()


def test_lapercu_demande_le_droit_de_telecharger(client, document_pdf):
    """Une image de la page **est** le document, en plus petit."""
    identifiant, _ = document_pdf
    assert client.get(f"/documents/{identifiant}/apercu").status_code == 200


def test_le_mode_daffichage_est_personnel(client):
    """
    Il dépend de la machine de celui qui regarde : le mettre dans les réglages du
    foyer aurait obligé à trancher pour tout le monde une question qui n'a pas de
    réponse commune. La vignette ouvre par défaut — c'est le mode qui coûte le
    moins à afficher (§19.21).
    """
    assert client.get("/moi").json()["mode_apercu"] == "miniature"

    change = client.put("/moi/preferences", json={"mode_apercu": "document"})
    assert change.status_code == 200, change.text
    assert change.json()["mode_apercu"] == "document"

    client.put("/moi/preferences", json={"mode_apercu": "miniature"})


def test_un_mode_inconnu_est_refuse(client):
    assert client.put("/moi/preferences", json={"mode_apercu": "hologramme"}).status_code == 422
