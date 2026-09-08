"""
Colonnes du tableau propres à chaque catégorie (§18.1).

Deux exigences se répondent ici : un tableau **utilisable sans configuration**
(les colonnes sont déduites de ce que la catégorie déclare et de ce que ses
documents portent) et un tableau **configurable** quand la déduction ne suffit
pas. Ces tests vérifient les deux, et le fait qu'une règle ajoutée après coup
n'attende pas qu'on retouche la configuration pour apparaître.
"""
import pytest

from app import colonnes
from app.db import (
    Categorie,
    ColonneCategorie,
    Document,
    Metadonnee,
    RegleChampCategorie,
    SessionLocal,
)


@pytest.fixture
def categorie_factures(base_de_test):
    """Une catégorie avec des champs attendus et des documents qui en portent."""
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_col%")).delete(
            synchronize_session=False)
        parent = Categorie(nom="_ColParent", ordre=980)
        session.add(parent)
        session.flush()
        categorie = Categorie(nom="_ColFactures", parent_id=parent.id, ordre=981)
        session.add(categorie)
        session.flush()
        enfant = Categorie(nom="_ColElectricite", parent_id=categorie.id, ordre=982)
        session.add(enfant)

        session.add(RegleChampCategorie(categorie_id=categorie.id, champ="meta:montant_ttc",
                                        libelle="Montant TTC", obligatoire=True, ordre=10))
        session.add(RegleChampCategorie(categorie_id=categorie.id, champ="meta:titulaire",
                                        libelle="Titulaire", obligatoire=False, ordre=50))

        doc = Document(nom_fichier="_col_facture.pdf", chemin_stockage="/x.pdf",
                       hash_sha256="col1".ljust(64, "c"), texte_ocr="x",
                       statut="traite", categorie_id=categorie.id)
        session.add(doc)
        session.flush()
        # extraite sans être exigée : c'est pourtant ce qu'on cherche des yeux
        session.add(Metadonnee(document_id=doc.id, cle="numero_facture", valeur="FR-001"))
        session.add(Metadonnee(document_id=doc.id, cle="montant_ttc", valeur="50.99"))
        session.commit()
        identifiants = (parent.id, categorie.id, enfant.id)
    finally:
        session.close()

    yield identifiants

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_col%")).delete(
            synchronize_session=False)
        for nom in ("_ColElectricite", "_ColFactures", "_ColParent"):
            session.query(Categorie).filter_by(nom=nom).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _champs(liste):
    return [c["champ"] for c in liste]


def test_sans_categorie_les_colonnes_restent_celles_du_registre(base_de_test):
    session = SessionLocal()
    try:
        assert _champs(colonnes.pour_categorie(session, None)) == colonnes.DEFAUT
    finally:
        session.close()


def test_les_colonnes_sont_deduites_sans_configuration(categorie_factures):
    """
    Rien n'est configuré : le tableau montre malgré tout ce qui compte — les
    champs déclarés par le type, dans l'ordre où on les a pensés, la date, puis
    les métadonnées réellement extraites.

    Plus d'émetteur en tête depuis le §21.12 : il n'est plus un champ du document
    mais une métadonnée comme une autre, et il n'apparaît donc que si le type le
    déclare — ce que fait la base livrée.
    """
    _, factures, _ = categorie_factures
    session = SessionLocal()
    try:
        champs = _champs(colonnes.pour_categorie(session, factures))
    finally:
        session.close()

    # Ni le classement ni le statut : dans le tableau d'un type, toutes les
    # lignes partagent le premier, et le second n'apprend rien depuis que le
    # registre écarte les documents incomplets (§18.9).
    assert "categorie" not in champs
    assert "statut" not in champs
    for attendu in ("date_document", "meta:montant_ttc", "meta:titulaire", "meta:numero_facture"):
        assert attendu in champs, f"{attendu} manque"


def test_le_type_de_la_regle_decide_de_la_presentation(categorie_factures):
    """
    Le type décide de la mise en forme et du contrôle de recherche — mais pas de
    l'alignement : toutes les colonnes sont à gauche (§18.15).
    """
    _, factures, _ = categorie_factures
    session = SessionLocal()
    try:
        montant = next(c for c in colonnes.pour_categorie(session, factures)
                       if c["champ"] == "meta:montant_ttc")
        date = next(c for c in colonnes.pour_categorie(session, factures)
                    if c["champ"] == "date_document")
    finally:
        session.close()

    assert montant["type"] == "montant", "de quoi écrire « 50,99 » plutôt que « 50.99 »"
    assert "alignement" not in montant, "aucune colonne n'a d'alignement propre"
    assert montant["libelle"] == "Montant TTC", "l'intitulé de la règle prime sur la clé"
    assert date["filtre"] == "date", "une date se filtre au calendrier"


def test_un_type_nherite_plus_des_colonnes_de_son_dossier(categorie_factures):
    """
    L'héritage a été retiré au §19.7. Il servait quand une catégorie pouvait à la
    fois porter des documents et en contenir d'autres ; depuis le §19.1, un
    parent est un **dossier**, qui ne porte aucune colonne et n'a donc rien à
    transmettre. Un type sans configuration retombe sur ses colonnes déduites —
    ce qui reste utilisable sans rien régler.
    """
    _, factures, enfant = categorie_factures
    session = SessionLocal()
    try:
        session.add(ColonneCategorie(categorie_id=factures, champ="meta:emetteur", ordre=0))
        session.add(ColonneCategorie(categorie_id=factures, champ="meta:numero_facture",
                                     libelle="N° facture", ordre=1))
        session.commit()
        propre = colonnes.pour_categorie(session, enfant)
    finally:
        session.query(ColonneCategorie).delete()
        session.commit()
        session.close()

    assert not any(c.get("heritee_de") for c in propre), \
        "plus rien ne doit se dire hérité"
    assert "meta:numero_facture" not in _champs(propre), \
        "la colonne configurée sur le parent ne doit pas descendre"
    assert propre, "l'enfant garde ses colonnes déduites, il n'est pas vide"


def test_appliquer_les_colonnes_aux_autres_types_du_dossier(client, categorie_factures):
    """
    Ce qui remplace l'héritage : une copie faite **une fois, à la demande**. Les
    types touchés gardent ensuite leur vie propre — c'est la différence, et c'est
    voulue : un réglage qu'on déclenche se voit, un héritage se découvre au
    mauvais moment.
    """
    parent, factures, enfant = categorie_factures
    session = SessionLocal()
    try:
        # les deux types doivent être dans le même dossier pour être voisins
        session.query(Categorie).filter_by(id=enfant).update({"parent_id": parent})
        session.query(Categorie).filter_by(id=parent).update({"nature": "dossier"})
        session.commit()
    finally:
        session.close()

    pose = client.put(f"/admin/categories/{factures}/colonnes", json=[
        {"champ": "meta:emetteur"}, {"champ": "meta:numero_facture", "libelle": "N° facture"}])
    assert pose.status_code == 200, pose.text

    bilan = client.post(f"/admin/categories/{factures}/colonnes/propager")
    assert bilan.status_code == 200, bilan.text
    assert bilan.json()["types"], "au moins un voisin doit avoir été servi"

    voisin = client.get(f"/admin/categories/{enfant}/colonnes").json()
    assert [c["champ"] for c in voisin["configurees"]] == ["meta:emetteur", "meta:numero_facture"]
    assert voisin["configurees"][1]["libelle"] == "N° facture"

    # ... et la copie s'arrête là : modifier la source ne suit plus
    client.put(f"/admin/categories/{factures}/colonnes", json=[{"champ": "date_document"}])
    apres = client.get(f"/admin/categories/{enfant}/colonnes").json()
    assert [c["champ"] for c in apres["configurees"]] == ["meta:emetteur", "meta:numero_facture"]


def test_appliquer_sans_colonnes_configurees_est_refuse(client, categorie_factures):
    """Il n'y aurait rien à copier : mieux vaut le dire que ne rien faire."""
    _, factures, _ = categorie_factures
    client.put(f"/admin/categories/{factures}/colonnes", json=[])
    refus = client.post(f"/admin/categories/{factures}/colonnes/propager")
    assert refus.status_code == 400
    assert "enregistrez" in refus.json()["detail"].lower()


def test_une_colonne_masquee_disparait_sans_faire_disparaitre_les_autres(categorie_factures):
    """
    Masquer se dit « pas celle-là ». Une ligne masquée reste dans la
    configuration — elle garde sa place et son intitulé — mais ne s'affiche pas ;
    la retirer de la liste, c'est autre chose, et cela se fait aussi.
    """
    _, factures, _ = categorie_factures
    session = SessionLocal()
    try:
        session.add(ColonneCategorie(categorie_id=factures, champ="meta:emetteur", ordre=0))
        session.add(ColonneCategorie(categorie_id=factures, champ="date_document", ordre=1))
        session.add(ColonneCategorie(categorie_id=factures, champ="statut",
                                     visible=False, ordre=2))
        session.commit()
        champs = _champs(colonnes.pour_categorie(session, factures))
    finally:
        session.query(ColonneCategorie).delete()
        session.commit()
        session.close()

    assert "statut" not in champs
    assert champs[:2] == ["meta:emetteur", "date_document"], "les autres restent, dans leur ordre"


def test_une_metadonnee_ecartee_ne_revient_pas_d_elle_meme(categorie_factures):
    """
    Une configuration est un choix. Si toute métadonnée trouvée dans les
    documents s'y ajoutait d'office, la colonne écartée hier reviendrait demain,
    et le réglage ne tiendrait pas.
    """
    _, factures, _ = categorie_factures
    session = SessionLocal()
    try:
        session.add(ColonneCategorie(categorie_id=factures, champ="meta:emetteur", ordre=0))
        session.add(ColonneCategorie(categorie_id=factures, champ="date_document", ordre=1))
        session.commit()
        champs = _champs(colonnes.pour_categorie(session, factures))
    finally:
        session.query(ColonneCategorie).delete()
        session.commit()
        session.close()

    assert "meta:numero_facture" not in champs, "extraite mais non déclarée : elle reste écartée"
    assert champs[:2] == ["meta:emetteur", "date_document"]
    # les champs *déclarés* par la catégorie, eux, restent visibles
    assert "meta:montant_ttc" in champs


def test_une_regle_ajoutee_apres_coup_apparait_sans_toucher_a_la_configuration(categorie_factures):
    _, factures, _ = categorie_factures
    session = SessionLocal()
    try:
        session.add(ColonneCategorie(categorie_id=factures, champ="meta:emetteur", ordre=0))
        session.add(RegleChampCategorie(categorie_id=factures, champ="meta:mode_paiement",
                                        libelle="Mode de paiement", obligatoire=False, ordre=60))
        session.commit()
        champs = _champs(colonnes.pour_categorie(session, factures))
    finally:
        session.query(ColonneCategorie).delete()
        session.query(RegleChampCategorie).filter_by(
            categorie_id=factures, champ="meta:mode_paiement").delete()
        session.commit()
        session.close()

    assert champs[0] == "meta:emetteur"
    assert "meta:mode_paiement" in champs, \
        "une colonne invisible jusqu'à ce qu'on y repense serait une colonne perdue"


def test_l_api_rend_les_colonnes_de_toutes_les_categories(client, categorie_factures):
    """En une réponse : changer de catégorie ne doit pas coûter un aller-retour."""
    _, factures, _ = categorie_factures
    reponse = client.get("/categories/colonnes")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert "defaut" in corps["colonnes"]
    assert str(factures) in corps["colonnes"]
    assert "date_document" in _champs(corps["colonnes"][str(factures)])
    # le tri d'ouverture voyage avec les colonnes (§18.49) : deux allers-retours
    # pour afficher un tableau, c'est un de trop
    assert corps["tris"]["defaut"]["champ"] == "date_import"
    assert corps["tris"][str(factures)]["sens"] in ("asc", "desc")


def test_l_administrateur_fixe_l_ordre_des_colonnes(client, categorie_factures):
    _, factures, _ = categorie_factures
    reponse = client.put(f"/admin/categories/{factures}/colonnes", json=[
        {"champ": "meta:emetteur"},
        {"champ": "meta:numero_facture", "libelle": "N° facture"},
        {"champ": "date_document", "libelle": "Émise le"},
        {"champ": "meta:montant_ttc"},
        {"champ": "meta:titulaire"},
        {"champ": "statut", "visible": False},
    ])
    assert reponse.status_code == 200, reponse.text
    champs = _champs(reponse.json()["effectives"])
    assert champs[:5] == ["meta:emetteur", "meta:numero_facture", "date_document",
                          "meta:montant_ttc", "meta:titulaire"]
    assert "statut" not in champs

    lecture = client.get(f"/admin/categories/{factures}/colonnes").json()
    assert len(lecture["configurees"]) == 6
    assert any(c["champ"] == "meta:numero_facture" for c in lecture["disponibles"])
    assert any(c["champ"] == "statut" for c in lecture["disponibles"]), \
        "le statut reste proposable, même s'il n'est plus déduit"

    # une liste vide rend la catégorie à ses colonnes déduites : c'est la façon
    # la plus simple de revenir en arrière
    assert client.put(f"/admin/categories/{factures}/colonnes", json=[]).status_code == 200
    apres = _champs(client.get("/categories/colonnes").json()["colonnes"][str(factures)])
    assert "meta:numero_facture" in apres and "statut" not in apres


def test_une_colonne_inconnue_est_refusee(client, categorie_factures):
    _, factures, _ = categorie_factures
    reponse = client.put(f"/admin/categories/{factures}/colonnes",
                         json=[{"champ": "colonne_qui_n_existe_pas"}])
    assert reponse.status_code == 400
    assert client.put(f"/admin/categories/{factures}/colonnes", json=[
        {"champ": "meta:emetteur"}, {"champ": "meta:emetteur"},
    ]).status_code == 400


def test_le_tri_porte_sur_une_metadonnee(client, categorie_factures):
    """
    L'essentiel des colonnes d'une catégorie sont des métadonnées : sans ce tri,
    un clic sur « Montant TTC » ne trierait rien.
    """
    reponse = client.get("/documents", params={"tri": "meta:montant_ttc", "sens": "asc"})
    assert reponse.status_code == 200, reponse.text
    assert client.get("/documents", params={"tri": "meta:"}).status_code == 422


def test_le_tri_douverture_se_regle_par_categorie(client, categorie_factures):
    """
    Le registre s'ouvrait sur un tri écrit en dur. Des factures se lisent par
    date d'émission, des courriers par émetteur : le tri est une propriété de ce
    qu'on regarde, il se règle donc là où se règlent les colonnes.
    """
    _, factures, _ = categorie_factures
    reponse = client.put(f"/admin/categories/{factures}/tri",
                         json={"champ": "date_document", "sens": "asc"})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["tri_effectif"] == {"champ": "date_document", "sens": "asc"}

    tris = client.get("/categories/colonnes").json()["tris"]
    assert tris[str(factures)] == {"champ": "date_document", "sens": "asc"}


def test_un_type_sans_tri_declare_suit_le_reglage_du_foyer(client, categorie_factures):
    """
    Un champ vide ne fixe pas un tri vide : il rend le type au réglage général.
    Plus d'héritage depuis le §19.7 — un dossier ne porte pas de tri, la remontée
    ne trouvait jamais rien et faisait croire à une règle qui n'existait pas.
    """
    _, factures, _ = categorie_factures
    client.put(f"/admin/categories/{factures}/tri", json={"champ": "date_document", "sens": "asc"})
    client.put(f"/admin/categories/{factures}/tri", json={"champ": None, "sens": None})

    tris = client.get("/categories/colonnes").json()["tris"]
    assert tris[str(factures)] == tris["defaut"]


def test_un_tri_sur_une_colonne_inconnue_est_refuse(client, categorie_factures):
    _, factures, _ = categorie_factures
    refus = client.put(f"/admin/categories/{factures}/tri",
                       json={"champ": "colonne_qui_n_existe_pas", "sens": "asc"})
    assert refus.status_code == 400


def test_un_sens_sans_colonne_est_refuse(client, categorie_factures):
    """Il ne trierait rien : mieux vaut le dire que l'enregistrer sans effet."""
    _, factures, _ = categorie_factures
    refus = client.put(f"/admin/categories/{factures}/tri", json={"champ": "", "sens": "asc"})
    assert refus.status_code == 400
    assert "colonne" in refus.json()["detail"].lower()


def test_un_dossier_peut_toujours_perdre_des_colonnes_heritees(client):
    """
    Un dossier ne porte pas de colonnes — mais il a pu en porter avant que la
    nature des catégories n'existe (§19.1). Le refus vaut donc pour ce qu'on
    **pose**, jamais pour ce qu'on **retire** (§22.47) : sans cela, on ne peut ni
    recréer ces colonnes ni s'en débarrasser, et la configuration du foyer cesse
    d'être remontable à la main.
    """
    from app.db import Categorie, ColonneCategorie, SessionLocal

    session = SessionLocal()
    try:
        dossier = session.query(Categorie).filter_by(nom="_DossierHerite").one_or_none()
        if dossier is None:
            dossier = Categorie(nom="_DossierHerite", nature="dossier", ordre=960)
            session.add(dossier)
            session.flush()
        session.query(ColonneCategorie).filter_by(categorie_id=dossier.id).delete()
        session.add(ColonneCategorie(categorie_id=dossier.id, champ="date_document",
                                     libelle="Date", ordre=0, visible=True))
        session.commit()
        identifiant = dossier.id
    finally:
        session.close()

    # Poser reste refusé : un dossier n'affiche aucun tableau.
    refus = client.put(f"/admin/categories/{identifiant}/colonnes",
                       json=[{"champ": "date_document", "libelle": "Date", "ordre": 0,
                              "visible": True}])
    assert refus.status_code == 400

    # Retirer, en revanche, doit toujours être possible.
    assert client.put(f"/admin/categories/{identifiant}/colonnes", json=[]).status_code == 200
    session = SessionLocal()
    try:
        assert session.query(ColonneCategorie).filter_by(categorie_id=identifiant).count() == 0
        session.query(Categorie).filter_by(id=identifiant).delete()
        session.commit()
    finally:
        session.close()


@pytest.fixture
def categorie_muette(base_de_test):
    """Un type qui n'a rien déclaré et dont aucun document ne porte de champ."""
    session = SessionLocal()
    try:
        categorie = Categorie(nom="_ColDiplomes", ordre=983)
        session.add(categorie)
        session.commit()
        identifiant = categorie.id
    finally:
        session.close()

    yield identifiant

    session = SessionLocal()
    try:
        session.query(Categorie).filter_by(nom="_ColDiplomes").delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_on_ne_propose_que_les_champs_du_type(categorie_factures, categorie_muette):
    """
    La liste « Ajouter une colonne » proposait le vocabulaire de **toute** la GED
    (§22.57) : sur un type qui n'a jamais parlé de factures, un numéro de facture.
    Beaucoup d'entrées, aucune qui décrive le document qu'on range.

    Ce que ce type-ci a nommé ou porte réellement, donc — plus les colonnes que
    porte tout document, qui sont les mêmes partout.
    """
    _, factures, _ = categorie_factures
    session = SessionLocal()
    try:
        siennes = _champs(colonnes.champs_proposables(session, factures))
        etrangeres = _champs(colonnes.champs_proposables(session, categorie_muette))
    finally:
        session.close()

    # Ce que le type déclare, et ce que ses documents portent sans être exigés.
    assert "meta:montant_ttc" in siennes
    assert "meta:titulaire" in siennes
    assert "meta:numero_facture" in siennes

    # Le voisin n'en hérite pas : il n'a rien déclaré, rien extrait.
    assert "meta:montant_ttc" not in etrangeres
    assert "meta:numero_facture" not in etrangeres

    # Les colonnes que porte tout document restent proposées partout.
    for champ in ("categorie", "date_document", "date_import", "nom_fichier", "statut"):
        assert champ in etrangeres, champ


def test_une_colonne_deja_reglee_reste_proposee(categorie_muette):
    """
    Restreindre ne doit pas faire disparaître ce qui est **déjà configuré** :
    l'écran s'en sert pour nommer la colonne et pour la retrouver. Une colonne
    posée avant la restriction resterait sinon sans intitulé, et impossible à
    renommer.
    """
    session = SessionLocal()
    try:
        session.add(ColonneCategorie(categorie_id=categorie_muette,
                                     champ="meta:numero_facture", ordre=10))
        session.commit()
        proposes = _champs(colonnes.champs_proposables(session, categorie_muette))
        session.query(ColonneCategorie).filter_by(categorie_id=categorie_muette).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()

    assert "meta:numero_facture" in proposes
