"""
Rattachement automatique aux tables du foyer (§17.18, §18.47).

Une facture porte le nom de son titulaire ; un contrôle technique porte une
immatriculation. Quand le document le dit, l'application le lit — quand il ne le
dit pas, ou qu'il en dit trop, elle s'abstient et laisse le Centre d'analyse
poser la question.

Ces tests portent surtout sur les abstentions : un rattachement faux ne se voit
pas, là où un champ vide se réclame de lui-même.
"""
import pytest
from sqlalchemy import text

from app import references_auto
from app.db import (
    Categorie, Document, Metadonnee, RegleChampCategorie, SessionLocal, TableDonnees,
)

TABLE = "usr_membres_test"


@pytest.fixture
def foyer(base_de_test):
    """Une catégorie « _Factures », un champ « titulaire » et trois membres."""
    session = SessionLocal()
    try:
        session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        session.execute(text(
            f"CREATE TABLE {TABLE} (id INT AUTO_INCREMENT PRIMARY KEY, "
            f"nom VARCHAR(150) NOT NULL, prenom VARCHAR(100) NOT NULL)"
        ))
        session.query(TableDonnees).filter_by(nom_table=TABLE).delete()
        session.add(TableDonnees(nom_table=TABLE, libelle="Membres (test)",
                                 colonne_libelle="nom", colonnes_identifiantes="prenom,nom"))

        categorie = session.query(Categorie).filter_by(nom="_FacturesRattachement").one_or_none()
        if not categorie:
            categorie = Categorie(nom="_FacturesRattachement", ordre=960)
            session.add(categorie)
            session.flush()
        session.query(RegleChampCategorie).filter_by(categorie_id=categorie.id).delete()
        # La déduction se déclare : `deduction="toutes"` dit que le prénom **et**
        # le nom doivent figurer dans le document. Sans cette déclaration, rien
        # n'est cherché — c'est ce que vérifie le premier test du fichier.
        session.add(RegleChampCategorie(categorie_id=categorie.id, champ="meta:titulaire",
                                        source_table=TABLE, libelle="Titulaire",
                                        deduction="toutes",
                                        obligatoire=False, ordre=50))
        # Deux Dupont : c'est tout l'enjeu du prénom.
        for prenom, nom in (("Jean", "Dupont"), ("Hélène", "Créton"), ("Léa", "Dupont")):
            session.execute(text(f"INSERT INTO {TABLE} (prenom, nom) VALUES (:prenom, :nom)"),
                            {"prenom": prenom, "nom": nom})
        session.commit()
        identifiant = categorie.id
    finally:
        session.close()

    yield identifiant

    session = SessionLocal()
    try:
        session.query(RegleChampCategorie).filter_by(categorie_id=identifiant).delete()
        session.query(TableDonnees).filter_by(nom_table=TABLE).delete()
        session.query(Document).filter(Document.nom_fichier.like("_ratt%")).delete(
            synchronize_session=False)
        session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        session.commit()
    finally:
        session.close()


def _document(nom, categorie_id, texte, metadonnees=None):
    session = SessionLocal()
    try:
        document = Document(nom_fichier=nom, chemin_stockage=f"/tmp/{nom}",
                            hash_sha256=nom.ljust(64, "r"), texte_ocr=texte,
                            statut="traite", categorie_id=categorie_id)
        session.add(document)
        session.flush()
        for cle, valeur in (metadonnees or {}).items():
            session.add(Metadonnee(document_id=document.id, cle=cle, valeur=valeur))
        session.commit()
        return document.id
    finally:
        session.close()


def _remplir(document_id):
    session = SessionLocal()
    try:
        document = session.get(Document, document_id)
        resultat = references_auto.remplir(session, document)
        session.commit()
        valeurs = {m.cle: m.valeur for m in document.metadonnees}
        return resultat, valeurs
    finally:
        session.close()


def _regler_deduction(categorie_id, mode, colonnes=None):
    """Change ce que le champ déclare chercher, comme le ferait l'écran d'administration."""
    session = SessionLocal()
    try:
        regle = session.query(RegleChampCategorie).filter_by(
            categorie_id=categorie_id, champ="meta:titulaire").one()
        regle.deduction = mode
        regle.colonnes_deduction = ",".join(colonnes) if colonnes else None
        session.commit()
    finally:
        session.close()


def test_rien_nest_deduit_tant_que_personne_ne_la_demande(foyer):
    """
    Le cas qui a motivé le §18.47 : le champ est rattaché à une table, le
    document nomme quelqu'un sans ambiguïté — et pourtant rien n'est rempli,
    parce qu'aucun administrateur n'a déclaré cette déduction.

    Un rattachement que l'on n'a pas demandé se lit comme une erreur, même
    quand il est juste : on ne peut pas le vérifier sans relire le document.
    """
    _regler_deduction(foyer, "aucune")
    identifiant = _document("_ratt_non_declare.pdf", foyer,
                            "Facture au nom de Monsieur Jean DUPONT")
    remplis, valeurs = _remplir(identifiant)
    assert remplis == {}
    assert "titulaire" not in valeurs


def test_les_colonnes_cherchees_sont_celles_qui_ont_ete_declarees(foyer):
    """
    Un autre foyer peut vouloir chercher autre chose. Ici, le nom seul : deux
    Dupont existent, la recherche en désigne donc deux et s'abstient — la règle
    du « une seule correspondance » continue de protéger, quel que soit le
    réglage.
    """
    _regler_deduction(foyer, "toutes", ["nom"])
    ambigu = _document("_ratt_col_nom.pdf", foyer, "Facture au nom de DUPONT")
    assert _remplir(ambigu)[0] == {}

    # ... mais un nom qui n'appartient qu'à une personne suffit désormais
    unique = _document("_ratt_col_creton.pdf", foyer, "Facture au nom de CRETON")
    assert _remplir(unique)[0] == {"titulaire": "Créton"}


def test_le_mode_une_seule_colonne_se_contente_dune_trouvaille(foyer):
    """
    Ce qui convient à une immatriculation ou un numéro de contrat : la valeur ne
    se répète nulle part ailleurs, l'exiger en entier n'apporte rien.
    """
    _regler_deduction(foyer, "une", ["prenom", "nom"])
    identifiant = _document("_ratt_une.pdf", foyer, "Contrat de Hélène, sans nom de famille")
    assert _remplir(identifiant)[0] == {"titulaire": "Hélène Créton"}


def test_rattache_quand_le_document_nomme_une_seule_personne(foyer):
    identifiant = _document("_ratt_simple.pdf", foyer,
                            "Facture d'électricité\nTitulaire : Monsieur Jean DUPONT\n120,50 EUR")
    remplis, valeurs = _remplir(identifiant)

    assert remplis == {"titulaire": "Jean Dupont"}
    # Depuis §17.28 la valeur porte sa source : deux sources ont chacune leur
    # ligne nº1, et un identifiant nu ne dirait plus laquelle.
    source, identifiant_ligne = valeurs["titulaire"].split(":", 1)
    assert source == TABLE
    assert identifiant_ligne.isdigit()


def test_ignore_les_accents_dans_les_deux_sens(foyer):
    """Un scan rend « Hélène » ou « Helene » selon la qualité de l'océrisation."""
    identifiant = _document("_ratt_accents.pdf", foyer, "Contrat au nom de HELENE CRETON")
    remplis, _ = _remplir(identifiant)
    assert remplis == {"titulaire": "Hélène Créton"}


def test_sabstient_sur_le_nom_de_famille_seul(foyer):
    """
    Deux Dupont dans le foyer : « Monsieur DUPONT » ne désigne personne en
    particulier. C'est exactement le cas qui a motivé la séparation du prénom et
    du nom — auparavant, le premier Dupont l'aurait emporté.
    """
    identifiant = _document("_ratt_nom_seul.pdf", foyer, "Facture au nom de Monsieur DUPONT")
    remplis, valeurs = _remplir(identifiant)
    assert remplis == {}
    assert "titulaire" not in valeurs


def test_sabstient_quand_deux_membres_sont_nommes(foyer):
    """
    « Jean Dupont » et « Léa Dupont » figurent tous deux : choisir à la place de
    quelqu'un serait un rattachement faux, et un rattachement faux ne se voit pas.
    """
    identifiant = _document("_ratt_ambigu.pdf", foyer,
                            "Facture commune : Jean Dupont et Léa Dupont")
    remplis, valeurs = _remplir(identifiant)
    assert remplis == {}
    assert "titulaire" not in valeurs


def test_sabstient_quand_personne_nest_nomme(foyer):
    identifiant = _document("_ratt_anonyme.pdf", foyer, "Facture de gaz, montant 42 EUR")
    remplis, valeurs = _remplir(identifiant)
    assert remplis == {}
    assert "titulaire" not in valeurs


def test_ne_recouvre_jamais_une_valeur_deja_saisie(foyer):
    """Une correction faite à la main ne doit pas être défaite au rejeu suivant."""
    identifiant = _document("_ratt_deja.pdf", foyer,
                            "Titulaire : Jean Dupont", metadonnees={"titulaire": "999"})
    remplis, valeurs = _remplir(identifiant)
    assert remplis == {}
    assert valeurs["titulaire"] == "999"


def test_document_sans_categorie_nest_pas_rattache(foyer):
    identifiant = _document("_ratt_sans_cat.pdf", None, "Titulaire : Jean Dupont")
    assert _remplir(identifiant)[0] == {}


def test_le_prenom_seul_ne_suffit_pas_non_plus(foyer):
    identifiant = _document("_ratt_prenom.pdf", foyer, "Bonjour Jean, voici votre facture")
    assert _remplir(identifiant)[0] == {}


def test_les_colonnes_obligatoires_sont_exigees_a_la_creation(client):
    """
    Un membre sans prénom ne sert à rien : le rattachement ne pourrait plus se
    faire. Le refus doit se dire en français, pas remonter en erreur d'intégrité.
    """
    refus = client.post("/admin/base/tables/usr_membres/lignes", json={"valeurs": {"nom": "Dupont"}})
    assert refus.status_code == 422, refus.text
    assert "prenom" in refus.json()["detail"] and "obligatoire" in refus.json()["detail"]

    accepte = client.post("/admin/base/tables/usr_membres/lignes",
                          json={"valeurs": {"nom": "_TestNom", "prenom": "_TestPrenom"}})
    assert accepte.status_code == 200, accepte.text
    client.delete(f"/admin/base/tables/usr_membres/lignes/{accepte.json()['id']}")


def test_la_vue_des_factures_sans_titulaire_existe_et_filtre(client):
    """
    Le champ « Titulaire » restant facultatif, c'est cette vue qui empêche les
    factures non attribuées de se perdre dans le registre.
    """
    vues = {v["nom"]: v for v in client.get("/vues").json()}
    vue = vues.get("Toutes les factures sans utilisateur associé")
    assert vue is not None, "la vue doit être installée par la migration"
    assert vue["partagee"] is True

    champs = {c["champ"]: c["operateur"] for c in vue["criteres"]}
    assert champs.get("meta:titulaire") == "vide"
    assert "categorie" in champs

    # ses critères doivent être acceptés par le moteur de filtres
    reponse = client.get("/documents", params={"filtres": __import__("json").dumps(vue["criteres"])})
    assert reponse.status_code == 200, reponse.text


def _categorie_jetable(client):
    """Une catégorie à soi, pour ne pas déranger le classement des autres tests."""
    cree = client.post("/admin/categories", json={
        "nom": "_DeductionTest", "regex_identification": None, "priorite": 950, "ordre": 950,
        "parent_id": None})
    assert cree.status_code == 200, cree.text
    return cree.json()["id"]


def test_une_deduction_se_declare_et_se_relit(client):
    """
    Ce que l'écran d'administration enregistre doit revenir tel quel : sans cela,
    rouvrir la fiche effacerait le réglage sans le dire.
    """
    categorie = _categorie_jetable(client)
    try:
        cree = client.post("/admin/regles-champs", json={
            "categorie_id": categorie, "champ": "meta:titulaire",
            "source_table": "usr_membres", "sources": ["usr_membres"],
            "libelle": "Titulaire", "obligatoire": False,
            "deduction": "toutes", "colonnes_deduction": ["prenom", "nom"], "ordre": 10,
        })
        assert cree.status_code == 200, cree.text
        assert cree.json()["deduction"] == "toutes"
        assert cree.json()["colonnes_deduction"] == ["prenom", "nom"]

        relu = [r for r in client.get(f"/admin/regles-champs?categorie_id={categorie}").json()
                if r["champ"] == "meta:titulaire"][0]
        assert relu["colonnes_deduction"] == ["prenom", "nom"]
    finally:
        client.delete(f"/admin/categories/{categorie}")


def test_une_deduction_sur_une_colonne_inexistante_est_refusee(client):
    """
    Sans ce refus, le réglage serait accepté puis ignoré en silence — et l'on
    chercherait longtemps pourquoi le champ ne se remplit jamais.
    """
    categorie = _categorie_jetable(client)
    try:
        refus = client.post("/admin/regles-champs", json={
            "categorie_id": categorie, "champ": "meta:titulaire",
            "source_table": "usr_membres", "sources": ["usr_membres"],
            "obligatoire": False, "deduction": "toutes",
            "colonnes_deduction": ["surnom"], "ordre": 10,
        })
        assert refus.status_code == 400
        assert "surnom" in refus.json()["detail"]
    finally:
        client.delete(f"/admin/categories/{categorie}")


def test_une_deduction_sans_source_est_refusee(client):
    """Chercher dans le texte n'a de sens que si l'on sait à quoi rattacher ce qu'on trouve."""
    categorie = _categorie_jetable(client)
    try:
        refus = client.post("/admin/regles-champs", json={
            "categorie_id": categorie, "champ": "meta:montant_ttc",
            "obligatoire": False, "deduction": "toutes", "ordre": 10,
        })
        assert refus.status_code == 400
        assert "source" in refus.json()["detail"].lower()
    finally:
        client.delete(f"/admin/categories/{categorie}")


def test_un_mode_de_deduction_inconnu_est_refuse(client):
    categorie = _categorie_jetable(client)
    try:
        refus = client.post("/admin/regles-champs", json={
            "categorie_id": categorie, "champ": "meta:titulaire",
            "source_table": "usr_membres", "sources": ["usr_membres"],
            "obligatoire": False, "deduction": "devine", "ordre": 10,
        })
        assert refus.status_code == 400
    finally:
        client.delete(f"/admin/categories/{categorie}")


def test_les_sources_annoncent_leurs_colonnes(client):
    """
    L'écran propose des colonnes à cocher : il faut bien qu'il sache lesquelles
    existent, sans les coder en dur.
    """
    membres = [s for s in client.get("/admin/sources-champs").json()
               if s["nom"] == "usr_membres"]
    assert membres, "la table des membres doit être proposable comme source"
    assert {"nom", "prenom"} <= set(membres[0]["colonnes"])
    assert membres[0]["colonnes_identifiantes"] == ["prenom", "nom"]


def test_le_champ_identifiant_survit_a_une_modification(client):
    """
    Le drapeau « identifie le document » ne repartait pas de l'API : rouvrir puis
    enregistrer une règle l'effaçait, et le versionnage cessait sans prévenir.
    """
    categorie = _categorie_jetable(client)
    try:
        cree = client.post("/admin/regles-champs", json={
            "categorie_id": categorie, "champ": "meta:numero_facture",
            "obligatoire": False, "identifiant": True, "ordre": 10,
        })
        assert cree.status_code == 200, cree.text
        assert cree.json()["identifiant"] is True

        relue = [r for r in client.get(f"/admin/regles-champs?categorie_id={categorie}").json()
                 if r["champ"] == "meta:numero_facture"][0]
        assert relue["identifiant"] is True
    finally:
        client.delete(f"/admin/categories/{categorie}")


def test_un_champ_deduit_ne_manque_plus_dans_la_foulee(foyer):
    """
    Le défaut signalé en service : « le registre affiche tous les champs, mais le
    serveur de travaux indique champ manquant ».

    Le serveur de travaux déduit la valeur puis contrôle la conformité **dans la
    même session**. Or `remplir` ajoutait la métadonnée par sa clé étrangère,
    sans l'attacher à la collection déjà chargée du document : `flush` écrit bien
    la ligne, mais ne rafraîchit pas une collection chargée. Le contrôle lisait
    donc un document encore dépourvu de son émetteur, bloquait le travail et
    posait le statut « incomplet » — tandis que le registre, qui repart d'une
    session neuve, montrait la valeur.

    Le test reproduit exactement cet enchaînement : déduction, puis contrôle,
    sans rouvrir de session entre les deux.
    """
    from app import conformite

    _regler_deduction(foyer, "toutes")
    session = SessionLocal()
    try:
        regle = session.query(RegleChampCategorie).filter_by(
            categorie_id=foyer, champ="meta:titulaire").one()
        regle.obligatoire = True
        session.commit()
    finally:
        session.close()

    identifiant = _document("_ratt_conformite.pdf", foyer,
                            "Facture établie au nom de Jean Dupont")
    session = SessionLocal()
    try:
        document = session.get(Document, identifiant)
        assert references_auto.remplir(session, document), "le titulaire doit être déduit"
        session.flush()
        manquants = conformite.champs_manquants(
            document, conformite.regles_par_categorie(session, {foyer}))
        assert manquants == [], \
            f"le titulaire vient d'être déduit, il ne peut pas manquer : {manquants}"
    finally:
        session.rollback()
        session.close()
