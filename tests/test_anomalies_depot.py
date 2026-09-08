"""
Emplacements non valides du dépôt (§19.5).

Le dépôt appartient à la GED. Ce qui peut être empêché l'est — la racine est
fermée en écriture. Mais aucune permission ne tient contre un partage monté en
écriture totale ou un dépôt fait par root : **ce qui ne peut pas être interdit
doit être visible**. Ces tests portent donc autant sur les droits posés que sur
ce qui est signalé quand ils n'ont pas suffi.
"""
import stat

import pytest

from app import categories as natures, config, depots
from app.db import Categorie, SessionLocal


@pytest.fixture
def depot(tmp_path, monkeypatch, base_de_test):
    monkeypatch.setattr(config, "OCR_WAIT_FOLDER", str(tmp_path / "ocr_wait"))
    monkeypatch.setattr(config, "CORBEILLE_FOLDER", str(tmp_path / "corbeille"))

    session = SessionLocal()
    try:
        session.query(Categorie).filter(Categorie.nom.like("_Anom%")).delete(
            synchronize_session=False)
        type_doc = Categorie(nom="_AnomFactures", nature=natures.TYPE, ordre=945)
        session.add(type_doc)
        session.flush()
        depots.attribuer(session, type_doc)
        session.commit()
        contexte = {"type": type_doc.id, "dossier": type_doc.dossier_depot}
    finally:
        session.close()

    session = SessionLocal()
    try:
        depots.synchroniser(session)
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(Categorie).filter(Categorie.nom.like("_Anom%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _corbeille():
    from pathlib import Path
    return Path(config.CORBEILLE_FOLDER)


def _anomalies():
    session = SessionLocal()
    try:
        return depots.anomalies(session)
    finally:
        session.close()


def test_la_racine_est_fermee_en_ecriture(depot):
    """
    Personne n'y crée de dossier ni de fichier — pas même son propriétaire, qui
    devrait pour cela changer les droits délibérément. C'est ce qui fait de la
    GED la seule à tenir cette arborescence.
    """
    mode = stat.S_IMODE(depots.racine().stat().st_mode)
    assert mode == depots.DROITS_RACINE
    assert not (mode & stat.S_IWOTH), "un tiers ne doit pas pouvoir écrire à la racine"
    assert not (mode & stat.S_IWUSR), "même le propriétaire doit avoir à y revenir exprès"


def test_les_dossiers_de_type_sont_ouverts_a_tous(depot):
    """
    C'est là qu'on dépose : tout le monde doit pouvoir y écrire. Le bit collant
    empêche en revanche d'effacer le dépôt d'un autre.
    """
    mode = stat.S_IMODE(depots.chemin(depot["dossier"]).stat().st_mode)
    assert mode & stat.S_IWOTH, "chacun doit pouvoir déposer"
    assert mode & stat.S_ISVTX, "personne ne doit pouvoir effacer le dépôt d'un autre"


def test_un_depot_en_ordre_ne_signale_rien(depot):
    assert _anomalies() == []


def test_un_dossier_cree_a_la_main_est_signale(depot):
    """Rien n'y sera lu : il n'appartient à aucun type."""
    (depots.racine() / "a_trier").mkdir()

    signalees = _anomalies()
    assert [e["chemin"] for e in signalees] == ["a_trier"]
    assert signalees[0]["raison"] == "dossier_inconnu"
    assert signalees[0]["dossier"] is True
    assert signalees[0]["traitable"] is False, "un dossier ne se range pas dans un type"


def test_les_fichiers_dun_dossier_inconnu_sont_signales_un_par_un(depot):
    """C'est le fichier qui compte : c'est lui qu'on veut retrouver."""
    inconnu = depots.racine() / "scanner"
    inconnu.mkdir()
    (inconnu / "facture.pdf").write_bytes(b"%PDF")

    par_chemin = {e["chemin"]: e for e in _anomalies()}
    assert "scanner" in par_chemin and par_chemin["scanner"]["contient"] == 1
    fichier = par_chemin["scanner/facture.pdf"]
    assert fichier["raison"] == "hors_dossier_de_type"
    assert fichier["traitable"] is True, "il peut rejoindre un type de document"


def test_un_format_non_traite_est_signale_meme_bien_range(depot):
    """
    Le cas qui ne se voyait nulle part : déposé au bon endroit, mais dans un
    format que le serveur ne lit pas. Il restait là indéfiniment, sans tâche ni
    message — donc sans que personne ne s'en aperçoive.
    """
    (depots.chemin(depot["dossier"]) / "note.txt").write_text("bonjour")

    signalee = _anomalies()[0]
    assert signalee["raison"] == "extension_non_traitee"
    assert signalee["traitable"] is False, \
        "le ranger ailleurs ne changerait rien : il ne serait pas lu davantage"


def test_un_fichier_a_la_racine_est_signale(depot):
    (depots.racine() / "egare.pdf").write_bytes(b"%PDF")
    assert _anomalies()[0]["raison"] == "racine"


def test_un_chemin_qui_sort_du_depot_est_refuse():
    """
    Ce contrôle n'est pas une formalité : le chemin vient de l'interface, et
    « ../../etc/passwd » y arriverait aussi bien qu'un nom de fichier.
    """
    with pytest.raises(depots.DepotRefuse):
        depots.chemin_sous_la_racine("../../etc/passwd")


def test_ranger_un_fichier_egare_le_rend_ordinaire(client, depot):
    inconnu = depots.racine() / "scanner"
    inconnu.mkdir()
    (inconnu / "facture.pdf").write_bytes(b"%PDF")

    reponse = client.post("/admin/depots/ranger", json={
        "chemin": "scanner/facture.pdf", "categorie_id": depot["type"]})
    assert reponse.status_code == 200, reponse.text
    assert (depots.chemin(depot["dossier"]) / "facture.pdf").is_file()
    assert not (inconnu / "facture.pdf").exists()


def test_retirer_un_fichier_le_met_a_la_corbeille(client, depot):
    """
    Jamais détruit : ce qui traîne a pu y arriver par erreur, et la destruction
    se décide en connaissance de cause.
    """
    (depots.racine() / "egare.pdf").write_bytes(b"%PDF")

    reponse = client.post("/admin/depots/retirer", json={"chemin": "egare.pdf"})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["corbeille"] is True
    assert (_corbeille() / "egare.pdf").is_file()
    assert not (depots.racine() / "egare.pdf").exists()


def test_un_dossier_non_vide_ne_se_supprime_pas(client, depot):
    """On ne sait pas ce qu'il contient : ses fichiers se traitent d'abord."""
    inconnu = depots.racine() / "scanner"
    inconnu.mkdir()
    (inconnu / "facture.pdf").write_bytes(b"%PDF")

    refus = client.post("/admin/depots/retirer", json={"chemin": "scanner"})
    assert refus.status_code == 400
    assert "pas vide" in refus.json()["detail"]

    inconnu.joinpath("facture.pdf").unlink()
    assert client.post("/admin/depots/retirer", json={"chemin": "scanner"}).status_code == 200
    assert not inconnu.exists()


def test_la_racine_elle_meme_ne_se_retire_pas(client, depot):
    refus = client.post("/admin/depots/retirer", json={"chemin": "."})
    assert refus.status_code == 400
