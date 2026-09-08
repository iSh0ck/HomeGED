"""
La recherche globale (§21.2).

Chercher supposait de savoir **où** : choisir un type, puis filtrer colonne par
colonne. Celui qui cherche n'a qu'un mot et ne sait pas dans quel classement il
tombe.
"""
import pytest
from sqlalchemy import text as sql

from app.db import Categorie, Document, Metadonnee, SessionLocal


def _nettoyer():
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_rc%")).delete(
            synchronize_session=False)
        session.execute(sql("DELETE FROM usr_membres WHERE nom = '_RcClio'"))
        session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_RcEmetteur'"))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def documents_cherchables(base_de_test):
    """Quatre documents, chacun ne portant le mot que d'une seule façon."""
    _nettoyer()
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        # L'émetteur est une chose désignée (§21.12) : la recherche le trouve par
        # la source « chose », comme un véhicule ou un membre.
        session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_RcEmetteur'"))
        session.execute(sql("INSERT INTO usr_emetteurs (nom) VALUES ('_RcEmetteur')"))
        emetteur = session.execute(sql(
            "SELECT id FROM usr_emetteurs WHERE nom = '_RcEmetteur'")).scalar()
        session.execute(sql("INSERT INTO usr_membres (nom, prenom) VALUES ('_RcClio', 'Zoe')"))
        membre = session.execute(sql(
            "SELECT id FROM usr_membres WHERE nom = '_RcClio'")).scalar()

        crees = {}
        for cle, nom, champs in (
            ("emetteur", "_rc_a.pdf", {}),
            ("fichier", "_rc_zorglub_b.pdf", {}),
            ("texte", "_rc_c.pdf", {"texte_ocr": "un contrat mentionnant zorglub ici"}),
            ("chose", "_rc_d.pdf", {}),
        ):
            document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                                hash_sha256=nom.ljust(64, "r"), statut="traite",
                                categorie_id=type_doc.id,
                                **{"texte_ocr": "rien de particulier", **champs})
            session.add(document)
            session.flush()
            crees[cle] = document.id
        session.add(Metadonnee(document_id=crees["chose"], cle="titulaire",
                               valeur=f"usr_membres:{membre}"))
        session.add(Metadonnee(document_id=crees["emetteur"], cle="numero_facture",
                               valeur="ZORGLUB-42"))
        session.add(Metadonnee(document_id=crees["emetteur"], cle="emetteur",
                               valeur=f"usr_emetteurs:{emetteur}"))
        session.commit()
        yield crees, "_RcEmetteur"
    finally:
        session.close()
    _nettoyer()


def _chercher(client, terme, **params):
    reponse = client.get("/recherche", params={"q": terme, **params})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_un_mot_suffit_quel_que_soit_le_champ_qui_le_porte(client, documents_cherchables):
    crees, _ = documents_cherchables
    resultats = _chercher(client, "zorglub")["resultats"]
    trouves = {r["document"]["id"] for r in resultats}

    assert crees["fichier"] in trouves, "le nom du fichier"
    assert crees["texte"] in trouves, "le texte océrisé"
    assert crees["emetteur"] in trouves, "une métadonnée"


def test_on_trouve_par_la_chose_designee(client, documents_cherchables):
    """
    Un document qui porte `usr_membres:4` ne contient nulle part le mot
    « _RcClio » : il doit pourtant sortir quand on le tape, sinon la table du
    foyer ne sert qu'à afficher.
    """
    crees, _ = documents_cherchables
    resultats = _chercher(client, "_RcClio")["resultats"]
    trouve = next(r for r in resultats if r["document"]["id"] == crees["chose"])
    assert any(raison["source"] == "chose" for raison in trouve["raisons"])


def test_le_resultat_dit_pourquoi_il_sort(client, documents_cherchables):
    """Sans cela, un document sans rapport apparent ressemble à une erreur."""
    crees, _ = documents_cherchables
    trouve = next(r for r in _chercher(client, "zorglub")["resultats"]
                  if r["document"]["id"] == crees["fichier"])
    assert trouve["raisons"][0]["libelle"] == "Nom du fichier"


def test_lemetteur_pese_plus_que_le_corps_du_texte(client, documents_cherchables):
    crees, nom_emetteur = documents_cherchables
    scores = {r["document"]["id"]: r["score"]
              for r in _chercher(client, nom_emetteur)["resultats"]}
    # Comparés entre eux, et non à toute la base : d'autres documents de test
    # portent ce mot ailleurs, et ce qu'on vérifie ici est le **poids** des
    # sources, pas le contenu du reste de la base.
    assert scores.get(crees["emetteur"], 0) > scores.get(crees["texte"], 0)


def test_le_perimetre_restreint_la_recherche(client, documents_cherchables):
    crees, _ = documents_cherchables
    session = SessionLocal()
    try:
        autre = session.query(Categorie).filter(
            Categorie.nature != "dossier",
            Categorie.id != session.get(Document, crees["texte"]).categorie_id).first()
        identifiant_autre = autre.id if autre else None
    finally:
        session.close()
    if identifiant_autre is None:
        pytest.skip("un seul type de document dans cette base")

    restreint = _chercher(client, "zorglub", perimetre="classement",
                          categorie_id=identifiant_autre)
    assert restreint["perimetre"] == "classement"
    assert restreint["resultats"] == [], "aucun de ces documents n'est dans ce classement"


def test_un_terme_trop_court_ne_declenche_rien(client, documents_cherchables):
    """Une lettre ramènerait toute l'archive : ce n'est pas une recherche."""
    assert _chercher(client, "z")["resultats"] == []


def test_un_document_en_corbeille_ne_se_retrouve_pas(client, documents_cherchables):
    crees, _ = documents_cherchables
    client.delete(f"/documents/{crees['fichier']}")
    try:
        trouves = {r["document"]["id"] for r in _chercher(client, "zorglub")["resultats"]}
        assert crees["fichier"] not in trouves
    finally:
        client.post(f"/corbeille/{crees['fichier']}/restaurer")


def test_les_plans_de_table_sont_gardes_un_moment(base_de_test):
    """
    Relire les réglages de chaque table à chaque frappe coûtait l'essentiel du
    temps de la recherche — information_schema n'est pas gratuit. Ils sont gardés
    une minute : un réglage modifié se voit au pire au bout de ce délai, ce qui
    est sans conséquence pour un classement de résultats.
    """
    import time

    from app import recherche

    session = SessionLocal()
    try:
        recherche._plans_caches.update(date=0.0, valeur={})
        depart = time.perf_counter()
        premier = recherche._plans(session)
        froid = time.perf_counter() - depart

        depart = time.perf_counter()
        second = recherche._plans(session)
        chaud = time.perf_counter() - depart

        assert second is premier, "le second appel ne reconstruit rien"
        assert chaud < froid, "et il coûte donc moins cher"
    finally:
        session.close()
