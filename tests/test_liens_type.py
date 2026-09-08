"""
Le rapprochement déclaré sur le type de document (§22.8).

L'exemple vient de l'utilisateur : un dossier porte un numéro, et ce numéro est
repris sur le devis, le bon de commande, le bon de livraison. Ouvrir l'un doit
montrer les autres — non parce qu'une machine l'a deviné, mais parce que
quelqu'un a **déclaré** que ce champ-là relie ces types-là.

C'est toute la différence avec le rapprochement automatique retiré au §22.7 : ce
qui s'affiche a été paramétré, et l'on sait donc pourquoi deux documents se
retrouvent côte à côte.
"""
import pytest

from app.db import Categorie, Document, LienType, Metadonnee, SessionLocal

NUMERO = "D-2026-1234"


@pytest.fixture
def dossier_et_pieces(client, base_de_test):
    """Un dossier technique et deux pièces qui portent son numéro."""
    session = SessionLocal()
    try:
        session.query(LienType).delete()
        session.query(Document).filter(Document.nom_fichier.like("_lt%")).delete(
            synchronize_session=False)
        types = {}
        for nom in ("_LtDossiers", "_LtDevis"):
            categorie = session.query(Categorie).filter_by(nom=nom).one_or_none()
            if not categorie:
                categorie = Categorie(nom=nom, nature="type", ordre=985)
                session.add(categorie)
                session.flush()
            types[nom] = categorie.id

        identifiants = {}
        for nom, type_nom, numero in (("_lt_dossier.pdf", "_LtDossiers", NUMERO),
                                      ("_lt_devis.pdf", "_LtDevis", NUMERO),
                                      ("_lt_autre.pdf", "_LtDevis", "D-2026-9999")):
            document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                                hash_sha256=nom.ljust(64, "l"), texte_ocr="x",
                                statut="traite", categorie_id=types[type_nom])
            session.add(document)
            session.flush()
            session.add(Metadonnee(document_id=document.id, cle="numero_dossier",
                                   valeur=numero))
            identifiants[nom] = document.id
        session.commit()
        contexte = (identifiants, types)
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(LienType).delete()
        session.query(Document).filter(Document.nom_fichier.like("_lt%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Lt%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _declarer(client, types, **extra):
    return client.post("/admin/liens-types", json={
        "categorie_id": types["_LtDossiers"],
        "champ_source": "meta:numero_dossier",
        "champ_cible": "meta:numero_dossier",
        "libelle": "Pièces du dossier",
        **extra,
    })


def test_sans_declaration_rien_ne_se_rapproche(client, dossier_et_pieces):
    """
    C'est le point de départ : deux documents qui portent le même numéro ne se
    voient pas tant que personne n'a dit que ce numéro les relie.
    """
    identifiants, _ = dossier_et_pieces
    reponse = client.get(f"/documents/{identifiants['_lt_dossier.pdf']}/rapprochements")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["rapprochements"] == []


def test_le_numero_de_dossier_rassemble_les_pieces(client, dossier_et_pieces):
    identifiants, types = dossier_et_pieces
    assert _declarer(client, types).status_code == 200

    groupes = client.get(
        f"/documents/{identifiants['_lt_dossier.pdf']}/rapprochements").json()["rapprochements"]
    assert len(groupes) == 1
    assert groupes[0]["libelle"] == "Pièces du dossier"
    assert groupes[0]["valeur"] == NUMERO
    rejoints = [d["id"] for d in groupes[0]["documents"]]
    assert identifiants["_lt_devis.pdf"] in rejoints
    assert identifiants["_lt_autre.pdf"] not in rejoints, \
        "un autre numéro n'est pas le même dossier"
    assert identifiants["_lt_dossier.pdf"] not in rejoints, \
        "un document ne se rapproche pas de lui-même"


def test_la_declaration_vaut_dans_les_deux_sens(client, dossier_et_pieces):
    """
    Déclarer une fois suffit : ouvrir le devis montre son dossier. Sans cela il
    faudrait six déclarations pour trois types, et l'on en oublierait toujours une.
    """
    identifiants, types = dossier_et_pieces
    _declarer(client, types, categorie_cible_id=types["_LtDevis"])

    groupes = client.get(
        f"/documents/{identifiants['_lt_devis.pdf']}/rapprochements").json()["rapprochements"]
    assert [d["id"] for d in groupes[0]["documents"]] == [identifiants["_lt_dossier.pdf"]]


def test_un_type_cible_borne_le_rapprochement(client, dossier_et_pieces):
    """« Tous les types » convient au numéro de dossier ; on peut vouloir plus étroit."""
    identifiants, types = dossier_et_pieces
    _declarer(client, types, categorie_cible_id=types["_LtDossiers"])

    groupes = client.get(
        f"/documents/{identifiants['_lt_dossier.pdf']}/rapprochements").json()["rapprochements"]
    assert groupes == [], "aucun autre dossier ne porte ce numéro"


def test_un_document_sans_la_valeur_ne_rapproche_rien(client, dossier_et_pieces):
    identifiants, types = dossier_et_pieces
    _declarer(client, types)

    session = SessionLocal()
    try:
        session.query(Metadonnee).filter_by(
            document_id=identifiants["_lt_dossier.pdf"]).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()

    groupes = client.get(
        f"/documents/{identifiants['_lt_dossier.pdf']}/rapprochements").json()["rapprochements"]
    assert groupes == []


def test_un_champ_qui_nexiste_pas_est_refuse_a_la_declaration(client, dossier_et_pieces):
    """
    Un champ mal écrit ne se manifesterait jamais : le rapprochement ne
    ramènerait rien, et l'on chercherait longtemps pourquoi deux documents qui
    portent le même numéro ne se voient pas.
    """
    _, types = dossier_et_pieces
    refus = _declarer(client, types, champ_cible="couleur")
    assert refus.status_code == 422


def test_la_declaration_se_relit_et_se_retire(client, dossier_et_pieces):
    identifiants, types = dossier_et_pieces
    cree = _declarer(client, types)
    liste = client.get("/admin/liens-types").json()
    assert [l["id"] for l in liste] == [cree.json()["id"]]
    assert liste[0]["categorie"] == "_LtDossiers"

    assert client.delete(f"/admin/liens-types/{cree.json()['id']}").status_code == 200
    assert client.get(
        f"/documents/{identifiants['_lt_dossier.pdf']}/rapprochements"
    ).json()["rapprochements"] == []
