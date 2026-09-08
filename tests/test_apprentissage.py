"""
L'apprentissage visuel des règles (§21.5, bêta).

Écrire une expression régulière à l'aveugle est la boucle la plus décourageante
du projet : on décrit avec des symboles ce qu'on a sous les yeux, on enregistre,
on relance un traitement, et l'on découvre que le motif ne prend rien. Ici on
**montre** la valeur, et la règle se construit — avec la vérification en même
temps.
"""
import pytest

from app import apprentissage

FACTURE = """FACTURE N° FR-001
Émise le 02/04/2026
Client : Cendrilon Ayot
Total HT 145.00
TVA 20% 29.00
Total TTC 174.00 €
Référence contrat : ABC-2026/17
"""


def test_la_forme_de_la_valeur_donne_le_motif():
    """Une date ne s'attrape pas comme un montant, ni un numéro comme une phrase."""
    date = apprentissage.proposer(FACTURE, "02/04/2026")
    assert date["type_champ"] == "date"
    assert date["fonction"] == "date_normalisee"

    montant = apprentissage.proposer(FACTURE, "174.00")
    assert montant["type_champ"] == "montant"
    assert montant["fonction"] == "nombre_normalise"


def test_lancre_est_ce_qui_fait_la_regle():
    """
    « Le nombre qui suit Total TTC » vaut pour toutes les factures de cet
    émetteur ; « le nombre à cet endroit de la page » ne vaut que pour celle-ci.
    """
    proposition = apprentissage.proposer(FACTURE, "174.00")
    assert "Total" in proposition["ancre"] and "TTC" in proposition["ancre"]
    assert proposition["pattern"].startswith("Total")


def test_la_proposition_dit_ce_quelle_extrait():
    """La vérification a lieu **avant** d'enregistrer, et non après un
    retraitement complet."""
    proposition = apprentissage.proposer(FACTURE, "145.00")
    assert proposition["trouve"] is True
    assert proposition["valeur_extraite"] == "145.00"
    assert proposition["conforme"] is True


def test_lancre_tolere_les_espaces_du_scan():
    """Un scan sépare « Total TTC » par un espace, deux, ou une tabulation."""
    proposition = apprentissage.proposer(FACTURE, "174.00")
    autre_document = FACTURE.replace("Total TTC 174.00", "Total   TTC  :  231,90")
    import re
    trouve = re.search(proposition["pattern"], autre_document, re.IGNORECASE | re.MULTILINE)
    assert trouve and trouve.group(1) == "231,90"


def test_lancre_peut_etre_imposee():
    """Celui qui règle voit le document ; le module ne voit qu'une suite de
    caractères."""
    proposition = apprentissage.proposer(FACTURE, "ABC-2026/17", ancre="Référence contrat")
    assert proposition["ancre"] == "Référence contrat"
    assert proposition["conforme"] is True


def test_une_valeur_sans_intitule_est_refusee():
    """
    Sans ancre, un motif libre attraperait n'importe quelle ligne : on refuse
    plutôt que de proposer une règle qui remplira le champ avec le premier texte
    venu.
    """
    proposition = apprentissage.proposer("Cendrilon Ayot\n", "Cendrilon Ayot")
    assert "erreur" in proposition


def test_une_valeur_de_forme_connue_se_passe_dancre():
    """Une date reste une date même seule sur sa ligne."""
    proposition = apprentissage.proposer("02/04/2026\n", "02/04/2026")
    assert "erreur" not in proposition
    assert proposition["conforme"] is True


def test_rien_de_designe_rien_de_propose():
    assert "erreur" in apprentissage.proposer(FACTURE, "   ")


def test_la_route_verifie_sur_le_document_reel(client):
    from app.db import Categorie, Document, SessionLocal

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ap5%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        document = Document(nom_fichier="_ap5.pdf", chemin_stockage="/tmp/_ap5.pdf",
                            hash_sha256="_ap5".ljust(64, "a"), texte_ocr=FACTURE,
                            statut="traite", categorie_id=type_doc.id)
        session.add(document)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    try:
        reponse = client.post("/admin/regles/apprendre", json={
            "document_id": identifiant, "valeur": "174.00", "champ_cible": "montant_ttc"})
        assert reponse.status_code == 200, reponse.text
        proposition = reponse.json()
        assert proposition["conforme"] is True
        assert proposition["champ_cible"] == "montant_ttc"

        refus = client.post("/admin/regles/apprendre", json={
            "document_id": identifiant, "valeur": "   "})
        assert refus.status_code == 422
    finally:
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier.like("_ap5%")).delete(
                synchronize_session=False)
            session.commit()
        finally:
            session.close()


def test_le_symbole_colle_a_la_valeur_ne_fait_pas_echouer_la_verification():
    """
    On clique un mot entier — « 174.00€ », « FR-001 : » — et le motif s'arrête à
    la valeur. Exiger le caractère près ferait dire « ce n'est pas ce que vous
    avez désigné » à une règle parfaitement juste, et l'on n'oserait plus s'y
    fier. Cas relevé sur le document réel de la base.
    """
    proposition = apprentissage.proposer("Total TTC 174.00€\n", "174.00€", ancre="Total TTC")
    assert proposition["valeur_extraite"] == "174.00"
    assert proposition["conforme"] is True


def test_une_extraction_qui_prend_autre_chose_reste_signalee():
    """La souplesse ne doit pas aller jusqu'à valider n'importe quoi."""
    # Un intitulé qui se répète : la règle prend la première occurrence, qui
    # n'est pas celle qu'on a montrée. C'est exactement ce qu'il faut dire.
    texte = "Montant 145.00\nMontant 174.00\n"
    proposition = apprentissage.proposer(texte, "174.00", ancre="Montant")
    assert proposition["valeur_extraite"] == "145.00"
    assert proposition["conforme"] is False


def test_les_exemples_montrent_le_dernier_mois_puis_toute_la_ged(client):
    """
    Le sélecteur d'exemple est borné comme les autres (§22.26) : sans rien
    taper, **le dernier mois** ; au-delà, il faut chercher, et pas sur deux
    lettres.

    Mais il porte sur **toute la GED** et **toutes les colonnes** (§22.36) : on
    montre la valeur sur le document qu'on a sous la main, et l'on doit pouvoir
    le retrouver par ce qu'il porte — ici un champ extrait — et non seulement par
    son nom de fichier.
    """
    from datetime import datetime, timedelta

    from app.db import Categorie, Document, Metadonnee, SessionLocal

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ap6%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        recent = Document(nom_fichier="_ap6_recent.pdf", chemin_stockage="/tmp/_ap6a.pdf",
                          hash_sha256="_ap6a".ljust(64, "a"), texte_ocr=FACTURE,
                          statut="traite", categorie_id=type_doc.id,
                          date_import=datetime.now())
        ancien = Document(nom_fichier="_ap6_ancien.pdf", chemin_stockage="/tmp/_ap6b.pdf",
                          hash_sha256="_ap6b".ljust(64, "a"), texte_ocr=FACTURE,
                          statut="traite", categorie_id=type_doc.id,
                          date_import=datetime.now() - timedelta(days=90))
        session.add_all([recent, ancien])
        session.flush()
        # Une valeur qui n'est nulle part ailleurs : ni dans le nom, ni dans le
        # texte. Seule la colonne la porte.
        session.add(Metadonnee(document_id=ancien.id, cle="numero", valeur="ZORGLUB77"))
        session.commit()
        type_doc_id = type_doc.id
        autre = (session.query(Categorie)
                 .filter(Categorie.nature == "type", Categorie.id != type_doc_id).first())
        autre_type_id = autre.id
    finally:
        session.close()

    try:
        sans_terme = client.get("/admin/regles/exemples?limite=50")
        assert sans_terme.status_code == 200, sans_terme.text
        corps = sans_terme.json()
        assert corps["recents"] is True and corps["minimum_recherche"] == 3
        noms = [d["nom_fichier"] for d in corps["documents"]]
        assert "_ap6_recent.pdf" in noms
        assert "_ap6_ancien.pdf" not in noms   # trop ancien pour l'extrait

        # Peu importe la colonne : la valeur cherchée n'est que dans un champ.
        cherche = client.get("/admin/regles/exemples?q=ZORGLUB77").json()
        assert cherche["recents"] is False
        assert "_ap6_ancien.pdf" in [d["nom_fichier"] for d in cherche["documents"]]

        # Cadré sur le type, le même document sort encore : il y est rangé.
        dans_le_type = client.get(
            f"/admin/regles/exemples?q=ZORGLUB77&categorie_id={type_doc_id}").json()
        assert "_ap6_ancien.pdf" in [d["nom_fichier"] for d in dans_le_type["documents"]]

        # Cadré sur un **autre** type, il ne sort plus — mais la réponse dit
        # qu'il existe ailleurs, sans quoi on conclurait qu'il n'existe pas.
        ailleurs = client.get(
            f"/admin/regles/exemples?q=ZORGLUB77&categorie_id={autre_type_id}").json()
        assert ailleurs["documents"] == []
        assert ailleurs["ailleurs"] >= 1

        assert client.get(
            "/admin/regles/exemples?categorie_id=999999").status_code == 404
    finally:
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier.like("_ap6%")).delete(
                synchronize_session=False)
            session.commit()
        finally:
            session.close()


def test_on_apprend_aussi_sur_un_texte_sans_document(client):
    """
    Un exemple importé n'entre pas au registre (§22.35) : il n'a pas
    d'identifiant, c'est son texte qui sert. Sans l'un ni l'autre, rien à lire.
    """
    reponse = client.post("/admin/regles/apprendre",
                          json={"texte": FACTURE, "valeur": "174.00",
                                "champ_cible": "montant_ttc"})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["conforme"] is True

    vide = client.post("/admin/regles/apprendre", json={"valeur": "174.00"})
    assert vide.status_code == 422


def test_un_exemple_importe_refuse_ce_qui_nest_pas_un_document(client):
    """Un .exe n'est pas un papier : le refus vient avant l'océrisation."""
    reponse = client.post("/admin/regles/exemple-importe",
                          files={"fichier": ("virus.exe", b"MZ", "application/octet-stream")})
    assert reponse.status_code == 422
    assert "Format" in reponse.json()["detail"]


def test_lapercu_dun_exemple_expire_se_dit(client):
    """
    Le dossier de passage est effacé au bout de deux heures : l'écran doit le
    dire, et non afficher une image cassée.
    """
    reponse = client.get("/admin/regles/exemple-importe/inconnu-mais-valide/apercu")
    assert reponse.status_code == 404


def test_un_exemple_importe_se_lit_se_journalise_et_sefface(client, tmp_path, monkeypatch):
    """
    La chaîne entière d'un exemple importé (§22.35) : océrisé, rendu, journalisé
    — et effacé par le serveur de travaux, sans jamais entrer au registre.
    """
    import os
    import subprocess
    import time
    from pathlib import Path

    from app import config, worker
    from app.db import Document, JournalAudit, SessionLocal

    monkeypatch.setattr(config, "DEPOTS_MANUELS_FOLDER", str(tmp_path / "depots"))

    postscript = tmp_path / "page.ps"
    postscript.write_text("%!PS\n/Helvetica findfont 12 scalefont setfont\n"
                          "72 700 moveto (Total TTC 174.00) show\nshowpage\n")
    pdf = tmp_path / "exemple.pdf"
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
                    f"-sOutputFile={pdf}", str(postscript)], check=True, capture_output=True)

    session = SessionLocal()
    try:
        avant = session.query(Document).count()
    finally:
        session.close()

    with open(pdf, "rb") as f:
        reponse = client.post("/admin/regles/exemple-importe",
                              files={"fichier": ("exemple.pdf", f.read(), "application/pdf")})
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert "174.00" in corps["texte"]
    assert corps["page"]["mots"], "les mots doivent être situés pour qu'on puisse les cliquer"

    image = client.get(f"/admin/regles/exemple-importe/{corps['jeton']}/apercu")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"

    session = SessionLocal()
    try:
        # Rien n'entre au registre : c'est un brouillon, pas une archive.
        assert session.query(Document).count() == avant
        # Mais un papier du foyer a été lu par le serveur, et cela se journalise.
        assert session.query(JournalAudit).filter(
            JournalAudit.action == "regle.exemple_importe").count() >= 1
    finally:
        session.close()

    dossier = Path(config.DEPOTS_MANUELS_FOLDER) / "apprentissage" / corps["jeton"]
    assert dossier.is_dir()
    vieux = time.time() - worker.DUREE_EXEMPLE_APPRENTISSAGE - 60
    os.utime(dossier, (vieux, vieux))
    assert worker.purger_exemples_apprentissage() == 1
    assert not dossier.exists()
