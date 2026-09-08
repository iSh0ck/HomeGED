"""
Export et import de la configuration (§18.26).

Ce que HomeGED sait d'un foyer se range en deux tas : **ses documents**, et **la
façon dont il les range**. Le premier a son export (§17.30). Le second — les
catégories, les regex de classement, les champs attendus, les colonnes, les vues,
les tableaux de bord, les tables de données du foyer — n'existait que dans la
base, sans porte pour le faire sortir ni entrer.

C'est pourtant lui qui rend le projet transposable : un foyer doit pouvoir partir
d'un modèle tout fait, l'élaguer, et un autre reprendre le sien. D'où ce module.

**Ce qui n'est pas exporté, et pourquoi** : les comptes, les rôles et les droits
(la configuration voyage, les identités non — importer les comptes d'un autre
foyer donnerait des accès à des gens qui n'y habitent pas), les documents et
leurs métadonnées, le journal d'audit, les sessions. Les **lignes** des tables de
données (membres du foyer, véhicules) ne partent qu'à la demande : ce sont des
données personnelles, pas de la structure — mais un foyer qui déménage son
installation veut les emmener.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import base_donnees, depots, reglages
from .db import (
    Categorie,
    ColonneCategorie,
    RegleChampCategorie,
    ProfilExtraction,
    RegleExtraction,
    Role,
    TableDonnees,
    TableauDeBord,
    VueEnregistree,
)

log = logging.getLogger(__name__)

FORMAT = 1        # version du format : un fichier plus récent est refusé, pas deviné

# Réglages qui décrivent la manière de travailler du foyer, et voyagent donc avec
# la configuration. Le nom du foyer et son fuseau restent dehors : ils désignent
# *ce* foyer-ci, pas sa façon de ranger. Le nombre de traitements simultanés
# (§22.41) reste dehors pour une raison voisine : il décrit **la machine** — ses
# cœurs, sa charge — et reprendre celui d'un serveur plus gros mettrait le foyer
# à genoux sans qu'il comprenne pourquoi. Les réglages de sauvegarde (§22.49)
# restent dehors pour la même raison, en plus grave : ils désignent un **chemin
# de disque**, et reprendre celui d'une autre installation ferait écrire les
# copies de secours à un endroit qui n'existe pas ici.
REGLAGES_EXPORTES = [
    # traitement
    "duree_verrou_edition_minutes", "langue_ocr", "resolution_ocr", "compression_niveau",
    # ce qu'on garde, et combien de temps
    "retention_jobs_jours", "retention_journal_jours", "retention_corbeille_jours",
    "retention_documents_supprimes_jours", "retention_consultations_jours",
    "expiration_export_minutes", "integrite_lot_par_passage",
    # jusqu'où la machine s'obstine avant de rendre la main (§21.15)
    "travaux_tentatives_max",
    # les arbitrages de sécurité du foyer : combien de temps une session vit, ce
    # qu'on tolère d'échecs, ce qu'on exige d'un mot de passe. Ce sont des
    # décisions de foyer au même titre que le classement, et les laisser dehors
    # obligeait à les reprendre une à une après chaque reprise.
    "duree_session_heures", "tentatives_avant_verrouillage", "duree_verrouillage_minutes",
    "longueur_min_mot_de_passe", "otp_obligatoire",
    # présentation
    "ecran_accueil", "lignes_par_page", "densite", "theme", "langue", "couleur_accent",
    "tri_defaut_champ", "tri_defaut_sens",
]

# Restent dehors, et c'est délibéré : `nom_foyer` et `fuseau_horaire` désignent
# **ce** foyer-ci, pas sa façon de ranger. Les importer renommerait l'installation
# d'accueil du nom de celle qui a exporté — la seule chose qu'une reprise de
# configuration ne doit jamais faire.


class ImportRefuse(Exception):
    pass


# ------------------------------------------------------------------
# Export
# ------------------------------------------------------------------

def exporter(session: Session, avec_donnees: bool = False) -> dict:
    """
    Rend la configuration sous forme de dictionnaire, prêt à être écrit en JSON.

    Les identifiants numériques ne sont **pas** exportés : ils n'ont de sens que
    dans la base qui les a émis. Les liens sont dits par les noms — une
    sous-catégorie nomme son parent, une vue nomme sa catégorie. C'est ce qui
    permet d'importer dans une base qui a déjà ses propres numéros.
    """
    categories = session.query(Categorie).order_by(Categorie.id).all()
    noms = {c.id: c.nom for c in categories}
    # Les vues sont désignées par leur nom dans les droits des rôles : un
    # identifiant ne voudrait rien dire dans la base d'accueil.
    nom_de_vue = {v.id: v.nom for v in session.query(VueEnregistree)}

    tables = session.query(TableDonnees).order_by(TableDonnees.nom_table).all()

    export = {
        "format": FORMAT,
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "categories": [{
            "nom": c.nom,
            # dossier ou type de document (§19.1) : sans elle, un classement
            # repris ailleurs perdrait la distinction qui le structure
            "nature": c.nature or "type",
            "parent": noms.get(c.parent_id),
            # table du foyer d'une fiche de liaison (§19.17)
            # tri d'ouverture du registre pour ce type (§18.49)
            "tri_champ": c.tri_champ,
            "tri_sens": c.tri_sens,
            "dossier_depot": c.dossier_depot,
            "ordre": c.ordre,
        } for c in categories],
        # Les jeux de règles portent la structure (§19.6) ; les règles y sont
        # imbriquées plutôt que listées à plat, pour qu'aucune ne puisse arriver
        # ailleurs sans son jeu — une règle sans jeu ne s'applique à rien.
        "jeux_extraction": [{
            "categorie": noms.get(p.categorie_id),
            "nom": p.nom,
            "reconnaissance": p.reconnaissance,
            "generique": bool(p.generique),
            "actif": bool(p.actif),
            "priorite": p.priorite,
            "regles": [{
                "nom": r.nom, "champ_cible": r.champ_cible, "pattern": r.pattern,
                "fonction": r.fonction, "parametre": r.parametre,
                "type_champ": r.type_champ,
                "actif": bool(r.actif), "priorite": r.priorite,
            } for r in sorted(p.regles, key=lambda r: (r.priorite or 100, r.id))],
        } for p in session.query(ProfilExtraction).order_by(ProfilExtraction.id)],
        "champs_attendus": [{
            "categorie": noms.get(r.categorie_id),
            "champ": r.champ, "libelle": r.libelle, "obligatoire": bool(r.obligatoire),
            "identifiant": bool(r.identifiant),
            "ordre": r.ordre, "source_table": r.source_table, "sources": r.sources,
            # ce que le champ déclare chercher dans les documents (§18.47)
            "deduction": r.deduction or "aucune",
            "colonnes_deduction": r.colonnes_deduction,
            "deduction_approchee": bool(r.deduction_approchee),
        } for r in session.query(RegleChampCategorie).order_by(RegleChampCategorie.id)],
        "colonnes": [{
            "categorie": noms.get(c.categorie_id),
            "champ": c.champ, "libelle": c.libelle, "ordre": c.ordre,
            "largeur": c.largeur, "visible": bool(c.visible),
        } for c in session.query(ColonneCategorie).order_by(ColonneCategorie.ordre)],
        "vues": [{
            "nom": v.nom, "categorie": noms.get(v.categorie_id),
            "criteres": _charger(v.criteres), "partagee": bool(v.partagee), "ordre": v.ordre,
        } for v in session.query(VueEnregistree).order_by(VueEnregistree.ordre)],
        # Rôles et droits (§19.12) : qui voit quoi fait partie de la façon de
        # ranger d'un foyer, au même titre que l'arborescence. Les **comptes**,
        # eux, restent dehors — ce sont des personnes, pas une configuration.
        # Tout est désigné par son nom : un identifiant n'aurait aucun sens d'une
        # installation à l'autre.
        "roles": [{
            "nom": role.nom,
            "description": role.description,
            "generaux": sorted(d.droit for d in role.droits_generaux),
            "vues": sorted(nom_de_vue.get(d.vue_id) for d in role.droits_vue
                           if nom_de_vue.get(d.vue_id)),
            "categories": [{
                "categorie": noms.get(d.categorie_id),
                "peut_voir": bool(d.peut_voir), "peut_modifier": bool(d.peut_modifier),
                "peut_deposer": bool(d.peut_deposer),
                "peut_telecharger": bool(d.peut_telecharger),
                "peut_supprimer": bool(d.peut_supprimer),
                "peut_gerer_versions": bool(d.peut_gerer_versions),
            } for d in role.droits_categorie if noms.get(d.categorie_id)],
        } for role in session.query(Role).order_by(Role.nom)],
        "tableaux_de_bord": [{
            "nom": t.nom, "description": t.description, "ordre": t.ordre,
            "partage": bool(t.partage), "widgets": _charger(t.widgets),
        } for t in session.query(TableauDeBord).order_by(TableauDeBord.ordre)],
        "tables_donnees": [{
            "nom_table": t.nom_table, "libelle": t.libelle, "description": t.description,
            "colonne_libelle": t.colonne_libelle,
            "colonnes_identifiantes": t.colonnes_identifiantes,
            # Chaque colonne emporte ce qui la décrit (§18.32) : son type, son
            # intitulé, la table qu'elle pointe. Sans cela, une configuration
            # reprise ailleurs perdrait ses liaisons — « propriétaire »
            # redeviendrait un texte libre.
            "colonnes": [{"nom": c["nom"], "type": c["type_logique"],
                          "obligatoire": not c["nullable"],
                          "libelle": c.get("libelle"),
                          "source_table": c.get("source_table")}
                         for c in base_donnees.colonnes(session, t.nom_table)
                         if c["nom"] != "id"],
            "cles_uniques": [k["colonnes"] for k in base_donnees.cles_uniques(session, t.nom_table)],
            "lignes": _lignes(session, t.nom_table) if avec_donnees else None,
        } for t in tables],
        "reglages": {cle: reglages.lire(session, cle) for cle in REGLAGES_EXPORTES},
    }
    return export


def _charger(texte: Optional[str]):
    try:
        return json.loads(texte) if texte else []
    except (TypeError, ValueError):
        return []


def _lignes(session: Session, nom_table: str) -> list:
    lignes = session.execute(text(f"SELECT * FROM `{nom_table}`")).mappings().all()
    return [{cle: valeur for cle, valeur in ligne.items() if cle != "id"} for ligne in lignes]


# ------------------------------------------------------------------
# Import
# ------------------------------------------------------------------

def importer(session: Session, donnees: dict, remplacer: bool = False) -> dict:
    """
    Applique une configuration.

    Deux façons de l'entendre, et le choix est celui de l'administrateur :

    * **compléter** (défaut) — ce qui existe déjà sous le même nom est laissé
      intact, seul ce qui manque est ajouté. C'est le mode sûr : on essaie un
      modèle sans rien perdre.
    * **remplacer** — la configuration existante est effacée d'abord. Refusé s'il
      existe des documents : leur classement disparaîtrait sous eux.

    **Sur l'atomicité, la vérité plutôt que la promesse** : créer une table est
    une opération que MariaDB ne sait pas défaire dans une transaction. Un import
    ne peut donc pas être tout ou rien, et prétendre le contraire serait mentir.
    Ce qui est garanti à la place : le format est vérifié avant la première
    écriture, chaque partie est appliquée séparément, et **le compte rendu dit
    exactement ce qui est passé** — y compris ce qui a échoué et pourquoi. C'est
    la leçon d'un essai raté en cours d'écriture, qui avait laissé la moitié d'un
    modèle en place sans que rien ne le dise.
    """
    if not isinstance(donnees, dict):
        raise ImportRefuse("Le fichier ne contient pas une configuration.")
    format_lu = donnees.get("format")
    if format_lu is None:
        raise ImportRefuse("Ce fichier ne dit pas dans quel format il est écrit.")
    if int(format_lu) > FORMAT:
        raise ImportRefuse(
            f"Ce fichier vient d'une version plus récente (format {format_lu}). "
            f"Mettez HomeGED à jour avant de l'importer.")

    if remplacer:
        from .db import Document
        if session.query(Document).count() > 0:
            raise ImportRefuse(
                "Des documents sont classés : leur classement disparaîtrait sous eux. "
                "Importez en mode « compléter », ou repartez d'une installation neuve.")
        session.query(VueEnregistree).delete(synchronize_session=False)
        session.query(ColonneCategorie).delete(synchronize_session=False)
        session.query(RegleChampCategorie).delete(synchronize_session=False)
        session.query(RegleExtraction).delete(synchronize_session=False)
        session.query(Categorie).delete(synchronize_session=False)
        session.commit()

    bilan = {cle: 0 for cle in ("categories", "jeux_extraction", "champs_attendus", "roles",
                                "colonnes", "vues", "tableaux_de_bord", "tables_donnees",
                                "lignes", "reglages")}
    bilan["erreurs"] = []

    def appliquer(nom, operation):
        """Applique une partie, et note son échec au lieu de le laisser tout emporter."""
        try:
            resultat = operation()
            session.commit()
            return resultat
        except Exception as erreur:      # noqa: BLE001 — on rapporte, on ne masque pas
            session.rollback()
            log.exception("Import : la partie « %s » a échoué", nom)
            bilan["erreurs"].append(f"{nom} : {erreur}")
            return 0

    bilan["categories"] = appliquer(
        "catégories", lambda: _importer_categories(session, donnees.get("categories") or []))
    identifiants = {c.nom: c.id for c in session.query(Categorie).all()}

    bilan["jeux_extraction"] = appliquer(
        "jeux de règles d'extraction",
        lambda: _importer_jeux(session, donnees.get("jeux_extraction") or [], identifiants))
    bilan["champs_attendus"] = appliquer(
        "champs attendus",
        lambda: _importer_champs(session, donnees.get("champs_attendus") or [], identifiants))
    bilan["colonnes"] = appliquer(
        "colonnes", lambda: _importer_colonnes(session, donnees.get("colonnes") or [], identifiants))
    bilan["vues"] = appliquer(
        "vues", lambda: _importer_vues(session, donnees.get("vues") or [], identifiants))
    bilan["tableaux_de_bord"] = appliquer(
        "tableaux de bord",
        lambda: _importer_tableaux(session, donnees.get("tableaux_de_bord") or []))

    # Les rôles après les vues : leurs droits peuvent en nommer.
    bilan["roles"] = appliquer(
        "rôles et droits",
        lambda: _importer_roles(session, donnees.get("roles") or [], identifiants))

    tables = appliquer("tables de données",
                       lambda: _importer_tables(session, donnees.get("tables_donnees") or []))
    bilan["tables_donnees"], bilan["lignes"] = tables if isinstance(tables, tuple) else (0, 0)

    valeurs = {cle: valeur for cle, valeur in (donnees.get("reglages") or {}).items()
               if cle in REGLAGES_EXPORTES}
    if valeurs:
        bilan["reglages"] = appliquer(
            "réglages", lambda: (reglages.enregistrer(session, valeurs), len(valeurs))[1])

    return bilan


def _importer_categories(session: Session, categories: list) -> int:
    """
    Les catégories d'abord, en deux passes : les racines, puis les enfants. Une
    sous-catégorie nomme son parent, et ce parent peut n'exister qu'après elle
    dans le fichier — l'ordre du fichier ne doit pas décider du résultat.
    """
    existantes = {c.nom: c for c in session.query(Categorie).all()}
    ajoutees = 0
    restantes = list(categories)

    # Un fichier écrit avant le §19.1 ne dit pas la nature de ses catégories. On
    # la déduit comme la migration l'a fait sur l'existant : une catégorie que
    # d'autres nomment comme parent est un dossier, une feuille est un type.
    # C'est la seule lecture possible sans deviner l'intention, et elle évite
    # d'importer une arborescence que le reste du logiciel ne saurait pas lire.
    parents = {e.get("parent") for e in categories if e.get("parent")}

    for _ in range(10):      # profondeur d'arborescence largement suffisante
        differees = []
        for entree in restantes:
            nom = (entree.get("nom") or "").strip()
            if not nom or nom in existantes:
                continue
            parent = entree.get("parent")
            if parent and parent not in existantes:
                differees.append(entree)
                continue
            categorie = Categorie(
                nom=nom,
                parent_id=existantes[parent].id if parent else None,
                nature=entree.get("nature") or ("dossier" if nom in parents else "type"),
                tri_champ=entree.get("tri_champ"),
                tri_sens=entree.get("tri_sens"),
                # Le dossier de dépôt (§19.2) : celui du fichier s'il est libre,
                # sinon l'application en propose un. Il n'est pas repris tel quel
                # sans vérification — deux types au même endroit rendraient le
                # dépôt ambigu, ce que l'unicité en base refuse de toute façon.
                ordre=entree.get("ordre") or 100,
            )
            session.add(categorie)
            session.flush()
            depots.attribuer(session, categorie, entree.get("dossier_depot"))
            existantes[nom] = categorie
            ajoutees += 1
        if not differees or len(differees) == len(restantes):
            break
        restantes = differees
    return ajoutees


def _importer_jeux(session: Session, jeux: list, categories: dict) -> int:
    """
    Importe les jeux de règles et leurs règles (§19.6).

    Un jeu appartient à un type de document : sans lui, ses règles ne
    s'appliqueraient à rien. Un jeu dont le type est absent du fichier est donc
    ignoré — l'importer produirait des règles orphelines, invisibles et sans effet.

    Depuis le §21.12, un jeu ne pose plus d'émetteur : c'est la déduction du champ
    attendu qui s'en charge, et elle voyage avec les champs.
    """
    connus = {(p.categorie_id, p.nom) for p in session.query(ProfilExtraction)}
    ajoutes = 0

    for entree in jeux:
        categorie_id = categories.get(entree.get("categorie"))
        nom = (entree.get("nom") or "").strip()
        if not categorie_id or not nom or (categorie_id, nom) in connus:
            continue
        profil = ProfilExtraction(
            categorie_id=categorie_id, nom=nom,
            reconnaissance=entree.get("reconnaissance") or None,
            generique=bool(entree.get("generique")),
            actif=bool(entree.get("actif", True)),
            priorite=entree.get("priorite") or 100,
        )
        session.add(profil)
        session.flush()
        for regle in entree.get("regles") or []:
            if not regle.get("nom") or not regle.get("champ_cible"):
                continue
            session.add(RegleExtraction(
                profil_id=profil.id, nom=regle["nom"], champ_cible=regle["champ_cible"],
                pattern=regle.get("pattern") or None, fonction=regle.get("fonction") or None,
                parametre=regle.get("parametre") or None,
                type_champ=regle.get("type_champ") or "texte",
                actif=bool(regle.get("actif", True)),
                priorite=regle.get("priorite") or 100,
            ))
        connus.add((categorie_id, nom))
        ajoutes += 1
    return ajoutes


def _importer_champs(session: Session, champs: list, categories: dict) -> int:
    connus = {(r.categorie_id, r.champ) for r in session.query(RegleChampCategorie).all()}
    ajoutes = 0
    for entree in champs:
        categorie_id = categories.get(entree.get("categorie"))
        if not categorie_id or (categorie_id, entree.get("champ")) in connus:
            continue
        session.add(RegleChampCategorie(
            categorie_id=categorie_id, champ=entree["champ"], libelle=entree.get("libelle"),
            obligatoire=bool(entree.get("obligatoire", True)),
            identifiant=bool(entree.get("identifiant")), ordre=entree.get("ordre") or 100,
            source_table=entree.get("source_table"), sources=entree.get("sources"),
            deduction=entree.get("deduction") or "aucune",
            colonnes_deduction=entree.get("colonnes_deduction"),
            deduction_approchee=bool(entree.get("deduction_approchee")),
        ))
        connus.add((categorie_id, entree["champ"]))
        ajoutes += 1
    return ajoutes


def _importer_colonnes(session: Session, colonnes: list, categories: dict) -> int:
    connues = {(c.categorie_id, c.champ) for c in session.query(ColonneCategorie).all()}
    ajoutees = 0
    for entree in colonnes:
        categorie_id = categories.get(entree.get("categorie"))
        if not categorie_id or (categorie_id, entree.get("champ")) in connues:
            continue
        session.add(ColonneCategorie(
            categorie_id=categorie_id, champ=entree["champ"], libelle=entree.get("libelle"),
            ordre=entree.get("ordre") or 100, largeur=entree.get("largeur"),
            visible=bool(entree.get("visible", True)),
        ))
        connues.add((categorie_id, entree["champ"]))
        ajoutees += 1
    return ajoutees


def _importer_roles(session: Session, roles: list, categories: dict) -> int:
    """
    Importe les rôles et leurs droits (§19.13).

    L'import **ajoute, il ne retire jamais**. Un rôle absent est créé avec ses
    droits ; un rôle déjà là reçoit ceux qui lui manquent, et garde les siens tels
    quels — une reprise de configuration ne doit pas rouvrir ce que quelqu'un a
    fermé, ni refermer ce qu'il a ouvert.

    Compléter un rôle existant n'est pas une facilité : après une remise à zéro du
    classement, les rôles survivent mais leurs droits par catégorie sont partis
    avec les catégories. Les ignorer laisserait des rôles vides que rien ne
    remplirait, et l'import n'aurait rien restauré.

    Les droits nommant une catégorie ou une vue absente sont ignorés en silence :
    ils ne pointeraient sur rien, et refuser tout le rôle pour un droit orphelin
    ferait perdre les autres.
    """
    from .db import DroitCategorie, DroitGeneral, DroitVue
    from . import droits as catalogue

    existants = {r.nom: r for r in session.query(Role)}
    vues = {v.nom: v.id for v in session.query(VueEnregistree)}
    touches = 0

    for entree in roles:
        nom = (entree.get("nom") or "").strip()
        if not nom:
            continue
        role = existants.get(nom)
        if role is None:
            role = Role(nom=nom, description=entree.get("description"))
            session.add(role)
            session.flush()
            existants[nom] = role

        deja_categories = {d.categorie_id for d in role.droits_categorie}
        deja_generaux = {d.droit for d in role.droits_generaux}
        deja_vues = {d.vue_id for d in role.droits_vue}
        avant = (len(deja_categories), len(deja_generaux), len(deja_vues))

        for droit in entree.get("categories") or []:
            categorie_id = categories.get(droit.get("categorie"))
            if not categorie_id or categorie_id in deja_categories:
                continue
            session.add(DroitCategorie(
                role_id=role.id, categorie_id=categorie_id,
                peut_voir=bool(droit.get("peut_voir", True)),
                peut_modifier=bool(droit.get("peut_modifier")),
                peut_deposer=bool(droit.get("peut_deposer")),
                peut_telecharger=bool(droit.get("peut_telecharger", True)),
                peut_supprimer=bool(droit.get("peut_supprimer")),
                peut_gerer_versions=bool(droit.get("peut_gerer_versions")),
            ))
            deja_categories.add(categorie_id)
        for general in entree.get("generaux") or []:
            if general in catalogue.GENERAUX and general not in deja_generaux:
                session.add(DroitGeneral(role_id=role.id, droit=general))
                deja_generaux.add(general)
        for nom_vue in entree.get("vues") or []:
            vue_id = vues.get(nom_vue)
            if vue_id and vue_id not in deja_vues:
                session.add(DroitVue(role_id=role.id, vue_id=vue_id))
                deja_vues.add(vue_id)

        if (len(deja_categories), len(deja_generaux), len(deja_vues)) != avant:
            touches += 1
    return touches


def _importer_vues(session: Session, vues: list, categories: dict) -> int:
    connues = {v.nom for v in session.query(VueEnregistree).all()}
    ajoutees = 0
    for entree in vues:
        nom = (entree.get("nom") or "").strip()
        if not nom or nom in connues:
            continue
        session.add(VueEnregistree(
            nom=nom, categorie_id=categories.get(entree.get("categorie")),
            criteres=json.dumps(entree.get("criteres") or [], ensure_ascii=False),
            partagee=bool(entree.get("partagee", True)), ordre=entree.get("ordre") or 100,
        ))
        connues.add(nom)
        ajoutees += 1
    return ajoutees


def _importer_tableaux(session: Session, tableaux: list) -> int:
    connus = {t.nom for t in session.query(TableauDeBord).all()}
    ajoutes = 0
    for entree in tableaux:
        nom = (entree.get("nom") or "").strip()
        if not nom or nom in connus:
            continue
        session.add(TableauDeBord(
            nom=nom, description=entree.get("description"),
            ordre=entree.get("ordre") or 100,
            partage=bool(entree.get("partage", True)),
            widgets=json.dumps(entree.get("widgets") or [], ensure_ascii=False),
        ))
        connus.add(nom)
        ajoutes += 1
    return ajoutes


def _importer_tables(session: Session, tables: list) -> tuple:
    """
    Crée les tables de données absentes, avec leurs colonnes et, si le fichier
    les porte, leurs lignes.

    Une table déjà présente n'est **pas** modifiée : ses colonnes pourraient
    différer, et les aligner d'autorité reviendrait à toucher aux données du
    foyer sans qu'il l'ait demandé.
    """
    ajoutees = lignes_ajoutees = 0
    existantes = {t.nom_table for t in session.query(TableDonnees).all()}
    a_regler: list = []

    for entree in tables:
        nom_table = (entree.get("nom_table") or "").strip()
        if not nom_table or nom_table in existantes:
            continue
        colonnes = [{"nom": c["nom"], "type": c.get("type") or "texte",
                     "obligatoire": bool(c.get("obligatoire"))}
                    for c in (entree.get("colonnes") or []) if c.get("nom")]
        if not colonnes:
            continue
        try:
            cree = base_donnees.creer_table(
                session, nom_table[len(base_donnees.PREFIXE_DONNEES):]
                if nom_table.startswith(base_donnees.PREFIXE_DONNEES) else nom_table,
                entree.get("libelle") or nom_table, colonnes, entree.get("description"))
        except base_donnees.OperationRefusee as erreur:
            log.warning("Table « %s » non importée : %s", nom_table, erreur)
            continue
        ajoutees += 1
        existantes.add(cree)

        # `SessionLocal` ne rince pas d'office (`autoflush=False`) : sans ce
        # flush, la table qu'on vient d'inscrire n'est pas encore visible de la
        # requête qui suit, et le réglage d'affichage échoue en prétendant que la
        # table n'existe pas.
        session.flush()
        try:
            base_donnees.regler_affichage(
                session, cree, entree.get("libelle"), entree.get("description"),
                entree.get("colonne_libelle"), entree.get("colonnes_identifiantes"))
        except base_donnees.OperationRefusee as erreur:
            # Un réglage d'affichage refusé ne doit pas emporter la table : elle
            # est créée, elle sert, et son affichage se règle à la main.
            log.warning("Affichage de « %s » non appliqué : %s", cree, erreur)

        # Réglages de colonnes : intitulé et liaison. Posés après la création de
        # **toutes** les tables ? Non — une liaison peut pointer une table encore
        # à créer, on les repasse donc en fin d'import (voir plus bas).
        for colonne in entree.get("colonnes") or []:
            if not (colonne.get("libelle") or colonne.get("source_table")):
                continue
            a_regler.append((cree, colonne))

        for cles in entree.get("cles_uniques") or []:
            try:
                base_donnees.definir_unicite(session, cree, cles)
            except base_donnees.OperationRefusee as erreur:
                log.warning("Unicité non posée sur « %s » : %s", cree, erreur)

        for ligne in entree.get("lignes") or []:
            try:
                base_donnees.inserer_ligne(session, cree, ligne)
                lignes_ajoutees += 1
            except base_donnees.OperationRefusee as erreur:
                log.warning("Ligne non importée dans « %s » : %s", cree, erreur)

    # Les liaisons en dernier : une colonne peut pointer une table que le fichier
    # décrit plus loin, et l'ordre du fichier ne doit pas décider du résultat.
    for nom_table, colonne in a_regler:
        try:
            base_donnees.regler_colonne(session, nom_table, colonne["nom"],
                                        colonne.get("libelle"), colonne.get("source_table"))
        except base_donnees.OperationRefusee as erreur:
            log.warning("Réglage de « %s.%s » non appliqué : %s",
                        nom_table, colonne["nom"], erreur)

    return ajoutees, lignes_ajoutees
