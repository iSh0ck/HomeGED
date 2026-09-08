"""
Les droits par branche (§21.7).

Nos droits se posaient sur les emplacements — un dossier, un type — et rien ne
permettait de dire « ce rôle ne voit que 2025 et 2026 ». Rien n'est dynamique
pour autant : ce ne sont pas « mes documents », mais des branches que
l'administration a nommées.
"""
import pytest

from app import droits
from app.db import (Categorie, Document, DroitBranche, DroitCategorie, Role,
                    SessionLocal, Utilisateur)


def _nettoyer():
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_db%")).delete(
            synchronize_session=False)
        for role in session.query(Role).filter(Role.nom.like("_DB%")):
            session.delete(role)
        for compte in session.query(Utilisateur).filter(Utilisateur.email.like("_db%")):
            session.delete(compte)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def foyer_restreint(base_de_test):
    """
    Trois documents (2024, 2025, 2026), un compte dont le rôle n'ouvre que 2026.
    """
    _nettoyer()
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        crees = {}
        for annee in ("2024", "2025", "2026"):
            document = Document(nom_fichier=f"_db_{annee}.pdf",
                                chemin_stockage=f"/tmp/_db_{annee}.pdf",
                                hash_sha256=f"_db{annee}".ljust(64, "d"), texte_ocr="x",
                                statut="traite", categorie_id=type_doc.id,
                                date_document=f"{annee}-06-15")
            session.add(document)
            session.flush()
            crees[annee] = document.id

        role = Role(nom="_DBRestreint")
        session.add(role)
        session.flush()
        session.add(DroitCategorie(role_id=role.id, categorie_id=type_doc.id,
                                   peut_voir=True, peut_telecharger=True))
        session.add(DroitBranche(role_id=role.id, champ="date_document", valeur="2026"))

        from app import auth
        compte = Utilisateur(email="_db_restreint@test", nom="Restreint", prenom="Compte",
                             mot_de_passe_hash=auth.hash_mot_de_passe("x"),
                             est_admin=False)
        compte.roles.append(role)
        session.add(compte)
        session.commit()
        yield crees, compte.id, role.id
    finally:
        session.close()
    _nettoyer()


def _visibles(compte_id):
    """Ce que ce compte voit, par le point de passage unique."""
    from app.api import _filtrer_par_droits

    session = SessionLocal()
    try:
        compte = session.get(Utilisateur, compte_id)
        query = _filtrer_par_droits(session.query(Document.id), session, compte)
        return {identifiant for (identifiant,) in query}
    finally:
        session.close()


def test_le_role_ne_voit_que_ses_branches(foyer_restreint):
    crees, compte_id, _ = foyer_restreint
    vus = _visibles(compte_id)
    assert crees["2026"] in vus
    assert crees["2025"] not in vus and crees["2024"] not in vus


def test_une_annee_est_un_intervalle(foyer_restreint):
    """
    Une restriction « 2026 » posée comme une égalité ne laisserait voir que les
    documents datés du 1er janvier.
    """
    crees, compte_id, _ = foyer_restreint
    session = SessionLocal()
    try:
        session.get(Document, crees["2026"]).date_document = "2026-12-31"
        session.commit()
    finally:
        session.close()
    assert crees["2026"] in _visibles(compte_id)


def test_sans_ligne_aucune_restriction(foyer_restreint):
    """Pouvoir restreindre n'oblige pas chaque foyer à le faire."""
    crees, compte_id, role_id = foyer_restreint
    session = SessionLocal()
    try:
        session.query(DroitBranche).filter_by(role_id=role_id).delete()
        session.commit()
    finally:
        session.close()
    assert set(crees.values()) <= _visibles(compte_id)


def test_un_role_sans_restriction_leve_celle_de_lautre(foyer_restreint):
    """
    Les rôles s'additionnent (§19.12) : une restriction que n'importe quel autre
    rôle lèverait serait un piège, pas un droit. On le dit donc explicitement.
    """
    crees, compte_id, _ = foyer_restreint
    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        large = Role(nom="_DBLarge")
        session.add(large)
        session.flush()
        session.add(DroitCategorie(role_id=large.id, categorie_id=type_doc.id,
                                   peut_voir=True))
        # Gardé dans une variable : sans référence, SQLAlchemy peut ramasser
        # l'objet avant qu'on ait modifié sa collection.
        compte = session.get(Utilisateur, compte_id)
        compte.roles.append(large)
        session.commit()
    finally:
        session.close()
    assert crees["2025"] in _visibles(compte_id)


def test_ladministrateur_nest_jamais_restreint(foyer_restreint):
    """C'est lui qui pose ces lignes : se les appliquer l'enfermerait dehors."""
    _, compte_id, role_id = foyer_restreint
    session = SessionLocal()
    try:
        compte = session.get(Utilisateur, compte_id)
        assert droits.branches_autorisees(session, compte)   # restreint tant qu'il ne l'est pas
        compte.est_admin = True
        assert droits.branches_autorisees(session, compte) == {}
    finally:
        session.rollback()
        session.close()


def test_ladresse_directe_nest_pas_une_porte_de_derriere(client, foyer_restreint):
    """
    Le filtre des listes ne suffit pas : sans contrôle sur la fiche, il restait
    l'URL. On y repasse par la même requête filtrée plutôt que de réécrire la
    règle — une règle écrite deux fois divergera.
    """
    from app.api import app, _verifier_acces
    from fastapi import HTTPException

    crees, compte_id, _ = foyer_restreint
    session = SessionLocal()
    try:
        compte = session.get(Utilisateur, compte_id)
        interdit = session.get(Document, crees["2025"])
        autorise = session.get(Document, crees["2026"])

        with pytest.raises(HTTPException) as refus:
            _verifier_acces(interdit, compte, session=session)
        assert refus.value.status_code == 404, "on ne dit pas qu'il existe"

        _verifier_acces(autorise, compte, session=session)   # ne lève pas
    finally:
        session.close()


def test_une_branche_illisible_ferme_au_lieu_douvrir(foyer_restreint):
    """
    Une restriction qu'on ne sait plus appliquer — champ renommé, table
    supprimée — ne doit pas se transformer en autorisation.
    """
    crees, compte_id, role_id = foyer_restreint
    session = SessionLocal()
    try:
        session.query(DroitBranche).filter_by(role_id=role_id).delete()
        session.add(DroitBranche(role_id=role_id, champ="meta:_db_disparu",
                                 valeur="x"))
        session.commit()
    finally:
        session.close()
    assert _visibles(compte_id) & set(crees.values()) == set()


def test_les_branches_se_declarent_depuis_ladministration(client, foyer_restreint):
    _, _, role_id = foyer_restreint
    role = next(r for r in client.get("/admin/roles").json() if r["id"] == role_id)
    assert role["branches"] == [{"champ": "date_document", "valeur": "2026"}]

    change = client.put(f"/admin/roles/{role_id}/droits", json={
        "categories": role["droits"], "generaux": role["generaux"], "vues": role["vues"],
        "branches": [{"champ": "date_document", "valeur": "2025"},
                     {"champ": "date_document", "valeur": "2026"}]})
    assert change.status_code == 200, change.text
    assert len(change.json()["branches"]) == 2

    refus = client.put(f"/admin/roles/{role_id}/droits", json={
        "categories": [], "generaux": [], "vues": [],
        "branches": [{"champ": "champ_inexistant", "valeur": "x"}]})
    assert refus.status_code == 422
