"""
Trace d'activité des sessions (§18.10).

Chaque requête authentifiée note que la session a servi. C'est un détail
d'affichage — « dernière activité il y a deux heures » dans l'écran de profil —
et cela ne doit jamais coûter une requête à l'utilisateur. Or c'est ce qui
arrivait : un écran de l'administration lance plusieurs appels d'un coup, ils
franchissaient ensemble le seuil de la minute, écrivaient tous la même ligne, et
MariaDB en refusait un — erreur 500 en pleine navigation.

**La cause tient à l'environnement.** MariaDB 12 applique par défaut l'isolation
par instantané (`innodb_snapshot_isolation`, depuis 11.6) : une transaction qui a
déjà *lu*, puis tente de modifier une ligne changée entre-temps, est refusée
(« Record has changed since last read ») au lieu d'attendre son tour. C'est aussi
pourquoi ces tests referment leur propre transaction avant de relire : ils
travaillent sur la même base, avec les mêmes règles.
"""
from datetime import datetime, timedelta

from sqlalchemy.exc import OperationalError

from app import auth
from app.db import SessionLocal, SessionOuverte, Utilisateur

JTI = "test-activite"


def _session_ouverte(session, il_y_a=timedelta(hours=2)):
    """Une session ouverte dont l'activité remonte à assez longtemps pour être notée."""
    utilisateur = session.query(Utilisateur).first()
    session.query(SessionOuverte).filter_by(jti=JTI).delete()
    ouverte = SessionOuverte(
        utilisateur_id=utilisateur.id,
        jti=JTI,
        date_expiration=datetime.now() + timedelta(hours=1),
        date_activite=datetime.now() - il_y_a,
    )
    session.add(ouverte)
    session.commit()
    return ouverte


def _relire(identifiant):
    """
    Relit la ligne dans une transaction neuve. Indispensable ici : sous
    REPEATABLE READ, une session qui a déjà lu continuerait de voir son
    instantané, et le test constaterait que rien n'a changé alors que tout a
    changé.
    """
    lecture = SessionLocal()
    try:
        return lecture.get(SessionOuverte, identifiant).date_activite
    finally:
        lecture.close()


def _nettoyer():
    menage = SessionLocal()
    try:
        menage.query(SessionOuverte).filter_by(jti=JTI).delete()
        menage.commit()
    finally:
        menage.close()


def test_l_activite_est_notee(client):
    session = SessionLocal()
    try:
        ouverte = _session_ouverte(session)
        identifiant = ouverte.id
        auth._tracer_activite(session, ouverte)
    finally:
        session.close()

    assert (datetime.now() - _relire(identifiant)).total_seconds() < 60
    _nettoyer()


def test_une_activite_recente_n_est_pas_reecrite(client):
    """Au plus une écriture par minute : le reste du temps, la base ne travaille pas."""
    session = SessionLocal()
    try:
        ouverte = _session_ouverte(session, il_y_a=timedelta(seconds=5))
        identifiant, avant = ouverte.id, ouverte.date_activite
        auth._tracer_activite(session, ouverte)
    finally:
        session.close()

    assert _relire(identifiant) == avant
    _nettoyer()


def test_l_ecriture_a_lieu_dans_sa_propre_transaction(client, monkeypatch):
    """
    Le cœur du correctif : la trace s'écrit dans une transaction neuve, dont
    l'UPDATE est la première instruction. Écrite depuis la transaction de la
    requête — qui a déjà lu le compte, la session, et le reste — elle se heurte à
    l'isolation par instantané et fait échouer la requête entière.
    """
    session = SessionLocal()
    fabriquees = []
    try:
        ouverte = _session_ouverte(session)
        vraie = auth.SessionLocal
        monkeypatch.setattr(auth, "SessionLocal",
                            lambda: (fabriquees.append(1), vraie())[1])
        auth._tracer_activite(session, ouverte)
        assert fabriquees, "la trace doit ouvrir sa propre transaction"
    finally:
        monkeypatch.undo()
        session.close()
    _nettoyer()


def test_une_panne_d_ecriture_ne_fait_pas_echouer_la_requete(client, monkeypatch):
    """
    Le filet, par principe : une trace d'activité ne vaut pas la peine de faire
    échouer la requête qui la produit, quelle que soit la raison de la panne.
    """
    session = SessionLocal()
    try:
        ouverte = _session_ouverte(session)

        class SessionQuiEchoue:
            def query(self, *args, **kwargs):
                raise OperationalError("UPDATE sys_sessions", {},
                                       Exception("1020 Record has changed"))

            def rollback(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(auth, "SessionLocal", SessionQuiEchoue)
        auth._tracer_activite(session, ouverte)   # ne doit rien lever
    finally:
        monkeypatch.undo()
        session.close()
    _nettoyer()


def test_la_navigation_enchainee_ne_casse_pas(client):
    """
    Plusieurs appels successifs sur les écrans d'administration : la situation
    qui produisait l'erreur 500 intermittente.
    """
    for chemin in ("/admin/categories", "/admin/regles", "/admin/base/tables",
                   "/admin/categories", "/auth/me"):
        reponse = client.get(chemin)
        assert reponse.status_code == 200, f"{chemin} → {reponse.status_code} {reponse.text[:200]}"


def test_la_trace_ne_salit_pas_la_session_de_la_requete(client):
    """
    Le piège dans lequel je suis tombé une fois : mettre à jour l'objet suivi
    par la requête « pour éviter une écriture » le rend sale, et l'ORM le
    réécrit au prochain `commit` — depuis la transaction de la requête, celle
    qu'on voulait justement tenir à l'écart. Le défaut revenait alors sur la
    requête suivante qui enregistrait quelque chose.
    """
    session = SessionLocal()
    try:
        ouverte = _session_ouverte(session)
        auth._tracer_activite(session, ouverte)
        assert not session.dirty, "la session de la requête doit rester propre"
        session.commit()   # ne doit émettre aucun UPDATE sur sys_sessions
    finally:
        session.close()
    _nettoyer()


def test_un_enregistrement_apres_une_trace_aboutit(client):
    """
    Le symptôme rapporté : une trace d'activité venait de s'écrire, et
    l'enregistrement suivant depuis l'administration tombait en 500.
    """
    session = SessionLocal()
    try:
        _session_ouverte(session)
    finally:
        session.close()

    assert client.get("/admin/categories").status_code == 200
    creation = client.post("/admin/categories", json={"nom": "_ColTrace", "parent_id": None})
    assert creation.status_code == 200, creation.text
    identifiant = creation.json()["id"]
    modification = client.put(f"/admin/categories/{identifiant}",
                              json={"nom": "_ColTrace2", "parent_id": None})
    assert modification.status_code == 200, modification.text
    assert client.delete(f"/admin/categories/{identifiant}").status_code == 200
    _nettoyer()
