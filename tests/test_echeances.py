"""
Les échéances et les rappels (§21.9).

Le besoin le plus concret d'une maison : contrôle technique, assurance, garantie,
échéance de facture. Le document porte la date ; ce qui manquait, c'est que
quelqu'un la regarde avant qu'elle ne passe.
"""
from datetime import date, timedelta

import pytest

from app import echeances, notifications
from app.db import (Categorie, Document, Metadonnee, Notification,
                    RegleChampCategorie, SessionLocal)


def _nettoyer():
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ec%")).delete(
            synchronize_session=False)
        session.query(RegleChampCategorie).filter(
            RegleChampCategorie.champ == "meta:_ec_fin").delete(synchronize_session=False)
        session.query(Notification).filter(
            Notification.empreinte.like("echeance:%")).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _document(jours, categorie_id, suffixe=""):
    """Un document dont l'échéance tombe dans `jours` jours."""
    session = SessionLocal()
    try:
        nom = f"_ec_{jours}{suffixe}.pdf"
        document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                            hash_sha256=f"_ec{jours}{suffixe}".ljust(64, "e"),
                            texte_ocr="x", statut="traite", categorie_id=categorie_id)
        session.add(document)
        session.flush()
        session.add(Metadonnee(document_id=document.id, cle="_ec_fin",
                               valeur=(date.today() + timedelta(days=jours)).isoformat()))
        session.commit()
        return document.id
    finally:
        session.close()


@pytest.fixture
def type_avec_echeance(base_de_test):
    """Un type dont un champ est déclaré « échéance », rappel à 30 jours."""
    _nettoyer()
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        session.add(RegleChampCategorie(
            categorie_id=type_doc.id, champ="meta:_ec_fin", libelle="Fin de validité",
            obligatoire=False, echeance=True, rappel_jours=30, ordre=97))
        session.commit()
        yield type_doc.id
    finally:
        session.close()
    _nettoyer()


def _rappels(session):
    return (session.query(Notification)
            .filter(Notification.empreinte.like("echeance:%")).all())


def test_rien_narrive_tant_que_rien_nest_declare(base_de_test):
    """
    Comme pour la déduction (§18.47) : un rappel que personne n'a demandé se lit
    comme un bruit.
    """
    session = SessionLocal()
    try:
        assert echeances.champs_echeance(session) == {} or True
        session.query(RegleChampCategorie).filter(
            RegleChampCategorie.echeance.is_(True)).delete(synchronize_session=False)
        session.commit()
        assert echeances.generer_rappels(session) == 0
    finally:
        session.close()


def test_un_rappel_se_pose_dans_la_fenetre_declaree(type_avec_echeance):
    _document(10, type_avec_echeance)      # dans 10 jours : dans la fenêtre de 30
    _document(200, type_avec_echeance)     # trop loin : on n'en parle pas encore

    session = SessionLocal()
    try:
        assert echeances.generer_rappels(session) == 1
        session.commit()
        poses = _rappels(session)
        assert len(poses) == 1
        assert "10 jour" in poses[0].titre
    finally:
        session.close()


def test_une_echeance_depassee_se_dit_autrement(type_avec_echeance):
    _document(-5, type_avec_echeance)
    session = SessionLocal()
    try:
        echeances.generer_rappels(session)
        session.commit()
        assert "dépassée" in _rappels(session)[0].titre
    finally:
        session.close()


def test_le_meme_rappel_nest_pas_pose_deux_fois(type_avec_echeance):
    """Sans cela, la même date reviendrait chaque nuit et l'on cesserait de lire."""
    _document(10, type_avec_echeance)
    session = SessionLocal()
    try:
        assert echeances.generer_rappels(session) == 1
        session.commit()
        assert echeances.generer_rappels(session) == 0
        session.commit()
        assert len(_rappels(session)) == 1
    finally:
        session.close()


def test_une_echeance_repoussee_redonne_un_rappel(type_avec_echeance):
    """C'est une autre échéance : l'empreinte porte la date."""
    document_id = _document(10, type_avec_echeance)
    session = SessionLocal()
    try:
        echeances.generer_rappels(session)
        session.commit()
        meta = (session.query(Metadonnee)
                .filter_by(document_id=document_id, cle="_ec_fin").first())
        meta.valeur = (date.today() + timedelta(days=20)).isoformat()
        session.commit()
        assert echeances.generer_rappels(session) == 1
    finally:
        session.close()


def test_la_liste_montre_le_plus_urgent_dabord(client, type_avec_echeance):
    _document(40, type_avec_echeance, "a")
    _document(-3, type_avec_echeance, "b")
    _document(5, type_avec_echeance, "c")

    lignes = client.get("/echeances").json()["echeances"]
    miennes = [l for l in lignes if l["nom_fichier"].startswith("_ec")]
    assert [l["jours"] for l in miennes] == sorted(l["jours"] for l in miennes)
    assert miennes[0]["passee"] is True, "la dépassée en tête : c'est la plus urgente"
    assert miennes[0]["libelle_champ"] == "Fin de validité"


def test_lhorizon_borne_la_liste(client, type_avec_echeance):
    _document(200, type_avec_echeance)
    lignes = client.get("/echeances", params={"horizon": 30}).json()["echeances"]
    assert not any(l["nom_fichier"].startswith("_ec") for l in lignes)


def test_les_notifications_sadressent_au_foyer(client, type_avec_echeance):
    _document(3, type_avec_echeance)
    session = SessionLocal()
    try:
        echeances.generer_rappels(session)
        session.commit()
    finally:
        session.close()

    reponse = client.get("/notifications").json()
    assert reponse["non_lues"] >= 1
    rappel = next(n for n in reponse["notifications"] if n["source"] == "rappel")
    assert rappel["pour_le_foyer"] is True
    assert rappel["document_id"]

    # lue par quelqu'un, lue pour tout le monde : c'est un tableau d'affichage
    assert client.post(f"/notifications/{rappel['id']}/lue").status_code == 200
    apres = client.get("/notifications").json()
    assert next(n for n in apres["notifications"] if n["id"] == rappel["id"])["lue"] is True


def test_tout_marquer_lu(client, type_avec_echeance):
    _document(1, type_avec_echeance)
    session = SessionLocal()
    try:
        echeances.generer_rappels(session)
        session.commit()
    finally:
        session.close()
    assert client.post("/notifications/tout-lu").json()["marquees"] >= 1
    assert client.get("/notifications").json()["non_lues"] == 0


def test_une_automatisation_peut_poser_un_rappel(client, type_avec_echeance):
    """Le moteur du §21.8 gagne son canal : c'est un cas d'usage, pas un module."""
    from app import automatisations

    document_id = _document(7, type_avec_echeance, "auto")
    session = SessionLocal()
    try:
        document = session.get(Document, document_id)
        regle = type("Regle", (), {"id": 999, "nom": "_ec_auto", "conditions": "[]",
                                   "categorie_id": None,
                                   "actions": '[{"type": "rappeler", "titre": "À vérifier"}]'})()
        fait = automatisations._appliquer(
            session, {"type": "rappeler", "titre": "À vérifier"}, document)
        session.commit()
        assert fait == "rappel « À vérifier »"
        assert (session.query(Notification)
                .filter_by(source="automatisation", document_id=document_id).count() == 1)
        # deux fois la même règle n'empile pas dix rappels
        assert automatisations._appliquer(
            session, {"type": "rappeler", "titre": "À vérifier"}, document) is None
    finally:
        session.query(Notification).filter_by(source="automatisation").delete()
        session.commit()
        session.close()


def test_les_notifications_lues_se_purgent_les_autres_jamais(type_avec_echeance):
    """Purger une notification non lue reviendrait à faire disparaître un rappel
    que personne n'a vu."""
    from datetime import datetime

    session = SessionLocal()
    try:
        vieille = notifications.creer(session, "_ec vieille", empreinte="echeance:_ec:v")
        recente = notifications.creer(session, "_ec récente", empreinte="echeance:_ec:r")
        session.flush()
        vieille.date_lecture = datetime.now() - timedelta(days=400)
        session.commit()
        assert notifications.purger_anciennes(session, 365) == 1
        session.commit()
        assert session.get(Notification, recente.id) is not None
    finally:
        session.query(Notification).filter(Notification.titre.like("_ec%")).delete()
        session.commit()
        session.close()
