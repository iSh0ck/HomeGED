"""
Export et import de la configuration (§18.26).

Ce que HomeGED sait d'un foyer se range en deux tas : ses documents, et la façon
dont il les range. Le second n'existait que dans la base, sans porte. C'est
pourtant lui qui rend le projet transposable : partir d'un modèle, l'élaguer,
reprendre celui d'un autre.

Ces tests portent autant sur ce qui voyage que sur **ce qui ne doit pas** : ni
comptes, ni documents, ni journal.
"""
import pytest

from app import configuration, modeles
from app.db import (
    Categorie,
    Document,
    RegleChampCategorie,
    RegleExtraction,
    SessionLocal,
    TableDonnees,
    VueEnregistree,
)
from tests.conftest import reconstruire_base


@pytest.fixture
def base_reconstruite(base_de_test):
    """
    Ces tests posent et retirent des configurations entières : ils rendent la
    base comme ils l'ont trouvée, sinon les suivants travaillent sur les restes.
    """
    yield
    reconstruire_base()


def test_l_export_dit_les_liens_par_leur_nom(client):
    """
    Les identifiants n'ont de sens que dans la base qui les a émis : une
    sous-catégorie doit nommer son parent, sans quoi rien ne s'importe ailleurs.
    """
    export = client.get("/admin/configuration").json()
    assert export["format"] == configuration.FORMAT
    assert export["categories"], "l'installation de test sème un classement"
    for entree in export["categories"]:
        assert "id" not in entree
        assert set(entree) >= {"nom", "parent"}
    for entree in export["champs_attendus"]:
        assert isinstance(entree["categorie"], (str, type(None)))


def test_l_export_ne_contient_ni_compte_ni_document(client):
    """
    La configuration voyage, les identités non : importer les comptes d'un autre
    foyer donnerait des accès à des gens qui n'y habitent pas.
    """
    brut = client.get("/admin/configuration").text
    export = client.get("/admin/configuration").json()
    assert "utilisateurs" not in export and "comptes" not in export
    assert "documents" not in export and "journal" not in export
    # Ce qu'on cherche, ce sont des identifiants — une empreinte de mot de passe,
    # une adresse. `longueur_min_mot_de_passe` est une exigence du foyer, pas un
    # secret : la première version de ce test la confondait avec l'un d'eux.
    assert "mot_de_passe_hash" not in brut and "@" not in brut

    # Les rôles voyagent depuis le §19.13 — qui voit quoi fait partie du
    # classement — mais sans personne dedans : ce sont des étiquettes, pas des
    # gens.
    assert "roles" in export
    assert all("utilisateurs" not in role for role in export["roles"])


def test_les_lignes_des_tables_ne_partent_qu_a_la_demande(client):
    """
    Le contenu des tables du foyer (membres, véhicules) est une donnée
    personnelle, pas de la structure : il sort pour un déménagement, pas pour un
    modèle qu'on publie.
    """
    sans = client.get("/admin/configuration").json()
    avec = client.get("/admin/configuration?avec_donnees=true").json()
    assert all(t["lignes"] is None for t in sans["tables_donnees"])
    assert all(isinstance(t["lignes"], list) for t in avec["tables_donnees"])


def test_un_format_plus_recent_est_refuse(client):
    refus = client.post("/admin/configuration/import",
                        json={"configuration": {"format": configuration.FORMAT + 1}})
    assert refus.status_code == 400
    assert "plus récente" in refus.json()["detail"]

    # un fichier qui porte quelque chose mais ne dit pas son format : refusé
    sans_format = client.post("/admin/configuration/import",
                              json={"configuration": {"categories": []}})
    assert sans_format.status_code == 400
    assert "format" in sans_format.json()["detail"]

    # un fichier vide : ce n'est pas un format douteux, c'est rien à importer
    vide = client.post("/admin/configuration/import", json={"configuration": {}})
    assert vide.status_code == 422


def test_importer_complete_sans_rien_ecraser(client, base_reconstruite):
    """Le mode sûr : on essaie un modèle sans rien perdre de ce qu'on avait."""
    avant = client.get("/admin/configuration").json()
    noms_avant = {c["nom"] for c in avant["categories"]}

    bilan = client.post("/admin/configuration/import", json={"modele": "complet"})
    assert bilan.status_code == 200, bilan.text
    resultat = bilan.json()
    assert resultat["erreurs"] == [], resultat["erreurs"]
    assert resultat["categories"] > 0

    apres = {c["nom"] for c in client.get("/admin/configuration").json()["categories"]}
    assert noms_avant <= apres, "aucune catégorie d'origine ne doit disparaître"
    assert "Véhicules" in apres and "Santé" in apres


def test_un_second_import_du_meme_modele_ne_double_rien(client, base_reconstruite):
    """
    Appliquer deux fois le même modèle est un geste banal — on hésite, on
    recommence. Cela ne doit pas créer deux fois « Santé ».
    """
    client.post("/admin/configuration/import", json={"modele": "complet"})
    second = client.post("/admin/configuration/import", json={"modele": "complet"}).json()
    assert second["categories"] == 0
    assert second["jeux_extraction"] == 0
    assert second["tables_donnees"] == 0

    session = SessionLocal()
    try:
        noms = [c.nom for c in session.query(Categorie).all()]
        assert len(noms) == len(set(noms)), "aucune catégorie en double"
    finally:
        session.close()


def test_le_modele_complet_pose_ses_tables_et_leur_affichage(client, base_reconstruite):
    client.post("/admin/configuration/import", json={"modele": "complet"})
    session = SessionLocal()
    try:
        tables = {t.nom_table: t for t in session.query(TableDonnees).all()}
        assert "usr_vehicules" in tables and "usr_contrats" in tables and "usr_biens" in tables
        assert tables["usr_vehicules"].colonnes_identifiantes == "marque,immatriculation"
    finally:
        session.close()

    # et les listes de choix s'en servent réellement
    options = client.get("/references/usr_contrats")
    assert options.status_code == 200


def test_remplacer_est_refuse_quand_des_documents_sont_classes(client, base_reconstruite):
    """Leur classement disparaîtrait sous eux."""
    session = SessionLocal()
    try:
        categorie = session.query(Categorie).first()
        session.add(Document(nom_fichier="_conf.pdf", chemin_stockage="/x.pdf",
                             hash_sha256="conf".ljust(64, "c"), texte_ocr="x",
                             statut="traite", categorie_id=categorie.id if categorie else None))
        session.commit()
    finally:
        session.close()

    refus = client.post("/admin/configuration/import",
                        json={"modele": "essentiel", "remplacer": True})
    assert refus.status_code == 400
    assert "documents" in refus.json()["detail"].lower()


def test_remplacer_repart_de_la_configuration_importee(client, base_reconstruite):
    session = SessionLocal()
    try:
        session.query(Document).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()

    bilan = client.post("/admin/configuration/import",
                        json={"modele": "essentiel", "remplacer": True})
    assert bilan.status_code == 200, bilan.text

    apres = {c["nom"] for c in client.get("/admin/configuration").json()["categories"]}
    assert apres == {"Factures", "Impôts", "Banque", "Courriers"}


def test_un_aller_retour_conserve_la_configuration(client, base_reconstruite):
    """
    Le test qui compte pour un déménagement : ce qui sort doit rentrer à
    l'identique. On repart d'une base vidée de sa configuration, on réapplique
    l'export, et l'on compare ce qui fait le classement.
    """
    client.post("/admin/configuration/import", json={"modele": "complet"})
    export = client.get("/admin/configuration").json()

    session = SessionLocal()
    try:
        session.query(Document).delete(synchronize_session=False)
        session.query(VueEnregistree).delete(synchronize_session=False)
        session.query(RegleChampCategorie).delete(synchronize_session=False)
        session.query(RegleExtraction).delete(synchronize_session=False)
        session.query(Categorie).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()

    bilan = client.post("/admin/configuration/import", json={"configuration": export})
    assert bilan.status_code == 200, bilan.text
    assert bilan.json()["erreurs"] == []

    apres = client.get("/admin/configuration").json()
    comparable = lambda config: (      # noqa: E731 — lisible tel quel
        # l'arborescence, avec ce qui la décrit : nature, dossier de dépôt, tri
        sorted((c["nom"], c["parent"], c["nature"], c["dossier_depot"],
                c["tri_champ"], c["tri_sens"]) for c in config["categories"]),
        # les jeux de règles, et les règles dedans (§19.6)
        sorted((jeu["categorie"], jeu["nom"], jeu["generique"], jeu["reconnaissance"],
                tuple(sorted(r["nom"] for r in jeu["regles"])))
               for jeu in config["jeux_extraction"]),
        # ce qu'un type exige, et ce qu'il déduit tout seul (§18.47)
        sorted((c["categorie"], c["champ"], c["obligatoire"], c["identifiant"],
                c["deduction"], c["colonnes_deduction"])
               for c in config["champs_attendus"]),
        # les colonnes de chaque tableau, dans leur ordre
        sorted((c["categorie"], c["champ"], c["ordre"], c["visible"])
               for c in config["colonnes"]),
        sorted((v["nom"], v["categorie"], v["partagee"]) for v in config["vues"]),
        sorted((t["nom"], t["partage"]) for t in config["tableaux_de_bord"]),
        # qui voit quoi (§19.12) : les rôles, leurs droits, leurs vues réservées
        sorted((r["nom"], tuple(r["generaux"]), tuple(r["vues"]),
                tuple(sorted((d["categorie"], d["peut_voir"], d["peut_modifier"],
                              d["peut_deposer"], d["peut_telecharger"],
                              d["peut_supprimer"], d["peut_gerer_versions"])
                             for d in r["categories"])))
               for r in config["roles"]),
        # les tables du foyer : colonnes, intitulés, liaisons, unicité
        sorted((t["nom_table"], t["colonne_libelle"], t["colonnes_identifiantes"],
                tuple(sorted((c["nom"], c["type"], c["libelle"], c["source_table"])
                             for c in t["colonnes"])),
                tuple(sorted(tuple(cle) for cle in t["cles_uniques"])))
               for t in config["tables_donnees"]),
        config["reglages"],
    )
    assert comparable(apres) == comparable(export)


def test_lexport_emporte_tout_ce_qui_decrit_le_classement(client):
    """
    La tâche différée du §8, tenue au §19.13 : vérifier qu'il ne manque rien.

    Ce test échouera le jour où l'on ajoutera une notion de classement sans
    l'exporter — c'est exactement son rôle, et c'est pourquoi il énumère les
    parties plutôt que de compter.
    """
    from app import configuration, reglages

    export = client.get("/admin/configuration").json()
    attendu = {"format", "genere_le", "categories", "jeux_extraction", "champs_attendus",
               "colonnes", "vues", "roles", "tableaux_de_bord", "tables_donnees",
               "reglages"}
    assert set(export) == attendu

    # Les réglages : tous, sauf ceux qui désignent **cette installation-ci** —
    # son nom, son fuseau, et sa façon de joindre le monde extérieur (§21.10).
    # Un mot de passe SMTP n'a évidemment rien à faire dans un export ; le
    # serveur et l'adresse d'expédition non plus, ils ne se reprennent pas d'un
    # foyer à l'autre. Le mode développeur (§21.14) reste dehors pour une autre
    # raison : il s'arme en connaissance de cause, sur cette installation-ci, et
    # ne doit pas s'allumer tout seul en reprenant la configuration d'un autre.
    dehors = set(reglages.CONNUS) - set(configuration.REGLAGES_EXPORTES)
    # `traitements_simultanes` (§22.41) décrit la **machine** et non le foyer :
    # reprendre celui d'un serveur plus gros mettrait celui-ci à genoux.
    assert dehors == {"nom_foyer", "fuseau_horaire", "mode_developpeur",
                      "courriel_actif", "smtp_serveur", "smtp_port", "smtp_securite",
                      "smtp_compte", "smtp_mot_de_passe", "smtp_expediteur",
                      "adresse_publique", "traitements_simultanes",
                      # La sauvegarde (§22.49) désigne un chemin de disque et un
                      # rythme : cela décrit la machine, pas la façon de ranger.
                      "sauvegarde_active", "sauvegarde_heures", "sauvegarde_dossier",
                      "sauvegarde_garder", "sauvegarde_archives",
                      # Un mot de passe ne s'exporte pas (§22.65) : il ouvre les
                      # papiers du foyer, et le reprendre d'une autre
                      # installation n'aurait aucun sens.
                      "sauvegarde_mot_de_passe",
                      "sauvegarde_alerte_jours"}, \
        "un réglage laissé dehors doit l'être pour une raison écrite"


def test_les_roles_livres_donnent_de_quoi_commencer(client):
    """
    Personne ne doit partir d'une grille vide : c'est en modifiant un rôle qui
    existe qu'on comprend ce que les six actions veulent dire.
    """
    for cle in modeles.MODELES:
        roles = modeles.MODELES[cle]["configuration"]["roles"]
        assert {r["nom"] for r in roles} == {"Lecture seule", "Dépôt et classement",
                                             "Gestion complète"}
        # aucun droit de catégorie : ils dépendent de l'arborescence du foyer,
        # et cocher à sa place reviendrait à décider pour lui
        assert all(r["categories"] == [] for r in roles)


def test_les_modeles_livres_sont_annonces(client):
    liste = client.get("/admin/configuration/modeles").json()
    cles = {m["cle"] for m in liste}
    assert cles == set(modeles.MODELES)
    for modele in liste:
        assert modele["libelle"] and modele["description"]
        assert modele["categories"] > 0


def test_un_modele_inconnu_est_refuse(client):
    assert client.post("/admin/configuration/import",
                       json={"modele": "chateau"}).status_code == 404


def test_un_compte_ordinaire_ne_touche_pas_a_la_configuration(client):
    cree = client.post("/admin/utilisateurs", json={
        "email": "_t_config@homeged.local", "nom": "Petit", "prenom": "Paul",
        "mot_de_passe": "MotDePasse!42", "est_admin": False, "actif": True, "role_ids": [],
    })
    assert cree.status_code == 200, cree.text
    try:
        from fastapi.testclient import TestClient
        from app.api import app
        with TestClient(app) as ordinaire:
            jeton = ordinaire.post("/auth/login", data={
                "username": "_t_config@homeged.local", "password": "MotDePasse!42"}).json()
            ordinaire.headers["Authorization"] = f"Bearer {jeton['access_token']}"
            assert ordinaire.get("/admin/configuration").status_code == 403
            assert ordinaire.post("/admin/configuration/import",
                                  json={"modele": "essentiel"}).status_code == 403
    finally:
        client.delete(f"/admin/utilisateurs/{cree.json()['id']}")


def test_la_configuration_emporte_les_reglages_de_colonnes(client, base_reconstruite):
    """
    Une configuration reprise ailleurs doit garder ses liaisons (§18.32) : sans
    elles, « propriétaire » redeviendrait un texte libre à l'arrivée, et le
    classement perdrait ce qui faisait sa cohérence.
    """
    from app import base_donnees
    from app.db import SessionLocal as Fabrique

    client.delete("/admin/base/tables/usr_flotte_conf")
    client.post("/admin/base/tables", json={
        "nom": "flotte_conf", "libelle": "Flotte (conf)",
        "colonnes": [{"nom": "marque", "type": "texte"},
                     {"nom": "immatriculation", "type": "texte"},
                     {"nom": "proprietaire", "type": "texte"}]})
    client.put("/admin/base/tables/usr_flotte_conf/colonnes/proprietaire/reglage",
               json={"libelle": "Propriétaire", "source_table": "usr_membres"})
    client.put("/admin/base/tables/usr_flotte_conf/unicite",
               json={"colonnes": ["immatriculation"]})

    export = client.get("/admin/configuration").json()
    table = next(t for t in export["tables_donnees"] if t["nom_table"] == "usr_flotte_conf")
    proprietaire = next(c for c in table["colonnes"] if c["nom"] == "proprietaire")
    assert proprietaire["source_table"] == "usr_membres"
    assert proprietaire["libelle"] == "Propriétaire"
    assert ["immatriculation"] in table["cles_uniques"]

    # et la configuration se repose ailleurs à l'identique
    client.delete("/admin/base/tables/usr_flotte_conf")
    bilan = client.post("/admin/configuration/import", json={"configuration": export})
    assert bilan.status_code == 200, bilan.text
    assert bilan.json()["erreurs"] == []

    session = Fabrique()
    try:
        colonnes = {c["nom"]: c for c in base_donnees.colonnes(session, "usr_flotte_conf")}
        assert colonnes["proprietaire"]["source_table"] == "usr_membres"
        assert colonnes["proprietaire"]["libelle"] == "Propriétaire"
        assert colonnes["immatriculation"]["unique"] is True
    finally:
        session.close()
        client.delete("/admin/base/tables/usr_flotte_conf")
