"""
Suivi du serveur de travaux : compteurs et filtres (§19.10).

Une rangée de pastilles suffisait à six états. Elle ne suffit plus depuis qu'on
veut aussi voir par type de document, et le décompte ne peut pas se faire à
l'écran : compter côté interface obligerait à charger tous les travaux pour n'en
afficher qu'une page — c'est-à-dire à charger d'autant plus qu'il y en a, au
moment précis où il y en a trop.
"""
import pytest

from app import categories as natures
from app.db import Categorie, Document, Job, SessionLocal


@pytest.fixture
def travaux(base_de_test):
    """Deux types de document, trois travaux : deux classés, un à classer."""
    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_suivi%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_suivi%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Suivi%")).delete(
            synchronize_session=False)

        premier = Categorie(nom="_SuiviFactures", nature=natures.TYPE, ordre=965)
        second = Categorie(nom="_SuiviCourriers", nature=natures.TYPE, ordre=966)
        session.add_all([premier, second])
        session.flush()

        identifiants = {}
        for nom, categorie, statut in (("_suivi_a.pdf", premier, "termine"),
                                       ("_suivi_b.pdf", premier, "bloque"),
                                       ("_suivi_c.pdf", second, "termine")):
            document = Document(nom_fichier=nom, chemin_stockage="/x.pdf",
                                hash_sha256=nom.ljust(64, "s"), texte_ocr="x",
                                statut="traite", categorie_id=categorie.id)
            session.add(document)
            session.flush()
            session.add(Job(nom_fichier=nom, statut=statut, document_id=document.id))

        # sans document : il n'appartient à aucun type, et c'est le sujet
        session.add(Job(nom_fichier="_suivi_d.pdf", statut="a_classer"))
        session.commit()
        identifiants = {"premier": premier.id, "second": second.id}
    finally:
        session.close()

    yield identifiants

    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_suivi%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_suivi%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Suivi%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_le_resume_compte_par_etat_et_par_type(client, travaux):
    resume = client.get("/admin/jobs/resume").json()

    assert resume["statuts"]["bloque"] >= 1
    assert resume["statuts"]["a_classer"] >= 1
    par_type = {t["nom"]: t["nombre"] for t in resume["types"]}
    assert par_type["_SuiviFactures"] == 2
    assert par_type["_SuiviCourriers"] == 1
    assert resume["total"] >= 4


def test_un_travail_sans_document_ne_compte_pour_aucun_type(client, travaux):
    """
    Il n'en a pas encore : « à classer » s'arrête avant l'indexation. Le ranger
    quelque part serait inventer un classement que personne n'a fait.
    """
    resume = client.get("/admin/jobs/resume").json()
    assert sum(t["nombre"] for t in resume["types"]
               if t["nom"].startswith("_Suivi")) == 3, \
        "les trois travaux à document, et eux seuls"


def test_les_travaux_se_filtrent_par_type_de_document(client, travaux):
    noms = {j["nom_fichier"] for j in
            client.get(f"/admin/jobs?categorie_id={travaux['premier']}").json()}
    assert noms == {"_suivi_a.pdf", "_suivi_b.pdf"}


def test_le_filtre_par_etat_reste_disponible(client, travaux):
    statuts = {j["statut"] for j in client.get("/admin/jobs?statut=a_classer").json()}
    assert statuts == {"a_classer"}


def test_les_etats_sont_rendus_dans_un_ordre_lisible(client, travaux):
    """
    D'abord ce qui attend une décision ou une action, puis ce qui se déroule,
    enfin ce qui est derrière nous. Un ordre alphabétique mettrait « bloqué »
    entre « à classer » et « en attente » sans que cela veuille rien dire.
    """
    etats = list(client.get("/admin/jobs/resume").json()["statuts"])
    assert etats == ["a_classer", "bloque", "erreur", "en_attente", "en_cours",
                     "termine", "ignore"]


def test_les_deux_filtres_se_cumulent(client, travaux):
    """
    « Ce qui est bloqué **dans** les factures » est la question qu'on se pose
    quand un type sort du lot (§19.17). Les deux filtres s'appliquaient l'un ou
    l'autre : choisir un type effaçait l'état retenu.
    """
    lignes = client.get(
        f"/admin/jobs?statut=termine&categorie_id={travaux['premier']}").json()
    assert {j["nom_fichier"] for j in lignes} == {"_suivi_a.pdf"}


def test_le_compte_par_etat_suit_le_type_retenu(client, travaux):
    """
    Une pastille qui annonce un nombre différent de la liste affichée est pire
    que pas de nombre du tout.
    """
    global_ = client.get("/admin/jobs/resume").json()
    premier = client.get(f"/admin/jobs/resume?categorie_id={travaux['premier']}").json()

    assert premier["statuts"]["termine"] == 1
    assert premier["statuts"]["a_classer"] == 0, \
        "la tâche sans document n'appartient à aucun type"
    assert global_["statuts"]["termine"] >= 2

    assert {t["nom"] for t in premier["types"]} == {t["nom"] for t in global_["types"]}, \
        "le menu doit continuer de montrer tous les types, c'est lui qui sert à en changer"
