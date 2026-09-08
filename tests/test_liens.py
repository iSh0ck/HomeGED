"""
Le critère de lien : « ce document concerne cette chose » (§20).

Le classement en arbre range par sorte de papier. Une facture d'entretien et une
carte grise parlent pourtant du même véhicule, et le disent chacune à leur façon
— « véhicule concerné » ici, « propriétaire » là. Demander `meta:vehicule` en
manquerait la moitié.
"""
import pytest
from sqlalchemy import text as sql

from app import filtres
from app.db import Categorie, Document, Metadonnee, SessionLocal


@pytest.fixture
def deux_documents_un_vehicule(base_de_test):
    """Deux documents qui désignent la même ligne par deux champs différents."""
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_lk%")).delete(
            synchronize_session=False)
        session.execute(sql("DELETE FROM usr_membres WHERE nom LIKE '_Lk%'"))
        session.execute(sql("INSERT INTO usr_membres (nom, prenom) VALUES ('_LkNom', 'Alice')"))
        membre = session.execute(sql(
            "SELECT id FROM usr_membres WHERE nom = '_LkNom'")).scalar()
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()

        identifiants = []
        for nom, cle in (("_lk_facture.pdf", "titulaire"),
                         ("_lk_carte.pdf", "proprietaire"),
                         ("_lk_etranger.pdf", None)):
            document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                                hash_sha256=nom.ljust(64, "k"), texte_ocr="x",
                                statut="traite", categorie_id=type_doc.id)
            session.add(document)
            session.flush()
            if cle:
                session.add(Metadonnee(document_id=document.id, cle=cle,
                                       valeur=f"usr_membres:{membre}"))
            identifiants.append(document.id)
        session.commit()
        yield identifiants, membre
    finally:
        session.query(Document).filter(Document.nom_fichier.like("_lk%")).delete(
            synchronize_session=False)
        session.execute(sql("DELETE FROM usr_membres WHERE nom LIKE '_Lk%'"))
        session.commit()
        session.close()


def _filtrer(critere):
    session = SessionLocal()
    try:
        query = filtres.appliquer(session.query(Document), session, [filtres.Filtre(**critere)])
        return {d.id for d in query}
    finally:
        session.close()


def test_le_lien_reunit_tous_les_champs_qui_designent_la_chose(deux_documents_un_vehicule):
    identifiants, membre = deux_documents_un_vehicule
    trouves = _filtrer({"champ": "lien:usr_membres", "operateur": "egal",
                        "valeur": f"usr_membres:{membre}"})
    assert identifiants[0] in trouves and identifiants[1] in trouves, \
        "« titulaire » et « propriétaire » désignent la même personne : les deux comptent"
    assert identifiants[2] not in trouves


def test_lidentifiant_seul_suffit(deux_documents_un_vehicule):
    """L'interface envoie tantôt « 4 », tantôt « usr_membres:4 » : les deux désignent
    la même ligne, et refuser l'un obligerait chaque appelant à savoir lequel."""
    identifiants, membre = deux_documents_un_vehicule
    assert _filtrer({"champ": "lien:usr_membres", "operateur": "egal", "valeur": str(membre)}) \
        == _filtrer({"champ": "lien:usr_membres", "operateur": "egal",
                     "valeur": f"usr_membres:{membre}"})


def test_une_reference_dune_autre_table_est_refusee(deux_documents_un_vehicule):
    with pytest.raises(filtres.FiltreInvalide):
        _filtrer({"champ": "lien:usr_membres", "operateur": "egal",
                  "valeur": "usr_vehicules:3"})


def test_rattache_ou_non_a_la_table(deux_documents_un_vehicule):
    identifiants, _ = deux_documents_un_vehicule
    rattaches = _filtrer({"champ": "lien:usr_membres", "operateur": "non_vide"})
    assert identifiants[0] in rattaches and identifiants[2] not in rattaches
    assert identifiants[2] in _filtrer({"champ": "lien:usr_membres", "operateur": "vide"})


def test_une_table_inconnue_est_refusee(base_de_test):
    session = SessionLocal()
    try:
        with pytest.raises(filtres.FiltreInvalide):
            filtres.valider_champ(session, "lien:sys_utilisateurs")
        with pytest.raises(filtres.FiltreInvalide):
            filtres.valider_champ(session, "lien:")
    finally:
        session.close()


def test_le_critere_porte_le_nom_de_la_table(base_de_test):
    """
    « Membres du foyer », pas « usr_membres » : le critère se choisit dans une
    liste lue par quelqu'un qui range ses papiers, pas par un administrateur de
    base.

    Il apparaît parce qu'un type **déclare un champ qui puise dans cette table**
    — ici « titulaire » — et non parce qu'une catégorie a été créée pour lui
    (§22.1). Le champ existait déjà : en faire dépendre le critère supprime un
    réglage sans rien retirer.
    """
    session = SessionLocal()
    try:
        champs = {c["champ"]: c for c in filtres.champs_disponibles(session)}
        assert "lien:usr_membres" in champs
        assert champs["lien:usr_membres"]["libelle"] == "Membres du foyer"
        assert champs["lien:usr_membres"]["type"] == "lien"
    finally:
        session.close()


def test_les_suggestions_ne_proposent_que_les_choses_concernees(deux_documents_un_vehicule):
    """
    Un foyer peut tenir la liste de ses membres sans qu'aucun document ne désigne
    le petit dernier : une suggestion qui ne ramène rien est une fausse piste.
    """
    identifiants, membre = deux_documents_un_vehicule
    session = SessionLocal()
    try:
        session.execute(sql("INSERT INTO usr_membres (nom, prenom) VALUES ('_LkSeul', 'Zoe')"))
        session.commit()
        base = session.query(Document.id).filter(Document.id.in_(identifiants)).scalar_subquery()
        valeurs = filtres.valeurs_distinctes(session, "lien:usr_membres", base)
        assert [v["valeur"] for v in valeurs] == [f"usr_membres:{membre}"]
        assert "Alice" in valeurs[0]["libelle"], "on propose un nom, pas un numéro de ligne"
    finally:
        session.execute(sql("DELETE FROM usr_membres WHERE nom LIKE '_Lk%'"))
        session.commit()
        session.close()


# ------------------------------------------------------------------
# Ce que le lien donne à voir depuis un document
#
# La « fiche de liaison » qui s'ouvrait sur les lignes d'une table a disparu au
# §22.1 : elle demandait trois réglages avant de montrer quoi que ce soit. Le
# lien, lui, n'en demande aucun — il vient des champs déjà déclarés.
# ------------------------------------------------------------------

def test_le_choix_dune_ligne_ramene_ses_documents(client, deux_documents_un_vehicule):
    """Le bout du parcours : le lien donne un critère, le registre le sait lire."""
    identifiants, membre = deux_documents_un_vehicule
    import json

    reponse = client.get("/documents", params={"filtres": json.dumps(
        [{"champ": "lien:usr_membres", "operateur": "egal",
          "valeur": f"usr_membres:{membre}"}])})
    assert reponse.status_code == 200, reponse.text
    trouves = {d["id"] for d in reponse.json()}
    assert identifiants[0] in trouves and identifiants[1] in trouves
    assert identifiants[2] not in trouves


# `test_depuis_un_document_le_lien_porte_son_critere` a été retiré avec la route
# `/documents/{id}/lies` : le rapprochement par valeur partagée ne s'affiche plus
# dans le panneau. Ce que ce fichier protège reste entier — le critère
# `lien:<table>`, qui sert aux filtres, aux vues et aux droits par branche, et la
# déduction qui remplit les champs à source.
