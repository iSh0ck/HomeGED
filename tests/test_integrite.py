"""
Le contrôle d'intégrité des archives (§21.3).

Nous posions une empreinte à l'import, et personne ne la revérifiait jamais. Une
archive familiale est censée durer vingt ans : un disque se dégrade, une
synchronisation se trompe de sens, et rien de cela ne prévient.
"""
import pytest

from app import integrite, pieces
from app.db import Categorie, Document, PieceDocument, SessionLocal


def _nettoyer():
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ig%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def archive(base_de_test, tmp_path):
    """
    Un document dont le fichier existe vraiment sur le disque, avec sa pièce
    principale — c'est elle que le contrôle relit depuis le §22.2 bis : un
    document ne porte pas de fichier en propre, il porte des pièces.
    """
    _nettoyer()
    fichier = tmp_path / "_ig_archive.pdf"
    fichier.write_bytes(b"%PDF-1.4 contenu d'origine")

    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
        document = Document(nom_fichier="_ig_archive.pdf", chemin_stockage=str(fichier),
                            hash_sha256="_ig".ljust(64, "i"), texte_ocr="x",
                            statut="traite", categorie_id=type_doc.id)
        integrite.poser(document, str(fichier))
        session.add(document)
        session.flush()
        piece = pieces.ajouter(session, document, str(fichier), "_ig_archive.pdf",
                               document.hash_sha256, texte="x", principale_=True)
        integrite.poser(piece, str(fichier))
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    yield identifiant, fichier
    _nettoyer()


def _etat(identifiant):
    """L'état du document — qui est celui de sa pièce principale, recopié."""
    session = SessionLocal()
    try:
        document = session.get(Document, identifiant)
        return document.integrite, document.empreinte_archive
    finally:
        session.close()


def _etat_piece(identifiant):
    """L'état de la pièce elle-même : c'est elle que le contrôle relit."""
    session = SessionLocal()
    try:
        piece = session.query(PieceDocument).filter_by(document_id=identifiant).first()
        return piece.integrite, piece.empreinte_archive
    finally:
        session.close()


def test_lempreinte_controlee_est_celle_de_larchive(archive):
    """
    Et non celle du fichier reçu : l'océrisation et la compression réécrivent le
    fichier. Les confondre signalerait une altération sur chaque document, ce qui
    revient à n'en signaler aucune.
    """
    identifiant, _ = archive
    etat, empreinte_archive = _etat(identifiant)
    session = SessionLocal()
    try:
        assert empreinte_archive != session.get(Document, identifiant).hash_sha256
    finally:
        session.close()
    assert etat == integrite.OK


def test_une_archive_intacte_reste_conforme(archive):
    identifiant, _ = archive
    session = SessionLocal()
    try:
        bilan = integrite.controler(session, lot=50)
        session.commit()
    finally:
        session.close()
    # Sur mon document, et non sur toute la base : les autres fichiers de test
    # portent des chemins qui n'existent pas, et le contrôle a raison de le dire.
    assert not any(a["id"] == identifiant for a in bilan["anomalies"])
    assert _etat(identifiant)[0] == integrite.OK


def test_un_octet_change_est_signale(archive):
    """C'est tout l'objet : un fichier qui bouge sans qu'on l'ait demandé."""
    identifiant, fichier = archive
    fichier.write_bytes(b"%PDF-1.4 contenu ALTERE")

    session = SessionLocal()
    try:
        bilan = integrite.controler(session, lot=50)
        session.commit()
    finally:
        session.close()

    signale = next(a for a in bilan["anomalies"] if a["id"] == identifiant)
    assert signale["etat"] == integrite.ALTEREE
    assert signale["attendu"] != signale["trouve"]
    assert _etat(identifiant)[0] == integrite.ALTEREE


def test_un_fichier_disparu_est_signale_aussi(archive):
    identifiant, fichier = archive
    fichier.unlink()

    session = SessionLocal()
    try:
        bilan = integrite.controler(session, lot=50)
        session.commit()
    finally:
        session.close()

    assert any(a["id"] == identifiant and a["etat"] == integrite.ABSENT
               for a in bilan["anomalies"])


def test_une_premiere_rencontre_nest_pas_une_verification(archive):
    """
    Un document archivé avant ce contrôle n'a pas d'empreinte de référence : on
    la pose, et on le dit. Prétendre l'avoir vérifié serait faux — le fichier a
    pu être abîmé la veille.
    """
    identifiant, _ = archive
    session = SessionLocal()
    try:
        session.query(PieceDocument).filter_by(document_id=identifiant).first() \
            .empreinte_archive = None
        session.commit()
        bilan = integrite.controler(session, lot=50)
        session.commit()
    finally:
        session.close()

    assert bilan["adoptees"] >= 1
    assert _etat_piece(identifiant)[1] is not None, "la référence est posée"
    assert not any(a["id"] == identifiant for a in bilan["anomalies"]), \
        "et rien n'est signalé : on n'a rien vérifié"


def test_les_moins_recemment_controlees_dabord(archive):
    """Sans cet ordre, le contrôle repasserait sur les mêmes et l'archive
    entière ne serait jamais parcourue."""
    from datetime import datetime, timedelta

    identifiant, _ = archive
    session = SessionLocal()
    try:
        mienne = session.query(PieceDocument).filter_by(document_id=identifiant).first()
        mienne.date_controle = datetime.now() - timedelta(days=365)
        # Sans microsecondes : la colonne DATETIME les tronque, et une
        # comparaison stricte échouerait sur la fraction de seconde perdue.
        recent = datetime.now().replace(microsecond=0)
        autres = (session.query(PieceDocument)
                  .filter(PieceDocument.document_id != identifiant)
                  .limit(5).all())
        for autre in autres:
            autre.date_controle = recent
        session.commit()
        identifiants_autres = [a.id for a in autres]

        identifiant_mien = mienne.id
        integrite.controler(session, lot=1)
        session.commit()
        session.expire_all()
        mienne = session.get(PieceDocument, identifiant_mien)

        # la vieille a été reprise…
        assert session.get(PieceDocument, mienne.id).date_controle >= recent
        # …et aucune des récentes n'a été touchée : une seule tenait dans le lot
        for autre_id in identifiants_autres:
            assert session.get(PieceDocument, autre_id).date_controle == recent
    finally:
        session.close()


def test_un_document_en_corbeille_nest_pas_controle(archive):
    """Il peut être purgé demain : relire son fichier serait du travail perdu."""
    from datetime import datetime

    identifiant, fichier = archive
    fichier.write_bytes(b"altere")
    session = SessionLocal()
    try:
        session.get(Document, identifiant).date_suppression = datetime.now()
        session.commit()
        bilan = integrite.controler(session, lot=50)
        session.commit()
    finally:
        session.close()
    assert not any(a["id"] == identifiant for a in bilan["anomalies"])


def test_le_resume_nomme_les_documents_en_cause(client, archive):
    identifiant, fichier = archive
    fichier.write_bytes(b"encore autre chose")

    lance = client.post("/admin/integrite/controler")
    assert lance.status_code == 200, lance.text

    etat = client.get("/admin/integrite").json()
    assert etat["alterees"] >= 1
    signale = next(a for a in etat["anomalies"] if a["id"] == identifiant)
    assert signale["libelle_etat"] == "altérée"
    assert signale["nom_fichier"] == "_ig_archive.pdf"


def test_le_reglage_a_zero_arrete_le_controle(base_de_test):
    session = SessionLocal()
    try:
        assert integrite.controler(session, lot=0) == {"controles": 0, "adoptees": 0,
                                                       "anomalies": []}
    finally:
        session.close()


def test_une_piece_jointe_est_surveillee_elle_aussi(archive, tmp_path):
    """
    L'oubli du §22.2 : le contrôle ne relisait que le fichier principal. Une
    garantie jointe s'abîme pourtant comme une facture, et personne ne l'ouvre
    pendant des années — c'est exactement le cas que ce contrôle existe pour
    attraper.
    """
    identifiant, _ = archive
    jointe = tmp_path / "_ig_garantie.pdf"
    jointe.write_bytes(b"%PDF-1.4 garantie d'origine")

    session = SessionLocal()
    try:
        document = session.get(Document, identifiant)
        piece = pieces.ajouter(session, document, str(jointe), "_ig_garantie.pdf",
                               "_iggar".ljust(64, "g"), texte="garantie")
        integrite.poser(piece, str(jointe))
        session.commit()
        piece_id = piece.id
    finally:
        session.close()

    jointe.write_bytes(b"%PDF-1.4 garantie ALTEREE")
    session = SessionLocal()
    try:
        bilan = integrite.controler(session, lot=50)
        session.commit()
    finally:
        session.close()

    signalee = next(a for a in bilan["anomalies"] if a.get("piece_id") == piece_id)
    assert signalee["etat"] == integrite.ALTEREE
    assert signalee["id"] == identifiant, "l'anomalie se nomme par le document qu'on ouvrira"
    assert signalee["principale"] is False

    # le document, lui, n'est pas dit altéré : c'est sa pièce jointe qui l'est,
    # et confondre les deux ferait douter d'un fichier parfaitement sain
    assert _etat(identifiant)[0] == integrite.OK
