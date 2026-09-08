"""
Dossiers de dépôt, un par type de document (§19.2).

Le classement cesse d'être deviné pour devenir déclaré : celui qui dépose choisit
le dossier. Ces tests portent sur ce qui rend ce dossier fiable — un nom qu'on
peut taper, jamais deux types au même endroit, et surtout : rien de ce qui
attendait ne doit se perdre quand la configuration change.
"""
import pytest

from app import categories as natures, config, depots
from app.db import Categorie, SessionLocal


@pytest.fixture
def racine_de_depot(tmp_path, monkeypatch):
    """Une arborescence de dépôt à soi : les tests n'écrivent pas dans /data."""
    dossier = tmp_path / "ocr_wait"
    monkeypatch.setattr(config, "OCR_WAIT_FOLDER", str(dossier))
    return dossier


@pytest.fixture
def types(base_de_test):
    session = SessionLocal()
    try:
        session.query(Categorie).filter(Categorie.nom.like("_Dep%")).delete(
            synchronize_session=False)
        dossier = Categorie(nom="_DepMaison", nature=natures.DOSSIER, ordre=930)
        session.add(dossier)
        session.flush()
        facture = Categorie(nom="_DepRelevés bancaires", nature=natures.TYPE,
                            parent_id=dossier.id, ordre=931)
        session.add(facture)
        session.commit()
        contexte = {"dossier": dossier.id, "type": facture.id}
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(Categorie).filter(Categorie.nom.like("_Dep%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_le_nom_du_dossier_se_tape_sans_accent_ni_majuscule():
    """Ce nom voyage dans un chemin, un scanner et un partage réseau."""
    assert depots.normaliser("Relevés bancaires") == "releves_bancaires"
    assert depots.normaliser("Impôts / Taxe foncière") == "impots_taxe_fonciere"
    assert depots.normaliser("  Factures  ") == "factures"


def test_un_nom_sans_lettre_ni_chiffre_est_refuse():
    """Il donnerait un dossier sans nom, que personne ne saurait désigner."""
    with pytest.raises(depots.DepotRefuse):
        depots.valider("///")


def test_deux_types_ne_visent_jamais_le_meme_dossier(types, racine_de_depot):
    """
    Un dépôt ambigu est exactement ce que la phase supprime. Plutôt que de
    refuser un homonyme — ce qui obligerait à deviner quels noms sont libres —
    on propose le suivant.
    """
    session = SessionLocal()
    try:
        premier = session.get(Categorie, types["type"])
        depots.attribuer(session, premier)
        session.flush()
        assert premier.dossier_depot == "depreleves_bancaires"

        jumeau = Categorie(nom=premier.nom, nature=natures.TYPE, ordre=932)
        session.add(jumeau)
        session.flush()
        depots.attribuer(session, jumeau)
        assert jumeau.dossier_depot != premier.dossier_depot
        assert jumeau.dossier_depot.endswith("_2")
    finally:
        session.rollback()
        session.close()


def test_un_dossier_de_classement_na_pas_de_depot(types, racine_de_depot):
    """Il ne reçoit aucun document : lui donner un dossier inviterait à s'y tromper."""
    session = SessionLocal()
    try:
        dossier = session.get(Categorie, types["dossier"])
        assert depots.attribuer(session, dossier) is None
        assert dossier.dossier_depot is None
    finally:
        session.rollback()
        session.close()


def test_la_synchronisation_cree_ce_qui_manque(types, racine_de_depot):
    session = SessionLocal()
    try:
        bilan = depots.synchroniser(session)
        assert bilan["attribues"] >= 1
        nom = session.get(Categorie, types["type"]).dossier_depot
    finally:
        session.close()

    assert (racine_de_depot / nom).is_dir()
    assert not (racine_de_depot / "_depmaison").exists(), \
        "un dossier de classement ne doit pas apparaître dans le dépôt"


def test_la_synchronisation_rattrape_un_dossier_efface_a_la_main(types, racine_de_depot):
    session = SessionLocal()
    try:
        depots.synchroniser(session)
        nom = session.get(Categorie, types["type"]).dossier_depot
    finally:
        session.close()

    (racine_de_depot / nom).rmdir()
    session = SessionLocal()
    try:
        assert depots.synchroniser(session)["crees"] == 1
    finally:
        session.close()
    assert (racine_de_depot / nom).is_dir()


def test_renommer_un_dossier_emporte_ce_qui_attendait(racine_de_depot):
    """
    Le point qui compte : sans le déplacement, un fichier déposé la veille ne
    serait plus jamais lu — il resterait dans un dossier que plus personne ne
    regarde.
    """
    depots.creer("factures")
    (racine_de_depot / "factures" / "edf.pdf").write_bytes(b"%PDF")

    depots.renommer("factures", "factures_energie")

    assert (racine_de_depot / "factures_energie" / "edf.pdf").is_file()
    assert not (racine_de_depot / "factures").exists()


def test_un_renommage_nefface_pas_ce_quon_na_pas_mis_la(racine_de_depot):
    """
    Un sous-dossier créé à la main n'a rien à faire là (§19.5 le signalera), mais
    le détruire au passage serait pire : on ne sait pas ce qu'il contient.
    """
    depots.creer("factures")
    (racine_de_depot / "factures" / "a_trier").mkdir()

    depots.renommer("factures", "factures_2026")

    assert (racine_de_depot / "factures_2026").is_dir()
    assert (racine_de_depot / "factures" / "a_trier").is_dir()


def test_le_type_se_deduit_du_dossier_ou_le_fichier_se_trouve(types, racine_de_depot):
    """
    C'est ce que le §19.3 lira à l'arrivée d'un fichier. Ici, seule la lecture du
    chemin est vérifiée : à la racine ou dans un dossier inconnu, personne ne le
    revendique.
    """
    session = SessionLocal()
    try:
        depots.synchroniser(session)
        nom = session.get(Categorie, types["type"]).dossier_depot

        depose = racine_de_depot / nom / "releve.pdf"
        depose.write_bytes(b"%PDF")
        assert depots.type_du_chemin(session, depose).id == types["type"]

        a_la_racine = racine_de_depot / "perdu.pdf"
        a_la_racine.write_bytes(b"%PDF")
        assert depots.type_du_chemin(session, a_la_racine) is None

        inconnu = racine_de_depot / "cree_a_la_main"
        inconnu.mkdir()
        (inconnu / "x.pdf").write_bytes(b"%PDF")
        assert depots.type_du_chemin(session, inconnu / "x.pdf") is None
    finally:
        session.close()


def test_un_dossier_cree_est_immediatement_utilisable(tmp_path, monkeypatch):
    """
    Les droits sont posés à la création, pas seulement à la synchronisation
    (§21.11).

    Un dossier créé par l'API héritait du masque du processus — 0755, propriété
    de root — et personne ne pouvait y déposer : on l'ouvrait, on y glissait un
    fichier, le système refusait, et il fallait attendre le passage d'entretien du
    serveur de travaux pour qu'il devienne utilisable. Un dossier de dépôt
    inutilisable ne vaut pas mieux qu'un dossier absent.
    """
    import os

    from app import config, depots

    monkeypatch.setattr(config, "OCR_WAIT_FOLDER", str(tmp_path / "ocr_wait"))
    assert depots.creer("contrats_travail") is True

    mode = os.stat(depots.chemin("contrats_travail")).st_mode & 0o7777
    assert mode == depots.DROITS_DOSSIER, \
        "chacun doit pouvoir y déposer, personne effacer le dépôt d'un autre"


def test_les_droits_se_reposent_sur_un_dossier_deja_la(tmp_path, monkeypatch):
    """Un dossier recréé à la main entre-temps retrouve ses droits."""
    import os

    from app import config, depots

    monkeypatch.setattr(config, "OCR_WAIT_FOLDER", str(tmp_path / "ocr_wait"))
    depots.creer("factures")
    os.chmod(depots.chemin("factures"), 0o700)

    assert depots.creer("factures") is False, "il existait déjà"
    assert os.stat(depots.chemin("factures")).st_mode & 0o7777 == depots.DROITS_DOSSIER


def test_le_dossier_de_depot_part_avec_le_type(client, tmp_path, monkeypatch):
    """
    Un dossier laissé en place après la suppression du type a l'air d'un point
    d'entrée vivant (§22.88). Ce qu'on y dépose finit au Centre d'analyse, sans
    classement, et l'on cherche pourquoi.
    """
    from app import depots

    monkeypatch.setattr(depots, "racine", lambda: tmp_path)
    categorie = client.post("/admin/categories",
                            json={"nom": "_DepotJetable", "nature": "type"}).json()
    dossier = depots.chemin(categorie["dossier_depot"])
    dossier.mkdir(parents=True, exist_ok=True)
    assert dossier.is_dir()

    reponse = client.delete(f"/admin/categories/{categorie['id']}")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["depot"] == "retire"
    assert not dossier.exists()


def test_un_dossier_qui_attend_encore_ne_part_pas(client, tmp_path, monkeypatch):
    """
    On n'efface pas ce qui attend : un fichier posé la veille n'a pas été lu, et
    le détruire perdrait un papier que personne n'a vu.
    """
    from app import depots

    monkeypatch.setattr(depots, "racine", lambda: tmp_path)
    categorie = client.post("/admin/categories",
                            json={"nom": "_DepotOccupe", "nature": "type"}).json()
    dossier = depots.chemin(categorie["dossier_depot"])
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "facture.pdf").write_bytes(b"%PDF-1.4")

    reponse = client.delete(f"/admin/categories/{categorie['id']}")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["depot"] == "garde"
    assert (dossier / "facture.pdf").is_file(), "le papier en attente reste"
