"""
La corbeille des documents (§21.1).

Supprimer effaçait sur-le-champ, dans une maison où chacun a le droit de
supprimer : une fausse manœuvre ne se rattrapait pas. Un document supprimé est
désormais **daté**, pas effacé — il quitte le registre et revient à sa place.
"""
import pytest

from app.db import Categorie, Document, Metadonnee, SessionLocal


def _nettoyer():
    """
    Une session neuve à chaque fois : celle qui a créé le document ne l'a plus vu
    changer, et MariaDB refuse d'écrire par-dessus une lecture périmée.
    """
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_cb%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def document_jetable(base_de_test):
    _nettoyer()
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        document = Document(nom_fichier="_cb_facture.pdf", chemin_stockage="/tmp/_cb.pdf",
                            hash_sha256="_cb".ljust(64, "c"), texte_ocr="corbeille",
                            statut="traite", categorie_id=type_doc.id)
        session.add(document)
        session.flush()
        session.add(Metadonnee(document_id=document.id, cle="_cb_cle", valeur="gardee"))
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    yield identifiant
    _nettoyer()


def test_supprimer_ne_detruit_plus_rien(client, document_jetable):
    assert client.delete(f"/documents/{document_jetable}").status_code == 200

    session = SessionLocal()
    try:
        doc = session.get(Document, document_jetable)
        assert doc is not None, "la fiche reste : c'est tout l'objet de la corbeille"
        assert doc.date_suppression is not None
        assert len(doc.metadonnees) == 1, "ses métadonnées l'attendent"
    finally:
        session.close()


def test_le_registre_ne_le_montre_plus(client, document_jetable):
    avant = {d["id"] for d in client.get("/documents").json()}
    assert document_jetable in avant

    client.delete(f"/documents/{document_jetable}")
    assert document_jetable not in {d["id"] for d in client.get("/documents").json()}
    # ni par la recherche plein texte, ni par son identifiant direct
    assert document_jetable not in {d["id"] for d in client.get("/documents?q=corbeille").json()}
    assert client.get(f"/documents/{document_jetable}").status_code == 404


def test_il_attend_dans_ma_corbeille_et_revient_a_sa_place(client, document_jetable):
    client.delete(f"/documents/{document_jetable}")

    corbeille = client.get("/corbeille").json()["documents"]
    ligne = next(d for d in corbeille if d["id"] == document_jetable)
    assert ligne["supprime_par"], "on doit savoir qui l'a jeté"
    assert ligne["categorie"], "et d'où il vient, pour le reconnaître"

    assert client.post(f"/corbeille/{document_jetable}/restaurer").status_code == 200
    assert document_jetable in {d["id"] for d in client.get("/documents").json()}
    # il a quitté la corbeille (qui peut contenir ce que d'autres tests y ont mis)
    assert document_jetable not in {d["id"] for d in client.get("/corbeille").json()["documents"]}


def test_le_retirer_de_sa_corbeille_ne_detruit_pas(client, document_jetable):
    """
    Le second geste dit « je n'ai plus besoin de le voir ici », pas « qu'il
    disparaisse ». Une corbeille qui détruit au second clic n'est plus un filet.
    """
    client.delete(f"/documents/{document_jetable}")
    assert client.delete(f"/corbeille/{document_jetable}").status_code == 200

    assert document_jetable not in {d["id"] for d in client.get("/corbeille").json()["documents"]}, \
        "il quitte ma vue"
    admin = client.get("/admin/documents-supprimes").json()
    ligne = next(d for d in admin if d["id"] == document_jetable)
    assert ligne["masquee"] is True, "l'administration le voit encore"

    session = SessionLocal()
    try:
        assert session.get(Document, document_jetable) is not None
    finally:
        session.close()


def test_ladministration_rattrape_le_geste_de_trop(client, document_jetable):
    client.delete(f"/documents/{document_jetable}")
    client.delete(f"/corbeille/{document_jetable}")

    assert client.post(
        f"/admin/documents-supprimes/{document_jetable}/restaurer").status_code == 200
    assert document_jetable in {d["id"] for d in client.get("/documents").json()}


def test_leffacement_definitif_est_reserve_a_ladministration(client, document_jetable):
    client.delete(f"/documents/{document_jetable}")
    assert client.delete(
        f"/admin/documents-supprimes/{document_jetable}").status_code == 200

    session = SessionLocal()
    try:
        assert session.get(Document, document_jetable) is None
        # le fichier, lui, n'est pas détruit ici : plus aucun document ne le
        # référence, le serveur de travaux le mettra de côté
    finally:
        session.close()


def test_on_ne_restaure_pas_un_document_vivant(client, document_jetable):
    assert client.post(f"/corbeille/{document_jetable}/restaurer").status_code == 404


def test_la_purge_automatique_respecte_le_delai(client, document_jetable):
    from datetime import datetime, timedelta

    from app import reglages, worker

    client.delete(f"/documents/{document_jetable}")
    session = SessionLocal()
    try:
        avant = reglages.entier(session, "retention_documents_supprimes_jours")
        # jeté il y a dix jours
        session.get(Document, document_jetable).date_suppression = \
            datetime.now() - timedelta(days=10)
        session.commit()

        reglages.enregistrer(session, {"retention_documents_supprimes_jours": "0"})
        session.commit()
        assert worker.purger_documents_supprimes() == 0, "zéro veut dire jamais"

        reglages.enregistrer(session, {"retention_documents_supprimes_jours": "30"})
        session.commit()
        assert worker.purger_documents_supprimes() == 0, "pas encore l'heure"

        reglages.enregistrer(session, {"retention_documents_supprimes_jours": "7"})
        session.commit()
        assert worker.purger_documents_supprimes() >= 1
        session.expire_all()
        assert session.get(Document, document_jetable) is None
    finally:
        reglages.enregistrer(session, {"retention_documents_supprimes_jours": str(avant)})
        session.commit()
        session.close()


def test_tout_retirer_dun_coup(client, document_jetable):
    """
    Vider sa corbeille est un geste de **rangement** — on ne veut plus les voir
    là —, pas une destruction : les documents passent en masqué et
    l'administration les retrouve. C'est ce qui rend le bouton sans danger.
    """
    client.delete(f"/documents/{document_jetable}")
    assert document_jetable in {d["id"] for d in client.get("/corbeille").json()["documents"]}

    bilan = client.post("/corbeille/vider")
    assert bilan.status_code == 200, bilan.text
    assert bilan.json()["retires"] >= 1

    assert document_jetable not in {d["id"] for d in client.get("/corbeille").json()["documents"]}
    admin = client.get("/admin/documents-supprimes").json()
    ligne = next(d for d in admin if d["id"] == document_jetable)
    assert ligne["masquee"] is True, "l'administration les voit encore"

    session = SessionLocal()
    try:
        assert session.get(Document, document_jetable) is not None, "rien n'est détruit"
    finally:
        session.close()


def test_vider_une_corbeille_vide_ne_fait_rien(client):
    assert client.post("/corbeille/vider").json()["retires"] == 0


def test_la_corbeille_dit_ce_qu_on_restaure(client, base_de_test):
    """
    « Factures · supprimé il y a 3 min » ne dit pas **laquelle** on s'apprête à
    perdre, et c'est pourtant la seule question qu'on se pose devant une
    corbeille (§22.63). Chaque ligne porte donc les colonnes de son type, comme
    dans le registre — et qui l'a jetée.

    Son propre type, et non un emprunté à la base : régler les colonnes d'une
    catégorie partagée déborderait sur les autres tests.
    """
    _nettoyer()
    categorie = client.post("/admin/categories", json={"nom": "_CbCorbeille"}).json()
    session = SessionLocal()
    try:
        document = Document(nom_fichier="_cb_a_reconnaitre.pdf",
                            chemin_stockage="/tmp/_cb_reco.pdf",
                            hash_sha256="_cbreco".ljust(64, "d"), texte_ocr="x",
                            statut="traite", categorie_id=categorie["id"])
        session.add(document)
        session.flush()
        session.add(Metadonnee(document_id=document.id, cle="numero_facture",
                               valeur="FR-2026-042"))
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    try:
        # La colonne décide de ce qui se lit : sans elle, rien à montrer.
        pose = client.put(f"/admin/categories/{categorie['id']}/colonnes",
                          json=[{"champ": "meta:numero_facture"}])
        assert pose.status_code == 200, pose.text

        client.delete(f"/documents/{identifiant}")
        ligne = next(d for d in client.get("/corbeille").json()["documents"] if d["id"] == identifiant)

        assert ligne["supprime_par"], "on doit savoir qui a jeté"
        assert [{"libelle": d["libelle"], "valeur": d["valeur"]} for d in ligne["details"]] \
            == [{"libelle": "N° facture", "valeur": "FR-2026-042"}], ligne["details"]
    finally:
        _nettoyer()
        client.delete(f"/admin/categories/{categorie['id']}")


def test_la_corbeille_des_fichiers_dit_d_ou_ils_viennent(client, document_jetable):
    """
    Un nom et une taille ne disent pas ce qu'on détruit (§22.63). Le journal
    garde la chaîne — chemin de la corbeille, chemin d'origine, document — et la
    liste la remonte. Sans trace, elle le dit plutôt que de laisser une case vide.
    """
    fichiers = client.get("/admin/corbeille").json()["fichiers"]
    assert isinstance(fichiers, list)
    for fichier in fichiers:
        assert "origine" in fichier
        assert fichier["origine"] in (None, "document", "orphelin")
        if fichier["origine"] == "document":
            assert fichier["document_id"], fichier


def test_la_corbeille_se_pagine_et_dit_ce_qui_reste(client, base_de_test):
    """
    Un plafond dur à 500 rendait les plus anciens **invisibles et
    irrécupérables** depuis cet écran, sans que rien ne le dise (§22.90). Le
    décompte porte sur la corbeille entière : on sait toujours ce qui reste.
    """
    _nettoyer()
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        for rang in range(5):
            session.add(Document(
                nom_fichier=f"_cb_page_{rang}.pdf", chemin_stockage=f"/tmp/_cb{rang}.pdf",
                hash_sha256=f"_cbp{rang}".ljust(64, "e"), texte_ocr="x",
                statut="traite", categorie_id=type_doc.id))
        session.commit()
        identifiants = [d.id for d in session.query(Document)
                        .filter(Document.nom_fichier.like("_cb_page_%"))]
    finally:
        session.close()

    try:
        for identifiant in identifiants:
            client.delete(f"/documents/{identifiant}")

        page = client.get("/corbeille?limite=2&decalage=0").json()
        assert page["total"] >= 5, "le total porte sur la corbeille, pas sur la page"
        assert len(page["documents"]) == 2

        suite = client.get("/corbeille?limite=2&decalage=2").json()
        assert suite["total"] == page["total"]
        assert {d["id"] for d in suite["documents"]}.isdisjoint(
            {d["id"] for d in page["documents"]}), "deux pages, deux contenus"
    finally:
        _nettoyer()


def test_la_corbeille_des_fichiers_se_pagine(client):
    """Elle dit aussi la place occupée : c'est ce qu'on vient y récupérer."""
    page = client.get("/admin/corbeille?limite=2").json()
    assert set(page) == {"total", "octets", "fichiers"}
    assert len(page["fichiers"]) <= 2
    assert page["octets"] >= 0
