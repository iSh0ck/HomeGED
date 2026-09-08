"""
D'où vient un document (§22.68, corrigé au §22.72).

Un foyer dépose de deux façons : en posant un fichier dans le dossier surveillé,
où le classement se déduit de l'endroit, et en le glissant dans l'application, où
l'on dit son type au dépôt. Une icône les distingue ; encore faut-il qu'elle dise
vrai.

La première version se fiait à `sys_jobs.chemin_source` — et c'était faux : le
fichier reçu est rangé à côté de son travail à la fin du traitement (§18.53),
dans le dossier des travaux, quelle que soit sa provenance. Tout se retrouvait
marqué « déposé à la main ». Ces tests fixent la règle qui la remplace.
"""
from pathlib import Path

from app import config, worker


def test_un_fichier_glisse_dans_lapplication_est_dit_manuel():
    chemin = Path(config.DEPOTS_MANUELS_FOLDER) / "abc123" / "facture.pdf"
    assert worker._origine_du_depot(chemin) is True


def test_un_fichier_du_dossier_surveille_ne_lest_pas():
    chemin = Path(config.OCR_WAIT_FOLDER) / "Factures" / "orange.pdf"
    assert worker._origine_du_depot(chemin) is False


def test_le_dossier_des_travaux_ne_dit_plus_rien():
    """
    C'est le défaut du §22.68 : le fichier reçu y est rangé à la fin du
    traitement, quelle que soit son origine. Un rejeu repart de là, et l'on
    préfère alors se taire plutôt que d'inventer.
    """
    chemin = Path(config.TRAVAUX_FOLDER) / "42" / "orange.pdf"
    assert worker._origine_du_depot(chemin) is None


def test_un_chemin_illisible_ne_fait_rien_echouer():
    assert worker._origine_du_depot(Path("/inexistant/nulle/part.pdf")) is None
