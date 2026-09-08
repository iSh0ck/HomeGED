"""
Limitation des tentatives de connexion : sans elle, rien n'empêche d'essayer des
mots de passe en boucle sur `/auth/login`.
"""
import pytest

from app import config
from app.limitation import LimiteurTentatives, cles


@pytest.fixture
def limiteur():
    return LimiteurTentatives(max_tentatives=3, fenetre=60, verrouillage=60)


def test_le_verrouillage_survient_au_seuil(limiteur):
    c = cles("10.0.0.1", "a@b.c")
    assert limiteur.attente_requise(c) is None
    assert limiteur.echec(c) is False
    assert limiteur.echec(c) is False
    assert limiteur.echec(c) is True, "le troisième échec doit verrouiller"
    assert limiteur.attente_requise(c) is not None


def test_une_connexion_reussie_efface_l_ardoise(limiteur):
    """Un utilisateur qui se trompe puis se rattrape ne doit pas être gêné ensuite."""
    c = cles("10.0.0.1", "a@b.c")
    limiteur.echec(c)
    limiteur.echec(c)
    limiteur.succes(c)
    assert limiteur.echec(c) is False
    assert limiteur.attente_requise(c) is None


def test_un_autre_compte_depuis_une_autre_adresse_n_est_pas_affecte(limiteur):
    for _ in range(3):
        limiteur.echec(cles("10.0.0.1", "victime@b.c"))
    assert limiteur.attente_requise(cles("10.0.0.2", "autre@b.c")) is None


def test_le_balayage_de_plusieurs_comptes_est_freine(limiteur):
    """Changer de compte à chaque essai ne doit pas contourner la limite."""
    for i in range(3):
        limiteur.echec(cles("10.0.0.9", f"compte{i}@b.c"))
    assert limiteur.attente_requise(cles("10.0.0.9", "encore-un@b.c")) is not None


def test_les_tentatives_anciennes_sont_oubliees():
    """La fenêtre est glissante : deux échecs très espacés ne verrouillent pas."""
    limiteur = LimiteurTentatives(max_tentatives=3, fenetre=0.05, verrouillage=60)
    import time
    c = cles("10.0.0.3", "a@b.c")
    limiteur.echec(c)
    limiteur.echec(c)
    time.sleep(0.1)
    assert limiteur.echec(c) is False
    assert limiteur.attente_requise(c) is None


def test_le_point_d_entree_refuse_apres_plusieurs_echecs(client):
    """Bout en bout : le énième mot de passe erroné renvoie 429, pas 401."""
    from app.api import limiteur_connexion
    limiteur_connexion.reinitialiser()
    try:
        codes = []
        for _ in range(config.LOGIN_MAX_TENTATIVES + 1):
            codes.append(client.post("/auth/login", data={
                "username": config.ADMIN_EMAIL, "password": "mauvais-mot-de-passe"}).status_code)
        assert codes[0] == 401
        assert codes[-1] == 429, f"codes obtenus : {codes}"

        refus = client.post("/auth/login", data={
            "username": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD})
        assert refus.status_code == 429, "le verrouillage doit valoir aussi pour le bon mot de passe"
        assert "Retry-After" in refus.headers
    finally:
        limiteur_connexion.reinitialiser()


def test_la_bonne_connexion_reste_possible_sous_le_seuil(client):
    from app.api import limiteur_connexion
    limiteur_connexion.reinitialiser()
    try:
        client.post("/auth/login", data={"username": config.ADMIN_EMAIL, "password": "faux"})
        reponse = client.post("/auth/login", data={
            "username": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD})
        assert reponse.status_code == 200
    finally:
        limiteur_connexion.reinitialiser()


def test_le_verrouillage_est_journalise(client):
    from app.api import limiteur_connexion
    limiteur_connexion.reinitialiser()
    try:
        for _ in range(config.LOGIN_MAX_TENTATIVES):
            client.post("/auth/login", data={"username": "intrus@test.local", "password": "x"})
        traces = client.get("/admin/audit", params={"action": "auth.verrouillage"}).json()
        assert traces["total"] >= 1
        assert traces["evenements"][0]["details"]["identifiant_tente"] == "intrus@test.local"
    finally:
        limiteur_connexion.reinitialiser()


# ------------------------------------------------------------
# Surveillance et déblocage depuis l'administration
# ------------------------------------------------------------

def test_l_ecran_de_surveillance_decrit_les_sources(client):
    from app.api import limiteur_connexion
    limiteur_connexion.reinitialiser()
    try:
        for _ in range(config.LOGIN_MAX_TENTATIVES):
            client.post("/auth/login", data={"username": "cible@test.local", "password": "x"})

        donnees = client.get("/admin/connexions").json()
        assert donnees["reglages"]["max_tentatives"] == config.LOGIN_MAX_TENTATIVES

        verrouillees = [e for e in donnees["entrees"] if e["verrouille"]]
        assert verrouillees, "aucune source verrouillée après le seuil"
        entree = verrouillees[0]
        assert entree["adresse"]
        assert entree["tentatives"] >= config.LOGIN_MAX_TENTATIVES
        assert entree["secondes_restantes"] > 0

        # le compte visé doit être identifiable
        comptes = [e["identifiant"] for e in donnees["entrees"] if e["portee"] == "compte"]
        assert "cible@test.local" in comptes

        # l'historique persiste, lui, au-delà de la mémoire du processus
        assert any(h["identifiant"] == "cible@test.local" for h in donnees["historique"])
    finally:
        limiteur_connexion.reinitialiser()


def test_le_deverrouillage_redonne_l_acces(client):
    from app.api import limiteur_connexion
    limiteur_connexion.reinitialiser()
    try:
        for _ in range(config.LOGIN_MAX_TENTATIVES + 1):
            client.post("/auth/login", data={
                "username": config.ADMIN_EMAIL, "password": "faux"})
        assert client.post("/auth/login", data={
            "username": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD}).status_code == 429

        for entree in client.get("/admin/connexions").json()["entrees"]:
            assert client.post("/admin/connexions/deverrouiller",
                               json={"cle": entree["cle"]}).status_code == 200

        assert client.post("/auth/login", data={
            "username": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD}).status_code == 200
    finally:
        limiteur_connexion.reinitialiser()


def test_deverrouiller_une_source_inconnue_renvoie_404(client):
    assert client.post("/admin/connexions/deverrouiller",
                       json={"cle": "adresse:203.0.113.9"}).status_code == 404


def test_tout_deverrouiller(client):
    from app.api import limiteur_connexion
    limiteur_connexion.reinitialiser()
    try:
        for compte in ("a@test.local", "b@test.local"):
            for _ in range(config.LOGIN_MAX_TENTATIVES):
                client.post("/auth/login", data={"username": compte, "password": "x"})
        assert client.get("/admin/connexions").json()["entrees"]
        assert client.post("/admin/connexions/tout-deverrouiller").json()["ok"] is True
        assert client.get("/admin/connexions").json()["entrees"] == []
    finally:
        limiteur_connexion.reinitialiser()
