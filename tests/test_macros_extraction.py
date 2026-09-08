"""
Les macros d'extraction (§21.4).

Nos règles extrayaient, mais ne **nettoyaient** presque pas : c'est ce qui
manquait le plus à la qualité des données, plus que des règles supplémentaires.
Chaque fonction est écrite pour ce que produit un OCR, pas pour du texte propre.
"""
import pytest

from app import extraction_fonctions as fonctions

FACTURE = """
    SARL DUBOIS ENERGIE — SIREN 552 100 554
    TVA intracommunautaire FR 32 552100554
    Facture n° F-2026-0412 du 02/04/2026
    IBAN : FR76 3000 4000 0312 3456 7890 143
    Contact : 01 46 32 24 45

    Total HT ............ 1 028,80 €
    dont TVA 20 % ....... 205,76 €
    Total TTC ........... 1 234,56 €

    À payer avant le 30/04/2026
"""


@pytest.mark.parametrize("cle, attendu", [
    ("montant_ttc", "1234.56"),
    ("montant_ht", "1028.80"),
    ("montant_tva", "205.76"),
    ("premiere_date", "2026-04-02"),
    ("derniere_date", "2026-04-30"),
    ("date_echeance", "2026-04-30"),
    ("siren", "552100554"),
    ("numero_tva", "FR32552100554"),
    ("iban", "FR7630004000031234567890143"),
    ("telephone", "0146322445"),
])
def test_ce_quune_facture_annonce_delle_meme(cle, attendu):
    assert fonctions.appliquer(cle, FACTURE) == attendu


def test_un_taux_nest_pas_un_montant():
    """
    « TVA 20 % : 205,76 » annonce d'abord le taux. Prendre le premier nombre venu
    rendait 20,00 € de TVA sur une facture de 1 234 € — une valeur fausse, et qui
    ne se voit pas.
    """
    assert fonctions.appliquer("montant_tva", "dont TVA 20% : 205,76 €") == "205.76"


def test_le_ht_ne_se_devine_pas():
    """Pas de repli sur « le plus grand montant » comme pour le TTC : un chiffre
    pris au hasard serait pire que rien, il ne se verrait pas."""
    assert fonctions.appliquer("montant_ht", "Facture de 1 234,56 € payable à réception") is None


def test_lecheance_exige_detre_annoncee():
    assert fonctions.appliquer("date_echeance", "Facture du 02/04/2026") is None


def test_lecheance_se_calcule_quand_elle_nest_quun_delai():
    """« Payable à 30 jours » n'annonce pas de date limite : il faut la poser."""
    assert fonctions.appliquer("ajouter_jours", "Facture du 02/04/2026",
                               parametre="30") == "2026-05-02"
    # un nombre négatif recule : un rappel se pose aussi *avant* une date
    assert fonctions.appliquer("ajouter_jours", "échéance 30/04/2026",
                               parametre="-7") == "2026-04-23"


def test_les_transformateurs_remettent_en_forme():
    assert fonctions.appliquer("date_normalisee", "émise le 21 août 2026") == "2026-08-21"
    assert fonctions.appliquer("nombre_normalise", "  1 234,56 € ") == "1234.56"
    assert fonctions.appliquer("espaces_condenses", " Jean   DUPONT ") == "Jean DUPONT"
    assert fonctions.appliquer("sans_accents", "Hélène") == "Helene"
    assert fonctions.appliquer("majuscules", "aa-123-bb") == "AA-123-BB"


def test_recoller_les_morceaux_captures():
    """Une expression peut cerner un prénom et un nom : deux règles pour un seul
    champ n'auraient pas de sens."""
    assert fonctions.appliquer("concat_groupes", "Jean", parametre=" ",
                               groupes=("Jean", "DUPONT")) == "Jean DUPONT"
    # sans groupes multiples, la valeur passe telle quelle
    assert fonctions.appliquer("concat_groupes", "seul", parametre=" ") == "seul"


def test_le_catalogue_dit_ce_quil_attend():
    catalogue = {f["cle"]: f for f in fonctions.decrire()}
    assert catalogue["ajouter_jours"]["parametre"]["libelle"] == "Nombre de jours"
    assert catalogue["montant_ttc"]["parametre"] is None, \
        "sans quoi l'écran afficherait un champ dont personne ne saurait quoi faire"
    assert fonctions.attend_un_parametre("ajouter_jours")
    assert not fonctions.attend_un_parametre("montant_ttc")


def test_une_fonction_parametree_sans_valeur_est_refusee(client):
    session_regles = client.get("/admin/jeux-extraction").json()
    if not session_regles:
        pytest.skip("aucun jeu de règles dans cette base")
    jeu = session_regles[0]["id"]

    refus = client.post("/admin/regles", json={
        "profil_id": jeu, "nom": "_mx_echeance", "champ_cible": "echeance",
        "pattern": r"du (\d{2}/\d{2}/\d{4})", "fonction": "ajouter_jours",
        "type_champ": "date"})
    assert refus.status_code == 422
    assert "nombre de jours" in refus.json()["detail"].lower()

    accepte = client.post("/admin/regles", json={
        "profil_id": jeu, "nom": "_mx_echeance", "champ_cible": "echeance",
        "pattern": r"du (\d{2}/\d{2}/\d{4})", "fonction": "ajouter_jours",
        "parametre": "30", "type_champ": "date"})
    assert accepte.status_code == 200, accepte.text
    try:
        assert accepte.json()["parametre"] == "30"
    finally:
        client.delete(f"/admin/regles/{accepte.json()['id']}")


def test_un_decalage_qui_nest_pas_un_nombre_est_refuse(client):
    jeux = client.get("/admin/jeux-extraction").json()
    if not jeux:
        pytest.skip("aucun jeu de règles dans cette base")
    refus = client.post("/admin/regles", json={
        "profil_id": jeux[0]["id"], "nom": "_mx_faux", "champ_cible": "echeance",
        "pattern": "(2026)", "fonction": "ajouter_jours", "parametre": "un mois"})
    assert refus.status_code == 422


# ------------------------------------------------------------------
# Le rapprochement approché (§21.4)
# ------------------------------------------------------------------

def _texte(brut):
    from app import references_auto

    return references_auto._sans_accents(brut)


@pytest.mark.parametrize("libelle, approche, attendu", [
    # un OCR lit « 0range » pour « Orange » : six lettres, une différence
    ("Orange", True, True),
    ("Orange", False, False),
    # « Dupond » pour « Dupont », mais le prénom doit tomber juste
    ("Jean Dupont", True, True),
    ("Yann Dupont", True, False),
    ("Marie Dupont", True, False),
    # un libellé court ne tolère rien : « Ubar » et « Uber » ne sont pas la même
    # entreprise
    ("Ubar", True, False),
    # une immatriculation non plus : un caractère sépare deux véhicules
    ("AA-123-BB", True, False),
])
def test_la_tolerance_sarrete_ou_elle_devient_une_devinette(libelle, approche, attendu):
    from app import references_auto

    texte = _texte("Facture etablie pour Jean Dupond, client 0range. Vehicule AA-123-BC")
    assert references_auto._mentionne(texte, libelle, approche) is attendu


def test_la_tolerance_ne_se_prend_jamais_delle_meme(client):
    """
    Elle se déclare champ par champ : sur un nom de personne elle rattrape un
    scan médiocre, sur une immatriculation elle confondrait deux véhicules.
    """
    from app.db import Categorie, SessionLocal

    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        identifiant = type_doc.id
    finally:
        session.close()

    creation = client.post("/admin/regles-champs", json={
        "categorie_id": identifiant, "champ": "meta:_mx_titulaire",
        "sources": ["usr_membres"], "deduction": "toutes"})
    assert creation.status_code in (200, 409), creation.text
    if creation.status_code == 409:
        pytest.skip("champ déjà réglé dans cette base")
    regle = creation.json()
    try:
        assert regle["deduction_approchee"] is False, "jamais par défaut"

        modifiee = client.put(f"/admin/regles-champs/{regle['id']}", json={
            **regle, "deduction_approchee": True})
        assert modifiee.status_code == 200, modifiee.text
        assert modifiee.json()["deduction_approchee"] is True
    finally:
        client.delete(f"/admin/regles-champs/{regle['id']}")


# ------------------------------------------------------------------
# Ce qu'un document réellement mal océrisé apprend (§21.4)
#
# Ces cas viennent d'une facture de la base d'essai : « ÉCHÉANCE 24/05/2019 » lu
# « 2410512019 », « 20 % » lu « 200% », un IBAN tronqué. Chacun avait produit une
# valeur fausse — et une valeur fausse ne se voit pas, alors qu'un champ vide se
# réclame.
# ------------------------------------------------------------------

FACTURE_MAL_LUE = """
FACTURÉ À ENVOYÉ À FACTURE N° FR-001
Cendrilon Ayot DATE 2ani20ie
22000 Paris COMMANDE N 16802016
ÉCHÉANCE 2410512019

QTÉ DÉSIGNATION PRIX UNIT. HT MONTANT HT
1 Grand brun escargot pour manger 100.00 100.00
2 Petitmarnière uniforme en bleu 15.00 3000

Total HT 145.00
TVA 200% 29.00
TOTAL 174.00€

IBAN: FR12 1234 5678
"""


def test_un_numero_de_commande_nest_pas_un_total():
    """Le repli « plus grand montant » ramassait « COMMANDE N 16802016 »."""
    assert fonctions.appliquer("montant_ttc", FACTURE_MAL_LUE) == "174.00"


def test_len_tete_de_colonne_ne_prime_pas_sur_le_total():
    """« MONTANT HT » est un en-tête de colonne : le nombre qui suit est le
    premier prix de la ligne, pas le total. « Total HT » passe donc devant."""
    assert fonctions.appliquer("montant_ht", FACTURE_MAL_LUE) == "145.00"


def test_un_taux_mal_lu_ne_devient_pas_le_montant():
    assert fonctions.appliquer("montant_tva", FACTURE_MAL_LUE) == "29.00"


def test_un_iban_tronque_vaut_mieux_vide():
    """Mieux vaut ne rien rendre qu'un début de compte bancaire."""
    assert fonctions.appliquer("iban", FACTURE_MAL_LUE) is None


def test_un_debut_diban_nest_pas_un_numero_de_tva():
    """« IBAN: FR12 1234 » a la forme d'un numéro de TVA, et n'en est pas un."""
    assert fonctions.appliquer("numero_tva", FACTURE_MAL_LUE) is None
