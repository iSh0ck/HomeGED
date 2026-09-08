"""
Conséquences d'une suppression.

Une confirmation qui ne dit rien de ce qu'elle emporte ne protège de rien : ces
tests vérifient que les conséquences annoncées correspondent à ce que le schéma
fait réellement.
"""
import pytest

from app import impact
from app.db import (
    Categorie, Document, DroitCategorie, Role, SessionLocal,
    VueEnregistree,
)


@pytest.fixture
def categorie_garnie(base_de_test):
    """Une catégorie avec une sous-catégorie, un document, une vue et un droit."""
    session = SessionLocal()
    parent = session.query(Categorie).filter_by(nom="_ImpactParent").first()
    if not parent:
        parent = Categorie(nom="_ImpactParent", ordre=900)
        session.add(parent)
        session.flush()
        session.add(Categorie(nom="_ImpactEnfant", parent_id=parent.id, ordre=901))
        session.add(Document(nom_fichier="impact.pdf", chemin_stockage="/tmp/impact.pdf",
                             hash_sha256="impact".ljust(64, "4"), texte_ocr="x",
                             statut="traite", categorie_id=parent.id))
        session.add(VueEnregistree(nom="_ImpactVue", categorie_id=parent.id, criteres="[]"))
        role = session.query(Role).first()
        if role:
            session.add(DroitCategorie(role_id=role.id, categorie_id=parent.id,
                                       peut_voir=True, peut_modifier=False))
        session.commit()
    identifiant = parent.id
    session.close()
    return identifiant


def _par_nature(resultat):
    groupes = {}
    for consequence in resultat["consequences"]:
        groupes.setdefault(consequence["nature"], []).append(consequence["libelle"])
    return groupes


def test_supprimer_une_categorie_annonce_ce_qu_elle_emporte(session, categorie_garnie):
    resultat = impact.calculer(session, "categorie", categorie_garnie)
    assert "_ImpactParent" in resultat["objet"]
    natures = _par_nature(resultat)
    # ce qui disparaît vraiment (cascade) et ce qui survit détaché
    assert any("vue" in l for l in natures.get("suppression", []))
    assert any("déclassé" in l for l in natures.get("detachement", []))
    assert any("sous-catégorie" in l for l in natures.get("detachement", []))


def test_les_consequences_vides_ne_sont_pas_annoncees(session, base_de_test):
    """Une catégorie sans rien attaché ne doit pas afficher « 0 document »."""
    session_ecriture = SessionLocal()
    vide = session_ecriture.query(Categorie).filter_by(nom="_ImpactVide").first()
    if not vide:
        vide = Categorie(nom="_ImpactVide", ordre=950)
        session_ecriture.add(vide)
        session_ecriture.commit()
    identifiant = vide.id
    session_ecriture.close()

    resultat = impact.calculer(session, "categorie", identifiant)
    assert all(c["nombre"] != 0 or c["nature"] == "avertissement"
               for c in resultat["consequences"])


# L'émetteur n'a plus d'impact à calculer (§21.12) : ce n'est plus un objet du
# système mais une **ligne d'une table du foyer**, et supprimer une ligne relève
# de l'écran « Base de données », qui dit déjà ce qu'elle emporte.


def test_un_objet_inexistant_est_signale(session):
    with pytest.raises(impact.ObjetIntrouvable):
        impact.calculer(session, "categorie", 999999)
    with pytest.raises(impact.ObjetIntrouvable):
        impact.calculer(session, "licorne", 1)


def test_la_route_d_administration_repond(client, categorie_garnie):
    reponse = client.get("/admin/impact-suppression",
                         params={"type_objet": "categorie", "identifiant": categorie_garnie})
    assert reponse.status_code == 200
    assert reponse.json()["consequences"]
    assert client.get("/admin/impact-suppression",
                      params={"type_objet": "categorie", "identifiant": 999999}).status_code == 404


def test_un_compte_ordinaire_n_interroge_que_ses_objets(client, jeton_de):
    """La route publique ne couvre que ce qu'un compte non-admin peut supprimer."""
    client.post("/admin/utilisateurs", json={
        "email": "_impact@test.local", "nom": "T", "prenom": "Test", "mot_de_passe": "motdepasse-test-1234",
        "est_admin": False, "actif": True, "role_ids": []})
    membre = jeton_de("_impact@test.local", "motdepasse-test-1234")
    assert membre.get("/impact-suppression",
                      params={"type_objet": "categorie", "identifiant": 1}).status_code == 403
    assert membre.get("/admin/impact-suppression",
                      params={"type_objet": "categorie", "identifiant": 1}).status_code == 403
