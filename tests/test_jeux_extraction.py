"""
Jeux de règles d'extraction, par type de document (§19.6).

Les règles formaient une liste unique appliquée à tout document. Elle grossit à
chaque émetteur — EDF n'écrit pas ses numéros comme Orange — et chaque règle
ajoutée devenait un risque pour les autres : une expression un peu large attrape
ce qui ne la regarde pas, sur des documents qu'on n'avait pas en tête.

Ces tests portent sur ce que le découpage garantit : une règle ne sort pas de son
type, un seul jeu s'applique à la fois, et l'on sait toujours lequel.
"""
import pytest

from app import categories as natures
from app.db import (
    Categorie, Document, Metadonnee, ProfilExtraction, RegleExtraction,
    SessionLocal,
)
from app.regex_engine import appliquer_regles, profil_applicable

TEXTE_ORANGE = "ORANGE SA\nFacture no OR-2026-001\nTotal TTC 30,00 EUR\n"
TEXTE_INCONNU = "FOURNISSEUR QUELCONQUE\nFacture no XX-2026-777\nTotal TTC 12,00 EUR\n"


@pytest.fixture
def jeux(base_de_test):
    """Un type « _JeuFactures », son jeu générique, et un jeu propre à Orange."""
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_jeu%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Jeu%")).delete(
            synchronize_session=False)
        type_doc = Categorie(nom="_JeuFactures", nature=natures.TYPE, ordre=950)
        autre = Categorie(nom="_JeuCourriers", nature=natures.TYPE, ordre=951)
        session.add_all([type_doc, autre])
        session.flush()

        specifique = ProfilExtraction(
            categorie_id=type_doc.id, nom="Facture Orange",
            reconnaissance=r"(?i)\bORANGE\b", priorite=10)
        generique = ProfilExtraction(
            categorie_id=type_doc.id, nom="Facture (générique)",
            generique=True, priorite=1000)
        session.add_all([specifique, generique])
        session.flush()

        session.add(RegleExtraction(
            profil_id=specifique.id, nom="N° Orange", champ_cible="numero_facture",
            pattern=r"(?i)facture\s+no\s+(OR-\S+)", type_champ="texte",
            actif=True, priorite=1))
        session.add(RegleExtraction(
            profil_id=generique.id, nom="N° générique", champ_cible="numero_facture",
            pattern=r"(?i)facture\s+no\s+(\S+)", type_champ="texte",
            actif=True, priorite=1))
        session.add(RegleExtraction(
            profil_id=generique.id, nom="Montant", champ_cible="montant_ttc",
            pattern=r"(?i)total\s+ttc\s+([0-9,.]+)", type_champ="montant",
            actif=True, priorite=2))
        session.commit()
        contexte = {"type": type_doc.id, "autre": autre.id,
                    "specifique": specifique.id, "generique": generique.id}
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_jeu%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Jeu%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _document(session, texte, categorie_id, nom="_jeu_doc.pdf"):
    document = Document(nom_fichier=nom, chemin_stockage="/x.pdf",
                        hash_sha256=nom.ljust(64, "j"), texte_ocr=texte,
                        statut="traite", categorie_id=categorie_id)
    session.add(document)
    session.flush()
    return document


def test_le_jeu_reconnu_lemporte(jeux):
    session = SessionLocal()
    try:
        document = _document(session, TEXTE_ORANGE, jeux["type"])
        profil = profil_applicable(session, document)
        assert profil.id == jeux["specifique"]
    finally:
        session.rollback()
        session.close()


def test_un_jeu_reconnu_est_seul_applique(jeux):
    """
    Décision D5 : ce qu'il ne trouve pas reste vide, et le document part au
    Centre d'analyse. Plus prévisible qu'un complément par le générique — on sait
    toujours quel jeu a produit une valeur.
    """
    session = SessionLocal()
    try:
        document = _document(session, TEXTE_ORANGE, jeux["type"])
        appliquer_regles(document, session)
        session.flush()
        valeurs = {m.cle: m.valeur for m in session.query(Metadonnee)
                   .filter_by(document_id=document.id)}
        assert valeurs["numero_facture"] == "OR-2026-001"
        assert "montant_ttc" not in valeurs, \
            "la règle du générique ne doit pas compléter un jeu reconnu"
    finally:
        session.rollback()
        session.close()


def test_a_defaut_de_reconnaissance_le_generique_sapplique(jeux):
    session = SessionLocal()
    try:
        document = _document(session, TEXTE_INCONNU, jeux["type"])
        appliquer_regles(document, session)
        session.flush()
        valeurs = {m.cle: m.valeur for m in session.query(Metadonnee)
                   .filter_by(document_id=document.id)}
        assert valeurs["numero_facture"] == "XX-2026-777"
        assert valeurs["montant_ttc"] == "12.00"
    finally:
        session.rollback()
        session.close()


# Un jeu ne pose plus d'émetteur (§21.12) : cette case en faisait le seul champ
# qu'une reconnaissance pouvait remplir sans passer par une règle, et elle ne
# valait que pour les factures. C'est la **déduction** du champ attendu qui s'en
# charge désormais — elle lit le document, au lieu de faire confiance au jeu.


def test_une_regle_ne_sort_pas_de_son_type(jeux):
    """
    Le cœur du §19.6 : une règle écrite pour les factures ne touche pas les
    courriers. C'est ce qui rend possible d'en écrire beaucoup sans qu'elles se
    gênent.
    """
    session = SessionLocal()
    try:
        document = _document(session, TEXTE_ORANGE, jeux["autre"], nom="_jeu_autre.pdf")
        assert profil_applicable(session, document) is None
        appliquer_regles(document, session)
        session.flush()
        assert session.query(Metadonnee).filter_by(document_id=document.id).count() == 0
    finally:
        session.rollback()
        session.close()


def test_un_document_sans_type_na_aucune_regle(jeux):
    session = SessionLocal()
    try:
        document = _document(session, TEXTE_ORANGE, None, nom="_jeu_sans_type.pdf")
        assert profil_applicable(session, document) is None
    finally:
        session.rollback()
        session.close()


def test_un_jeu_sans_reconnaissance_ni_generique_est_refuse(client, jeux):
    """Il ne serait jamais choisi : l'accepter reviendrait à cacher un réglage mort."""
    refus = client.post("/admin/jeux-extraction", json={
        "categorie_id": jeux["type"], "nom": "_Jeu muet"})
    assert refus.status_code == 422
    assert "jamais choisi" in refus.json()["detail"]


def test_un_second_jeu_generique_est_refuse(client, jeux):
    """On ne saurait pas lequel sert de repli."""
    refus = client.post("/admin/jeux-extraction", json={
        "categorie_id": jeux["type"], "nom": "_Jeu bis", "generique": True})
    assert refus.status_code == 409
    assert "générique" in refus.json()["detail"]


def test_un_jeu_ne_sattache_pas_a_un_dossier(client, jeux):
    session = SessionLocal()
    try:
        dossier = Categorie(nom="_JeuDossier", nature=natures.DOSSIER, ordre=952)
        session.add(dossier)
        session.commit()
        identifiant = dossier.id
    finally:
        session.close()

    refus = client.post("/admin/jeux-extraction", json={
        "categorie_id": identifiant, "nom": "_Jeu impossible", "generique": True})
    assert refus.status_code == 400


def test_supprimer_un_jeu_emporte_ses_regles(client, jeux):
    """Elles n'existaient que par lui : les laisser en ferait des orphelines sans effet."""
    reponse = client.delete(f"/admin/jeux-extraction/{jeux['specifique']}")
    assert reponse.status_code == 200
    assert reponse.json()["regles_supprimees"] == 1

    session = SessionLocal()
    try:
        assert session.query(RegleExtraction).filter_by(
            profil_id=jeux["specifique"]).count() == 0
    finally:
        session.close()


def test_lessai_dit_quel_jeu_sapplique(client, jeux):
    """
    Sans cela, on chercherait longtemps pourquoi une règle « ne marche pas » :
    elle marche, elle appartient simplement à un autre jeu.
    """
    session = SessionLocal()
    try:
        document = _document(session, TEXTE_ORANGE, jeux["type"], nom="_jeu_essai.pdf")
        session.commit()
        identifiant = document.id
    finally:
        session.close()

    essai = client.post(f"/documents/{identifiant}/tester-extraction").json()
    assert essai["jeu"]["id"] == jeux["specifique"]
    assert essai["jeu"]["reconnu"] is True
    assert [r["regle"] for r in essai["regles"]] == ["N° Orange"], \
        "l'essai ne montre que les règles du jeu qui s'applique"


def test_les_champs_cibles_ne_debordent_pas_sur_un_autre_type(client, base_de_test):
    """
    Un jeu générique appartient quand même à **son** type : compter ses règles
    pour un autre faisait dire « rempli tout seul » de ce que rien ne remplissait
    ici, et envoyait le raccourci « aller à la règle » chez le voisin (§22.28).
    """
    from app.db import Categorie, ProfilExtraction, RegleExtraction, SessionLocal

    session = SessionLocal()
    try:
        session.query(Categorie).filter(Categorie.nom.like("_Cb%")).delete(
            synchronize_session=False)
        types = []
        for nom in ("_CbIci", "_CbAilleurs"):
            categorie = Categorie(nom=nom, nature="type", ordre=975)
            session.add(categorie)
            session.flush()
            types.append(categorie.id)
        profil = ProfilExtraction(nom="_CbJeuAilleurs", categorie_id=types[1],
                                  generique=True, actif=True, priorite=100)
        session.add(profil)
        session.flush()
        session.add(RegleExtraction(profil_id=profil.id, nom="_CbRegle",
                                    champ_cible="_cb_ailleurs", pattern="x",
                                    type_champ="texte", priorite=100, actif=True))
        session.commit()
        identifiants = types
    finally:
        session.close()

    try:
        cibles = client.get(f"/admin/regles/champs-cibles?categorie_id={identifiants[0]}").json()
        assert not any(c["champ"] == "_cb_ailleurs" for c in cibles), \
            "la règle d'un autre type n'a rien à faire ici"

        chez_lui = client.get(
            f"/admin/regles/champs-cibles?categorie_id={identifiants[1]}").json()
        sienne = next(c for c in chez_lui if c["champ"] == "_cb_ailleurs")
        assert sienne["remplie_par_regle"] is True
        assert sienne["regles"][0]["nom"] == "_CbRegle", \
            "et l'on sait quelle règle ouvrir"
    finally:
        session = SessionLocal()
        try:
            session.query(Categorie).filter(Categorie.nom.like("_Cb%")).delete(
                synchronize_session=False)
            session.commit()
        finally:
            session.close()
