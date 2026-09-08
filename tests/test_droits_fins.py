"""
Droits fins : par action, par emplacement, avec héritage (§19.12).

C'est le point le plus sensible du projet : une régression ici expose des
documents à des comptes qui ne doivent pas les voir, ou retire à quelqu'un un
accès dont personne ne se souvient l'avoir donné.

Ces tests portent sur les trois axes — l'action, l'emplacement, le reste — et
surtout sur ce qui les relie : l'héritage d'un dossier vers ses types, et le fait
qu'un contrôle oublié se remarque.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app import categories as natures, droits
from app.api import app
from app.db import Categorie, Document, Role, SessionLocal, Utilisateur

MDP = "MotDePasse!42"


@pytest.fixture
def foyer(client):
    """Un dossier, deux types dedans, un document dans chacun, et un rôle vierge."""
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_df%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Df%")).delete(
            synchronize_session=False)
        dossier = Categorie(nom="_DfMaison", nature=natures.DOSSIER, ordre=970)
        session.add(dossier)
        session.flush()
        factures = Categorie(nom="_DfFactures", nature=natures.TYPE,
                             parent_id=dossier.id, ordre=971)
        sante = Categorie(nom="_DfSante", nature=natures.TYPE,
                          parent_id=dossier.id, ordre=972)
        session.add_all([factures, sante])
        session.flush()
        for nom, categorie in (("_df_facture.pdf", factures), ("_df_sante.pdf", sante)):
            session.add(Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                                 hash_sha256=nom.ljust(64, "d"), texte_ocr="x",
                                 statut="traite", categorie_id=categorie.id))
        session.commit()
        contexte = {"dossier": dossier.id, "factures": factures.id, "sante": sante.id}
    finally:
        session.close()

    for existant in client.get("/admin/roles").json():
        if existant["nom"] == "_DfRole":
            client.delete(f"/admin/roles/{existant['id']}")
    role = client.post("/admin/roles", json={"nom": "_DfRole", "description": None})
    contexte["role"] = role.json()["id"]

    for u in client.get("/admin/utilisateurs").json():
        if u["email"] == "_df@homeged.local":
            client.delete(f"/admin/utilisateurs/{u['id']}")
    cree = client.post("/admin/utilisateurs", json={
        "email": "_df@homeged.local", "nom": "Fine", "prenom": "Droit",
        "mot_de_passe": MDP, "est_admin": False, "actif": True,
        "role_ids": [contexte["role"]]})
    assert cree.status_code == 200, cree.text
    contexte["utilisateur"] = cree.json()["id"]

    yield contexte

    client.delete(f"/admin/utilisateurs/{contexte['utilisateur']}")
    client.delete(f"/admin/roles/{contexte['role']}")
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_df%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Df%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _donner(client, foyer, **payload):
    reponse = client.put(f"/admin/roles/{foyer['role']}/droits", json=payload)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def _connecte():
    membre = TestClient(app)
    jeton = membre.post("/auth/login", data={"username": "_df@homeged.local", "password": MDP})
    assert jeton.status_code == 200, jeton.text
    membre.headers["Authorization"] = f"Bearer {jeton.json()['access_token']}"
    return membre


def _document(client, nom):
    return next(d for d in client.get("/documents").json() if d["nom_fichier"] == nom)


# ------------------------------------------------------------------
# L'emplacement, et son héritage
# ------------------------------------------------------------------

def test_un_droit_sur_le_dossier_vaut_pour_ses_types(client, foyer):
    """
    Sans cet héritage, ouvrir un dossier demanderait de cocher chacun de ses
    types, et d'y repenser à chaque type ajouté : le genre d'oubli qui donne un
    accès qu'on croyait fermé.
    """
    _donner(client, foyer, categories=[
        {"categorie_id": foyer["dossier"], "peut_voir": True}])

    membre = _connecte()
    noms = {d["nom_fichier"] for d in membre.get("/documents").json()}
    assert {"_df_facture.pdf", "_df_sante.pdf"} <= noms


def test_un_droit_sur_un_type_lemporte_sur_son_dossier(client, foyer):
    """
    C'est le sens même d'une exception : sans cela, ouvrir un dossier rouvrirait
    ce qu'on avait fermé en dessous.
    """
    _donner(client, foyer, categories=[
        {"categorie_id": foyer["dossier"], "peut_voir": True},
        {"categorie_id": foyer["sante"], "peut_voir": False},
    ])

    membre = _connecte()
    noms = {d["nom_fichier"] for d in membre.get("/documents").json()}
    assert "_df_facture.pdf" in noms
    assert "_df_sante.pdf" not in noms, "l'exception posée sur le type doit primer"


# ------------------------------------------------------------------
# L'action
# ------------------------------------------------------------------

def test_voir_nemporte_pas_telecharger(client, foyer):
    """
    Laisser quelqu'un lire une fiche n'oblige pas à lui donner le PDF : c'est
    précisément ce que deux droits séparés permettent de dire.
    """
    _donner(client, foyer, categories=[
        {"categorie_id": foyer["factures"], "peut_voir": True, "peut_telecharger": False}])

    membre = _connecte()
    document = _document(client, "_df_facture.pdf")
    assert membre.get(f"/documents/{document['id']}").status_code == 200
    refus = membre.get(f"/documents/{document['id']}/fichier")
    assert refus.status_code == 403
    assert "télécharger" in refus.json()["detail"].lower()


def test_modifier_nemporte_pas_supprimer(client, foyer):
    """Corriger un champ se défait ; mettre une pièce à la corbeille se rattrape mal."""
    _donner(client, foyer, categories=[
        {"categorie_id": foyer["factures"], "peut_voir": True, "peut_modifier": True,
         "peut_supprimer": False}])

    membre = _connecte()
    document = _document(client, "_df_facture.pdf")
    assert membre.patch(f"/documents/{document['id']}",
                        json={"metadonnees": {"essai": "oui"}}).status_code == 200
    assert membre.delete(f"/documents/{document['id']}").status_code == 403


def test_un_refus_dit_ce_qui_manque(client, foyer):
    """Un refus qu'on ne comprend pas se contourne mal, et se corrige plus mal encore."""
    _donner(client, foyer, categories=[
        {"categorie_id": foyer["factures"], "peut_voir": True}])

    membre = _connecte()
    document = _document(client, "_df_facture.pdf")
    refus = membre.delete(f"/documents/{document['id']}")
    assert refus.status_code == 403
    assert "corbeille" in refus.json()["detail"].lower()
    assert "_DfFactures" in refus.json()["detail"], "le refus doit dire où"


# ------------------------------------------------------------------
# Les droits généraux
# ------------------------------------------------------------------

def test_sans_aucun_droit_general_ladministration_reste_fermee(client, foyer):
    membre = _connecte()
    assert membre.get("/admin/jobs").status_code == 403


def test_un_droit_general_ouvre_son_ecran_et_lui_seul(client, foyer):
    """
    C'est tout l'intérêt : donner le suivi des travaux à quelqu'un ne lui donne
    pas l'export de l'archive du foyer.
    """
    _donner(client, foyer, generaux=["travaux"])

    membre = _connecte()
    assert membre.get("/admin/jobs").status_code == 200
    assert membre.get("/admin/utilisateurs").status_code == 403
    refus = membre.post("/admin/export", json={"mot_de_passe": MDP})
    assert refus.status_code == 403


def test_un_droit_general_inconnu_est_refuse(client, foyer):
    """Il ne serait jamais vérifié : l'accepter donnerait l'illusion d'un réglage."""
    refus = client.put(f"/admin/roles/{foyer['role']}/droits",
                       json={"generaux": ["tout_pouvoir"]})
    assert refus.status_code == 422


def test_le_catalogue_des_droits_vient_du_code(client):
    """
    Une liste tenue à l'écran finirait par proposer un droit que rien ne vérifie,
    ou par en oublier un que le code exige.
    """
    catalogue = client.get("/admin/droits/catalogue").json()
    assert {a["cle"] for a in catalogue["actions"]} == set(droits.ACTIONS)
    assert {g["cle"] for g in catalogue["generaux"]} == set(droits.GENERAUX)


# ------------------------------------------------------------------
# Les vues préfiltrées
# ------------------------------------------------------------------

def test_une_vue_peut_etre_reservee_a_certains_roles(client, foyer):
    """
    Une vue est une lecture préfiltrée du registre : « Documents médicaux » ne
    regarde pas forcément tout le monde. `partagee` ne disait que « privée » ou
    « visible de tous ».
    """
    _donner(client, foyer, categories=[
        {"categorie_id": foyer["dossier"], "peut_voir": True}])
    vue = client.post("/vues", json={
        "nom": "_DfVueReservee", "categorie_id": None, "criteres": [],
        "partagee": True, "ordre": 990})
    assert vue.status_code == 200, vue.text
    identifiant = vue.json()["id"]

    try:
        membre = _connecte()
        assert any(v["id"] == identifiant for v in membre.get("/vues").json()), \
            "partagée sans restriction, elle doit être visible"

        # réservée à un autre rôle : elle disparaît pour celui-ci
        autre = client.post("/admin/roles", json={"nom": "_DfAutre", "description": None})
        client.put(f"/admin/roles/{autre.json()['id']}/droits", json={"vues": [identifiant]})
        try:
            membre = _connecte()
            assert not any(v["id"] == identifiant for v in membre.get("/vues").json())

            # ... et réapparaît dès que son propre rôle y a droit
            _donner(client, foyer, categories=[
                {"categorie_id": foyer["dossier"], "peut_voir": True}],
                vues=[identifiant])
            membre = _connecte()
            assert any(v["id"] == identifiant for v in membre.get("/vues").json())
        finally:
            client.delete(f"/admin/roles/{autre.json()['id']}")
    finally:
        client.delete(f"/vues/{identifiant}")


# ------------------------------------------------------------------
# Aucun point d'entrée sans garde
# ------------------------------------------------------------------

def test_aucune_route_dadministration_nest_sans_droit_declare():
    """
    Un contrôle oublié n'est pas une gêne, c'est un trou. Ce test parcourt le
    code plutôt que les réponses : il attrape la route ajoutée demain, que
    personne n'aura pensé à tester.
    """
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "app" / "admin.py"
    routes = re.findall(r'@router\.(get|post|put|patch|delete)\("([^"]+)"([^)]*)\)',
                        source.read_text(encoding="utf-8"))
    sans_garde = [f"{m.upper()} {c}" for m, c, reste in routes
                  if "dependencies=" not in reste]
    assert sans_garde == [], f"routes sans droit déclaré : {sans_garde}"


def test_le_resume_dit_a_linterface_ce_quelle_peut_proposer(client, foyer):
    """
    Un écran qui propose une action refusée ensuite fait perdre deux fois : au
    clic, et à la lecture du message.
    """
    _donner(client, foyer, categories=[
        {"categorie_id": foyer["factures"], "peut_voir": True, "peut_modifier": True}],
        generaux=["analyser"])

    session = SessionLocal()
    try:
        membre = session.get(Utilisateur, foyer["utilisateur"])
        resume = droits.resume(session, membre)
        assert resume["generaux"] == ["analyser"]
        assert foyer["factures"] in resume["categories"]["modifier"]
        assert foyer["sante"] not in resume["categories"]["voir"]
    finally:
        session.close()
