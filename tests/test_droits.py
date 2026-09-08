"""
Droits d'accès : c'est le point le plus sensible du projet — une régression y
exposerait des documents à des comptes qui ne doivent pas les voir.
"""
from app.db import Categorie, Document, SessionLocal


def _preparer(client):
    """Deux catégories, un document dans chacune, et un compte restreint à la première."""
    session = SessionLocal()
    banque = session.query(Categorie).filter_by(nom="Banque").one()
    factures = session.query(Categorie).filter_by(nom="Factures").one()
    for suffixe, categorie in (("banque", banque), ("facture", factures)):
        if not session.query(Document).filter_by(nom_fichier=f"droits_{suffixe}.pdf").first():
            session.add(Document(
                nom_fichier=f"droits_{suffixe}.pdf", chemin_stockage=f"/tmp/{suffixe}.pdf",
                hash_sha256=suffixe.ljust(64, "0"), texte_ocr="x", statut="traite",
                categorie_id=categorie.id,
            ))
    session.commit()
    ids = (banque.id, factures.id)
    session.close()

    role = client.post("/admin/roles", json={"nom": "Restreint", "description": None})
    role_id = role.json()["id"] if role.status_code == 200 else next(
        r["id"] for r in client.get("/admin/roles").json() if r["nom"] == "Restreint")
    # Depuis le §19.12 les droits se posent action par action, et les trois axes
    # s'envoient ensemble : un enregistrement partiel laisserait un rôle à moitié
    # changé si le second appel échouait.
    client.put(f"/admin/roles/{role_id}/droits", json={"categories": [
        {"categorie_id": ids[0], "peut_voir": True, "peut_modifier": True,
         "peut_deposer": True, "peut_telecharger": True, "peut_supprimer": True,
         "peut_gerer_versions": True}]})
    client.post("/admin/utilisateurs", json={
        "email": "restreint@test.local", "nom": "Restreint", "prenom": "Test", "mot_de_passe": "motdepasse-test-1234",
        "est_admin": False, "actif": True, "role_ids": [role_id]})
    return ids


def test_un_compte_restreint_ne_voit_que_ses_categories(client, jeton_de):
    _preparer(client)
    membre = jeton_de("restreint@test.local", "motdepasse-test-1234")
    noms = {d["nom_fichier"] for d in membre.get("/documents").json()}
    assert "droits_banque.pdf" in noms
    assert "droits_facture.pdf" not in noms, "document d'une catégorie non autorisée visible"


def test_un_compte_restreint_ne_peut_pas_ouvrir_un_document_interdit(client, jeton_de):
    _preparer(client)
    membre = jeton_de("restreint@test.local", "motdepasse-test-1234")
    interdit = next(d for d in client.get("/documents").json()
                    if d["nom_fichier"] == "droits_facture.pdf")
    assert membre.get(f"/documents/{interdit['id']}").status_code == 403
    assert membre.delete(f"/documents/{interdit['id']}").status_code == 403


def test_un_compte_en_lecture_seule_ne_peut_pas_supprimer(client, jeton_de):
    ids = _preparer(client)
    role_id = next(r["id"] for r in client.get("/admin/roles").json() if r["nom"] == "Restreint")
    client.put(f"/admin/roles/{role_id}/droits", json={"categories": [
        {"categorie_id": ids[0], "peut_voir": True, "peut_modifier": False,
         "peut_supprimer": False}]})
    membre = jeton_de("restreint@test.local", "motdepasse-test-1234")
    autorise = next(d for d in membre.get("/documents").json()
                    if d["nom_fichier"] == "droits_banque.pdf")
    assert membre.delete(f"/documents/{autorise['id']}").status_code == 403
    client.put(f"/admin/roles/{role_id}/droits", json={"categories": [
        {"categorie_id": ids[0], "peut_voir": True, "peut_modifier": True,
         "peut_deposer": True, "peut_telecharger": True, "peut_supprimer": True,
         "peut_gerer_versions": True}]})


def test_le_dernier_administrateur_est_protege(client):
    """Le supprimer ou le rétrograder rendrait l'administration définitivement inaccessible."""
    moi = client.get("/auth/me").json()
    assert client.delete(f"/admin/utilisateurs/{moi['id']}").status_code == 409
    reponse = client.put(f"/admin/utilisateurs/{moi['id']}", json={
        "email": moi["email"], "nom": moi["nom"], "est_admin": False, "actif": True, "role_ids": []})
    assert reponse.status_code == 409


def test_l_administration_est_refusee_aux_non_admins(client, jeton_de):
    _preparer(client)
    membre = jeton_de("restreint@test.local", "motdepasse-test-1234")
    for route in ("/admin/utilisateurs", "/admin/jobs", "/admin/audit", "/admin/corbeille",
                  "/admin/base/tables"):
        assert membre.get(route).status_code == 403, route


# ------------------------------------------------------------
# Ordre d'affichage des catégories
# ------------------------------------------------------------

def test_l_ordre_d_affichage_prime_sur_l_alphabet(client):
    """
    `ordre` décide de la place dans la navigation ; l'alphabet ne départage que
    les catégories de même rang.
    """
    categories = client.get("/admin/categories").json()
    racines = [c for c in categories if not c["parent_id"]]
    assert len(racines) >= 2, "il faut au moins deux catégories racines pour ce test"

    # on force un ordre volontairement contraire à l'alphabet
    inverse = sorted(racines, key=lambda c: c["nom"], reverse=True)
    for position, categorie in enumerate(inverse):
        client.put(f"/admin/categories/{categorie['id']}", json={
            "nom": categorie["nom"], "nature": categorie["nature"],
            "dossier_depot": categorie["dossier_depot"], "ordre": (position + 1) * 10,
            "parent_id": categorie["parent_id"]})

    visibles = [c["nom"] for c in client.get("/categories").json() if not c["parent_id"]]
    assert visibles == [c["nom"] for c in inverse]
    assert visibles != sorted(visibles), "l'ordre choisi devrait différer de l'alphabet"


# `test_l_ordre_d_affichage_et_la_priorite_de_test_sont_independants` a été retiré
# au §19.3 : la priorité de test n'existe plus. Elle ordonnait les expressions de
# classement, et le classement ne se devine plus — il se dépose (`test_depots.py`,
# `test_emplacement.py`). Seul `ordre` demeure, et c'est la navigation.


def test_une_categorie_creee_recoit_un_ordre_par_defaut(client):
    creee = client.post("/admin/categories", json={
        "nom": "_Ordre par défaut", "parent_id": None}).json()
    assert creee["ordre"] == 100
    client.delete(f"/admin/categories/{creee['id']}")


def test_le_dernier_administrateur_ne_peut_pas_se_desactiver(client):
    """
    Perdre le dernier administrateur ferme l'administration à tout le monde, et
    le compte initial n'est recréé que sur une base vide : il faudrait alors
    intervenir en SQL. Trois portes à garder — désactiver, rétrograder, supprimer.
    """
    moi = client.get("/auth/me").json()
    utilisateurs = client.get("/admin/utilisateurs").json()
    autres_admins = [u for u in utilisateurs
                     if u["id"] != moi["id"] and u["est_admin"] and u["actif"]]
    for autre in autres_admins:      # on se met dans la situation « dernier admin »
        client.put(f"/admin/utilisateurs/{autre['id']}", json={
            "email": autre["email"], "nom": autre.get("nom") or "X",
            "est_admin": False, "actif": autre["actif"], "role_ids": []})

    base = {"email": moi["email"], "nom": moi["nom"], "role_ids": []}
    try:
        desactivation = client.put(f"/admin/utilisateurs/{moi['id']}",
                                   json={**base, "est_admin": True, "actif": False})
        assert desactivation.status_code == 409, desactivation.text
        assert "dernier administrateur" in desactivation.json()["detail"]

        retrogradation = client.put(f"/admin/utilisateurs/{moi['id']}",
                                    json={**base, "est_admin": False, "actif": True})
        assert retrogradation.status_code == 409

        suppression = client.delete(f"/admin/utilisateurs/{moi['id']}")
        assert suppression.status_code == 409

        # le compte est intact : un refus ne doit rien avoir changé au passage
        apres = client.get("/auth/me").json()
        assert apres["est_admin"] is True
    finally:
        for autre in autres_admins:
            client.put(f"/admin/utilisateurs/{autre['id']}", json={
                "email": autre["email"], "nom": autre.get("nom") or "X",
                "est_admin": True, "actif": autre["actif"], "role_ids": []})


def test_un_second_administrateur_lève_le_verrou(client):
    """Le refus porte sur le *dernier* : à deux, chacun peut être désactivé."""
    second = client.post("/admin/utilisateurs", json={
        "email": "_t_second_admin@homeged.local", "nom": "Second", "prenom": "Admin",
        "mot_de_passe": "MotDePasse!42", "est_admin": True, "actif": True, "role_ids": [],
    })
    assert second.status_code == 200, second.text
    identifiant = second.json()["id"]
    try:
        desactivation = client.put(f"/admin/utilisateurs/{identifiant}", json={
            "email": "_t_second_admin@homeged.local", "nom": "Second",
            "est_admin": True, "actif": False, "role_ids": []})
        assert desactivation.status_code == 200, desactivation.text
    finally:
        client.delete(f"/admin/utilisateurs/{identifiant}")


def test_les_criteres_dune_vue_se_modifient_depuis_ladministration(client):
    """
    Ils ne se changeaient qu'en refaisant la recherche dans le registre puis en
    réenregistrant la vue (§19.8) : corriger une vue partagée demandait de
    reconstituer une recherche qu'on n'avait pas forcément faite soi-même.
    """
    creee = client.post("/vues", json={
        "nom": "_Vue à corriger", "categorie_id": None,
        "criteres": [{"champ": "nom_fichier", "operateur": "contient", "valeur": "edf"}],
        "partagee": True, "ordre": 900})
    assert creee.status_code == 200, creee.text
    identifiant = creee.json()["id"]

    try:
        modifiee = client.put(f"/vues/{identifiant}", json={
            "nom": "_Vue à corriger", "categorie_id": None,
            "criteres": [
                {"champ": "date_document", "operateur": "apres", "valeur": "2026-01-01"},
                {"champ": "meta:emetteur", "operateur": "non_vide", "valeur": None},
            ],
            "partagee": True, "ordre": 900})
        assert modifiee.status_code == 200, modifiee.text
        assert [c["champ"] for c in modifiee.json()["criteres"]] == \
            ["date_document", "meta:emetteur"]

        # ... et ils restent exécutables par le moteur : une vue qu'on ne peut
        # pas appliquer serait pire qu'une vue qu'on ne peut pas corriger
        import json as json_module
        registre = client.get("/documents", params={
            "filtres": json_module.dumps(modifiee.json()["criteres"])})
        assert registre.status_code == 200, registre.text
    finally:
        client.delete(f"/vues/{identifiant}")


def test_un_critere_impossible_est_refuse_a_lenregistrement(client):
    """
    Mieux vaut refuser à la saisie que produire une vue qui échouera à chaque
    ouverture, sans dire pourquoi.
    """
    refus = client.post("/vues", json={
        "nom": "_Vue impossible", "categorie_id": None,
        "criteres": [{"champ": "nom_fichier", "operateur": "avant", "valeur": "2026-01-01"}],
        "partagee": False, "ordre": 901})
    assert refus.status_code in (400, 422), refus.text


def test_le_centre_danalyse_exige_son_droit_general(client, jeton_de):
    """
    Les fichiers **à classer** n'ont pas encore de catégorie (§22.38) : aucun
    droit par branche ne peut les protéger, et le filtrage par document ne s'y
    applique pas. C'est donc le droit général « Centre d'analyse » qui tient la
    porte — sans quoi n'importe quel compte connecté pouvait lister, télécharger
    et classer tout ce qui attendait, y compris ce qu'il n'aurait jamais dû voir.
    """
    from app.db import Job, SessionLocal

    _preparer(client)
    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_dr9%")).delete(
            synchronize_session=False)
        job = Job(nom_fichier="_dr9_recu.pdf", statut="a_classer",
                  chemin_source="/tmp/_dr9_recu.pdf")
        session.add(job)
        session.commit()
        job_id = job.id
    finally:
        session.close()

    try:
        membre = jeton_de("restreint@test.local", "motdepasse-test-1234")
        assert membre.get("/a-classer").status_code == 403
        assert membre.get(f"/a-classer/{job_id}/fichier").status_code == 403
        assert membre.post(f"/a-classer/{job_id}",
                           json={"categorie_id": 1}).status_code == 403
        assert membre.delete(f"/a-classer/{job_id}").status_code == 403

        # L'administrateur, lui, passe : la porte se ferme sans se bloquer.
        assert client.get("/a-classer").status_code == 200
    finally:
        session = SessionLocal()
        try:
            session.query(Job).filter(Job.nom_fichier.like("_dr9%")).delete(
                synchronize_session=False)
            session.commit()
        finally:
            session.close()
