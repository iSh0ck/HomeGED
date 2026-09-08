"""
Le journal des consultations (§21.16).

Nous ne consignions que le dépôt, la modification et la suppression — ce qui
**change** un document, jamais ce qui le regarde. Or savoir qui a ouvert un
papier est le propre d'une GED, et dans une maison c'est souvent la lecture qui
compte : qui a consulté l'acte notarié, et quand.
"""
from datetime import datetime, timedelta

import pytest

from app import audit, reglages, worker
from app.db import Categorie, Document, JournalAudit, SessionLocal, Utilisateur


@pytest.fixture
def document(base_de_test):
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_cs%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        doc = Document(nom_fichier="_cs_acte.pdf", chemin_stockage="/tmp/_cs_acte.pdf",
                       hash_sha256="_cs".ljust(64, "c"), texte_ocr="x",
                       statut="traite", categorie_id=type_doc.id)
        session.add(doc)
        session.commit()
        identifiant = doc.id
    finally:
        session.close()

    yield identifiant

    session = SessionLocal()
    try:
        session.query(JournalAudit).filter(
            JournalAudit.objet_type == "document",
            JournalAudit.objet_id == identifiant).delete(synchronize_session=False)
        session.query(Document).filter(Document.id == identifiant).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _consultations(document_id):
    session = SessionLocal()
    try:
        return (session.query(JournalAudit)
                .filter(JournalAudit.action == audit.CONSULTATION,
                        JournalAudit.objet_id == document_id)
                .all())
    finally:
        session.close()


def test_ouvrir_un_document_laisse_une_trace(client, document):
    assert client.get(f"/documents/{document}").status_code == 200

    traces = _consultations(document)
    assert len(traces) == 1
    assert traces[0].utilisateur_email, "on trace qui, pas seulement quand"
    assert traces[0].objet_type == "document"


def test_rouvrir_dans_la_foulee_nen_ajoute_pas_une_autre(client, document):
    """
    Ouvrir une fiche, la refermer, la rouvrir pour vérifier une ligne est un seul
    geste. Vingt lignes identiques ne diraient rien de plus, et noieraient
    l'information que l'historique porte.
    """
    for _ in range(4):
        client.get(f"/documents/{document}")
    assert len(_consultations(document)) == 1


def test_une_lecture_plus_tard_est_une_autre_lecture(client, document):
    client.get(f"/documents/{document}")

    session = SessionLocal()
    try:
        trace = (session.query(JournalAudit)
                 .filter(JournalAudit.action == audit.CONSULTATION,
                         JournalAudit.objet_id == document).one())
        trace.date_evenement = datetime.now() - audit.FENETRE_CONSULTATION - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    client.get(f"/documents/{document}")
    assert len(_consultations(document)) == 2


def test_la_consultation_se_lit_dans_lhistorique_du_document(client, document):
    client.get(f"/documents/{document}")
    journal = client.get(f"/documents/{document}/journal").json()
    assert any(e["action"] == audit.CONSULTATION for e in journal["evenements"]), \
        "l'historique d'une fiche doit dire qui l'a ouverte"


def test_les_consultations_se_purgent_sans_toucher_au_reste(client, document):
    """
    Elles sont nombreuses et vieillissent vite ; le reste de l'histoire d'un
    document — dépôt, modification, suppression — n'est jamais purgé.
    """
    session = SessionLocal()
    try:
        # Les deux rétentions sont posées explicitement : la suite partage sa
        # base entre fichiers, et un test voisin qui aurait laissé une purge du
        # journal active ferait dépendre celui-ci de l'ordre d'exécution.
        reglages.enregistrer(session, {"retention_consultations_jours": "30",
                                       "retention_journal_jours": "0"})
        # Un compte qui existe **au moment du test**, et non « l'utilisateur nº1 » :
        # la base est partagée entre fichiers, un voisin peut avoir recréé les
        # comptes, et la clé étrangère du journal refusait alors l'insertion.
        auteur = session.query(Utilisateur.id).order_by(Utilisateur.id).first()[0]
        vieille = JournalAudit(action=audit.CONSULTATION, objet_type="document",
                               objet_id=document, utilisateur_id=auteur,
                               date_evenement=datetime.now() - timedelta(days=90))
        depot = JournalAudit(action="document.depot", objet_type="document",
                             objet_id=document, utilisateur_id=auteur,
                             date_evenement=datetime.now() - timedelta(days=90))
        session.add_all([vieille, depot])
        session.commit()
        identifiants = (vieille.id, depot.id)
    finally:
        session.close()

    # Relu juste avant la purge : la suite partage sa base entre fichiers, et un
    # test voisin qui aurait réécrit ce réglage rendrait l'échec incompréhensible.
    session = SessionLocal()
    try:
        assert reglages.entier(session, "retention_consultations_jours") == 30
        assert reglages.entier(session, "retention_journal_jours") == 0
    finally:
        session.close()

    worker.purger_journal_ancien()

    session = SessionLocal()
    try:
        assert session.get(JournalAudit, identifiants[0]) is None, "la lecture ancienne part"
        assert session.get(JournalAudit, identifiants[1]) is not None, \
            "le dépôt reste : c'est l'histoire du document"
    finally:
        session.close()
        session = SessionLocal()
        reglages.enregistrer(session, {"retention_consultations_jours": "365",
                                       "retention_journal_jours": "0"})
        session.commit()
        session.close()
