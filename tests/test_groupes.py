"""
Le repli du registre en arborescence (§21.6).

Un tableau plat de trois cents lignes se filtre colonne par colonne. Replié sur
un critère — l'année, l'émetteur, le véhicule concerné — il se parcourt sans
qu'on écrive un seul filtre.
"""
import json

import pytest
from sqlalchemy import text as sql

from app import groupes
from app.db import Categorie, Document, Metadonnee, SessionLocal


def _nettoyer():
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_gr%")).delete(
            synchronize_session=False)
        session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_GrEmetteur'"))
        session.execute(sql("DELETE FROM usr_membres WHERE nom = '_GrNom'"))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def documents_groupables(base_de_test):
    """Trois documents : deux de 2026, un de 2025 ; deux émetteurs."""
    _nettoyer()
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        # Un émetteur à soi : les autres fichiers de test déposent aussi des
        # documents datés de cette année-là, et un décompte partagé ne prouverait
        # rien sur l'enchaînement des niveaux. C'est une ligne de la table du
        # foyer, désignée par une métadonnée (§21.12).
        session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_GrEmetteur'"))
        session.execute(sql("INSERT INTO usr_emetteurs (nom) VALUES ('_GrEmetteur')"))
        emetteur = session.execute(sql(
            "SELECT id FROM usr_emetteurs WHERE nom = '_GrEmetteur'")).scalar()
        session.execute(sql("INSERT INTO usr_membres (nom, prenom) VALUES ('_GrNom', 'Ada')"))
        membre = session.execute(sql(
            "SELECT id FROM usr_membres WHERE nom = '_GrNom'")).scalar()

        crees = []
        for nom, date, avec_emetteur in (("_gr_a.pdf", "2026-04-02", True),
                                         ("_gr_b.pdf", "2026-11-20", True),
                                         ("_gr_c.pdf", "2025-01-15", False)):
            document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                                hash_sha256=nom.ljust(64, "g"), texte_ocr="x",
                                statut="traite", categorie_id=type_doc.id,
                                date_document=date)
            session.add(document)
            session.flush()
            session.add(Metadonnee(document_id=document.id, cle="titulaire",
                                   valeur=f"usr_membres:{membre}"))
            if avec_emetteur:
                session.add(Metadonnee(document_id=document.id, cle="emetteur",
                                       valeur=f"usr_emetteurs:{emetteur}"))
            crees.append(document.id)
        session.commit()
        yield crees, "_GrEmetteur", membre
    finally:
        session.close()
    _nettoyer()


def _branches(client, champ, **params):
    reponse = client.get("/groupes", params={"champ": champ, **params})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_les_dates_se_replient_par_annee(client, documents_groupables):
    """
    Grouper au jour près donnerait autant de branches que de documents : ce n'est
    plus un classement, c'est la liste elle-même, en plus lent.
    """
    par_annee = {b["libelle"]: b for b in _branches(client, "date_document")["branches"]}
    assert par_annee["2026"]["nombre"] >= 2
    assert par_annee["2025"]["nombre"] >= 1
    # et l'année devient un intervalle, sans quoi le critère ne trouverait que le
    # 1er janvier
    assert par_annee["2026"]["critere"]["operateur"] == "entre"


def test_une_branche_nest_quun_filtre(client, documents_groupables):
    crees, _, _ = documents_groupables
    branche = next(b for b in _branches(client, "date_document")["branches"]
                   if b["libelle"] == "2026")

    documents = client.get("/documents", params={
        "filtres": json.dumps([branche["critere"]])}).json()
    trouves = {d["id"] for d in documents}
    assert crees[0] in trouves and crees[1] in trouves
    assert crees[2] not in trouves, "le document de 2025 n'est pas dans cette branche"


def test_on_se_replie_aussi_sur_lemetteur(client, documents_groupables):
    _, nom_emetteur, _ = documents_groupables
    branches = _branches(client, "lien:usr_emetteurs")["branches"]
    assert any(b["libelle"] == nom_emetteur and b["nombre"] >= 2 for b in branches)


def test_et_sur_la_chose_concernee(client, documents_groupables):
    """Le repli parle le même vocabulaire que les filtres : `lien:` compris."""
    _, _, membre = documents_groupables
    branches = _branches(client, "lien:usr_membres")["branches"]
    trouvee = next(b for b in branches if b["valeur"] == f"usr_membres:{membre}")
    assert trouvee["nombre"] == 3
    assert "Ada" in trouvee["libelle"], "on lit un nom, pas un identifiant"


def test_les_niveaux_senchainent(client, documents_groupables):
    """Descendre « 2026 » puis « émetteur » : le second niveau ne compte que ce
    que le premier a laissé."""
    crees, nom_emetteur, _ = documents_groupables
    annee = next(b for b in _branches(client, "date_document")["branches"]
                 if b["libelle"] == "2026")
    second = _branches(client, "lien:usr_emetteurs", filtres=json.dumps([annee["critere"]]))
    trouvee = next(b for b in second["branches"] if b["libelle"] == nom_emetteur)
    assert trouvee["nombre"] == 2


def test_le_texte_du_document_ne_se_groupe_pas(client):
    reponse = client.get("/groupes", params={"champ": "texte"})
    assert reponse.status_code == 422
    assert "valeur commune" in reponse.json()["detail"]


def test_un_champ_inconnu_est_refuse(client):
    assert client.get("/groupes", params={"champ": "couleur"}).status_code == 422


def test_une_vue_memorise_son_repli(client, documents_groupables):
    creation = client.post("/vues", json={
        "nom": "_gr_vue", "criteres": [], "groupement": ["date_document", "meta:emetteur"]})
    assert creation.status_code == 200, creation.text
    vue = creation.json()
    try:
        assert vue["groupement"] == ["date_document", "meta:emetteur"]
        relue = next(v for v in client.get("/vues").json() if v["id"] == vue["id"])
        assert relue["groupement"] == ["date_document", "meta:emetteur"]

        refus = client.put(f"/vues/{vue['id']}", json={
            **vue, "groupement": ["nimporte_quoi"]})
        assert refus.status_code == 422
    finally:
        client.delete(f"/vues/{vue['id']}")


def test_le_repli_declare_se_relit_dans_lordre():
    class FausseVue:
        groupement = " date_document , meta:emetteur "
    assert groupes.declares(FausseVue()) == ["date_document", "meta:emetteur"]
    assert groupes.declares(None) == []
