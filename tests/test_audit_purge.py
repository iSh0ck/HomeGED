"""
Purge du journal d'audit.

Un journal qu'on peut vider sans laisser de trace ne prouve plus rien. Ces tests
vérifient les trois propriétés qui rendent la purge acceptable : elle ne touche
qu'à ce qui précède la date choisie, elle se journalise elle-même, et elle ne
peut pas emporter les événements du jour — donc pas sa propre trace.
"""
from datetime import datetime, timedelta

from app.db import JournalAudit, SessionLocal


def _semer(entrees):
    """Écrit des entrées d'audit à des dates imposées, et rend leurs identifiants."""
    session = SessionLocal()
    identifiants = []
    try:
        for action, date_evenement in entrees:
            entree = JournalAudit(action=action, objet_type="_test_purge",
                                  date_evenement=date_evenement)
            session.add(entree)
            session.flush()
            identifiants.append(entree.id)
        session.commit()
    finally:
        session.close()
    return identifiants


def _existe(identifiant):
    session = SessionLocal()
    try:
        return session.get(JournalAudit, identifiant) is not None
    finally:
        session.close()


def test_purge_ne_touche_que_ce_qui_precede_la_date(client):
    maintenant = datetime.now()
    vieux, recent = _semer([
        ("_test.vieux", maintenant - timedelta(days=40)),
        ("_test.recent", maintenant - timedelta(days=1)),
    ])
    coupure = (maintenant - timedelta(days=7)).strftime("%Y-%m-%d")

    apercu = client.get(f"/admin/audit/purge-apercu?avant={coupure}")
    assert apercu.status_code == 200, apercu.text
    assert apercu.json()["nombre"] >= 1

    reponse = client.request("DELETE", f"/admin/audit?avant={coupure}")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["supprimes"] == apercu.json()["nombre"]

    assert not _existe(vieux), "l'entrée antérieure à la coupure aurait dû partir"
    assert _existe(recent), "l'entrée postérieure à la coupure devait être conservée"


def test_la_purge_laisse_sa_propre_trace(client):
    maintenant = datetime.now()
    _semer([("_test.a_purger", maintenant - timedelta(days=30))])
    coupure = (maintenant - timedelta(days=2)).strftime("%Y-%m-%d")

    supprimes = client.request("DELETE", f"/admin/audit?avant={coupure}").json()["supprimes"]

    journal = client.get("/admin/audit?action=audit.purge&limite=1").json()
    assert journal["evenements"], "la purge doit apparaître au journal"
    trace = journal["evenements"][0]
    assert trace["details"]["avant"] == coupure
    assert trace["details"]["entrees_supprimees"] == supprimes
    assert trace["utilisateur"], "la purge doit être signée par son auteur"


def test_les_evenements_du_jour_sont_intouchables(client):
    """
    La coupure ne peut pas dépasser aujourd'hui : autrement, la purge effacerait
    la trace qu'elle vient d'écrire, et l'historique disparaîtrait sans témoin.
    """
    demain = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert client.get(f"/admin/audit/purge-apercu?avant={demain}").status_code == 422
    assert client.request("DELETE", f"/admin/audit?avant={demain}").status_code == 422

    du_jour = _semer([("_test.du_jour", datetime.now())])[0]
    client.request("DELETE", f"/admin/audit?avant={datetime.now().strftime('%Y-%m-%d')}")
    assert _existe(du_jour)


def test_date_mal_formee_refusee(client):
    assert client.get("/admin/audit/purge-apercu?avant=01/09/2026").status_code == 422
    assert client.request("DELETE", "/admin/audit?avant=hier").status_code == 422


def test_purge_reservee_aux_administrateurs(client, jeton_de):
    client.post("/admin/utilisateurs", json={
        "email": "_purge_non_admin@homeged.local", "nom": "Sans droits", "prenom": "Test",
        "mot_de_passe": "MotDePasse!42", "est_admin": False, "actif": True, "roles": [],
    })
    simple = jeton_de("_purge_non_admin@homeged.local", "MotDePasse!42")
    coupure = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert simple.request("DELETE", f"/admin/audit?avant={coupure}").status_code == 403
    assert simple.get(f"/admin/audit/purge-apercu?avant={coupure}").status_code == 403
