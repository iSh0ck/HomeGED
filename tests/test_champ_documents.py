"""
Un champ qui attache des documents existants (§22.11).

L'exemple de l'utilisateur : sous « Entretiens », noter ce qui a été fait sur le
véhicule **et** y attacher une ou plusieurs factures déjà présentes dans la GED.
Le besoin est général — une déclaration de sinistre et ses devis, un chantier et
ses pièces —, d'où un champ générique plutôt qu'une notion de plus.

Ce n'est ni une pièce (§22.2 : un fichier de plus dans **ce** document), ni un
rattachement à la main (§22.4 : un lien sans nom), ni un rapprochement déclaré
(§22.8 : deux documents qui portent la même valeur). C'est un **champ** : il a un
intitulé, il est propre à un type, et son contenu est une liste de documents.
"""
from datetime import datetime, timedelta

import pytest

from app.db import (Categorie, Document, DocumentAttache, Metadonnee,
                    RegleChampCategorie, SessionLocal)


@pytest.fixture
def entretien_et_factures(client, base_de_test):
    """Une fiche « _CdEntretiens » qui attache des factures, et deux factures."""
    fiche = client.post("/admin/categories", json={
        "nom": "_CdEntretiens", "nature": "fiche", "ordre": 965}).json()
    champ = client.post("/admin/regles-champs", json={
        "categorie_id": fiche["id"], "champ": "meta:commentaire",
        "libelle": "Ce qui a été fait", "obligatoire": True, "ordre": 10})
    assert champ.status_code == 200, champ.text
    attaches = client.post("/admin/regles-champs", json={
        "categorie_id": fiche["id"], "champ": "meta:factures_liees",
        "libelle": "Factures liées", "obligatoire": False,
        "attache_documents": True, "ordre": 20})
    assert attaches.status_code == 200, attaches.text

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_cd%")).delete(
            synchronize_session=False)
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        factures = []
        for nom in ("_cd_facture_a.pdf", "_cd_facture_b.pdf"):
            document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                                hash_sha256=nom.ljust(64, "c"), texte_ocr="x",
                                statut="traite", categorie_id=type_doc.id)
            session.add(document)
            session.flush()
            factures.append(document.id)
        session.commit()
        contexte = (fiche["id"], factures)
    finally:
        session.close()

    yield contexte

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_cd%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.categorie_id == fiche["id"]).delete(
            synchronize_session=False)
        session.query(RegleChampCategorie).filter_by(categorie_id=fiche["id"]).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.id == fiche["id"]).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _entree(client, fiche, commentaire="Vidange et filtres"):
    creee = client.post("/documents", json={
        "categorie_id": fiche, "valeurs": {"meta:commentaire": commentaire}})
    assert creee.status_code == 200, creee.text
    return creee.json()


def test_lecran_sait_quel_champ_attache_des_documents(client, entretien_et_factures):
    """Sans cela, l'interface offrirait une saisie de texte là où il faut choisir."""
    fiche, _ = entretien_et_factures
    champs = client.get(f"/categories/{fiche}/champs").json()["champs"]
    par_champ = {c["champ"]: c for c in champs}
    assert par_champ["meta:factures_liees"]["attache_documents"] is True
    assert par_champ["meta:commentaire"]["attache_documents"] is False


def test_on_attache_des_documents_existants_a_une_entree(client, entretien_et_factures):
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)

    pose = client.put(f"/documents/{entree['id']}/attaches/meta:factures_liees",
                      json={"documents": factures})
    assert pose.status_code == 200, pose.text

    lu = client.get(f"/documents/{entree['id']}/attaches").json()["attaches"]
    champ = next(a for a in lu if a["champ"] == "meta:factures_liees")
    assert champ["libelle"] == "Factures liées"
    assert [d["id"] for d in champ["documents"]] == factures


def test_lordre_choisi_est_conserve(client, entretien_et_factures):
    """C'est celui dans lequel on les a choisies, et souvent celui dans lequel on
    veut les relire."""
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)
    client.put(f"/documents/{entree['id']}/attaches/meta:factures_liees",
               json={"documents": list(reversed(factures))})

    lu = client.get(f"/documents/{entree['id']}/attaches").json()["attaches"]
    champ = next(a for a in lu if a["champ"] == "meta:factures_liees")
    assert [d["id"] for d in champ["documents"]] == list(reversed(factures))


def test_enregistrer_remplace_le_contenu_du_champ(client, entretien_et_factures):
    """Un champ porte ce qu'on lui a donné en dernier — pas une accumulation."""
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)
    client.put(f"/documents/{entree['id']}/attaches/meta:factures_liees",
               json={"documents": factures})
    client.put(f"/documents/{entree['id']}/attaches/meta:factures_liees",
               json={"documents": factures[:1]})

    lu = client.get(f"/documents/{entree['id']}/attaches").json()["attaches"]
    champ = next(a for a in lu if a["champ"] == "meta:factures_liees")
    assert [d["id"] for d in champ["documents"]] == factures[:1]


def test_un_champ_ordinaire_nattache_rien(client, entretien_et_factures):
    """Le refus dit quoi faire : déclarer le champ, et non chercher pourquoi."""
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)

    refus = client.put(f"/documents/{entree['id']}/attaches/meta:commentaire",
                       json={"documents": factures})
    assert refus.status_code == 404
    assert "Champs attendus" in refus.json()["detail"]


def test_un_document_inconnu_est_refuse(client, entretien_et_factures):
    fiche, _ = entretien_et_factures
    entree = _entree(client, fiche)
    refus = client.put(f"/documents/{entree['id']}/attaches/meta:factures_liees",
                       json={"documents": [999999]})
    assert refus.status_code == 404


def test_le_lien_part_avec_le_document_attache(client, entretien_et_factures):
    """
    Une facture supprimée pour de bon ne doit pas laisser une ligne fantôme dans
    la fiche d'un entretien.
    """
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)
    client.put(f"/documents/{entree['id']}/attaches/meta:factures_liees",
               json={"documents": factures})

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.id == factures[0]).delete(
            synchronize_session=False)
        session.commit()
        restants = session.query(DocumentAttache).filter_by(
            document_id=entree["id"]).count()
        assert restants == 1
    finally:
        session.close()


# ------------------------------------------------------------------
# Ce que le champ accepte (§22.14)
#
# « Le bouton "Documents de la GED" est trop général : il faut pouvoir choisir un
# type de document, et par quels champs la recherche peut se faire. » Un champ
# qui propose toute la GED ne guide personne.
# ------------------------------------------------------------------

def _borner(client, fiche, categorie_cible, champs):
    """Déclare ce que « Factures liées » accepte, comme le ferait l'écran."""
    regles = client.get(f"/admin/regles-champs?categorie_id={fiche}").json()
    regle = next(r for r in regles if r["champ"] == "meta:factures_liees")
    reponse = client.put(f"/admin/regles-champs/{regle['id']}", json={
        **regle, "documents_categorie_id": categorie_cible, "documents_champs": champs})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_la_declaration_se_relit(client, entretien_et_factures):
    fiche, factures = entretien_et_factures
    session = SessionLocal()
    try:
        type_facture = session.get(Document, factures[0]).categorie_id
    finally:
        session.close()

    relue = _borner(client, fiche, type_facture, ["meta:numero_facture"])
    assert relue["documents_categorie_id"] == type_facture
    assert relue["documents_champs"] == ["meta:numero_facture"]

    # et l'écran de saisie la reçoit avec le champ
    champs = client.get(f"/categories/{fiche}/champs").json()["champs"]
    par_champ = {c["champ"]: c for c in champs}
    assert par_champ["meta:factures_liees"]["documents_categorie_id"] == type_facture


def test_le_selecteur_ne_propose_que_le_type_accepte(client, entretien_et_factures):
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)
    session = SessionLocal()
    try:
        type_facture = session.get(Document, factures[0]).categorie_id
        autre_type = session.query(Categorie).filter(
            Categorie.nature == "type", Categorie.id != type_facture).first()
        etranger = Document(nom_fichier="_cd_etranger.pdf",
                            chemin_stockage="/tmp/_cd_etranger.pdf",
                            hash_sha256="_cdetr".ljust(64, "e"), texte_ocr="x",
                            statut="traite", categorie_id=autre_type.id)
        session.add(etranger)
        session.commit()
        identifiant = etranger.id
    finally:
        session.close()

    _borner(client, fiche, type_facture, [])
    proposes = client.get(
        f"/categories/{fiche}/attachables?champ=meta:factures_liees"
        f"&sauf={entree['id']}").json()["documents"]
    trouves = {d["id"] for d in proposes}
    assert set(factures) <= trouves
    assert identifiant not in trouves, "un document d'un autre type n'a rien à faire ici"


def test_la_recherche_porte_sur_les_champs_declares(client, entretien_et_factures):
    """
    Chercher « Orange » dans le texte entier ramènerait la moitié de la GED ;
    dans le champ « émetteur », cela ramène ce qu'on cherche.
    """
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)
    session = SessionLocal()
    try:
        type_facture = session.get(Document, factures[0]).categorie_id
        session.add(Metadonnee(document_id=factures[0], cle="numero_facture",
                               valeur="F-2026-777"))
        # le second document porte le mot dans son texte, mais pas dans le champ
        session.get(Document, factures[1]).texte_ocr = "F-2026-777 en toutes lettres"
        session.commit()
    finally:
        session.close()

    _borner(client, fiche, type_facture, ["meta:numero_facture"])
    proposes = client.get(
        f"/categories/{fiche}/attachables"
        f"?champ=meta:factures_liees&q=F-2026-777").json()["documents"]
    assert [d["id"] for d in proposes] == [factures[0]]


def test_lapi_refuse_un_document_hors_du_type_accepte(client, entretien_et_factures):
    """Le type accepté est un contrôle, pas une aide à la saisie."""
    fiche, factures = entretien_et_factures
    entree = _entree(client, fiche)
    session = SessionLocal()
    try:
        type_facture = session.get(Document, factures[0]).categorie_id
        autre_type = session.query(Categorie).filter(
            Categorie.nature == "type", Categorie.id != type_facture).first()
        etranger = Document(nom_fichier="_cd_refuse.pdf",
                            chemin_stockage="/tmp/_cd_refuse.pdf",
                            hash_sha256="_cdref".ljust(64, "f"), texte_ocr="x",
                            statut="traite", categorie_id=autre_type.id)
        session.add(etranger)
        session.commit()
        identifiant = etranger.id
    finally:
        session.close()

    _borner(client, fiche, type_facture, [])
    refus = client.put(f"/documents/{entree['id']}/attaches/meta:factures_liees",
                       json={"documents": [identifiant]})
    assert refus.status_code == 404
    assert "type" in refus.json()["detail"]


def test_on_cherche_un_emetteur_par_son_nom(client, entretien_et_factures):
    """
    Le défaut signalé en service : cocher « Émetteur » ne servait à rien. La
    métadonnée porte `usr_emetteurs:5`, pas « Orange » — chercher le mot dans la
    valeur brute ne pouvait rien trouver (§22.19).
    """
    from sqlalchemy import text as sql

    fiche, factures = entretien_et_factures
    session = SessionLocal()
    try:
        type_facture = session.get(Document, factures[0]).categorie_id
        session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_CdOrange'"))
        session.execute(sql("INSERT INTO usr_emetteurs (nom) VALUES ('_CdOrange')"))
        emetteur = session.execute(sql(
            "SELECT id FROM usr_emetteurs WHERE nom = '_CdOrange'")).scalar()
        # le champ « émetteur » du type cible puise dans cette table
        session.query(RegleChampCategorie).filter_by(
            categorie_id=type_facture, champ="meta:emetteur").delete()
        session.add(RegleChampCategorie(categorie_id=type_facture, champ="meta:emetteur",
                                        libelle="Émetteur", source_table="usr_emetteurs",
                                        sources="usr_emetteurs", obligatoire=False,
                                        ordre=50))
        session.add(Metadonnee(document_id=factures[0], cle="emetteur",
                               valeur=f"usr_emetteurs:{emetteur}"))
        session.commit()
    finally:
        session.close()

    try:
        _borner(client, fiche, type_facture, ["meta:emetteur"])
        proposes = client.get(
            f"/categories/{fiche}/attachables"
            f"?champ=meta:factures_liees&q=_CdOrange").json()["documents"]
        assert [d["id"] for d in proposes] == [factures[0]]

        # et le détail montre ce qui a été coché, par son libellé
        details = {d["libelle"]: d["valeur"] for d in proposes[0]["details"]}
        assert details == {"Émetteur": "_CdOrange"}
    finally:
        session = SessionLocal()
        try:
            session.query(RegleChampCategorie).filter_by(
                categorie_id=session.get(Document, factures[0]).categorie_id,
                champ="meta:emetteur").delete()
            session.execute(sql("DELETE FROM usr_emetteurs WHERE nom = '_CdOrange'"))
            session.commit()
        finally:
            session.close()


def test_le_detail_montre_les_champs_coches(client, entretien_et_factures):
    """
    « Factures · 2026-03-23 » ne distingue pas deux factures du même mois. Ce
    qu'on a coché en administration doit se lire dans la liste.
    """
    fiche, factures = entretien_et_factures
    session = SessionLocal()
    try:
        type_facture = session.get(Document, factures[0]).categorie_id
        session.add(Metadonnee(document_id=factures[0], cle="numero_facture",
                               valeur="F-2026-424"))
        session.commit()
    finally:
        session.close()

    _borner(client, fiche, type_facture, ["meta:numero_facture"])
    proposes = client.get(
        f"/categories/{fiche}/attachables?champ=meta:factures_liees").json()["documents"]
    avec = next(d for d in proposes if d["id"] == factures[0])
    assert avec["details"] == [{"libelle": "N° facture", "valeur": "F-2026-424"}] \
        or avec["details"][0]["valeur"] == "F-2026-424"
    # un document qui ne porte pas la valeur n'invente pas une ligne vide
    sans = next(d for d in proposes if d["id"] == factures[1])
    assert sans["details"] == []


# ------------------------------------------------------------------
# Ce que le sélecteur montre, et quand il cherche (§22.26)
#
# Un foyer accumule des milliers de documents : les proposer tous à chaque
# ouverture de liste coûte une requête lourde pour un résultat qu'on ne lit pas.
# ------------------------------------------------------------------

def test_sans_recherche_on_ne_montre_que_le_dernier_mois(client, entretien_et_factures):
    fiche, factures = entretien_et_factures
    session = SessionLocal()
    try:
        # l'une des deux factures date d'un an
        vieille = session.get(Document, factures[1])
        vieille.date_import = datetime.now() - timedelta(days=365)
        session.commit()
    finally:
        session.close()

    reponse = client.get(
        f"/categories/{fiche}/attachables?champ=meta:factures_liees").json()
    assert reponse["recents"] is True, "l'écran doit pouvoir dire que c'est un extrait"
    assert reponse["jours_recents"] == 30
    trouves = {d["id"] for d in reponse["documents"]}
    assert factures[0] in trouves
    assert factures[1] not in trouves, "un document d'il y a un an se cherche"


def test_la_recherche_attend_trois_caracteres(client, entretien_et_factures):
    """« fa » ramènerait la moitié de la GED : cela ne rend service à personne."""
    fiche, factures = entretien_et_factures
    session = SessionLocal()
    try:
        session.get(Document, factures[1]).date_import = datetime.now() - timedelta(days=365)
        session.commit()
    finally:
        session.close()

    court = client.get(
        f"/categories/{fiche}/attachables?champ=meta:factures_liees&q=_c").json()
    assert court["recents"] is True, "trop court : on rend l'extrait récent, pas un résultat"
    assert court["minimum_recherche"] == 3

    # à partir de trois caractères, on cherche vraiment — y compris dans l'ancien
    long = client.get(
        f"/categories/{fiche}/attachables?champ=meta:factures_liees&q=_cd_facture_b").json()
    assert long["recents"] is False
    assert [d["id"] for d in long["documents"]] == [factures[1]]
