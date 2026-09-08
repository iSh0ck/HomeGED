"""
Migrations SQL du schéma HomeGED.

`db/schema.sql` n'est joué par MariaDB qu'à la toute première création du
volume : il ne sert donc qu'aux bases vierges. Pour faire évoluer une base
déjà en service, on applique des fichiers `db/migrations/NNN_nom.sql`, une
seule fois chacun, dans l'ordre de leur numéro. Les versions déjà appliquées
sont tracées dans la table `sys_schema_migrations`.

Règle de tenue à jour : toute nouvelle table ou colonne doit être écrite à la
fois dans `db/schema.sql` (base vierge) et dans une migration (base existante).

L'API et le worker appellent tous les deux `appliquer_migrations()` au
démarrage ; un verrou nommé MariaDB garantit qu'un seul des deux les applique
réellement, l'autre attend puis constate qu'il n'y a plus rien à faire.
"""
import logging
import re
from pathlib import Path

from sqlalchemy import text

from .db import engine

log = logging.getLogger(__name__)

DOSSIER_MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"
FICHIER_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
NOM_VERROU = "homeged_migrations"
TIMEOUT_VERROU_SECONDES = 120


TABLE_VERSIONS = "sys_schema_migrations"


def _renommer_table_des_versions(connexion) -> None:
    """
    Fait passer la table de suivi à son nom préfixé.

    Ce renommage ne peut pas être une migration : le runner écrit dans cette
    table au moment même où il applique une migration ; la renommer en cours de
    route lui ferait perdre le fil. On le fait donc ici, avant toute lecture.
    """
    existantes = {
        ligne[0] for ligne in connexion.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name IN "
            f"('schema_migrations', '{TABLE_VERSIONS}')")
    }
    if "schema_migrations" in existantes and TABLE_VERSIONS not in existantes:
        connexion.exec_driver_sql(f"RENAME TABLE schema_migrations TO {TABLE_VERSIONS}")
        connexion.commit()


def _versions_appliquees(connexion) -> set[str]:
    _renommer_table_des_versions(connexion)
    connexion.execute(text(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_VERSIONS} (
            version VARCHAR(50) PRIMARY KEY,
            nom VARCHAR(255) NOT NULL,
            date_application DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
    ))
    return {ligne[0] for ligne in connexion.execute(text(f"SELECT version FROM {TABLE_VERSIONS}"))}


def _fichiers_migrations() -> list[tuple[str, Path]]:
    """Renvoie [(version, chemin), ...] trié par numéro de version croissant."""
    if not DOSSIER_MIGRATIONS.is_dir():
        return []
    fichiers = []
    for chemin in DOSSIER_MIGRATIONS.glob("*.sql"):
        correspondance = re.match(r"^(\d+)", chemin.name)
        if not correspondance:
            log.warning(f"Migration ignorée (nom sans numéro en préfixe) : {chemin.name}")
            continue
        fichiers.append((correspondance.group(1), chemin))
    return sorted(fichiers, key=lambda item: int(item[0]))


def _instructions(sql: str) -> list[str]:
    """
    Découpe un fichier SQL en instructions, séparées par `;`.

    Le découpage tient compte du contexte, ce qu'un simple `split(";")` ne fait
    pas : un point-virgule à l'intérieur d'un commentaire (`-- ... ; ...`) ou
    d'une chaîne littérale (`'a;b'`) n'est pas un séparateur. Ne pas le voir
    tronquait l'instruction en plein milieu, avec une erreur de syntaxe
    incompréhensible à l'exécution.

    Les migrations restent volontairement simples : pas de procédures stockées
    ni de délimiteurs personnalisés. Elles sont exécutées telles quelles, sans
    interprétation des `:mot` comme paramètres (cf. `appliquer_migrations`).
    """
    instructions = []
    courante = []
    dans_chaine = False
    i, n = 0, len(sql)

    while i < n:
        caractere = sql[i]

        if dans_chaine:
            courante.append(caractere)
            if caractere == "\\" and i + 1 < n:      # échappement : le caractère suivant est littéral
                courante.append(sql[i + 1])
                i += 2
                continue
            if caractere == "'":
                if i + 1 < n and sql[i + 1] == "'":  # '' = apostrophe échappée, la chaîne continue
                    courante.append("'")
                    i += 2
                    continue
                dans_chaine = False
            i += 1
            continue

        if caractere == "'":
            dans_chaine = True
            courante.append(caractere)
            i += 1
            continue

        # commentaire jusqu'à la fin de la ligne (MariaDB exige `--` puis une espace)
        if sql.startswith("--", i) and (i + 2 >= n or sql[i + 2] in " \t\r\n"):
            fin = sql.find("\n", i)
            i = n if fin == -1 else fin
            continue

        # commentaire de bloc
        if sql.startswith("/*", i):
            fin = sql.find("*/", i + 2)
            i = n if fin == -1 else fin + 2
            continue

        if caractere == ";":
            instructions.append("".join(courante))
            courante = []
            i += 1
            continue

        courante.append(caractere)
        i += 1

    instructions.append("".join(courante))
    return [instruction.strip() for instruction in instructions if instruction.strip()]


def base_vierge(connexion) -> bool:
    """
    Vrai si la base ne porte aucune table de l'application.

    On regarde `sys_documents` : c'est la table centrale, présente depuis la
    première version. Sa seule absence suffit à dire que rien n'a été installé.
    """
    presente = connexion.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = 'sys_documents'"
    )).scalar()
    return not presente


def installer_schema() -> bool:
    """
    Pose `db/schema.sql` sur une base vide (§18.31).

    **Pourquoi ne pas s'en remettre à Docker.** MariaDB joue les fichiers de
    `/docker-entrypoint-initdb.d/` au premier démarrage — à condition de pouvoir
    les lire. Sur une machine où le dépôt est en droits restreints, l'utilisateur
    `mysql` du conteneur ne le peut pas : l'entrée du journal dit « Permission
    denied », la base démarre vide, et l'API tourne en boucle sur des tables
    absentes. Rien dans l'interface ne l'explique, et le message d'erreur parle
    d'une table, pas d'un droit de lecture.

    L'application pose donc son schéma elle-même quand elle trouve une base
    vierge. Elle lit le fichier avec ses propres droits, ce qui supprime la
    dépendance à un détail de l'hôte — et rend une installation neuve réellement
    reproductible ailleurs.

    Rend `True` si le schéma vient d'être posé.
    """
    if not FICHIER_SCHEMA.is_file():
        return False

    with engine.connect() as connexion:
        if not base_vierge(connexion):
            return False

        log.info("Base vierge : installation du schéma depuis %s", FICHIER_SCHEMA.name)
        sql = FICHIER_SCHEMA.read_text(encoding="utf-8")
        curseur = connexion.connection.cursor()
        try:
            for instruction in _instructions(sql):
                # `CREATE DATABASE` / `USE` sont écartés : la base est déjà
                # choisie par la connexion, et son nom peut différer de celui du
                # fichier (installation d'essai, base de test).
                debut = instruction.lstrip().upper()
                if debut.startswith("CREATE DATABASE") or debut.startswith("USE "):
                    continue
                curseur.execute(instruction)
            connexion.connection.commit()
        finally:
            curseur.close()
    log.info("Schéma installé.")
    return True


def appliquer_migrations() -> None:
    """Applique les migrations non encore jouées. Idempotent, sûr à appeler à chaque démarrage."""
    installer_schema()
    migrations = _fichiers_migrations()
    if not migrations:
        return

    with engine.connect() as connexion:
        verrou = connexion.execute(
            text("SELECT GET_LOCK(:nom, :timeout)"),
            {"nom": NOM_VERROU, "timeout": TIMEOUT_VERROU_SECONDES},
        ).scalar()
        if verrou != 1:
            raise RuntimeError(
                f"Impossible d'obtenir le verrou de migration '{NOM_VERROU}' "
                f"après {TIMEOUT_VERROU_SECONDES}s"
            )
        try:
            deja_appliquees = _versions_appliquees(connexion)
            connexion.commit()

            for version, chemin in migrations:
                if version in deja_appliquees:
                    continue
                log.info(f"Application de la migration {chemin.name}...")
                try:
                    curseur = connexion.connection.cursor()
                    for instruction in _instructions(chemin.read_text(encoding="utf-8")):
                        # Exécution par le curseur brut, **sans argument** : c'est la
                        # seule façon de ne subir aucune interprétation. `text()`
                        # prendrait `:mot` pour un paramètre nommé — un groupe non
                        # capturant `(?:de\s+)?` suffit à le déclencher — et
                        # `exec_driver_sql` laisse le pilote traiter les `%` comme des
                        # marqueurs de format, ce qui casse un `LIKE 'a\_%'`.
                        # Une migration est du SQL littéral, sans aucun paramètre.
                        curseur.execute(instruction)
                    connexion.execute(
                        text(f"INSERT INTO {TABLE_VERSIONS} (version, nom) VALUES (:version, :nom)"),
                        {"version": version, "nom": chemin.name},
                    )
                    connexion.commit()
                except Exception:
                    connexion.rollback()
                    log.exception(f"Échec de la migration {chemin.name}, arrêt.")
                    raise
                log.info(f"Migration {chemin.name} appliquée.")
        finally:
            connexion.execute(text("SELECT RELEASE_LOCK(:nom)"), {"nom": NOM_VERROU})
