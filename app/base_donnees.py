"""
Exploration et administration de la base (§17).

Deux régimes, et c'est toute la sécurité du dispositif :

- **Tables du système** (préfixe `sys_`) : consultation seule. Écrire dedans depuis une grille
  générique court-circuiterait les droits par catégorie, le contrôle de
  conformité, l'audit et la gestion des fichiers ; retoucher `utilisateurs` ou
  `journal_audit` ruinerait la sécurité et la traçabilité. Certaines colonnes
  n'y sont même pas lisibles (empreintes de mots de passe) ou sont tronquées
  (texte océrisé, plusieurs centaines de kilo-octets).

- **Tables de données** (préfixe `usr_`), créées depuis l'administration et
  inscrites dans `tables_donnees` : lecture **et** écriture complètes. Ce sont
  les tables de référence du foyer — véhicules, personnes, contrats — appelées
  à alimenter des champs personnalisés.

Aucune requête n'est composée à partir de texte libre : les noms de table et de
colonne sont validés par une expression stricte **puis** vérifiés comme
existant réellement, et toutes les valeurs passent par des paramètres liés.
"""
import logging
import re
import time
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import filtres
from .db import TableDonnees, engine

log = logging.getLogger(__name__)

PREFIXE_DONNEES = "usr_"

# Un identifiant SQL acceptable ici : minuscules, chiffres et soulignés, commençant
# par une lettre. Volontairement restrictif — on n'a pas besoin de plus, et cela
# évite d'avoir à échapper quoi que ce soit.
IDENTIFIANT = re.compile(r"^[a-z][a-z0-9_]{0,40}$")

# Colonnes jamais renvoyées, quelle que soit la table.
COLONNES_MASQUEES = {("sys_utilisateurs", "mot_de_passe_hash")}

# Colonnes tronquées à l'affichage : leur contenu se compte en centaines de
# kilo-octets et n'a aucun intérêt dans une grille.
COLONNES_TRONQUEES = {("sys_documents", "texte_ocr")}
LONGUEUR_TRONCATURE = 200

# Types proposés à la création d'une colonne. La table de correspondance est ce
# qui garantit qu'aucun fragment de SQL fourni par le client n'atteint la base.
TYPES_COLONNES = {
    "texte": "VARCHAR(255)",
    "texte_long": "TEXT",
    "nombre": "INT",
    "decimal": "DECIMAL(14,2)",
    "date": "DATE",
    "datetime": "DATETIME",
    "booleen": "BOOLEAN",
}


def type_logique(type_sql: str) -> str:
    """
    Retrouve le type déclaré à partir de ce que la base rend (§18.26).

    L'export d'une configuration doit pouvoir recréer une table ailleurs : il lui
    faut « texte », pas « VARCHAR(255) ». La correspondance se lit dans
    `TYPES_COLONNES`, à l'envers — et retombe sur « texte », qui accepte tout ce
    qui se lit, plutôt que de refuser une table entière pour un type exotique.
    """
    normalise = str(type_sql or "").upper().strip()
    for logique, sql in TYPES_COLONNES.items():
        if sql.upper() == normalise:
            return logique
    for logique, sql in TYPES_COLONNES.items():
        if normalise.startswith(sql.split("(")[0].upper()):
            return logique
    return "texte"


class OperationRefusee(ValueError):
    """Opération que l'on refuse d'exécuter, avec un motif présentable à l'utilisateur."""


def _verifier_identifiant(valeur: str, quoi: str) -> str:
    valeur = (valeur or "").strip().lower()
    if not IDENTIFIANT.match(valeur):
        raise OperationRefusee(
            f"{quoi} « {valeur} » invalide : lettres minuscules, chiffres et soulignés "
            f"uniquement, en commençant par une lettre."
        )
    return valeur


# Ce que la base dit d'elle-même, gardé quelques secondes (§22.40).
#
# `SHOW FULL TABLES` et `SHOW CREATE TABLE` ne sont pas gratuits : une seule
# ouverture du registre en déclenchait **dix-huit**, parce que résoudre le
# libellé d'un émetteur passe par « cette table existe-t-elle ? » puis « quelles
# sont ses colonnes ? », et que la question se repose pour chaque source de
# chaque champ. Mesuré sur cinq mille documents : c'est l'essentiel du temps de
# réponse du registre.
#
# Le schéma d'un foyer ne bouge que quand un administrateur crée une table ou
# ajoute une colonne — et ces gestes-là **vident le cache** (`oublier_le_schema`).
# Le délai n'est donc qu'un filet de sécurité pour ce qui changerait sans passer
# par ici (une migration, une reprise à la main).
DUREE_SCHEMA = 30
_schema_cache: dict = {"tables": None, "tables_date": 0.0, "colonnes": {}, "index": {}}


def oublier_le_schema() -> None:
    """À appeler après tout changement de structure : le cache ne doit jamais
    survivre à ce qu'il décrit."""
    _schema_cache.update(tables=None, tables_date=0.0, colonnes={}, index={})


def _frais(horodatage: float) -> bool:
    return time.time() - horodatage < DUREE_SCHEMA


def tables_existantes() -> set[str]:
    if _schema_cache["tables"] is not None and _frais(_schema_cache["tables_date"]):
        return _schema_cache["tables"]
    trouvees = set(inspect(engine).get_table_names())
    _schema_cache.update(tables=trouvees, tables_date=time.time())
    return trouvees


def table_connue(nom: str) -> bool:
    """
    Cette table existe-t-elle ? **Un « non » est toujours revérifié.**

    C'est ce qui rend le cache sans danger : il ne peut mentir que dans un sens
    — annoncer absente une table créée à l'instant — et ce sens-là est celui
    qu'on relit. Une table créée hors d'ici (un modèle d'installation, une
    migration, une reprise à la main) est donc vue tout de suite, sans que
    chaque chemin de création ait à penser à vider le cache.
    """
    if nom in tables_existantes():
        return True
    oublier_le_schema()
    return nom in tables_existantes()


def _colonnes_du_schema(nom_table: str) -> list[dict]:
    """Les colonnes telles que la base les décrit, sans repasser par elle."""
    horodatage, valeur = _schema_cache["colonnes"].get(nom_table, (0.0, None))
    if valeur is not None and _frais(horodatage):
        return valeur
    lues = inspect(engine).get_columns(nom_table)
    _schema_cache["colonnes"][nom_table] = (time.time(), lues)
    return lues


def _index_du_schema(nom_table: str) -> list[dict]:
    horodatage, valeur = _schema_cache["index"].get(nom_table, (0.0, None))
    if valeur is not None and _frais(horodatage):
        return valeur
    lus = inspect(engine).get_indexes(nom_table)
    _schema_cache["index"][nom_table] = (time.time(), lus)
    return lus


# Une source de valeurs est une **table de données du foyer**, et rien d'autre
# (§18.13). Les comptes de connexion l'ont été un temps : c'était une exception
# codée en dur — `sys_utilisateurs` n'est pas une table de données, ses colonnes
# ne se règlent pas depuis l'administration, et un foyer qui reprendrait
# l'application héritait de ce couplage sans pouvoir y toucher. Les deux notions
# ne se recouvrent d'ailleurs pas : un enfant reçoit des factures sans avoir de
# compte, et un compte peut n'être qu'un accès partagé. Ce qu'un document désigne,
# ce sont des personnes ; elles vivent dans une table du foyer.


def est_table_donnees(session: Session, nom: str) -> bool:
    """Une table n'est modifiable que si elle est inscrite au registre ET existe."""
    if not nom.startswith(PREFIXE_DONNEES):
        return False
    inscrite = session.query(TableDonnees).filter_by(nom_table=nom).first() is not None
    return inscrite and table_connue(nom)


def _table_verifiee(session: Session, nom: str, ecriture: bool) -> str:
    nom = _verifier_identifiant(nom, "Nom de table")
    if not table_connue(nom):
        raise OperationRefusee(f"La table « {nom} » n'existe pas.")
    if ecriture and not est_table_donnees(session, nom):
        raise OperationRefusee(
            f"La table « {nom} » fait partie du fonctionnement de l'application : "
            f"elle est consultable, mais ne se modifie pas depuis cet écran. "
            f"Seules les tables de données créées ici sont modifiables."
        )
    return nom


def colonnes(session: Session, nom_table: str) -> list[dict]:
    """
    Colonnes d'une table, avec ce qui les décrit : type, obligation, unicité,
    intitulé lisible et table pointée (§18.32).

    Tout vient de deux sources, et chacune est celle qui fait foi pour ce qu'elle
    dit : le **schéma** pour ce que la base impose (type, NOT NULL, UNIQUE), la
    table de réglages pour ce que l'administrateur a déclaré (intitulé, liaison).
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=False)
    uniques = colonnes_uniques(session, nom_table)
    reglages_colonnes = _reglages_colonnes(session, nom_table)

    resultat = []
    for colonne in _colonnes_du_schema(nom_table):
        nom = colonne["name"]
        reglage = reglages_colonnes.get(nom)
        resultat.append({
            "nom": nom,
            "type": str(colonne["type"]),
            "type_logique": type_logique(str(colonne["type"])),
            "nullable": bool(colonne.get("nullable", True)),
            "unique": nom in uniques,
            "libelle": reglage.libelle if reglage else None,
            "source_table": reglage.source_table if reglage else None,
            "masquee": (nom_table, nom) in COLONNES_MASQUEES,
            "tronquee": (nom_table, nom) in COLONNES_TRONQUEES,
        })
    return resultat


def _reglages_colonnes(session: Session, nom_table: str) -> dict:
    from .db import ColonneDonnees
    return {r.colonne: r
            for r in session.query(ColonneDonnees).filter_by(nom_table=nom_table).all()}


def colonnes_uniques(session: Session, nom_table: str) -> set:
    """
    Colonnes portant une contrainte d'unicité, `id` excepté (clé primaire).

    Lues dans le schéma et non dans un réglage : dupliquer l'information
    garantirait qu'elles finissent par diverger, et c'est la base qui refuse
    réellement un doublon.
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=False)
    trouvees = set()
    for index in _index_du_schema(nom_table):
        if index.get("unique"):
            trouvees.update(c for c in index.get("column_names") or [] if c)
    return trouvees


def cles_uniques(session: Session, nom_table: str) -> list[dict]:
    """Les contraintes d'unicité, chacune avec les colonnes qu'elle porte."""
    nom_table = _table_verifiee(session, nom_table, ecriture=False)
    return [{"nom": index["name"], "colonnes": [c for c in index.get("column_names") or [] if c]}
            for index in _index_du_schema(nom_table) if index.get("unique")]


def _colonnes_lisibles(session: Session, nom_table: str) -> list[str]:
    return [c["nom"] for c in colonnes(session, nom_table) if not c["masquee"]]


def lister_tables(session: Session) -> list[dict]:
    """Toutes les tables, en distinguant celles que l'on peut modifier."""
    inscrites = {t.nom_table: t for t in session.query(TableDonnees).all()}
    resultat = []
    for nom in sorted(tables_existantes()):
        inscrite = inscrites.get(nom)
        try:
            nombre = session.execute(text(f"SELECT COUNT(*) FROM `{nom}`")).scalar()
        except Exception:
            nombre = None
        resultat.append({
            "nom": nom,
            "libelle": inscrite.libelle if inscrite else nom,
            "description": inscrite.description if inscrite else None,
            "modifiable": inscrite is not None,
            "nb_lignes": nombre,
            # Réglages d'affichage (§18.13) : ce qui décide de la façon dont une
            # ligne se donne à lire dans les listes de choix, et de ce qui la
            # désigne dans le texte d'un document. Réglable depuis
            # l'administration, et non plus figé par une migration.
            "colonne_libelle": inscrite.colonne_libelle if inscrite else None,
            "colonnes_identifiantes": inscrite.colonnes_identifiantes if inscrite else None,
        })
    return resultat


def regler_affichage(session: Session, nom_table: str, libelle: Optional[str] = None,
                     description: Optional[str] = None, colonne_libelle_: Optional[str] = None,
                     colonnes_identifiantes_: Optional[str] = None) -> dict:
    """
    Règle comment une table se présente : son intitulé, la colonne qui désigne
    une ligne, et les colonnes qui, ensemble, la reconnaissent.

    Les colonnes identifiantes servent deux fois, et c'est voulu : elles
    composent le libellé affiché dans les listes de choix — `prenom,nom` donne
    « Camille DURAND » — et ce sont elles que l'on cherche dans le texte d'un
    document pour rattacher une facture à quelqu'un. Une seule déclaration, deux
    usages qui ne peuvent donc pas diverger.
    """
    inscrite = session.query(TableDonnees).filter_by(nom_table=nom_table).first()
    if not inscrite:
        raise OperationRefusee(f"« {nom_table} » n'est pas une table de données modifiable.")

    disponibles = {c["nom"] for c in colonnes(session, nom_table)}
    if colonne_libelle_ is not None:
        choisie = (colonne_libelle_ or "").strip()
        if choisie and choisie not in disponibles:
            raise OperationRefusee(f"La colonne « {choisie} » n'existe pas dans cette table.")
        inscrite.colonne_libelle = choisie or None
    if colonnes_identifiantes_ is not None:
        demandees = [c.strip() for c in (colonnes_identifiantes_ or "").split(",") if c.strip()]
        inconnues = [c for c in demandees if c not in disponibles]
        if inconnues:
            raise OperationRefusee(
                f"Colonne(s) inconnue(s) dans cette table : {', '.join(inconnues)}.")
        inscrite.colonnes_identifiantes = ",".join(demandees) or None
    if libelle is not None and libelle.strip():
        inscrite.libelle = libelle.strip()
    if description is not None:
        inscrite.description = description.strip() or None

    session.commit()
    return {
        "nom": inscrite.nom_table,
        "libelle": inscrite.libelle,
        "description": inscrite.description,
        "colonne_libelle": inscrite.colonne_libelle,
        "colonnes_identifiantes": inscrite.colonnes_identifiantes,
    }


def lire_lignes(session: Session, nom_table: str, limite: int = 50, decalage: int = 0,
                recherche: Optional[str] = None) -> dict:
    """
    Page de lignes d'une table. La recherche porte sur toutes les colonnes
    textuelles, via des paramètres liés — jamais par concaténation.
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=False)
    lisibles = _colonnes_lisibles(session, nom_table)
    if not lisibles:
        return {"total": 0, "colonnes": [], "lignes": []}

    selection = ", ".join(f"`{c}`" for c in lisibles)
    where, parametres = "", {}
    if recherche and recherche.strip():
        # `LIKE` sur toutes les colonnes : MariaDB convertit implicitement les
        # types non textuels, ce qui permet de chercher aussi un nombre ou une date
        conditions = [f"CAST(`{c}` AS CHAR) LIKE :motif ESCAPE '\\\\'" for c in lisibles]
        where = " WHERE " + " OR ".join(conditions)
        parametres["motif"] = f"%{filtres.echapper_like(recherche.strip())}%"

    total = session.execute(
        text(f"SELECT COUNT(*) FROM `{nom_table}`{where}"), parametres
    ).scalar()

    parametres.update({"limite": max(1, min(limite, 500)), "decalage": max(0, decalage)})
    lignes = session.execute(
        text(f"SELECT {selection} FROM `{nom_table}`{where} LIMIT :limite OFFSET :decalage"),
        parametres,
    ).mappings().all()

    tronquees = {c for (t, c) in COLONNES_TRONQUEES if t == nom_table}
    resultat = []
    for ligne in lignes:
        valeurs = {}
        for cle, valeur in dict(ligne).items():
            if cle in tronquees and isinstance(valeur, str) and len(valeur) > LONGUEUR_TRONCATURE:
                valeur = valeur[:LONGUEUR_TRONCATURE] + "…"
            valeurs[cle] = valeur
        resultat.append(valeurs)

    # Colonnes qui pointent une autre table (§18.32) : la valeur enregistrée est
    # un identifiant, on rend aussi le libellé correspondant. L'interface affiche
    # « Camille DURAND » là où la base porte « 4 » — et garde l'identifiant pour
    # savoir quoi réécrire.
    return {"total": total, "colonnes": lisibles, "lignes": resultat,
            "liens": _libelles_liens(session, nom_table, resultat)}


def _libelles_liens(session: Session, nom_table: str, lignes: list[dict]) -> dict:
    """`{colonne: {identifiant: libellé}}` pour les colonnes qui pointent une table."""
    liens = {c["nom"]: c["source_table"] for c in colonnes(session, nom_table)
             if c.get("source_table")}
    if not liens or not lignes:
        return {}
    resultat = {}
    for colonne, source in liens.items():
        ids = {str(ligne.get(colonne)) for ligne in lignes
               if ligne.get(colonne) not in (None, "")}
        if not ids:
            continue
        try:
            resultat[colonne] = libelles_par_id(session, source, ids)
        except Exception:      # table disparue, droits, valeur non numérique
            log.debug("Libellés illisibles pour %s.%s", nom_table, colonne, exc_info=True)
    return resultat


# ------------------------------------------------------------
# Écriture — réservée aux tables de données
# ------------------------------------------------------------

def creer_table(session: Session, nom: str, libelle: str, colonnes_demandees: list[dict],
                description: Optional[str] = None) -> str:
    """
    Crée une table de données. Le nom reçoit le préfixe `usr_` et la table
    reçoit toujours une clé primaire `id` : sans identifiant stable, aucune ligne
    ne pourrait être modifiée ni supprimée ensuite de façon fiable.
    """
    nom = _verifier_identifiant(nom, "Nom de table")
    if not nom.startswith(PREFIXE_DONNEES):
        nom = PREFIXE_DONNEES + nom
    _verifier_identifiant(nom, "Nom de table")
    # Créer est rare : on relit le schéma pour de bon plutôt que de croire le
    # cache. Il ne peut se tromper que dans un sens dangereux ici — annoncer
    # présente une table disparue entre-temps — et refuser une création pour
    # cette raison-là serait incompréhensible.
    oublier_le_schema()
    if nom in tables_existantes():
        raise OperationRefusee(f"Une table « {nom} » existe déjà.")
    if not libelle or not libelle.strip():
        raise OperationRefusee("L'intitulé de la table est obligatoire.")
    if not colonnes_demandees:
        raise OperationRefusee("Il faut au moins une colonne.")

    definitions, noms_vus = ["`id` INT AUTO_INCREMENT PRIMARY KEY"], {"id"}
    for colonne in colonnes_demandees:
        nom_colonne = _verifier_identifiant(colonne.get("nom", ""), "Nom de colonne")
        if nom_colonne in noms_vus:
            raise OperationRefusee(f"La colonne « {nom_colonne} » est déclarée deux fois.")
        type_sql = TYPES_COLONNES.get(colonne.get("type", "texte"))
        if not type_sql:
            raise OperationRefusee(
                f"Type « {colonne.get('type')} » inconnu "
                f"(attendu : {', '.join(sorted(TYPES_COLONNES))})."
            )
        noms_vus.add(nom_colonne)
        definitions.append(
            f"`{nom_colonne}` {type_sql}" + (" NOT NULL" if colonne.get("obligatoire") else " NULL")
        )

    session.execute(text(f"CREATE TABLE `{nom}` ({', '.join(definitions)}) ENGINE=InnoDB"))
    oublier_le_schema()   # la structure a changé : le cache ne vaut plus rien
    premiere = next((c for c in colonnes_demandees), None)
    session.add(TableDonnees(
        nom_table=nom, libelle=libelle.strip(), description=(description or "").strip() or None,
        colonne_libelle=_verifier_identifiant(premiere["nom"], "Nom de colonne") if premiere else None,
    ))
    return nom


def ajouter_colonne(session: Session, nom_table: str, nom_colonne: str, type_colonne: str,
                    obligatoire: bool = False) -> None:
    """
    Ajoute une colonne. Ajout seulement : supprimer ou changer le type d'une
    colonne existante détruirait les valeurs déjà saisies, et une table de
    référence peut déjà être pointée par des documents.
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    nom_colonne = _verifier_identifiant(nom_colonne, "Nom de colonne")
    if nom_colonne in {c["nom"] for c in colonnes(session, nom_table)}:
        raise OperationRefusee(f"La colonne « {nom_colonne} » existe déjà.")
    type_sql = TYPES_COLONNES.get(type_colonne)
    if not type_sql:
        raise OperationRefusee(f"Type « {type_colonne} » inconnu.")
    # une colonne ajoutée à une table déjà remplie ne peut pas être NOT NULL
    # sans valeur par défaut : les lignes existantes n'en auraient aucune
    nombre = session.execute(text(f"SELECT COUNT(*) FROM `{nom_table}`")).scalar()
    contrainte = " NOT NULL" if obligatoire and not nombre else " NULL"
    session.execute(text(f"ALTER TABLE `{nom_table}` ADD COLUMN `{nom_colonne}` {type_sql}{contrainte}"))
    oublier_le_schema()   # la structure a changé : le cache ne vaut plus rien


PREFIXE_UNICITE = "uq_"


def definir_unicite(session: Session, nom_table: str, colonnes_demandees: list[str],
                    nom_contrainte: Optional[str] = None) -> dict:
    """
    Pose (ou retire) une contrainte d'unicité sur une ou plusieurs colonnes
    (§18.32).

    `id` reste la clé primaire, toujours : c'est lui qui permet de modifier une
    ligne dont on vient de changer l'immatriculation. Ce qu'on déclare ici est un
    **identifiant naturel** — ce qui, pour un humain, désigne la ligne sans
    ambiguïté : une immatriculation, un numéro de contrat.

    **Les doublons existants sont cherchés avant**, et le refus les nomme. Sans
    cela, la base renvoie une erreur d'index sans dire quelle ligne pose
    problème, et il faut aller la chercher à la main.
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    disponibles = {c["nom"] for c in colonnes(session, nom_table)}
    voulues = [_verifier_identifiant(str(c), "Nom de colonne")
               for c in (colonnes_demandees or []) if str(c).strip()]

    inconnues = [c for c in voulues if c not in disponibles]
    if inconnues:
        raise OperationRefusee(f"Colonne(s) inconnue(s) : {', '.join(inconnues)}.")
    if "id" in voulues:
        raise OperationRefusee("`id` est déjà la clé primaire : inutile de l'y ajouter.")

    existantes = {c["nom"]: c for c in cles_uniques(session, nom_table)}
    if nom_contrainte and nom_contrainte in existantes:
        session.execute(text(f"ALTER TABLE `{nom_table}` DROP INDEX `{nom_contrainte}`"))
        oublier_le_schema()   # la structure a changé : le cache ne vaut plus rien
        session.commit()
        if not voulues:
            return {"retiree": nom_contrainte}

    if not voulues:
        raise OperationRefusee("Indiquez au moins une colonne, ou la contrainte à retirer.")

    doublons = _doublons(session, nom_table, voulues)
    if doublons:
        exemples = ", ".join(f"« {d} »" for d in doublons[:3])
        raise OperationRefusee(
            f"{len(doublons)} valeur(s) en double empêchent cette unicité : {exemples}"
            f"{'…' if len(doublons) > 3 else ''}. Corrigez ces lignes d'abord.")

    nom_index = _verifier_identifiant(
        (nom_contrainte or f"{PREFIXE_UNICITE}{nom_table}_{'_'.join(voulues)}")[:60],
        "Nom de contrainte")
    liste = ", ".join(f"`{c}`" for c in voulues)
    session.execute(text(f"ALTER TABLE `{nom_table}` ADD CONSTRAINT `{nom_index}` UNIQUE ({liste})"))
    oublier_le_schema()   # la structure a changé : le cache ne vaut plus rien
    session.commit()
    return {"posee": nom_index, "colonnes": voulues}


def _doublons(session: Session, nom_table: str, colonnes_voulues: list[str]) -> list[str]:
    """Valeurs déjà présentes plus d'une fois — celles qui empêcheraient l'unicité."""
    liste = ", ".join(f"`{c}`" for c in colonnes_voulues)
    concat = "CONCAT_WS(' / ', " + ", ".join(f"COALESCE(`{c}`, '')" for c in colonnes_voulues) + ")"
    lignes = session.execute(text(
        f"SELECT {concat} AS valeur FROM `{nom_table}` "
        f"GROUP BY {liste} HAVING COUNT(*) > 1 LIMIT 20"
    )).mappings().all()
    return [str(l["valeur"]) for l in lignes]


def impact_colonne(session: Session, nom_table: str, nom_colonne: str) -> dict:
    """
    Ce qu'une suppression de colonne emporterait. Une confirmation qui ne dit pas
    ce qu'elle détruit ne protège de rien (§13).
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    definitions = {c["nom"]: c for c in colonnes(session, nom_table)}
    if nom_colonne not in definitions:
        raise OperationRefusee(f"La colonne « {nom_colonne} » n'existe pas.")

    remplies = session.execute(text(
        f"SELECT COUNT(*) FROM `{nom_table}` WHERE `{nom_colonne}` IS NOT NULL "
        f"AND CAST(`{nom_colonne}` AS CHAR) <> ''")).scalar() or 0

    inscrite = session.query(TableDonnees).filter_by(nom_table=nom_table).first()
    identifiantes = [c.strip() for c in ((inscrite.colonnes_identifiantes if inscrite else "") or "").split(",") if c.strip()]

    return {
        "colonne": nom_colonne,
        "valeurs_remplies": int(remplies),
        "est_colonne_libelle": bool(inscrite and inscrite.colonne_libelle == nom_colonne),
        "est_identifiante": nom_colonne in identifiantes,
        "est_unique": definitions[nom_colonne]["unique"],
        "pointe_une_table": definitions[nom_colonne]["source_table"],
    }


def supprimer_colonne(session: Session, nom_table: str, nom_colonne: str) -> dict:
    """
    Supprime une colonne, avec les garde-fous qui empêchent de casser la table.

    Trois refus, et ils portent tous sur la même idée : une colonne qui **sert**
    à quelque chose ne se retire pas par surprise. Celle qui donne son nom à une
    ligne, celles qui la reconnaissent dans un document, et `id` — sans lequel
    plus aucune ligne ne serait modifiable. On demande de défaire le réglage
    d'abord ; c'est un geste de plus, mais délibéré.
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    impact = impact_colonne(session, nom_table, nom_colonne)

    if nom_colonne == "id":
        raise OperationRefusee(
            "`id` ne se retire pas : sans lui, aucune ligne ne pourrait plus être "
            "modifiée ni supprimée de façon fiable.")
    if impact["est_colonne_libelle"]:
        raise OperationRefusee(
            f"« {nom_colonne} » désigne les lignes de cette table dans les listes de choix. "
            f"Choisissez d'abord une autre colonne d'affichage.")
    if impact["est_identifiante"]:
        raise OperationRefusee(
            f"« {nom_colonne} » sert à reconnaître une ligne dans le texte des documents. "
            f"Retirez-la d'abord des colonnes identifiantes.")
    if len([c for c in colonnes(session, nom_table) if c["nom"] != "id"]) <= 1:
        raise OperationRefusee(
            "C'est la dernière colonne de la table : une table qui n'a plus que des "
            "identifiants ne contient plus rien. Supprimez la table si c'est ce que vous voulez.")

    from .db import ColonneDonnees
    session.query(ColonneDonnees).filter_by(nom_table=nom_table, colonne=nom_colonne).delete()
    session.execute(text(f"ALTER TABLE `{nom_table}` DROP COLUMN `{nom_colonne}`"))
    oublier_le_schema()   # la structure a changé : le cache ne vaut plus rien
    session.commit()
    return impact


def modifier_colonne(session: Session, nom_table: str, nom_colonne: str,
                     nouveau_nom: Optional[str] = None, type_colonne: Optional[str] = None,
                     obligatoire: Optional[bool] = None) -> dict:
    """
    Renomme une colonne, change son type, ou son caractère obligatoire.

    **Le changement de type est tenté, pas simulé.** MariaDB refuse en bloc un
    `ALTER` qui ne peut pas convertir une valeur, et laisse alors la table
    exactement comme elle était : l'échec est sans dommage, et son message dit
    quelle valeur bloque. Deviner à l'avance ce que la base saura convertir
    reviendrait à réécrire ses règles, moins bien qu'elle.

    Un renommage entraîne les réglages qui citent la colonne — colonne
    d'affichage, colonnes identifiantes, liaisons — sans quoi la table
    deviendrait muette au premier renommage.
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    definitions = {c["nom"]: c for c in colonnes(session, nom_table)}
    if nom_colonne not in definitions:
        raise OperationRefusee(f"La colonne « {nom_colonne} » n'existe pas.")
    if nom_colonne == "id":
        raise OperationRefusee("`id` ne se modifie pas : c'est la clé de la table.")

    cible = _verifier_identifiant(nouveau_nom, "Nom de colonne") if nouveau_nom else nom_colonne
    if cible != nom_colonne and cible in definitions:
        raise OperationRefusee(f"Une colonne « {cible} » existe déjà.")

    actuelle = definitions[nom_colonne]
    type_sql = TYPES_COLONNES.get(type_colonne) if type_colonne else None
    if type_colonne and not type_sql:
        raise OperationRefusee(
            f"Type « {type_colonne} » inconnu (attendu : {', '.join(sorted(TYPES_COLONNES))}).")
    type_sql = type_sql or TYPES_COLONNES.get(actuelle["type_logique"], "VARCHAR(255)")

    exige = actuelle["nullable"] is False if obligatoire is None else bool(obligatoire)
    if exige:
        vides = session.execute(text(
            f"SELECT COUNT(*) FROM `{nom_table}` WHERE `{nom_colonne}` IS NULL")).scalar() or 0
        if vides:
            raise OperationRefusee(
                f"{vides} ligne(s) n'ont aucune valeur dans « {nom_colonne} » : elles "
                f"empêchent de la rendre obligatoire. Remplissez-les d'abord.")
    contrainte = " NOT NULL" if exige else " NULL"

    session.execute(text(
        f"ALTER TABLE `{nom_table}` CHANGE COLUMN `{nom_colonne}` `{cible}` {type_sql}{contrainte}"))
    oublier_le_schema()   # la structure a changé : le cache ne vaut plus rien

    if cible != nom_colonne:
        _repercuter_renommage(session, nom_table, nom_colonne, cible)
    session.commit()
    return {"colonne": cible, "type": type_sql, "obligatoire": exige}


def _repercuter_renommage(session: Session, nom_table: str, avant: str, apres: str) -> None:
    """Un renommage qui laisserait les réglages en arrière rendrait la table muette."""
    from .db import ColonneDonnees

    inscrite = session.query(TableDonnees).filter_by(nom_table=nom_table).first()
    if inscrite:
        if inscrite.colonne_libelle == avant:
            inscrite.colonne_libelle = apres
        if inscrite.colonnes_identifiantes:
            morceaux = [apres if c.strip() == avant else c.strip()
                        for c in inscrite.colonnes_identifiantes.split(",") if c.strip()]
            inscrite.colonnes_identifiantes = ",".join(morceaux)
    session.query(ColonneDonnees).filter_by(nom_table=nom_table, colonne=avant).update(
        {"colonne": apres})


def regler_colonne(session: Session, nom_table: str, nom_colonne: str,
                   libelle: Optional[str] = None, source_table: Optional[str] = None) -> dict:
    """
    Déclare l'intitulé d'une colonne et, le cas échéant, la table qu'elle pointe
    (§18.32).

    C'est ce qui fait qu'une colonne « propriétaire » cesse d'être un texte libre
    pour désigner une ligne de « Membres du foyer » : la saisie devient une liste
    de choix, la valeur enregistrée est l'identifiant de la ligne, et l'affichage
    suit le nom même quand celui-ci change.

    Rien n'est figé : n'importe quelle colonne peut pointer n'importe quelle table
    du foyer. Deux garde-fous seulement — une table ne se pointe pas elle-même
    (on tournerait en rond) et la table pointée doit exister.
    """
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    definitions = {c["nom"]: c for c in colonnes(session, nom_table)}
    if nom_colonne not in definitions or nom_colonne == "id":
        raise OperationRefusee(f"La colonne « {nom_colonne} » ne peut pas être réglée.")

    source = (source_table or "").strip() or None
    if source:
        if source == nom_table:
            raise OperationRefusee("Une table ne peut pas se pointer elle-même.")
        if not est_table_donnees(session, source):
            raise OperationRefusee(f"« {source} » n'est pas une table de données du foyer.")
        # Les valeurs déjà saisies ne sont pas des identifiants : on prévient
        # plutôt que de les effacer ou de les laisser mentir.
        parasites = session.execute(text(
            f"SELECT COUNT(*) FROM `{nom_table}` WHERE `{nom_colonne}` IS NOT NULL "
            f"AND CAST(`{nom_colonne}` AS CHAR) <> '' "
            f"AND `{nom_colonne}` NOT IN (SELECT CAST(`id` AS CHAR) FROM `{source}`)"
        )).scalar() or 0
    else:
        parasites = 0

    from .db import ColonneDonnees
    reglage = (session.query(ColonneDonnees)
               .filter_by(nom_table=nom_table, colonne=nom_colonne).first())
    if not reglage:
        reglage = ColonneDonnees(nom_table=nom_table, colonne=nom_colonne)
        session.add(reglage)
    if libelle is not None:
        reglage.libelle = (libelle or "").strip() or None
    reglage.source_table = source
    session.commit()
    return {"colonne": nom_colonne, "source_table": source,
            "valeurs_a_reprendre": int(parasites)}


def _valeurs_verifiees(session: Session, nom_table: str, valeurs: dict,
                      creation: bool = False) -> dict:
    """
    Ne retient que les colonnes qui existent, `id` excepté (jamais imposé).

    À la création, les colonnes déclarées obligatoires en base doivent être
    fournies et non vides. Sans ce contrôle, l'oubli remonterait sous forme
    d'erreur d'intégrité — un message de base de données là où l'utilisateur
    attend « le prénom est obligatoire ».
    """
    definitions = {c["nom"]: c for c in colonnes(session, nom_table)}
    retenues = {}
    for cle, valeur in (valeurs or {}).items():
        cle = _verifier_identifiant(str(cle), "Nom de colonne")
        if cle == "id":
            continue
        if cle not in definitions:
            raise OperationRefusee(f"La colonne « {cle} » n'existe pas dans « {nom_table} ».")
        retenues[cle] = None if valeur == "" else valeur
    if not retenues:
        raise OperationRefusee("Aucune valeur à enregistrer.")

    if creation:
        for nom, definition in definitions.items():
            if nom == "id" or definition["nullable"]:
                continue
            if retenues.get(nom) in (None, ""):
                raise OperationRefusee(f"La colonne « {nom} » est obligatoire.")

    # Une colonne qui pointe une table doit recevoir l'identifiant d'une ligne
    # qui existe (§18.32). Sans ce contrôle, une valeur libre s'y logerait et
    # l'affichage montrerait un numéro sans nom, sans qu'on sache pourquoi.
    for nom, valeur in retenues.items():
        source = definitions[nom].get("source_table")
        if not source or valeur in (None, ""):
            continue
        existe = session.execute(
            text(f"SELECT COUNT(*) FROM `{source}` WHERE `id` = :valeur"), {"valeur": valeur}
        ).scalar()
        if not existe:
            raise OperationRefusee(
                f"« {nom} » doit désigner une ligne de « {source} » : "
                f"« {valeur} » n'y correspond à rien.")
    return retenues


def inserer_ligne(session: Session, nom_table: str, valeurs: dict) -> int:
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    retenues = _valeurs_verifiees(session, nom_table, valeurs, creation=True)
    colonnes_sql = ", ".join(f"`{c}`" for c in retenues)
    parametres_sql = ", ".join(f":{c}" for c in retenues)
    session.execute(
        text(f"INSERT INTO `{nom_table}` ({colonnes_sql}) VALUES ({parametres_sql})"), retenues
    )
    return session.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def modifier_ligne(session: Session, nom_table: str, ligne_id: int, valeurs: dict) -> None:
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    retenues = _valeurs_verifiees(session, nom_table, valeurs)
    affectations = ", ".join(f"`{c}` = :{c}" for c in retenues)
    resultat = session.execute(
        text(f"UPDATE `{nom_table}` SET {affectations} WHERE `id` = :ligne_id"),
        {**retenues, "ligne_id": ligne_id},
    )
    if resultat.rowcount == 0:
        raise OperationRefusee(f"Aucune ligne nº{ligne_id} dans « {nom_table} ».")


def lire_ligne(session: Session, nom_table: str, ligne_id: int) -> Optional[dict]:
    nom_table = _table_verifiee(session, nom_table, ecriture=False)
    ligne = session.execute(
        text(f"SELECT * FROM `{nom_table}` WHERE `id` = :ligne_id"), {"ligne_id": ligne_id}
    ).mappings().first()
    return dict(ligne) if ligne else None


def supprimer_ligne(session: Session, nom_table: str, ligne_id: int) -> dict:
    """Supprime une ligne et renvoie son contenu, pour que le journal en garde trace."""
    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    avant = lire_ligne(session, nom_table, ligne_id)
    if avant is None:
        raise OperationRefusee(f"Aucune ligne nº{ligne_id} dans « {nom_table} ».")
    session.execute(text(f"DELETE FROM `{nom_table}` WHERE `id` = :ligne_id"), {"ligne_id": ligne_id})
    return avant


def supprimer_table(session: Session, nom_table: str) -> int:
    """
    Supprime une table de données et son inscription. Renvoie le nombre de lignes
    perdues.

    **Les réglages de colonnes partent avec elle**, et les liaisons qui la
    pointaient depuis d'autres tables sont défaites. Sans cela, deux ennuis :
    recréer une table du même nom ressusciterait des réglages qu'on croyait
    disparus — un test l'a montré, une colonne se retrouvant liée sans que
    personne ne l'ait demandé —, et une colonne resterait à pointer une table
    absente, affichant des identifiants sans nom.
    """
    from .db import ColonneDonnees

    nom_table = _table_verifiee(session, nom_table, ecriture=True)
    session.query(ColonneDonnees).filter_by(nom_table=nom_table).delete(
        synchronize_session=False)
    orphelines = (session.query(ColonneDonnees)
                  .filter_by(source_table=nom_table)
                  .update({"source_table": None}, synchronize_session=False))
    if orphelines:
        log.info("%s liaison(s) vers « %s » défaites : la table disparaît.",
                 orphelines, nom_table)
    nombre = session.execute(text(f"SELECT COUNT(*) FROM `{nom_table}`")).scalar()
    session.query(TableDonnees).filter_by(nom_table=nom_table).delete()
    session.execute(text(f"DROP TABLE `{nom_table}`"))
    oublier_le_schema()   # la structure a changé : le cache ne vaut plus rien
    return nombre or 0


# ------------------------------------------------------------
# Sources de valeurs pour les champs personnalisés (§17)
# ------------------------------------------------------------

def colonne_libelle(session: Session, nom_table: str) -> str:
    """
    Colonne servant à désigner une ligne dans les listes de choix. On retient
    celle déclarée à la création, sinon la première colonne autre que `id` :
    afficher un identifiant nu ne dirait rien à l'utilisateur.
    """
    inscrite = session.query(TableDonnees).filter_by(nom_table=nom_table).first()
    disponibles = [c["nom"] for c in colonnes(session, nom_table)]
    if inscrite and inscrite.colonne_libelle in disponibles:
        return inscrite.colonne_libelle
    return next((c for c in disponibles if c != "id"), "id")


def colonnes_identifiantes(session: Session, nom_table: str) -> list[str]:
    """
    Colonnes qui, ensemble, désignent une ligne dans le texte d'un document
    (§17.19). Déclaré table par table ; à défaut, la seule colonne d'affichage.

    Pour les membres du foyer, c'est « prenom,nom » : deux personnes d'une même
    famille portent le même nom, et « Dupont » seul ne désigne personne.
    """
    inscrite = session.query(TableDonnees).filter_by(nom_table=nom_table).first()
    disponibles = [c["nom"] for c in colonnes(session, nom_table)]
    declarees = [c.strip() for c in (inscrite.colonnes_identifiantes or "").split(",") if c.strip()]
    retenues = [c for c in declarees if c in disponibles]
    return retenues or [colonne_libelle(session, nom_table)]


def valeurs_identifiantes(session: Session, nom_table: str) -> dict:
    """`{id de ligne: [valeurs qui la désignent]}` — de quoi la reconnaître dans un texte."""
    identifiantes = colonnes_identifiantes(session, nom_table)
    selection = ", ".join(f"`{c}`" for c in ["id", *identifiantes])
    lignes = session.execute(text(f"SELECT {selection} FROM `{nom_table}`")).mappings().all()
    return {
        ligne["id"]: [str(ligne[c]).strip() for c in identifiantes if ligne.get(c)]
        for ligne in lignes
    }


def valeurs_des_colonnes(session: Session, nom_table: str, colonnes_voulues: list[str]) -> dict:
    """
    `{id de ligne: {colonne: valeur}}` pour les colonnes demandées (§18.47).

    Sœur de `valeurs_identifiantes`, à ceci près qu'elle ne décide pas de ce
    qu'elle lit : c'est le champ qui déclare les colonnes qu'il cherche dans le
    texte des documents. Les colonnes inconnues de la table sont ignorées —
    plusieurs sources peuvent servir un même champ, et elles n'ont pas les mêmes
    colonnes.
    """
    disponibles = {c["nom"] for c in colonnes(session, nom_table)}
    retenues = [c for c in colonnes_voulues if c in disponibles and c != "id"]
    if not retenues:
        return {}
    selection = ", ".join(f"`{c}`" for c in ["id", *retenues])
    lignes = session.execute(text(f"SELECT {selection} FROM `{nom_table}`")).mappings().all()
    return {
        ligne["id"]: {c: str(ligne[c]).strip() for c in retenues if ligne.get(c)}
        for ligne in lignes
    }


def options(session: Session, nom_table: str, recherche: Optional[str] = None,
            limite: int = 200, affichage: Optional[list[str]] = None) -> list[dict]:
    """
    Lignes d'une table de données proposées comme valeurs d'un champ personnalisé.

    Restreint aux tables de données : ce point d'entrée est ouvert à tous les
    utilisateurs connectés (ils remplissent les champs depuis le Centre
    d'analyse), il ne doit donc jamais donner accès aux tables du système.

    `affichage` est le choix du **champ** (§22.59) : les colonnes qui composent
    ce qu'on lit, et sur lesquelles porte la recherche. Absent, la table décide,
    comme avant.
    """
    nom_table = _verifier_identifiant(nom_table, "Nom de table")
    if not est_table_donnees(session, nom_table):
        raise OperationRefusee(f"« {nom_table} » n'est pas une table de données consultable ici.")

    identifiantes, separateur = _affichage_retenu(session, nom_table, affichage)
    libelle = colonne_libelle(session, nom_table)
    autres = [c["nom"] for c in colonnes(session, nom_table) if c["nom"] not in {"id", libelle}]
    # un complément (modèle, immatriculation...) distingue deux lignes de même libellé
    complement = autres[0] if autres and len(identifiantes) < 2 else None

    where, parametres = "", {}
    if recherche and recherche.strip():
        # la recherche porte sur toutes les colonnes qui désignent la ligne :
        # on doit pouvoir taper « Camille » aussi bien que « DURAND »
        cibles = identifiantes if len(identifiantes) > 1 else [libelle]
        where = " WHERE " + " OR ".join(
            f"CAST(`{c}` AS CHAR) LIKE :motif ESCAPE '\\\\'" for c in cibles)
        parametres["motif"] = f"%{filtres.echapper_like(recherche.strip())}%"
    parametres["limite"] = max(1, min(limite, 500))

    colonnes_lues = sorted({libelle, *identifiantes, *( [complement] if complement else [] )})
    selection = ", ".join([" `id`"] + [f"`{c}`" for c in colonnes_lues])
    tri = ", ".join(f"`{c}`" for c in (identifiantes if len(identifiantes) > 1 else [libelle]))
    lignes = session.execute(
        text(f"SELECT {selection} FROM `{nom_table}`{where} ORDER BY {tri} LIMIT :limite"),
        parametres,
    ).mappings().all()

    return [{
        "valeur": str(ligne["id"]),
        "libelle": _libelle_ligne(ligne, identifiantes, libelle, separateur),
        "complement": str(ligne[complement]) if complement and ligne[complement] is not None else None,
    } for ligne in lignes]


# Deux compositions, parce qu'il y a deux intentions (§22.60).
#
# Les colonnes **identifiantes d'une table** composent un nom : `prenom,nom`
# donne « Camille DURAND », et un tiret y serait une faute de français.
#
# Les colonnes **choisies par un champ** (§22.59) composent une ligne
# d'information : « Clio III - AA-123-BB ». Ce ne sont pas les morceaux d'un
# nom mais deux renseignements côte à côte, et l'œil a besoin qu'on les sépare.
SEPARATEUR_NOM = " "
SEPARATEUR_CHOIX = " - "


def _libelle_ligne(ligne, identifiantes: list[str], colonne_affichage: str,
                   separateur: str = SEPARATEUR_NOM) -> str:
    """
    Comment une ligne se donne à lire dans une liste de choix.

    Quand la table déclare **plusieurs colonnes identifiantes**, elles composent
    le libellé, dans l'ordre déclaré : pour les membres du foyer, `prenom,nom`
    donne « Camille DURAND ». C'est le même réglage qui sert déjà à reconnaître
    une personne dans le texte d'un document — il n'y a donc rien de neuf à
    régler, et rien de codé en dur : un autre foyer qui range ses tables
    autrement obtient l'affichage qui correspond à ce qu'il a déclaré.

    Sinon, la colonne d'affichage seule, comme avant.

    Un champ peut passer ses propres colonnes en `identifiantes` (§22.59) : ce
    qu'on vient chercher dans un sélecteur n'est pas toujours ce qui désigne la
    ligne. Il passe alors son propre `separateur`.
    """
    if len(identifiantes) > 1:
        morceaux = [str(ligne[c]).strip() for c in identifiantes
                    if c in ligne.keys() and ligne[c] is not None and str(ligne[c]).strip()]
        if morceaux:
            return separateur.join(morceaux)
    valeur = ligne[colonne_affichage] if colonne_affichage in ligne.keys() else None
    return str(valeur) if valeur is not None else f"Ligne nº{ligne['id']}"


SEPARATEUR_SOURCE = ":"


def decouper_valeur(valeur: str, source_par_defaut: Optional[str] = None) -> tuple:
    """
    Sépare une valeur de champ en `(source, identifiant)`.

    Un champ peut puiser dans plusieurs sources (§17.28), et deux sources ont
    chacune leur ligne nº3 : la valeur porte donc sa source — `usr_membres:3`.
    Une valeur sans préfixe est antérieure à ce changement ; elle appartient à
    la source déclarée en premier, d'où `source_par_defaut`.
    """
    texte = str(valeur or "").strip()
    if SEPARATEUR_SOURCE in texte:
        source, identifiant = texte.split(SEPARATEUR_SOURCE, 1)
        return source.strip(), identifiant.strip()
    return source_par_defaut, texte


def _affichage_retenu(session: Session, nom_table: str,
                      affichage: Optional[list[str]]) -> tuple[list[str], str]:
    """
    Les colonnes qui composent ce qu'on lit d'une ligne, et **ce qui les sépare**
    (§22.59, §22.60).

    Celles que le champ a choisies si elles existent encore — une colonne
    supprimée de la table ne doit pas vider l'affichage —, sinon celles que la
    table déclare. On ne se retrouve donc jamais avec un « Ligne nº7 ».

    Le séparateur suit la provenance : un tiret pour un choix de champ, une
    espace pour les colonnes identifiantes, qui composent un nom.
    """
    if not affichage:
        return colonnes_identifiantes(session, nom_table), SEPARATEUR_NOM
    disponibles = {c["nom"] for c in colonnes(session, nom_table)}
    retenues = [c for c in affichage if c in disponibles]
    if retenues:
        return retenues, SEPARATEUR_CHOIX
    return colonnes_identifiantes(session, nom_table), SEPARATEUR_NOM


def libelles_par_id(session: Session, nom_table: str, ids: set[str],
                    affichage: Optional[list[str]] = None) -> dict:
    """Libellés d'un lot de lignes référencées, pour afficher autre chose qu'un numéro."""
    identifiants = [int(i) for i in ids if str(i).isdigit()]
    if not identifiants:
        return {}
    if not est_table_donnees(session, nom_table):
        return {}
    # Même composition que dans les listes de choix : ce qu'on a choisi doit se
    # relire à l'identique dans le tableau et sur la fiche, sinon on doute
    # d'avoir choisi la bonne personne.
    libelle = colonne_libelle(session, nom_table)
    identifiantes, separateur = _affichage_retenu(session, nom_table, affichage)
    colonnes_lues = sorted({libelle, *identifiantes})
    selection = ", ".join(["`id`"] + [f"`{c}`" for c in colonnes_lues])
    lignes = session.execute(
        text(f"SELECT {selection} FROM `{nom_table}` WHERE `id` IN :ids"),
        {"ids": tuple(identifiants)},
    ).mappings().all()
    return {str(l["id"]): _libelle_ligne(l, identifiantes, libelle, separateur)
            for l in lignes}
