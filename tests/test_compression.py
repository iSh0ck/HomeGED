"""
Compression des archives (§17.8).

Le gain se mesure sur de vrais scans, pas dans une suite de tests : ici on
vérifie ce qui protège l'archive. Un document compressé remplace l'original —
opération irréversible sur le seul exemplaire conservé. Ces tests décrivent donc
tous les cas où le remplacement **ne doit pas** avoir lieu.
"""
import os
import subprocess

import pytest

from app import compression


class FauxResultat:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture
def archive(tmp_path):
    """Un fichier qui tient lieu d'archive : son contenu importe peu ici."""
    chemin = tmp_path / "archive.pdf"
    chemin.write_bytes(b"%PDF-1.7\n" + b"x" * 10000)
    return chemin


def _simuler(monkeypatch, archive, original, candidat, echec=False):
    """
    Remplace l'optimiseur et la mesure des fichiers.

    `original` et `candidat` sont des triplets (taille, pages, texte) : le
    premier décrit l'archive en place, le second ce que rendrait l'optimiseur.
    Les mesurer pour de vrai supposerait de fabriquer des PDF illustrés — ce que
    ces tests ne cherchent pas à vérifier. Le gain réel, lui, a été mesuré sur
    les documents du projet (cf. app/config.py).
    """
    def faux_run(commande, **kwargs):
        if echec:
            return FauxResultat(returncode=2, stderr="ocrmypdf: quelque chose a mal tourné")
        with open(commande[-1], "wb") as sortie:      # le candidat, dernier argument
            sortie.write(b"%PDF-1.7\n" + b"y" * candidat[0])
        return FauxResultat()

    def fausse_mesure(chemin):
        return original if os.path.samefile(chemin, str(archive)) else candidat

    monkeypatch.setattr(subprocess, "run", faux_run)
    monkeypatch.setattr(compression, "_mesurer", fausse_mesure)


def test_remplace_quand_le_resultat_est_verifie_et_plus_petit(monkeypatch, archive):
    _simuler(monkeypatch, archive, (10000, 2, 500), (3000, 2, 500))
    bilan = compression.optimiser(str(archive))
    assert bilan["remplace"] is True
    assert bilan["avant"] == 10000 and bilan["apres"] == 3000
    assert archive.read_bytes().startswith(b"%PDF"), "l'archive a bien été remplacée"


def test_refuse_si_une_page_a_disparu(monkeypatch, archive):
    avant = archive.read_bytes()
    _simuler(monkeypatch, archive, (10000, 2, 500), (2000, 1, 500))
    bilan = compression.optimiser(str(archive))
    assert bilan["remplace"] is False
    assert "pages" in bilan["motif"]
    assert archive.read_bytes() == avant, "l'original doit rester intact"


def test_refuse_si_le_texte_a_ete_perdu(monkeypatch, archive):
    """
    Le texte porte la recherche plein texte et les règles d'extraction : un
    document qui l'a perdu est illisible pour l'application, quelle que soit son
    apparence à l'écran.
    """
    avant = archive.read_bytes()
    _simuler(monkeypatch, archive, (10000, 2, 500), (2000, 2, 100))
    bilan = compression.optimiser(str(archive))
    assert bilan["remplace"] is False
    assert "texte" in bilan["motif"]
    assert archive.read_bytes() == avant


def test_refuse_un_gain_derisoire(monkeypatch, archive):
    """Réécrire un fichier d'archive pour 2 % ne vaut pas le risque."""
    avant = archive.read_bytes()
    _simuler(monkeypatch, archive, (10000, 2, 500), (9800, 2, 500))
    bilan = compression.optimiser(str(archive))
    assert bilan["remplace"] is False
    assert bilan["motif"] == "gain insuffisant"
    assert archive.read_bytes() == avant


def test_optimiseur_en_echec_laisse_tout_en_place(monkeypatch, archive):
    avant = archive.read_bytes()
    _simuler(monkeypatch, archive, (10000, 2, 500), (0, 0, 0), echec=True)
    bilan = compression.optimiser(str(archive))
    assert bilan["remplace"] is False
    assert "échec" in bilan["motif"]
    assert archive.read_bytes() == avant


def test_niveau_zero_ne_touche_a_rien(monkeypatch, archive):
    avant = archive.read_bytes()
    appels = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: appels.append(a))
    bilan = compression.optimiser(str(archive), niveau=0)
    assert bilan["remplace"] is False
    assert appels == [], "l'optimiseur ne doit même pas être lancé"
    assert archive.read_bytes() == avant
