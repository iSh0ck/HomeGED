"""
Verrou d'édition et historique d'un document (§17.21).

Deux personnes du foyer peuvent ouvrir la même facture au même moment. Sans
verrou, la dernière à enregistrer écrase l'autre sans que personne ne le sache —
et l'on ne s'en aperçoit que plus tard, en constatant qu'une correction a
disparu.

Ces tests vérifient les trois propriétés qui rendent le verrou utile : il
empêche l'écrasement, il n'immobilise pas le document indéfiniment, et il se
rend.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.db import Document, SessionLocal, VerrouDocument

MDP = "MotDePasse!42"


@pytest.fixture
def document(base_de_test):
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier == "_verrou.pdf").delete()
        doc = Document(nom_fichier="_verrou.pdf", chemin_stockage="/tmp/_verrou.pdf",
                       hash_sha256="verrou".ljust(64, "v"), texte_ocr="x", statut="traite")
        session.add(doc)
        session.commit()
        identifiant = doc.id
    finally:
        session.close()
    yield identifiant
    session = SessionLocal()
    try:
        session.query(VerrouDocument).filter_by(document_id=identifiant).delete()
        session.query(Document).filter_by(id=identifiant).delete()
        session.commit()
    finally:
        session.close()


@pytest.fixture
def autre_compte(client):
    email = "_t_verrou@homeged.local"
    for u in client.get("/admin/utilisateurs").json():
        if u["email"] == email:
            client.delete(f"/admin/utilisateurs/{u['id']}")
    cree = client.post("/admin/utilisateurs", json={
        "email": email, "nom": "Second", "prenom": "Compte", "mot_de_passe": MDP,
        "est_admin": True, "actif": True, "role_ids": [],
    })
    assert cree.status_code == 200, cree.text

    sous_client = TestClient(app)
    jeton = sous_client.post("/auth/login", data={"username": email, "password": MDP})
    sous_client.headers["Authorization"] = f"Bearer {jeton.json()['access_token']}"
    yield sous_client
    client.delete(f"/admin/utilisateurs/{cree.json()['id']}")


def test_le_verrou_empeche_lecrasement_par_un_autre(client, autre_compte, document):
    assert client.post(f"/documents/{document}/verrou").status_code == 200

    refus = autre_compte.post(f"/documents/{document}/verrou")
    assert refus.status_code == 409
    assert "modification" in refus.json()["detail"].lower()

    # et l'enregistrement lui-même est refusé, pas seulement la prise du verrou :
    # sans cela, il suffirait de ne pas demander le verrou pour l'ignorer
    ecriture = autre_compte.patch(f"/documents/{document}", json={"date_document": "2026-01-01"})
    assert ecriture.status_code == 409

    assert client.patch(f"/documents/{document}",
                        json={"date_document": "2026-02-02"}).status_code == 200


def test_le_verrou_se_rend(client, autre_compte, document):
    client.post(f"/documents/{document}/verrou")
    assert client.delete(f"/documents/{document}/verrou").status_code == 200
    assert autre_compte.post(f"/documents/{document}/verrou").status_code == 200


def test_un_verrou_perime_ne_bloque_plus_rien(client, autre_compte, document):
    """
    Un onglet fermé sans un mot ne doit pas immobiliser un document pour le
    foyer entier : c'est toute la raison de la date d'expiration.
    """
    client.post(f"/documents/{document}/verrou")

    session = SessionLocal()
    try:
        verrou = session.query(VerrouDocument).filter_by(document_id=document).one()
        verrou.date_expiration = datetime.now() - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    assert autre_compte.post(f"/documents/{document}/verrou").status_code == 200
    assert autre_compte.patch(f"/documents/{document}",
                              json={"date_document": "2026-03-03"}).status_code == 200


def test_reprendre_son_propre_verrou_le_prolonge(client, document):
    premier = client.post(f"/documents/{document}/verrou").json()
    second = client.post(f"/documents/{document}/verrou").json()
    assert second["detenu"] is True
    assert second["expire_le"] >= premier["expire_le"], "la fenêtre ouverte prolonge le verrou"


def test_letat_du_verrou_dit_qui_le_detient(client, autre_compte, document):
    client.post(f"/documents/{document}/verrou")
    etat = autre_compte.get(f"/documents/{document}/verrou").json()
    assert etat["detenu"] is False
    assert etat["par"], "l'autre doit savoir à qui s'adresser"


def test_lhistorique_dit_ce_qui_a_change_et_en_clair(client, document):
    """
    « Catégorie modifiée » n'apprend rien. La trace doit porter l'ancienne et la
    nouvelle valeur, et les écrire comme on les lit — « Factures », pas « 2 » :
    un journal se relit des mois plus tard, parfois après qu'une catégorie a été
    renommée, et l'identifiant ne désignerait alors plus rien.
    """
    client.post(f"/documents/{document}/verrou")
    client.patch(f"/documents/{document}", json={"date_document": "2026-04-04"})

    journal = client.get(f"/documents/{document}/journal").json()["evenements"]
    assert journal, "la modification doit laisser une trace lisible depuis la fiche"
    assert journal[0]["action"] == "document.modification"
    assert journal[0]["auteur"], "on doit savoir qui a modifié"

    details = journal[0]["details"]
    assert details["avant"]["date_document"] is None
    assert details["apres"]["date_document"] == "2026-04-04"

    categorie = client.get("/categories").json()[0]
    client.patch(f"/documents/{document}", json={"categorie_id": categorie["id"]})
    dernier = client.get(f"/documents/{document}/journal").json()["evenements"][0]
    assert dernier["details"]["apres"]["categorie"] == categorie["nom"], \
        "la catégorie doit être écrite en toutes lettres, pas en numéro"


def test_une_modification_qui_ne_change_rien_ne_laisse_pas_de_trace(client, document):
    """L'histoire d'un document doit se lire sans avoir à écarter le bruit."""
    client.post(f"/documents/{document}/verrou")
    client.patch(f"/documents/{document}", json={"date_document": "2026-05-05"})
    avant = client.get(f"/documents/{document}/journal").json()["total"]

    client.patch(f"/documents/{document}", json={"date_document": "2026-05-05"})
    assert client.get(f"/documents/{document}/journal").json()["total"] == avant


def test_une_metadonnee_homonyme_dun_champ_ne_masque_pas_le_changement(client, document):
    """
    Les règles d'extraction écrivent volontiers une métadonnée `date_document`.
    Si elle écrasait le champ du document dans le relevé, un changement de date
    passerait pour inchangé et ne serait pas journalisé — c'est le défaut trouvé
    à l'essai de §17.22.
    """
    from app.db import Metadonnee, SessionLocal
    session = SessionLocal()
    try:
        session.add(Metadonnee(document_id=document, cle="date_document", valeur="1999-01-01"))
        session.commit()
    finally:
        session.close()

    client.post(f"/documents/{document}/verrou")
    client.patch(f"/documents/{document}", json={"date_document": "2026-08-08"})
    dernier = client.get(f"/documents/{document}/journal").json()["evenements"][0]
    assert dernier["details"]["apres"]["date_document"] == "2026-08-08"


def test_les_champs_attendus_accompagnent_la_fiche(client, document):
    """
    La fenêtre de modification a besoin de **tout** ce que la catégorie attend,
    pas seulement de ce qui manque : sinon elle ne saurait pas quoi proposer.
    """
    fiche = client.get(f"/documents/{document}").json()
    assert "champs_attendus" in fiche


def test_lhistorique_remonte_jusquau_depot(client, document):
    """
    Un document sans modification a quand même une histoire : son arrivée.
    Elle est restituée depuis la date d'import plutôt que dupliquée en base —
    ce qui vaut aussi pour les documents archivés avant que ce journal n'existe.
    """
    journal = client.get(f"/documents/{document}/journal").json()["evenements"]
    assert journal[-1]["action"] == "document.depot"
    assert journal[-1]["date_evenement"], "l'arrivée est datée"

    client.post(f"/documents/{document}/verrou")
    client.patch(f"/documents/{document}", json={"date_document": "2026-09-09"})
    apres = client.get(f"/documents/{document}/journal").json()["evenements"]
    assert apres[0]["action"] == "document.modification", "le plus récent d'abord"
    assert apres[-1]["action"] == "document.depot", "le dépôt reste au commencement"


def test_la_fiche_annonce_la_derniere_modification(client, document):
    assert client.get(f"/documents/{document}").json()["derniere_modification"] is None

    client.post(f"/documents/{document}/verrou")
    client.patch(f"/documents/{document}", json={"date_document": "2026-10-10"})

    derniere = client.get(f"/documents/{document}").json()["derniere_modification"]
    assert derniere["date"], "on doit savoir quand"
    assert derniere["auteur"], "et par qui"


def test_la_purge_du_journal_epargne_lhistoire_des_documents(client, document):
    """
    La purge existe pour empêcher le journal d'enfler, pas pour amputer les
    documents de leur passé : celui-ci se lit depuis la fiche et répond des
    années plus tard à « d'où sort cette valeur ? ».
    """
    from datetime import datetime, timedelta
    from app.db import JournalAudit, SessionLocal

    client.post(f"/documents/{document}/verrou")
    client.patch(f"/documents/{document}", json={"date_document": "2026-11-11"})

    # on vieillit artificiellement la trace pour qu'elle tombe dans la purge
    session = SessionLocal()
    try:
        trace = (session.query(JournalAudit)
                 .filter_by(objet_type="document", objet_id=document)
                 .order_by(JournalAudit.id.desc()).first())
        trace.date_evenement = datetime.now() - timedelta(days=30)
        session.commit()
    finally:
        session.close()

    coupure = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert client.request("DELETE", f"/admin/audit?avant={coupure}").status_code == 200

    restant = client.get(f"/documents/{document}/journal").json()["evenements"]
    assert any(e["action"] == "document.modification" for e in restant), \
        "l'histoire du document doit survivre à la purge du journal"


def test_lhistorique_se_pagine_sans_perdre_le_depot(client, document):
    """
    Un document qui a beaucoup vécu ne doit pas produire une réponse sans fin.
    Le dépôt, qui n'est pas une ligne du journal mais une propriété du document,
    doit compter dans le total et fermer la **dernière** page — sans quoi il
    réapparaîtrait sur chacune, ou disparaîtrait de toutes.
    """
    client.post(f"/documents/{document}/verrou")
    for jour in range(1, 6):
        client.patch(f"/documents/{document}", json={"date_document": f"2026-01-0{jour}"})

    premiere = client.get(f"/documents/{document}/journal", params={"limite": 2}).json()
    assert premiere["total"] == 6, "cinq modifications, plus le dépôt"
    assert len(premiere["evenements"]) == 2
    assert all(e["action"] != "document.depot" for e in premiere["evenements"])

    derniere = client.get(f"/documents/{document}/journal",
                          params={"limite": 2, "decalage": 4}).json()
    assert derniere["evenements"][-1]["action"] == "document.depot"
