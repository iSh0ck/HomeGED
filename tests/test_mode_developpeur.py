"""
Le mode développeur (§21.14).

Les scripts Python sont la porte de sortie universelle : ce qu'aucun écran ne
prévoit et qu'on ne va pas coder pour un foyer. L'utilisateur les autorise
**sous condition d'un mode activé en administration, qui énonce d'abord ce que
cela pose**.

Ces tests portent presque tous sur les bornes — c'est ce qui rend le mode
acceptable : un point d'entrée, une durée maximale, aucun accès à la base, et
une trace de chaque exécution.
"""
import pytest

from app import reglages, scripts
from app.db import ExecutionScript, Script, SessionLocal


def _mode(actif):
    session = SessionLocal()
    try:
        reglages.enregistrer(session, {"mode_developpeur": "1" if actif else "0"})
        session.commit()
    finally:
        session.close()


@pytest.fixture
def mode_arme(base_de_test):
    _mode(True)
    yield
    _mode(False)
    session = SessionLocal()
    try:
        session.query(ExecutionScript).delete()
        session.query(Script).filter(Script.nom.like("_md%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


# ------------------------------------------------------------------
# L'interrupteur
# ------------------------------------------------------------------

def test_le_mode_est_eteint_par_defaut(base_de_test):
    """C'est le seul défaut acceptable pour une porte de sortie."""
    _mode(False)
    session = SessionLocal()
    try:
        assert scripts.mode_actif(session) is False
        with pytest.raises(scripts.ScriptRefuse):
            scripts.exiger_mode_actif(session)
    finally:
        session.close()


def test_rien_ne_senregistre_tant_que_le_mode_est_eteint(client, base_de_test):
    _mode(False)
    refus = client.post("/admin/scripts", json={
        "nom": "_mdInterdit", "code": "def executer(contexte):\\n    return 1"})
    assert refus.status_code == 409
    assert "mode développeur" in refus.json()["detail"].lower()


# ------------------------------------------------------------------
# Les bornes
# ------------------------------------------------------------------

def test_le_point_dentree_est_exige(mode_arme):
    """Sans lui, on ne saurait pas quoi donner au script — ni ce qu'il attend."""
    with pytest.raises(scripts.ScriptRefuse) as refus:
        scripts.valider("print('bonjour')")
    assert "executer(contexte)" in str(refus.value)


def test_un_script_illisible_est_refuse_a_lecriture(mode_arme):
    """Une faute de frappe se corrige au moment où on l'écrit, pas trois semaines
    plus tard devant une trace d'exécution."""
    with pytest.raises(scripts.ScriptRefuse):
        scripts.valider("def executer(contexte)\\n    return 1")


def test_un_script_rend_ce_quil_calcule(mode_arme):
    bilan = scripts.executer(
        "def executer(contexte):\n"
        "    return sum(contexte['nombres'])",
        {"nombres": [1, 2, 3]})
    assert bilan["reussite"] is True
    assert bilan["sortie"].strip() == "6"


def test_une_erreur_du_script_est_rendue_sans_faire_tomber_le_service(mode_arme):
    bilan = scripts.executer("def executer(contexte):\n    return 1 / 0", {})
    assert bilan["reussite"] is False
    assert "ZeroDivisionError" in bilan["erreur"]


def test_une_boucle_infinie_est_arretee(mode_arme):
    """Un script qui ne rend pas la main ne doit pas emporter le serveur."""
    bilan = scripts.executer(
        "def executer(contexte):\n"
        "    while True:\n"
        "        pass", {}, duree_max=2)
    assert bilan["reussite"] is False
    assert "secondes" in bilan["erreur"]


def test_le_script_na_pas_acces_a_la_base(mode_arme):
    """
    La borne qui coûte le plus en confort, et celle qui rend le reste
    acceptable : le script rend un texte, que quelqu'un lit. La GED ne se
    modifie pas dans le dos de ses écrans.
    """
    bilan = scripts.executer(
        "def executer(contexte):\n"
        "    from app.db import SessionLocal\n"
        "    return 'entré dans la base'", {})
    assert bilan["reussite"] is False
    assert "app" in (bilan["erreur"] or "")


def test_le_contexte_est_le_seul_apport(mode_arme):
    """Le script ne va pas se servir : on lui donne, et c'est tout ce qu'il a."""
    bilan = scripts.executer(
        "import os\n"
        "def executer(contexte):\n"
        "    return os.environ.get('DB_PASSWORD', 'rien')", {})
    assert bilan["reussite"] is True
    assert bilan["sortie"].strip('"\n ') == "rien"


# ------------------------------------------------------------------
# De bout en bout
# ------------------------------------------------------------------

def test_un_script_senregistre_puis_sexecute_et_laisse_une_trace(client, mode_arme):
    cree = client.post("/admin/scripts", json={
        "nom": "_mdCompte", "description": "Compte ce qu'on lui donne",
        "code": "def executer(contexte):\n    return len(contexte.get('lignes', []))"})
    assert cree.status_code == 200, cree.text
    identifiant = cree.json()["id"]

    lance = client.post(f"/admin/scripts/{identifiant}/executer",
                        json={"contexte": {"lignes": [1, 2, 3, 4]}})
    assert lance.status_code == 200, lance.text
    assert lance.json()["reussite"] is True
    assert lance.json()["sortie"].strip() == "4"

    # la trace est la contrepartie du mode : « un script a tourné » sans trace ne
    # serait qu'une rumeur
    historique = client.get("/admin/scripts/executions").json()
    assert historique[0]["script_id"] == identifiant
    assert historique[0]["reussite"] is True
    assert historique[0]["par"]
