"""
L'emplacement du dépôt fait foi (§19.3).

Le classement était deviné : le serveur essayait des expressions régulières sur
le texte océrisé et rangeait le document là où la première correspondait. Il se
déclare maintenant — on dépose dans le dossier du type, et c'est tout.

Ce que ces tests surveillent : que l'emplacement soit bien la seule source du
classement, et que ce qui est déposé ailleurs s'arrête **avant** l'étape coûteuse
plutôt que d'être rangé au hasard.
"""
import pytest

from app import categories as natures, config, depots, worker
from app.db import Categorie, Document, Job, SessionLocal


@pytest.fixture
def depot(tmp_path, monkeypatch, base_de_test):
    """Un dépôt à soi, avec un type de document et son dossier."""
    monkeypatch.setattr(config, "OCR_WAIT_FOLDER", str(tmp_path / "ocr_wait"))
    monkeypatch.setattr(config, "TRAVAUX_FOLDER", str(tmp_path / "travaux"))

    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_empl%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_empl%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Empl%")).delete(
            synchronize_session=False)
        type_doc = Categorie(nom="_EmplContrats", nature=natures.TYPE, ordre=940)
        session.add(type_doc)
        session.flush()
        depots.attribuer(session, type_doc)
        session.commit()
        contexte = {"type": type_doc.id, "dossier": type_doc.dossier_depot}
    finally:
        session.close()

    depots.synchroniser(SessionLocal())
    yield contexte

    session = SessionLocal()
    try:
        session.query(Job).filter(Job.nom_fichier.like("_empl%")).delete(
            synchronize_session=False)
        session.query(Document).filter(Document.nom_fichier.like("_empl%")).delete(
            synchronize_session=False)
        session.query(Categorie).filter(Categorie.nom.like("_Empl%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _dernier_job(nom):
    session = SessionLocal()
    try:
        return (session.query(Job).filter_by(nom_fichier=nom)
                .order_by(Job.id.desc()).first())
    finally:
        session.close()


def test_un_fichier_a_la_racine_sarrete_a_classer(depot):
    """
    Personne ne le revendique : le ranger au jugé serait une surprise qu'on
    découvre trop tard. Il attend qu'on dise de quoi il s'agit.
    """
    fichier = depots.racine() / "_empl_racine.pdf"
    fichier.write_bytes(b"%PDF-1.7 " + b"x" * 200)

    worker.traiter_fichier(fichier)

    job = _dernier_job("_empl_racine.pdf")
    assert job is not None and job.statut == "a_classer"
    assert job.document_id is None, "rien n'est indexé tant que le type est inconnu"
    assert "ocr_wait" in (job.diagnostic or ""), "le diagnostic doit dire où déposer"


def test_un_fichier_a_classer_nest_pas_ocerise(depot):
    """
    Décision D6 : le texte reconnu ne servirait à rien tant qu'on ignore de quoi
    il s'agit, et l'océrisation est l'étape la plus coûteuse du traitement. Ce
    test le prouve en la rendant impossible — si elle était tentée, il échouerait.
    """
    def refuser(*args, **kwargs):
        raise AssertionError("l'océrisation ne doit pas avoir lieu avant le classement")

    fichier = depots.racine() / "_empl_sans_ocr.pdf"
    fichier.write_bytes(b"%PDF-1.7 " + b"y" * 200)

    ancien = worker.ocr_to_searchable_pdf
    worker.ocr_to_searchable_pdf = refuser
    try:
        worker.traiter_fichier(fichier)
    finally:
        worker.ocr_to_searchable_pdf = ancien

    assert _dernier_job("_empl_sans_ocr.pdf").statut == "a_classer"


def test_un_fichier_dans_un_dossier_inconnu_sarrete_aussi(depot):
    """Un dossier créé à la main n'est réclamé par aucun type."""
    inconnu = depots.racine() / "cree_a_la_main"
    inconnu.mkdir(parents=True, exist_ok=True)
    fichier = inconnu / "_empl_inconnu.pdf"
    fichier.write_bytes(b"%PDF-1.7 " + b"z" * 200)

    worker.traiter_fichier(fichier)

    assert _dernier_job("_empl_inconnu.pdf").statut == "a_classer"


def test_le_fichier_a_classer_est_conserve(depot):
    """
    Il quitte le dépôt pour le dossier de sa tâche (§18.53) : sans cela, chaque
    balayage le retraiterait et créerait un travail de plus. Et il reste
    consultable — c'est ce qui permettra de le ranger sans l'avoir perdu.
    """
    fichier = depots.racine() / "_empl_conserve.pdf"
    fichier.write_bytes(b"%PDF-1.7 " + b"w" * 200)

    worker.traiter_fichier(fichier)

    job = _dernier_job("_empl_conserve.pdf")
    assert not fichier.exists(), "il ne doit plus être balayé"
    assert job.chemin_source and str(job.id) in job.chemin_source


def test_un_travail_a_classer_nest_pas_purge(depot):
    """
    Comme « bloqué » ou « en erreur », il appelle une action. Le purger ferait
    disparaître un fichier que personne n'a classé.
    """
    assert "a_classer" not in worker.STATUTS_PURGEABLES


def test_le_classement_par_expression_reguliere_a_disparu():
    """
    Deux mécanismes concurrents pour ranger un document, c'est un de trop : celui
    qu'on ne voit pas gagne toujours au mauvais moment.
    """
    from app import regex_engine

    assert not hasattr(regex_engine, "identifier_categorie")
    assert not hasattr(Categorie, "regex_identification")
    assert not hasattr(Categorie, "priorite"), \
        "la priorité n'ordonnait que les expressions de classement"


def _travail_a_classer(depot, nom="_empl_a_ranger.pdf"):
    fichier = depots.racine() / nom
    fichier.write_bytes(b"%PDF-1.7 " + b"r" * 200)
    worker.traiter_fichier(fichier)
    return _dernier_job(nom)


def test_classer_deplace_le_fichier_et_rend_la_main_au_serveur(client, depot):
    """
    Le service rendu (§19.4) : on dit de quel type il s'agit, le fichier rejoint
    le dossier correspondant, et le serveur reprend. Pas de chemin de traitement
    parallèle — c'est ce qui garantit qu'un classement à la main vaut un dépôt
    bien fait.
    """
    job = _travail_a_classer(depot)

    reponse = client.post(f"/a-classer/{job.id}", json={"categorie_id": depot["type"]})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["dossier_depot"] == depot["dossier"]

    session = SessionLocal()
    try:
        consigne = session.get(Job, job.id)
        assert consigne.categorie_demandee == depot["type"]
        assert consigne.rejouer_demande is True
        assert consigne.etape_demandee == "empreinte", \
            "rien n'a encore été fait de ce fichier : la reprise part du début"
        assert consigne.statut == "en_attente"
    finally:
        session.close()

    # C'est le serveur de travaux qui déplace : les fichiers reçus lui sont
    # montés en lecture seule côté API, et la consigne se relève au passage
    # suivant, comme une demande de rejeu ordinaire.
    worker._ranger_avant_rejeu(job.id)

    attendu = depots.chemin(depot["dossier"]) / job.nom_fichier
    assert attendu.is_file(), "le fichier doit rejoindre le dossier de son type"
    session = SessionLocal()
    try:
        range_ = session.get(Job, job.id)
        assert range_.chemin_source == str(attendu)
        assert range_.categorie_demandee is None, "la consigne est exécutée, pas gardée"
    finally:
        session.close()


def test_un_fichier_reclame_par_un_travail_ne_donne_pas_un_second(client, depot):
    """
    Après un classement, deux chemins mènent au même fichier : la surveillance du
    dossier et le rejeu demandé. Sans garde-fou, le dépôt produisait deux travaux
    dont l'un finissait « doublon », sans que rien ne l'explique.
    """
    job = _travail_a_classer(depot, "_empl_double.pdf")
    client.post(f"/a-classer/{job.id}", json={"categorie_id": depot["type"]})
    worker._ranger_avant_rejeu(job.id)

    # la surveillance repasse avant le rejeu : elle doit retrouver le travail
    worker.traiter_fichier(depots.chemin(depot["dossier"]) / "_empl_double.pdf")

    session = SessionLocal()
    try:
        travaux = session.query(Job).filter_by(nom_fichier="_empl_double.pdf").all()
        assert len(travaux) == 1, "un seul travail pour un seul fichier"
    finally:
        session.close()


def test_on_ne_classe_pas_dans_un_dossier(client, depot):
    """Un dossier de classement n'a pas de dossier de dépôt : il n'y a nulle part où poser."""
    job = _travail_a_classer(depot, "_empl_refus.pdf")
    session = SessionLocal()
    try:
        rangement = Categorie(nom="_EmplRangement", nature=natures.DOSSIER, ordre=941)
        session.add(rangement)
        session.commit()
        identifiant = rangement.id
    finally:
        session.close()

    refus = client.post(f"/a-classer/{job.id}", json={"categorie_id": identifiant})
    assert refus.status_code == 400
    assert "dossier" in refus.json()["detail"]


def test_un_travail_deja_classe_ne_se_reclasse_pas(client, depot):
    """Le fichier a bougé : reclasser le déplacerait une seconde fois, depuis nulle part."""
    job = _travail_a_classer(depot, "_empl_unique.pdf")
    assert client.post(f"/a-classer/{job.id}",
                       json={"categorie_id": depot["type"]}).status_code == 200
    second = client.post(f"/a-classer/{job.id}", json={"categorie_id": depot["type"]})
    assert second.status_code == 404


def test_le_centre_danalyse_annonce_ce_qui_attend_un_type(client, depot):
    job = _travail_a_classer(depot, "_empl_liste.pdf")
    liste = client.get("/a-classer").json()
    ligne = next((t for t in liste if t["id"] == job.id), None)
    assert ligne is not None
    assert ligne["fichier_disponible"] is True, \
        "sans le fichier, il n'y a rien à regarder pour décider"
    assert ligne["taille_octets"] > 0


def test_une_consigne_qui_ne_peut_plus_sappliquer_est_retiree(client, depot):
    """
    Type supprimé entre-temps, fichier disparu : la consigne ne doit pas être
    relevée à chaque passage du serveur. On la retire, le travail reste visible.
    """
    job = _travail_a_classer(depot, "_empl_consigne.pdf")
    client.post(f"/a-classer/{job.id}", json={"categorie_id": depot["type"]})

    session = SessionLocal()
    try:
        session.query(Categorie).filter_by(id=depot["type"]).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()

    worker._ranger_avant_rejeu(job.id)

    session = SessionLocal()
    try:
        assert session.get(Job, job.id).categorie_demandee is None
    finally:
        session.close()
