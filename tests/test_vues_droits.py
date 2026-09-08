"""
Qui peut créer et supprimer une vue (§17.17).

Une vue enregistrée est un élément de navigation partagé par le foyer, au même
titre qu'une catégorie : sa création et sa suppression appartiennent à
l'administration. Ces tests vérifient que la règle tient **à l'API**, et pas
seulement dans l'interface — masquer un bouton ne protège de rien.
"""
import pytest
from fastapi.testclient import TestClient

from app.api import app

MDP = "MotDePasse!42"


@pytest.fixture
def compte_ordinaire(client):
    email = "_t_vues_api@homeged.local"
    for u in client.get("/admin/utilisateurs").json():
        if u["email"] == email:
            client.delete(f"/admin/utilisateurs/{u['id']}")
    reponse = client.post("/admin/utilisateurs", json={
        "email": email, "nom": "Sans droits", "prenom": "Test", "mot_de_passe": MDP,
        "est_admin": False, "actif": True, "role_ids": [],
    })
    assert reponse.status_code == 200, reponse.text
    identifiant = reponse.json()["id"]

    sous_client = TestClient(app)
    jeton = sous_client.post("/auth/login", data={"username": email, "password": MDP})
    sous_client.headers["Authorization"] = f"Bearer {jeton.json()['access_token']}"

    yield sous_client
    client.delete(f"/admin/utilisateurs/{identifiant}")


@pytest.fixture
def vue(client):
    reponse = client.post("/vues", json={
        "nom": "_VueDroits", "categorie_id": None, "criteres": [],
        "partagee": True, "ordre": 900,
    })
    assert reponse.status_code == 200, reponse.text
    identifiant = reponse.json()["id"]
    yield identifiant
    client.delete(f"/vues/{identifiant}")


def test_un_compte_ordinaire_ne_cree_pas_de_vue(compte_ordinaire):
    reponse = compte_ordinaire.post("/vues", json={
        "nom": "_Interdite", "categorie_id": None, "criteres": [],
        "partagee": True, "ordre": 100,
    })
    assert reponse.status_code == 403
    assert "administrateur" in reponse.json()["detail"].lower()


def test_un_compte_ordinaire_ne_supprime_pas_de_vue(compte_ordinaire, vue):
    assert compte_ordinaire.delete(f"/vues/{vue}").status_code == 403
    # la vue est toujours là, et il la voit toujours
    noms = [v["nom"] for v in compte_ordinaire.get("/vues").json()]
    assert "_VueDroits" in noms


def test_les_vues_ne_sont_pas_annoncees_modifiables_a_un_compte_ordinaire(compte_ordinaire, vue):
    """
    L'interface se fie à ce drapeau pour afficher — ou non — le bouton de
    suppression. S'il mentait, l'utilisateur cliquerait sur un bouton qui échoue.
    """
    for v in compte_ordinaire.get("/vues").json():
        assert v["modifiable"] is False


def test_un_administrateur_cree_et_supprime(client):
    creation = client.post("/vues", json={
        "nom": "_VueAdmin", "categorie_id": None, "criteres": [],
        "partagee": True, "ordre": 901,
    })
    assert creation.status_code == 200, creation.text
    assert creation.json()["modifiable"] is True
    assert client.delete(f"/vues/{creation.json()['id']}").status_code == 200
