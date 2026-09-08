"""
Session par cookie et protection CSRF.

Le jeton n'est plus stocké dans la page : il vit dans un cookie `httpOnly`,
qu'un script injecté ne peut pas lire. En contrepartie le navigateur l'envoie
de lui-même, y compris sur une requête déclenchée par un autre site — d'où le
jeton anti-CSRF exigé sur toute écriture.
"""
import pytest

from app import auth, config
from app.db import Document, SessionLocal


@pytest.fixture
def document(base_de_test):
    """Un document à modifier, créé ici pour que le fichier soit autonome."""
    session = SessionLocal()
    existant = session.query(Document).filter_by(nom_fichier="session.pdf").first()
    if not existant:
        existant = Document(nom_fichier="session.pdf", chemin_stockage="/tmp/session.pdf",
                            hash_sha256="session".ljust(64, "7"), texte_ocr="x", statut="traite")
        session.add(existant)
        session.commit()
    identifiant, categorie = existant.id, existant.categorie_id
    session.close()
    return {"id": identifiant, "categorie_id": categorie}


def _connexion(sans_jeton):
    return sans_jeton.post("/auth/login", data={
        "username": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD})


def test_la_connexion_pose_un_cookie_de_session_httponly(client):
    reponse = _connexion(client)
    assert reponse.status_code == 200
    entetes = reponse.headers.get_list("set-cookie")
    session = next(c for c in entetes if c.startswith(auth.NOM_COOKIE_SESSION))
    assert "HttpOnly" in session, "le jeton de session doit être illisible par un script"
    assert "SameSite=strict" in session.replace("samesite", "SameSite")
    csrf = next(c for c in entetes if c.startswith(auth.NOM_COOKIE_CSRF))
    assert "HttpOnly" not in csrf, "le jeton anti-CSRF doit rester lisible par la page"


def test_le_jeton_reste_renvoye_pour_scripter_l_api(client):
    """Un script n'a pas de cookie : il continue d'utiliser l'en-tête Authorization."""
    assert _connexion(client).json().get("access_token")


def test_lecture_authentifiee_par_le_seul_cookie(client, jeton_de):
    from fastapi.testclient import TestClient
    from app.api import app

    navigateur = TestClient(app)
    _connexion(navigateur)
    assert navigateur.get("/documents").status_code == 200


def test_une_ecriture_sans_jeton_anti_csrf_est_refusee(client, document):
    from fastapi.testclient import TestClient
    from app.api import app

    navigateur = TestClient(app)
    _connexion(navigateur)
    refus = navigateur.patch(f"/documents/{document['id']}", json={"categorie_id": None})
    assert refus.status_code == 403
    assert "CSRF" in refus.json()["detail"]


def test_une_ecriture_avec_le_bon_jeton_est_acceptee(client, document):
    from fastapi.testclient import TestClient
    from app.api import app

    navigateur = TestClient(app)
    _connexion(navigateur)
    csrf = navigateur.cookies.get(auth.NOM_COOKIE_CSRF)
    reponse = navigateur.patch(f"/documents/{document['id']}",
                               json={"categorie_id": document["categorie_id"]},
                               headers={auth.ENTETE_CSRF: csrf})
    assert reponse.status_code == 200


def test_un_jeton_anti_csrf_falsifie_est_refuse(client, document):
    from fastapi.testclient import TestClient
    from app.api import app

    navigateur = TestClient(app)
    _connexion(navigateur)
    assert navigateur.patch(f"/documents/{document['id']}", json={"categorie_id": None},
                            headers={auth.ENTETE_CSRF: "faux"}).status_code == 403


def test_l_en_tete_authorization_n_exige_pas_de_jeton_anti_csrf(client, document):
    """
    Un en-tête `Authorization` n'est jamais joint automatiquement par un
    navigateur : il n'expose donc pas au CSRF, et n'a pas à porter ce garde-fou.
    """
    reponse = client.patch(f"/documents/{document['id']}",
                           json={"categorie_id": document["categorie_id"]})
    assert reponse.status_code == 200


def test_la_deconnexion_retire_les_cookies(client):
    from fastapi.testclient import TestClient
    from app.api import app

    navigateur = TestClient(app)
    _connexion(navigateur)
    csrf = navigateur.cookies.get(auth.NOM_COOKIE_CSRF)
    assert navigateur.post("/auth/logout", headers={auth.ENTETE_CSRF: csrf}).status_code == 200
    navigateur.cookies.clear()
    assert navigateur.get("/documents").status_code == 401


def test_un_cookie_de_session_invalide_est_rejete(client):
    from fastapi.testclient import TestClient
    from app.api import app

    navigateur = TestClient(app)
    navigateur.cookies.set(auth.NOM_COOKIE_SESSION, "jeton.forge.par.un.tiers")
    assert navigateur.get("/documents").status_code == 401
