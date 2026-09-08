"""
Consultation du registre sous l'identité d'un autre compte (§18.50).

Régler des droits sans pouvoir vérifier ce qu'ils donnent à voir, c'est régler à
l'aveugle. Mais la fonction consiste à se faire passer pour quelqu'un d'autre :
ces tests portent donc moins sur ce qu'elle permet que sur ce qu'elle interdit.
"""
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.api import app
from app.db import JournalAudit, SessionLocal

ENTETE = auth.ENTETE_CONSULTATION


@pytest.fixture
def compte_ordinaire(client):
    """Un compte sans droits, et sans catégorie autorisée."""
    email = "_t_consult@homeged.local"
    for u in client.get("/admin/utilisateurs").json():
        if u["email"] == email:
            client.delete(f"/admin/utilisateurs/{u['id']}")
    cree = client.post("/admin/utilisateurs", json={
        "email": email, "nom": "Sans", "prenom": "Droits",
        "mot_de_passe": "MotDePasse!42", "est_admin": False, "actif": True, "role_ids": [],
    })
    assert cree.status_code == 200, cree.text
    yield cree.json()
    client.delete(f"/admin/utilisateurs/{cree.json()['id']}")


def test_ladministrateur_voit_le_registre_avec_les_yeux_de_lautre(client, compte_ordinaire):
    ouverture = client.post(f"/admin/consultation/{compte_ordinaire['id']}")
    assert ouverture.status_code == 200, ouverture.text
    jeton = ouverture.json()["jeton"]

    moi = client.get("/moi", headers={ENTETE: jeton})
    assert moi.status_code == 200
    assert moi.json()["email"] == compte_ordinaire["email"]
    assert moi.json()["est_admin"] is False, \
        "l'interface doit se replier sur ce que voit le compte consulté"

    # sans l'en-tête, l'administrateur reste lui-même
    assert client.get("/moi").json()["est_admin"] is True


def test_la_consultation_est_en_lecture_seule(client, compte_ordinaire):
    """
    Le garde-fou principal : une action passée sous une autre identité
    apparaîtrait au journal au nom de quelqu'un qui ne l'a pas faite.
    """
    jeton = client.post(f"/admin/consultation/{compte_ordinaire['id']}").json()["jeton"]

    refus = client.post("/vues", json={"nom": "_essai", "criteres": []},
                        headers={ENTETE: jeton})
    assert refus.status_code == 403
    assert "lecture seule" in refus.json()["detail"].lower()


def test_le_jeton_ne_vaut_que_pour_ladministrateur_qui_la_demande(client, compte_ordinaire):
    """
    Nominatif : un jeton récupéré ailleurs ne doit pas servir à un autre
    appelant, fût-il administrateur.
    """
    jeton = auth.creer_token_consultation(compte_ordinaire["email"], administrateur_id=999999)
    refus = client.get("/moi", headers={ENTETE: jeton})
    assert refus.status_code == 403


def test_un_jeton_de_consultation_nouvre_pas_de_session(client, compte_ordinaire):
    """
    Il porte un « usage » : présenté comme jeton de session, il doit être refusé.
    Sans quoi la fonction deviendrait un moyen de se connecter sans mot de passe.
    """
    jeton = client.post(f"/admin/consultation/{compte_ordinaire['id']}").json()["jeton"]

    autre = TestClient(app)
    autre.headers["Authorization"] = f"Bearer {jeton}"
    assert autre.get("/moi").status_code == 401


def test_un_compte_ordinaire_ne_peut_pas_consulter(client, compte_ordinaire):
    ordinaire = TestClient(app)
    connexion = ordinaire.post("/auth/login", data={
        "username": compte_ordinaire["email"], "password": "MotDePasse!42"})
    assert connexion.status_code == 200, connexion.text
    ordinaire.headers["Authorization"] = f"Bearer {connexion.json()['access_token']}"

    assert ordinaire.post(f"/admin/consultation/{compte_ordinaire['id']}").status_code == 403

    # et il ne peut pas davantage se servir d'un jeton forgé pour quelqu'un d'autre
    jeton = auth.creer_token_consultation("admin@homeged.local", compte_ordinaire["id"])
    assert ordinaire.get("/moi", headers={ENTETE: jeton}).status_code == 403


def test_un_compte_desactive_ne_se_consulte_pas(client, compte_ordinaire):
    """Il ne verrait rien, et cela ne prouverait rien."""
    client.put(f"/admin/utilisateurs/{compte_ordinaire['id']}", json={
        "email": compte_ordinaire["email"], "nom": "Sans", "prenom": "Droits",
        "est_admin": False, "actif": False, "role_ids": [],
    })
    refus = client.post(f"/admin/consultation/{compte_ordinaire['id']}")
    assert refus.status_code == 400


def test_louverture_est_tracee_au_journal(client, compte_ordinaire):
    """Une fois, à l'ouverture : la tracer à chaque requête noierait l'information."""
    client.post(f"/admin/consultation/{compte_ordinaire['id']}")

    session = SessionLocal()
    try:
        entree = (session.query(JournalAudit)
                  .filter_by(action="consultation.ouverte")
                  .order_by(JournalAudit.id.desc()).first())
        assert entree is not None
        assert compte_ordinaire["email"] in (entree.details or "")
    finally:
        session.close()
