"""
Une entrée saisie à la main, sans fichier (§22.7).

Une fiche simple sert à noter ce qu'un foyer garde et qui n'a pas toujours de
papier : un contrat verbal, une garantie annoncée au téléphone, le code d'un
cadenas. Jusqu'ici il fallait un fichier pour créer une ligne — on n'avait donc
nulle part où l'écrire.

Le document devient l'unité de **ce que l'on sait** ; le fichier est une pièce
parmi d'autres, et l'on peut la glisser plus tard, ou jamais.
"""
import pytest

from app.db import Categorie, Document, RegleChampCategorie, SessionLocal


@pytest.fixture
def fiche(client, base_de_test):
    """Une fiche simple « _EmActes », avec un champ attendu."""
    creee = client.post("/admin/categories", json={
        "nom": "_EmActes", "nature": "fiche", "ordre": 955})
    assert creee.status_code == 200, creee.text
    identifiant = creee.json()["id"]
    champ = client.post("/admin/regles-champs", json={
        "categorie_id": identifiant, "champ": "meta:notaire", "libelle": "Notaire",
        "obligatoire": False, "ordre": 10})
    assert champ.status_code == 200, champ.text

    yield identifiant

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.categorie_id == identifiant).delete(
            synchronize_session=False)
        session.query(RegleChampCategorie).filter_by(categorie_id=identifiant).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.id == identifiant).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_lecran_sait_quoi_demander(client, fiche):
    """Un formulaire se construit à partir de ce que la catégorie attend."""
    reponse = client.get(f"/categories/{fiche}/champs")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["categorie"]["nature"] == "fiche"
    assert [c["champ"] for c in corps["champs"]] == ["meta:notaire"]
    assert corps["champs"][0]["libelle"] == "Notaire"


def test_une_entree_se_cree_sans_le_moindre_fichier(client, fiche):
    """
    L'intitulé n'est pas une case en plus : il vient de ce que la fiche déclare,
    dans l'ordre où elle le déclare (§22.10). Inventer « Intitulé » et « Date »
    obligerait tout le monde à remplir ce qui n'a de sens que pour certains.
    """
    creee = client.post("/documents", json={
        "categorie_id": fiche, "valeurs": {"meta:notaire": "Maître Durand"}})
    assert creee.status_code == 200, creee.text
    corps = creee.json()
    assert corps["nom_fichier"] == "Maître Durand"
    assert corps["metadonnees"]["notaire"] == "Maître Durand"

    # et elle se retrouve dans le registre, comme n'importe quel document
    liste = client.get(f"/documents?categorie_id={fiche}").json()
    assert [d["id"] for d in liste] == [corps["id"]]


def test_une_entree_sans_fichier_na_rien_a_ouvrir(client, fiche):
    """Le dire clairement vaut mieux qu'un aperçu gris qui tourne sans fin."""
    entree = client.post("/documents", json={
        "categorie_id": fiche, "valeurs": {"meta:notaire": "Code du cadenas"}}).json()

    assert client.get(f"/documents/{entree['id']}/pieces").json() == []
    assert client.get(f"/documents/{entree['id']}/fichier").status_code == 404
    assert client.get(f"/documents/{entree['id']}/apercu").status_code == 404


def test_on_peut_lui_joindre_une_piece_plus_tard(client, fiche):
    """C'est tout l'intérêt : on note d'abord, le papier arrive ensuite."""
    entree = client.post("/documents", json={
        "categorie_id": fiche, "valeurs": {"meta:notaire": "Contrat verbal"}}).json()
    depot = client.post(f"/documents/{entree['id']}/pieces",
                        files={"fichier": ("contrat.pdf", b"%PDF-1.4", "application/pdf")})
    assert depot.status_code == 200, depot.text
    assert depot.json()["document_id"] == entree["id"]


def test_on_ne_cree_pas_une_entree_dans_un_type_de_document(client, fiche):
    """
    Un type décrit ce qui arrive par son dossier de dépôt : y créer une ligne
    vide contournerait le classement par l'emplacement (§19.3).
    """
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        identifiant = type_doc.id
    finally:
        session.close()

    refus = client.post("/documents", json={
        "categorie_id": identifiant, "valeurs": {"meta:notaire": "x"}})
    assert refus.status_code == 400
    assert "dossier de dépôt" in refus.json()["detail"]


def test_une_fiche_sans_champ_declare_ne_recoit_rien(client, base_de_test):
    """
    Une fiche qui n'attend rien n'a rien à recevoir, et le refus dit où aller le
    déclarer — plutôt que d'inventer deux cases universelles.
    """
    vide = client.post("/admin/categories", json={
        "nom": "_EmVide", "nature": "fiche", "ordre": 956}).json()
    try:
        refus = client.post("/documents", json={"categorie_id": vide["id"], "valeurs": {}})
        assert refus.status_code == 400
        assert "Champs attendus" in refus.json()["detail"]
    finally:
        client.delete(f"/admin/categories/{vide['id']}")


def test_un_champ_obligatoire_non_rempli_est_refuse(client, fiche):
    """Le champ a été déclaré obligatoire : le contourner à la création
    produirait une entrée que le registre signalerait aussitôt comme incomplète."""
    session = SessionLocal()
    try:
        regle = session.query(RegleChampCategorie).filter_by(categorie_id=fiche).one()
        regle.obligatoire = True
        session.commit()
    finally:
        session.close()

    refus = client.post("/documents", json={"categorie_id": fiche, "valeurs": {}})
    assert refus.status_code == 422
    assert "Notaire" in refus.json()["detail"]


def test_une_entree_sans_fichier_ne_passe_pas_pour_un_fichier_manquant(client, fiche):
    """
    L'archive de secours signale les PDF introuvables. Une entrée qui n'a jamais
    eu de fichier n'en est pas un : la compter ferait douter d'une archive
    parfaitement complète.
    """
    from app import export

    client.post("/documents", json={
        "categorie_id": fiche, "valeurs": {"meta:notaire": "Note sans papier"}})
    session = SessionLocal()
    try:
        entree = session.query(Document).filter_by(categorie_id=fiche).one()
        assert export._fichiers_du_document(session, entree, "Actes/Note.pdf") == []
    finally:
        session.close()


def test_la_premiere_piece_dune_entree_en_devient_la_principale(client, fiche):
    """
    Une entrée saisie à la main n'a d'abord aucune pièce. La première qu'on lui
    joint doit devenir la principale : sans cela, le document n'aurait toujours
    rien à ouvrir alors qu'on vient de lui donner un fichier.
    """
    from app import pieces

    entree = client.post("/documents", json={
        "categorie_id": fiche, "valeurs": {"meta:notaire": "Bail — garage"}}).json()

    session = SessionLocal()
    try:
        document = session.get(Document, entree["id"])
        piece = pieces.ajouter(session, document, "/tmp/_em_bail.pdf", "bail.pdf",
                               "_embail".ljust(64, "b"), texte="bail")
        session.commit()
        assert piece.principale is True
        document = session.get(Document, entree["id"])
        assert document.chemin_stockage == "/tmp/_em_bail.pdf"
        assert document.nom_fichier == "bail.pdf"
    finally:
        session.close()


def test_un_champ_libre_declare_son_type(client, fiche):
    """
    Le type décide de la façon dont le champ se saisit (§22.12) : un calendrier
    pour une date, plusieurs lignes pour un commentaire. Deviner d'après le nom
    marchait pour « date_facture » et ratait « echeance ».
    """
    cree = client.post("/admin/regles-champs", json={
        "categorie_id": fiche, "champ": "meta:commentaire", "libelle": "Commentaire",
        "obligatoire": False, "type_champ": "texte_long", "ordre": 20})
    assert cree.status_code == 200, cree.text
    assert cree.json()["type_champ"] == "texte_long"

    # et l'écran de saisie le reçoit avec le champ
    champs = client.get(f"/categories/{fiche}/champs").json()["champs"]
    par_champ = {c["champ"]: c for c in champs}
    assert par_champ["meta:commentaire"]["type_champ"] == "texte_long"
    assert par_champ["meta:notaire"]["type_champ"] == "texte", "le défaut ne change rien"


def test_un_type_inconnu_retombe_sur_le_texte(client, fiche):
    """Un champ mal typé se saisit maladroitement ; un champ refusé n'existe pas."""
    cree = client.post("/admin/regles-champs", json={
        "categorie_id": fiche, "champ": "meta:bizarre", "libelle": "Bizarre",
        "obligatoire": False, "type_champ": "hologramme", "ordre": 30})
    assert cree.status_code == 200, cree.text
    assert cree.json()["type_champ"] == "texte"


def test_les_types_proposes_viennent_de_lapi(client):
    """Une liste tenue dans l'écran finirait par proposer ce que l'API refuse."""
    types = client.get("/admin/types-de-champ").json()
    assert {t["valeur"] for t in types} >= {"texte", "texte_long", "date", "nombre",
                                            "montant", "booleen"}


def test_un_champ_declare_attendre_une_regle_dextraction(client, fiche):
    """
    Sans cette déclaration, « aucune règle ne le vise » ne distinguait pas un
    commentaire qu'on saisit — et c'est très bien — d'un numéro de facture dont
    la règle manque, ce qui est un réglage à faire (§22.27).
    """
    cree = client.post("/admin/regles-champs", json={
        "categorie_id": fiche, "champ": "meta:numero", "libelle": "Numéro",
        "obligatoire": False, "extraction_attendue": True, "ordre": 40})
    assert cree.status_code == 200, cree.text
    assert cree.json()["extraction_attendue"] is True

    # et l'écran de saisie le reçoit avec le champ
    champs = client.get(f"/categories/{fiche}/champs").json()["champs"]
    par_champ = {c["champ"]: c for c in champs}
    assert par_champ["meta:numero"]["extraction_attendue"] is True
    assert par_champ["meta:notaire"]["extraction_attendue"] is False, \
        "le défaut ne réclame rien à personne"


def test_une_fiche_ne_recoit_pas_la_date_du_document(client, fiche):
    """
    « Date du document » est une colonne du document, pas une métadonnée. Elle
    s'affichait en dur dans le formulaire, pour tous les types (§22.62) : sur une
    fiche simple qui déclare sa propre date, cela faisait **deux** cases « date »
    dont une qui n'apparaît nulle part dans le tableau.

    Même travers que « Émetteur » au §21.12, et même sort : le type décide.
    """
    champs = client.get(f"/categories/{fiche}/champs").json()["champs"]
    assert "date_document" not in [c["champ"] for c in champs]


def test_un_type_qui_montre_la_date_la_propose(client, fiche):
    """
    Elle revient dès que le type la porte pour de bon — colonne réglée de son
    tableau. Une colonne visible doit rester remplissable à la main.
    """
    pose = client.put(f"/admin/categories/{fiche}/colonnes",
                      json=[{"champ": "date_document"}])
    assert pose.status_code == 200, pose.text
    champs = client.get(f"/categories/{fiche}/champs").json()["champs"]
    assert "date_document" in [c["champ"] for c in champs]


def test_une_date_deja_portee_reste_corrigeable(client, fiche):
    """
    Une date extraite par une règle doit pouvoir être corrigée, même si le type
    ne l'a jamais réclamée : on ne cache pas ce qui existe.
    """
    entree = client.post("/documents", json={
        "categorie_id": fiche, "valeurs": {"meta:notaire": "Maître Durand"}}).json()
    client.patch(f"/documents/{entree['id']}", json={"date_document": "2026-03-04"})
    fiche_relue = client.get(f"/documents/{entree['id']}").json()
    assert "date_document" in [c["champ"] for c in fiche_relue["champs_attendus"]]
