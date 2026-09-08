"""
Moteur de filtres générique appliqué aux documents.

Un filtre est un triplet `{champ, operateur, valeur}`. Une liste de filtres est
combinée en ET. Ce format unique sert à la fois :
  - à la recherche par colonne du tableau (§10 du cahier des charges) ;
  - aux critères mémorisés par une vue enregistrée (§9.B) ;
  - à tout filtrage ultérieur (centre d'analyse, exports...).

Champs reconnus :
  texte           recherche plein texte sur le texte océrisé (index FULLTEXT)
  nom_fichier     nom technique du fichier
  categorie       par identifiant (sous-catégories incluses) ou par nom
  statut          état de traitement du document
  date_document   date extraite du document
  date_import     date d'entrée dans le registre
  meta:<cle>      n'importe quelle métadonnée extraite (ex: `meta:montant_ttc`)
  lien:<table>    la **chose** concernée, quel que soit le champ qui la nomme
                  (ex: `lien:usr_vehicules` = « ce document concerne ce véhicule »)

Le préfixe `meta:` est ce qui rend le moteur générique : toute règle
d'extraction crée une clé dans `metadonnees`, immédiatement filtrable sans
modifier ni le code ni le schéma. Les futurs champs personnalisés passeront
par le même chemin.

Aucune valeur n'est interpolée dans du SQL : les champs sont résolus par une
table de correspondance et les valeurs passent par des paramètres liés.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import String, and_, cast, exists, not_, select
from sqlalchemy.orm import Session

from .db import (
    Categorie, Document, Metadonnee, RegleExtraction,
    ids_categorie_et_descendants,
)

PREFIXE_META = "meta:"
# La chose concernée, et non le champ qui la nomme (§20). Un document désigne un
# véhicule par « véhicule concerné », un autre par « propriétaire » : demander
# `meta:vehicule` en manquerait la moitié. `lien:usr_vehicules` réunit **tous**
# les champs qui pointent cette table — c'est le « l'un ou l'autre » que le reste
# du moteur, qui combine en ET, ne sait pas dire.
PREFIXE_LIEN = "lien:"

# Opérateurs acceptés, par famille de champ.
OPERATEURS_TEXTE = {"contient", "egal", "commence_par", "vide", "non_vide"}
OPERATEURS_DATE = {"egal", "contient", "avant", "apres", "entre", "vide", "non_vide"}
OPERATEURS_REFERENCE = {"egal", "contient", "vide", "non_vide"}
# Pas de « contient » sur un lien : on désigne une ligne, on ne cherche pas un
# morceau de son nom. La recherche par nom se fait sur le champ qui la porte.
OPERATEURS_LIEN = {"egal", "vide", "non_vide"}

CHAMPS_TEXTE = {"nom_fichier": Document.nom_fichier}
CHAMPS_DATE = {"date_document": Document.date_document, "date_import": Document.date_import}


class FiltreInvalide(ValueError):
    """Filtre rejetable tel quel vers un HTTP 422."""


class Filtre(BaseModel):
    champ: str
    operateur: str = "contient"
    valeur: Optional[object] = None


def _texte(valeur) -> str:
    if valeur is None:
        raise FiltreInvalide("une valeur est attendue")
    return str(valeur).strip()


def _date(valeur) -> date:
    texte = _texte(valeur)
    for format_date in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texte, format_date).date()
        except ValueError:
            continue
    raise FiltreInvalide(f"date illisible : « {texte} » (attendu AAAA-MM-JJ)")


def echapper_like(valeur: str) -> str:
    """
    Neutralise ce que MariaDB lirait comme un joker dans un `LIKE` (§22.38).

    Sans cela, chercher « 50 % » ramenait tout — `%` veut dire « n'importe quoi »
    — et « 2026_08 » ramenait « 2026-08 » comme « 2026x08 ». Ce ne sont pas des
    jokers volontaires : c'est du texte tapé dans un champ de recherche.
    """
    return (str(valeur or "").replace("\\", "\\\\")
            .replace("%", "\\%").replace("_", "\\_"))


def _condition_texte(colonne, operateur: str, valeur):
    if operateur == "vide":
        return (colonne.is_(None)) | (colonne == "")
    if operateur == "non_vide":
        return (colonne.isnot(None)) & (colonne != "")
    motif = _texte(valeur)
    if operateur == "egal":
        return colonne == motif
    if operateur == "commence_par":
        return colonne.like(f"{echapper_like(motif)}%", escape="\\")
    return colonne.like(f"%{echapper_like(motif)}%", escape="\\")  # contient


def _condition_date(colonne, operateur: str, valeur):
    if operateur == "vide":
        return colonne.is_(None)
    if operateur == "non_vide":
        return colonne.isnot(None)
    if operateur == "contient":
        # saisie partielle depuis un champ de recherche de colonne : « 2026 »,
        # « 2026-08 »... on compare alors la date sous sa forme texte
        return cast(colonne, String).like(
            f"%{echapper_like(_texte(valeur))}%", escape="\\")
    if operateur == "entre":
        if not isinstance(valeur, (list, tuple)) or len(valeur) != 2:
            raise FiltreInvalide("l'opérateur « entre » attend deux dates [début, fin]")
        return colonne.between(_date(valeur[0]), _date(valeur[1]))
    valeur_date = _date(valeur)
    if operateur == "avant":
        return colonne < valeur_date
    if operateur == "apres":
        return colonne > valeur_date
    return colonne == valeur_date  # egal


def _condition_reference(session: Session, filtre: Filtre, modele, colonne_document):
    """
    Filtre sur une table de référence (catégorie, émetteur) sans jointure : on
    passe par un `IN (sous-requête)`, ce qui permet d'empiler plusieurs filtres
    sur le même champ sans conflit de jointure.
    """
    if filtre.operateur == "vide":
        return colonne_document.is_(None)
    if filtre.operateur == "non_vide":
        return colonne_document.isnot(None)

    valeur = _texte(filtre.valeur)
    if filtre.operateur == "egal" and valeur.isdigit():
        identifiant = int(valeur)
        if modele is Categorie:
            # sélectionner une section doit ramener ses sous-catégories
            return colonne_document.in_(ids_categorie_et_descendants(session, identifiant))
        return colonne_document == identifiant

    sous_requete = select(modele.id).where(
        modele.nom == valeur if filtre.operateur == "egal" else modele.nom.like(f"%{valeur}%")
    )
    return colonne_document.in_(sous_requete)


def _condition_metadonnee(filtre: Filtre, cle: str):
    """Filtre sur une métadonnée extraite, via EXISTS corrélé sur `metadonnees`."""
    base = and_(Metadonnee.document_id == Document.id, Metadonnee.cle == cle)

    if filtre.operateur == "vide":
        return not_(exists(select(Metadonnee.id).where(
            base, Metadonnee.valeur.isnot(None), Metadonnee.valeur != ""
        )))
    if filtre.operateur == "non_vide":
        condition_valeur = and_(Metadonnee.valeur.isnot(None), Metadonnee.valeur != "")
    else:
        condition_valeur = _condition_texte(Metadonnee.valeur, filtre.operateur, filtre.valeur)

    return exists(select(Metadonnee.id).where(base, condition_valeur))


def _condition_lien(session: Session, filtre: Filtre, table: str):
    """
    « Ce document concerne cette chose », sans dire par quel champ (§20).

    Les références sont stockées `usr_vehicules:3` dans la valeur de la
    métadonnée, quelle qu'en soit la clé. Il suffit donc de chercher la valeur
    et d'ignorer la clé : le OU entre les champs est obtenu sans jamais écrire
    de OU, et le jour où quelqu'un invente un troisième champ pointant la même
    table, il compte sans qu'on ait rien à modifier.
    """
    from . import base_donnees

    if filtre.operateur in {"vide", "non_vide"}:
        # rattaché à *n'importe quelle* ligne de cette table
        rattache = exists(select(Metadonnee.id).where(
            Metadonnee.document_id == Document.id,
            Metadonnee.valeur.like(f"{table}{base_donnees.SEPARATEUR_SOURCE}%"),
        ))
        return rattache if filtre.operateur == "non_vide" else not_(rattache)

    valeur = _texte(filtre.valeur)
    if not valeur:
        raise FiltreInvalide("un lien se pose sur une ligne précise")
    # On accepte « 3 » comme « usr_vehicules:3 » : l'interface envoie l'un ou
    # l'autre selon qu'elle vient d'une liste de lignes ou d'une métadonnée déjà
    # écrite, et les deux désignent la même chose.
    if base_donnees.SEPARATEUR_SOURCE in valeur:
        source, identifiant = valeur.split(base_donnees.SEPARATEUR_SOURCE, 1)
        if source != table:
            raise FiltreInvalide(
                f"la référence « {valeur} » ne concerne pas la table « {table} »")
    else:
        identifiant = valeur
    reference = f"{table}{base_donnees.SEPARATEUR_SOURCE}{identifiant}"

    return exists(select(Metadonnee.id).where(
        Metadonnee.document_id == Document.id, Metadonnee.valeur == reference))


def _table_de_lien(session: Session, champ: str) -> str:
    """La table visée par `lien:<table>`, vérifiée — le nom vient du client."""
    from . import base_donnees

    table = champ[len(PREFIXE_LIEN):].strip()
    if not table:
        raise FiltreInvalide("le champ « lien: » doit être suivi d'une table du foyer")
    if not base_donnees.est_table_donnees(session, table):
        raise FiltreInvalide(f"« {table} » n'est pas une table du foyer")
    return table


def _verifier_operateur(filtre: Filtre, autorises: set[str]) -> None:
    if filtre.operateur not in autorises:
        raise FiltreInvalide(
            f"opérateur « {filtre.operateur} » non supporté pour le champ « {filtre.champ} » "
            f"(attendu : {', '.join(sorted(autorises))})"
        )


def condition(session: Session, filtre: Filtre):
    """Traduit un filtre en condition SQLAlchemy. Lève FiltreInvalide si le filtre est incorrect."""
    champ = (filtre.champ or "").strip()

    try:
        if champ.startswith(PREFIXE_META):
            cle = champ[len(PREFIXE_META):]
            if not cle:
                raise FiltreInvalide("le champ « meta: » doit être suivi d'une clé de métadonnée")
            _verifier_operateur(filtre, OPERATEURS_TEXTE)
            return _condition_metadonnee(filtre, cle)

        if champ.startswith(PREFIXE_LIEN):
            _verifier_operateur(filtre, OPERATEURS_LIEN)
            return _condition_lien(session, filtre, _table_de_lien(session, champ))

        if champ == "texte":
            valeur = _texte(filtre.valeur)
            return Document.texte_ocr.match(valeur)

        if champ == "statut":
            _verifier_operateur(filtre, {"egal"})
            return Document.statut == _texte(filtre.valeur)

        if champ == "categorie":
            _verifier_operateur(filtre, OPERATEURS_REFERENCE)
            return _condition_reference(session, filtre, Categorie, Document.categorie_id)

        if champ in CHAMPS_DATE:
            _verifier_operateur(filtre, OPERATEURS_DATE)
            return _condition_date(CHAMPS_DATE[champ], filtre.operateur, filtre.valeur)

        if champ in CHAMPS_TEXTE:
            _verifier_operateur(filtre, OPERATEURS_TEXTE)
            return _condition_texte(CHAMPS_TEXTE[champ], filtre.operateur, filtre.valeur)

    except FiltreInvalide as erreur:
        raise FiltreInvalide(f"Filtre « {champ} » : {erreur}")

    raise FiltreInvalide(f"Champ de filtre inconnu : « {champ} »")


def valider_champ(session: Session, champ: str) -> None:
    """
    Vérifie qu'un champ de filtre existe, **indépendamment de sa valeur**.

    `appliquer()` ignore volontairement un filtre sans valeur : c'est ce qui
    permet à l'interface d'envoyer une colonne laissée vide. Mais une définition
    que l'on **enregistre** — vue, tableau de bord — doit être vérifiée dès la
    saisie, sans quoi la faute de frappe ne se manifesterait jamais.
    """
    champ = (champ or "").strip()
    if champ.startswith(PREFIXE_META):
        if not champ[len(PREFIXE_META):]:
            raise FiltreInvalide("le champ « meta: » doit être suivi d'une clé de métadonnée")
        return
    if champ.startswith(PREFIXE_LIEN):
        _table_de_lien(session, champ)   # lève si la table n'existe pas
        return
    if champ not in {c["champ"] for c in champs_disponibles(session)}:
        raise FiltreInvalide(f"Champ de filtre inconnu : « {champ} »")


def appliquer(query, session: Session, filtres: list[Filtre]):
    """Ajoute tous les filtres à la requête, combinés en ET. Les filtres vides sont ignorés."""
    for filtre in filtres:
        if filtre.operateur not in {"vide", "non_vide"} and (
            filtre.valeur is None or (isinstance(filtre.valeur, str) and not filtre.valeur.strip())
        ):
            continue  # champ de recherche laissé vide dans l'interface
        query = query.filter(condition(session, filtre))
    return query


def champs_disponibles(session: Session) -> list[dict]:
    """
    Décrit les champs filtrables, pour que l'interface construise ses colonnes
    de recherche sans les coder en dur (y compris les métadonnées existantes).
    """
    champs = [
        {"champ": "texte", "libelle": "Texte du document", "type": "texte_integral",
         "operateurs": ["contient"]},
        {"champ": "categorie", "libelle": "Catégorie", "type": "reference",
         "operateurs": sorted(OPERATEURS_REFERENCE)},
        {"champ": "date_document", "libelle": "Date du document", "type": "date",
         "operateurs": sorted(OPERATEURS_DATE)},
        {"champ": "date_import", "libelle": "Date d'import", "type": "date",
         "operateurs": sorted(OPERATEURS_DATE)},
        {"champ": "statut", "libelle": "Statut", "type": "liste", "operateurs": ["egal"]},
        {"champ": "nom_fichier", "libelle": "Nom du fichier", "type": "texte",
         "operateurs": sorted(OPERATEURS_TEXTE)},
    ]
    # Trois sources réunies, et chacune répond à un moment différent de la vie
    # d'un champ :
    #
    #   * les clés **déjà portées par un document** — ce qui existe pour de bon ;
    #   * les **cibles des règles d'extraction** — une règle écrite mais qui n'a
    #     encore rien reconnu doit pouvoir être exigée ou filtrée sans attendre
    #     qu'un document la déclenche ;
    #   * les **champs qu'un type déclare attendre** — c'est le cas qui manquait :
    #     un type peut réclamer « Titulaire » sans qu'aucune règle ne le remplisse
    #     (il se saisit à la main, ou se déduit d'une table du foyer, §18.47). Il
    #     n'apparaissait alors nulle part, et l'on ne pouvait ni filtrer dessus ni
    #     construire une vue avec — alors que c'est précisément une colonne du
    #     tableau de ce type.
    from . import conformite
    from .db import RegleChampCategorie, TableDonnees

    cles = {c[0] for c in session.query(Metadonnee.cle).distinct() if c[0]}
    cles |= {c[0] for c in session.query(RegleExtraction.champ_cible).distinct() if c[0]}

    # Les intitulés déclarés par les types : « Montant TTC » a été nommé une fois,
    # là où on l'exige. Le reprendre ici évite de montrer « Montant ttc » dans un
    # écran et « Montant TTC » dans l'autre.
    libelles = {}
    for regle in session.query(RegleChampCategorie):
        if not regle.champ.startswith(PREFIXE_META):
            continue
        cle = regle.champ[len(PREFIXE_META):]
        cles.add(cle)
        if regle.libelle and cle not in libelles:
            libelles[cle] = regle.libelle

    champs.extend({
        "champ": f"{PREFIXE_META}{cle}",
        "libelle": libelles.get(cle) or cle.replace("_", " ").capitalize(),
        "type": "texte",
        "operateurs": sorted(OPERATEURS_TEXTE),
    } for cle in sorted(cles))

    # Un critère par **table réellement désignée par un champ** (§22).
    #
    # Ce critère répond à « tout ce qui concerne cette chose-là », quel que soit
    # le champ qui la nomme : le titulaire d'un contrat et l'émetteur d'une
    # facture puisent dans la même table, `lien:` les réunit. La liste vient donc
    # des champs attendus qui puisent quelque part — une table que personne ne
    # désigne ne ramènerait jamais rien, et la liste des critères est déjà longue.
    #
    # Avant le §22.1, elle venait des « fiches de liaison » : il fallait créer une
    # catégorie pour qu'un critère apparaisse, alors que le champ, lui, existait
    # déjà. Un réglage de moins pour le même résultat.
    tables = set()
    for regle in session.query(RegleChampCategorie):
        tables.update(conformite.sources_de(regle))
    libelles_tables = {t.nom_table: t.libelle for t in session.query(TableDonnees)}
    for table in sorted(tables):
        champs.append({
            "champ": f"{PREFIXE_LIEN}{table}",
            "libelle": libelles_tables.get(table) or table,
            "type": "lien",
            "operateurs": sorted(OPERATEURS_LIEN),
        })
    return champs


# ------------------------------------------------------------------
# Valeurs réellement présentes dans les documents
# ------------------------------------------------------------------

def _valeurs_reference(session, base_ids, modele, colonne_document, recherche, limite):
    """Valeurs d'une table de référence effectivement portées par des documents."""
    ids_utilises = {
        identifiant
        for (identifiant,) in session.query(colonne_document)
        .filter(Document.id.in_(base_ids), colonne_document.isnot(None))
        .distinct()
    }
    if not ids_utilises:
        return []

    elements = {e.id: e for e in session.query(modele).all()}

    if modele is not Categorie:
        valeurs = [
            {"valeur": str(i), "libelle": elements[i].nom, "profondeur": 0}
            for i in ids_utilises if i in elements
        ]
        valeurs.sort(key=lambda v: v["libelle"].lower())
        return _limiter(valeurs, recherche, limite)

    # Catégories : on retient aussi les catégories parentes dont la descendance
    # porte des documents. Une section comme « Maison » n'est jamais posée sur un
    # document, mais la proposer permet de regrouper ses sous-catégories en un
    # clic — et elle correspond bien à des documents réellement présents.
    retenus = set(ids_utilises)
    for identifiant in ids_utilises:
        parent = elements[identifiant].parent_id if identifiant in elements else None
        vus = set()
        while parent is not None and parent in elements and parent not in vus:
            vus.add(parent)
            retenus.add(parent)
            parent = elements[parent].parent_id

    def ascendance(identifiant):
        """Chemin des noms depuis la racine — sert au tri et à la profondeur."""
        noms, courant, vus = [], identifiant, set()
        while courant is not None and courant in elements and courant not in vus:
            vus.add(courant)
            noms.append(elements[courant].nom.lower())
            courant = elements[courant].parent_id
        return list(reversed(noms))

    valeurs = [
        {"valeur": str(i), "libelle": elements[i].nom, "profondeur": len(ascendance(i)) - 1}
        for i in retenus if i in elements
    ]
    valeurs.sort(key=lambda v: ascendance(int(v["valeur"])))  # ordre de l'arborescence
    return _limiter(valeurs, recherche, limite)


def _limiter(valeurs, recherche, limite):
    if recherche:
        motif = recherche.strip().lower()
        valeurs = [v for v in valeurs if motif in v["libelle"].lower()]
    return valeurs[:limite]


def valeurs_distinctes(session: Session, champ: str, base_ids, recherche: Optional[str] = None,
                       limite: int = 50) -> list[dict]:
    """
    Valeurs déjà présentes dans les documents pour un champ donné — c'est ce que
    proposent les listes de suggestion des colonnes, plutôt qu'un catalogue de
    valeurs théoriques. Seules les valeurs distinctes sont renvoyées, sans
    décompte d'occurrences.

    `base_ids` est une requête d'identifiants de documents déjà restreinte aux
    droits de l'utilisateur (et éventuellement aux autres filtres actifs), afin
    que les suggestions ne révèlent rien qu'il n'a pas le droit de voir.
    """
    champ = (champ or "").strip()

    if champ == "categorie":
        return _valeurs_reference(session, base_ids, Categorie, Document.categorie_id, recherche, limite)
    if champ.startswith(PREFIXE_LIEN):
        return _valeurs_lien(session, _table_de_lien(session, champ), base_ids, recherche, limite)

    if champ.startswith(PREFIXE_META):
        cle = champ[len(PREFIXE_META):]
        if not cle:
            raise FiltreInvalide("le champ « meta: » doit être suivi d'une clé de métadonnée")
        colonne = Metadonnee.valeur
        requete = session.query(colonne).filter(
            Metadonnee.document_id.in_(base_ids),
            Metadonnee.cle == cle,
            colonne.isnot(None),
            colonne != "",
        )
    elif champ in CHAMPS_TEXTE or champ in CHAMPS_DATE or champ == "statut":
        colonne = CHAMPS_TEXTE.get(champ) or CHAMPS_DATE.get(champ) or Document.statut
        requete = session.query(colonne).filter(Document.id.in_(base_ids), colonne.isnot(None))
    else:
        raise FiltreInvalide(f"Champ de filtre inconnu : « {champ} »")

    if champ.startswith(PREFIXE_META):
        # Une métadonnée adossée à une source vaut « sys_utilisateurs:13 » :
        # proposer cela dans une liste de suggestions ne veut rien dire. On
        # résout les libellés, et la recherche porte alors sur le nom lisible —
        # on tape « Dupont », pas un numéro de ligne.
        valeurs = [
            str(v) for (v,) in requete.distinct().order_by(colonne)
            if v is not None and str(v) != ""
        ]
        libelles = _libelles_metadonnee(session, cle, valeurs)
        if libelles:
            resultat = [
                {"valeur": v, "libelle": libelles.get(v, v), "profondeur": 0}
                for v in valeurs
            ]
            return _limiter(resultat, recherche, limite)

    if recherche:
        requete = requete.filter(cast(colonne, String).like(
            f"%{echapper_like(recherche.strip())}%", escape="\\"))

    return [
        {"valeur": str(valeur), "libelle": str(valeur), "profondeur": 0}
        for (valeur,) in requete.distinct().order_by(colonne).limit(limite)
        if valeur is not None and str(valeur) != ""
    ]


def _valeurs_lien(session: Session, table: str, base_ids, recherche, limite) -> list[dict]:
    """
    Les choses **réellement concernées** par les documents visibles (§20).

    On ne propose pas toutes les lignes de la table : un foyer peut tenir la
    liste de ses membres sans qu'aucun document ne désigne le petit dernier, et
    une suggestion qui ne ramène rien est une fausse piste. La liste vient donc
    des documents, comme partout ailleurs dans cet écran.
    """
    from . import base_donnees

    prefixe = f"{table}{base_donnees.SEPARATEUR_SOURCE}"
    references = {
        str(v) for (v,) in session.query(Metadonnee.valeur)
        .filter(Metadonnee.document_id.in_(base_ids), Metadonnee.valeur.like(f"{prefixe}%"))
        .distinct()
        if v
    }
    if not references:
        return []
    identifiants = {r[len(prefixe):] for r in references}
    libelles = base_donnees.libelles_par_id(session, table, identifiants)
    valeurs = sorted(
        ({"valeur": reference, "libelle": libelles.get(reference[len(prefixe):], reference),
          "profondeur": 0} for reference in references),
        key=lambda v: v["libelle"].lower())
    return _limiter(valeurs, recherche, limite)


def _libelles_metadonnee(session: Session, cle: str, valeurs: list[str]) -> dict:
    """
    Libellés des valeurs d'une métadonnée adossée à une ou plusieurs sources.
    Renvoie un dictionnaire vide si le champ n'est adossé à rien — le cas de
    l'immense majorité des métadonnées, qui portent déjà leur propre texte.
    """
    from . import base_donnees, conformite

    champ = f"{PREFIXE_META}{cle}"
    tables: list[str] = []
    for (_, champ_regle), sources in conformite.sources_par_categorie(session).items():
        if champ_regle == champ:
            for source in sources:
                if source not in tables:
                    tables.append(source)
    if not tables:
        return {}

    besoins: dict[str, set] = {}
    decoupe = {}
    for valeur in valeurs:
        table, identifiant = base_donnees.decouper_valeur(valeur, tables[0])
        if table in tables:
            besoins.setdefault(table, set()).add(identifiant)
            decoupe[valeur] = (table, identifiant)

    resolus = {t: base_donnees.libelles_par_id(session, t, ids) for t, ids in besoins.items()}
    libelles = {}
    for valeur, (table, identifiant) in decoupe.items():
        libelle = resolus.get(table, {}).get(str(identifiant))
        if libelle:
            libelles[valeur] = libelle
    return libelles


# ------------------------------------------------------------
# Tri
# ------------------------------------------------------------

# Colonnes sur lesquelles un tri est accepté. Liste fermée : le nom de colonne
# vient du client, il ne doit jamais atteindre la requête sans être reconnu.
TRIS = {
    "date_import": Document.date_import,
    "date_document": Document.date_document,
    "statut": Document.statut,
    "nom_fichier": Document.nom_fichier,
}

# Trier sur le **nom** d'une table liée, pas sur son identifiant : « Banque »
# avant « Factures », et non l'ordre de création. Une sous-requête corrélée
# évite la jointure, qui entrerait en conflit avec celles des filtres.
TRIS_LIES = {
    "categorie": (Categorie, Document.categorie_id),
}


def tris_disponibles(session: Optional[Session] = None) -> list[str]:
    """
    Colonnes triables. Avec une session, les métadonnées connues sont ajoutées :
    ce sont elles qui composent l'essentiel des tableaux par catégorie.
    """
    tris = list(TRIS) + list(TRIS_LIES)
    if session is not None:
        cles = {c[0] for c in session.query(Metadonnee.cle).distinct() if c[0]}
        tris += [f"{PREFIXE_META}{cle}" for cle in cles]
    return sorted(tris)


def ordonner(query, tri: Optional[str], sens: Optional[str]):
    """
    Applique un tri à la requête. Un champ inconnu est refusé plutôt qu'ignoré :
    l'utilisateur doit savoir que son tri n'a pas été pris en compte.

    Les métadonnées (`meta:<cle>`) sont triées comme du texte, y compris les
    montants : la valeur est stockée telle qu'extraite. « 9,90 » passe donc
    après « 100,00 ». Trier sur des nombres demanderait de les convertir à la
    volée sur toute la table — la lenteur serait payée à chaque tri, pour un
    besoin qui reste marginal.
    """
    tri = (tri or "date_import").strip()
    descendant = (sens or "desc").lower() != "asc"

    if tri in TRIS:
        colonne = TRIS[tri]
    elif tri in TRIS_LIES:
        modele, cle = TRIS_LIES[tri]
        colonne = select(modele.nom).where(modele.id == cle).scalar_subquery()
    elif tri.startswith(PREFIXE_META):
        # Les colonnes propres à une catégorie sont pour la plupart des
        # métadonnées (§18.1) : sans ce cas, un clic sur « Montant TTC » ne
        # triait rien. Sous-requête corrélée plutôt que jointure, pour la même
        # raison que les tris liés — une jointure entrerait en conflit avec
        # celles des filtres actifs.
        meta = tri[len(PREFIXE_META):]
        if not meta:
            raise FiltreInvalide("le tri « meta: » doit être suivi d'une clé de métadonnée")
        colonne = (
            select(Metadonnee.valeur)
            .where(Metadonnee.document_id == Document.id, Metadonnee.cle == meta)
            .limit(1)
            .scalar_subquery()
        )
    else:
        raise FiltreInvalide(
            f"Tri « {tri} » inconnu (attendu : {', '.join(tris_disponibles())})"
        )

    # `id` en second critère : sans lui, deux documents de même date pourraient
    # changer d'ordre entre deux pages et l'un apparaître deux fois
    ordre = colonne.desc() if descendant else colonne.asc()
    return query.order_by(ordre, Document.id.desc())
