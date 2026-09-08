"""
Administration de la base : la frontière lecture/écriture et l'absence de SQL
arbitraire sont les garanties de sécurité du §17.
"""
import pytest

from app.base_donnees import OperationRefusee, _verifier_identifiant


@pytest.mark.parametrize("identifiant", [
    "documents; DROP TABLE documents", "documents`", "../etc/passwd", "", "1table", "a" * 60,
])
def test_les_identifiants_dangereux_sont_refuses(identifiant):
    with pytest.raises(OperationRefusee):
        _verifier_identifiant(identifiant, "Nom de table")


def test_un_identifiant_normal_est_accepte():
    assert _verifier_identifiant("usr_vehicules", "Nom de table") == "usr_vehicules"


def test_les_tables_du_systeme_sont_en_lecture_seule(client):
    """Écrire dans `documents` contournerait droits, conformité, audit et fichiers."""
    assert client.get("/admin/base/tables/sys_documents/lignes").status_code == 200
    for methode, route, corps in (
        ("post", "/admin/base/tables/sys_documents/lignes", {"valeurs": {"nom_fichier": "x"}}),
        ("post", "/admin/base/tables/sys_utilisateurs/lignes", {"valeurs": {"est_admin": 1}}),
        ("put", "/admin/base/tables/sys_journal_audit/lignes/1", {"valeurs": {"action": "rien"}}),
    ):
        reponse = getattr(client, methode)(route, json=corps)
        assert reponse.status_code == 422, route
    assert client.delete("/admin/base/tables/sys_documents").status_code == 422


def test_les_colonnes_sensibles_ne_sont_jamais_restituees(client):
    colonnes = client.get("/admin/base/tables/sys_utilisateurs/lignes").json()["colonnes"]
    assert "mot_de_passe_hash" not in colonnes


def test_cycle_complet_sur_une_table_de_donnees(client):
    client.delete("/admin/base/tables/usr_test_auto")
    creation = client.post("/admin/base/tables", json={
        "nom": "test_auto", "libelle": "Test", "description": None,
        "colonnes": [{"nom": "marque", "type": "texte", "obligatoire": True},
                     {"nom": "modele", "type": "texte"}]})
    assert creation.status_code == 200, creation.text
    table = creation.json()["nom_table"]
    assert table == "usr_test_auto"

    ligne = client.post(f"/admin/base/tables/{table}/lignes",
                        json={"valeurs": {"marque": "Renault", "modele": "Clio"}})
    assert ligne.status_code == 200
    ligne_id = ligne.json()["id"]

    assert client.put(f"/admin/base/tables/{table}/lignes/{ligne_id}",
                      json={"valeurs": {"modele": "Clio V"}}).status_code == 200
    contenu = client.get(f"/admin/base/tables/{table}/lignes", params={"recherche": "Clio"}).json()
    assert contenu["total"] == 1 and contenu["lignes"][0]["modele"] == "Clio V"

    # une table de données peut servir de source de valeurs à un champ personnalisé
    options = client.get(f"/references/{table}").json()
    assert options and options[0]["libelle"] == "Renault"

    assert client.delete(f"/admin/base/tables/{table}/lignes/{ligne_id}").status_code == 200
    assert client.delete(f"/admin/base/tables/{table}").status_code == 200


def test_les_tables_du_systeme_ne_sont_pas_des_sources_de_valeurs(client):
    """
    `/references` est ouvert à tout compte connecté : il n'expose que les tables
    de données du foyer, et aucune table du système.

    Les comptes en ont été l'exception un temps (§17.27) ; ils ne le sont plus
    (§18.13). La porte est donc refermée sans exception, ce qui est plus simple
    à tenir : il n'y a plus de liste d'exceptions à surveiller.
    """
    for interdite in ("sys_documents", "sys_journal_audit", "sys_sessions",
                      "sys_utilisateurs", "sys_exports"):
        assert client.get(f"/references/{interdite}").status_code == 404, interdite


def test_un_type_de_colonne_inconnu_est_refuse(client):
    reponse = client.post("/admin/base/tables", json={
        "nom": "test_injection", "libelle": "T",
        "colonnes": [{"nom": "a", "type": "TEXT); DROP TABLE documents;--"}]})
    assert reponse.status_code == 422
