"""
Plusieurs sources pour un même champ (§17.28, revu au §18.13).

Le titulaire d'une facture peut être quelqu'un du foyer ou quelqu'un d'une autre
liste tenue à part — les personnes hébergées, les proches dont on garde les
papiers. Obliger à choisir une seule liste rendrait l'autre inatteignable.

Conséquence : une valeur porte sa source (`usr_membres:3`), puisque deux tables
ont chacune leur ligne nº3. Ces tests vérifient que le préfixe est écrit, relu,
et que les valeurs enregistrées **avant** ce changement restent comprises.

Les deux sources sont ici deux tables du foyer. Elles l'ont un temps été « les
comptes de la GED et une table » ; les comptes ne sont plus une source depuis le
§18.13 — une table du système ne se règle pas depuis l'administration.
"""
import pytest
from sqlalchemy import text

from app import base_donnees, references_auto
from app.db import (
    Categorie, Document, Metadonnee, RegleChampCategorie, SessionLocal, TableDonnees,
)

FOYER = "usr_membres_multi"
PROCHES = "usr_proches_multi"


def _creer(session, nom_table, libelle, personnes):
    session.execute(text(f"DROP TABLE IF EXISTS {nom_table}"))
    session.execute(text(
        f"CREATE TABLE {nom_table} (id INT AUTO_INCREMENT PRIMARY KEY, "
        f"nom VARCHAR(150) NOT NULL, prenom VARCHAR(100) NOT NULL)"))
    session.query(TableDonnees).filter_by(nom_table=nom_table).delete()
    session.add(TableDonnees(nom_table=nom_table, libelle=libelle,
                             colonne_libelle="nom", colonnes_identifiantes="prenom,nom"))
    for prenom, nom in personnes:
        session.execute(text(f"INSERT INTO {nom_table} (prenom, nom) VALUES (:p, :n)"),
                        {"p": prenom, "n": nom})


@pytest.fixture
def champ_a_deux_sources(client):
    """Un champ « titulaire » qui puise dans deux tables de personnes."""
    session = SessionLocal()
    try:
        _creer(session, FOYER, "Membres du foyer (test)", [("Timothée", "Renard")])
        _creer(session, PROCHES, "Proches (test)", [("Sophie", "Martin")])

        categorie = session.query(Categorie).filter_by(nom="_MultiSources").one_or_none()
        if not categorie:
            categorie = Categorie(nom="_MultiSources", ordre=980)
            session.add(categorie)
            session.flush()
        session.query(RegleChampCategorie).filter_by(categorie_id=categorie.id).delete()
        session.add(RegleChampCategorie(
            categorie_id=categorie.id, champ="meta:titulaire",
            source_table=PROCHES, sources=f"{PROCHES},{FOYER}",
            # la déduction se déclare depuis le §18.47 ; sans elle rien n'est cherché
            deduction="toutes",
            libelle="Titulaire", obligatoire=False, ordre=50))
        session.commit()
        sophie = session.execute(
            text(f"SELECT id FROM {PROCHES} WHERE prenom = 'Sophie'")).scalar()
        contexte = {"categorie_id": categorie.id, "sophie": sophie}
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(RegleChampCategorie).filter_by(categorie_id=contexte["categorie_id"]).delete()
        session.query(Document).filter(Document.nom_fichier.like("_multi%")).delete(
            synchronize_session=False)
        for nom_table in (FOYER, PROCHES):
            session.query(TableDonnees).filter_by(nom_table=nom_table).delete()
            session.execute(text(f"DROP TABLE IF EXISTS {nom_table}"))
        session.commit()
    finally:
        session.close()


def _document(nom, categorie_id, texte, valeur_titulaire=None):
    session = SessionLocal()
    try:
        doc = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                       hash_sha256=nom.ljust(64, "m"), texte_ocr=texte,
                       statut="traite", categorie_id=categorie_id)
        session.add(doc)
        session.flush()
        if valeur_titulaire:
            session.add(Metadonnee(document_id=doc.id, cle="titulaire", valeur=valeur_titulaire))
        session.commit()
        return doc.id
    finally:
        session.close()


def test_les_deux_sources_sont_proposees(client, champ_a_deux_sources):
    proches = client.get(f"/references/{PROCHES}").json()
    foyer = client.get(f"/references/{FOYER}").json()
    assert any(o["libelle"] == "Sophie Martin" for o in proches)
    assert any(o["libelle"] == "Timothée Renard" for o in foyer)

    identifiant = _document("_multi_fiche.pdf", champ_a_deux_sources["categorie_id"], "x")
    fiche_champ = next(
        c for c in client.get(f"/documents/{identifiant}").json()["champs_attendus"]
        if c["champ"] == "meta:titulaire"
    )
    assert fiche_champ["sources"] == [PROCHES, FOYER]


def test_le_rattachement_cherche_dans_toutes_les_sources(champ_a_deux_sources):
    proche = _document("_multi_proche.pdf", champ_a_deux_sources["categorie_id"],
                       "Facture au nom de Sophie MARTIN")
    membre = _document("_multi_membre.pdf", champ_a_deux_sources["categorie_id"],
                       "Facture au nom de Timothee RENARD")

    for identifiant, attendu, source in ((proche, "Sophie Martin", PROCHES),
                                         (membre, "Timothée Renard", FOYER)):
        session = SessionLocal()
        try:
            document = session.get(Document, identifiant)
            remplis = references_auto.remplir(session, document)
            session.commit()
            assert set(remplis["titulaire"].split()) == set(attendu.split())
            valeur = {m.cle: m.valeur for m in document.metadonnees}["titulaire"]
            # la valeur porte sa source : deux tables ont chacune leur ligne nº1
            assert valeur.startswith(f"{source}:")
        finally:
            session.close()


def test_une_valeur_ambigue_entre_deux_sources_nest_pas_tranchee(champ_a_deux_sources):
    """Si le document nomme les deux, choisir à la place de quelqu'un serait faux."""
    identifiant = _document("_multi_ambigu.pdf", champ_a_deux_sources["categorie_id"],
                            "Sophie Martin et Timothee Renard")
    session = SessionLocal()
    try:
        document = session.get(Document, identifiant)
        assert references_auto.remplir(session, document) == {}
    finally:
        session.close()


def test_une_valeur_sans_prefixe_reste_comprise(client, champ_a_deux_sources):
    """
    Les valeurs écrites avant les sources multiples n'ont pas de préfixe : elles
    appartiennent à la première source déclarée. Les perdre reviendrait à effacer
    des rattachements déjà faits.
    """
    identifiant = _document("_multi_ancien.pdf", champ_a_deux_sources["categorie_id"], "x",
                            valeur_titulaire=str(champ_a_deux_sources["sophie"]))
    fiche = client.get(f"/documents/{identifiant}").json()
    assert fiche["libelles_references"]["titulaire"] == "Sophie Martin"


def test_le_decoupage_dune_valeur_est_sans_ambiguite():
    assert base_donnees.decouper_valeur("usr_membres:3", "usr_proches") == ("usr_membres", "3")
    assert base_donnees.decouper_valeur("7", "usr_proches") == ("usr_proches", "7")
    assert base_donnees.decouper_valeur("", "usr_proches") == ("usr_proches", "")
