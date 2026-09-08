"""
Indicateurs des tableaux de bord.

Un indicateur (« widget ») est une description déclarative, jamais du code :

    {"type": "somme", "titre": "Factures 2026", "champ": "meta:montant_ttc",
     "filtres": [{"champ": "categorie", "operateur": "egal", "valeur": "2"}],
     "periode": {"champ": "date_document", "type": "annee_en_cours"},
     "unite": "€"}

Quatre types couvrent les besoins courants :

  `nombre`      combien de documents correspondent
  `somme`       total d'une métadonnée numérique (montants...)
  `repartition` groupement par catégorie, émetteur, statut ou métadonnée
  `evolution`   série par mois ou par année, pour suivre une tendance

Les **filtres réutilisent le format du registre** (`app/filtres.py`) : décrire
« les factures EDF » se fait de la même façon dans un tableau de bord et dans
une recherche par colonne. Une période n'est qu'un raccourci lisible qui se
traduit en filtres de date.

Tout passe par la requête de base fournie par l'appelant, déjà restreinte aux
droits de l'utilisateur : un tableau de bord ne révèle jamais l'existence de
documents que son lecteur ne peut pas consulter.

`portee` dit ce qu'un indicateur fait des documents incomplets (§17.7) :
`complets` par défaut — ils ne comptent pas —, `incomplets` pour ne compter
qu'eux, `tous` pour ne pas trancher.
"""
from datetime import date
from typing import Optional

from sqlalchemy import Numeric, func
from sqlalchemy.orm import Session

from . import conformite
from . import filtres as moteur_filtres
from .db import Categorie, Document, Metadonnee

PREFIXE_META = moteur_filtres.PREFIXE_META

TYPES = ("nombre", "somme", "repartition", "evolution")

# Portée d'un indicateur vis-à-vis des documents incomplets (§17.7).
#
# Par défaut un tableau de bord ne compte que ce qui est réellement classé : un
# document auquel il manque un champ exigé n'a pas sa place dans un total par
# catégorie. Mais l'indicateur « À reprendre » de l'accueil ne parle que d'eux —
# il lui faut donc pouvoir demander l'inverse. D'où ce réglage explicite, plutôt
# qu'une exclusion imposée à tous les indicateurs, qui aurait rendu ce compteur
# perpétuellement nul.
PORTEES = ("complets", "incomplets", "tous")


def appliquer_portee(base, indicateur: dict):
    """Restreint la requête de base selon la portée demandée par l'indicateur."""
    portee = indicateur.get("portee") or "complets"
    if portee not in PORTEES:
        raise IndicateurInvalide(
            f"Portée « {portee} » inconnue (attendu : {', '.join(PORTEES)})."
        )
    if portee == "complets":
        return conformite.sans_les_fantomes(base)
    if portee == "incomplets":
        return base.filter(conformite.incomplet_range())
    return base

# Périodes proposées, exprimées relativement à aujourd'hui : un tableau de bord
# doit rester juste l'an prochain sans qu'on y retouche.
PERIODES = {
    "tout": "Depuis toujours",
    "annee_en_cours": "Année en cours",
    "annee_precedente": "Année précédente",
    "12_derniers_mois": "12 derniers mois",
    "mois_en_cours": "Mois en cours",
    "personnalisee": "Période choisie",
}

CHAMPS_GROUPEMENT = {
    # « Type de document » et « Dossier » sont les deux niveaux de l'arborescence
    # depuis le §19.1 : un document appartient à un type, un type vit dans un
    # dossier. Grouper par type dit « combien de factures » ; grouper par dossier
    # dit « combien pour la maison », ce qu'aucun groupement ne savait faire —
    # un dossier ne porte aucun document en propre, il ne serait jamais apparu.
    "categorie": "Type de document",
    "dossier": "Dossier",
    "statut": "Statut",
}


class IndicateurInvalide(ValueError):
    """Description d'indicateur inexploitable, présentable à l'utilisateur."""


# ------------------------------------------------------------
# Périodes
# ------------------------------------------------------------

def bornes(periode: Optional[dict], aujourdhui: Optional[date] = None) -> tuple:
    """Traduit une période en couple (début, fin) de dates, inclus. (None, None) = pas de borne."""
    if not periode:
        return None, None
    aujourdhui = aujourdhui or date.today()
    type_periode = periode.get("type", "tout")

    if type_periode == "tout":
        return None, None
    if type_periode == "annee_en_cours":
        return date(aujourdhui.year, 1, 1), date(aujourdhui.year, 12, 31)
    if type_periode == "annee_precedente":
        return date(aujourdhui.year - 1, 1, 1), date(aujourdhui.year - 1, 12, 31)
    if type_periode == "mois_en_cours":
        debut = date(aujourdhui.year, aujourdhui.month, 1)
        return debut, _dernier_jour_du_mois(aujourdhui)
    if type_periode == "12_derniers_mois":
        # onze mois pleins plus le mois courant
        debut = _premier_jour_du_mois(aujourdhui, recul=11)
        return debut, _dernier_jour_du_mois(aujourdhui)
    if type_periode == "personnalisee":
        return _date_ou_none(periode.get("debut")), _date_ou_none(periode.get("fin"))
    raise IndicateurInvalide(f"Période « {type_periode} » inconnue.")


def _premier_jour_du_mois(reference: date, recul: int = 0) -> date:
    """Premier jour du mois de `reference`, éventuellement `recul` mois en arrière."""
    total = reference.year * 12 + (reference.month - 1) - recul
    return date(total // 12, total % 12 + 1, 1)


def _dernier_jour_du_mois(reference: date) -> date:
    suivant = _premier_jour_du_mois(reference, recul=-1)
    return date.fromordinal(suivant.toordinal() - 1)


def _date_ou_none(valeur) -> Optional[date]:
    if not valeur:
        return None
    try:
        return date.fromisoformat(str(valeur)[:10])
    except ValueError:
        raise IndicateurInvalide(f"Date « {valeur} » attendue au format AAAA-MM-JJ.")


def _colonne_date(nom: str):
    if nom == "date_import":
        return Document.date_import
    if nom in (None, "", "date_document"):
        return Document.date_document
    raise IndicateurInvalide(f"« {nom} » n'est pas une date exploitable ici.")


# ------------------------------------------------------------
# Construction de la requête
# ------------------------------------------------------------

def _requete(session: Session, base, indicateur: dict):
    """Requête d'identifiants de documents, restreinte aux droits puis à l'indicateur."""
    query = appliquer_portee(base, indicateur)
    criteres = indicateur.get("filtres") or []
    if not isinstance(criteres, list):
        raise IndicateurInvalide("Les filtres doivent être une liste.")
    try:
        query = moteur_filtres.appliquer(
            query, session, [moteur_filtres.Filtre(**c) for c in criteres]
        )
    except moteur_filtres.FiltreInvalide as erreur:
        raise IndicateurInvalide(str(erreur))
    except TypeError as erreur:
        raise IndicateurInvalide(f"Filtre illisible : {erreur}")

    periode = indicateur.get("periode")
    debut, fin = bornes(periode)
    if debut or fin:
        colonne = _colonne_date((periode or {}).get("champ"))
        if debut:
            query = query.filter(colonne >= debut)
        if fin:
            query = query.filter(colonne <= fin)
    return query


def _montant(champ: str):
    """
    Expression numérique d'une métadonnée. Les montants sont normalisés en
    « 50.99 » par le moteur d'extraction ; on convertit donc directement, et
    une valeur non numérique compte pour zéro plutôt que de faire échouer tout
    l'indicateur.
    """
    if not champ or not champ.startswith(PREFIXE_META):
        raise IndicateurInvalide(
            "Une somme porte sur une métadonnée : indiquez un champ « meta:… »."
        )
    # la virgule décimale est tolérée : une valeur saisie à la main peut valoir
    # « 50,99 » là où l'extraction normalise en « 50.99 »
    return func.coalesce(
        func.sum(func.cast(func.replace(Metadonnee.valeur, ",", "."), Numeric(16, 2))), 0
    )


def _somme(session: Session, ids, champ: str) -> float:
    # la validation d'abord : sans elle, un champ absent produisait une erreur
    # technique illisible au lieu du message explicatif
    expression = _montant(champ)
    cle = champ[len(PREFIXE_META):]
    total = session.query(expression).filter(
        Metadonnee.document_id.in_(ids), Metadonnee.cle == cle
    ).scalar()
    return float(total or 0)


# ------------------------------------------------------------
# Calcul d'un indicateur
# ------------------------------------------------------------

def calculer(session: Session, base, indicateur: dict) -> dict:
    """
    Calcule un indicateur. `base` est une requête d'identifiants de documents
    déjà restreinte aux droits de l'utilisateur.
    """
    type_indicateur = indicateur.get("type")
    if type_indicateur not in TYPES:
        raise IndicateurInvalide(
            f"Type d'indicateur « {type_indicateur} » inconnu (attendu : {', '.join(TYPES)})."
        )
    query = _requete(session, base, indicateur)
    ids = query.scalar_subquery()

    if type_indicateur == "nombre":
        return {"type": "nombre", "valeur": query.count()}

    if type_indicateur == "somme":
        return {"type": "somme", "valeur": _somme(session, ids, indicateur.get("champ"))}

    if type_indicateur == "repartition":
        return _repartition(session, query, ids, indicateur)

    return _evolution(session, query, ids, indicateur)


def _somme_demandee(indicateur: dict) -> bool:
    """La mesure est-elle une somme ? Sinon, c'est un compte — et il se fait en SQL."""
    return indicateur.get("mesure") == "somme" and bool(indicateur.get("mesure_champ"))


def _grouper(session: Session, query, colonnes_groupe, indicateur: dict) -> dict:
    """
    `{clé: valeur}` pour un indicateur groupé, sans passer les documents par
    Python quand ce n'est pas nécessaire (§22.43).

    Compter des documents par catégorie ou par mois se fait en une requête : la
    base sait le faire, et c'est la seule façon que cela ne coûte pas plus cher
    à mesure que le registre grossit. Mesuré sur vingt mille documents : 261 ms
    pour ramener chaque identifiant et les compter ici, 12 ms pour demander le
    compte à la base.

    **Une somme, elle, garde l'ancien chemin** : elle porte sur une métadonnée,
    et il faut les identifiants des documents de chaque groupe pour l'établir.
    C'est un cas rare, et il ne mérite pas qu'on le complique.
    """
    cles = tuple(colonnes_groupe)
    if _somme_demandee(indicateur):
        groupes: dict = {}
        for ligne in query.with_entities(*cles, Document.id):
            groupes.setdefault(ligne[:-1], []).append(ligne[-1])
        return {cle: _somme(session, ids, indicateur["mesure_champ"]) if ids else 0
                for cle, ids in groupes.items()}
    return {ligne[:-1]: ligne[-1] for ligne in
            query.with_entities(*cles, func.count(Document.id)).group_by(*cles)}


def _mesure(session: Session, ids_par_groupe: dict, indicateur: dict) -> dict:
    """Applique la mesure demandée (compte ou somme) à des groupes de documents."""
    champ = indicateur.get("mesure_champ")
    if indicateur.get("mesure") != "somme" or not champ:
        return {cle: len(ids) for cle, ids in ids_par_groupe.items()}
    cle_meta = champ[len(PREFIXE_META):] if champ.startswith(PREFIXE_META) else None
    if not cle_meta:
        raise IndicateurInvalide("Une somme porte sur une métadonnée « meta:… ».")
    return {
        cle: _somme(session, ids, champ) if ids else 0
        for cle, ids in ids_par_groupe.items()
    }


def _repartition(session: Session, query, ids, indicateur: dict) -> dict:
    champ = indicateur.get("champ") or "categorie"
    limite = max(1, min(int(indicateur.get("limite", 12)), 50))

    if champ == "dossier":
        return _repartition_par_dossier(session, query, indicateur, limite)
    if champ == "categorie":
        colonne, modele = Document.categorie_id, Categorie
    elif champ == "statut":
        colonne, modele = Document.statut, None
    elif champ.startswith(PREFIXE_META):
        return _repartition_metadonnee(session, query, ids, indicateur, champ, limite)
    else:
        raise IndicateurInvalide(
            f"Groupement « {champ} » impossible (attendu : "
            f"{', '.join(CHAMPS_GROUPEMENT)} ou meta:…)."
        )

    valeurs = {cle[0]: valeur for cle, valeur in
               _grouper(session, query, [colonne], indicateur).items()}

    libelles = {}
    if modele is not None:
        libelles = {m.id: m.nom for m in session.query(modele)}

    points = [{
        "libelle": (libelles.get(cle) if modele is not None else cle) or "Non renseigné",
        "cle": str(cle) if cle is not None else None,
        "valeur": valeurs.get(cle, 0),
    } for cle in valeurs]
    points.sort(key=lambda p: p["valeur"], reverse=True)
    return {"type": "repartition", "champ": champ, "points": points[:limite]}


def _repartition_par_dossier(session, query, indicateur: dict, limite: int) -> dict:
    """
    Groupe les documents par **dossier** plutôt que par type (§19.9).

    Un document appartient toujours à un type ; c'est le type qui vit dans un
    dossier. On remonte donc jusqu'au dossier le plus proche, et les types
    rangés à la racine forment leur propre groupe — les mettre dans « Non
    renseigné » laisserait croire à une erreur de classement là où il n'y en a
    pas.
    """
    parents = {c.id: c.parent_id for c in session.query(Categorie)}
    noms = {c.id: c.nom for c in session.query(Categorie)}

    def dossier_de(categorie_id):
        """Le dossier qui contient ce type, ou le type lui-même s'il est à la racine."""
        courant, garde = categorie_id, 0
        while courant is not None and parents.get(courant) and garde < 20:
            courant = parents[courant]
            garde += 1
        return courant

    groupes = {}
    for categorie_id, document_id in query.with_entities(Document.categorie_id, Document.id):
        groupes.setdefault(dossier_de(categorie_id), []).append(document_id)

    valeurs = _mesure(session, groupes, indicateur)
    points = [{
        "libelle": noms.get(cle) or "Non renseigné",
        "cle": str(cle) if cle is not None else None,
        "valeur": valeurs.get(cle, 0),
    } for cle in groupes]
    points.sort(key=lambda p: p["valeur"], reverse=True)
    return {"type": "repartition", "champ": "dossier", "points": points[:limite]}


def _repartition_metadonnee(session, query, ids, indicateur, champ, limite) -> dict:
    """
    Répartition sur une métadonnée.

    Deux choses que seul l'ancien groupement par émetteur savait faire, et que
    celui-ci a reprises quand l'émetteur est devenu une métadonnée (§21.12) :

      * **les valeurs adossées à une table se lisent** — « EDF », pas
        `usr_emetteurs:1`. Un graphique d'identifiants n'apprend rien ;
      * **ceux qui n'ont pas la valeur comptent aussi**, sous « Non renseigné ».
        Une répartition qui tait les documents sans émetteur flatte les données :
        on croit avoir tout classé.
    """
    from .filtres import _libelles_metadonnee

    cle_meta = champ[len(PREFIXE_META):]
    lignes = session.query(Metadonnee.valeur, Metadonnee.document_id).filter(
        Metadonnee.document_id.in_(ids), Metadonnee.cle == cle_meta,
        Metadonnee.valeur.isnot(None), Metadonnee.valeur != "",
    ).all()
    groupes = {}
    renseignes = set()
    for valeur, document_id in lignes:
        groupes.setdefault(valeur, []).append(document_id)
        renseignes.add(document_id)

    tous = [identifiant for (identifiant,) in query.with_entities(Document.id)]
    manquants = [identifiant for identifiant in tous if identifiant not in renseignes]
    if manquants:
        groupes[None] = manquants

    valeurs = _mesure(session, groupes, indicateur)
    libelles = _libelles_metadonnee(session, cle_meta,
                                    [c for c in groupes if c is not None])
    points = [{"libelle": (libelles.get(cle) or str(cle)) if cle is not None
                          else "Non renseigné",
               "cle": str(cle) if cle is not None else None,
               "valeur": valeurs.get(cle, 0)}
              for cle in groupes]
    points.sort(key=lambda p: p["valeur"], reverse=True)
    return {"type": "repartition", "champ": champ, "points": points[:limite]}


def _evolution(session: Session, query, ids, indicateur: dict) -> dict:
    """
    Série chronologique. Les périodes sans document apparaissent à zéro : une
    courbe trouée se lit mal, et l'absence de documents est une information.
    """
    granularite = indicateur.get("granularite", "mois")
    if granularite not in ("mois", "annee"):
        raise IndicateurInvalide("Granularité attendue : « mois » ou « annee ».")
    colonne = _colonne_date((indicateur.get("periode") or {}).get("champ"))

    # Le regroupement par période se fait en SQL : l'année et le mois sont
    # extraits par la base, qui ne rend qu'une ligne par période au lieu d'une
    # par document (§22.43).
    parties = ([func.year(colonne), func.month(colonne)] if granularite == "mois"
               else [func.year(colonne)])
    valeurs = {}
    for morceaux, valeur in _grouper(session, query.filter(colonne.isnot(None)),
                                     parties, indicateur).items():
        cle = (f"{int(morceaux[0]):04d}-{int(morceaux[1]):02d}" if granularite == "mois"
               else f"{int(morceaux[0]):04d}")
        valeurs[cle] = valeurs.get(cle, 0) + valeur

    debut, fin = bornes(indicateur.get("periode"))
    cles = _cles_periode(sorted(valeurs), debut, fin, granularite)
    return {
        "type": "evolution",
        "granularite": granularite,
        "points": [{"libelle": _libelle_periode(c, granularite), "cle": c,
                    "valeur": valeurs.get(c, 0)} for c in cles],
    }


def _cles_periode(presentes: list, debut, fin, granularite: str) -> list:
    """Suite continue de périodes, pour ne pas laisser de trous dans la série."""
    if not presentes and not (debut and fin):
        return []
    premier = debut or _depuis_cle(presentes[0], granularite)
    dernier = fin or _depuis_cle(presentes[-1], granularite)
    cles = []
    annee, mois = premier.year, premier.month
    while (annee, mois if granularite == "mois" else 12) <= (
            dernier.year, dernier.month if granularite == "mois" else 12):
        cles.append(f"{annee:04d}-{mois:02d}" if granularite == "mois" else f"{annee:04d}")
        if granularite == "mois":
            annee, mois = (annee + 1, 1) if mois == 12 else (annee, mois + 1)
        else:
            annee += 1
        if len(cles) > 240:  # garde-fou : 20 ans de mois
            break
    return cles


def _depuis_cle(cle: str, granularite: str) -> date:
    return date(int(cle[:4]), int(cle[5:7]) if granularite == "mois" else 1, 1)


MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin",
        "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def _libelle_periode(cle: str, granularite: str) -> str:
    if granularite == "annee":
        return cle
    return f"{MOIS[int(cle[5:7]) - 1]} {cle[2:4]}"


# ------------------------------------------------------------
# Tableau de bord d'accueil
# ------------------------------------------------------------

def tableau_accueil() -> dict:
    """
    Vue d'ensemble livrée d'emblée, sans configuration. Elle ne suppose aucune
    catégorie ni règle particulière : elle fonctionne sur une installation
    neuve comme sur un registre fourni.
    """
    return {
        "id": "accueil",
        "nom": "Accueil",
        "description": "Vue d'ensemble du registre.",
        "modifiable": False,
        "widgets": [
            {"id": "total", "type": "nombre", "titre": "Documents",
             "icone": "FileText", "lien": {}},
            {"id": "mois", "type": "nombre", "titre": "Ce mois-ci", "icone": "CalendarDays",
             "periode": {"champ": "date_import", "type": "mois_en_cours"}},
            # Compté sur la conformité réelle, comme le Centre d'analyse — et non
            # sur le statut `incomplet`, qui vieillit : une règle ajoutée après
            # coup rend des documents non conformes sans que le serveur de
            # travaux repasse changer leur statut.
            {"id": "a_reprendre", "type": "nombre", "titre": "À reprendre",
             "icone": "AlertTriangle", "accent": "amber", "portee": "incomplets",
             "lien": {"vers": "analyse"}},
            {"id": "non_classes", "type": "nombre", "titre": "Non classés",
             "icone": "FolderQuestion",
             "filtres": [{"champ": "categorie", "operateur": "vide"}],
             "lien": {"filtres": [{"champ": "categorie", "operateur": "vide"}]}},
            # La répartition par émetteur a été retirée de l'accueil : les émetteurs
            # sont une donnée du foyer, dont la liste n'éclaire pas la vue
            # d'ensemble du registre. Elle reste composable dans un tableau dédié.
            {"id": "par_categorie", "type": "repartition", "titre": "Par catégorie",
             "champ": "categorie", "largeur": 4},
            {"id": "arrivees", "type": "evolution", "titre": "Documents reçus",
             "granularite": "mois", "largeur": 4,
             "periode": {"champ": "date_import", "type": "12_derniers_mois"}},
        ],
    }
