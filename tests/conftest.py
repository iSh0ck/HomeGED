"""
Socle des tests.

Les tests tournent sur une **base dédiée**, construite comme une installation
neuve : `db/schema.sql` puis toutes les migrations, dans l'ordre. Cela vérifie
au passage que ces deux sources restent compatibles — c'est précisément là que
plusieurs défauts sont passés inaperçus (schéma divergent, colonnes sans valeur
par défaut, clés étrangères en RESTRICT).

Aucune donnée de l'installation réelle n'est touchée : le nom de la base est
imposé par la variable d'environnement `DB_NAME` avant tout import applicatif.
"""
import os
import re
import tempfile
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# Doit précéder l'import des modules applicatifs : `app.config` lit
# l'environnement à l'import, et `app.db` crée le moteur dans la foulée.
#
# **Une base par processus de test** (§18.34). La suite s'exécute en parallèle ;
# or chaque processus reconstruit le schéma au démarrage et plusieurs tests
# vident des tables entières. Sur une base commune, ils se détruiraient
# mutuellement — et les échecs seraient d'autant plus difficiles à lire qu'ils
# dépendraient de l'ordre d'exécution. `PYTEST_XDIST_WORKER` vaut « gw0 »,
# « gw1 »… dans les processus parallèles, et rien du tout en exécution simple.
_processus = os.environ.get("PYTEST_XDIST_WORKER", "")
_base = os.environ.get("DB_NAME", "homeged_test")
# `setdefault` ne suffisait pas : le harnais passe déjà `DB_NAME`, si bien que le
# suffixe était ignoré et que tous les processus travaillaient sur la même base —
# ils s'y détruisaient mutuellement le schéma. On dérive donc du nom reçu.
os.environ["DB_NAME"] = f"{_base}_{_processus}" if _processus else _base
os.environ.setdefault("SECRET_KEY", "cle-de-test-suffisamment-longue-pour-les-tests")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.local")
os.environ.setdefault("ADMIN_PASSWORD", "motdepasse-de-test-1234")

# Les tests d'export construisent de vraies archives. Sans cette ligne, elles
# atterrissent dans le dossier d'export de l'installation réelle et y restent :
# leurs lignes en base disparaissent avec la base de test, plus rien ne les
# réclame. Une copie complète des documents du foyer oubliée sur le disque par
# la suite de tests — exactement ce que la fonctionnalité cherche à éviter.
os.environ.setdefault(
    "EXPORT_FOLDER", tempfile.mkdtemp(prefix="homeged-exports-test-")
)

# Même raison pour les dépôts manuels (§22.1) : l'API y écrit le fichier glissé
# dans une fiche simple avant que le serveur de travaux ne le reprenne. Sans
# cette ligne, la suite déposerait ses fichiers d'essai dans la file de
# l'installation réelle, qui les archiverait pour de bon.
os.environ.setdefault(
    "DEPOTS_MANUELS_FOLDER", tempfile.mkdtemp(prefix="homeged-depots-test-")
)

from app import auth, config  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.migrations import _instructions, appliquer_migrations  # noqa: E402


def _appliquer_schema_initial(connexion):
    """
    Rejoue `db/schema.sql` comme le ferait MariaDB à la création du volume.
    Les deux premières instructions (CREATE DATABASE / USE) sont écartées : la
    base de test est déjà choisie par la connexion.
    """
    sql = (RACINE / "db" / "schema.sql").read_text(encoding="utf-8")
    for instruction in _instructions(sql):
        if re.match(r"^\s*(CREATE\s+DATABASE|USE)\b", instruction, re.IGNORECASE):
            continue
        connexion.exec_driver_sql(instruction)


def _creer_base_si_absente():
    """
    Crée la base de ce processus s'il n'en a pas encore.

    En exécution parallèle, chaque processus a la sienne (`homeged_test_gw0`…) ;
    le script d'appel ne peut pas les créer d'avance, il ignore combien il y en
    aura. On se connecte donc au serveur sans base pour la créer.
    """
    from sqlalchemy import create_engine

    from app import config

    sans_base = create_engine(
        f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/?charset=utf8mb4"
    )
    with sans_base.connect() as connexion:
        connexion.exec_driver_sql(
            f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        connexion.commit()
    sans_base.dispose()


def reconstruire_base():
    """
    Remet la base dans l'état d'une installation neuve : toutes les tables
    supprimées, `db/schema.sql` rejoué, migrations vérifiées.

    Extrait de la fixture de session pour qu'un test qui abîme volontairement
    l'état commun puisse le rendre — celui de l'installation « page blanche »,
    qui efface le classement semé dont d'autres tests ont besoin.
    """
    with engine.connect() as connexion:
        # On vide la base de **toutes** ses tables, quels qu'en soient les noms :
        # une liste tenue à la main se périme au premier renommage, et laisse
        # alors traîner des tables d'une exécution précédente. Les contraintes
        # sont désactivées le temps de la suppression, l'ordre n'ayant alors
        # plus d'importance.
        connexion.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        tables = [ligne[0] for ligne in connexion.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")]
        for nom in tables:
            connexion.exec_driver_sql(f"DROP TABLE IF EXISTS `{nom}`")
        connexion.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
        connexion.commit()
        _appliquer_schema_initial(connexion)
        connexion.commit()
    # `db/schema.sql` inscrit déjà les migrations comme appliquées : cet appel
    # ne devrait donc rien faire. On le garde pour vérifier justement cela — que
    # le repère est bien posé et qu'une installation neuve ne rejoue rien.
    appliquer_migrations()
    # Le schéma vient d'être refait **hors** des chemins qui savent le dire
    # (§22.40) : ce que l'application avait retenu de sa forme ne vaut plus rien.
    from app import base_donnees
    base_donnees.oublier_le_schema()


@pytest.fixture(scope="session", autouse=True)
def base_de_test():
    """Base vierge reconstruite une fois pour toute la session de tests."""
    _creer_base_si_absente()
    reconstruire_base()
    yield


@pytest.fixture
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def client(base_de_test):
    """Client HTTP sur l'application, avec le compte administrateur initial."""
    from fastapi.testclient import TestClient
    from app.api import app

    session = SessionLocal()
    try:
        auth.creer_admin_si_absent(session)
    finally:
        session.close()

    with TestClient(app) as client:
        reponse = client.post("/auth/login", data={
            "username": config.ADMIN_EMAIL, "password": config.ADMIN_PASSWORD,
        })
        assert reponse.status_code == 200, reponse.text
        client.headers["Authorization"] = f"Bearer {reponse.json()['access_token']}"
        yield client


@pytest.fixture
def jeton_de(client):
    """Fabrique un client authentifié pour un compte quelconque."""
    from fastapi.testclient import TestClient
    from app.api import app

    def fabriquer(email, mot_de_passe):
        autre = TestClient(app)
        reponse = autre.post("/auth/login", data={"username": email, "password": mot_de_passe})
        assert reponse.status_code == 200, reponse.text
        autre.headers["Authorization"] = f"Bearer {reponse.json()['access_token']}"
        return autre

    return fabriquer


def jeu_generique(session, categorie_id):
    """
    Le jeu de règles générique d'un type de document, créé au besoin (§19.6).

    Depuis les jeux de règles, une règle n'existe plus toute seule : elle
    appartient à un jeu, qui appartient à un type. Ce raccourci évite de
    reconstruire cette chaîne dans chaque test, tout en la respectant — un test
    qui contournerait la structure ne prouverait rien du fonctionnement réel.
    """
    from app.db import ProfilExtraction

    profil = (session.query(ProfilExtraction)
              .filter_by(categorie_id=categorie_id, generique=True).first())
    if not profil:
        profil = ProfilExtraction(categorie_id=categorie_id, nom="Jeu de test",
                                  generique=True, actif=True, priorite=1000)
        session.add(profil)
        session.flush()
    return profil
