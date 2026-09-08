"""
Les automatisations « quand… alors… » (§21.8).

Le workflow d'EzGED enchaîne étapes et tâches ; pour une maison, la même idée
tient en une phrase. Générique et réglée depuis l'administration — rien de
spécifique aux factures n'est écrit dans le code.
"""
import json

import pytest

from app import automatisations
from app.db import (Automatisation, Categorie, Document, ExecutionAutomatisation,
                    Metadonnee, SessionLocal)


def _nettoyer():
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_au%")).delete(
            synchronize_session=False)
        session.query(Automatisation).filter(Automatisation.nom.like("_AU%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def document_et_regle(base_de_test):
    _nettoyer()
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        document = Document(nom_fichier="_au_facture.pdf", chemin_stockage="/tmp/_au.pdf",
                            hash_sha256="_au".ljust(64, "a"), texte_ocr="facture urgente",
                            statut="traite", categorie_id=type_doc.id)
        session.add(document)
        session.flush()
        session.add(Metadonnee(document_id=document.id, cle="montant_ttc", valeur="1500.00"))
        session.commit()
        yield document.id, type_doc.id
    finally:
        session.close()
    _nettoyer()


def _regle(nom, conditions, actions, declencheur=automatisations.DEPOT, categorie_id=None):
    session = SessionLocal()
    try:
        regle = Automatisation(
            nom=nom, declencheur=declencheur, categorie_id=categorie_id,
            conditions=json.dumps(conditions), actions=json.dumps(actions), actif=True)
        session.add(regle)
        session.commit()
        return regle.id
    finally:
        session.close()


def _executer(document_id, declencheur=automatisations.DEPOT):
    session = SessionLocal()
    try:
        document = session.get(Document, document_id)
        bilan = automatisations.executer(session, declencheur, document)
        session.commit()
        return bilan
    finally:
        session.close()


def _meta(document_id, cle):
    session = SessionLocal()
    try:
        valeur = (session.query(Metadonnee)
                  .filter_by(document_id=document_id, cle=cle).first())
        return valeur.valeur if valeur else None
    finally:
        session.close()


def test_quand_la_condition_est_vraie_laction_a_lieu(document_et_regle):
    document_id, _ = document_et_regle
    _regle("_AU_urgent",
           [{"champ": "texte", "operateur": "contient", "valeur": "urgente"}],
           [{"type": "affecter_champ", "champ": "meta:a_verifier", "valeur": "oui"}])

    bilan = _executer(document_id)
    assert bilan and bilan[0]["faits"] == ["a_verifier = oui"]
    assert _meta(document_id, "a_verifier") == "oui"


def test_quand_elle_est_fausse_rien_ne_se_passe(document_et_regle):
    document_id, _ = document_et_regle
    _regle("_AU_jamais",
           [{"champ": "texte", "operateur": "contient", "valeur": "zorglub"}],
           [{"type": "affecter_champ", "champ": "meta:a_verifier", "valeur": "oui"}])

    assert _executer(document_id) == []
    assert _meta(document_id, "a_verifier") is None


def test_les_conditions_parlent_le_langage_des_filtres(document_et_regle):
    """
    Tout ce qui se filtre se teste : il n'y a pas de second vocabulaire à
    apprendre, et une condition écrite ici se vérifie dans le registre.
    """
    document_id, _ = document_et_regle
    _regle("_AU_montant",
           [{"champ": "meta:montant_ttc", "operateur": "contient", "valeur": "1500"}],
           [{"type": "journaliser", "message": "gros montant"}])

    assert _executer(document_id)[0]["faits"] == ["gros montant"]


def test_une_valeur_saisie_a_la_main_nest_pas_ecrasee(document_et_regle):
    """Une valeur posée par quelqu'un vaut mieux que la nôtre."""
    document_id, _ = document_et_regle
    _regle("_AU_montant2", [],
           [{"type": "affecter_champ", "champ": "meta:montant_ttc", "valeur": "0.00"}])

    assert _executer(document_id) == []
    assert _meta(document_id, "montant_ttc") == "1500.00"


def test_sauf_si_on_le_demande(document_et_regle):
    document_id, _ = document_et_regle
    _regle("_AU_montant3", [],
           [{"type": "affecter_champ", "champ": "meta:montant_ttc", "valeur": "0.00",
             "ecraser": True}])

    _executer(document_id)
    assert _meta(document_id, "montant_ttc") == "0.00"


def test_une_regle_peut_se_limiter_a_un_type(document_et_regle):
    document_id, type_id = document_et_regle
    session = SessionLocal()
    try:
        autre = (session.query(Categorie)
                 .filter(Categorie.nature == "type", Categorie.id != type_id).first())
        autre_id = autre.id if autre else None
    finally:
        session.close()
    if autre_id is None:
        pytest.skip("un seul type de document dans cette base")

    _regle("_AU_ailleurs", [], [{"type": "journaliser", "message": "x"}],
           categorie_id=autre_id)
    assert _executer(document_id) == []


def test_le_journal_dit_aussi_pourquoi_rien_na_ete_fait(document_et_regle):
    """« Pourquoi cette règle n'a rien fait » est la question la plus fréquente."""
    document_id, _ = document_et_regle
    regle_id = _regle("_AU_muette",
                      [{"champ": "texte", "operateur": "contient", "valeur": "zorglub"}],
                      [{"type": "journaliser", "message": "x"}])
    _executer(document_id)

    session = SessionLocal()
    try:
        lignes = automatisations.journal(session, automatisation_id=regle_id)
        assert lignes and lignes[0]["agi"] is False
        assert lignes[0]["detail"]["conditions_reunies"] is False
    finally:
        session.close()


def test_le_declencheur_de_date_nagit_quune_fois(document_et_regle):
    """La date, elle, revient tous les jours."""
    document_id, _ = document_et_regle
    _regle("_AU_echeance", [], [{"type": "journaliser", "message": "rappel"}],
           declencheur=automatisations.DATE)

    assert _executer(document_id, automatisations.DATE), "premier passage : ça agit"
    assert _executer(document_id, automatisations.DATE) == [], "second : plus rien"


def test_un_document_en_corbeille_est_laisse_tranquille(document_et_regle):
    from datetime import datetime

    document_id, _ = document_et_regle
    _regle("_AU_corbeille", [], [{"type": "journaliser", "message": "x"}])
    session = SessionLocal()
    try:
        session.get(Document, document_id).date_suppression = datetime.now()
        session.commit()
    finally:
        session.close()
    assert _executer(document_id) == []


def test_une_regle_sans_action_est_refusee(client):
    """Elle ne ferait rien, et rien à l'écran ne dirait pourquoi."""
    refus = client.post("/admin/automatisations", json={
        "nom": "_AU_vide", "declencheur": "document_depose", "conditions": [], "actions": []})
    assert refus.status_code == 422
    assert "sans action" in refus.json()["detail"]


def test_une_action_ou_un_declencheur_inconnu_est_refuse(client):
    assert client.post("/admin/automatisations", json={
        "nom": "_AU_x", "declencheur": "quand_il_pleut",
        "actions": [{"type": "journaliser", "message": "x"}]}).status_code == 422
    assert client.post("/admin/automatisations", json={
        "nom": "_AU_x", "declencheur": "document_depose",
        "actions": [{"type": "envoyer_une_fusee"}]}).status_code == 422


def test_le_catalogue_est_annonce_a_linterface(client):
    catalogue = client.get("/admin/automatisations/catalogue").json()
    assert {d["cle"] for d in catalogue["declencheurs"]} == set(automatisations.DECLENCHEURS)
    assert {a["cle"] for a in catalogue["actions"]} == set(automatisations.ACTIONS)
    for action in catalogue["actions"]:
        assert action["libelle"] and action["description"]


def test_lessai_ne_garde_rien(client, document_et_regle):
    """
    Écrire une automatisation puis attendre le prochain dépôt pour savoir si elle
    mord est la boucle décourageante qu'on a déjà corrigée pour les règles.
    """
    document_id, _ = document_et_regle
    creation = client.post("/admin/automatisations", json={
        "nom": "_AU_essai", "declencheur": "document_depose",
        "conditions": [{"champ": "texte", "operateur": "contient", "valeur": "urgente"}],
        "actions": [{"type": "affecter_champ", "champ": "meta:_au_essai", "valeur": "oui"}]})
    assert creation.status_code == 200, creation.text
    regle = creation.json()
    try:
        essai = client.post(f"/admin/automatisations/{regle['id']}/essayer",
                            params={"document_id": document_id})
        assert essai.status_code == 200, essai.text
        assert essai.json()["conditions_reunies"] is True
        assert essai.json()["faits"] == ["_au_essai = oui"]
        # rien n'a été gardé, ni la valeur ni la ligne de journal
        assert _meta(document_id, "_au_essai") is None
        session = SessionLocal()
        try:
            assert session.query(ExecutionAutomatisation).filter_by(
                automatisation_id=regle["id"]).count() == 0
        finally:
            session.close()
    finally:
        client.delete(f"/admin/automatisations/{regle['id']}")
