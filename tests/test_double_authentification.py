"""
Mot de passe et double authentification, vus depuis l'API.

`test_otp.py` vérifie l'algorithme ; ici on vérifie ce qui l'entoure, et qui
compte tout autant : qu'un code refusé refuse, qu'un code de secours ne serve
qu'une fois, qu'un changement de mot de passe referme les sessions ouvertes, et
qu'une double authentification imposée par un administrateur contraigne
réellement au lieu de suggérer.
"""
import pytest
from fastapi.testclient import TestClient

from app import otp
from app.api import app
from app.db import SessionLocal, Utilisateur

MDP = "MotDePasse!42"


@pytest.fixture
def compte(client):
    """Un compte ordinaire, jetable, et un client connecté dessus."""
    email = "_t_2fa_api@homeged.local"
    session = SessionLocal()
    try:
        existant = session.query(Utilisateur).filter_by(email=email).one_or_none()
        if existant:
            session.delete(existant)
            session.commit()
    finally:
        session.close()

    reponse = client.post("/admin/utilisateurs", json={
        "email": email, "nom": "Test 2FA", "prenom": "Test", "mot_de_passe": MDP,
        "est_admin": False, "actif": True, "role_ids": [],
    })
    assert reponse.status_code == 200, reponse.text
    identifiant = reponse.json()["id"]

    yield identifiant, email, _connecter(email, MDP)

    client.delete(f"/admin/utilisateurs/{identifiant}")


def _connecter(email, mot_de_passe):
    """Client authentifié, ou la réponse brute si un second facteur est attendu."""
    sous_client = TestClient(app)
    reponse = sous_client.post("/auth/login", data={"username": email, "password": mot_de_passe})
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    if corps.get("access_token"):
        sous_client.headers["Authorization"] = f"Bearer {corps['access_token']}"
    sous_client.corps_connexion = corps
    return sous_client


def _activer_otp(session_client):
    """Prépare puis active la double authentification ; rend (secret, codes)."""
    preparation = session_client.post("/moi/otp/preparer")
    assert preparation.status_code == 200, preparation.text
    secret = preparation.json()["secret"]
    activation = session_client.post("/moi/otp/activer", json={"code": otp.code(secret)})
    assert activation.status_code == 200, activation.text
    return secret, activation.json()["codes"]


# ------------------------------------------------------------
# Mot de passe
# ------------------------------------------------------------

def test_changement_de_mot_de_passe_ferme_les_sessions_ouvertes(compte):
    _, email, connecte = compte
    ancien_jeton = connecte.headers["Authorization"]

    assert connecte.post("/moi/mot-de-passe",
                         json={"ancien": "faux", "nouveau": "AssezLong!2026"}).status_code == 400
    assert connecte.post("/moi/mot-de-passe",
                         json={"ancien": MDP, "nouveau": "court"}).status_code == 422
    assert connecte.post("/moi/mot-de-passe",
                         json={"ancien": MDP, "nouveau": MDP}).status_code == 422

    reponse = connecte.post("/moi/mot-de-passe", json={"ancien": MDP, "nouveau": "AssezLong!2026"})
    assert reponse.status_code == 200, reponse.text

    # une autre session, ouverte avant le changement, tombe
    autre = TestClient(app)
    autre.headers["Authorization"] = ancien_jeton
    assert autre.get("/moi").status_code == 401

    # celle qui a demandé le changement continue, avec son jeton renouvelé
    connecte.headers["Authorization"] = f"Bearer {reponse.json()['access_token']}"
    assert connecte.get("/moi").status_code == 200
    assert _connecter(email, "AssezLong!2026").get("/moi").status_code == 200


# ------------------------------------------------------------
# Double authentification
# ------------------------------------------------------------

def test_activation_exige_un_code_valide(compte):
    _, _, connecte = compte
    secret = connecte.post("/moi/otp/preparer").json()["secret"]
    assert connecte.post("/moi/otp/activer", json={"code": "000000"}).status_code == 400
    assert connecte.get("/moi").json()["otp_actif"] is False

    assert connecte.post("/moi/otp/activer", json={"code": otp.code(secret)}).status_code == 200
    profil = connecte.get("/moi").json()
    assert profil["otp_actif"] is True
    assert profil["codes_secours_restants"] == otp.NOMBRE_CODES_SECOURS


def test_connexion_en_deux_temps(compte):
    _, email, connecte = compte
    secret, _ = _activer_otp(connecte)

    anonyme = TestClient(app)
    premiere = anonyme.post("/auth/login", data={"username": email, "password": MDP}).json()
    assert premiere["otp_requis"] is True
    assert premiere["access_token"] is None, "le mot de passe seul n'ouvre plus la session"

    intermediaire = premiere["jeton_intermediaire"]
    # le jeton intermédiaire n'est pas une session
    porteur = TestClient(app)
    porteur.headers["Authorization"] = f"Bearer {intermediaire}"
    assert porteur.get("/moi").status_code == 401

    refus = anonyme.post("/auth/otp", json={"jeton_intermediaire": intermediaire, "code": "111111"})
    assert refus.status_code == 401

    ok = anonyme.post("/auth/otp",
                      json={"jeton_intermediaire": intermediaire, "code": otp.code(secret)})
    assert ok.status_code == 200, ok.text
    porteur.headers["Authorization"] = f"Bearer {ok.json()['access_token']}"
    assert porteur.get("/moi").status_code == 200


def test_code_de_secours_utilisable_une_seule_fois(compte):
    _, email, connecte = compte
    _, codes = _activer_otp(connecte)
    anonyme = TestClient(app)

    def etape_deux(code_propose):
        premiere = anonyme.post("/auth/login", data={"username": email, "password": MDP}).json()
        return anonyme.post("/auth/otp", json={"jeton_intermediaire": premiere["jeton_intermediaire"],
                                               "code": code_propose})

    assert etape_deux(codes[0]).status_code == 200
    assert etape_deux(codes[0]).status_code == 401, "un code de secours ne resservira pas"
    assert etape_deux(codes[1]).status_code == 200
    assert connecte.get("/moi").json()["codes_secours_restants"] == otp.NOMBRE_CODES_SECOURS - 2


def test_desactivation_exige_le_mot_de_passe(compte):
    _, _, connecte = compte
    _activer_otp(connecte)
    assert connecte.post("/moi/otp/desactiver", json={"mot_de_passe": "faux"}).status_code == 400
    assert connecte.get("/moi").json()["otp_actif"] is True
    assert connecte.post("/moi/otp/desactiver", json={"mot_de_passe": MDP}).status_code == 200
    assert connecte.get("/moi").json()["otp_actif"] is False


# ------------------------------------------------------------
# Exigence administrateur
# ------------------------------------------------------------

def test_double_authentification_imposee_contraint_vraiment(client, compte):
    identifiant, email, connecte = compte
    impose = client.put(f"/admin/utilisateurs/{identifiant}", json={
        "email": email, "nom": "Test 2FA", "prenom": "Test", "est_admin": False, "actif": True,
        "otp_impose": True, "role_ids": [],
    })
    assert impose.status_code == 200, impose.text
    assert impose.json()["otp_impose"] is True

    entree = TestClient(app)
    corps = entree.post("/auth/login", data={"username": email, "password": MDP}).json()
    assert corps["otp_a_configurer"] is True
    entree.headers["Authorization"] = f"Bearer {corps['access_token']}"

    # la session existe, mais elle ne donne accès qu'à la configuration
    assert entree.get("/documents").status_code == 403
    assert entree.get("/moi").status_code == 200
    # /auth/me doit répondre : c'est par lui que l'interface reconnaît la
    # session au chargement. Le refuser renvoyait le compte à l'écran de
    # connexion après une connexion réussie — bloqué hors de la page censée
    # le débloquer.
    assert entree.get("/auth/me").status_code == 200

    secret = entree.post("/moi/otp/preparer").json()["secret"]
    assert entree.post("/moi/otp/activer", json={"code": otp.code(secret)}).status_code == 200

    apres = TestClient(app)
    premiere = apres.post("/auth/login", data={"username": email, "password": MDP}).json()
    ouverture = apres.post("/auth/otp", json={"jeton_intermediaire": premiere["jeton_intermediaire"],
                                              "code": otp.code(secret)})
    apres.headers["Authorization"] = f"Bearer {ouverture.json()['access_token']}"
    assert apres.get("/documents").status_code == 200

    # et l'utilisateur ne peut pas défaire ce qu'un administrateur exige
    assert apres.post("/moi/otp/desactiver", json={"mot_de_passe": MDP}).status_code == 403


def test_administrateur_peut_debloquer_un_second_facteur_perdu(client, compte):
    identifiant, email, connecte = compte
    _activer_otp(connecte)

    reponse = client.post(f"/admin/utilisateurs/{identifiant}/otp/reinitialiser")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["otp_actif"] is False

    # le compte se reconnecte au mot de passe seul
    retour = TestClient(app).post("/auth/login", data={"username": email, "password": MDP}).json()
    assert retour["otp_requis"] is False
    assert retour["access_token"]


def test_routes_du_compte_refusees_sans_session():
    anonyme = TestClient(app)
    assert anonyme.get("/moi").status_code == 401
    assert anonyme.post("/moi/otp/preparer").status_code == 401
    assert anonyme.post("/moi/mot-de-passe", json={"ancien": "a", "nouveau": "b"}).status_code == 401
