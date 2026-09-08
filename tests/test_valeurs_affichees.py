"""
Ce qui se lit d'une ligne de table, champ par champ (§22.59).

Une table déclare ses colonnes identifiantes, et c'est ce qui composait
l'affichage partout. Un réglage unique par table, donc — alors que le même
véhicule se lit « AA-123-BB » sous « Véhicule concerné » et
« Clio III · AA-123-BB » dans un sélecteur où l'on cherche la bonne voiture.

Le choix appartient désormais au champ. Rien de déclaré veut dire « comme la
table le dit » : c'est l'état de tout champ existant, et rien ne devait changer
pour eux.
"""
import pytest

TABLE = "usr_vehicules_test"


@pytest.fixture
def voitures(client):
    """Une table à deux colonnes, dont une seule identifie la ligne."""
    client.delete(f"/admin/base/tables/{TABLE}")
    cree = client.post("/admin/base/tables", json={
        "nom": "vehicules_test", "libelle": "Véhicules (test)",
        "colonnes": [{"nom": "immatriculation", "type": "texte"},
                     {"nom": "modele", "type": "texte"}],
    })
    assert cree.status_code == 200, cree.text
    reglage = client.put(f"/admin/base/tables/{TABLE}", json={
        "colonne_libelle": "immatriculation",
        "colonnes_identifiantes": "immatriculation",
    })
    assert reglage.status_code == 200, reglage.text
    client.post(f"/admin/base/tables/{TABLE}/lignes",
                json={"valeurs": {"immatriculation": "AA-123-BB", "modele": "Clio III"}})

    # Une **fiche simple** : c'est là qu'une entrée se saisit à la main (§19.1),
    # et c'est là que le choix de ce qui se montre a lieu.
    categorie = client.post("/admin/categories",
                            json={"nom": "_AffichageTest", "nature": "fiche"}).json()
    yield categorie
    client.delete(f"/admin/categories/{categorie['id']}")
    client.delete(f"/admin/base/tables/{TABLE}")


def _regle(client, categorie, **extra):
    reponse = client.post("/admin/regles-champs", json={
        "categorie_id": categorie["id"], "champ": "meta:vehicule_test",
        "source_table": TABLE, "libelle": "Véhicule", "obligatoire": False, **extra,
    })
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_sans_choix_la_table_decide(client, voitures):
    """L'état de tout champ existant : rien ne change pour lui."""
    regle = _regle(client, voitures)
    assert regle["colonnes_affichees"] == []

    options = client.get(f"/references/{TABLE}?categorie_id={voitures['id']}"
                         "&champ=meta:vehicule_test").json()
    assert [o["libelle"] for o in options] == ["AA-123-BB"]


def test_le_champ_choisit_ce_qui_se_lit(client, voitures):
    regle = _regle(client, voitures, colonnes_affichees=["modele", "immatriculation"])
    assert regle["colonnes_affichees"] == ["modele", "immatriculation"]

    options = client.get(f"/references/{TABLE}?categorie_id={voitures['id']}"
                         "&champ=meta:vehicule_test").json()
    # Un tiret, et non une espace (§22.60) : ce ne sont pas les morceaux d'un
    # nom mais deux renseignements côte à côte.
    assert [o["libelle"] for o in options] == ["Clio III - AA-123-BB"]


def test_sans_contexte_la_table_decide_encore(client, voitures):
    """
    Le choix se lit sur la règle, jamais dans la requête : un appelant ne désigne
    pas les colonnes qu'il veut voir.
    """
    _regle(client, voitures, colonnes_affichees=["modele"])
    options = client.get(f"/references/{TABLE}").json()
    assert [o["libelle"] for o in options] == ["AA-123-BB"]


def test_une_colonne_inconnue_est_refusee(client, voitures):
    """Refusée plutôt qu'ignorée : un réglage qui ne fait rien se cherche longtemps."""
    refus = client.post("/admin/regles-champs", json={
        "categorie_id": voitures["id"], "champ": "meta:vehicule_test",
        "source_table": TABLE, "libelle": "Véhicule", "obligatoire": False,
        "colonnes_affichees": ["couleur"],
    })
    assert refus.status_code == 400, refus.text
    assert "couleur" in refus.json()["detail"]


def test_une_colonne_disparue_ne_vide_pas_l_affichage(client, voitures):
    """
    Une colonne supprimée de la table ne doit pas laisser un « Ligne nº7 » :
    on retombe sur ce que la table déclare.
    """
    regle = _regle(client, voitures, colonnes_affichees=["modele"])
    retrait = client.delete(f"/admin/base/tables/{TABLE}/colonnes/modele")
    assert retrait.status_code == 200, retrait.text

    options = client.get(f"/references/{TABLE}?categorie_id={voitures['id']}"
                         f"&champ={regle['champ']}").json()
    assert [o["libelle"] for o in options] == ["AA-123-BB"]


def test_les_colonnes_identifiantes_composent_toujours_un_nom(client):
    """
    Le tiret est réservé au choix d'un champ. Les colonnes identifiantes d'une
    table composent un nom — « Camille DURAND » —, et un tiret y serait une
    faute de français (§22.60).
    """
    table = "usr_personnes_affichage"
    client.delete(f"/admin/base/tables/{table}")
    try:
        cree = client.post("/admin/base/tables", json={
            "nom": "personnes_affichage", "libelle": "Personnes (affichage)",
            "colonnes": [{"nom": "prenom", "type": "texte"}, {"nom": "nom", "type": "texte"}],
        })
        assert cree.status_code == 200, cree.text
        client.put(f"/admin/base/tables/{table}", json={
            "colonne_libelle": "nom", "colonnes_identifiantes": "prenom,nom"})
        client.post(f"/admin/base/tables/{table}/lignes",
                    json={"valeurs": {"prenom": "Camille", "nom": "DURAND"}})

        options = client.get(f"/references/{table}").json()
        assert [o["libelle"] for o in options] == ["Camille DURAND"]
    finally:
        client.delete(f"/admin/base/tables/{table}")


def _entree(client, categorie, valeur, affichages=None):
    reponse = client.post("/documents", json={
        "categorie_id": categorie["id"],
        "valeurs": {"meta:vehicule_test": valeur},
        "affichages": affichages or {},
    })
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_l_entree_retient_ce_qui_merite_une_colonne(client, voitures):
    """
    Trois niveaux (§22.61) : la table déclare, le champ compose, l'entrée
    retient. Le modèle éclaire une ligne et encombre la suivante — c'est un
    jugement de celui qui saisit, pas un réglage de foyer.
    """
    _regle(client, voitures, colonnes_affichees=["modele", "immatriculation"],
           obligatoire=False)

    complete = _entree(client, voitures, "usr_vehicules_test:1")
    brieve = _entree(client, voitures, "usr_vehicules_test:1",
                     affichages={"meta:vehicule_test": ["immatriculation"]})

    assert complete["libelles_references"]["vehicule_test"] == "Clio III - AA-123-BB"
    assert brieve["libelles_references"]["vehicule_test"] == "AA-123-BB"


def test_l_entree_ne_deborde_pas_la_palette(client, voitures):
    """
    Un choix hors de ce que le champ propose serait un réglage qui ne fait rien.
    On retombe sur la composition du champ.
    """
    _regle(client, voitures, colonnes_affichees=["immatriculation"], obligatoire=False)
    entree = _entree(client, voitures, "usr_vehicules_test:1",
                     affichages={"meta:vehicule_test": ["modele"]})
    assert entree["libelles_references"]["vehicule_test"] == "AA-123-BB"
    assert entree["affichages"] == {}


def test_le_choix_de_l_entree_se_relit_et_se_defait(client, voitures):
    _regle(client, voitures, colonnes_affichees=["modele", "immatriculation"],
           obligatoire=False)
    entree = _entree(client, voitures, "usr_vehicules_test:1",
                     affichages={"meta:vehicule_test": ["immatriculation"]})
    assert entree["affichages"] == {"meta:vehicule_test": ["immatriculation"]}

    # Retenir toute la palette, c'est n'avoir rien à dire : la ligne s'efface.
    revenu = client.patch(f"/documents/{entree['id']}", json={
        "affichages": {"meta:vehicule_test": ["modele", "immatriculation"]}})
    assert revenu.status_code == 200, revenu.text
    assert revenu.json()["affichages"] == {}
    relu = client.get(f"/documents/{entree['id']}").json()
    assert relu["libelles_references"]["vehicule_test"] == "Clio III - AA-123-BB"


def test_une_entree_nommee_par_une_reference(client, voitures):
    """
    `_nom_dune_entree` appelait une fonction qui n'existait nulle part (§22.61) :
    créer une entrée dont l'un des deux premiers champs remplis pointe une table
    tombait en 500. Elle porte maintenant le libellé de la ligne, composé comme
    partout ailleurs.
    """
    _regle(client, voitures, colonnes_affichees=["modele", "immatriculation"],
           obligatoire=False)
    entree = _entree(client, voitures, "usr_vehicules_test:1")
    assert entree["nom_fichier"] == "Clio III - AA-123-BB"
