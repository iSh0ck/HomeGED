"""
Copie de secours (§22.49).

L'application détient l'unique exemplaire des papiers du foyer. Ce que ces tests
vérifient n'est pas que « ça sauvegarde », mais les trois propriétés dont tout le
reste dépend : rien ne part sans qu'on l'ait demandé, une sauvegarde incomplète
ne se fait pas passer pour valable, et l'état se lit — une sauvegarde silencieuse
qui a cessé est pire que pas de sauvegarde.
"""
import shutil
from pathlib import Path

import pytest

from app import sauvegarde


@pytest.fixture
def dossier(tmp_path):
    return str(tmp_path / "sauvegardes")


def test_rien_ne_se_sauvegarde_tant_que_le_foyer_ne_l_a_pas_demande(client):
    """Le défaut est **non** : remplir le disque de quelqu'un sans son accord
    serait une mauvaise façon de le protéger."""
    etat = client.get("/admin/sauvegardes")
    assert etat.status_code == 200, etat.text
    corps = etat.json()
    assert corps["active"] is False
    assert corps["jamais_faite"] is True
    assert corps["sauvegardes"] == []


def test_une_sauvegarde_se_relit_sans_l_application(client, dossier):
    """
    Le format est un dossier daté : un dump SQL en clair et une copie des
    archives. On doit pouvoir le restaurer avec `mariadb <` et `cp -r`, sans ce
    code — sans quoi la sauvegarde ne vaut que tant que le logiciel tourne.
    """
    bilan = sauvegarde.executer(dossier, avec_archives=False)
    cible = Path(bilan["dossier"])
    assert (cible / sauvegarde.NOM_BASE).is_file()
    assert bilan["octets_base"] > 0
    # La marque écrite en dernier : c'est elle qui distingue une sauvegarde finie
    # d'une sauvegarde interrompue.
    marque = (cible / sauvegarde.NOM_MARQUE).read_text(encoding="utf-8")
    assert "Pour restaurer" in marque and sauvegarde.NOM_BASE in marque
    # Le dump contient bien le schéma du foyer.
    debut = (cible / sauvegarde.NOM_BASE).read_text(encoding="utf-8", errors="replace")[:4000]
    assert "sys_documents" in debut or "CREATE TABLE" in debut


def test_une_sauvegarde_interrompue_ne_passe_pas_pour_valable(dossier):
    """Sans sa marque finale, elle ne compte pas — et n'est pas proposée comme
    dernière sauvegarde réussie."""
    bilan = sauvegarde.executer(dossier, avec_archives=False)
    (Path(bilan["dossier"]) / sauvegarde.NOM_MARQUE).unlink()

    listees = sauvegarde.lister(dossier)
    assert listees and listees[0]["complete"] is False
    assert sauvegarde.etat(dossier)["jamais_faite"] is True


def test_on_ne_garde_que_le_nombre_voulu(dossier):
    """Ce qui ne s'efface jamais tout seul finit par occuper un disque — et une
    sauvegarde est une copie complète du foyer."""
    for _ in range(4):
        bilan = sauvegarde.executer(dossier, avec_archives=False)
        # Les noms portent la minute : on les distingue à la main pour le test.
        Path(bilan["dossier"]).rename(
            Path(bilan["dossier"]).parent / f"{Path(bilan['dossier']).name}-{_}")
    assert len(sauvegarde.lister(dossier)) == 4
    sauvegarde.purger(dossier, garder=2)
    assert len(sauvegarde.lister(dossier)) == 2


def test_l_etat_dit_quand_la_sauvegarde_a_cesse(dossier):
    """
    Une sauvegarde qui ne se fait plus, et que personne ne surveille, est pire
    que pas de sauvegarde : on s'y fie. L'état porte donc le retard.
    """
    assert sauvegarde.etat(dossier, alerte_jours=3)["jamais_faite"] is True
    sauvegarde.executer(dossier, avec_archives=False)
    etat = sauvegarde.etat(dossier, alerte_jours=3)
    assert etat["jamais_faite"] is False
    assert etat["en_retard"] is False
    assert etat["nombre"] == 1
    # Une sauvegarde vieille de dix jours, avec une alerte à trois, est en retard.
    assert sauvegarde.etat(dossier, alerte_jours=0)["en_retard"] is True
    shutil.rmtree(dossier, ignore_errors=True)


def test_on_peut_en_declencher_une_a_la_demande(client, tmp_path):
    """C'est le geste qu'on fait avant une opération risquée — et ce qui prouve
    que le réglage fonctionne."""
    cible = str(tmp_path / "a_la_demande")
    assert client.put("/admin/reglages",
                      json={"sauvegarde_dossier": cible,
                            "sauvegarde_archives": "0"}).status_code == 200
    try:
        reponse = client.post("/admin/sauvegardes")
        assert reponse.status_code == 200, reponse.text
        assert reponse.json()["octets_base"] > 0

        etat = client.get("/admin/sauvegardes").json()
        assert etat["nombre"] == 1 and etat["jamais_faite"] is False

        nom = etat["sauvegardes"][0]["nom"]
        assert client.delete(f"/admin/sauvegardes/{nom}").status_code == 200
        assert client.get("/admin/sauvegardes").json()["nombre"] == 0
        # Un nom qui sort du dossier est refusé : il désigne un dossier, jamais
        # un chemin. Le code exact importe peu — 400 par le contrôle, 404 quand
        # le routage a déjà normalisé le chemin —, ce qui compte est que rien ne
        # s'efface hors du dossier de sauvegarde.
        assert client.delete("/admin/sauvegardes/..").status_code in (400, 404)
        assert client.delete("/admin/sauvegardes/%2E%2E").status_code in (400, 404)
        assert client.delete("/admin/sauvegardes/inexistante").status_code == 404
    finally:
        client.put("/admin/reglages", json={"sauvegarde_dossier": "/data/sauvegardes"})


def test_une_sauvegarde_chiffree_se_relit_avec_openssl_seul(dossier, tmp_path):
    """
    Le deuxième principe tient même chiffrée (§22.65) : `openssl` est un outil
    standard, la commande exacte est écrite en clair à côté de l'archive, et il
    n'y a rien de propre à ce code pour la relire.
    """
    import subprocess

    bilan = sauvegarde.executer(dossier, avec_archives=False, mot_de_passe="ouvre-toi")
    assert bilan["chiffree"] is True

    archive = Path(bilan["dossier"])
    assert archive.is_file() and archive.name.endswith(sauvegarde.SUFFIXE_CHIFFRE)
    # Le dossier en clair ne doit pas rester à côté : ce serait rendre le
    # chiffrement inutile.
    assert not archive.with_suffix("").is_dir()

    marque = Path(f"{archive}.txt")
    assert marque.is_file(), "la façon de la relire doit rester lisible"
    assert "openssl enc -d -aes-256-cbc -pbkdf2" in marque.read_text(encoding="utf-8")

    sortie = tmp_path / "relu"
    sortie.mkdir()
    dechiffre = subprocess.run(
        f"openssl enc -d -aes-256-cbc -pbkdf2 -pass pass:ouvre-toi -in {archive} | tar -xzf - -C {sortie}",
        shell=True, capture_output=True)
    assert dechiffre.returncode == 0, dechiffre.stderr
    base = next(sortie.rglob(sauvegarde.NOM_BASE))
    assert base.stat().st_size > 0


def test_un_mauvais_mot_de_passe_ne_rend_rien(dossier, tmp_path):
    """Sans le mot de passe, la sauvegarde est perdue — c'est le principe."""
    import subprocess

    bilan = sauvegarde.executer(dossier, avec_archives=False, mot_de_passe="ouvre-toi")
    essai = subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "pass:autre",
         "-in", bilan["dossier"]],
        capture_output=True)
    assert essai.returncode != 0


def test_une_archive_chiffree_se_liste_et_se_purge(dossier):
    """
    Elle est un fichier et non un dossier : la liste et la purge la voient.

    Deux sauvegardes rapprochées portent le même nom à la minute près ; sans
    l'archive chiffrée dans le test de collision, la seconde écrasait la
    première en silence — c'est ce test qui l'a montré.
    """
    sauvegarde.executer(dossier, avec_archives=False, mot_de_passe="secret")
    faites = sauvegarde.lister(dossier)
    assert len(faites) == 1
    assert faites[0]["chiffree"] is True and faites[0]["complete"] is True

    sauvegarde.executer(dossier, avec_archives=False, mot_de_passe="secret")
    assert sauvegarde.purger(dossier, garder=1) == 1
    restantes = sauvegarde.lister(dossier)
    assert len(restantes) == 1
    # La marque en clair part avec l'archive : rien d'orphelin dans le dossier.
    assert list(Path(dossier).glob("*.txt")) == [
        Path(f"{restantes[0]['chemin']}.txt")]


def test_sans_mot_de_passe_rien_ne_change(dossier):
    """Le chiffrement est facultatif : le dossier lisible reste le défaut."""
    bilan = sauvegarde.executer(dossier, avec_archives=False)
    assert bilan["chiffree"] is False
    assert Path(bilan["dossier"]).is_dir()
