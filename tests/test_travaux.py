

def test_un_depot_secarte_depuis_le_centre_danalyse(client):
    """
    Un fichier « à classer » n'est pas toujours à classer (§21.14) : un double
    scan, une page de garde. On pouvait dire de quel type il était, jamais qu'il
    n'en était aucun — et il restait là à appeler une action.

    L'API pose la consigne, le serveur de travaux efface le fichier reçu : elle
    seule a les fichiers reçus en lecture seule.
    """
    from app.db import Job, SessionLocal

    session = SessionLocal()
    try:
        job = Job(nom_fichier="_ecarte.pdf", statut="a_classer",
                  chemin_source="/tmp/_ecarte.pdf")
        session.add(job)
        session.commit()
        identifiant = job.id
    finally:
        session.close()

    try:
        assert identifiant in {t["id"] for t in client.get("/a-classer").json()}

        assert client.delete(f"/a-classer/{identifiant}").status_code == 200

        session = SessionLocal()
        try:
            releve = session.get(Job, identifiant)
            assert releve.rejet_demande is True, "la consigne est posée…"
            assert releve.statut == "a_classer", "…et le worker fera le reste"
            assert "Écarté" in (releve.diagnostic or ""), "on sait qui l'a écarté"
        finally:
            session.close()
    finally:
        session = SessionLocal()
        try:
            session.query(Job).filter(Job.nom_fichier == "_ecarte.pdf").delete()
            session.commit()
        finally:
            session.close()


def test_le_serveur_de_travaux_execute_lecartement(tmp_path):
    """Le fichier reçu est effacé, et le travail garde sa trace dans le suivi."""
    from app.db import Job, SessionLocal
    from app import worker

    fichier = tmp_path / "_ecarte2.pdf"
    fichier.write_bytes(b"%PDF")
    session = SessionLocal()
    try:
        job = Job(nom_fichier="_ecarte2.pdf", statut="a_classer",
                  chemin_source=str(fichier), rejet_demande=True,
                  diagnostic="Écarté depuis le Centre d'analyse par Essai")
        session.add(job)
        session.commit()
        identifiant = job.id
    finally:
        session.close()

    try:
        assert worker.traiter_rejets() >= 1
        assert not fichier.exists(), "le dépôt écarté est effacé"

        session = SessionLocal()
        try:
            releve = session.get(Job, identifiant)
            assert releve.statut == "ignore"
            assert releve.rejet_demande is False
            assert "Écarté" in releve.diagnostic
        finally:
            session.close()
    finally:
        session = SessionLocal()
        try:
            session.query(Job).filter(Job.nom_fichier == "_ecarte2.pdf").delete()
            session.commit()
        finally:
            session.close()


def test_un_travail_rejoue_retrouve_son_type(base_de_test, tmp_path, monkeypatch):
    """
    Le classement vient de l'emplacement du dépôt (§19.3), et c'est une bonne
    règle — rien n'est deviné sur le texte. Mais au **rejeu**, le fichier n'est
    plus dans le dossier où on l'avait mis : il vit dans `travaux/`, où le serveur
    l'avait conservé. L'emplacement ne dit plus rien, et le travail retombait
    « à classer » : on redemandait une réponse déjà donnée (§21.15).
    """
    from app import config, depots, worker
    from app.db import Categorie, Job, SessionLocal

    monkeypatch.setattr(config, "OCR_WAIT_FOLDER", str(tmp_path / "ocr_wait"))

    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        depots.creer(type_doc.dossier_depot)
        identifiant_type = type_doc.id
        nom_type = type_doc.nom
        nom_dossier = type_doc.dossier_depot

        # Le fichier tel qu'il est au rejeu : hors du dossier de dépôt.
        ailleurs = tmp_path / "travaux" / "12"
        ailleurs.mkdir(parents=True)
        fichier = ailleurs / "_rejeu.pdf"
        fichier.write_bytes(b"%PDF")

        # Sans souvenir, l'emplacement ne dit rien…
        assert depots.type_du_chemin(session, fichier) is None

        job = Job(nom_fichier="_rejeu.pdf", statut="bloque",
                  chemin_source=str(fichier), categorie_id=identifiant_type)
        session.add(job)
        session.commit()
        identifiant_job = job.id
    finally:
        session.close()

    try:
        session = SessionLocal()
        try:
            releve = session.get(Job, identifiant_job)
            # …mais le travail, lui, s'en souvient : c'est la règle qui décide.
            retrouve = worker.type_du_travail(session, fichier, releve)
            assert retrouve is not None and retrouve.nom == nom_type

            # Sans travail, ou sans souvenir, l'emplacement reste seul juge : un
            # fichier posé n'importe où reste « à classer ».
            assert worker.type_du_travail(session, fichier, None) is None
            releve.categorie_id = None
            assert worker.type_du_travail(session, fichier, releve) is None

            # Et quand le dossier parle, c'est lui qui l'emporte : on a pu
            # déplacer le fichier depuis, et c'est le geste le plus récent.
            dans_le_dossier = depots.chemin(nom_dossier) / "_rejeu.pdf"
            dans_le_dossier.write_bytes(b"%PDF")
            releve.categorie_id = 999999   # un souvenir devenu faux
            assert worker.type_du_travail(session, dans_le_dossier, releve).nom == nom_type
        finally:
            session.close()
    finally:
        session = SessionLocal()
        try:
            session.query(Job).filter(Job.nom_fichier == "_rejeu.pdf").delete()
            session.commit()
        finally:
            session.close()
