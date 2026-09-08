"""
Conformité d'un document aux règles de champs de sa catégorie (§15).

Une catégorie déclare les champs attendus sur ses documents et, pour chacun,
s'il est obligatoire ou facultatif. Ce module dit, pour un document donné,
quels champs obligatoires manquent.

Le vocabulaire des champs est **celui du moteur de filtres** (`app/filtres.py`) :
soit un champ du document, soit `meta:<cle>` pour une métadonnée extraite.
Conséquence directe : une nouvelle règle d'extraction crée une clé qui devient
aussitôt exigible, sans migration ni code supplémentaire.

Un document sans catégorie n'a aucune règle à respecter : on ne sait pas encore
ce qu'on attend de lui.
"""
from typing import Optional

from sqlalchemy import and_, exists, func, literal, or_, select
from sqlalchemy.orm import Session

from .db import Document, Metadonnee, RegleChampCategorie
from .filtres import PREFIXE_META


def libelle_par_defaut(champ: str) -> str:
    """Intitulé lisible d'un champ, quand la règle n'en précise pas."""
    connus = {
        "categorie": "Catégorie",
        "date_document": "Date du document",
        "date_import": "Date d'import",
        "nom_fichier": "Nom du fichier",
        "statut": "Statut",
    }
    if champ in connus:
        return connus[champ]
    if champ.startswith(PREFIXE_META):
        return champ[len(PREFIXE_META):].replace("_", " ").capitalize()
    return champ


def _valeur_presente(document: Document, champ: str) -> bool:
    """Le document porte-t-il une valeur exploitable pour ce champ ?"""
    if champ.startswith(PREFIXE_META):
        cle = champ[len(PREFIXE_META):]
        return any(
            m.cle == cle and m.valeur is not None and str(m.valeur).strip() != ""
            for m in document.metadonnees
        )
    if champ == "categorie":
        return document.categorie_id is not None
    if champ == "date_document":
        return document.date_document is not None
    if champ == "nom_fichier":
        return bool(document.nom_fichier)
    if champ == "statut":
        return bool(document.statut)
    # champ inconnu : on ne peut rien affirmer, on ne bloque donc pas le document
    return True


def clause_incomplet(session: Optional[Session] = None):
    """
    Expression SQL vraie pour un document à qui il manque un champ obligatoire.

    Elle double `_valeur_presente`, et c'est assumé : le Python sert à *dire*
    ce qui manque sur un document qu'on affiche, le SQL à *écarter* ceux qui
    manquent avant même de les compter. Le faire en Python obligerait à charger
    tout le registre pour en paginer une page.

    **Les règles sont lues d'abord, et non corrélées** (§22.40). L'écriture
    précédente demandait à la base, *pour chaque document*, « existe-t-il une
    règle obligatoire de sa catégorie dont la valeur manque ? » — deux niveaux
    de sous-requêtes corrélées, mesurés à 146 ms pour compter cinq mille
    documents, et ce compte est refait à chaque page du registre et à chaque
    relevé des compteurs. Or les règles d'un foyer se comptent sur les doigts :
    les lire en une requête, puis composer une condition par couple
    (catégorie, champ), laisse à la base des comparaisons indexées — 6 ms pour
    le même compte.

    Deux propriétés à conserver si l'on touche à l'un des deux :

    * un champ inconnu ne bloque rien — aucune branche ne lui correspond, donc
      il ne rend personne incomplet ;
    * un document sans catégorie n'est jamais incomplet : aucune condition ne
      porte sur `categorie_id IS NULL`. On ne sait pas encore ce qu'on attend
      de lui.

    Sans `session`, on retombe sur la forme corrélée : quelques appels anciens
    n'en passent pas, et un garde-fou ne doit pas dépendre d'un renommage
    réussi partout du premier coup.
    """
    if session is None:
        return _clause_incomplet_correlee()

    # Les couples (catégorie, champ) sont relus **une fois par session**, donc
    # une fois par requête HTTP : un tableau de bord qui pose quatre indicateurs
    # les relisait quatre fois pour un résultat identique.
    paires = session.info.get("champs_obligatoires")
    if paires is None:
        paires = [(r.categorie_id, r.champ) for r in
                  session.query(RegleChampCategorie.categorie_id, RegleChampCategorie.champ)
                  .filter(RegleChampCategorie.obligatoire.is_(True))]
        session.info["champs_obligatoires"] = paires

    par_categorie: dict[int, list] = {}
    for categorie_id, champ in paires:
        condition = _condition_manque(champ)
        if condition is not None:
            par_categorie.setdefault(categorie_id, []).append(condition)

    if not par_categorie:
        # Aucune règle : personne n'est incomplet. `false()` plutôt qu'un `or_()`
        # vide, qui vaudrait `true` et masquerait tout le registre.
        return literal(False)
    # `categorie_id IS NOT NULL` en tête, et ce n'est pas une précaution de
    # style : sans lui, `categorie_id = 2` vaut **NULL** pour un document sans
    # catégorie, le OU entier vaut NULL, et `NOT NULL` vaut encore NULL — le
    # document disparaissait du registre au lieu d'y rester. La logique à trois
    # valeurs de SQL ne pardonne pas ; la forme corrélée, elle, rendait `false`.
    return and_(Document.categorie_id.isnot(None),
                or_(*[and_(Document.categorie_id == categorie, or_(*conditions))
                      for categorie, conditions in par_categorie.items()]))


def _condition_manque(champ: str):
    """Ce qui, en SQL, dit que ce champ-là manque. `None` pour un champ inconnu."""
    if champ == "date_document":
        return Document.date_document.is_(None)
    if champ == "nom_fichier":
        return or_(Document.nom_fichier.is_(None), Document.nom_fichier == "")
    if champ == "statut":
        return or_(Document.statut.is_(None), Document.statut == "")
    if champ.startswith(PREFIXE_META):
        cle = champ[len(PREFIXE_META):]
        # La clé est **une constante** ici, et non tirée d'une colonne : l'index
        # (document_id, cle) des métadonnées s'applique enfin.
        return ~exists(
            select(literal(1)).where(and_(
                Metadonnee.document_id == Document.id,
                Metadonnee.cle == cle,
                Metadonnee.valeur.isnot(None),
                func.trim(Metadonnee.valeur) != "",
            )).correlate(Document)
        )
    return None


def _clause_incomplet_correlee():
    """La forme d'origine, corrélée sur les règles. Voir `clause_incomplet`."""
    valeur_meta_absente = ~exists(
        select(literal(1)).where(and_(
            Metadonnee.document_id == Document.id,
            Metadonnee.cle == func.substring(RegleChampCategorie.champ, len(PREFIXE_META) + 1),
            Metadonnee.valeur.isnot(None),
            func.trim(Metadonnee.valeur) != "",
        ))
        # `correlate` explicite, et c'est indispensable : à deux niveaux
        # d'imbrication, SQLAlchemy ne devine pas que `sys_documents` vient de
        # la requête englobante et le remet dans le FROM de la sous-requête.
        .correlate(Document, RegleChampCategorie)
    )
    return exists(
        select(literal(1)).where(and_(
            RegleChampCategorie.categorie_id == Document.categorie_id,
            RegleChampCategorie.obligatoire.is_(True),
            or_(
                and_(RegleChampCategorie.champ == "date_document",
                     Document.date_document.is_(None)),
                and_(RegleChampCategorie.champ == "nom_fichier",
                     or_(Document.nom_fichier.is_(None), Document.nom_fichier == "")),
                and_(RegleChampCategorie.champ == "statut",
                     or_(Document.statut.is_(None), Document.statut == "")),
                and_(RegleChampCategorie.champ.like(f"{PREFIXE_META}%"), valeur_meta_absente),
            ),
        ))
    )


def incomplet_range():
    """
    Ce que **lisent les écrans** : l'état rangé sur le document (§22.41).

    À distinguer de `clause_incomplet`, qui *calcule* la réponse et reste la
    définition de référence : elle sert à écrire cet état, jamais à l'afficher.
    Une seule définition, deux usages — l'une écrit, l'autre lit, et le contrôle
    périodique du serveur de travaux vérifie qu'elles disent la même chose.
    """
    return Document.conforme.is_(False)


def evaluer(document: Document, regles_par_cat: dict) -> bool:
    """Ce document est-il conforme ? La question telle qu'on la range."""
    return not champs_manquants(document, regles_par_cat)


def ranger(session: Session, document: Document,
           regles_par_cat: Optional[dict] = None) -> list[dict]:
    """
    Recalcule la conformité d'un document et **l'écrit sur lui**.

    Rend les champs manquants, parce que les deux appelants en ont besoin pour
    le dire à l'écran. Appelée aux deux seuls endroits où la réponse peut
    changer : la fin du traitement d'un document, et une correction à la main.

    La collection des métadonnées est relue depuis la base : les étapes qui
    précèdent viennent d'en écrire, et une collection déjà chargée ne se remplit
    pas toute seule au `flush`. Le défaut se voyait en service — travail bloqué
    sur « Émetteur manquant » alors que le registre affichait l'émetteur.
    """
    session.flush()
    session.expire(document, ["metadonnees"])
    if regles_par_cat is None:
        regles_par_cat = regles_par_categorie(
            session, {document.categorie_id} if document.categorie_id else set())
    manquants = champs_manquants(document, regles_par_cat)
    document.conforme = not manquants
    return manquants


def recalculer(session: Session, categorie_ids: Optional[set] = None) -> int:
    """
    Repose l'état de conformité sur un lot de documents, et rend le nombre de
    ceux qui ont changé d'avis.

    Deux appelants : l'administration, quand les champs attendus d'une catégorie
    changent — ce qui rend non conformes des documents déjà indexés sans que
    personne ne repasse dessus — et le contrôle périodique du serveur de
    travaux, qui vérifie que le rangé et le calculé disent la même chose.

    Le calcul passe par la clause SQL, donc en un aller-retour : on ne charge
    pas les documents pour les interroger un par un.
    """
    base = session.query(Document.id).filter(Document.date_suppression.is_(None))
    if categorie_ids is not None:
        if not categorie_ids:
            return 0
        base = base.filter(Document.categorie_id.in_(categorie_ids))

    incomplets = {i for (i,) in base.filter(clause_incomplet(session))}
    ranges = {i for (i,) in base.filter(Document.conforme.is_(False))}

    a_marquer = incomplets - ranges
    a_liberer = ranges - incomplets
    for lot, valeur in ((a_marquer, False), (a_liberer, True)):
        for debut in range(0, len(lot), 500):
            morceau = list(lot)[debut:debut + 500]
            (session.query(Document).filter(Document.id.in_(morceau))
             .update({Document.conforme: valeur}, synchronize_session=False))
    return len(a_marquer) + len(a_liberer)


def sans_les_fantomes(query):
    """
    Écarte les documents incomplets d'une requête.

    Un document auquel il manque un champ exigé par sa catégorie n'a pas encore
    sa place dans le registre : le montrer classé alors qu'il ne l'est qu'à
    moitié laisse croire que le classement est fait. Il reste consultable par
    son identifiant, et visible au Centre d'analyse — là où on le complète.
    """
    # L'état **rangé** (§22.41), et non le calcul : c'est la seule requête du
    # projet que tout le monde traverse, et la recalculer à chaque page coûtait
    # à elle seule l'essentiel du temps de réponse du registre.
    return query.filter(Document.conforme.is_(True))


def regles_par_categorie(session: Session, categorie_ids: Optional[set[int]] = None) -> dict:
    """
    Règles obligatoires groupées par catégorie. `categorie_ids` limite la
    lecture aux catégories réellement présentes dans un lot de documents, pour
    éviter une requête par document lors de l'affichage d'une liste.
    """
    query = session.query(RegleChampCategorie).filter(RegleChampCategorie.obligatoire.is_(True))
    if categorie_ids is not None:
        if not categorie_ids:
            return {}
        query = query.filter(RegleChampCategorie.categorie_id.in_(categorie_ids))

    regles: dict[int, list[RegleChampCategorie]] = {}
    for regle in query.order_by(RegleChampCategorie.ordre, RegleChampCategorie.champ):
        regles.setdefault(regle.categorie_id, []).append(regle)
    return regles


def champs_manquants(document: Document, regles_par_cat: dict) -> list[dict]:
    """
    Champs obligatoires absents du document, dans l'ordre des règles.
    Renvoie une liste de `{champ, libelle}` — vide si le document est conforme
    ou s'il n'a pas encore de catégorie.
    """
    if document.categorie_id is None:
        return []
    return [
        {"champ": regle.champ, "libelle": regle.libelle or libelle_par_defaut(regle.champ)}
        for regle in regles_par_cat.get(document.categorie_id, [])
        if not _valeur_presente(document, regle.champ)
    ]


# Les types qu'un champ libre peut prendre (§22.12). C'est le type qui décide de
# la façon dont le champ se saisit et se relit ; sans lui, l'écran devinait
# d'après le nom de la clé — « date_facture » donnait un calendrier, « echeance »
# non.
TYPES_CHAMP = {
    "texte": "Texte",
    "texte_long": "Texte long (plusieurs lignes)",
    "date": "Date",
    "nombre": "Nombre",
    "montant": "Montant",
    "booleen": "Oui / non",
}


def valider_type(type_champ: Optional[str]) -> str:
    """Un type inconnu retombe sur « texte » plutôt que de refuser : un champ mal
    typé se saisit maladroitement, un champ refusé n'existe pas."""
    valeur = (type_champ or "texte").strip().lower()
    return valeur if valeur in TYPES_CHAMP else "texte"


def sources_de(regle) -> list[str]:
    """
    Sources d'une règle, dans l'ordre déclaré (§17.28).

    La première a un statut particulier : c'est elle qui donne son sens à une
    valeur enregistrée sans préfixe, comme celles écrites avant que les sources
    multiples n'existent.
    """
    declarees = [s.strip() for s in (regle.sources or "").split(",") if s.strip()]
    if declarees:
        return declarees
    return [regle.source_table] if regle.source_table else []


def sources_par_categorie(session: Session, categorie_ids: Optional[set[int]] = None) -> dict:
    """
    `{(categorie_id, champ): [sources]}` pour toutes les règles adossées à une ou
    plusieurs sources — obligatoires **ou** facultatives : un champ facultatif se
    saisit et s'affiche comme les autres.
    """
    query = session.query(RegleChampCategorie).filter(
        (RegleChampCategorie.source_table.isnot(None)) | (RegleChampCategorie.sources.isnot(None))
    )
    if categorie_ids is not None:
        if not categorie_ids:
            return {}
        query = query.filter(RegleChampCategorie.categorie_id.in_(categorie_ids))
    return {(r.categorie_id, r.champ): sources_de(r) for r in query if sources_de(r)}


def affichages_par_categorie(session: Session,
                             categorie_ids: Optional[set[int]] = None) -> dict:
    """
    `{(categorie_id, champ): [colonnes]}` — ce que chaque champ veut lire de sa
    ligne (§22.59). Seules les règles qui ont fait un choix figurent ici : les
    autres s'en remettent à la table, et n'ont rien à dire.
    """
    query = session.query(RegleChampCategorie).filter(
        RegleChampCategorie.colonnes_affichees.isnot(None))
    if categorie_ids is not None:
        if not categorie_ids:
            return {}
        query = query.filter(RegleChampCategorie.categorie_id.in_(categorie_ids))
    return {(r.categorie_id, r.champ):
            [c.strip() for c in r.colonnes_affichees.split(",") if c.strip()]
            for r in query}
