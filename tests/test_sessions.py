"""
Registre des sessions (§17.2).

Un JWT porte sa propre validité : jusqu'ici, le serveur ne savait pas qui était
connecté et ne pouvait fermer aucune session avant son expiration. Ces tests
vérifient les deux capacités que le registre apporte — voir ses appareils, et en
fermer un — ainsi que la propriété qui les rend utiles : une session fermée
cesse **immédiatement** de donner accès.
"""
import pytest
from fastapi.testclient import TestClient

from app.api import app

AGENT_PORTABLE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")
AGENT_TELEPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1")


@pytest.fixture
def compte(client):
    """Un compte ordinaire, et de quoi ouvrir plusieurs sessions dessus."""
    email, motdepasse = "_t_sessions@homeged.local", "MotDePasse!42"
    existant = [u for u in client.get("/admin/utilisateurs").json() if u["email"] == email]
    for u in existant:
        client.delete(f"/admin/utilisateurs/{u['id']}")
    reponse = client.post("/admin/utilisateurs", json={
        "email": email, "nom": "Test sessions", "prenom": "Test", "mot_de_passe": motdepasse,
        "est_admin": False, "actif": True, "role_ids": [],
    })
    assert reponse.status_code == 200, reponse.text
    identifiant = reponse.json()["id"]
    yield email, motdepasse
    client.delete(f"/admin/utilisateurs/{identifiant}")


def _ouvrir(email, motdepasse, agent):
    client = TestClient(app)
    client.headers["User-Agent"] = agent
    reponse = client.post("/auth/login", data={"username": email, "password": motdepasse})
    assert reponse.status_code == 200, reponse.text
    client.headers["Authorization"] = f"Bearer {reponse.json()['access_token']}"
    return client


def test_chaque_connexion_apparait_avec_son_appareil(compte):
    email, motdepasse = compte
    portable = _ouvrir(email, motdepasse, AGENT_PORTABLE)
    _ouvrir(email, motdepasse, AGENT_TELEPHONE)

    sessions = portable.get("/moi/sessions").json()
    assert len(sessions) == 2
    appareils = {s["appareil"] for s in sessions}
    assert appareils == {"Chrome sur Windows", "Safari sur iPhone"}, \
        "l'utilisateur doit reconnaître ses appareils, pas lire un User-Agent"
    courantes = [s for s in sessions if s["courante"]]
    assert len(courantes) == 1 and courantes[0]["appareil"] == "Chrome sur Windows", \
        "une seule session est celle qui pose la question, et elle est signalée"


def test_fermer_une_session_coupe_immediatement_son_acces(compte):
    email, motdepasse = compte
    portable = _ouvrir(email, motdepasse, AGENT_PORTABLE)
    telephone = _ouvrir(email, motdepasse, AGENT_TELEPHONE)
    assert telephone.get("/auth/me").status_code == 200

    cible = next(s for s in portable.get("/moi/sessions").json() if not s["courante"])
    assert portable.delete(f"/moi/sessions/{cible['id']}").status_code == 200

    assert telephone.get("/auth/me").status_code == 401, "le jeton fermé ne vaut plus rien"
    assert portable.get("/auth/me").status_code == 200, "celle qui a fermé continue"
    assert len(portable.get("/moi/sessions").json()) == 1


def test_fermer_les_autres_laisse_la_sienne(compte):
    email, motdepasse = compte
    portable = _ouvrir(email, motdepasse, AGENT_PORTABLE)
    telephone = _ouvrir(email, motdepasse, AGENT_TELEPHONE)
    script = _ouvrir(email, motdepasse, "python-urllib/3.12")

    reponse = portable.post("/moi/sessions/fermer-les-autres")
    assert reponse.status_code == 200 and reponse.json()["fermees"] == 2

    assert telephone.get("/auth/me").status_code == 401
    assert script.get("/auth/me").status_code == 401
    assert portable.get("/auth/me").status_code == 200


def test_la_deconnexion_revoque_le_jeton(compte):
    """
    Sans révocation côté serveur, le jeton d'une session « fermée » restait
    valable jusqu'à son expiration pour qui l'aurait recopié.
    """
    email, motdepasse = compte
    session = _ouvrir(email, motdepasse, AGENT_PORTABLE)
    jeton = session.headers["Authorization"]

    assert session.post("/auth/logout").status_code == 200

    autre = TestClient(app)
    autre.headers["Authorization"] = jeton
    assert autre.get("/auth/me").status_code == 401


def test_on_ne_voit_ni_ne_ferme_les_sessions_dun_autre(client, compte):
    email, motdepasse = compte
    autre = _ouvrir(email, motdepasse, AGENT_PORTABLE)
    sienne = autre.get("/moi/sessions").json()[0]

    # l'administrateur a ses propres sessions, pas celles-là
    miennes = {s["id"] for s in client.get("/moi/sessions").json()}
    assert sienne["id"] not in miennes
    assert client.delete(f"/moi/sessions/{sienne['id']}").status_code == 404
    assert autre.get("/auth/me").status_code == 200, "elle ne devait pas être touchée"


def test_changer_de_mot_de_passe_ferme_les_autres_sessions(compte):
    email, motdepasse = compte
    portable = _ouvrir(email, motdepasse, AGENT_PORTABLE)
    telephone = _ouvrir(email, motdepasse, AGENT_TELEPHONE)

    reponse = portable.post("/moi/mot-de-passe",
                            json={"ancien": motdepasse, "nouveau": "AutreMotDePasse!7"})
    assert reponse.status_code == 200, reponse.text
    portable.headers["Authorization"] = f"Bearer {reponse.json()['access_token']}"

    assert telephone.get("/auth/me").status_code == 401
    assert portable.get("/auth/me").status_code == 200
    assert len(portable.get("/moi/sessions").json()) == 1
