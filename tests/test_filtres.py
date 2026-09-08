"""Moteur de filtres : combinaisons, sous-catégories, et refus des entrées invalides."""
import json

from app.db import Categorie, Document, Metadonnee, SessionLocal
from sqlalchemy import text as sql


def _jeu_de_donnees():
    session = SessionLocal()
    factures = session.query(Categorie).filter_by(nom="Factures").one()
    banque = session.query(Categorie).filter_by(nom="Banque").one()
    # L'émetteur est une **métadonnée** comme une autre depuis le §21.12 : on le
    # désigne par sa référence, `usr_emetteurs:<id>`, comme un véhicule ou un membre.
    orange = session.execute(sql("SELECT id FROM usr_emetteurs WHERE nom = 'Orange'")).scalar()
    # « Maison » chapeaute les deux, pour vérifier le regroupement par section
    maison = session.query(Categorie).filter_by(nom="Maison").first()
    if not maison:
        maison = Categorie(nom="Maison")
        session.add(maison)
        session.flush()
    factures.parent_id = maison.id
    banque.parent_id = maison.id

    donnees = [("filtre_a.pdf", factures.id, orange, "2026-08-21", "120.50"),
               ("filtre_b.pdf", factures.id, None, "2026-07-15", "19.99"),
               ("filtre_c.pdf", banque.id, None, "2026-08-01", None)]
    for nom, categorie, emetteur, date, montant in donnees:
        if session.query(Document).filter_by(nom_fichier=nom).first():
            continue
        document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                            hash_sha256=nom.ljust(64, "1"), texte_ocr="x", statut="traite",
                            categorie_id=categorie, date_document=date)
        session.add(document)
        session.flush()
        if montant:
            session.add(Metadonnee(document_id=document.id, cle="montant_ttc", valeur=montant))
        if emetteur:
            session.add(Metadonnee(document_id=document.id, cle="emetteur",
                                   valeur=f"usr_emetteurs:{emetteur}"))
    session.commit()
    ids = {"factures": factures.id, "banque": banque.id, "maison": maison.id,
           "orange": orange}
    session.close()
    return ids


def _noms(client, criteres):
    reponse = client.get("/documents", params={"filtres": json.dumps(criteres)})
    assert reponse.status_code == 200, reponse.text
    return {d["nom_fichier"] for d in reponse.json()}


def test_filtre_par_categorie_inclut_les_sous_categories(client):
    ids = _jeu_de_donnees()
    sous_section = _noms(client, [{"champ": "categorie", "operateur": "egal", "valeur": str(ids["maison"])}])
    assert {"filtre_a.pdf", "filtre_b.pdf", "filtre_c.pdf"} <= sous_section


def test_filtres_combines_en_et(client):
    ids = _jeu_de_donnees()
    resultat = _noms(client, [
        {"champ": "categorie", "operateur": "egal", "valeur": str(ids["factures"])},
        # L'émetteur se désigne par sa référence : c'est la liste de suggestions
        # qui montre « Orange » et envoie `usr_emetteurs:5` (§21.12).
        {"champ": "lien:usr_emetteurs", "operateur": "egal",
         "valeur": f"usr_emetteurs:{ids['orange']}"},
    ])
    assert "filtre_a.pdf" in resultat and "filtre_b.pdf" not in resultat


def test_filtre_sur_une_metadonnee(client):
    _jeu_de_donnees()
    assert "filtre_b.pdf" in _noms(client, [{"champ": "meta:montant_ttc", "valeur": "19"}])


def test_filtres_sur_les_dates(client):
    _jeu_de_donnees()
    assert "filtre_a.pdf" in _noms(client, [
        {"champ": "date_document", "operateur": "apres", "valeur": "2026-08-10"}])
    assert {"filtre_b.pdf", "filtre_c.pdf"} <= _noms(client, [
        {"champ": "date_document", "operateur": "entre", "valeur": ["2026-07-01", "2026-08-05"]}])
    assert "filtre_a.pdf" in _noms(client, [
        {"champ": "date_document", "operateur": "contient", "valeur": "2026-08"}])


def test_champ_vide_et_non_vide(client):
    _jeu_de_donnees()
    assert "filtre_c.pdf" in _noms(client, [{"champ": "meta:emetteur", "operateur": "vide"}])
    assert "filtre_a.pdf" in _noms(client, [{"champ": "meta:emetteur", "operateur": "non_vide"}])


def test_les_entrees_invalides_sont_refusees(client):
    """Un champ ou un opérateur inconnu doit être rejeté, jamais interprété."""
    for criteres in ([{"champ": "; DROP TABLE documents", "valeur": "x"}],
                     [{"champ": "statut", "operateur": "avant", "valeur": "x"}],
                     [{"champ": "date_document", "operateur": "apres", "valeur": "hier"}]):
        assert client.get("/documents", params={"filtres": json.dumps(criteres)}).status_code == 422
    assert client.get("/documents", params={"filtres": "pas du json"}).status_code == 422


# ------------------------------------------------------------
# Tri et pagination, effectués par la base
# ------------------------------------------------------------

def _noms_ordonnes(client, **params):
    reponse = client.get("/documents", params=params)
    assert reponse.status_code == 200, reponse.text
    return [d["nom_fichier"] for d in reponse.json()], reponse.headers.get("x-total-count")


def test_tri_par_nom_dans_les_deux_sens(client):
    _jeu_de_donnees()
    croissant, _ = _noms_ordonnes(client, tri="nom_fichier", sens="asc", limite=100)
    decroissant, _ = _noms_ordonnes(client, tri="nom_fichier", sens="desc", limite=100)
    assert croissant == sorted(croissant)
    assert decroissant == list(reversed(croissant))


def test_tri_sur_le_nom_de_la_table_liee(client):
    """
    Trier par classement suit l'ordre alphabétique des noms, pas celui des
    identifiants — c'est ce que lit l'utilisateur. (L'émetteur, lui, est devenu
    une métadonnée au §21.12 et se trie comme telle.)
    """
    _jeu_de_donnees()
    reponse = client.get("/documents", params={"tri": "categorie", "sens": "asc", "limite": 100})
    noms = [d["categorie"] for d in reponse.json() if d["categorie"]]
    assert noms == sorted(noms)


def test_le_tri_porte_sur_tout_le_registre_et_non_sur_la_page(client):
    """Le premier élément d'une page de 1 doit être le premier du tri global."""
    _jeu_de_donnees()
    tous, _ = _noms_ordonnes(client, tri="nom_fichier", sens="asc", limite=100)
    page, _ = _noms_ordonnes(client, tri="nom_fichier", sens="asc", limite=1)
    assert page == [tous[0]]


def test_pagination_sans_recouvrement(client):
    _jeu_de_donnees()
    page1, total = _noms_ordonnes(client, tri="nom_fichier", sens="asc", limite=2, decalage=0)
    page2, _ = _noms_ordonnes(client, tri="nom_fichier", sens="asc", limite=2, decalage=2)
    assert len(page1) == 2
    assert not set(page1) & set(page2), "une page reprend des documents de la précédente"
    # le total porte sur l'ensemble, il dépasse donc la taille d'une page
    assert int(total) > len(page1)


def test_le_total_suit_le_filtre(client):
    """`X-Total-Count` compte le filtre entier, pas la page renvoyée."""
    _jeu_de_donnees()
    _, total_large = _noms_ordonnes(
        client, limite=1,
        filtres=json.dumps([{"champ": "nom_fichier", "operateur": "contient", "valeur": "filtre_"}]))
    _, total_etroit = _noms_ordonnes(
        client, limite=1,
        filtres=json.dumps([{"champ": "nom_fichier", "operateur": "contient", "valeur": "filtre_a"}]))
    # le total suit le filtre et non la page : il vaut 3 alors qu'une seule
    # ligne est renvoyée, et se resserre quand le filtre se resserre
    assert int(total_large) == 3
    assert int(total_etroit) == 1


def test_un_tri_inconnu_est_refuse(client):
    """Refusé plutôt qu'ignoré : l'utilisateur doit savoir que son tri n'a pas porté."""
    assert client.get("/documents", params={"tri": "mot_de_passe_hash"}).status_code == 422


def test_un_champ_attendu_par_un_type_est_filtrable(session):
    """
    Signalé : « je ne vois pas le titulaire alors que cela devrait être
    dynamique » (§19.16).

    Un type peut réclamer un champ qu'aucune règle ne remplit — le titulaire se
    saisit à la main ou se déduit d'une table du foyer. Il n'apparaissait alors
    dans aucune liste : ni pour filtrer une colonne, ni pour construire une vue.
    Or c'est précisément une colonne du tableau de ce type.
    """
    from app.db import Categorie, RegleChampCategorie

    type_doc = session.query(Categorie).filter(Categorie.nature != "dossier").first()
    session.add(RegleChampCategorie(
        categorie_id=type_doc.id, champ="meta:_filtre_titulaire",
        libelle="Titulaire du dossier", obligatoire=False, ordre=99))
    session.flush()

    from app import filtres as moteur

    champs = {c["champ"]: c for c in moteur.champs_disponibles(session)}
    assert "meta:_filtre_titulaire" in champs
    assert champs["meta:_filtre_titulaire"]["libelle"] == "Titulaire du dossier", \
        "l'intitulé déclaré par le type doit être repris : « Montant TTC », pas « Montant ttc »"


def test_les_jokers_tapes_dans_un_filtre_restent_du_texte(client):
    """
    « % » et « _ » sont des jokers pour la base, pas pour qui les tape (§22.38).

    Chercher « % » dans un nom de fichier ramenait **tout** le registre, et
    « filtre_a » ramenait aussi bien « filtre-a » : le souligné vaut « n'importe
    quel caractère ». Ce sont des caractères ordinaires dans un champ de
    recherche — un montant, un numéro de dossier — et ils doivent le rester.
    """
    _jeu_de_donnees()
    assert _noms(client, [{"champ": "nom_fichier", "operateur": "contient",
                           "valeur": "%"}]) == set()
    # Le souligné ne joue plus le joker : seul le vrai nom répond.
    trouves = _noms(client, [{"champ": "nom_fichier", "operateur": "contient",
                              "valeur": "filtre_a"}])
    assert trouves == {"filtre_a.pdf"}
    # …et la recherche ordinaire continue de fonctionner.
    assert "filtre_b.pdf" in _noms(client, [{"champ": "nom_fichier",
                                             "operateur": "contient", "valeur": "filtre"}])
