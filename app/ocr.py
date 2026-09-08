"""
OCR des documents entrants.
- PDF : on passe par ocrmypdf pour ajouter une couche texte invisible (garde le rendu original).
- Images (jpg/png/tiff) : on les convertit d'abord en PDF, puis même traitement.
Nécessite les binaires système : ocrmypdf, tesseract, img2pdf (installés dans le Dockerfile).
"""
import logging
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional

from pdfminer.high_level import extract_text as pdf_extract_text
from pdfminer.layout import LAParams

from . import config

log = logging.getLogger(__name__)

# `--force-ocr` rasterise chaque page : le PDF produit contient une image, et la
# couche de texte océrisé se retrouve **à l'intérieur de cette figure**. Or
# pdfminer n'analyse pas la mise en page du texte contenu dans les figures, sauf
# à le lui demander : sans ce réglage, il restitue les glyphes à la suite, sans
# saut de ligne ni séparateur — « Votre factureinternet fibre ». Le texte devient
# alors inexploitable, aussi bien par les expressions régulières d'extraction que
# par la recherche plein texte de MariaDB, qui découpe sur les espaces.
PARAMS_MISE_EN_PAGE = LAParams(all_texts=True)


def _image_to_pdf(image_path: str) -> str:
    """Convertit une image en PDF temporaire (nécessaire avant OCR)."""
    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
    subprocess.run(["img2pdf", image_path, "-o", tmp_pdf], check=True)
    return tmp_pdf


def porte_du_texte(chemin_pdf: str, minimum: int = 40) -> bool:
    """
    Le PDF contient-il déjà du texte exploitable ?

    C'est la question qui décide de tout : un document né numérique — une
    facture reçue par courriel — porte son texte, exact et vectoriel. Le
    rastériser pour l'océriser le rend huit fois plus lourd, flou au zoom, et
    **moins juste** : l'OCR réintroduit des fautes là où le texte était parfait.

    Le seuil écarte les PDF qui ne portent qu'un filigrane ou un numéro de page.
    """
    try:
        texte = pdf_extract_text(chemin_pdf, laparams=PARAMS_MISE_EN_PAGE) or ""
    except Exception:
        return False
    return len(texte.strip()) >= minimum


def resolution_maximale(chemin_pdf: str) -> int:
    """
    Résolution de l'image la plus fine du document, en points par pouce.

    0 si le document ne contient aucune image — il est alors vectoriel, et la
    question de la résolution ne se pose pas.
    """
    try:
        import pikepdf
    except ImportError:                      # pragma: no cover
        return 0
    maximum = 0
    try:
        with pikepdf.open(chemin_pdf) as pdf:
            for page in pdf.pages:
                boite = page.get("/MediaBox")
                if not boite:
                    continue
                largeur_pt = float(boite[2]) - float(boite[0])
                if largeur_pt <= 0:
                    continue
                ressources = (page.get("/Resources") or {}).get("/XObject") or {}
                for _, objet in ressources.items():
                    if objet.get("/Subtype") != "/Image":
                        continue
                    largeur_px = int(objet.get("/Width") or 0)
                    maximum = max(maximum, round(largeur_px / (largeur_pt / 72)))
    except Exception:
        return 0
    return maximum


def _reduire_resolution(chemin_pdf: str, ppp: int) -> str:
    """
    Rend un PDF dont les pages sont rendues à `ppp` points par pouce.

    Passe par un rendu complet de la page plutôt que par le sous-échantillonnage
    de Ghostscript : celui-ci ne sait diviser que par des entiers — de 400 ppp,
    il donne 200 ou rien, jamais 300. Un document déjà image ne perd rien à être
    rendu : il n'y a pas de vectoriel à préserver.
    """
    dossier = tempfile.mkdtemp(prefix="homeged_ppp_")
    motif = os.path.join(dossier, "page-%04d.png")
    subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", f"-r{ppp}",
         f"-sOutputFile={motif}", chemin_pdf],
        check=True, capture_output=True,
    )
    pages = sorted(Path(dossier).glob("page-*.png"))
    if not pages:
        raise RuntimeError("Ghostscript n'a produit aucune page")
    sortie = os.path.join(dossier, "reduit.pdf")
    # Pas de résolution à repréciser ici : Ghostscript inscrit la densité dans
    # le PNG (segment pHYs) et img2pdf la lit pour dimensionner la page. La lui
    # redonner en option n'existe d'ailleurs pas — `--dpi` n'est pas un argument
    # d'img2pdf, l'essayer fait échouer la commande.
    subprocess.run(["img2pdf", "-o", sortie, *[str(page) for page in pages]],
                   check=True, capture_output=True)
    return sortie


def choisir_strategie(chemin_pdf, strategie=None, resolution=None) -> tuple[str, Optional[int]]:
    """
    Décide comment océriser : `(mode, résolution à imposer)`.

    Trois cas, et un seul justifie de tout rastériser :

      le document porte du texte      → `redo` : on garde ce texte et on
                                        n'océrise que les zones image ;
      c'est un scan trop défini       → `force`, après ramener la page à la
                                        résolution cible ;
      c'est un scan raisonnable       → `force`, tel quel.

    `OCR_STRATEGIE=force` court-circuite l'analyse : tout est rastérisé, ce qui
    reste la bonne réponse face à un scanner dont la couche de texte est fausse.
    """
    if (strategie or config.OCR_STRATEGIE) == "force":
        return "force", None
    if porte_du_texte(chemin_pdf):
        return "redo", None
    cible = config.RESOLUTION_CIBLE if resolution is None else resolution
    actuelle = resolution_maximale(chemin_pdf)
    if cible > 0 and actuelle > cible:
        return "force", cible
    return "force", None


def ocr_to_searchable_pdf(input_path: str, output_path: str, langue: Optional[str] = None,
                          resolution: Optional[int] = None,
                          optimisation: Optional[int] = None,
                          strategie: Optional[str] = None) -> None:
    """
    Produit un PDF océrisé (texte invisible superposé) à partir d'un PDF ou d'une image.

    Le mode d'océrisation est choisi document par document (cf. `choisir_strategie`) :
    préserver le texte quand il existe, rastériser quand il n'y a rien à préserver.

    Langue, résolution, compression et stratégie viennent des réglages du foyer
    (§18.22) ; le worker les lit et les passe ici. À défaut, ce sont les valeurs
    de `.env` — un traitement ne doit pas s'arrêter parce qu'un réglage manque.
    """
    langue = langue or "fra"
    optimisation = config.PDF_OPTIMISATION if optimisation is None else optimisation
    ext = Path(input_path).suffix.lower()
    source_pdf = input_path
    temporaires = []

    if ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        source_pdf = _image_to_pdf(input_path)
        temporaires.append(source_pdf)

    mode, resolution = choisir_strategie(source_pdf, strategie, resolution)
    if resolution:
        try:
            reduit = _reduire_resolution(source_pdf, resolution)
            temporaires.append(reduit)
            source_pdf = reduit
            log.info(f"{Path(input_path).name} : page ramenée à {resolution} ppp avant océrisation")
        except Exception:
            # Ramener la résolution est un confort, pas une condition : en cas
            # d'échec on océrise le document tel qu'il est arrivé.
            log.exception(f"Réduction de résolution impossible pour {input_path}")

    options = ["--redo-ocr"] if mode == "redo" else ["--force-ocr"]
    commande = [
        "ocrmypdf", *options,
        "--language", langue,
        # Compression des images dans la foulée (§17.8) : le document arrive
        # déjà allégé, sans passage supplémentaire.
        "--optimize", str(optimisation),
        "--output-type", "pdf",
        source_pdf,
        output_path,
    ]

    try:
        resultat = subprocess.run(commande, capture_output=True, text=True)
        if resultat.returncode != 0 and mode == "redo":
            # `--redo-ocr` refuse certains PDF (structure de texte inhabituelle).
            # Mieux vaut un document rastérisé qu'un document rejeté : on
            # retombe sur la méthode qui marche toujours.
            log.warning(f"{Path(input_path).name} : --redo-ocr a échoué, reprise en --force-ocr "
                        f"({(resultat.stderr or '').strip().splitlines()[-1:]})")
            commande[1] = "--force-ocr"
            resultat = subprocess.run(commande, capture_output=True, text=True)
        if resultat.returncode != 0:
            raise subprocess.CalledProcessError(resultat.returncode, commande,
                                                output=resultat.stdout, stderr=resultat.stderr)
    finally:
        for chemin in temporaires:
            if os.path.exists(chemin):
                if os.path.isfile(chemin):
                    os.remove(chemin)


def extraire_texte(pdf_path: str) -> str:
    """
    Extrait le texte brut d'un PDF (déjà océrisé ou natif), en analysant aussi
    le texte situé dans les figures — c'est là que se trouve la couche océrisée
    des documents rasterisés (cf. PARAMS_MISE_EN_PAGE).
    """
    return pdf_extract_text(pdf_path, laparams=PARAMS_MISE_EN_PAGE) or ""
