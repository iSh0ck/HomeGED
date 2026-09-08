"""Cycle de vie d'un document : conformité, correction en place, suppression."""
from app.db import Categorie, Document, SessionLocal


def _document(nom, categorie_nom=None, **champs):
    session = SessionLocal()
    existant = session.query(Document).filter_by(nom_fichier=nom).first()
    if existant:
        identifiant = existant.id
        session.close()
        return identifiant
    categorie = session.query(Categorie).filter_by(nom=categorie_nom).one() if categorie_nom else None
    document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                        hash_sha256=nom.ljust(64, "2"), texte_ocr="x", statut="traite",
                        categorie_id=categorie.id if categorie else None, **champs)
    session.add(document)
    session.commit()
    identifiant = document.id
    session.close()
    return identifiant


def test_un_champ_exige_rend_le_document_incomplet(client):
    categorie = client.post("/admin/categories", json={
        "nom": "Conformite", "parent_id": None}).json()
    client.post("/admin/regles-champs", json={
        "categorie_id": categorie["id"], "champ": "meta:reference", "source_table": None,
        "libelle": "Référence", "obligatoire": True, "ordre": 10})
    document_id = _document("conformite.pdf")
    client.patch(f"/documents/{document_id}", json={"categorie_id": categorie["id"]})

    detail = client.get(f"/documents/{document_id}").json()
    assert [c["libelle"] for c in detail["champs_manquants"]] == ["Référence"]
    assert document_id in {d["id"] for d in client.get("/analyse").json()}

    # correction en place : le document doit reprendre son cours
    corrige = client.patch(f"/documents/{document_id}",
                           json={"metadonnees": {"reference": "ABC-123"}}).json()
    assert corrige["champs_manquants"] == []
    assert corrige["statut"] == "traite"
    assert document_id not in {d["id"] for d in client.get("/analyse").json()}


def test_une_valeur_effacee_fait_revenir_le_document(client):
    document_id = _document("conformite.pdf")
    retour = client.patch(f"/documents/{document_id}", json={"metadonnees": {"reference": ""}}).json()
    assert retour["statut"] == "incomplet"
    client.patch(f"/documents/{document_id}", json={"metadonnees": {"reference": "ABC-123"}})


def test_la_suppression_epargne_un_fichier_encore_reference(client):
    """
    Deux enregistrements peuvent partager un même PDF (dépôts homonymes
    antérieurs au correctif). Supprimer l'un ne doit pas condamner le fichier.

    Depuis le §21.1, la suppression n'y touche de toute façon plus : elle met à
    la corbeille, et le fichier reste référencé par la fiche elle-même. C'est à
    l'effacement définitif que la question se pose, et le balayage du serveur de
    travaux — qui ne retient que les fichiers sans **aucune** référence — y
    répond seul.
    """
    session = SessionLocal()
    for suffixe in ("x", "y"):
        if not session.query(Document).filter_by(nom_fichier=f"partage_{suffixe}.pdf").first():
            session.add(Document(nom_fichier=f"partage_{suffixe}.pdf",
                                 chemin_stockage="/tmp/partage.pdf",
                                 hash_sha256=f"partage{suffixe}".ljust(64, "3"),
                                 texte_ocr="x", statut="traite"))
    session.commit()
    ids = [d.id for d in session.query(Document)
           .filter(Document.nom_fichier.like("partage_%")).order_by(Document.id)]
    session.close()

    assert client.delete(f"/documents/{ids[0]}").json()["corbeille"] is True
    # le second est intact, et le fichier partagé toujours référencé deux fois
    assert ids[1] in {d["id"] for d in client.get("/documents").json()}

    assert client.delete(f"/admin/documents-supprimes/{ids[0]}").status_code == 200
    session = SessionLocal()
    try:
        restants = (session.query(Document)
                    .filter(Document.chemin_stockage == "/tmp/partage.pdf").count())
        assert restants == 1, "le fichier reste porté par l'autre fiche"
    finally:
        session.close()


def test_la_suppression_est_journalisee(client):
    document_id = _document("a_supprimer.pdf")
    assert client.delete(f"/documents/{document_id}").status_code == 200
    traces = client.get("/admin/audit", params={
        "action": "document.suppression", "objet_id": document_id}).json()
    assert traces["total"] == 1
    details = traces["evenements"][0]["details"]
    assert details["nom_fichier"] == "a_supprimer.pdf"


def test_le_document_absent_renvoie_404(client):
    assert client.get("/documents/999999").status_code == 404
    assert client.delete("/documents/999999").status_code == 404


def test_une_vue_enregistree_rejoue_ses_criteres(client):
    document_id = _document("vue.pdf", "Courriers")
    categorie = next(c for c in client.get("/categories").json() if c["nom"] == "Courriers")
    vue = client.post("/vues", json={
        "nom": "Courriers du foyer", "categorie_id": categorie["id"],
        "criteres": [{"champ": "categorie", "operateur": "egal", "valeur": str(categorie["id"])}],
        "partagee": False, "ordre": 100}).json()
    rechargee = next(v for v in client.get("/vues").json() if v["id"] == vue["id"])
    import json as _json
    resultats = client.get("/documents", params={"filtres": _json.dumps(rechargee["criteres"])}).json()
    assert document_id in {d["id"] for d in resultats}
    assert client.delete(f"/vues/{vue['id']}").status_code == 200


def test_une_vue_aux_criteres_invalides_est_refusee(client):
    reponse = client.post("/vues", json={
        "nom": "KO", "categorie_id": None,
        "criteres": [{"champ": "inexistant", "valeur": "x"}], "partagee": False, "ordre": 100})
    assert reponse.status_code == 422


# ------------------------------------------------------------
# Verrou de modification : ce que voit celui qui arrive second (§17.21)
# ------------------------------------------------------------

def test_le_second_arrivant_est_prevenu_par_un_message_nomme(client):
    """
    Deux personnes du foyer ouvrent la même facture. La seconde doit comprendre
    ce qui se passe — pas se heurter à un refus muet, ni écraser le travail de
    l'autre sans le savoir.
    """
    from app.db import Document, SessionLocal

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier == "_verrou.pdf").delete()
        document = Document(nom_fichier="_verrou.pdf", chemin_stockage="/x.pdf",
                            hash_sha256="verrou".ljust(64, "v"), texte_ocr="x", statut="traite")
        session.add(document)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    autre = client.post("/admin/utilisateurs", json={
        "email": "_t_verrou@homeged.local", "nom": "Martin", "prenom": "Claire",
        "mot_de_passe": "MotDePasse!42", "est_admin": False, "actif": True, "role_ids": [],
    })
    assert autre.status_code == 200, autre.text

    try:
        # Claire prend le verrou
        from fastapi.testclient import TestClient
        from app.api import app
        with TestClient(app) as claire:
            jeton = claire.post("/auth/login", data={
                "username": "_t_verrou@homeged.local", "password": "MotDePasse!42"}).json()
            claire.headers["Authorization"] = f"Bearer {jeton['access_token']}"
            assert claire.post(f"/documents/{identifiant}/verrou").status_code == 200

            # l'administrateur arrive ensuite
            refus = client.post(f"/documents/{identifiant}/verrou")
            assert refus.status_code == 409
            message = refus.json()["detail"]
            assert "Claire Martin" in message, "le message doit nommer qui détient la fiche"
            assert "modification" in message.lower()

            # et la modification elle-même est refusée, pas seulement la prise du verrou
            ecriture = client.patch(f"/documents/{identifiant}", json={"date_document": None})
            assert ecriture.status_code == 409
            assert "Claire Martin" in ecriture.json()["detail"]
    finally:
        client.delete(f"/admin/utilisateurs/{autre.json()['id']}")
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier == "_verrou.pdf").delete()
            session.commit()
        finally:
            session.close()


# `test_les_documents_qui_designent_la_meme_chose_se_rejoignent` et
# `test_un_document_sans_reference_na_aucun_lien` ont été retirés avec la route
# `/documents/{id}/lies` : le rapprochement automatique par valeur partagée ne
# s'affiche plus (demande de l'utilisateur — « c'est plus l'affichage côté
# frontend qui me dérange »). Ce qu'ils protégeaient vit ailleurs : la déduction
# des champs à source est couverte par `test_references_auto.py`, et le critère
# `lien:<table>` par `test_liens.py`.


def test_la_fiche_montre_les_champs_du_type_meme_vides(client):
    """
    Quand on ouvre une fiche, on cherche souvent ce qui **manque** (§19.20). Une
    case vide se voit et se réclame ; une case absente laisse croire que le champ
    n'existe pas.
    """
    from app.db import Categorie, RegleChampCategorie, SessionLocal

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_fiche%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        session.query(RegleChampCategorie).filter_by(
            categorie_id=type_doc.id, champ="meta:_fiche_jamais_rempli").delete()
        session.add(RegleChampCategorie(
            categorie_id=type_doc.id, champ="meta:_fiche_jamais_rempli",
            libelle="Champ jamais rempli", obligatoire=False, ordre=98))
        document = Document(nom_fichier="_fiche_doc.pdf", chemin_stockage="/tmp/x.pdf",
                            hash_sha256="fiche".ljust(64, "f"), texte_ocr="x",
                            statut="traite", categorie_id=type_doc.id)
        session.add(document)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    try:
        champs = client.get(f"/documents/{identifiant}").json()["champs_fiche"]
        par_cle = {c["cle"]: c for c in champs}
        assert "_fiche_jamais_rempli" in par_cle, \
            "un champ que le type attend doit se voir, même sans valeur"
        assert par_cle["_fiche_jamais_rempli"]["valeur"] is None
        assert par_cle["_fiche_jamais_rempli"]["libelle"] == "Champ jamais rempli"
    finally:
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier.like("_fiche%")).delete(
                synchronize_session=False)
            session.query(RegleChampCategorie).filter_by(
                champ="meta:_fiche_jamais_rempli").delete()
            session.commit()
        finally:
            session.close()


def test_les_colonnes_retirees_ne_reviennent_sur_la_fiche_que_si_le_type_le_dit(client):
    """
    Le réglage a d'abord vécu dans le profil de chacun ; il est remonté sur le
    type (§19.21). Retirer une colonne est une décision d'administration : si
    chacun pouvait la contourner de son côté, deux personnes n'auraient plus la
    même fiche sous les yeux et le réglage ne voudrait plus rien dire.
    """
    from app.db import Categorie, ColonneCategorie, Metadonnee, SessionLocal

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_masq%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        type_id, avant = type_doc.id, bool(type_doc.fiche_champs_masques)
        session.query(ColonneCategorie).filter_by(
            categorie_id=type_id, champ="meta:_masq_note").delete()
        session.add(ColonneCategorie(categorie_id=type_id, champ="meta:_masq_note",
                                     libelle="Note interne", visible=False, ordre=97))
        document = Document(nom_fichier="_masq_doc.pdf", chemin_stockage="/tmp/x.pdf",
                            hash_sha256="masq".ljust(64, "m"), texte_ocr="x",
                            statut="traite", categorie_id=type_id)
        session.add(document)
        session.flush()
        session.add(Metadonnee(document_id=document.id, cle="_masq_note", valeur="secret"))
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    def cles():
        return {c["cle"] for c in client.get(f"/documents/{identifiant}").json()["champs_fiche"]}

    try:
        # par défaut, une colonne retirée du tableau l'est aussi de la fiche
        assert "_masq_note" not in cles()

        assert client.put(f"/admin/categories/{type_id}/fiche",
                          json={"champs_masques": True}).status_code == 200
        assert "_masq_note" in cles(), \
            "le type a demandé à les revoir : la donnée ne doit pas rester introuvable"

        client.put(f"/admin/categories/{type_id}/fiche", json={"champs_masques": False})
        assert "_masq_note" not in cles()
    finally:
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier.like("_masq%")).delete(
                synchronize_session=False)
            session.query(ColonneCategorie).filter_by(champ="meta:_masq_note").delete()
            categorie = session.get(Categorie, type_id)
            categorie.fiche_champs_masques = avant
            session.commit()
        finally:
            session.close()


def test_une_valeur_a_source_unique_est_prefixee_a_la_saisie(client):
    """
    Un champ qui puise dans une table range `usr_emetteurs:5`, pas `5` (§21.12).

    Sans ce préfixe, la valeur ne se relit plus : ni son libellé, ni le
    rattachement, ni le repli, ni le filtre. Le document affichait un numéro nu,
    et l'on cherchait pourquoi l'émetteur « n'était pas trouvé » alors qu'il
    venait d'être choisi. Constaté en service sur deux factures.
    """
    from sqlalchemy import text as sql

    from app.db import Categorie, RegleChampCategorie, SessionLocal

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_pfx%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        session.query(RegleChampCategorie).filter_by(
            categorie_id=type_doc.id, champ="meta:_pfx_emetteur").delete()
        session.add(RegleChampCategorie(
            categorie_id=type_doc.id, champ="meta:_pfx_emetteur", libelle="Émetteur",
            obligatoire=False, source_table="usr_emetteurs", sources="usr_emetteurs",
            ordre=15))
        document = Document(nom_fichier="_pfx.pdf", chemin_stockage="/tmp/_pfx.pdf",
                            hash_sha256="_pfx".ljust(64, "p"), texte_ocr="x",
                            statut="traite", categorie_id=type_doc.id)
        session.add(document)
        session.commit()
        identifiant = document.id
        emetteur = session.execute(sql("SELECT id FROM usr_emetteurs LIMIT 1")).scalar()
    finally:
        session.close()

    try:
        reponse = client.patch(f"/documents/{identifiant}",
                               json={"metadonnees": {"_pfx_emetteur": str(emetteur)}})
        assert reponse.status_code == 200, reponse.text
        assert reponse.json()["metadonnees"]["_pfx_emetteur"] == f"usr_emetteurs:{emetteur}"
        # et la valeur se relit : le libellé accompagne la référence
        assert reponse.json()["libelles_references"].get("_pfx_emetteur")

        # une valeur déjà préfixée n'est pas préfixée deux fois
        client.patch(f"/documents/{identifiant}",
                     json={"metadonnees": {"_pfx_emetteur": f"usr_emetteurs:{emetteur}"}})
        assert client.get(f"/documents/{identifiant}").json()[
            "metadonnees"]["_pfx_emetteur"] == f"usr_emetteurs:{emetteur}"

        # un champ sans source garde ce qu'on lui donne : « 5 » peut être un numéro
        client.patch(f"/documents/{identifiant}", json={"metadonnees": {"_pfx_libre": "5"}})
        assert client.get(f"/documents/{identifiant}").json()["metadonnees"]["_pfx_libre"] == "5"
    finally:
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier.like("_pfx%")).delete(
                synchronize_session=False)
            session.query(RegleChampCategorie).filter_by(champ="meta:_pfx_emetteur").delete()
            session.commit()
        finally:
            session.close()


def test_les_compteurs_de_la_barre_disent_la_meme_chose_que_les_ecrans(client):
    """
    Les quatre chiffres de la barre d'outils viennent d'une seule requête de
    `COUNT` (§22.39) : l'écran les obtenait en listant tout — le registre entier
    chargé quatre fois par minute pour afficher « 3 ».

    Ce qui compte ici, c'est qu'ils **disent la même chose** que les écrans :
    un compteur qui annonce autre chose que ce qu'on trouve en cliquant est pire
    qu'absent.
    """
    compteurs = client.get("/compteurs")
    assert compteurs.status_code == 200, compteurs.text
    corps = compteurs.json()

    analyse = client.get("/analyse").json()
    a_classer = client.get("/a-classer").json()
    corbeille = client.get("/corbeille").json()["documents"]

    assert corps["a_analyser"] == len(analyse)
    assert corps["a_classer"] == len(a_classer)
    assert corps["corbeille"] == len(corbeille)
    assert corps["rappels"] == client.get("/notifications?non_lues=true").json()["non_lues"]


def test_le_centre_danalyse_se_lit_par_page(client):
    """
    Mille huit cents documents à reprendre pesaient 825 ko à chaque ouverture
    (§22.43) : on les traite ligne à ligne, la page suffit. Le total part dans
    l'en-tête, comme au registre — sans quoi l'écran ne saurait pas combien il
    en reste.
    """
    reponse = client.get("/analyse?limite=2")
    assert reponse.status_code == 200, reponse.text
    assert "X-Total-Count" in reponse.headers
    total = int(reponse.headers["X-Total-Count"])
    assert len(reponse.json()) <= 2
    assert len(reponse.json()) <= total

    # La page suivante ne redonne pas les mêmes documents.
    if total > 2:
        premiers = {d["id"] for d in reponse.json()}
        suivants = {d["id"] for d in client.get("/analyse?limite=2&decalage=2").json()}
        assert not (premiers & suivants)
