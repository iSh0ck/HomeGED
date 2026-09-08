"""
Le lien déclaré sur la vue (§22.5).

La « correspondance de champs » d'EzGED : depuis une vue, ouvrir **une autre vue
filtrée sur la ligne qu'on regarde**. « Depuis les membres du foyer, voir ses
factures. »

Ce n'est ni un rapprochement par valeur partagée (§19.19) — celui-là se voit
sans qu'on le déclare — ni un rattachement à la main (§22.4) — celui-là vise
deux documents précis. C'est un **chemin de navigation**, déclaré une fois et
valable pour toutes les lignes.
"""
import pytest

from app import liens_vue
from app.db import SessionLocal, VueEnregistree


@pytest.fixture
def deux_vues(client, base_de_test):
    """Une vue « membres » et une vue « factures », à relier."""
    session = SessionLocal()
    try:
        session.query(VueEnregistree).filter(VueEnregistree.nom.like("_lv%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()

    depart = client.post("/vues", json={"nom": "_lvDepart", "criteres": [], "ordre": 900})
    arrivee = client.post("/vues", json={"nom": "_lvArrivee", "criteres": [], "ordre": 901})
    assert depart.status_code == 200 and arrivee.status_code == 200
    identifiants = (depart.json()["id"], arrivee.json()["id"])

    yield identifiants

    session = SessionLocal()
    try:
        session.query(VueEnregistree).filter(VueEnregistree.nom.like("_lv%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_une_vue_declare_par_ou_lon_continue(client, deux_vues):
    depart, arrivee = deux_vues
    enregistree = client.put(f"/vues/{depart}", json={
        "nom": "_lvDepart", "criteres": [], "ordre": 900,
        "liens": [{"vue_id": arrivee, "champ_source": "meta:titulaire",
                   "champ_cible": "meta:titulaire", "libelle": "Ses factures"}],
    })
    assert enregistree.status_code == 200, enregistree.text
    liens = enregistree.json()["liens"]
    assert len(liens) == 1
    assert liens[0]["vue_id"] == arrivee
    assert liens[0]["libelle"] == "Ses factures"

    # et la déclaration se relit telle quelle
    relue = [v for v in client.get("/vues").json() if v["id"] == depart][0]
    assert relue["liens"] == liens


def test_un_champ_inconnu_est_refuse_a_la_declaration(client, deux_vues):
    """
    Une correspondance fausse ne produit aucune erreur à l'usage : elle ouvre une
    liste vide, et l'on cherche pendant une heure d'où vient le vide.
    """
    depart, arrivee = deux_vues
    refus = client.put(f"/vues/{depart}", json={
        "nom": "_lvDepart", "criteres": [], "ordre": 900,
        "liens": [{"vue_id": arrivee, "champ_source": "couleur",
                   "champ_cible": "meta:titulaire"}],
    })
    assert refus.status_code == 422


def test_une_vue_ne_se_lie_pas_a_elle_meme(client, deux_vues):
    depart, _ = deux_vues
    refus = client.put(f"/vues/{depart}", json={
        "nom": "_lvDepart", "criteres": [], "ordre": 900,
        "liens": [{"vue_id": depart, "champ_source": "meta:titulaire",
                   "champ_cible": "meta:titulaire"}],
    })
    assert refus.status_code == 422
    assert "elle-même" in refus.json()["detail"]


def test_une_vue_disparue_est_refusee(client, deux_vues):
    depart, _ = deux_vues
    refus = client.put(f"/vues/{depart}", json={
        "nom": "_lvDepart", "criteres": [], "ordre": 900,
        "liens": [{"vue_id": 999999, "champ_source": "meta:titulaire",
                   "champ_cible": "meta:titulaire"}],
    })
    assert refus.status_code == 422


def test_le_lien_ne_produit_quun_filtre_ordinaire():
    """
    C'est tout ce qu'il fait, et c'est pourquoi il tient en si peu de lignes :
    rien ne change côté droits, pagination ou recherche.
    """
    critere = liens_vue.critere(
        {"champ_cible": "meta:titulaire", "champ_source": "meta:titulaire"},
        "usr_membres:4")
    assert critere == {"champ": "meta:titulaire", "operateur": "egal",
                       "valeur": "usr_membres:4"}
