"""
L'envoi de courriel (§21.10).

Les rappels n'existaient que dans l'application : encore fallait-il l'ouvrir. Un
rappel de contrôle technique doit venir vous chercher — mais un courriel traverse
des machines qui ne sont pas les nôtres, et l'insistance tue les rappels.
"""
from datetime import datetime, timedelta

import pytest

from app import courriel, notifications, reglages
from app.db import Notification, SessionLocal, Utilisateur


def _regler(**valeurs):
    session = SessionLocal()
    try:
        reglages.enregistrer(session, valeurs)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def courriel_regle(base_de_test):
    """Un SMTP déclaré (jamais joint : les envois sont interceptés)."""
    avant = {}
    session = SessionLocal()
    try:
        for cle in ("courriel_actif", "smtp_serveur", "smtp_expediteur", "adresse_publique",
                    "smtp_mot_de_passe"):
            avant[cle] = reglages.lire(session, cle)
    finally:
        session.close()

    _regler(courriel_actif="true", smtp_serveur="smtp.test.lan",
            smtp_expediteur="ged@test.lan", adresse_publique="https://ged.test.lan",
            smtp_mot_de_passe="secret-smtp")
    yield
    session = SessionLocal()
    try:
        session.query(Notification).filter(Notification.titre.like("_cr%")).delete(
            synchronize_session=False)
        for compte in session.query(Utilisateur):
            compte.palier_courriel = 0
            compte.date_dernier_courriel = None
            compte.courriel_rappels = True
        session.commit()
    finally:
        session.close()
    _regler(**{cle: valeur for cle, valeur in avant.items() if cle != "smtp_mot_de_passe"})


def test_un_secret_ne_se_relit_pas(client, courriel_regle):
    """L'écran montre qu'il existe, pas sa valeur."""
    valeurs = client.get("/admin/reglages").json()["valeurs"]
    assert valeurs["smtp_mot_de_passe"] == reglages.MARQUE_SECRET
    assert "secret-smtp" not in str(valeurs)


def test_renvoyer_la_marque_ne_lecrase_pas(client, courriel_regle):
    """
    L'écran renvoie la marque quand personne n'a retouché le champ : l'écrire
    telle quelle remplacerait le mot de passe par des points — et l'on ne s'en
    apercevrait qu'au premier envoi raté.
    """
    reponse = client.put("/admin/reglages", json={
        "smtp_mot_de_passe": reglages.MARQUE_SECRET,
        "smtp_serveur": "smtp.autre.lan"})
    assert reponse.status_code == 200, reponse.text

    session = SessionLocal()
    try:
        assert reglages.lire(session, "smtp_mot_de_passe") == "secret-smtp"
        assert reglages.lire(session, "smtp_serveur") == "smtp.autre.lan"
    finally:
        session.close()


def test_le_secret_ne_part_pas_dans_lexport(client, courriel_regle):
    export = client.get("/admin/configuration").json()
    assert "smtp_mot_de_passe" not in export["reglages"]
    assert "secret-smtp" not in str(export)


def test_sans_reglage_rien_ne_part(base_de_test):
    _regler(courriel_actif="false")
    session = SessionLocal()
    try:
        assert courriel.resumer(session)["envoyes"] == 0
    finally:
        session.close()


def test_le_resume_ne_contient_quun_lien(courriel_regle, monkeypatch):
    """
    Jamais le contenu d'un document : ce qui part chez un hébergeur de messagerie
    n'est plus à nous.
    """
    envoyes = []
    monkeypatch.setattr(courriel, "envoyer",
                        lambda session, dest, sujet, texte: envoyes.append(
                            (dest, sujet, texte)) or 1)

    session = SessionLocal()
    try:
        compte = session.query(Utilisateur).filter(Utilisateur.email.isnot(None)).first()
        notification = notifications.creer(session, "_cr Fin de garantie",
                                           "Document nº31 : Fin de garantie au 2026-10-05")
        session.flush()
        notification.date_creation = datetime.now() - timedelta(minutes=30)
        compte.palier_courriel = 0
        session.commit()

        bilan = courriel.resumer(session)
        session.commit()
    finally:
        session.close()

    assert bilan["envoyes"] >= 1
    _, sujet, texte = envoyes[0]
    assert "rappel" in sujet.lower()
    assert "https://ged.test.lan" in texte
    assert "_cr Fin de garantie" in texte


def test_ce_qui_est_parti_ne_repart_pas(courriel_regle, monkeypatch):
    monkeypatch.setattr(courriel, "envoyer", lambda *a, **k: 1)
    session = SessionLocal()
    try:
        compte = session.query(Utilisateur).filter(Utilisateur.email.isnot(None)).first()
        notification = notifications.creer(session, "_cr une fois")
        session.flush()
        notification.date_creation = datetime.now() - timedelta(minutes=30)
        compte.palier_courriel = 0
        compte.date_dernier_courriel = None
        session.commit()

        assert courriel.resumer(session)["envoyes"] >= 1
        session.commit()
        # le palier a avancé et la notification est marquée envoyée
        assert courriel.resumer(session)["envoyes"] == 0
        session.commit()
    finally:
        session.close()


def test_les_paliers_espacent_puis_cessent():
    """
    5 min, 15 min, 1 h, 24 h, 1 semaine, puis on cesse : quelqu'un qui n'a pas
    réagi en une semaine ne réagira pas au huitième message, et l'insistance fait
    basculer les rappels dans le bruit.
    """
    assert courriel.PALIERS == (5, 15, 60, 24 * 60, 7 * 24 * 60)
    assert courriel.palier_suivant(0) == 5
    assert courriel.palier_suivant(4) == 7 * 24 * 60
    assert courriel.palier_suivant(5) is None


def test_lire_un_rappel_fait_repartir_du_premier_palier(client, courriel_regle):
    """
    Sans cela, quelqu'un qui traite ses rappels resterait puni du silence qu'il a
    observé la semaine d'avant.
    """
    session = SessionLocal()
    try:
        from app import config

        compte = session.query(Utilisateur).filter_by(email=config.ADMIN_EMAIL).first()
        compte.palier_courriel = 3
        notifications.creer(session, "_cr à lire")
        session.commit()
    finally:
        session.close()

    reponse = client.get("/notifications").json()
    notification = next(n for n in reponse["notifications"] if n["titre"] == "_cr à lire")
    client.post(f"/notifications/{notification['id']}/lue")

    session = SessionLocal()
    try:
        from app import config

        assert session.query(Utilisateur).filter_by(
            email=config.ADMIN_EMAIL).first().palier_courriel == 0
    finally:
        session.close()


def test_chacun_peut_ne_pas_etre_derange(client, courriel_regle, monkeypatch):
    """
    Se taire par courriel ne fait pas perdre les rappels : ils restent dans
    l'application. C'est un choix de personne, comme le mode d'affichage.
    """
    from app import config

    servis = []
    monkeypatch.setattr(courriel, "envoyer",
                        lambda session, dest, sujet, texte: servis.extend(dest) or 1)

    assert client.put("/moi/preferences",
                      json={"courriel_rappels": False}).json()["courriel_rappels"] is False
    try:
        session = SessionLocal()
        try:
            notification = notifications.creer(session, "_cr silencieux")
            session.flush()
            notification.date_creation = datetime.now() - timedelta(minutes=30)
            for compte in session.query(Utilisateur):
                compte.palier_courriel = 0
                compte.date_dernier_courriel = None
            session.commit()
            courriel.resumer(session)
            session.commit()
        finally:
            session.close()

        assert config.ADMIN_EMAIL not in servis, \
            "personne ne doit être servi contre son gré"
        # et le rappel est toujours là, dans l'application
        assert any(n["titre"] == "_cr silencieux"
                   for n in client.get("/notifications").json()["notifications"])
    finally:
        client.put("/moi/preferences", json={"courriel_rappels": True})


def test_lessai_dit_ce_qui_ne_va_pas(client, courriel_regle):
    """« Ça n'a pas marché » n'aide personne à régler un SMTP."""
    refus = client.post("/admin/courriel/essai", json={"adresse": "pas-une-adresse"})
    assert refus.status_code == 422

    echec = client.post("/admin/courriel/essai", json={"adresse": "quelquun@test.lan"})
    assert echec.status_code == 422
    # Le serveur d'essai n'existe pas : le message doit dire pourquoi, et non se
    # contenter d'un refus — c'est là qu'on a besoin de savoir si c'est le port,
    # le mot de passe ou le certificat.
    detail = echec.json()["detail"].lower()
    assert any(mot in detail for mot in ("impossible", "refus", "serveur")), detail
    assert len(detail) > 20, "un refus sans explication n'aide pas à régler un SMTP"
