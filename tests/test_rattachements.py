"""
Rattacher deux documents à la main (§22.4).

Le rapprochement par valeur partagée (§19.19) réunit ce qui **désigne la même
chose** : deux papiers qui nomment le même véhicule se retrouvent sans qu'on ait
rien à faire. Reste ce qui ne partage rien et se répond quand même — un contrat
et son avenant. Seul quelqu'un qui les a lus le sait.

Ces tests portent sur ce qui doit rester vrai : le lien se lit des deux côtés, il
ne se pose pas deux fois, et l'administration peut le borner sans que le réglage
vide n'interdise quoi que ce soit.
"""
import pytest

from app.db import Categorie, Document, RattachementType, SessionLocal


@pytest.fixture
def deux_documents(base_de_test):
    """Un contrat et son avenant, dans deux types différents."""
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_rt%")).delete(
            synchronize_session=False)
        session.query(RattachementType).delete()
        for nom in ("_RtContrats", "_RtAvenants"):
            if not session.query(Categorie).filter_by(nom=nom).first():
                session.add(Categorie(nom=nom, nature="type", ordre=980))
        session.flush()
        types = {c.nom: c.id for c in session.query(Categorie)
                 .filter(Categorie.nom.in_(("_RtContrats", "_RtAvenants")))}
        identifiants = []
        for nom, categorie in (("_rt_contrat.pdf", "_RtContrats"),
                               ("_rt_avenant.pdf", "_RtAvenants")):
            document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                                hash_sha256=nom.ljust(64, "t"), texte_ocr="x",
                                statut="traite", categorie_id=types[categorie])
            session.add(document)
            session.flush()
            identifiants.append(document.id)
        session.commit()
        contexte = (identifiants[0], identifiants[1], types)
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_rt%")).delete(
            synchronize_session=False)
        session.query(RattachementType).delete()
        session.query(Categorie).filter(Categorie.nom.like("_Rt%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_le_lien_se_lit_des_deux_cotes(client, deux_documents):
    """Un avenant sans son contrat n'a pas plus de sens que l'inverse."""
    contrat, avenant, _ = deux_documents
    pose = client.post(f"/documents/{contrat}/rattachements",
                       json={"document_id": avenant, "libelle": "avenant"})
    assert pose.status_code == 200, pose.text

    vu_du_contrat = client.get(f"/documents/{contrat}/rattachements").json()["rattachements"]
    vu_de_lavenant = client.get(f"/documents/{avenant}/rattachements").json()["rattachements"]
    assert [r["document_id"] for r in vu_du_contrat] == [avenant]
    assert [r["document_id"] for r in vu_de_lavenant] == [contrat]
    assert vu_de_lavenant[0]["intitule"] == "avenant"


def test_poser_deux_fois_le_meme_lien_ne_le_double_pas(client, deux_documents):
    """Le geste est idempotent : on peut le refaire sans y penser."""
    contrat, avenant, _ = deux_documents
    client.post(f"/documents/{contrat}/rattachements", json={"document_id": avenant})
    # et dans l'autre sens, ce qui est le vrai piège d'un lien symétrique
    client.post(f"/documents/{avenant}/rattachements", json={"document_id": contrat})

    liens = client.get(f"/documents/{contrat}/rattachements").json()["rattachements"]
    assert len(liens) == 1


def test_un_document_ne_se_rattache_pas_a_lui_meme(client, deux_documents):
    contrat, _, _ = deux_documents
    refus = client.post(f"/documents/{contrat}/rattachements", json={"document_id": contrat})
    assert refus.status_code == 400
    assert "lui-même" in refus.json()["detail"]


def test_detacher_retire_le_lien_des_deux_cotes(client, deux_documents):
    contrat, avenant, _ = deux_documents
    client.post(f"/documents/{contrat}/rattachements", json={"document_id": avenant})

    # depuis l'autre côté : détacher engage les deux fiches, comme le poser
    retrait = client.delete(f"/documents/{avenant}/rattachements/{contrat}")
    assert retrait.status_code == 200, retrait.text
    assert client.get(f"/documents/{contrat}/rattachements").json()["rattachements"] == []

    encore = client.delete(f"/documents/{avenant}/rattachements/{contrat}")
    assert encore.status_code == 404, "détacher ce qui ne l'est pas doit le dire"


def test_sans_declaration_tout_est_permis(client, deux_documents):
    """
    Un réglage vide ne doit pas interdire une fonction : personne ne comprendrait
    pourquoi le bouton refuse.
    """
    contrat, avenant, _ = deux_documents
    assert client.get("/admin/rattachements-types").json()["libre"] is True
    assert client.post(f"/documents/{contrat}/rattachements",
                       json={"document_id": avenant}).status_code == 200


def test_une_paire_declaree_borne_le_reste(client, deux_documents):
    contrat, avenant, types = deux_documents
    # on déclare que ce foyer relie ses contrats à ses avenants…
    declaree = client.post("/admin/rattachements-types",
                           json={"categorie_a": types["_RtContrats"],
                                 "categorie_b": types["_RtAvenants"],
                                 "libelle": "avenant"})
    assert declaree.status_code == 200, declaree.text
    assert client.get("/admin/rattachements-types").json()["libre"] is False

    # …ce qui reste permis dans les deux sens : une déclaration est un fait sur
    # deux types, pas une direction
    assert client.post(f"/documents/{avenant}/rattachements",
                       json={"document_id": contrat}).status_code == 200

    # …et interdit le reste
    session = SessionLocal()
    try:
        autre_type = session.query(Categorie).filter(
            Categorie.nature == "type",
            ~Categorie.nom.in_(("_RtContrats", "_RtAvenants"))).first()
        etranger = Document(nom_fichier="_rt_etranger.pdf",
                            chemin_stockage="/tmp/_rt_etranger.pdf",
                            hash_sha256="_rtetr".ljust(64, "z"), texte_ocr="x",
                            statut="traite", categorie_id=autre_type.id)
        session.add(etranger)
        session.commit()
        identifiant = etranger.id
    finally:
        session.close()

    refus = client.post(f"/documents/{contrat}/rattachements",
                        json={"document_id": identifiant})
    assert refus.status_code == 400
    assert "n'autorise pas" in refus.json()["detail"]


def test_le_rattachement_se_lit_dans_lhistorique(client, deux_documents):
    """L'historique d'une fiche doit dire ce qui lui est arrivé, y compris quand
    c'est depuis l'autre qu'on a agi."""
    contrat, avenant, _ = deux_documents
    client.post(f"/documents/{contrat}/rattachements", json={"document_id": avenant})

    journal = client.get(f"/documents/{avenant}/journal").json()
    assert any(e["action"] == "document.rattachement" for e in journal["evenements"])
