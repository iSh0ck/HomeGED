"""
Documents fantômes (§17.7).

Un document auquel il manque un champ exigé par sa catégorie n'est pas encore
classé : le montrer dans le registre laisserait croire le contraire. Il reste
consultable par son identifiant et visible au Centre d'analyse — là où on le
complète — mais il ne compte ni dans les listes, ni dans les tableaux de bord.

Le mécanisme a trois parties depuis le §22.41, et ces tests les couvrent toutes :
le Python qui **dit** ce qui manque sur un document affiché, l'état **rangé** sur
le document que lisent les listes, et le contrôle périodique qui vérifie que les
deux disent la même chose. Si l'un dérivait des autres, un document deviendrait
invisible **et** absent du Centre d'analyse, donc perdu.
"""
import pytest

from app import conformite
from app.db import (
    Categorie, Document, Metadonnee, RegleChampCategorie, SessionLocal,
)


@pytest.fixture
def categorie_exigeante(client):
    """Une catégorie qui réclame une métadonnée « montant »."""
    session = SessionLocal()
    try:
        categorie = session.query(Categorie).filter_by(nom="_FantomeCat").one_or_none()
        if not categorie:
            categorie = Categorie(nom="_FantomeCat", ordre=950)
            session.add(categorie)
            session.flush()
        session.query(RegleChampCategorie).filter_by(categorie_id=categorie.id).delete()
        session.add(RegleChampCategorie(categorie_id=categorie.id, champ="meta:montant",
                                        libelle="Montant", obligatoire=True, ordre=10))
        session.commit()
        identifiant = categorie.id
    finally:
        session.close()
    yield identifiant

    session = SessionLocal()
    try:
        session.query(RegleChampCategorie).filter_by(categorie_id=identifiant).delete()
        session.query(Document).filter(Document.nom_fichier.like("_fantome%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _creer_document(nom, categorie_id, montant=None):
    session = SessionLocal()
    try:
        document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                            hash_sha256=nom.ljust(64, "f"), texte_ocr="x",
                            statut="traite", categorie_id=categorie_id)
        session.add(document)
        session.flush()
        if montant is not None:
            session.add(Metadonnee(document_id=document.id, cle="montant", valeur=montant))
        # Ce que fait le serveur de travaux à la fin d'un traitement (§22.41) :
        # il range l'état de conformité sur le document. Un document créé sans
        # passer par là mentirait — et c'est précisément ce que le contrôle
        # périodique rattrape (voir plus bas).
        conformite.ranger(session, document)
        session.commit()
        return document.id
    finally:
        session.close()


def _ids_registre(client, **params):
    reponse = client.get("/documents", params={"limite": 1000, **params})
    assert reponse.status_code == 200, reponse.text
    return {d["id"] for d in reponse.json()}


def test_document_incomplet_absent_du_registre(client, categorie_exigeante):
    fantome = _creer_document("_fantome_incomplet.pdf", categorie_exigeante)
    complet = _creer_document("_fantome_complet.pdf", categorie_exigeante, montant="42,10")

    ids = _ids_registre(client)
    assert complet in ids, "un document complet doit rester au registre"
    assert fantome not in ids, "un document incomplet n'a pas encore sa place au registre"


def test_le_fantome_reste_consultable_et_visible_au_centre_danalyse(client, categorie_exigeante):
    fantome = _creer_document("_fantome_a_reprendre.pdf", categorie_exigeante)

    # écarté des listes, mais pas perdu : c'est la différence entre cacher et supprimer
    assert client.get(f"/documents/{fantome}").status_code == 200
    a_reprendre = {d["id"] for d in client.get("/analyse").json()}
    assert fantome in a_reprendre


def test_le_document_reparait_une_fois_complete(client, categorie_exigeante):
    fantome = _creer_document("_fantome_a_completer.pdf", categorie_exigeante)
    assert fantome not in _ids_registre(client)

    reponse = client.patch(f"/documents/{fantome}", json={"metadonnees": {"montant": "99,00"}})
    assert reponse.status_code == 200, reponse.text

    assert fantome in _ids_registre(client), "complété, il rejoint le registre"
    assert fantome not in {d["id"] for d in client.get("/analyse").json()}


def test_une_regle_ajoutee_apres_coup_renvoie_le_document_dans_lombre(client, categorie_exigeante):
    """
    Le worker n'est pas repassé : c'est bien la règle, lue à chaque requête, qui
    décide. Un flag figé en base aurait laissé ce document visible à tort.
    """
    document = _creer_document("_fantome_regle_tardive.pdf", categorie_exigeante, montant="10")
    assert document in _ids_registre(client)

    reponse = client.post("/admin/regles-champs", json={
        "categorie_id": categorie_exigeante, "champ": "meta:reference",
        "libelle": "Référence", "obligatoire": True, "ordre": 20,
    })
    assert reponse.status_code == 200, reponse.text
    try:
        assert document not in _ids_registre(client)
    finally:
        client.delete(f"/admin/regles-champs/{reponse.json()['id']}")


def test_document_sans_categorie_nest_jamais_fantome(client, categorie_exigeante):
    """On ne sait pas encore ce qu'on attend de lui : rien ne peut lui manquer."""
    orphelin = _creer_document("_fantome_sans_categorie.pdf", None)
    assert orphelin in _ids_registre(client)


def test_la_clause_sql_et_le_calcul_python_disent_la_meme_chose(categorie_exigeante):
    """
    Les deux moitiés du mécanisme doivent rester d'accord. Si le SQL écartait un
    document que le Python juge complet, ce document disparaîtrait du registre
    **et** du centre d'analyse : introuvable.
    """
    _creer_document("_fantome_accord_ko.pdf", categorie_exigeante)
    _creer_document("_fantome_accord_ok.pdf", categorie_exigeante, montant="5")

    session = SessionLocal()
    try:
        documents = session.query(Document).filter(
            Document.nom_fichier.like("_fantome_accord%")).all()
        regles = conformite.regles_par_categorie(session, {categorie_exigeante})
        selon_python = {d.id for d in documents if conformite.champs_manquants(d, regles)}

        selon_sql = {
            d.id for d in session.query(Document)
            .filter(Document.nom_fichier.like("_fantome_accord%"))
            .filter(conformite.clause_incomplet()).all()
        }
        assert selon_python == selon_sql
    finally:
        session.close()


def test_les_tableaux_de_bord_savent_compter_les_deux(client, categorie_exigeante):
    """
    L'exclusion des incomplets ne peut pas être imposée à tous les indicateurs :
    l'indicateur « À reprendre » ne parle que d'eux. C'est ce qu'a révélé
    l'usage — mis en place sans réglage de portée, ce compteur restait à zéro.
    """
    _creer_document("_fantome_tdb_ko.pdf", categorie_exigeante)
    _creer_document("_fantome_tdb_ok.pdf", categorie_exigeante, montant="7")

    accueil = client.get("/tableaux-de-bord/accueil/donnees")
    assert accueil.status_code == 200, accueil.text
    valeurs = {w["titre"]: w.get("valeur") for w in accueil.json()["widgets"] if "valeur" in w}
    a_reprendre = len(client.get("/analyse").json())
    assert valeurs["À reprendre"] == a_reprendre, "le compteur doit dire ce que montre le centre d'analyse"
    assert valeurs["À reprendre"] >= 1


def test_portee_inconnue_refusee(client):
    """Une portée mal écrite doit se dire à la saisie, pas produire un compte faux."""
    reponse = client.post("/admin/tableaux-de-bord", json={
        "nom": "_TdbPortee", "description": "", "partage": False, "ordre": 900,
        "widgets": [{"id": "w1", "type": "nombre", "titre": "Essai", "portee": "n_importe_quoi"}],
    })
    assert reponse.status_code == 422
    assert "portée" in reponse.json()["detail"].lower()


def test_le_controle_periodique_rattrape_un_etat_qui_ment(client, categorie_exigeante):
    """
    L'état rangé est écrit aux deux moments où il change (§22.41) — mais un
    chemin oublié le ferait mentir, et un document disparaîtrait du registre sans
    que personne ne sache pourquoi. Le serveur de travaux repose donc la question
    à la source, et corrige les écarts en les journalisant.
    """
    from app import worker

    fantome = _creer_document("_fantome_menteur.pdf", categorie_exigeante)
    assert fantome not in _ids_registre(client)

    # On abîme volontairement l'état rangé, comme le ferait un chemin d'écriture
    # qui aurait oublié de le poser.
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.id == fantome).update({Document.conforme: True})
        session.commit()
    finally:
        session.close()
    assert fantome in _ids_registre(client), "le mensonge se voit : le fantôme revient au registre"

    assert worker.verifier_conformite_rangee() >= 1
    assert fantome not in _ids_registre(client), "et le contrôle l'a remis à sa place"
