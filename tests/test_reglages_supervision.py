"""
Réglages généraux (§18.19) et supervision (§18.18).

Deux écrans d'administration sans rapport apparent, réunis ici parce qu'ils
répondent à la même question : ce que l'on peut savoir et régler **depuis
l'interface**, sans accès au serveur.
"""
from app import reglages
from app.db import Reglage, SessionLocal


def _nettoyer():
    session = SessionLocal()
    try:
        session.query(Reglage).delete()
        session.commit()
    finally:
        session.close()


def test_le_fuseau_par_defaut_est_celui_du_foyer(client):
    _nettoyer()
    valeurs = client.get("/reglages").json()
    assert valeurs["fuseau_horaire"] == "Europe/Paris"


def test_un_administrateur_change_le_fuseau(client):
    _nettoyer()
    reponse = client.put("/admin/reglages", json={"fuseau_horaire": "America/Montreal"})
    assert reponse.status_code == 200, reponse.text
    assert client.get("/reglages").json()["fuseau_horaire"] == "America/Montreal"
    _nettoyer()


def test_un_fuseau_inconnu_est_refuse(client):
    """
    Il rendrait toutes les heures illisibles d'un coup : mieux vaut refuser
    l'enregistrement que d'avoir à le deviner ensuite.
    """
    _nettoyer()
    refus = client.put("/admin/reglages", json={"fuseau_horaire": "Terre/Milieu"})
    assert refus.status_code == 422
    assert "fuseau" in refus.json()["detail"].lower()
    assert client.get("/reglages").json()["fuseau_horaire"] == "Europe/Paris"


def test_une_cle_inconnue_est_refusee(client):
    refus = client.put("/admin/reglages", json={"couleur_du_ciel": "bleu"})
    assert refus.status_code == 422


def test_rien_n_est_ecrit_si_un_reglage_du_lot_est_invalide(client):
    """
    Le lot est validé en entier avant d'être écrit : un réglage juste ne doit pas
    être enregistré à côté d'un réglage refusé, sinon l'écran affiche un état que
    la base ne porte qu'à moitié.
    """
    _nettoyer()
    refus = client.put("/admin/reglages",
                       json={"nom_foyer": "Chez nous", "fuseau_horaire": "Nulle/Part"})
    assert refus.status_code == 422
    assert client.get("/reglages").json()["nom_foyer"] == ""


def test_un_compte_ordinaire_lit_les_reglages_mais_ne_les_change_pas(client):
    """Le fuseau décide de l'affichage pour tout le monde ; il se règle par un seul."""
    cree = client.post("/admin/utilisateurs", json={
        "email": "_t_reglages@homeged.local", "nom": "Petit", "prenom": "Jean",
        "mot_de_passe": "MotDePasse!42", "est_admin": False, "actif": True, "role_ids": [],
    })
    assert cree.status_code == 200, cree.text
    try:
        from fastapi.testclient import TestClient
        from app.api import app
        with TestClient(app) as ordinaire:
            jeton = ordinaire.post("/auth/login", data={
                "username": "_t_reglages@homeged.local", "password": "MotDePasse!42",
            }).json()["access_token"]
            ordinaire.headers["Authorization"] = f"Bearer {jeton}"
            assert ordinaire.get("/reglages").status_code == 200
            assert ordinaire.put("/admin/reglages",
                                 json={"fuseau_horaire": "UTC"}).status_code == 403
    finally:
        client.delete(f"/admin/utilisateurs/{cree.json()['id']}")


def test_la_validation_ne_touche_pas_a_la_base(client):
    assert reglages.valider("fuseau_horaire", " Europe/Paris ") == "Europe/Paris"
    assert reglages.valider("fuseau_horaire", "") == "Europe/Paris"
    for invalide in ("Terre/Milieu", "Paris", "Europe/Marseille"):
        try:
            reglages.valider("fuseau_horaire", invalide)
            raise AssertionError(f"« {invalide} » aurait dû être refusé")
        except reglages.ReglageInvalide:
            pass


def test_le_releve_de_supervision_dit_l_essentiel(client):
    """
    Trois questions posées trop tard d'habitude : reste-t-il de la place, la
    machine tient-elle, le traitement suit-il.
    """
    releve = client.get("/admin/supervision")
    assert releve.status_code == 200, releve.text
    etat = releve.json()

    assert etat["disques"]["archives"]["total"] > 0
    assert 0 <= etat["disques"]["archives"]["pourcentage"] <= 100
    assert etat["machine"]["memoire"]["total"] > 0
    assert 0 <= etat["machine"]["cpu"]["pourcentage"] <= 100
    assert etat["base"]["octets"] >= 0
    assert "sys_documents" in [t["nom"] for t in etat["base"]["tables"]] or etat["base"]["tables"]
    assert etat["travaux"]["en_attente"] >= 0
    assert etat["documents"]["total"] >= 0
    assert etat["activite"]["comptes_actifs"] >= 1


def test_la_supervision_n_est_pas_ouverte_a_tous(client):
    cree = client.post("/admin/utilisateurs", json={
        "email": "_t_supervision@homeged.local", "nom": "Petit", "prenom": "Anne",
        "mot_de_passe": "MotDePasse!42", "est_admin": False, "actif": True, "role_ids": [],
    })
    assert cree.status_code == 200, cree.text
    try:
        from fastapi.testclient import TestClient
        from app.api import app
        with TestClient(app) as ordinaire:
            jeton = ordinaire.post("/auth/login", data={
                "username": "_t_supervision@homeged.local", "password": "MotDePasse!42",
            }).json()["access_token"]
            ordinaire.headers["Authorization"] = f"Bearer {jeton}"
            assert ordinaire.get("/admin/supervision").status_code == 403
    finally:
        client.delete(f"/admin/utilisateurs/{cree.json()['id']}")


# ------------------------------------------------------------
# Les réglages ne sont pas décoratifs : ils changent le comportement (§18.22)
# ------------------------------------------------------------

def test_la_duree_de_session_suit_le_reglage(client):
    from app import auth
    from app.db import SessionLocal as Fabrique

    session = Fabrique()
    try:
        reglages.enregistrer(session, {"duree_session_heures": "3"})
        assert auth.duree_session_minutes(session) == 180
        reglages.enregistrer(session, {"duree_session_heures": "24"})
        assert auth.duree_session_minutes(session) == 1440
    finally:
        session.close()
        _nettoyer()


def test_le_seuil_de_verrouillage_suit_le_reglage(client):
    """
    Le compteur d'échecs vit en mémoire du processus : ses seuils sont relus à
    chaque tentative, faute de quoi il faudrait redémarrer pour qu'un réglage
    prenne effet — ce qui reviendrait à le laisser dans `.env`.
    """
    from app.api import limiteur_connexion

    client.put("/admin/reglages", json={"tentatives_avant_verrouillage": "3",
                                        "duree_verrouillage_minutes": "7"})
    client.post("/auth/login", data={"username": "inconnu@nulle.part", "password": "faux"})
    assert limiteur_connexion.max_tentatives == 3
    assert limiteur_connexion.verrouillage == 7 * 60
    _nettoyer()


def test_la_longueur_minimale_du_mot_de_passe_suit_le_reglage(client):
    client.put("/admin/reglages", json={"longueur_min_mot_de_passe": "20"})
    refus = client.post("/moi/mot-de-passe", json={
        "ancien": "motdepasse-de-test-1234", "nouveau": "trop-court-mais-pas-vingt"[:15]})
    assert refus.status_code == 422
    assert "20 caractères" in refus.json()["detail"]
    _nettoyer()


def test_la_double_authentification_peut_etre_exigee_du_foyer_entier(client):
    """
    Sans ce réglage, il fallait cocher la case compte par compte — et y penser
    pour chaque compte créé ensuite.
    """
    client.put("/admin/reglages", json={"otp_obligatoire": "true"})
    profil = client.get("/auth/me").json()
    assert profil["otp_impose"] is True, "le compte doit savoir qu'on l'exige de lui"
    _nettoyer()
    assert client.get("/auth/me").json()["otp_impose"] is False


def test_les_reglages_de_traitement_parviennent_au_worker(client):
    from app import worker
    from app.db import SessionLocal as Fabrique

    session = Fabrique()
    try:
        reglages.enregistrer(session, {"langue_ocr": "fra+eng", "resolution_ocr": "200",
                                       "compression_niveau": "1"})
        lus = worker.reglages_traitement(session)
    finally:
        session.close()
        _nettoyer()

    assert lus == {"langue": "fra+eng", "resolution": 200, "optimisation": 1}


def test_une_langue_d_ocr_mal_ecrite_est_refusee(client):
    for invalide in ("français", "fr", "fra+e", "12+eng"):
        refus = client.put("/admin/reglages", json={"langue_ocr": invalide})
        assert refus.status_code == 422, invalide
    assert client.put("/admin/reglages", json={"langue_ocr": "fra+eng"}).status_code == 200
    # un « + » en trop est une faute de frappe à l'intention limpide : on la corrige
    # plutôt que de la refuser
    assert client.put("/admin/reglages",
                      json={"langue_ocr": "fra+"}).json()["langue_ocr"] == "fra"
    _nettoyer()


def test_une_couleur_d_accent_doit_etre_une_couleur(client):
    assert client.put("/admin/reglages", json={"couleur_accent": "bleu"}).status_code == 422
    ok = client.put("/admin/reglages", json={"couleur_accent": "3E5C46"})
    assert ok.status_code == 200
    assert ok.json()["couleur_accent"] == "#3e5c46", "normalisée, dièse compris"
    _nettoyer()


# ------------------------------------------------------------
# Journal : ce qui a changé, et rien d'autre (§18.33)
# ------------------------------------------------------------

def _dernier_evenement(action):
    import json
    from app.db import JournalAudit, SessionLocal as Fabrique

    session = Fabrique()
    try:
        entree = (session.query(JournalAudit)
                  .filter(JournalAudit.action == action)
                  .order_by(JournalAudit.id.desc()).first())
        if not entree:
            return None
        return json.loads(entree.details) if entree.details else {}
    finally:
        session.close()


def test_le_journal_ne_retient_que_les_reglages_modifies(client):
    """
    L'entrée portait l'état complet — dix-neuf réglages dont dix-huit inchangés.
    Relire le journal ne disait donc rien de ce qui avait changé, ce qui est
    l'inverse de ce qu'on lui demande.
    """
    _nettoyer()
    client.put("/admin/reglages", json={"duree_session_heures": "6"})

    details = _dernier_evenement("reglages.modification")
    assert set(details["avant"]) == {"duree_session_heures"}
    assert set(details["apres"]) == {"duree_session_heures"}
    assert details["avant"]["duree_session_heures"] == "8", "l'ancienne valeur"
    assert details["apres"]["duree_session_heures"] == "6", "la nouvelle"
    assert "theme" not in details["apres"], "un réglage non soumis n'a rien à faire là"
    _nettoyer()


def test_le_journal_porte_les_intitules_lisibles(client):
    """
    « duree_session_heures » ne se relit pas. Les intitulés voyagent avec
    l'événement : le réglage peut être renommé, voire retiré, entre le moment où
    on le change et celui où on relit le journal.
    """
    _nettoyer()
    client.put("/admin/reglages", json={"densite": "compacte"})
    details = _dernier_evenement("reglages.modification")
    assert details["libelles"]["densite"] == "Densité du tableau"
    _nettoyer()


def test_plusieurs_reglages_en_un_lot_donnent_une_seule_entree(client):
    _nettoyer()
    client.put("/admin/reglages", json={"densite": "compacte", "theme": "sombre",
                                        "lignes_par_page": "100"})
    details = _dernier_evenement("reglages.modification")
    assert set(details["apres"]) == {"densite", "theme", "lignes_par_page"}
    # Le défaut est « auto » depuis le §22.50 : la palette suit le système tant
    # que le foyer n'a rien choisi.
    assert details["avant"]["theme"] == "auto"
    _nettoyer()


def test_un_reglage_reenregistre_a_l_identique_ne_laisse_pas_de_trace(client):
    """Un journal qui consigne des non-événements se relit mal."""
    from app.db import JournalAudit, SessionLocal as Fabrique

    _nettoyer()
    client.put("/admin/reglages", json={"theme": "sombre"})

    session = Fabrique()
    try:
        avant = session.query(JournalAudit).filter(
            JournalAudit.action == "reglages.modification").count()
    finally:
        session.close()

    client.put("/admin/reglages", json={"theme": "sombre"})   # même valeur

    session = Fabrique()
    try:
        apres = session.query(JournalAudit).filter(
            JournalAudit.action == "reglages.modification").count()
    finally:
        session.close()
    assert apres == avant, "réenregistrer la même valeur n'est pas un événement"
    _nettoyer()


def test_la_retention_du_suivi_se_regle_depuis_ladministration(client):
    """
    Elle vivait dans une variable d'environnement (§19.11) : la changer demandait
    d'éditer un fichier `.env` et de redémarrer un conteneur, ce qu'un foyer
    tiers n'a pas à faire pour un nombre de jours.
    """
    champs = {c["cle"]: c for c in client.get("/admin/reglages").json()["champs"]}
    assert "retention_jobs_jours" in champs
    assert champs["retention_jobs_jours"]["groupe"] == "exploitation"

    enregistre = client.put("/admin/reglages", json={"retention_jobs_jours": "30"})
    assert enregistre.status_code == 200, enregistre.text
    assert client.get("/admin/reglages").json()["valeurs"]["retention_jobs_jours"] == "30"


def test_une_retention_a_zero_ne_purge_rien(base_de_test):
    """
    Zéro se lit « ne purge pas » et non « purge tout » : le contraire effacerait
    tout le suivi à la première passe d'entretien.
    """
    from app import reglages, worker
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        avant = reglages.lire(session, "retention_jobs_jours")
        reglages.enregistrer(session, {"retention_jobs_jours": "0"})
        session.commit()
    finally:
        session.close()

    try:
        assert worker.purger_jobs_anciens() == 0
    finally:
        session = SessionLocal()
        try:
            reglages.enregistrer(session, {"retention_jobs_jours": avant})
            session.commit()
        finally:
            session.close()
