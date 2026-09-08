"""
Choix de la stratégie d'océrisation (§17.10).

Le pipeline rastérisait toute page à 400 ppp, y compris celles qui portaient
déjà du vrai texte. Mesuré : une facture née numérique devenait huit fois plus
lourde, floue au zoom, et son texte **moins juste** — l'OCR réintroduisait des
fautes là où le texte d'origine était parfait.

Ces tests vérifient que chaque nature de document reçoit le traitement qui lui
convient, et que les mesures qui fondent la décision (présence de texte,
résolution) disent vrai.
"""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from app import config, ocr

# Une facture vectorielle, avec des mentions en petits caractères : c'est là que
# la résolution se joue, pas sur les titres.
POSTSCRIPT = """%!PS
/Helvetica-Bold findfont 14 scalefont setfont
72 780 moveto (FOURNISSEUR D'ENERGIE SA) show
/Helvetica findfont 10 scalefont setfont
72 755 moveto (Facture n 2026-00184 du 12 mars 2026) show
72 735 moveto (TOTAL TTC : 116,52 EUR) show
/Helvetica findfont 7 scalefont setfont
72 700 moveto (SIRET 812 345 678 00019 - Reference contrat 4021-XZ-9987) show
showpage
"""


@pytest.fixture(scope="module")
def documents():
    """Un PDF né numérique et un « scan » de la même page, à 600 ppp."""
    dossier = tempfile.mkdtemp(prefix="homeged_ocr_")
    source_ps = os.path.join(dossier, "facture.ps")
    Path(source_ps).write_text(POSTSCRIPT)

    natif = os.path.join(dossier, "natif.pdf")
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
                    f"-sOutputFile={natif}", source_ps], check=True, capture_output=True)

    image = os.path.join(dossier, "scan.png")
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", "-r600",
                    f"-sOutputFile={image}", natif], check=True, capture_output=True)
    scan = os.path.join(dossier, "scan.pdf")
    subprocess.run(["img2pdf", "-o", scan, image], check=True, capture_output=True)

    return {"dossier": dossier, "natif": natif, "scan": scan}


def test_reconnait_un_document_qui_porte_deja_du_texte(documents):
    assert ocr.porte_du_texte(documents["natif"]) is True
    assert ocr.porte_du_texte(documents["scan"]) is False, "un scan n'a pas de couche texte"


def test_lit_la_resolution_des_images(documents):
    assert ocr.resolution_maximale(documents["natif"]) == 0, "un PDF vectoriel n'a pas de ppp"
    assert 595 <= ocr.resolution_maximale(documents["scan"]) <= 605


def test_le_document_ne_numerique_nest_pas_rasterise(documents):
    mode, resolution = ocr.choisir_strategie(documents["natif"])
    assert mode == "redo", "son texte doit être préservé, pas refait"
    assert resolution is None


def test_un_scan_trop_defini_est_ramene_a_la_resolution_cible(documents):
    mode, resolution = ocr.choisir_strategie(documents["scan"])
    assert mode == "force", "rien à préserver : la page est une image"
    assert resolution == config.RESOLUTION_CIBLE


def test_le_mode_force_court_circuite_lanalyse(documents, monkeypatch):
    """
    Face à un scanner dont la couche de texte est fausse, tout ré-océriser reste
    la bonne réponse — d'où le réglage, et d'où ce test.
    """
    monkeypatch.setattr(config, "OCR_STRATEGIE", "force")
    assert ocr.choisir_strategie(documents["natif"]) == ("force", None)


def test_ocerisation_dun_document_ne_numerique_preserve_texte_et_poids(documents):
    """
    Le cœur du changement : ni rastérisation, ni perte de texte, ni gonflement.
    Avant, ce même document passait de 4 à 29 Ko et son texte gagnait des fautes.
    """
    sortie = os.path.join(documents["dossier"], "natif_ocr.pdf")
    ocr.ocr_to_searchable_pdf(documents["natif"], sortie)

    assert ocr.resolution_maximale(sortie) == 0, "aucune image : la page est restée vectorielle"
    assert os.path.getsize(sortie) < os.path.getsize(documents["natif"]) * 3

    texte = ocr.extraire_texte(sortie).replace(" ", "")
    for repere in ("116,52", "4021-XZ-9987", "81234567800019"):
        assert repere.replace(" ", "") in texte, f"« {repere} » doit rester lisible"
