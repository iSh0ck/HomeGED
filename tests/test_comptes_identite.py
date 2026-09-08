"""
Identité des comptes : prénom et nom (§17.20).

Les comptes n'avaient qu'un champ « nom » libre. Le prénom est désormais un
champ à part, et les deux sont exigés des comptes du foyer — ce sont eux qui
permettent de reconnaître une personne, et de rapprocher un document d'elle.

Un administrateur en est dispensé : c'est un rôle de gestion, pas un membre du
foyer, et son adresse suffit à le désigner.
"""
import pytest


def _payload(**modifications):
    base = {
        "email": "_t_identite@homeged.local", "mot_de_passe": "MotDePasse!42",
        "est_admin": False, "actif": True, "role_ids": [],
    }
    base.update(modifications)
    return base


@pytest.fixture(autouse=True)
def _nettoyer(client):
    def purger():
        for u in client.get("/admin/utilisateurs").json():
            if u["email"].startswith("_t_identite"):
                client.delete(f"/admin/utilisateurs/{u['id']}")
    purger()
    yield
    purger()


def test_un_compte_du_foyer_exige_prenom_et_nom(client):
    sans_prenom = client.post("/admin/utilisateurs", json=_payload(nom="Martin"))
    assert sans_prenom.status_code == 422
    assert "prénom" in sans_prenom.json()["detail"]

    sans_nom = client.post("/admin/utilisateurs", json=_payload(prenom="Marie"))
    assert sans_nom.status_code == 422
    assert "nom" in sans_nom.json()["detail"]

    complet = client.post("/admin/utilisateurs", json=_payload(nom="Martin", prenom="Marie"))
    assert complet.status_code == 200, complet.text
    assert complet.json()["nom_affiche"] == "Marie Martin"


def test_un_administrateur_peut_se_passer_des_deux(client):
    """Un rôle de gestion n'a pas à décliner une identité civile pour exister."""
    reponse = client.post("/admin/utilisateurs", json=_payload(est_admin=True))
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["nom"] is None and corps["prenom"] is None
    # …mais il reste identifiable à l'écran
    assert corps["nom_affiche"] == "_t_identite@homeged.local"


def test_la_regle_vaut_aussi_a_la_modification(client):
    cree = client.post("/admin/utilisateurs", json=_payload(nom="Martin", prenom="Marie"))
    identifiant = cree.json()["id"]

    vide = client.put(f"/admin/utilisateurs/{identifiant}", json=_payload(nom="Martin", prenom=""))
    assert vide.status_code == 422, "on ne doit pas pouvoir retirer le prénom après coup"

    promu = client.put(f"/admin/utilisateurs/{identifiant}",
                       json=_payload(est_admin=True, nom="", prenom=""))
    assert promu.status_code == 200, "un compte devenu administrateur peut s'en passer"


def test_les_espaces_seuls_ne_valent_pas_une_identite(client):
    reponse = client.post("/admin/utilisateurs", json=_payload(nom="   ", prenom="Marie"))
    assert reponse.status_code == 422


def test_les_lignes_par_page_du_compte_priment_sur_le_foyer(client):
    """
    Le foyer donne le nombre de départ, le compte le remplace (§22.44) : cinquante
    lignes tiennent sur un grand écran et débordent sur un portable. Zéro rend la
    main au réglage du foyer — il faut pouvoir revenir au défaut sans deviner le
    nombre qu'il porte.
    """
    assert client.get("/moi").json()["lignes_par_page"] is None

    reponse = client.put("/moi/preferences", json={"lignes_par_page": 100})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["lignes_par_page"] == 100
    assert client.get("/moi").json()["lignes_par_page"] == 100

    # Un nombre qui n'est pas proposé est refusé, et non arrondi en silence.
    assert client.put("/moi/preferences", json={"lignes_par_page": 77}).status_code == 422

    # Zéro remet le compte à la suite du foyer.
    assert client.put("/moi/preferences", json={"lignes_par_page": 0}).json()[
        "lignes_par_page"] is None
