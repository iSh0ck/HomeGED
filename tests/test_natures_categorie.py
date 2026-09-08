"""
Dossiers et types de document (§19.1).

L'arborescence confondait deux choses : ce qui **organise** (Maison, Impôts) et
ce qui **porte des documents** (Factures). Régler les colonnes de « Maison »
n'avait aucun sens, et rien ne l'empêchait.

Ces tests portent surtout sur les refus. Un garde-fou qui laisse passer un état
que le reste du logiciel ne sait pas lire ne sert à rien — et un refus qui ne
dit pas quoi faire à la place se contourne mal, d'où la vérification des
messages.
"""
import pytest

from app.db import Categorie, Document, SessionLocal


@pytest.fixture
def arborescence(client, base_de_test):
    """Un dossier « _NatMaison » et un type « _NatFactures » à l'intérieur."""
    dossier = client.post("/admin/categories", json={
        "nom": "_NatMaison", "nature": "dossier", "ordre": 900, "priorite": 900})
    assert dossier.status_code == 200, dossier.text
    type_doc = client.post("/admin/categories", json={
        "nom": "_NatFactures", "nature": "type", "parent_id": dossier.json()["id"],
        "ordre": 901, "priorite": 901})
    assert type_doc.status_code == 200, type_doc.text

    contexte = {"dossier": dossier.json()["id"], "type": type_doc.json()["id"]}
    yield contexte

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_nat%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Nat%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_la_nature_est_rendue_par_lapi(client, arborescence):
    """L'interface s'en sert pour ses icônes et pour n'offrir que ce qui a du sens."""
    par_nom = {c["nom"]: c for c in client.get("/categories").json()}
    assert par_nom["_NatMaison"]["nature"] == "dossier"
    assert par_nom["_NatFactures"]["nature"] == "type"


def test_une_categorie_est_un_type_par_defaut(client, arborescence):
    """Le cas courant est de porter des documents ; un dossier se demande."""
    cree = client.post("/admin/categories", json={"nom": "_NatSimple", "ordre": 902})
    assert cree.status_code == 200, cree.text
    assert cree.json()["nature"] == "type"


def test_un_type_de_document_naccueille_pas_de_sous_categorie(client, arborescence):
    """
    Sans cette règle, on retrouverait des documents à mi-chemin de l'arbre, dans
    une catégorie qui en contient d'autres — ce que la distinction supprime.
    """
    refus = client.post("/admin/categories", json={
        "nom": "_NatSous", "nature": "type", "parent_id": arborescence["type"], "ordre": 903})
    assert refus.status_code == 400
    assert "ne peut pas contenir de sous-catégorie" in refus.json()["detail"]


def test_un_document_ne_se_range_pas_dans_un_dossier(client, arborescence):
    session = SessionLocal()
    try:
        document = Document(nom_fichier="_nat_doc.pdf", chemin_stockage="/x.pdf",
                            hash_sha256="nature".ljust(64, "n"), texte_ocr="x",
                            statut="traite", categorie_id=arborescence["type"])
        session.add(document)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    refus = client.patch(f"/documents/{identifiant}",
                         json={"categorie_id": arborescence["dossier"]})
    assert refus.status_code == 400
    assert "dossier" in refus.json()["detail"]
    assert "type de document" in refus.json()["detail"], \
        "le refus doit dire quoi faire à la place"


def test_un_dossier_ne_porte_ni_colonnes_ni_champs_attendus(client, arborescence):
    """
    Ces deux écrans décrivent ce qu'est un document. Un dossier n'en contient
    aucun : le régler produirait un réglage sans effet, ce qui est pire qu'un
    refus.
    """
    colonnes = client.put(f"/admin/categories/{arborescence['dossier']}/colonnes",
                          json=[{"champ": "fournisseur"}])
    assert colonnes.status_code == 400
    assert "colonnes" in colonnes.json()["detail"]

    tri = client.put(f"/admin/categories/{arborescence['dossier']}/tri",
                     json={"champ": "date_document", "sens": "asc"})
    assert tri.status_code == 400

    champ = client.post("/admin/regles-champs", json={
        "categorie_id": arborescence["dossier"], "champ": "meta:montant_ttc",
        "obligatoire": True, "ordre": 10})
    assert champ.status_code == 400
    assert "champs attendus" in champ.json()["detail"]


def test_un_dossier_avec_des_enfants_ne_devient_pas_un_type(client, arborescence):
    refus = client.put(f"/admin/categories/{arborescence['dossier']}", json={
        "nom": "_NatMaison", "nature": "type", "ordre": 900, "priorite": 900})
    assert refus.status_code == 400
    assert "sous-catégorie" in refus.json()["detail"]
    assert "Déplacez" in refus.json()["detail"], "un refus doit dire par quoi commencer"


def test_un_type_qui_porte_des_documents_ne_devient_pas_un_dossier(client, arborescence):
    session = SessionLocal()
    try:
        session.add(Document(nom_fichier="_nat_porte.pdf", chemin_stockage="/y.pdf",
                             hash_sha256="portee".ljust(64, "p"), texte_ocr="x",
                             statut="traite", categorie_id=arborescence["type"]))
        session.commit()
    finally:
        session.close()

    refus = client.put(f"/admin/categories/{arborescence['type']}", json={
        "nom": "_NatFactures", "nature": "dossier", "parent_id": arborescence["dossier"],
        "ordre": 901, "priorite": 901})
    assert refus.status_code == 400
    assert "document" in refus.json()["detail"]
    assert "Reclassez" in refus.json()["detail"]


def test_une_nature_inconnue_est_refusee(client, arborescence):
    refus = client.post("/admin/categories", json={
        "nom": "_NatFausse", "nature": "classeur", "ordre": 904})
    assert refus.status_code == 400
    assert "fiche simple" in refus.json()["detail"]


# `test_le_classement_automatique_ignore_les_dossiers` a été retiré au §19.3 :
# il n'y a plus de classement automatique. Ce que ce test protégeait — qu'un
# document n'atterrisse jamais dans un dossier — est désormais garanti en amont :
# seuls les types ont un dossier de dépôt, et c'est l'emplacement qui classe
# (`test_emplacement.py`).


def test_la_conversion_de_lexistant_suit_larborescence(client, arborescence):
    """
    La règle de la migration, vérifiée sur ce qui existe : une catégorie qui a
    des enfants est un dossier, une feuille est un type. C'est la seule lecture
    possible sans deviner l'intention.
    """
    categories = client.get("/categories").json()
    enfants = {c["parent_id"] for c in categories if c["parent_id"]}
    for categorie in categories:
        if categorie["id"] in enfants:
            assert categorie["nature"] == "dossier", \
                f"« {categorie['nom'] } » a des enfants : ce ne peut pas être un type"


def test_un_modele_livre_ne_decrit_jamais_un_dossier(client):
    """
    Les modèles sont la première chose que voit un foyer tiers : ils doivent
    montrer le bon découpage. Un dossier qui porterait des colonnes ou des champs
    attendus produirait, dès l'import, un état que l'administration refuse de
    créer à la main.
    """
    from app import modeles

    for nom, entree in modeles.MODELES.items():
        modele = entree["configuration"]
        parents = {c.get("parent") for c in modele["categories"] if c.get("parent")}
        natures = {c["nom"]: c.get("nature", "type") for c in modele["categories"]}

        for categorie, nature in natures.items():
            if categorie in parents:
                assert nature == "dossier", \
                    f"modèle « {nom} » : « {categorie} » a des enfants, ce doit être un dossier"

        dossiers = {c for c, n in natures.items() if n == "dossier"}
        for cle in ("champs_attendus", "colonnes"):
            décrites = {e.get("categorie") for e in modele.get(cle, [])}
            assert not (décrites & dossiers), \
                f"modèle « {nom} » : {décrites & dossiers} sont des dossiers, ils ne " \
                f"peuvent rien déclarer dans « {cle} »"


def test_une_configuration_sans_nature_reste_importable(base_de_test):
    """
    Un fichier exporté avant le §19.1 n'en dit rien. Plutôt que de tout importer
    en « type » — ce qui donnerait des types avec des enfants —, la nature se
    déduit comme la migration l'a fait : parent d'une autre, donc dossier.
    """
    from app import configuration
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        configuration._importer_categories(session, [
            {"nom": "_NatAncienDossier", "parent": None, "ordre": 910},
            {"nom": "_NatAncienType", "parent": "_NatAncienDossier", "ordre": 911},
        ])
        session.flush()
        natures = {c.nom: c.nature for c in session.query(Categorie).filter(
            Categorie.nom.like("_NatAncien%"))}
        assert natures["_NatAncienDossier"] == "dossier"
        assert natures["_NatAncienType"] == "type"
    finally:
        session.rollback()
        session.close()


def test_une_fiche_simple_ne_recoit_aucun_depot(client, arborescence):
    """
    La fiche simple (§22.1) porte des documents comme un type, à une différence
    près : **rien n'y entre tout seul**. Pas de dossier sous `ocr_wait`, donc pas
    de dépôt automatique — on y glisse un fichier à la main.
    """
    cree = client.post("/admin/categories", json={
        "nom": "_NatActes", "nature": "fiche",
        "parent_id": arborescence["dossier"], "ordre": 905})
    assert cree.status_code == 200, cree.text
    assert cree.json()["nature"] == "fiche"
    assert cree.json()["dossier_depot"] is None, \
        "un dossier de dépôt ferait entrer des documents sans qu'on les ait posés là"


def test_une_fiche_porte_ses_colonnes_et_ses_champs_attendus(client, arborescence):
    """
    C'est tout l'intérêt : on y saisit les valeurs à la main. Sans champs
    attendus, il n'y aurait rien à remplir ; sans colonnes, rien à lire.

    L'ancienne fiche de liaison les refusait — elle ne décrivait aucune sorte de
    document —, et c'est une des raisons pour lesquelles elle ne servait à rien.
    """
    fiche = client.post("/admin/categories", json={
        "nom": "_NatFiche", "nature": "fiche", "ordre": 908}).json()

    colonnes = client.put(f"/admin/categories/{fiche['id']}/colonnes",
                          json=[{"champ": "nom_fichier"}])
    assert colonnes.status_code == 200, colonnes.text

    champ = client.post("/admin/regles-champs", json={
        "categorie_id": fiche["id"], "champ": "meta:numero_acte",
        "obligatoire": True, "ordre": 10})
    assert champ.status_code == 200, champ.text


def test_un_document_se_range_dans_une_fiche(client, arborescence):
    """Elle porte des documents : les y déplacer à la main est le geste normal."""
    fiche = client.post("/admin/categories", json={
        "nom": "_NatFicheRange", "nature": "fiche", "ordre": 911}).json()
    session = SessionLocal()
    try:
        document = Document(nom_fichier="_nat_range.pdf", chemin_stockage="/z.pdf",
                            hash_sha256="range".ljust(64, "r"), texte_ocr="x",
                            statut="traite", categorie_id=arborescence["type"])
        session.add(document)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    deplace = client.patch(f"/documents/{identifiant}", json={"categorie_id": fiche["id"]})
    assert deplace.status_code == 200, deplace.text
    assert deplace.json()["categorie_id"] == fiche["id"]


def test_une_fiche_naccueille_pas_de_sous_categorie(client, arborescence):
    fiche = client.post("/admin/categories", json={
        "nom": "_NatFicheParente", "nature": "fiche", "ordre": 909}).json()
    refus = client.post("/admin/categories", json={
        "nom": "_NatSousFiche", "nature": "type", "parent_id": fiche["id"], "ordre": 910})
    assert refus.status_code == 400
    assert "sous-catégorie" in refus.json()["detail"]
