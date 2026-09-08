"""
Découpage des fichiers de migration. Deux défauts ont été trouvés ici : un
point-virgule dans un commentaire coupait l'instruction en plein milieu, et les
chaînes littérales n'étaient pas reconnues.
"""
import pytest

from app.migrations import _instructions


@pytest.mark.parametrize("libelle, sql, attendu", [
    ("instruction simple", "SELECT 1;", 1),
    ("deux instructions", "SELECT 1; SELECT 2;", 2),
    ("sans point-virgule final", "SELECT 1", 1),
    ("point-virgule dans un commentaire de fin de ligne",
     "CREATE TABLE t (\n  a INT,  -- ceci ; n'est pas un separateur\n  b INT\n);", 1),
    ("commentaire sur sa propre ligne", "-- commentaire ;\nSELECT 1;", 1),
    ("commentaire de bloc", "/* un ; commentaire */ SELECT 1;", 1),
    ("point-virgule dans une chaine", "INSERT INTO t VALUES ('a;b');", 1),
    ("apostrophe echappee", "INSERT INTO t VALUES ('l''an; 2000');", 1),
    ("antislash dans une expression reguliere", r"INSERT INTO t VALUES ('(?i)\bEDF\b');", 1),
    ("lignes vides ignorees", "SELECT 1;\n\n\n;\n", 1),
])
def test_decoupage(libelle, sql, attendu):
    assert len(_instructions(sql)) == attendu, libelle


def test_le_commentaire_est_retire_mais_pas_l_instruction():
    (instruction,) = _instructions("SELECT 1; -- fin ; de ligne")
    assert instruction == "SELECT 1"


def test_le_contenu_des_chaines_est_preserve():
    (instruction,) = _instructions("INSERT INTO t VALUES ('a -- b');")
    assert "a -- b" in instruction


def test_les_pourcents_ne_sont_pas_pris_pour_des_marqueurs():
    """
    Une migration contenant `LIKE 'a\\_%'` doit passer telle quelle. Le pilote
    MySQL interprète les `%` comme des marqueurs de format dès qu'on lui passe
    des arguments : le runner exécute donc sans aucun argument.
    """
    (instruction,) = _instructions("UPDATE t SET a = 1 WHERE b LIKE 'donnees\\_%';")
    assert instruction.endswith("LIKE 'donnees\\_%'")


def test_les_deux_points_ne_sont_pas_pris_pour_des_parametres():
    """`(?:de\\s+)?` dans une expression régulière contient `:de`, qui n'est pas un paramètre."""
    (instruction,) = _instructions("INSERT INTO t VALUES ('(?i)date\\s*(?:de\\s+)?facture');")
    assert "(?:de" in instruction
