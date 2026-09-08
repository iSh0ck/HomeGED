"""
Moteur d'extraction : normalisation des valeurs, priorité des règles, et
application sur un texte de facture réaliste.
"""
import pytest

from tests.conftest import jeu_generique

from app.db import Document, Metadonnee, RegleExtraction
from app.regex_engine import _convertir_valeur, appliquer_regles

TEXTE_FACTURE = """n° de facture : 05C060T853 26G1- 1G08

date de facture : 21/08/26

Votre facture internet fibre

prochaine facture vers le 24.09.2026

total auprès d'Orange 50,99 €

n° client : 026 580 4351
"""


@pytest.mark.parametrize("brut, attendu", [
    ("21/08/2026", "2026-08-21"),
    ("21/08/26", "2026-08-21"),     # année sur deux chiffres : cas réel des factures
    ("24.09.2026", "2026-09-24"),   # séparateur point
    ("21-08-2026", "2026-08-21"),
    ("pas une date", "pas une date"),
])
def test_normalisation_des_dates(brut, attendu):
    assert _convertir_valeur(brut, "date") == attendu


def test_normalisation_des_montants():
    assert _convertir_valeur("50,99", "montant") == "50.99"


def _document_de_test(session, texte=TEXTE_FACTURE):
    """
    Un document **classé** : depuis le §19.6, les règles appartiennent à un jeu,
    qui appartient à un type de document. Un document sans type n'a donc aucune
    règle à lui — ce qui est le comportement voulu, pas une limite du test.
    """
    from app.db import Categorie

    type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
    document = Document(
        nom_fichier="facture.pdf", chemin_stockage="/tmp/facture.pdf",
        hash_sha256="f" * 64, texte_ocr=texte, statut="traite",
        categorie_id=type_doc.id,
    )
    session.add(document)
    session.flush()
    return document


def _regle(session, **champs):
    """Une règle dans le jeu générique du type qui accueille les documents de test."""
    from app.db import Categorie

    type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
    profil = jeu_generique(session, type_doc.id)
    regle = RegleExtraction(profil_id=profil.id, **champs)
    session.add(regle)
    session.flush()
    return regle


def test_extraction_sur_une_facture_reelle(session):
    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.flush()
    valeurs = {m.cle: m.valeur for m in session.query(Metadonnee)
               .filter_by(document_id=document.id)}

    assert valeurs["numero_facture"] == "05C060T853 26G1- 1G08"
    assert valeurs["date_document"] == "2026-08-21"
    assert valeurs["montant_ttc"] == "50.99"
    assert valeurs["numero_client"] == "026 580 4351"
    assert str(document.date_document) == "2026-08-21"


def test_lemetteur_ne_sinvente_pas(session):
    """
    L'émetteur est devenu une métadonnée comme une autre (§21.12) : rien ne le
    remplit tant qu'une règle ou une déduction déclarée ne le fait — le texte a
    beau dire « Orange » partout.
    """
    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.flush()
    cles = {m.cle for m in session.query(Metadonnee).filter_by(document_id=document.id)}
    assert "emetteur" not in cles


def test_toute_regle_active_s_applique_des_le_depot(session):
    """
    Une règle pouvait être réservée à un émetteur (§18.43). L'option a été
    retirée, puis l'émetteur lui-même a cessé d'être un champ du document
    (§21.12). Ce test garde ce qui compte : une règle active joue **dès le
    premier passage**, sans que personne ait à renseigner quoi que ce soit.
    """
    _regle(session, nom="Référence opérateur", champ_cible="reference_operateur",
           pattern=r"(?i)n[°ºo]\s*client\s*:\s*(\S.*?)\s*$", type_champ="texte",
           priorite=5, actif=True)

    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.flush()
    cles = {m.cle for m in session.query(Metadonnee).filter_by(document_id=document.id)}
    assert "reference_operateur" in cles


def test_la_regle_prioritaire_l_emporte_sur_le_repli(session):
    """
    La règle ciblée « date de facture : … » est testée avant le repli générique
    (priorité plus basse). Le repli ne doit pas écraser sa valeur : ici il
    trouverait « 24.09.2026 », la date de la *prochaine* facture.
    """
    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.flush()
    date = session.query(Metadonnee).filter_by(
        document_id=document.id, cle="date_document").one().valeur
    assert date == "2026-08-21", "le repli générique a écrasé la règle ciblée"


def test_une_regle_invalide_n_empeche_pas_les_autres(session):
    """Une expression incorrecte est signalée et ignorée, sans faire échouer le lot."""
    _regle(session, nom="Règle cassée", champ_cible="casse", pattern="(?i)[abc",
           type_champ="texte", priorite=1, actif=True)
    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.flush()
    valeurs = {m.cle for m in session.query(Metadonnee).filter_by(document_id=document.id)}
    assert "numero_facture" in valeurs
    assert "casse" not in valeurs


def test_le_rejeu_rafraichit_une_valeur_obsolete(session):
    """
    Rejouer l'extraction doit corriger une valeur issue d'un passage antérieur.

    La valeur porte l'identifiant d'une règle, et c'est ce qui la distingue d'une
    saisie humaine (§18.45) : la première se rafraîchit, la seconde est
    respectée. Ce test la posait sans identifiant — ce qui, depuis, signifie
    « saisie à la main » et la rendait intouchable.
    """
    document = _document_de_test(session)
    regle = session.query(RegleExtraction).filter_by(champ_cible="numero_facture").first()
    session.add(Metadonnee(document_id=document.id, cle="numero_facture",
                           valeur="périmé", regle_id=regle.id if regle else None))
    session.flush()
    appliquer_regles(document, session)
    session.flush()
    valeur = session.query(Metadonnee).filter_by(
        document_id=document.id, cle="numero_facture").one().valeur
    assert valeur == "05C060T853 26G1- 1G08"


# ------------------------------------------------------------------
# Reprise automatique des travaux bloqués (§18.45)
# ------------------------------------------------------------------

def test_une_valeur_saisie_a_la_main_nest_pas_ecrasee_par_une_regle(session):
    """
    Le garde-fou sans lequel la reprise automatique serait destructrice : une
    personne a corrigé une valeur depuis la fiche, une expression régulière ne
    doit pas la remplacer cinq minutes plus tard.
    """
    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.flush()

    # correction manuelle : `regle_id` nul, c'est ce qui la distingue
    manuelle = (session.query(Metadonnee)
                .filter_by(document_id=document.id, cle="date_document").one())
    manuelle.valeur = "1999-01-01"
    manuelle.regle_id = None
    session.flush()

    appliquer_regles(document, session)
    session.flush()
    relue = (session.query(Metadonnee)
             .filter_by(document_id=document.id, cle="date_document").one())
    assert relue.valeur == "1999-01-01", "la saisie humaine l'emporte sur l'expression"


def test_une_valeur_issue_dune_regle_reste_rafraichie(session):
    """
    L'inverse doit rester vrai : corriger une expression et rejouer doit bien
    remplacer ce que l'ancienne avait trouvé, sinon le rejeu ne servirait à rien.
    """
    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.flush()

    posee = (session.query(Metadonnee)
             .filter_by(document_id=document.id, cle="date_document").one())
    assert posee.regle_id is not None
    posee.valeur = "1999-01-01"          # valeur d'une règle, désormais fausse
    session.flush()

    appliquer_regles(document, session)
    session.flush()
    relue = (session.query(Metadonnee)
             .filter_by(document_id=document.id, cle="date_document").one())
    assert relue.valeur == "2026-08-21"


def test_la_date_ne_fait_pas_deux_champs(session, client):
    """
    Une règle qui cible `date_document` écrit **deux choses** : la colonne du
    document, pour le tri et la recherche, et une métadonnée du même nom — celle
    qui porte « corrigé à la main », le garde-fou du §18.45.

    La métadonnée a sa raison d'être ; elle n'a pas sa case. La fiche montrait
    « Date du document », déclaré par le type, **et** « date document », son
    ombre — deux champs pour une valeur (§22.79).
    """
    document = _document_de_test(session)
    appliquer_regles(document, session)
    session.commit()

    fiche = client.get(f"/documents/{document.id}").json()
    assert fiche["date_document"] == "2026-08-21"
    assert "date_document" not in [c["cle"] for c in fiche["champs_fiche"]], \
        "l'ombre de la colonne ne fait pas une ligne de fiche"
    # Elle reste en base : c'est elle que le rejeu consulte.
    assert session.query(Metadonnee).filter_by(
        document_id=document.id, cle="date_document").one().valeur == "2026-08-21"
