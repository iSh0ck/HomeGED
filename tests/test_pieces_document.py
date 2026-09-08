"""
Un document porte plusieurs pièces (§22.2).

Un document **était** un fichier : réunir une facture, sa garantie et le bon de
livraison demandait trois documents et un lien entre eux — trois fiches à
remplir, trois classements à décider, pour un seul achat. Une fiche porte
désormais N fichiers, comme le « docpak » d'EzGED.

Une pièce n'est pas une version : la version est le **même papier redéposé**
(§18.36), la pièce est un **autre papier du même dossier**. Ces tests portent
surtout sur ce qui doit rester vrai quoi qu'il arrive : il y a toujours une
pièce principale et une seule, le document reflète son fichier, et le texte
cherché est celui de toutes les pièces.
"""
import pytest

from app import pieces
from app.db import Categorie, Document, Job, PieceDocument, SessionLocal

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture
def facture(base_de_test, tmp_path):
    """Un document archivé, avec la pièce que la migration lui donne."""
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_pc%")).delete(
            synchronize_session=False)
        session.commit()
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        archive = tmp_path / "_pc_facture.pdf"
        archive.write_bytes(PDF)
        document = Document(nom_fichier="_pc_facture.pdf", chemin_stockage=str(archive),
                            hash_sha256="piece".ljust(64, "a"), texte_ocr="facture orange",
                            statut="traite", categorie_id=type_doc.id)
        session.add(document)
        session.flush()
        pieces.ajouter(session, document, str(archive), "_pc_facture.pdf",
                       document.hash_sha256, texte="facture orange", principale_=True)
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    yield identifiant

    session = SessionLocal()
    try:
        session.query(Job).filter(Job.piece_pour_document_id == identifiant).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.id == identifiant).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _joindre(session, document_id, nom, empreinte, texte, tmp_path):
    """Une pièce de plus, comme le serveur de travaux l'ajouterait une fois archivée."""
    archive = tmp_path / nom
    archive.write_bytes(PDF)
    document = session.get(Document, document_id)
    return pieces.ajouter(session, document, str(archive), nom, empreinte, texte=texte)


# ------------------------------------------------------------------
# Le modèle
# ------------------------------------------------------------------

def test_un_document_a_toujours_une_piece_principale(facture):
    session = SessionLocal()
    try:
        document = session.get(Document, facture)
        principale = pieces.principale(session, document)
        assert principale is not None
        assert principale.chemin_stockage == document.chemin_stockage
    finally:
        session.close()


def test_une_piece_jointe_ne_prend_pas_la_place_de_la_principale(facture, tmp_path):
    """
    C'est toute la différence avec une version : la garantie ne remplace pas la
    facture, elle s'ajoute à côté.
    """
    session = SessionLocal()
    try:
        avant = session.get(Document, facture).chemin_stockage
        _joindre(session, facture, "_pc_garantie.pdf", "garantie".ljust(64, "b"),
                 "garantie deux ans", tmp_path)
        session.commit()

        document = session.get(Document, facture)
        assert document.chemin_stockage == avant, "le document ouvre toujours sa facture"
        toutes = pieces.lister(session, document)
        assert [p.ordre for p in toutes] == [1, 2]
        assert [p.principale for p in toutes] == [True, False]
    finally:
        session.close()


def test_le_texte_cherche_est_celui_de_toutes_les_pieces(facture, tmp_path):
    """
    Sans cela, chercher « garantie » ne ramènerait pas la facture à laquelle elle
    est jointe — et c'est pourtant la question qu'on se pose en la cherchant.
    """
    session = SessionLocal()
    try:
        _joindre(session, facture, "_pc_garantie.pdf", "garantie".ljust(64, "b"),
                 "garantie deux ans", tmp_path)
        session.commit()
        texte = session.get(Document, facture).texte_ocr
        assert "facture orange" in texte and "garantie deux ans" in texte
    finally:
        session.close()


def test_changer_de_piece_principale_change_ce_quon_ouvre(facture, tmp_path):
    session = SessionLocal()
    try:
        jointe = _joindre(session, facture, "_pc_contrat.pdf", "contrat".ljust(64, "c"),
                          "contrat signé", tmp_path)
        document = session.get(Document, facture)
        pieces.definir_principale(session, document, jointe)
        session.commit()

        document = session.get(Document, facture)
        assert document.chemin_stockage == jointe.chemin_stockage
        assert document.nom_fichier == "_pc_contrat.pdf"
        assert document.hash_sha256 == jointe.hash_sha256
        # une seule principale, toujours
        assert [p.principale for p in pieces.lister(session, document)].count(True) == 1
    finally:
        session.close()


def test_la_derniere_piece_ne_se_retire_pas(facture):
    """Un document sans fichier n'est plus un document : pour s'en défaire, on le
    jette — la corbeille est faite pour ça, et elle se restaure."""
    session = SessionLocal()
    try:
        document = session.get(Document, facture)
        seule = pieces.lister(session, document)[0]
        with pytest.raises(pieces.PieceRefusee) as refus:
            pieces.retirer(session, document, seule)
        assert "corbeille" in str(refus.value)
    finally:
        session.rollback()
        session.close()


def test_retirer_la_principale_en_designe_une_autre(facture, tmp_path):
    """Le document doit toujours avoir un fichier à ouvrir, quoi qu'on retire."""
    session = SessionLocal()
    try:
        jointe = _joindre(session, facture, "_pc_bon.pdf", "bon".ljust(64, "d"),
                          "bon de livraison", tmp_path)
        document = session.get(Document, facture)
        principale = pieces.principale(session, document)
        pieces.retirer(session, document, principale)
        session.commit()

        document = session.get(Document, facture)
        restantes = pieces.lister(session, document)
        assert len(restantes) == 1
        assert restantes[0].id == jointe.id and restantes[0].principale
        assert document.chemin_stockage == jointe.chemin_stockage
        assert "bon de livraison" in document.texte_ocr
        assert "facture orange" not in document.texte_ocr, \
            "le texte d'une pièce retirée ne doit plus faire trouver le document"
    finally:
        session.close()


def test_les_pieces_se_rangent_dans_lordre_voulu(facture, tmp_path):
    session = SessionLocal()
    try:
        deux = _joindre(session, facture, "_pc_deux.pdf", "deux".ljust(64, "e"), "deux",
                        tmp_path)
        trois = _joindre(session, facture, "_pc_trois.pdf", "trois".ljust(64, "f"), "trois",
                         tmp_path)
        document = session.get(Document, facture)
        # une liste partielle ne doit pas faire disparaître les autres
        rangees = pieces.reordonner(session, document, [trois.id, deux.id])
        session.commit()
        assert [p.id for p in rangees][:2] == [trois.id, deux.id]
        assert len(rangees) == 3
    finally:
        session.close()


def test_une_version_remplace_le_fichier_de_la_piece_principale(facture, tmp_path):
    """
    Le même papier rescanné prend la place de celui qu'il remplace, **là où il
    était**. Sans cela le document pointerait le nouveau fichier et sa pièce
    l'ancien : la vignette montrerait le scan d'avant.
    """
    from app import versions

    session = SessionLocal()
    try:
        nouveau = tmp_path / "_pc_facture_v2.pdf"
        nouveau.write_bytes(PDF)
        document = session.get(Document, facture)
        versions.enregistrer_depot(session, document, str(nouveau), "_pc_facture_v2.pdf",
                                   "versionb".ljust(64, "g"))
        session.commit()

        document = session.get(Document, facture)
        principale = pieces.principale(session, document)
        assert principale.chemin_stockage == str(nouveau)
        assert principale.hash_sha256 == "versionb".ljust(64, "g")
        assert document.chemin_stockage == str(nouveau)
    finally:
        session.close()


# ------------------------------------------------------------------
# Ce que l'écran demande
# ------------------------------------------------------------------

def test_lapi_rend_les_pieces_dans_lordre(client, facture, tmp_path):
    session = SessionLocal()
    try:
        _joindre(session, facture, "_pc_garantie.pdf", "garantie".ljust(64, "b"),
                 "garantie", tmp_path)
        session.commit()
    finally:
        session.close()

    reponse = client.get(f"/documents/{facture}/pieces")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert [p["nom_fichier"] for p in corps] == ["_pc_facture.pdf", "_pc_garantie.pdf"]
    assert [p["principale"] for p in corps] == [True, False]


def test_une_piece_se_lit_dans_le_navigateur(client, facture):
    """Servie pour être regardée : type réel et disposition « inline », comme le
    fichier reçu d'un travail (§22.1b)."""
    piece = client.get(f"/documents/{facture}/pieces").json()[0]
    reponse = client.get(f"/documents/{facture}/pieces/{piece['id']}/fichier")

    assert reponse.status_code == 200, reponse.text
    assert reponse.headers["content-type"] == "application/pdf"
    assert reponse.headers["content-disposition"].startswith("inline")


def test_une_piece_dun_autre_document_est_introuvable(client, facture, tmp_path):
    """Le numéro d'une pièce ne suffit pas : elle doit appartenir au document
    qu'on regarde, sans quoi les droits du document ne voudraient plus rien dire."""
    session = SessionLocal()
    try:
        autre = Document(nom_fichier="_pc_autre.pdf", chemin_stockage="/tmp/_pc_autre.pdf",
                         hash_sha256="autre".ljust(64, "z"), texte_ocr="x", statut="traite")
        session.add(autre)
        session.flush()
        etrangere = _joindre(session, autre.id, "_pc_etrangere.pdf",
                             "etrangere".ljust(64, "y"), "x", tmp_path)
        session.commit()
        identifiant = etrangere.id
        autre_id = autre.id
    finally:
        session.close()

    try:
        refus = client.get(f"/documents/{facture}/pieces/{identifiant}/fichier")
        assert refus.status_code == 404
    finally:
        session = SessionLocal()
        session.query(Document).filter(Document.id == autre_id).delete()
        session.commit()
        session.close()


def test_joindre_une_piece_cree_un_travail_qui_vise_le_document(client, facture):
    """
    L'API dépose le fichier et passe la main ; le travail porte la consigne —
    « celui-ci va au document nº12 » —, car ni le dossier ni le fichier ne le
    disent.
    """
    reponse = client.post(f"/documents/{facture}/pieces",
                          files={"fichier": ("garantie.pdf", PDF, "application/pdf")})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["document_id"] == facture

    session = SessionLocal()
    try:
        travail = session.get(Job, reponse.json()["job_id"])
        assert travail.statut == "en_attente"
        assert travail.piece_pour_document_id == facture
    finally:
        session.close()


def test_designer_la_piece_principale_depuis_lecran(client, facture, tmp_path):
    session = SessionLocal()
    try:
        jointe = _joindre(session, facture, "_pc_contrat.pdf", "contrat".ljust(64, "c"),
                          "contrat", tmp_path)
        session.commit()
        identifiant = jointe.id
    finally:
        session.close()

    reponse = client.put(f"/documents/{facture}/pieces/{identifiant}/principale")
    assert reponse.status_code == 200, reponse.text
    principales = [p for p in reponse.json() if p["principale"]]
    assert len(principales) == 1 and principales[0]["id"] == identifiant


def test_retirer_une_piece_depuis_lecran(client, facture, tmp_path):
    session = SessionLocal()
    try:
        jointe = _joindre(session, facture, "_pc_bon.pdf", "bon".ljust(64, "d"), "bon",
                          tmp_path)
        session.commit()
        identifiant = jointe.id
    finally:
        session.close()

    reponse = client.delete(f"/documents/{facture}/pieces/{identifiant}")
    assert reponse.status_code == 200, reponse.text
    assert [p["id"] for p in reponse.json()["pieces"]] != [identifiant]

    refus = client.delete(f"/documents/{facture}/pieces/"
                          f"{client.get(f'/documents/{facture}/pieces').json()[0]['id']}")
    assert refus.status_code == 400, "la dernière pièce ne se retire pas"


# ------------------------------------------------------------------
# Pièce ou version ? (§22.3)
#
# La seule question qu'on ne puisse pas deviner : le même PDF est une pièce de
# plus ou une nouvelle version d'une pièce existante selon ce qu'on vient de
# faire. On la pose donc au dépôt.
# ------------------------------------------------------------------

def test_le_depot_dit_sil_remplace_une_piece(client, facture):
    """Sans consigne, c'est une pièce de plus — le cas courant."""
    piece = client.get(f"/documents/{facture}/pieces").json()[0]

    ajout = client.post(f"/documents/{facture}/pieces",
                        files={"fichier": ("garantie.pdf", PDF, "application/pdf")})
    assert ajout.status_code == 200, ajout.text
    assert ajout.json()["remplace_piece_id"] is None

    remplacement = client.post(f"/documents/{facture}/pieces",
                               files={"fichier": ("facture_v2.pdf", PDF, "application/pdf")},
                               data={"remplace_piece_id": piece["id"]})
    assert remplacement.status_code == 200, remplacement.text
    assert remplacement.json()["remplace_piece_id"] == piece["id"]

    session = SessionLocal()
    try:
        travail = session.get(Job, remplacement.json()["job_id"])
        assert travail.version_pour_piece_id == piece["id"]
        assert travail.piece_pour_document_id == facture
    finally:
        session.close()


def test_on_ne_remplace_pas_la_piece_dun_autre_document(client, facture):
    refus = client.post(f"/documents/{facture}/pieces",
                        files={"fichier": ("x.pdf", PDF, "application/pdf")},
                        data={"remplace_piece_id": 999999})
    assert refus.status_code == 404


def test_rescanner_une_piece_jointe_ne_touche_pas_a_la_principale(facture, tmp_path):
    """
    C'est tout l'enjeu du §22.3 : le document ouvre toujours sa facture, et c'est
    la garantie qui a changé — avec son propre historique.
    """
    from app import versions

    session = SessionLocal()
    try:
        jointe = _joindre(session, facture, "_pc_garantie.pdf", "garantie".ljust(64, "b"),
                          "garantie 2 ans", tmp_path)
        session.commit()
        avant = session.get(Document, facture).chemin_stockage

        rescan = tmp_path / "_pc_garantie_v2.pdf"
        rescan.write_bytes(PDF)
        document = session.get(Document, facture)
        versions.enregistrer_depot(session, document, str(rescan), "_pc_garantie_v2.pdf",
                                   "garantie2".ljust(64, "h"), piece=jointe)
        session.commit()

        document = session.get(Document, facture)
        assert document.chemin_stockage == avant, "le registre ouvre toujours la facture"
        jointe = session.get(PieceDocument, jointe.id)
        assert jointe.chemin_stockage == str(rescan)
        # l'historique est celui de cette pièce-là
        historique = versions.lister(session, facture, piece_id=jointe.id)
        assert [v["nom_fichier"] for v in historique][0] == "_pc_garantie_v2.pdf"
        assert len(historique) == 2, "l'original de la pièce et son rescan"
        assert all(v["piece_id"] == jointe.id for v in historique)
    finally:
        session.close()


def test_lhistorique_du_document_reste_celui_de_toutes_ses_pieces(facture, tmp_path):
    """
    Chaque pièce a son historique, et le document les rassemble : on peut vouloir
    voir tous les dépôts d'un dossier, sans avoir à ouvrir chaque pièce.
    """
    from app import versions

    session = SessionLocal()
    try:
        jointe = _joindre(session, facture, "_pc_bon.pdf", "bon".ljust(64, "d"), "bon",
                          tmp_path)
        document = session.get(Document, facture)
        # un dépôt sur chacune des deux pièces
        versions.enregistrer_depot(session, document, str(tmp_path / "_pc_bon.pdf"),
                                   "_pc_bon.pdf", "bon".ljust(64, "d"), piece=jointe)
        principale = pieces.principale(session, document)
        rescan = tmp_path / "_pc_facture_v2.pdf"
        rescan.write_bytes(PDF)
        versions.enregistrer_depot(session, document, str(rescan), "_pc_facture_v2.pdf",
                                   "facturev2".ljust(64, "i"), piece=principale)
        session.commit()

        tout = versions.lister(session, facture)
        assert len({v["piece_id"] for v in tout}) == 2, \
            "l'historique du document rassemble celui de ses deux pièces"
        assert len(versions.lister(session, facture, piece_id=jointe.id)) == 1, \
            "celui d'une pièce ne contient que ses dépôts à elle"
    finally:
        session.close()
