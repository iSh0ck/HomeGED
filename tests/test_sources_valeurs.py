"""
Les sources de valeurs d'un champ personnalisé (§18.13).

Une source est une **table de données du foyer**, et rien d'autre. Les comptes de
connexion l'ont été un temps (§17.27) ; ils ne le sont plus, à la demande de
l'utilisateur et pour une raison qui vaut au-delà de son foyer : `sys_utilisateurs`
n'est pas une table de données, ses colonnes ne se règlent pas depuis
l'administration, et quiconque reprendrait l'application héritait de ce couplage
sans pouvoir y toucher. Les deux notions ne se recouvrent d'ailleurs pas — un
enfant reçoit des factures sans avoir de compte.

Ce qui reste vrai et doit le rester : les tables du système ne sont accessibles
par aucune de ces portes.
"""
from sqlalchemy import text

from app import base_donnees
from app.db import SessionLocal

TABLE = "usr_personnes_test"


def _creer_table(client):
    client.delete(f"/admin/base/tables/{TABLE}")
    cree = client.post("/admin/base/tables", json={
        "nom": "personnes_test", "libelle": "Personnes (test)",
        "colonnes": [{"nom": "nom", "type": "texte"}, {"nom": "prenom", "type": "texte"}],
    })
    assert cree.status_code == 200, cree.text
    regle = client.put(f"/admin/base/tables/{TABLE}", json={
        "colonne_libelle": "nom", "colonnes_identifiantes": "prenom,nom",
    })
    assert regle.status_code == 200, regle.text
    for prenom, nom in (("Camille", "DUPONT"), ("Lucie", "MARTIN")):
        client.post(f"/admin/base/tables/{TABLE}/lignes",
                    json={"valeurs": {"nom": nom, "prenom": prenom}})


def test_les_comptes_ne_sont_plus_proposes_comme_source(client):
    sources = {s["nom"] for s in client.get("/admin/sources-champs").json()}
    assert "sys_utilisateurs" not in sources
    assert all(not s.startswith("sys_") for s in sources), \
        "aucune table du système n'a sa place dans cette liste"


def test_une_table_du_systeme_est_refusee_comme_source(client):
    categorie = client.post("/admin/categories", json={"nom": "_SourceTest"}).json()
    try:
        refus = client.post("/admin/regles-champs", json={
            "categorie_id": categorie["id"], "champ": "meta:titulaire_test",
            "source_table": "sys_utilisateurs", "libelle": "Titulaire", "obligatoire": False,
        })
        assert refus.status_code == 422, refus.text
    finally:
        client.delete(f"/admin/categories/{categorie['id']}")


def test_les_tables_du_systeme_restent_inaccessibles(client):
    """Ni lecture ni écriture par la porte des tables de données."""
    ecriture = client.post("/admin/base/tables/sys_utilisateurs/lignes",
                           json={"valeurs": {"nom": "Intrus"}})
    assert ecriture.status_code in (403, 404, 422)
    assert client.get("/references/sys_utilisateurs").status_code in (403, 404, 422)

    session = SessionLocal()
    try:
        assert base_donnees.est_table_donnees(session, "sys_utilisateurs") is False
    finally:
        session.close()


def test_une_personne_s_affiche_prenom_puis_nom(client):
    """
    « Camille DURAND », et non « DURAND — Camille ». L'ordre vient des colonnes
    identifiantes déclarées pour la table (`prenom,nom`) : rien n'est codé en
    dur, un foyer qui range ses tables autrement obtient l'affichage qui
    correspond à ce qu'il a déclaré.
    """
    _creer_table(client)
    try:
        options = client.get(f"/references/{TABLE}").json()
        libelles = [o["libelle"] for o in options]
        assert "Camille DUPONT" in libelles
        assert not any("—" in l or " - " in l for l in libelles), "ni tiret ni inversion"
        # l'ordre suit le premier champ identifiant : Camille avant Lucie
        assert libelles.index("Camille DUPONT") < libelles.index("Lucie MARTIN")
    finally:
        client.delete(f"/admin/base/tables/{TABLE}")


def test_la_recherche_porte_sur_le_prenom_comme_sur_le_nom(client):
    """On tape « Camille » aussi bien que « DUPONT » : les deux la désignent."""
    _creer_table(client)
    try:
        for motif in ("Camille", "DUPONT"):
            trouves = client.get(f"/references/{TABLE}?recherche={motif}").json()
            assert [o["libelle"] for o in trouves] == ["Camille DUPONT"], motif
    finally:
        client.delete(f"/admin/base/tables/{TABLE}")


def test_la_valeur_choisie_se_relit_a_l_identique(client):
    """
    Le libellé affiché dans le tableau et sur la fiche doit être celui de la
    liste de choix : sinon on doute d'avoir choisi la bonne personne.
    """
    _creer_table(client)
    session = SessionLocal()
    try:
        identifiant = session.execute(
            text(f"SELECT id FROM `{TABLE}` WHERE prenom = 'Camille'")).scalar()
        libelles = base_donnees.libelles_par_id(session, TABLE, {str(identifiant)})
        assert libelles[str(identifiant)] == "Camille DUPONT"
    finally:
        session.close()
        client.delete(f"/admin/base/tables/{TABLE}")


def test_l_affichage_d_une_table_se_regle_depuis_l_administration(client):
    """
    Le fond de la demande : rien ne doit être figé dans le code. L'ordre des
    colonnes identifiantes décide de l'affichage, et il se change ici.
    """
    _creer_table(client)
    try:
        inverse = client.put(f"/admin/base/tables/{TABLE}",
                             json={"colonnes_identifiantes": "nom,prenom"})
        assert inverse.status_code == 200, inverse.text
        libelles = [o["libelle"] for o in client.get(f"/references/{TABLE}").json()]
        assert "DUPONT Camille" in libelles, "l'ordre déclaré est celui qui s'affiche"

        # une colonne qui n'existe pas est refusée : sans ce contrôle, la table
        # deviendrait illisible sans qu'on sache pourquoi
        refus = client.put(f"/admin/base/tables/{TABLE}",
                           json={"colonnes_identifiantes": "prenom,inexistante"})
        assert refus.status_code == 422

        # la table reste lisible : le réglage refusé n'a rien changé
        assert "DUPONT Camille" in [o["libelle"] for o in client.get(f"/references/{TABLE}").json()]
    finally:
        client.delete(f"/admin/base/tables/{TABLE}")
