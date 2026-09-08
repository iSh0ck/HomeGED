"""
Versions d'un document (§18.36).

Un document du foyer n'est pas figé : on rescanne une facture mal cadrée, on
reçoit la version corrigée d'un avis. Chaque dépôt devient une version de la
même fiche — au lieu d'une fiche de plus, sans lien avec la première.

Ce que ces tests surveillent surtout, c'est la **retenue** du rapprochement : il
repose sur une supposition (même catégorie, même émetteur, même date), et une
supposition trop large fusionnerait deux pièces distinctes.
"""
from datetime import date

import pytest

from app import versions
from app.db import (
    Categorie, Document, Metadonnee, RegleChampCategorie, SessionLocal,
    VersionDocument,
)


@pytest.fixture
def deux_documents(base_de_test, tmp_path):
    """
    Deux fiches identiques quant à ce qui les identifie, et leurs fichiers.

    La catégorie déclare son champ identifiant (§18.40) : sans cette déclaration,
    aucun rapprochement n'a lieu, et c'est bien le comportement voulu.
    """
    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ver%")).delete(
            synchronize_session=False)
        categorie = session.query(Categorie).first()
        if categorie:
            regle = (session.query(RegleChampCategorie)
                     .filter_by(categorie_id=categorie.id, champ="meta:numero_facture")
                     .one_or_none())
            if not regle:
                regle = RegleChampCategorie(categorie_id=categorie.id,
                                            champ="meta:numero_facture",
                                            libelle="N° facture", obligatoire=False, ordre=5)
                session.add(regle)
            regle.identifiant = True
            session.flush()

        fichiers = []
        identifiants = []
        for numero in (1, 2):
            fichier = tmp_path / f"_ver_{numero}.pdf"
            fichier.write_bytes(b"%PDF-1.7\n" + bytes([numero]) * 200)
            fichiers.append(fichier)
            document = Document(
                nom_fichier=f"_ver_{numero}.pdf", chemin_stockage=str(fichier),
                hash_sha256=f"version{numero}".ljust(64, "v"), texte_ocr="x",
                statut="traite", categorie_id=categorie.id if categorie else None,
                date_document=date(2026, 8, 21),
                taille_octets=fichier.stat().st_size,
            )
            session.add(document)
            session.flush()
            # Ce qui désigne la pièce : sans cela, aucun rapprochement n'a lieu
            # — et c'est voulu (cf. `CLES_IDENTIFIANTES`).
            session.add(Metadonnee(document_id=document.id, cle="numero_facture",
                                   valeur="FR-2026-08-21"))
            identifiants.append(document.id)
        session.commit()
    finally:
        session.close()

    yield identifiants, fichiers

    session = SessionLocal()
    try:
        session.query(Document).filter(Document.nom_fichier.like("_ver%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_un_document_est_sa_propre_premiere_version(client, deux_documents):
    """
    Une fiche antérieure au versionnage n'a aucune version : son fichier d'origine
    en devient une, datée de son import. Sans cela, l'historique commencerait au
    deuxième dépôt et l'original ne serait nulle part.
    """
    identifiants, _ = deux_documents
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        versions._assurer_version_initiale(session, document)
        session.commit()
        liste = versions.lister(session, identifiants[0])
    finally:
        session.close()

    assert len(liste) == 1
    assert liste[0]["courante"] is True
    assert liste[0]["nom_fichier"] == "_ver_1.pdf"


def test_un_nouveau_depot_devient_la_version_courante(client, deux_documents):
    identifiants, fichiers = deux_documents
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        versions.enregistrer_depot(session, document, str(fichiers[1]), "rescan.pdf",
                                   "rescan".ljust(64, "r"))
        session.commit()

        liste = versions.lister(session, identifiants[0])
        document = session.get(Document, identifiants[0])
        chemin, empreinte = document.chemin_stockage, document.hash_sha256
    finally:
        session.close()

    assert [v["courante"] for v in liste] == [True, False], "la plus récente d'abord"
    assert liste[0]["nom_fichier"] == "rescan.pdf"
    # la fiche montre le dernier état : sans cela il faudrait aller chercher la
    # bonne version à chaque consultation
    assert chemin == str(fichiers[1])
    assert empreinte == "rescan".ljust(64, "r")


def test_le_rapprochement_exige_une_metadonnee_identifiante(client, deux_documents):
    """
    C'est la **catégorie** qui dit sur quoi se fonder : les champs cochés comme
    identifiants dans ses champs attendus. Sans déclaration, aucun rapprochement
    — et c'est voulu : deviner reviendrait à fusionner deux pièces distinctes.
    """
    identifiants, _ = deux_documents
    session = SessionLocal()
    try:
        second = session.get(Document, identifiants[1])
        assert versions.document_jumeau(session, second) is not None, \
            "les deux portent le même numéro de facture"

        # on retire ce qui les désigne : le rapprochement doit s'abstenir
        for metadonnee in list(second.metadonnees):
            session.delete(metadonnee)
        session.flush()
        session.refresh(second)
        assert versions.document_jumeau(session, second) is None

        # la date non plus ne se devine pas
        second.date_document = None
        session.flush()
        assert versions.document_jumeau(session, second) is None
    finally:
        session.rollback()
        session.close()


def test_sans_champ_identifiant_declare_rien_ne_se_rapproche(client, deux_documents):
    """
    L'abstention est le comportement par défaut : une catégorie qui n'a rien
    déclaré ne verra jamais deux de ses documents fusionner par surprise.
    """
    identifiants, _ = deux_documents
    session = SessionLocal()
    try:
        second = session.get(Document, identifiants[1])
        session.query(RegleChampCategorie).filter_by(
            categorie_id=second.categorie_id).update({"identifiant": False},
                                                     synchronize_session=False)
        session.flush()
        session.expire_all()
        second = session.get(Document, identifiants[1])
        assert versions.champs_identifiants(session, second.categorie_id) == []
        assert versions.document_jumeau(session, second) is None
    finally:
        session.rollback()
        session.close()


def test_plusieurs_champs_identifiants_comptent_ensemble(client, deux_documents):
    """
    Deux documents ne sont la même pièce que s'ils s'accordent sur **tous** les
    champs déclarés : un numéro identique mais une date différente, ce sont deux
    pièces.
    """
    identifiants, _ = deux_documents
    session = SessionLocal()
    try:
        second = session.get(Document, identifiants[1])
        regle = (session.query(RegleChampCategorie)
                 .filter_by(categorie_id=second.categorie_id, champ="date_document")
                 .one_or_none())
        if not regle:
            regle = RegleChampCategorie(categorie_id=second.categorie_id,
                                        champ="date_document", obligatoire=False, ordre=6)
            session.add(regle)
        regle.identifiant = True
        session.flush()
        assert versions.document_jumeau(session, second) is not None

        second.date_document = date(2026, 12, 25)
        session.flush()
        assert versions.document_jumeau(session, second) is None
    finally:
        session.rollback()
        session.close()


def test_l_api_rend_les_versions_et_leur_fichier(client, deux_documents):
    identifiants, fichiers = deux_documents
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        versions.enregistrer_depot(session, document, str(fichiers[1]), "rescan.pdf",
                                   "rescan2".ljust(64, "r"))
        session.commit()
    finally:
        session.close()

    liste = client.get(f"/documents/{identifiants[0]}/versions").json()
    assert len(liste) == 2
    assert liste[0]["fichier_present"] is True

    fichier = client.get(f"/documents/{identifiants[0]}/versions/{liste[1]['id']}/fichier")
    assert fichier.status_code == 200
    assert fichier.content.startswith(b"%PDF")

    # et le décompte accompagne le document, pour que le tableau sache quoi montrer
    fiche = client.get(f"/documents/{identifiants[0]}").json()
    assert fiche["nb_versions"] == 2


def test_supprimer_une_version_promeut_la_precedente(client, deux_documents):
    identifiants, fichiers = deux_documents
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        versions.enregistrer_depot(session, document, str(fichiers[1]), "rescan.pdf",
                                   "rescan3".ljust(64, "r"))
        session.commit()
    finally:
        session.close()

    liste = client.get(f"/documents/{identifiants[0]}/versions").json()
    courante = next(v for v in liste if v["courante"])
    suppression = client.delete(f"/documents/{identifiants[0]}/versions/{courante['id']}")
    assert suppression.status_code == 200, suppression.text

    apres = client.get(f"/documents/{identifiants[0]}/versions").json()
    assert len(apres) == 1
    assert apres[0]["courante"] is True, "la fiche doit toujours montrer quelque chose"


def test_on_ne_supprime_pas_la_seule_version(client, deux_documents):
    """Une fiche sans fichier ne s'ouvre plus, et rien ne dirait pourquoi."""
    identifiants, _ = deux_documents
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        versions._assurer_version_initiale(session, document)
        session.commit()
        seule = session.query(VersionDocument).filter_by(document_id=identifiants[0]).one()
        version_id = seule.id
    finally:
        session.close()

    refus = client.delete(f"/documents/{identifiants[0]}/versions/{version_id}")
    assert refus.status_code == 409
    assert "seule version" in refus.json()["detail"]


def test_seul_un_administrateur_supprime_une_version(client, deux_documents):
    identifiants, fichiers = deux_documents
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        # Sans catégorie : le document est alors visible de tout compte connecté
        # (choix de conception S10). C'est ce qui permet d'éprouver le droit de
        # **suppression** sans le confondre avec un droit de lecture manquant —
        # ce que la première version de ce test faisait, et le 403 obtenu ne
        # prouvait alors rien.
        document.categorie_id = None
        versions.enregistrer_depot(session, document, str(fichiers[1]), "rescan.pdf",
                                   "rescan4".ljust(64, "r"))
        session.commit()
        version_id = (session.query(VersionDocument)
                      .filter_by(document_id=identifiants[0], courante=True).one().id)
    finally:
        session.close()

    cree = client.post("/admin/utilisateurs", json={
        "email": "_t_versions@homeged.local", "nom": "Petit", "prenom": "Marc",
        "mot_de_passe": "MotDePasse!42", "est_admin": False, "actif": True, "role_ids": [],
    })
    assert cree.status_code == 200, cree.text
    try:
        from fastapi.testclient import TestClient
        from app.api import app
        with TestClient(app) as ordinaire:
            jeton = ordinaire.post("/auth/login", data={
                "username": "_t_versions@homeged.local", "password": "MotDePasse!42"}).json()
            ordinaire.headers["Authorization"] = f"Bearer {jeton['access_token']}"
            # il consulte…
            assert ordinaire.get(f"/documents/{identifiants[0]}/versions").status_code == 200
            # …mais n'efface pas
            assert ordinaire.delete(
                f"/documents/{identifiants[0]}/versions/{version_id}").status_code == 403
    finally:
        client.delete(f"/admin/utilisateurs/{cree.json()['id']}")


def test_un_fichier_deja_deposé_est_reconnu_meme_comme_ancienne_version(client, deux_documents):
    """
    Redéposer une ancienne version ne doit pas créer de fiche : l'empreinte la
    reconnaît, quelle que soit la version où elle se trouve.
    """
    identifiants, fichiers = deux_documents
    session = SessionLocal()
    try:
        document = session.get(Document, identifiants[0])
        versions.enregistrer_depot(session, document, str(fichiers[1]), "rescan.pdf",
                                   "rescan5".ljust(64, "r"))
        session.commit()

        # l'empreinte du fichier d'origine appartient désormais à une version
        # non courante : elle doit rester reconnue
        trouvee = versions.version_par_empreinte(session, "version1".ljust(64, "v"))
        assert trouvee is not None
        assert trouvee.document_id == identifiants[0]
    finally:
        session.close()


def test_le_depot_dun_document_deja_connu_cree_une_version(client, base_de_test, tmp_path,
                                                          monkeypatch):
    """
    Le chemin complet, celui qui compte : deux dépôts successifs de la même
    pièce, par le serveur de travaux, et une seule fiche à l'arrivée.

    On passe par `traiter_fichier` plutôt que par les fonctions de versionnage :
    c'est l'enchaînement — océrisation, extraction, rapprochement — qui doit être
    juste, et c'est là que le premier critère s'était révélé inapplicable, faute
    d'émetteur sur un document fraîchement déposé.
    """
    import subprocess

    from app import config, depots, worker
    from app.db import Job

    # Les archives réelles sont montées en lecture seule dans le conteneur de
    # test : le dépôt écrit donc dans un dossier jetable. Sans cela, l'océrisation
    # échoue sur un « permission refusée » que rien ne relie au versionnage.
    monkeypatch.setattr(config, "STORAGE_FOLDER", str(tmp_path / "archives"))
    monkeypatch.setattr(config, "OCR_WAIT_FOLDER", str(tmp_path / "veille"))

    # Une facture née numérique, comme dans les tests d'océrisation : rapide à
    # traiter (pas de rastérisation) et porteuse de ce qu'il faut extraire.
    postscript = tmp_path / "facture.ps"
    postscript.write_text(
        "%!PS\n"
        "/Helvetica findfont 11 scalefont setfont\n"
        "72 780 moveto (FACTURE) show\n"
        # « no » et non « n » : la règle semée cherche « n° » ou « no », et
        # PostScript n'écrit pas le degré sans encodage particulier. Sans lui,
        # aucun numéro n'est extrait — donc aucun identifiant, donc aucun
        # rapprochement, et le test échouait pour une raison qui n'est pas la sienne.
        "72 760 moveto (Facture no 2026-00184 du 12/03/2026) show\n"
        "72 740 moveto (TOTAL TTC : 116,52 EUR) show\n"
        "showpage\n")
    modele = tmp_path / "modele.pdf"
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
                    f"-sOutputFile={modele}", str(postscript)],
                   check=True, capture_output=True)

    session = SessionLocal()
    try:
        session.query(Job).delete(synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_depot%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()

    # Depuis le §19.3, c'est l'emplacement du dépôt qui donne le type de document :
    # un fichier posé ailleurs que dans le dossier d'un type s'arrête à « à classer »
    # et n'est même pas océrisé. Le dépôt de ce test passe donc par le dossier d'un
    # vrai type, comme un dépôt réel.
    session = SessionLocal()
    try:
        type_accueil = session.query(Categorie).filter(
            Categorie.dossier_depot.isnot(None)).order_by(Categorie.id).first()
        assert type_accueil is not None, "il faut au moins un type de document"
        dossier_depot = type_accueil.dossier_depot
        identifiant_type = type_accueil.id
    finally:
        session.close()

    depots.creer(dossier_depot)

    def deposer(nom, octets_en_plus=b""):
        """Copie le modèle sous un autre nom, avec de quoi changer son empreinte."""
        cible = depots.chemin(dossier_depot) / nom
        cible.write_bytes(modele.read_bytes() + octets_en_plus)
        worker.traiter_fichier(cible)

    try:
        deposer("_depot_1.pdf")
        session = SessionLocal()
        try:
            # La catégorie d'accueil déclare son identifiant : sans cela, aucun
            # rapprochement n'a lieu — c'est le comportement par défaut (§18.40).
            depose = session.query(Document).filter(
                Document.nom_fichier.like("_depot%")).first()
            if depose and depose.categorie_id:
                regle = (session.query(RegleChampCategorie)
                         .filter_by(categorie_id=depose.categorie_id,
                                    champ="meta:numero_facture").one_or_none())
                if not regle:
                    regle = RegleChampCategorie(categorie_id=depose.categorie_id,
                                                champ="meta:numero_facture",
                                                obligatoire=False, ordre=5)
                    session.add(regle)
                regle.identifiant = True
                session.commit()
        finally:
            session.close()

        session = SessionLocal()
        try:
            documents = session.query(Document).filter(
                Document.nom_fichier.like("_depot%")).all()
            assert len(documents) == 1, "le premier dépôt crée une fiche"
            premier = documents[0]
            assert premier.date_document is not None, "l'extraction doit lire la date"
            identifiant = premier.id
            assert len(versions.lister(session, identifiant)) == 1
        finally:
            session.close()

        # Le même document rescanné : mêmes valeurs extraites, fichier différent.
        deposer("_depot_2.pdf", b"\n% rescan\n")

        session = SessionLocal()
        try:
            documents = session.query(Document).filter(
                Document.nom_fichier.like("_depot%")).all()
            assert len(documents) == 1, "toujours une seule fiche : c'est le même papier"
            liste = versions.lister(session, identifiant)
            assert len(liste) == 2, "deux dépôts, deux versions"
            assert liste[0]["courante"] is True
            assert liste[0]["nom_fichier"] == "_depot_2.pdf", "la dernière prend la main"
        finally:
            session.close()

        # Et le même fichier, au bit près : rien à ajouter.
        deposer("_depot_3.pdf")
        session = SessionLocal()
        try:
            assert len(versions.lister(session, identifiant)) == 2, \
                "un fichier identique ne raconte rien de neuf"
        finally:
            session.close()
    finally:
        session = SessionLocal()
        try:
            session.query(Document).filter(Document.nom_fichier.like("_depot%")).delete(
                synchronize_session=False)
            session.commit()
        finally:
            session.close()
