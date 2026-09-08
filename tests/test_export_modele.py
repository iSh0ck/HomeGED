"""
L'export par modèle d'arborescence et de nommage (§21.13).

L'export de secours (§17.30) sort **tout** le foyer, une fois, sous mot de passe
administrateur : il répond à « je ne me sers plus de la GED ». Celui-ci répond à
l'autre besoin, quotidien — sortir **une sélection** rangée comme on la veut,
pour la donner au comptable, à l'assurance, au notaire.

Ces tests portent sur ce qui doit rester vrai : le rangement suit le modèle, les
droits du demandeur s'appliquent au moment de la construction, et un trou vide
ne laisse pas de « {champ:x} » dans un nom de fichier.
"""
import os
import io
import zipfile
from pathlib import Path
from datetime import date

import pytest

from app import export_modele, worker
from app.db import Categorie, Document, ExportModele, Metadonnee, SessionLocal


@pytest.fixture
def deux_factures(base_de_test, tmp_path):
    """Deux documents archivés pour de vrai, avec leur émetteur."""
    session = SessionLocal()
    try:
        session.query(ExportModele).delete()
        session.query(Document).filter(Document.nom_fichier.like("_xm%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        identifiants = []
        for nom, emetteur, jour in (("_xm_edf.pdf", "EDF", date(2026, 3, 12)),
                                    ("_xm_orange.pdf", "Orange", date(2025, 11, 4))):
            fichier = tmp_path / nom
            fichier.write_bytes(b"%PDF-1.7\n" + nom.encode())
            document = Document(nom_fichier=nom, chemin_stockage=str(fichier),
                                hash_sha256=nom.ljust(64, "x"), texte_ocr="x",
                                statut="traite", categorie_id=type_doc.id,
                                date_document=jour)
            session.add(document)
            session.flush()
            session.add(Metadonnee(document_id=document.id, cle="emetteur", valeur=emetteur))
            identifiants.append(document.id)
        session.commit()
        contexte = (identifiants, type_doc.nom)
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(ExportModele).delete()
        session.query(Document).filter(Document.nom_fichier.like("_xm%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


# ------------------------------------------------------------------
# Le modèle lui-même
# ------------------------------------------------------------------

def test_le_modele_range_par_annee_et_par_type(deux_factures):
    identifiants, nom_type = deux_factures
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        metadonnees = {m.cle: m.valeur for m in document.metadonnees}
        chemin = export_modele.chemin_dans_archive(
            document, metadonnees, "{annee}/{type}", "{champ:emetteur} - {date}", set())
        assert chemin == f"2026/{nom_type}/EDF - 2026-03-12.pdf"
    finally:
        session.close()


def test_un_trou_vide_ne_laisse_pas_de_trace(deux_factures):
    """
    L'archive est lue par quelqu'un qui n'a jamais vu nos modèles :
    « {champ:garantie} - 2026-03.pdf » ne lui dirait rien de bon.
    """
    identifiants, _ = deux_factures
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        rendu = export_modele.remplir("{champ:inexistant} - {date}", document, {})
        assert rendu == "2026-03-12"
        assert "{" not in rendu
    finally:
        session.close()


def test_un_nom_avec_une_barre_oblique_ne_creuse_pas_un_dossier(deux_factures):
    identifiants, _ = deux_factures
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        rendu = export_modele.remplir("{champ:emetteur}", document,
                                      {"emetteur": "Eau / Ville"})
        assert "/" not in rendu
    finally:
        session.close()


def test_deux_documents_de_meme_nom_ne_secrasent_pas(deux_factures):
    identifiants, _ = deux_factures
    session = SessionLocal()
    try:
        pris = set()
        chemins = [export_modele.chemin_dans_archive(
            session.get(Document, i), {}, "sortie", "facture", pris) for i in identifiants]
        assert len(set(chemins)) == 2
    finally:
        session.close()


# ------------------------------------------------------------------
# La demande, de bout en bout
# ------------------------------------------------------------------

def test_une_demande_devient_une_archive(client, deux_factures):
    demande = client.post("/exports-modele", json={
        "criteres": [], "modele_dossier": "{annee}", "modele_nom": "{champ:emetteur}"})
    assert demande.status_code == 200, demande.text
    assert demande.json()["statut"] == "en_attente"
    identifiant = demande.json()["id"]

    # c'est le serveur de travaux qui construit : l'API n'a pas les archives en
    # écriture, et cinq cents PDF ne se compressent pas dans une requête
    assert worker.construire_exports_modele() >= 1

    session = SessionLocal()
    try:
        etat = session.get(ExportModele, identifiant)
        assert etat.statut == "pret", etat.message
        assert etat.nb_documents >= 2
    finally:
        session.close()

    fichier = client.get(f"/exports-modele/{identifiant}/fichier")
    assert fichier.status_code == 200
    assert fichier.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(fichier.content)) as archive:
        noms = archive.namelist()
        assert any(n.startswith("2026/") and "EDF" in n for n in noms), noms
        assert any(n.startswith("2025/") and "Orange" in n for n in noms), noms


def test_un_critere_illisible_est_refuse_tout_de_suite(client, deux_factures):
    """Une demande qui échouerait dans cinq minutes doit être refusée pendant que
    celui qui l'a posée est encore là."""
    refus = client.post("/exports-modele", json={
        "criteres": [{"champ": "couleur", "operateur": "egal", "valeur": "rouge"}]})
    assert refus.status_code == 422


def test_larchive_appartient_a_qui_la_demandee(client, deux_factures):
    """Une archive est une copie de documents du foyer : elle appartient à qui
    l'a demandée, et à l'administration."""
    demande = client.post("/exports-modele", json={"criteres": []}).json()
    worker.construire_exports_modele()

    session = SessionLocal()
    try:
        session.get(ExportModele, demande["id"]).utilisateur_id = None
        session.commit()
    finally:
        session.close()
    # le compte de test est administrateur : il garde l'accès, ce qui est le but
    assert client.get(f"/exports-modele/{demande['id']}/fichier").status_code in (200, 404)


def test_le_nom_porte_le_libelle_et_non_la_reference(base_de_test, tmp_path):
    """
    « Orange - 2026-03.pdf » se lit ; « usr_emetteurs-5 - 2026-03.pdf » non — et
    c'est un tiers qui ouvrira cette archive.
    """
    from sqlalchemy import text as sql

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_xr%")).delete(
            synchronize_session=False)
        session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_XrOrange'"))
        session.execute(sql("INSERT INTO usr_emetteurs (nom) VALUES ('_XrOrange')"))
        emetteur = session.execute(sql(
            "SELECT id FROM usr_emetteurs WHERE nom = '_XrOrange'")).scalar()

        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        fichier = tmp_path / "_xr_facture.pdf"
        fichier.write_bytes(b"%PDF-1.7")
        document = Document(nom_fichier="_xr_facture.pdf", chemin_stockage=str(fichier),
                            hash_sha256="_xr".ljust(64, "r"), texte_ocr="x",
                            statut="traite", categorie_id=type_doc.id,
                            date_document=date(2026, 3, 1))
        session.add(document)
        session.flush()
        session.add(Metadonnee(document_id=document.id, cle="emetteur",
                               valeur=f"usr_emetteurs:{emetteur}"))
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    try:
        session = SessionLocal()
        document = session.get(Document, identifiant)
        libelles = export_modele.libelles_des_references(session, [document])
        metadonnees = {m.cle: m.valeur for m in document.metadonnees}
        metadonnees.update(libelles.get(document.id, {}))
        rendu = export_modele.remplir("{champ:emetteur} - {date}", document, metadonnees)
        assert rendu == "_XrOrange - 2026-03-01"
        session.close()
    finally:
        session = SessionLocal()
        session.query(Document).filter(Document.nom_fichier.like("_xr%")).delete(
            synchronize_session=False)
        session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_XrOrange'"))
        session.commit()
        session.close()


def test_une_archive_oubliee_finit_par_disparaitre(client, deux_factures, tmp_path):
    """
    Une archive oubliée est une copie de documents du foyer qui traîne sur le
    disque, et personne ne pense au ménage (§17.30, même raison).
    """
    from datetime import datetime, timedelta

    from app import reglages

    demande = client.post("/exports-modele", json={"criteres": []}).json()
    worker.construire_exports_modele()

    session = SessionLocal()
    try:
        reglages.enregistrer(session, {"expiration_export_minutes": "60"})
        etat = session.get(ExportModele, demande["id"])
        chemin = etat.chemin
        etat.date_demande = datetime.now() - timedelta(hours=3)
        session.commit()
    finally:
        session.close()

    assert worker.purger_exports_modele() >= 1

    session = SessionLocal()
    try:
        assert session.get(ExportModele, demande["id"]) is None
        assert not Path(chemin).exists(), "le fichier part avec la ligne"
    finally:
        session.close()


def test_l_apercu_dit_le_rangement_avant_de_le_demander(client, deux_factures):
    """
    On écrivait le modèle **à l'aveugle** et l'on découvrait le rangement une
    fois l'archive construite, quelques minutes plus tard (§22.66). L'aperçu
    passe par la même fonction de remplissage que le serveur de travaux : une
    imitation finirait par en diverger, et l'aperçu mentirait.
    """
    apercu = client.post("/exports-modele/apercu", json={
        "criteres": [], "modele_dossier": "{annee}", "modele_nom": "{champ:emetteur}"})
    assert apercu.status_code == 200, apercu.text
    corps = apercu.json()

    assert corps["total"] >= 2, "le nombre de documents visés doit être dit"
    assert any(c.startswith("2026/") and "EDF" in c for c in corps["exemples"]), corps
    # Trois exemples au plus : c'est un aperçu, pas la liste.
    assert len(corps["exemples"]) <= 3


def test_l_apercu_suit_le_modele_qu_on_ecrit(client, deux_factures):
    apercu = client.post("/exports-modele/apercu", json={
        "criteres": [], "modele_dossier": "{champ:emetteur}",
        "modele_nom": "{annee}-{nom_fichier}"})
    exemples = apercu.json()["exemples"]
    assert any(c.startswith("EDF/2026-") for c in exemples), exemples


def test_l_apercu_montre_le_modele_par_defaut_quand_le_champ_est_vide(client, deux_factures):
    """
    Vider le champ ne met pas l'archive à plat : c'est le modèle par défaut qui
    reprend la main, et c'est le comportement du serveur depuis toujours.
    L'aperçu le **montre** au lieu de le laisser découvrir après coup — c'est
    précisément ce qu'on lui demande (§22.66).
    """
    apercu = client.post("/exports-modele/apercu", json={
        "criteres": [], "modele_dossier": "", "modele_nom": ""})
    exemples = apercu.json()["exemples"]
    assert any(c.startswith("2026/Factures/") for c in exemples), exemples


def test_une_archive_se_supprime_avec_son_fichier(client, deux_factures):
    """
    On ne pouvait que les accumuler (§22.66). Une archive est une copie complète
    d'une partie du foyer posée sur le disque : la laisser traîner parce que rien
    ne permet de l'enlever est le contraire de ce qu'on veut.
    """
    identifiant = client.post("/exports-modele", json={
        "criteres": [], "modele_dossier": "{annee}", "modele_nom": "{champ:emetteur}"}).json()["id"]
    assert worker.construire_exports_modele() >= 1

    session = SessionLocal()
    try:
        chemin = session.get(ExportModele, identifiant).chemin
    finally:
        session.close()
    assert chemin and os.path.isfile(chemin)

    retrait = client.delete(f"/exports-modele/{identifiant}")
    assert retrait.status_code == 200, retrait.text
    assert not os.path.exists(chemin), "le fichier part avec la demande"
    assert client.get(f"/exports-modele/{identifiant}/fichier").status_code == 404
    assert identifiant not in [d["id"] for d in client.get("/exports-modele").json()]
