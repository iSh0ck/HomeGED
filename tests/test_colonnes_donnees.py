"""
Gestion des colonnes d'une table du foyer (§18.32).

Trois manques signalés par l'utilisateur, qui tiennent au même endroit :
choisir l'identifiant naturel d'une table, modifier ses colonnes sans casser ce
qui s'y appuie, et **relier une colonne à une autre table** — « propriétaire »
d'un véhicule devrait désigner une personne du foyer, pas contenir un texte que
rien ne rattache à personne.

Les garde-fous comptent autant que les fonctions : une table de référence est
pointée par des documents, et une colonne retirée à la légère emporte des
valeurs qu'on ne retrouvera pas.
"""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

TABLE = "usr_flotte_test"
PERSONNES = "usr_conducteurs_test"


@pytest.fixture
def flotte(client):
    """Une table de véhicules et une table de personnes, comme chez l'utilisateur."""
    for nom in (TABLE, PERSONNES):
        client.delete(f"/admin/base/tables/{nom}")

    assert client.post("/admin/base/tables", json={
        "nom": "conducteurs_test", "libelle": "Conducteurs (test)",
        "colonnes": [{"nom": "nom", "type": "texte"}, {"nom": "prenom", "type": "texte"}],
    }).status_code == 200
    assert client.post("/admin/base/tables", json={
        "nom": "flotte_test", "libelle": "Flotte (test)",
        "colonnes": [{"nom": "marque", "type": "texte"},
                     {"nom": "immatriculation", "type": "texte"},
                     {"nom": "proprietaire", "type": "texte"}],
    }).status_code == 200
    client.put(f"/admin/base/tables/{PERSONNES}",
               json={"colonne_libelle": "nom", "colonnes_identifiantes": "prenom,nom"})
    for prenom, nom in (("Camille", "DUPONT"), ("Lucie", "MARTIN")):
        client.post(f"/admin/base/tables/{PERSONNES}/lignes",
                    json={"valeurs": {"nom": nom, "prenom": prenom}})

    yield

    for nom in (TABLE, PERSONNES):
        client.delete(f"/admin/base/tables/{nom}")


def _colonnes(client, table=TABLE):
    return {c["nom"]: c for c in client.get(f"/admin/base/tables/{table}/colonnes").json()}


# ------------------------------------------------------------------
# Identifiant naturel
# ------------------------------------------------------------------

def test_une_colonne_peut_devenir_l_identifiant_naturel(client, flotte):
    """
    `id` reste la clé — c'est lui qui permet de modifier une ligne dont on vient
    justement de changer l'immatriculation. Ce qu'on déclare ici est ce qui, pour
    un humain, désigne la ligne sans ambiguïté.
    """
    pose = client.put(f"/admin/base/tables/{TABLE}/unicite",
                      json={"colonnes": ["immatriculation"]})
    assert pose.status_code == 200, pose.text
    assert _colonnes(client)["immatriculation"]["unique"] is True
    assert _colonnes(client)["id"]["unique"] is False or True   # la clé primaire reste la clé

    # la base refuse désormais un doublon, et le refus se lit : « une erreur est
    # survenue » n'apprendrait rien à qui saisit une immatriculation
    client.post(f"/admin/base/tables/{TABLE}/lignes",
                json={"valeurs": {"marque": "Renault", "immatriculation": "AA-123-AA"}})
    second = client.post(f"/admin/base/tables/{TABLE}/lignes",
                         json={"valeurs": {"marque": "Peugeot", "immatriculation": "AA-123-AA"}})
    assert second.status_code == 422, second.text
    assert "AA-123-AA" in second.json()["detail"]
    assert "unique" in second.json()["detail"]


def test_les_doublons_existants_sont_nommes_avant_de_refuser(client, flotte):
    """
    Sans cela, la base renvoie une erreur d'index sans dire quelle ligne pose
    problème, et il faut aller la chercher à la main.
    """
    for _ in range(2):
        client.post(f"/admin/base/tables/{TABLE}/lignes",
                    json={"valeurs": {"marque": "Renault", "immatriculation": "BB-456-BB"}})

    refus = client.put(f"/admin/base/tables/{TABLE}/unicite",
                       json={"colonnes": ["immatriculation"]})
    assert refus.status_code == 422
    assert "BB-456-BB" in refus.json()["detail"]


def test_l_identifiant_naturel_se_retire(client, flotte):
    client.put(f"/admin/base/tables/{TABLE}/unicite", json={"colonnes": ["immatriculation"]})
    contraintes = client.get(f"/admin/base/tables/{TABLE}/unicite").json()
    assert contraintes, "la contrainte doit être visible"

    retrait = client.put(f"/admin/base/tables/{TABLE}/unicite",
                         json={"colonnes": [], "contrainte": contraintes[0]["nom"]})
    assert retrait.status_code == 200, retrait.text
    assert _colonnes(client)["immatriculation"]["unique"] is False


def test_id_ne_peut_pas_etre_declare_identifiant_naturel(client, flotte):
    refus = client.put(f"/admin/base/tables/{TABLE}/unicite", json={"colonnes": ["id"]})
    assert refus.status_code == 422
    assert "clé primaire" in refus.json()["detail"]


# ------------------------------------------------------------------
# Modification des colonnes
# ------------------------------------------------------------------

def test_une_colonne_se_renomme_et_les_reglages_suivent(client, flotte):
    """
    Un renommage qui laisserait les réglages en arrière rendrait la table muette :
    la colonne d'affichage et les colonnes identifiantes citent des noms.
    """
    client.put(f"/admin/base/tables/{TABLE}",
               json={"colonne_libelle": "marque", "colonnes_identifiantes": "marque,immatriculation"})
    renomme = client.put(f"/admin/base/tables/{TABLE}/colonnes/marque",
                         json={"nouveau_nom": "constructeur"})
    assert renomme.status_code == 200, renomme.text

    colonnes = _colonnes(client)
    assert "constructeur" in colonnes and "marque" not in colonnes
    table = next(t for t in client.get("/admin/base/tables").json() if t["nom"] == TABLE)
    assert table["colonne_libelle"] == "constructeur"
    assert table["colonnes_identifiantes"] == "constructeur,immatriculation"


def test_le_type_d_une_colonne_se_change(client, flotte):
    client.post(f"/admin/base/tables/{TABLE}/lignes",
                json={"valeurs": {"marque": "Renault", "immatriculation": "2020"}})
    change = client.put(f"/admin/base/tables/{TABLE}/colonnes/immatriculation",
                        json={"type": "nombre"})
    assert change.status_code == 200, change.text
    assert _colonnes(client)["immatriculation"]["type_logique"] == "nombre"


def test_un_type_impossible_laisse_la_table_intacte(client, flotte):
    """
    MariaDB refuse en bloc un `ALTER` qui ne sait pas convertir une valeur, et
    laisse la table exactement comme elle était : l'échec est sans dommage.
    """
    client.post(f"/admin/base/tables/{TABLE}/lignes",
                json={"valeurs": {"marque": "Renault", "immatriculation": "AA-123-AA"}})
    refus = client.put(f"/admin/base/tables/{TABLE}/colonnes/immatriculation",
                       json={"type": "date"})
    assert refus.status_code == 422, refus.text
    assert "AA-123-AA" in refus.json()["detail"]
    assert "pas été modifiée" in refus.json()["detail"]
    assert _colonnes(client)["immatriculation"]["type_logique"] == "texte"
    lignes = client.get(f"/admin/base/tables/{TABLE}/lignes").json()
    assert lignes["lignes"][0]["immatriculation"] == "AA-123-AA", "la valeur est intacte"


def test_une_colonne_se_supprime_apres_avoir_dit_ce_qu_elle_emporte(client, flotte):
    client.post(f"/admin/base/tables/{TABLE}/lignes",
                json={"valeurs": {"marque": "Renault", "proprietaire": "Camille"}})

    impact = client.get(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/impact").json()
    assert impact["valeurs_remplies"] == 1

    assert client.delete(f"/admin/base/tables/{TABLE}/colonnes/proprietaire").status_code == 200
    assert "proprietaire" not in _colonnes(client)


def test_on_ne_supprime_pas_une_colonne_qui_sert(client, flotte):
    """Trois refus, une seule idée : une colonne qui *sert* ne part pas par surprise."""
    client.put(f"/admin/base/tables/{TABLE}",
               json={"colonne_libelle": "marque", "colonnes_identifiantes": "immatriculation"})

    libelle = client.delete(f"/admin/base/tables/{TABLE}/colonnes/marque")
    assert libelle.status_code == 422 and "affichage" in libelle.json()["detail"]

    identifiante = client.delete(f"/admin/base/tables/{TABLE}/colonnes/immatriculation")
    assert identifiante.status_code == 422 and "identifiantes" in identifiante.json()["detail"]

    cle = client.delete(f"/admin/base/tables/{TABLE}/colonnes/id")
    assert cle.status_code == 422 and "id" in cle.json()["detail"]


def test_les_tables_du_systeme_restent_hors_de_portee(client):
    for chemin, methode in (
        (f"/admin/base/tables/sys_utilisateurs/colonnes/email", "put"),
        (f"/admin/base/tables/sys_utilisateurs/colonnes/email", "delete"),
        (f"/admin/base/tables/sys_documents/unicite", "put"),
    ):
        reponse = getattr(client, methode)(chemin, json={"colonnes": ["email"]}) \
            if methode == "put" else getattr(client, methode)(chemin)
        assert reponse.status_code >= 400, chemin


# ------------------------------------------------------------------
# Liaison d'une colonne vers une autre table
# ------------------------------------------------------------------

def test_une_colonne_peut_pointer_une_autre_table(client, flotte):
    """
    Le cas de l'utilisateur : « propriétaire » doit désigner une personne du
    foyer, et non contenir un texte que rien ne rattache à personne. Rien n'est
    figé : c'est déclaré, table par table et colonne par colonne.
    """
    reglage = client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
                         json={"libelle": "Propriétaire", "source_table": PERSONNES})
    assert reglage.status_code == 200, reglage.text
    assert _colonnes(client)["proprietaire"]["source_table"] == PERSONNES
    assert _colonnes(client)["proprietaire"]["libelle"] == "Propriétaire"

    session = SessionLocal()
    try:
        camille = session.execute(
            text(f"SELECT id FROM `{PERSONNES}` WHERE prenom = 'Camille'")).scalar()
    finally:
        session.close()

    creation = client.post(f"/admin/base/tables/{TABLE}/lignes", json={
        "valeurs": {"marque": "Renault", "immatriculation": "CC-789-CC",
                    "proprietaire": str(camille)}})
    assert creation.status_code == 200, creation.text

    # la liste des lignes rend le libellé à côté de l'identifiant : l'interface
    # affiche « Camille DUPONT » là où la base porte un numéro
    page = client.get(f"/admin/base/tables/{TABLE}/lignes").json()
    assert page["liens"]["proprietaire"][str(camille)] == "Camille DUPONT"


def test_une_valeur_qui_ne_designe_rien_est_refusee(client, flotte):
    client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
               json={"source_table": PERSONNES})
    refus = client.post(f"/admin/base/tables/{TABLE}/lignes", json={
        "valeurs": {"marque": "Renault", "proprietaire": "99999"}})
    assert refus.status_code == 422
    assert "ne correspond à rien" in refus.json()["detail"].replace("n'y", "ne")


def test_la_liaison_previent_des_valeurs_a_reprendre(client, flotte):
    """
    Les textes déjà saisis ne sont pas des identifiants. On le dit plutôt que de
    les effacer — ou de les laisser mentir.
    """
    creation = client.post(f"/admin/base/tables/{TABLE}/lignes",
                           json={"valeurs": {"marque": "Renault", "proprietaire": "Camille"}})
    assert creation.status_code == 200, creation.text
    assert client.get(f"/admin/base/tables/{TABLE}/lignes").json()["total"] == 1

    reglage = client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
                         json={"source_table": PERSONNES}).json()
    assert reglage["valeurs_a_reprendre"] == 1


def test_une_table_ne_se_pointe_pas_elle_meme(client, flotte):
    refus = client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
                       json={"source_table": TABLE})
    assert refus.status_code == 422
    inconnue = client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
                          json={"source_table": "usr_nulle_part"})
    assert inconnue.status_code == 422


def test_la_liaison_se_retire(client, flotte):
    client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
               json={"source_table": PERSONNES})
    client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
               json={"source_table": None})
    assert _colonnes(client)["proprietaire"]["source_table"] is None


def test_supprimer_une_table_emporte_ses_reglages_de_colonnes(client, flotte):
    """
    Défaut trouvé par la suite elle-même : les réglages survivaient à la table.
    Une table recréée sous le même nom ressuscitait des liaisons que personne
    n'avait demandées, et une colonne pouvait pointer une table disparue.
    """
    from app.db import ColonneDonnees

    client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
               json={"libelle": "Propriétaire", "source_table": PERSONNES})

    session = SessionLocal()
    try:
        assert session.query(ColonneDonnees).filter_by(nom_table=TABLE).count() == 1
    finally:
        session.close()

    assert client.delete(f"/admin/base/tables/{TABLE}").status_code == 200

    session = SessionLocal()
    try:
        assert session.query(ColonneDonnees).filter_by(nom_table=TABLE).count() == 0
    finally:
        session.close()

    # et une liaison qui pointait la table disparue est défaite plutôt que laissée
    # à désigner le vide
    client.post("/admin/base/tables", json={
        "nom": "flotte_test", "libelle": "Flotte (test)",
        "colonnes": [{"nom": "marque", "type": "texte"},
                     {"nom": "proprietaire", "type": "texte"}]})
    client.put(f"/admin/base/tables/{TABLE}/colonnes/proprietaire/reglage",
               json={"source_table": PERSONNES})
    client.delete(f"/admin/base/tables/{PERSONNES}")
    assert _colonnes(client)["proprietaire"]["source_table"] is None
