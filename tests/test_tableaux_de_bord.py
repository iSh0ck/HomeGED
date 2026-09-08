"""
Indicateurs des tableaux de bord : justesse des calculs, périodes, et refus des
descriptions inexploitables.
"""
from datetime import date

import pytest

from app import statistiques
from app.db import Categorie, Document, Metadonnee, SessionLocal
from sqlalchemy import text as sql


@pytest.fixture(scope="module")
def jeu(base_de_test):
    """Six factures réparties sur deux années, avec des montants connus."""
    session = SessionLocal()
    factures = session.query(Categorie).filter_by(nom="Factures").one()
    # L'émetteur est une métadonnée depuis le §21.12 : une référence
    # `usr_emetteurs:<id>`, comme tout ce qu'un document désigne.
    edf = session.execute(sql("SELECT id FROM usr_emetteurs WHERE nom = 'EDF'")).scalar()
    lignes = [
        ("tb1.pdf", "2026-01-15", edf, "100.00"),
        ("tb2.pdf", "2026-02-20", edf, "50.50"),
        ("tb3.pdf", "2026-02-28", None, "25.00"),
        ("tb4.pdf", "2025-06-10", edf, "300.00"),
        ("tb5.pdf", "2025-11-02", None, "10.00"),
        ("tb6.pdf", "2026-03-05", edf, None),   # sans montant : compté, non totalisé
    ]
    for nom, jour, emetteur, montant in lignes:
        if session.query(Document).filter_by(nom_fichier=nom).first():
            continue
        document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                            hash_sha256=nom.ljust(64, "9"), texte_ocr="x", statut="traite",
                            categorie_id=factures.id,
                            date_document=jour, date_import=jour)
        session.add(document)
        session.flush()
        if montant:
            session.add(Metadonnee(document_id=document.id, cle="montant_ttc", valeur=montant))
        if emetteur:
            session.add(Metadonnee(document_id=document.id, cle="emetteur",
                                   valeur=f"usr_emetteurs:{emetteur}"))
    session.commit()
    identifiants = {"factures": factures.id, "edf": edf}
    session.close()
    return identifiants


def _base(session):
    return session.query(Document.id).filter(Document.nom_fichier.like("tb%.pdf"))


def _calcul(session, indicateur):
    return statistiques.calculer(session, _base(session), indicateur)


@pytest.mark.parametrize("type_periode, attendu", [
    ("annee_en_cours", (date(2026, 1, 1), date(2026, 12, 31))),
    ("annee_precedente", (date(2025, 1, 1), date(2025, 12, 31))),
    ("mois_en_cours", (date(2026, 9, 1), date(2026, 9, 30))),
    ("12_derniers_mois", (date(2025, 10, 1), date(2026, 9, 30))),
    ("tout", (None, None)),
])
def test_bornes_des_periodes(type_periode, attendu):
    """Les périodes sont relatives à aujourd'hui : le tableau reste juste l'an prochain."""
    assert statistiques.bornes({"type": type_periode}, aujourdhui=date(2026, 9, 3)) == attendu


def test_nombre_sur_une_periode(session, jeu):
    resultat = _calcul(session, {"type": "nombre",
                                 "periode": {"champ": "date_document", "type": "annee_en_cours"}})
    assert resultat["valeur"] == 4   # tb1, tb2, tb3, tb6


def test_somme_des_montants(session, jeu):
    """Un document sans montant est compté mais ne fausse pas le total."""
    resultat = _calcul(session, {"type": "somme", "champ": "meta:montant_ttc",
                                 "periode": {"champ": "date_document", "type": "annee_en_cours"}})
    assert resultat["valeur"] == pytest.approx(175.50)
    precedente = _calcul(session, {"type": "somme", "champ": "meta:montant_ttc",
                                   "periode": {"champ": "date_document", "type": "annee_precedente"}})
    assert precedente["valeur"] == pytest.approx(310.00)


def test_repartition_par_emetteur(session, jeu):
    resultat = _calcul(session, {"type": "repartition", "champ": "meta:emetteur"})
    valeurs = {p["libelle"]: p["valeur"] for p in resultat["points"]}
    assert valeurs["EDF"] == 4
    assert valeurs["Non renseigné"] == 2


def test_repartition_en_totalisant_un_montant(session, jeu):
    resultat = _calcul(session, {"type": "repartition", "champ": "meta:emetteur",
                                 "mesure": "somme", "mesure_champ": "meta:montant_ttc"})
    valeurs = {p["libelle"]: p["valeur"] for p in resultat["points"]}
    assert valeurs["EDF"] == pytest.approx(450.50)   # 100 + 50,50 + 300
    assert valeurs["Non renseigné"] == pytest.approx(35.00)


def test_repartition_triee_par_valeur_decroissante(session, jeu):
    points = _calcul(session, {"type": "repartition", "champ": "meta:emetteur"})["points"]
    assert [p["valeur"] for p in points] == sorted((p["valeur"] for p in points), reverse=True)


def test_evolution_mensuelle_sans_trous(session, jeu):
    """
    Les mois sans document valent zéro : une série trouée se lit mal, et
    l'absence de document est elle-même une information.
    """
    resultat = _calcul(session, {"type": "evolution", "granularite": "mois",
                                 "periode": {"champ": "date_document", "type": "annee_en_cours"}})
    valeurs = {p["cle"]: p["valeur"] for p in resultat["points"]}
    assert len(resultat["points"]) == 12
    assert valeurs["2026-01"] == 1 and valeurs["2026-02"] == 2 and valeurs["2026-04"] == 0


def test_evolution_annuelle(session, jeu):
    resultat = _calcul(session, {"type": "evolution", "granularite": "annee"})
    valeurs = {p["cle"]: p["valeur"] for p in resultat["points"]}
    assert valeurs["2025"] == 2 and valeurs["2026"] == 4


def test_le_perimetre_est_respecte(session, jeu):
    """Un filtre restreint bien l'indicateur, au format du registre."""
    resultat = _calcul(session, {
        "type": "nombre",
        # La valeur est la **référence** de la ligne, pas son identifiant nu :
        # c'est ce que la liste de suggestions envoie (§21.12).
        "filtres": [{"champ": "meta:emetteur", "operateur": "egal",
                     "valeur": f"usr_emetteurs:{jeu['edf']}"}],
    })
    assert resultat["valeur"] == 4


@pytest.mark.parametrize("indicateur, extrait", [
    ({"type": "camembert"}, "inconnu"),
    ({"type": "somme"}, "métadonnée"),
    ({"type": "repartition", "champ": "nom_fichier"}, "impossible"),
    ({"type": "nombre", "periode": {"type": "hier"}}, "Période"),
    ({"type": "evolution", "granularite": "semaine"}, "Granularité"),
])
def test_descriptions_inexploitables(session, indicateur, extrait):
    with pytest.raises(statistiques.IndicateurInvalide) as erreur:
        _calcul(session, indicateur)
    assert extrait.lower() in str(erreur.value).lower()


def test_le_tableau_d_accueil_est_calculable(client):
    """Il est livré avec l'application : il doit fonctionner sur toute installation."""
    tableau = client.get("/tableaux-de-bord/accueil/donnees").json()
    assert tableau["modifiable"] is False
    assert tableau["widgets"], "le tableau d'accueil ne contient aucun indicateur"
    for widget in tableau["widgets"]:
        assert widget.get("erreur") is None, f"{widget['titre']} : {widget.get('erreur')}"


def test_un_indicateur_fautif_n_empeche_pas_les_autres(client):
    """Une case en erreur ne doit pas emporter tout le tableau."""
    reponse = client.post("/admin/tableaux-de-bord", json={
        "nom": "Test mixte", "widgets": [{"id": "ok", "type": "nombre", "titre": "Total"}],
        "partage": True, "ordre": 900})
    tableau_id = reponse.json()["id"]
    # on force ensuite une description fautive directement en base
    session = SessionLocal()
    from app.db import TableauDeBord
    tableau = session.get(TableauDeBord, tableau_id)
    tableau.widgets = '[{"id":"ok","type":"nombre","titre":"Total"},' \
                      '{"id":"ko","type":"camembert","titre":"Cassé"}]'
    session.commit()
    session.close()

    widgets = client.get(f"/tableaux-de-bord/{tableau_id}/donnees").json()["widgets"]
    par_id = {w["id"]: w for w in widgets}
    assert par_id["ok"].get("erreur") is None and par_id["ok"]["valeur"] >= 0
    assert par_id["ko"].get("erreur")
    client.delete(f"/admin/tableaux-de-bord/{tableau_id}")


def test_un_tableau_n_est_composable_que_par_un_administrateur(client, jeton_de):
    client.post("/admin/utilisateurs", json={
        "email": "_tb@test.local", "nom": "T", "prenom": "Test", "mot_de_passe": "motdepasse-test-1234",
        "est_admin": False, "actif": True, "role_ids": []})
    membre = jeton_de("_tb@test.local", "motdepasse-test-1234")
    assert membre.post("/admin/tableaux-de-bord",
                       json={"nom": "X", "widgets": []}).status_code == 403
    assert membre.get("/tableaux-de-bord").status_code == 200


def test_repartition_par_dossier(session, jeu):
    """
    Mesurer un ensemble (§19.9) : un document appartient à un type, et c'est le
    type qui vit dans un dossier. Grouper par dossier répond à « combien pour la
    maison », ce qu'aucun groupement ne savait faire — un dossier ne porte aucun
    document en propre, il ne serait jamais apparu dans un groupement par
    catégorie.
    """
    factures = session.get(Categorie, jeu["factures"])
    dossier = Categorie(nom="_TbDossier", nature="dossier", ordre=960)
    session.add(dossier)
    session.flush()
    parent_avant = factures.parent_id
    factures.parent_id = dossier.id
    session.flush()

    try:
        resultat = _calcul(session, {"type": "repartition", "champ": "dossier",
                                     "portee": "tous"})
        libelles = {p["libelle"]: p["valeur"] for p in resultat["points"]}
        assert libelles.get("_TbDossier") == 6, \
            "les six factures doivent compter pour leur dossier, pas pour leur type"
    finally:
        factures.parent_id = parent_avant
        session.delete(dossier)
        session.flush()


def test_un_type_a_la_racine_forme_son_propre_groupe(session, jeu):
    """
    Le ranger dans « Non renseigné » laisserait croire à une erreur de classement
    là où il n'y en a pas : un type peut très bien vivre à la racine.
    """
    resultat = _calcul(session, {"type": "repartition", "champ": "dossier", "portee": "tous"})
    libelles = {p["libelle"] for p in resultat["points"]}
    assert "Factures" in libelles


def test_le_dossier_est_propose_comme_groupement(client):
    options = client.get("/tableaux-de-bord/options").json()
    champs = {g["champ"]: g["libelle"] for g in options["groupements"]}
    assert champs["dossier"] == "Dossier"
    assert champs["categorie"] == "Type de document", \
        "les deux niveaux doivent se distinguer là où ils se côtoient"


def test_un_indicateur_limite_a_un_dossier_compte_ses_types(session, jeu):
    """
    Le filtre par catégorie remontait déjà les descendants ; ce test le fige pour
    un **dossier**, qui est désormais le cas courant — c'est ainsi qu'on mesure
    « tout ce qui est rangé sous Maison ».
    """
    factures = session.get(Categorie, jeu["factures"])
    dossier = Categorie(nom="_TbPortee", nature="dossier", ordre=961)
    session.add(dossier)
    session.flush()
    parent_avant = factures.parent_id
    factures.parent_id = dossier.id
    session.flush()

    try:
        resultat = _calcul(session, {
            "type": "nombre", "portee": "tous",
            "filtres": [{"champ": "categorie", "operateur": "egal", "valeur": str(dossier.id)}],
        })
        assert resultat["valeur"] == 6
    finally:
        factures.parent_id = parent_avant
        session.delete(dossier)
        session.flush()
