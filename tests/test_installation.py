"""
Première installation (§18.23).

Le premier compte naissait de `.env` : pour ouvrir HomeGED chez soi il fallait un
accès au serveur, et le mot de passe du foyer restait écrit en clair sur le
disque. Il se crée maintenant depuis l'écran — à la seule condition qu'aucun
compte n'existe.

C'est cette condition qui rend la porte sûre, et c'est donc elle que ces tests
éprouvent en premier.
"""
import pytest

from app import auth, config, installation
from tests.conftest import reconstruire_base
from app.db import Categorie, Document, RegleExtraction, SessionLocal, Utilisateur


@pytest.fixture
def base_sans_compte(base_de_test, monkeypatch):
    """
    Vide les comptes le temps d'un test, puis rétablit l'administrateur attendu
    par les autres. Sans ce rétablissement, tout ce qui suit ne pourrait plus se
    connecter — et l'on chercherait longtemps pourquoi.

    Le mot de passe de `.env` est neutralisé pendant ce temps : sans cela, le
    démarrage de l'application recrée aussitôt le compte, et l'on n'observe
    jamais l'état qu'on voulait éprouver. C'est d'ailleurs exactement la
    situation d'un foyer neuf, dont le `.env` ne porte aucun mot de passe choisi.
    """
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "changeme")
    session = SessionLocal()
    try:
        session.query(Utilisateur).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()

    yield

    monkeypatch.undo()
    session = SessionLocal()
    try:
        session.query(Utilisateur).delete(synchronize_session=False)
        session.commit()
        session.add(Utilisateur(
            email=config.ADMIN_EMAIL, nom="Administrateur",
            mot_de_passe_hash=auth.hash_mot_de_passe(config.ADMIN_PASSWORD),
            est_admin=True, actif=True))
        session.commit()
    finally:
        session.close()


def _client_nu():
    from fastapi.testclient import TestClient
    from app.api import app
    return TestClient(app)


def test_l_installation_est_annoncee_quand_la_base_est_vierge(base_sans_compte):
    with _client_nu() as client:
        etat = client.get("/installation").json()
        assert etat["requise"] is True
        assert etat["classement_seme"] >= 0
        assert "Europe/Paris" in etat["fuseaux"]


def test_la_porte_est_fermee_des_qu_un_compte_existe(client):
    """Le seul verrou, et il suffit : plus de compte à créer, plus d'entrée."""
    assert client.get("/installation").json()["requise"] is False
    refus = client.post("/installation", json={
        "email": "intrus@exemple.fr", "mot_de_passe": "MotDePasse!42",
    })
    assert refus.status_code == 400
    assert "déjà installé" in refus.json()["detail"]


def test_le_premier_compte_se_cree_depuis_l_ecran(base_sans_compte):
    with _client_nu() as client:
        reponse = client.post("/installation", json={
            "email": "Chef@Foyer.fr", "mot_de_passe": "MotDePasse!42",
            "prenom": "Camille", "nom": "Dupont",
            "nom_foyer": "Maison Dupont", "fuseau_horaire": "America/Montreal",
            "classement": "conserver",
        })
        assert reponse.status_code == 200, reponse.text
        corps = reponse.json()
        assert corps["email"] == "chef@foyer.fr", "l'adresse est normalisée"
        assert corps["access_token"], "on entre directement, sans reconnexion"
        assert corps["reglages"]["nom_foyer"] == "Maison Dupont"
        assert corps["reglages"]["fuseau_horaire"] == "America/Montreal"

        # le compte créé est bien administrateur, et il peut se connecter
        connexion = client.post("/auth/login", data={
            "username": "chef@foyer.fr", "password": "MotDePasse!42"})
        assert connexion.status_code == 200
        client.headers["Authorization"] = f"Bearer {connexion.json()['access_token']}"
        assert client.get("/auth/me").json()["est_admin"] is True

        # et la porte s'est refermée
        assert client.get("/installation").json()["requise"] is False


def test_un_mot_de_passe_trop_court_est_refuse(base_sans_compte):
    with _client_nu() as client:
        refus = client.post("/installation", json={
            "email": "chef@foyer.fr", "mot_de_passe": "court"})
        assert refus.status_code == 400
        assert "caractères" in refus.json()["detail"]
        # rien n'a été créé : une tentative refusée ne doit pas fermer la porte
        assert client.get("/installation").json()["requise"] is True


def test_un_reglage_invalide_n_installe_rien(base_sans_compte):
    """
    Tout est validé avant d'écrire : un compte créé puis un fuseau refusé
    laisserait une installation à moitié faite, dont la seconde tentative se
    heurterait à la porte désormais fermée.
    """
    with _client_nu() as client:
        refus = client.post("/installation", json={
            "email": "chef@foyer.fr", "mot_de_passe": "MotDePasse!42",
            "fuseau_horaire": "Terre/Milieu"})
        assert refus.status_code in (400, 422)
        assert client.get("/installation").json()["requise"] is True


def test_repartir_d_une_page_blanche_efface_le_classement_seme(base_sans_compte, monkeypatch):
    """
    Ce test **abîme l'état commun pour de bon** : il efface le classement semé,
    dont d'autres tests ont besoin. Il le rend donc, en reconstruisant la base
    comme au premier démarrage. C'est le prix d'un test qui éprouve une opération
    globale ; le camoufler — en ne vérifiant qu'un appel de fonction — reviendrait
    à ne pas la tester.

    Les documents laissés par les tests précédents empêcheraient légitimement le
    vidage (voir le test suivant) : on neutralise ce garde-fou ici, puisque le
    cas qu'on éprouve est celui d'une base neuve.
    """
    monkeypatch.setattr(installation, "_documents_classes", lambda session: 0)
    session = SessionLocal()
    try:
        assert session.query(Categorie).count() > 0, "le classement semé doit être là au départ"
    finally:
        session.close()

    try:
        with _client_nu() as client:
            reponse = client.post("/installation", json={
                "email": "chef@foyer.fr", "mot_de_passe": "MotDePasse!42",
                "classement": "vierge"})
            assert reponse.status_code == 200, reponse.text

        session = SessionLocal()
        try:
            assert session.query(Categorie).count() == 0
            assert session.query(RegleExtraction).count() == 0
        finally:
            session.close()
    finally:
        reconstruire_base()


def test_on_ne_vide_pas_un_classement_qui_porte_des_documents(base_sans_compte):
    """
    Le classement n'est pas décoratif : des fiches y sont rattachées. L'effacer
    d'un revers laisserait des documents sans catégorie et des champs sans règle.
    """
    session = SessionLocal()
    try:
        categorie = session.query(Categorie).first()
        if not categorie:
            categorie = Categorie(nom="_InstallTest")
            session.add(categorie)
            session.flush()
        session.add(Document(nom_fichier="_install.pdf", chemin_stockage="/x.pdf",
                             hash_sha256="install".ljust(64, "i"), texte_ocr="x",
                             statut="traite", categorie_id=categorie.id))
        session.commit()
    finally:
        session.close()

    try:
        with _client_nu() as client:
            refus = client.post("/installation", json={
                "email": "chef@foyer.fr", "mot_de_passe": "MotDePasse!42",
                "classement": "vierge"})
            assert refus.status_code == 400
            assert "documents" in refus.json()["detail"].lower()
            assert client.get("/installation").json()["requise"] is True
    finally:
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier == "_install.pdf").delete()
            session.commit()
        finally:
            session.close()


def test_l_amorcage_par_env_reste_possible(base_sans_compte, monkeypatch):
    """
    Les installations existantes ne changent pas de comportement : un `.env` qui
    porte un mot de passe délibéré crée toujours son compte au démarrage.
    """
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "MotDePasseChoisi!42")
    session = SessionLocal()
    try:
        auth.creer_admin_si_absent(session)
        assert session.query(Utilisateur).count() == 1
    finally:
        session.close()


def test_un_mot_de_passe_d_exemple_n_ouvre_aucun_compte(base_sans_compte):
    """
    Un `.env` recopié sans être relu ne doit pas ouvrir un compte administrateur
    dont le mot de passe est connu de tous. Dans ce cas, l'assistant prend la main.
    (Le mot de passe est déjà neutralisé par la fixture.)
    """
    session = SessionLocal()
    try:
        auth.creer_admin_si_absent(session)
        assert session.query(Utilisateur).count() == 0
        assert installation.est_requise(session) is True
    finally:
        session.close()


def test_l_application_pose_son_schema_sur_une_base_vierge(base_de_test):
    """
    Une installation neuve ne doit dépendre ni des droits de lecture d'un fichier
    de l'hôte, ni d'un montage qu'on aurait oublié (§18.31).

    MariaDB joue `db/schema.sql` au premier démarrage **s'il peut le lire**. Sur
    une machine où le dépôt est en droits restreints, l'utilisateur `mysql` du
    conteneur ne le peut pas : la base démarre vide, et l'API tourne en boucle
    sur des tables absentes en se plaignant d'une table, pas d'un droit. Le
    conteneur d'essai a mis ce défaut au jour ; l'application pose désormais son
    schéma elle-même.
    """
    from sqlalchemy import text as sql_text

    from app.db import engine
    from app.migrations import base_vierge, installer_schema

    with engine.connect() as connexion:
        assert base_vierge(connexion) is False, "la base des tests porte déjà le schéma"

    # Sur une base déjà installée, l'opération ne fait rien : elle est sûre à
    # chaque démarrage, comme les migrations.
    assert installer_schema() is False

    # Base vidée : le schéma se réinstalle seul, et les migrations sont marquées
    # comme déjà appliquées — une installation neuve ne les rejoue pas.
    with engine.connect() as connexion:
        connexion.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        for (nom,) in connexion.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()"
        ):
            connexion.exec_driver_sql(f"DROP TABLE IF EXISTS `{nom}`")
        connexion.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
        connexion.commit()
        assert base_vierge(connexion) is True

    try:
        assert installer_schema() is True
        with engine.connect() as connexion:
            assert base_vierge(connexion) is False
            tables = connexion.execute(sql_text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE()")).scalar()
            migrations = connexion.execute(
                sql_text("SELECT COUNT(*) FROM sys_schema_migrations")).scalar()
        assert tables > 15, "le schéma complet, pas seulement quelques tables"
        assert migrations > 0, "les migrations sont marquées appliquées, pas rejouées"
    finally:
        # Ce test défait la base commune : il la rend, comme celui du classement
        # remis à blanc.
        reconstruire_base()
