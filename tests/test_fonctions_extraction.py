"""
Fonctions d'extraction prêtes à l'emploi (§18.35).

Écrire une expression régulière pour attraper une date ou un montant est le
passage obligé du projet, et le plus ingrat : chaque foyer réécrit les mêmes
motifs avec les mêmes oublis. Ces fonctions font ce travail une fois pour
toutes — et sont écrites pour ce que produit un OCR, pas pour du texte propre.
"""
import pytest

from tests.conftest import jeu_generique

from app import extraction_fonctions as fonctions
from app.db import Document, Metadonnee, RegleExtraction, SessionLocal
from app.regex_engine import appliquer_regles


# ------------------------------------------------------------------
# Les fonctions elles-mêmes
# ------------------------------------------------------------------

@pytest.mark.parametrize("texte, attendu", [
    ("Facture du 21/08/2026", "2026-08-21"),
    ("Facture du 21/08/26", "2026-08-21"),          # année sur deux chiffres
    ("Émise le 21.08.2026", "2026-08-21"),
    ("Date 2026-08-21 sur la ligne", "2026-08-21"),
    ("Établie le 3 septembre 2026", "2026-09-03"),  # en toutes lettres
    ("Le 3 décembre 2026", "2026-12-03"),           # accent compris
    ("aucune date ici", None),
])
def test_la_premiere_date_se_lit_dans_toutes_ses_ecritures(texte, attendu):
    assert fonctions.premiere_date(texte) == attendu


def test_une_date_impossible_est_ecartee_au_profit_de_la_suivante():
    """Un 31 février n'est pas une date : le prendre serait pire que ne rien prendre."""
    assert fonctions.premiere_date("le 31/02/2026 puis le 05/03/2026") == "2026-03-05"


def test_la_premiere_date_est_bien_la_premiere():
    assert fonctions.premiere_date("échéance 30/09/2026, facture du 21/08/2026") == "2026-09-30"


@pytest.mark.parametrize("texte, attendu", [
    ("Total HT 100,00 € Total TTC 120,50 €", "120.50"),
    ("Net à payer : 89,99 €", "89.99"),
    ("TOTAL T.T.C. 1 234,56", "1234.56"),           # espace des milliers
    ("Montant dû 45.00", "45.00"),
])
def test_le_montant_annonce_prime(texte, attendu):
    assert fonctions.montant_ttc(texte) == attendu


def test_a_defaut_d_intitule_le_plus_grand_montant_est_retenu():
    """
    Sur une facture, le total dépasse chacune de ses lignes. C'est une
    supposition, et elle est faillible ; elle vaut mieux que rien et se corrige
    d'un clic sur la fiche.
    """
    assert fonctions.montant_ttc("12,00 puis 1 234,56 et 9,90") == "1234.56"
    assert fonctions.montant_ttc("pas le moindre chiffre") is None


def test_les_montants_gardent_leurs_centimes():
    """« 120.5 » se lit mal sur une facture, et se trie mal dans une colonne."""
    assert fonctions.montant_ttc("Total TTC 120,5") == "120.50"


@pytest.mark.parametrize("texte, attendu", [
    ("N° 026 580 4351", "0265804351"),
    ("réf. AB-123-CD", "123"),
    ("sans chiffre", None),
])
def test_ne_garder_que_les_chiffres(texte, attendu):
    assert fonctions.chiffres_seuls(texte) == attendu


def test_supprimer_les_espaces_insecables_compris():
    assert fonctions.sans_espaces("FR76 3000 4000 03") == "FR763000400003"
    assert fonctions.sans_espaces("A B C") == "ABC"


# ------------------------------------------------------------------
# Leur usage dans une règle
# ------------------------------------------------------------------

@pytest.fixture
def document_a_lire(base_de_test):
    session = SessionLocal()
    try:
        session.query(RegleExtraction).filter(RegleExtraction.nom.like("_fn%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_fn%")).delete(
            synchronize_session=False)
        # Classé : depuis le §19.6, les règles appartiennent au jeu d'un type de
        # document. Un document sans type n'a aucune règle qui le concerne.
        from app.db import Categorie
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        document = Document(
            nom_fichier="_fn_facture.pdf", chemin_stockage="/x.pdf",
            hash_sha256="fonctions".ljust(64, "f"), statut="traite",
            categorie_id=type_doc.id,
            texte_ocr="ORANGE\nFacture du 21/08/2026\n"
                      "N° client : 026 580 4351\nTotal TTC 120,50 €\n",
        )
        session.add(document)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    yield identifiant

    session = SessionLocal()
    try:
        session.query(RegleExtraction).filter(RegleExtraction.nom.like("_fn%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_fn%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _regle(session, **champs):
    """
    Une règle dans le jeu générique du type qui accueille les documents de test.
    Depuis le §19.6, une règle appartient à un jeu, et un jeu à un type.
    """
    from app.db import Categorie

    type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
    profil = jeu_generique(session, type_doc.id)
    regle = RegleExtraction(profil_id=profil.id, actif=True, priorite=1, **champs)
    session.add(regle)
    session.commit()
    return regle


def _mettre_en_sommeil(session):
    """
    Écarte les règles semées le temps d'un test, **sans les supprimer**.

    Elles étaient effacées : les tests de ce fichier passaient, et ceux qui
    suivaient dans le même processus se retrouvaient sans aucune règle
    d'extraction — le versionnage, qui a besoin d'une date extraite pour
    reconnaître une pièce, échouait alors une fois sur deux selon l'ordre
    d'exécution. Les endormir puis les réveiller ne détruit rien.
    """
    endormies = [r.id for r in session.query(RegleExtraction).filter_by(actif=True)]
    session.query(RegleExtraction).filter(RegleExtraction.id.in_(endormies)).update(
        {"actif": False}, synchronize_session=False)
    session.commit()
    return endormies


def _reveiller(session, endormies):
    if endormies:
        session.query(RegleExtraction).filter(RegleExtraction.id.in_(endormies)).update(
            {"actif": True}, synchronize_session=False)
        session.commit()


def _valeurs(session, document_id) -> dict:
    return {m.cle: m.valeur for m in
            session.query(Metadonnee).filter_by(document_id=document_id)}


def test_une_fonction_seule_se_passe_d_expression(client, document_a_lire):
    """« Première date » et « Montant TTC » cherchent d'elles-mêmes."""
    session = SessionLocal()
    endormies = []
    try:
        endormies = _mettre_en_sommeil(session)
        _regle(session, nom="_fn date", champ_cible="date_document",
               pattern=None, fonction="premiere_date", type_champ="date")
        _regle(session, nom="_fn montant", champ_cible="montant_ttc",
               pattern=None, fonction="montant_ttc", type_champ="montant")

        document = session.get(Document, document_a_lire)
        appliquer_regles(document, session)
        session.commit()
        valeurs = _valeurs(session, document_a_lire)
    finally:
        _reveiller(session, endormies)
        session.close()

    assert valeurs["date_document"] == "2026-08-21"
    assert valeurs["montant_ttc"] == "120.50"


def test_une_fonction_nettoie_ce_que_l_expression_a_trouve(client, document_a_lire):
    """L'expression délimite la zone, la fonction en tire la valeur."""
    session = SessionLocal()
    endormies = []
    try:
        endormies = _mettre_en_sommeil(session)
        _regle(session, nom="_fn client", champ_cible="numero_client",
               pattern=r"(?i)n[°o]\s*client\s*:?\s*([0-9 ]{6,20})",
               fonction="chiffres_seuls", type_champ="texte")

        document = session.get(Document, document_a_lire)
        appliquer_regles(document, session)
        session.commit()
        valeurs = _valeurs(session, document_a_lire)
    finally:
        _reveiller(session, endormies)
        session.close()

    assert valeurs["numero_client"] == "0265804351"


def _un_jeu(client):
    """Un jeu de règles quelconque : depuis le §19.6, une règle en réclame un."""
    jeux = client.get("/admin/jeux-extraction").json()
    assert jeux, "la base d'essai doit avoir au moins un jeu générique"
    return jeux[0]["id"]


def test_une_regle_sans_expression_ni_fonction_cherchante_est_refusee(client):
    """
    Elle ne s'appliquerait jamais, et rien à l'écran ne dirait pourquoi. Mieux
    vaut refuser à la saisie.
    """
    profil = _un_jeu(client)
    refus = client.post("/admin/regles", json={
        "profil_id": profil, "nom": "_fn vide", "champ_cible": "peu_importe",
        "pattern": "", "fonction": "chiffres_seuls", "type_champ": "texte"})
    assert refus.status_code == 422
    assert "cherche" in refus.json()["detail"]

    sans_rien = client.post("/admin/regles", json={
        "profil_id": profil, "nom": "_fn rien", "champ_cible": "peu_importe",
        "pattern": "", "type_champ": "texte"})
    assert sans_rien.status_code == 422


def test_une_fonction_inconnue_est_refusee(client):
    refus = client.post("/admin/regles", json={
        "profil_id": _un_jeu(client), "nom": "_fn inconnue", "champ_cible": "x",
        "pattern": "(.*)", "fonction": "devine_toi_meme"})
    assert refus.status_code == 422
    assert "inconnue" in refus.json()["detail"]


def test_le_catalogue_est_annonce_a_l_interface(client):
    catalogue = client.get("/admin/regles/fonctions").json()
    cles = {f["cle"] for f in catalogue}
    assert cles == set(fonctions.CATALOGUE)
    for entree in catalogue:
        assert entree["libelle"] and entree["description"]
    # Les fonctions qui cherchent d'elles-mêmes : elles se passent d'expression,
    # et l'écran doit pouvoir le dire. La liste s'est étoffée au §21.4.
    cherchantes = {f["cle"] for f in catalogue if f["extracteur"]}
    assert cherchantes == {"premiere_date", "derniere_date", "date_echeance",
                           "montant_ttc", "montant_ht", "montant_tva",
                           "siren", "numero_tva", "iban", "telephone"}
    # Et celles qui attendent une valeur la déclarent, pour que l'écran sache
    # afficher un champ plutôt que de laisser la règle sans effet.
    assert {f["cle"] for f in catalogue if f["parametre"]} == {"ajouter_jours",
                                                              "concat_groupes"}


# ------------------------------------------------------------------
# Essai d'extraction, sans rien enregistrer (§18.41)
# ------------------------------------------------------------------

def test_l_essai_dit_ce_que_les_regles_trouvent(client, document_a_lire):
    """
    Écrire une règle puis relancer un traitement complet pour savoir si elle
    attrape quelque chose est la boucle la plus décourageante du projet.
    """
    essai = client.post(f"/documents/{document_a_lire}/tester-extraction")
    assert essai.status_code == 200, essai.text
    resultat = essai.json()

    assert resultat["valeurs_retenues"].get("date_document") == "2026-08-21"
    assert resultat["valeurs_retenues"].get("montant_ttc") == "120.50"
    assert any(r["retenue"] for r in resultat["regles"])
    # une règle devancée par une autre est signalée comme trouvée, non retenue
    assert all("retenue" in r and "trouve" in r for r in resultat["regles"])


def test_l_essai_n_enregistre_rien(client, document_a_lire):
    """Un essai qui modifierait la fiche ne serait plus un essai."""
    from app.db import Metadonnee, SessionLocal as Fabrique

    session = Fabrique()
    try:
        session.query(Metadonnee).filter_by(document_id=document_a_lire).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()

    client.post(f"/documents/{document_a_lire}/tester-extraction")

    session = Fabrique()
    try:
        assert session.query(Metadonnee).filter_by(document_id=document_a_lire).count() == 0
    finally:
        session.close()


def test_l_essai_annonce_ce_qui_manque(client, document_a_lire):
    """
    L'autre moitié de la question : ce que la catégorie attend et qu'on n'a
    toujours pas.
    """
    from app.db import Categorie, Document, RegleChampCategorie, SessionLocal as Fabrique

    session = Fabrique()
    try:
        document = session.get(Document, document_a_lire)
        categorie = session.query(Categorie).first()
        document.categorie_id = categorie.id
        session.add(RegleChampCategorie(
            categorie_id=categorie.id, champ="meta:champ_introuvable",
            libelle="Champ introuvable", obligatoire=True, ordre=99))
        session.commit()
    finally:
        session.close()

    try:
        resultat = client.post(f"/documents/{document_a_lire}/tester-extraction").json()
        manquants = {m["champ"]: m for m in resultat["manquants"]}
        assert "meta:champ_introuvable" in manquants
        assert manquants["meta:champ_introuvable"]["obligatoire"] is True
    finally:
        session = Fabrique()
        try:
            session.query(RegleChampCategorie).filter_by(
                champ="meta:champ_introuvable").delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()


def test_les_colonnes_cibles_sont_proposees(client):
    """
    La colonne cible se tapait à l'aveugle (§21.11) : une faute de frappe créait
    une métadonnée jumelle — « montant_ttc » et « montant_tt » — que rien ne
    signalait, et l'on cherchait ensuite pourquoi la colonne restait vide.
    """
    categories = client.get("/admin/categories").json()
    type_doc = next(c for c in categories if c["nature"] == "type")

    propositions = client.get("/admin/regles/champs-cibles",
                              params={"categorie_id": type_doc["id"]}).json()
    par_champ = {p["champ"]: p["origine"] for p in propositions}

    # la date du document : le seul nom que le moteur traite à part
    assert par_champ.get("date_document") == "date du document"
    # et ce que le foyer a déjà nommé pour ce type
    assert len(par_champ) > 1, "un type réglé propose au moins ses champs attendus"
    assert all(p["champ"] and p["origine"] for p in propositions)


def test_les_propositions_se_limitent_au_type_demande(client):
    """Proposer les champs d'un autre type ferait écrire des règles qui ne
    rempliraient jamais rien."""
    categories = client.get("/admin/categories").json()
    types = [c for c in categories if c["nature"] == "type"]
    if len(types) < 2:
        import pytest
        pytest.skip("un seul type de document dans cette base")

    globales = {p["champ"] for p in client.get("/admin/regles/champs-cibles").json()}
    du_type = {p["champ"] for p in client.get(
        "/admin/regles/champs-cibles", params={"categorie_id": types[0]["id"]}).json()}
    assert du_type <= globales
