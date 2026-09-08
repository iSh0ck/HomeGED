"""
Colonnes du tableau, propres à chaque catégorie (§18.1).

Un registre unique force toutes les catégories dans le même moule : quatre
colonnes qui conviennent à peu près à tout et bien à rien. Une facture se lit en
une ligne — émetteur, numéro, date d'émission, montant, titulaire — et pas une
de ces colonnes n'a de sens pour un courrier.

**Le tableau d'une catégorie est utilisable sans configuration.** Les colonnes
sont déduites de ce que la catégorie déclare (ses champs attendus) et de ce que
ses documents portent réellement. `sys_colonnes_categorie` ne sert qu'à corriger
cette déduction : retirer une colonne parasite, réordonner, renommer. Rien à
régler pour que ça marche, tout à régler si l'on veut.

Le vocabulaire des champs est celui du moteur de filtres (`app/filtres.py`) :
`date_document`, `meta:<cle>`, `lien:<table>`. Une colonne est donc filtrable et
triable sans une ligne de code de plus.
"""
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .db import (
    Categorie,
    ColonneCategorie,
    Document,
    Metadonnee,
    ProfilExtraction,
    RegleChampCategorie,
    RegleExtraction,
    ids_categorie_et_descendants,
)

PREFIXE_META = "meta:"
PREFIXE_LIEN = "lien:"    # « tout ce qui concerne cette chose-là » (§22)

# Colonnes du registre sans catégorie sélectionnée : on ne peut alors rien
# supposer des documents affichés, sinon ce que tout document possède.
#
# Le statut n'y figure plus (§18.9) : le registre écarte déjà les documents
# incomplets, et ceux qu'il montre sont traités dans leur immense majorité — une
# colonne qui répète « Traité » sur chaque ligne n'apprend rien. Il reste
# proposé à la configuration pour qui veut suivre les traitements de près, et le
# Centre d'analyse comme le serveur de travaux disent ce qui ne va pas.
DEFAUT = ["categorie", "date_document"]

# Au-delà, un tableau déduit devient illisible et lent à parcourir. Les
# métadonnées retenues sont les plus répandues dans la catégorie : celles que
# l'on a le plus de chances de vouloir lire.
MAX_METADONNEES_DEDUITES = 6

# Intitulés des champs du document. Une métadonnée, elle, tire son intitulé de
# la règle de la catégorie, à défaut de quoi sa clé est mise en forme.
LIBELLES = {
    "categorie": "Catégorie",
    "date_document": "Date",
    "date_import": "Déposé le",
    "statut": "Statut",
    "nom_fichier": "Fichier",
}

# Contrôle de recherche affiché sous l'en-tête (cf. ColumnFilter.jsx).
FILTRES = {
    "categorie": "reference",
    "date_document": "date",
    "date_import": "date",
    "statut": "statut",
}

SOURCES_REFERENCE = {"categorie": "categories"}


def _libelle_par_defaut(champ: str) -> str:
    """
    Intitulé tiré de la clé, faute de mieux. « numero_facture » donne « N°
    facture » et non « Numero facture » : un en-tête de colonne est lu cent fois,
    il vaut la peine d'être écrit correctement.
    """
    if champ in LIBELLES:
        return LIBELLES[champ]
    cle = champ[len(PREFIXE_META):] if champ.startswith(PREFIXE_META) else champ
    texte = cle.replace("_", " ")
    if texte.startswith("numero "):
        return "N° " + texte[len("numero "):]
    return texte.capitalize()


# Quelles clés de métadonnée vivent dans quelle catégorie, gardées entre deux
# écritures (§22.43).
#
# Cette question demande de croiser **tous** les documents avec **toutes** leurs
# métadonnées : 181 ms sur vingt mille documents, et elle est posée à chaque
# chargement du registre, uniquement pour savoir quelles colonnes proposer.
#
# Le repère n'est pas une durée mais **le dernier identifiant de métadonnée** :
# une clé n'apparaît que par une ligne écrite, et cette ligne porte forcément un
# identifiant plus grand. Un `MAX(id)` est une lecture d'index — instantanée — et
# elle vaut pour tous les processus : ce que le serveur de travaux vient
# d'indexer invalide le cache de l'API sans qu'ils aient à se parler. Reste le
# cas d'une clé qui **disparaît** partout : le cache la proposerait encore
# jusqu'à la prochaine écriture, ce qui ne coûte qu'une colonne vide.
_cles_caches: dict = {"repere": None, "valeur": {}}


def oublier_les_cles() -> None:
    """Le cache ne doit pas survivre à un changement qu'on vient de faire."""
    _cles_caches.update(repere=None, valeur={})


def _cles_par_categorie(session: Session) -> dict:
    repere = session.query(func.max(Metadonnee.id)).scalar()
    if _cles_caches["repere"] is not None and _cles_caches["repere"] == repere:
        return _cles_caches["valeur"]
    trouvees: dict = {}
    lignes = (
        session.query(Document.categorie_id, Metadonnee.cle,
                      func.count(Metadonnee.id).label("n"))
        .join(Metadonnee, Metadonnee.document_id == Document.id)
        .filter(Document.categorie_id.isnot(None),
                Metadonnee.valeur.isnot(None), Metadonnee.valeur != "")
        .group_by(Document.categorie_id, Metadonnee.cle)
        .all()
    )
    for categorie_id, cle, nombre in lignes:
        trouvees.setdefault(categorie_id, {})[cle] = nombre
    _cles_caches.update(repere=repere, valeur=trouvees)
    return trouvees


class _Contexte:
    """
    Les lectures communes à toutes les catégories, faites une fois (§18.56).

    `toutes()` décrivait chaque catégorie de façon indépendante : types des
    métadonnées, intitulés déclarés ailleurs, colonnes configurées, champs
    attendus — tout était relu pour chacune. Mesuré sur cinq catégories : **49
    requêtes et 184 ms** à chaque chargement du registre, et cela croît
    linéairement avec l'arborescence.

    Rien de tout cela ne dépend de la catégorie : ce sont des tables entières,
    qu'on lit une fois et qu'on interroge ensuite en mémoire. Les mêmes
    fonctions servent pour une catégorie seule — sans contexte, elles lisent
    comme avant, ce qui garde `pour_categorie` utilisable tel quel.
    """

    def __init__(self, session: Session):
        self.types = _types_metadonnees(session)
        self.libelles_declares = {
            regle.champ: regle.libelle
            for regle in session.query(RegleChampCategorie).filter(
                RegleChampCategorie.libelle.isnot(None))
        }
        self.regles = {}
        for regle in (session.query(RegleChampCategorie)
                      .order_by(RegleChampCategorie.ordre, RegleChampCategorie.champ)):
            self.regles.setdefault(regle.categorie_id, []).append(regle)
        self.configurees = {}
        for ligne in (session.query(ColonneCategorie)
                      .order_by(ColonneCategorie.ordre, ColonneCategorie.id)):
            self.configurees.setdefault(ligne.categorie_id, []).append(ligne)
        self.categories = {c.id: c for c in session.query(Categorie)}
        self.metadonnees = _cles_par_categorie(session)

    def descendants(self, categorie_id: int) -> set:
        """La catégorie et tout ce qui pend en dessous, sans requête."""
        retenus, a_voir = set(), [categorie_id]
        while a_voir:
            courant = a_voir.pop()
            if courant in retenus:
                continue
            retenus.add(courant)
            a_voir += [c.id for c in self.categories.values() if c.parent_id == courant]
        return retenus

    def cles_metadonnees(self, categorie_id: int) -> list[str]:
        """Clés présentes dans la catégorie et ses descendants, les plus répandues d'abord."""
        totaux = {}
        for identifiant in self.descendants(categorie_id):
            for cle, nombre in self.metadonnees.get(identifiant, {}).items():
                totaux[cle] = totaux.get(cle, 0) + nombre
        return [cle for cle, _ in sorted(totaux.items(), key=lambda x: (-x[1], x[0]))]

def _types_metadonnees(session: Session) -> dict:
    """
    Type déclaré par les règles d'extraction, par clé. Il décide de la mise en
    forme de la valeur et du contrôle de recherche : un montant s'écrit « 50,99 »,
    une date veut un calendrier. Une clé visée par deux règles de types différents
    est laissée en texte — le désaccord ne se tranche pas ici.

    Il ne décide en revanche plus de l'alignement : toutes les colonnes sont
    alignées à gauche (§18.15). Une exception décale l'intitulé de son champ de
    recherche et de ses valeurs, et l'œil qui descend la colonne perd son repère.
    """
    types: dict[str, Optional[str]] = {}
    for regle in session.query(RegleExtraction).all():
        cible = regle.champ_cible
        if cible in types and types[cible] != regle.type_champ:
            types[cible] = "texte"
        else:
            types.setdefault(cible, regle.type_champ)
    return types


def _decrire(champ: str, libelle: Optional[str], types: dict, largeur=None) -> dict:
    """Description d'une colonne, telle que l'interface l'attend."""
    cle = champ[len(PREFIXE_META):] if champ.startswith(PREFIXE_META) else None
    type_champ = types.get(cle) if cle else None

    filtre = FILTRES.get(champ) or ("date" if type_champ == "date" else "texte")
    colonne = {
        "champ": champ,
        "libelle": libelle or _libelle_par_defaut(champ),
        "filtre": filtre,
        "type": type_champ or ("date" if champ.startswith("date") else "texte"),
    }
    if champ in SOURCES_REFERENCE:
        colonne["source"] = SOURCES_REFERENCE[champ]
    if largeur:
        colonne["largeur"] = largeur
    return colonne


def _champs_deduits(session: Session, categorie_id: int,
                    contexte: Optional["_Contexte"] = None) -> list[tuple[str, Optional[str]]]:
    """
    Colonnes déduites d'une catégorie : `(champ, libellé de la règle)`.

    L'émetteur d'abord — c'est par lui qu'on reconnaît un document —, puis les
    champs que la catégorie déclare attendre, dans leur ordre de saisie : c'est
    l'ordre dans lequel l'utilisateur les a lui-même pensés. Viennent ensuite les
    métadonnées effectivement extraites que les règles ne mentionnent pas (un
    numéro de facture est extrait sans être exigé, et c'est pourtant ce qu'on
    cherche des yeux en premier).
    """
    champs: list[tuple[str, Optional[str]]] = []
    vus: set = set()

    regles = contexte.regles.get(categorie_id, []) if contexte else (
        session.query(RegleChampCategorie)
        .filter(RegleChampCategorie.categorie_id == categorie_id)
        .order_by(RegleChampCategorie.ordre, RegleChampCategorie.champ)
        .all()
    )
    for regle in regles:
        if regle.champ not in vus:
            champs.append((regle.champ, regle.libelle))
            vus.add(regle.champ)

    if "date_document" not in vus:
        champs.append(("date_document", None))
        vus.add("date_document")

    # Métadonnées réellement présentes sur les documents de la catégorie et de
    # ses sous-catégories, les plus répandues d'abord.
    if contexte:
        presentes = contexte.cles_metadonnees(categorie_id)
    else:
        ids = ids_categorie_et_descendants(session, categorie_id)
        presentes = [
            cle for cle, _ in
            session.query(Metadonnee.cle, func.count(Metadonnee.id).label("n"))
            .join(Document, Document.id == Metadonnee.document_id)
            .filter(Document.categorie_id.in_(ids),
                    Metadonnee.valeur.isnot(None), Metadonnee.valeur != "")
            .group_by(Metadonnee.cle)
            .order_by(func.count(Metadonnee.id).desc(), Metadonnee.cle)
            .all()
        ]
    # Intitulés déclarés ailleurs : « Montant TTC » a été nommé une fois, sur la
    # catégorie qui l'exige. Une catégorie parente qui affiche la même donnée
    # n'a pas à la renommer, ni à la montrer sous sa clé technique.
    ailleurs = contexte.libelles_declares if contexte else {
        regle.champ: regle.libelle
        for regle in session.query(RegleChampCategorie).filter(
            RegleChampCategorie.libelle.isnot(None))
    }

    reste = MAX_METADONNEES_DEDUITES
    for cle in presentes:
        champ = f"{PREFIXE_META}{cle}"
        # `date_document` est aussi une clé de métadonnée chez certaines règles
        # d'extraction : la colonne du document existe déjà, ne pas la doubler.
        if champ in vus or cle in vus or reste <= 0:
            continue
        champs.append((champ, ailleurs.get(champ)))
        vus.add(champ)
        reste -= 1

    return champs


# L'héritage entre catégories a été retiré au §19.7. Il servait quand une
# catégorie pouvait à la fois porter des documents et en contenir d'autres : une
# sous-catégorie reprenait alors les colonnes de son parent. Depuis le §19.1, un
# parent est un **dossier** — il ne porte aucun document, donc aucune colonne, et
# n'avait plus rien à transmettre. Une action explicite le remplace : « appliquer
# ces colonnes à tous les types de ce dossier ». Un réglage qu'on déclenche vaut
# mieux qu'un héritage qu'on subit ; le second se découvre au mauvais moment.


def pour_categorie(session: Session, categorie_id: Optional[int],
                   contexte: Optional["_Contexte"] = None) -> list[dict]:
    """
    Colonnes à afficher pour un type de document. Sans catégorie, le jeu par défaut.

    Un type sans configuration propre affiche des colonnes **déduites** de ce
    qu'il déclare attendre et de ce que ses documents portent : le tableau est
    utilisable sans rien régler. Il n'hérite de rien (§19.7) — son parent est un
    dossier, qui ne porte aucune colonne.
    """
    types = contexte.types if contexte else _types_metadonnees(session)
    if categorie_id is None:
        return [_decrire(champ, None, types) for champ in DEFAUT]

    lignes = contexte.configurees.get(categorie_id, []) if contexte else (
        session.query(ColonneCategorie)
        .filter(ColonneCategorie.categorie_id == categorie_id)
        .order_by(ColonneCategorie.ordre, ColonneCategorie.id)
        .all()
    )
    reglages = {ligne.champ: ligne for ligne in lignes}

    # Une seule déduction : elle sert aux intitulés, puis à compléter la
    # configuration. La calculer deux fois doublait le travail pour rien.
    champs_deduits = _champs_deduits(session, categorie_id, contexte)
    deduits = dict(champs_deduits)

    colonnes, places = [], set()
    for champ, ligne in reglages.items():
        places.add(champ)
        if not ligne.visible:
            continue
        colonnes.append(_decrire(champ, ligne.libelle or deduits.get(champ), types, ligne.largeur))

    # Une configuration est un choix : on n'y ajoute pas d'office toutes les
    # métadonnées trouvées dans les documents, sinon la colonne écartée hier
    # reviendrait demain. Seul un **champ attendu déclaré par la catégorie**
    # s'invite — une exigence ajoutée après coup doit se voir, faute de quoi on
    # ne saurait pas quels documents lui manquent. L'administrateur peut la
    # masquer à son tour.
    if reglages:
        regles = contexte.regles.get(categorie_id, []) if contexte else (
            session.query(RegleChampCategorie)
            .filter(RegleChampCategorie.categorie_id == categorie_id)
            .order_by(RegleChampCategorie.ordre, RegleChampCategorie.champ)
        )
        declares = [regle.champ for regle in regles]
        for champ in declares:
            if champ not in places:
                colonnes.append(_decrire(champ, deduits.get(champ), types))
    else:
        for champ, libelle in champs_deduits:
            if champ not in places:
                colonnes.append(_decrire(champ, libelle, types))

    if not colonnes:
        # Tout masquer laisserait un tableau sans une seule colonne, donc sans
        # rien à lire ni à cliquer. Le jeu par défaut vaut mieux que le vide.
        return [_decrire(champ, None, types) for champ in DEFAUT]

    return colonnes


def tri_pour(session: Session, categorie_id: Optional[int], categories=None,
             defaut: Optional[dict] = None) -> dict:
    """
    Tri d'ouverture du registre pour une catégorie (§18.49) : `{champ, sens}`.

    Le type d'abord, le réglage général du foyer à défaut. Plus d'héritage depuis
    le §19.7 : un dossier ne porte pas de tri, il n'avait donc rien à transmettre
    — la remontée ne trouvait jamais rien et faisait croire à une règle qui
    n'existait pas.
    """
    from . import reglages

    if categorie_id is not None:
        connues = categories if categories is not None else {
            c.id: c for c in session.query(Categorie).all()}
        vue = connues.get(categorie_id)
        if vue is not None and vue.tri_champ:
            return {"champ": vue.tri_champ, "sens": vue.tri_sens or "asc"}

    # `defaut` est fourni par l'appel groupé : sans lui, ces deux réglages
    # étaient relus pour chaque catégorie.
    return defaut or {"champ": reglages.lire(session, "tri_defaut_champ") or "date_import",
                      "sens": reglages.lire(session, "tri_defaut_sens") or "desc"}


def toutes(session: Session) -> dict:
    """
    Colonnes et tri d'ouverture de chaque catégorie, en une seule réponse :
    l'interface change de catégorie sans aller-retour réseau, et sans
    clignotement du tableau.
    """
    contexte = _Contexte(session)
    tri_du_foyer = tri_pour(session, None)
    colonnes = {"defaut": pour_categorie(session, None, contexte)}
    tris = {"defaut": tri_du_foyer}
    for identifiant in contexte.categories:
        colonnes[str(identifiant)] = pour_categorie(session, identifiant, contexte)
        tris[str(identifiant)] = tri_pour(session, identifiant, contexte.categories, tri_du_foyer)
    return {"colonnes": colonnes, "tris": tris}


# D'où vient un champ proposé (§21.13). La liste mélangeait sans le dire ce que
# l'application tient elle-même, ce que le type déclare attendre, et ce que les
# règles ont fini par écrire dans les documents. Trois origines, trois façons de
# les changer : les nommer évite de chercher longtemps pourquoi tel champ existe.
ORIGINE_SYSTEME = "systeme"
ORIGINE_ATTENDU = "attendu"
ORIGINE_EXTRAIT = "extrait"
ORIGINE_LIAISON = "liaison"

ORIGINES = {
    ORIGINE_SYSTEME: "Tenus par l'application",
    ORIGINE_ATTENDU: "Champs attendus de ce type",
    ORIGINE_EXTRAIT: "Extraits des documents",
    ORIGINE_LIAISON: "Ce que le document concerne",
}

# Les champs que l'application tient elle-même, dits comme on les lit dans un
# tableau — et non comme la base les nomme.
LIBELLES_SYSTEME = {
    "categorie": "Classement (type de document)",
    "date_document": "Date du document",
    "date_import": "Date d'entrée au registre",
    "statut": "État du traitement",
    "nom_fichier": "Nom du fichier d'origine",
}


def _vocabulaire_du_type(session: Session, categorie_id: int) -> set[str]:
    """
    Ce que **ce type** a nommé, ou porte pour de bon (§22.57).

    Quatre provenances, et chacune répond à un moment différent :

      * ses **champs attendus** — ce qu'un administrateur a déclaré ;
      * ses **colonnes déjà réglées** — sans quoi une colonne configurée hier
        disparaîtrait de la liste, et l'on ne pourrait plus la renommer ;
      * les cibles de **ses règles d'extraction**, jeux génériques compris : une
        règle écrite qui n'a encore rien reconnu doit pouvoir devenir une colonne
        sans attendre qu'un document la déclenche ;
      * les **métadonnées réellement portées** par ses documents et ceux de ses
        sous-catégories — ce qui existe, même si rien ne l'a déclaré.

    Sans compter les tables que ses champs désignent : « tout ce qui concerne ce
    véhicule » n'a de sens que sur un type qui parle de véhicules.
    """
    retenus: set[str] = set()
    tables: set[str] = set()

    for regle in (session.query(RegleChampCategorie)
                  .filter(RegleChampCategorie.categorie_id == categorie_id)):
        retenus.add(regle.champ)
        if regle.source_table:
            tables.add(regle.source_table)

    for colonne in (session.query(ColonneCategorie)
                    .filter(ColonneCategorie.categorie_id == categorie_id)):
        retenus.add(colonne.champ)

    cibles = (session.query(RegleExtraction.champ_cible)
              .join(ProfilExtraction, RegleExtraction.profil_id == ProfilExtraction.id)
              .filter(or_(ProfilExtraction.categorie_id == categorie_id,
                          ProfilExtraction.categorie_id.is_(None)))
              .distinct())
    for (cible,) in cibles:
        if not cible:
            continue
        # `date_document` n'est pas une métadonnée mais la date du document
        # elle-même : c'est le seul nom que le moteur traite à part.
        retenus.add(cible if cible == "date_document" else f"{PREFIXE_META}{cible}")

    ids = ids_categorie_et_descendants(session, categorie_id)
    presentes = (session.query(Metadonnee.cle)
                 .join(Document, Document.id == Metadonnee.document_id)
                 .filter(Document.categorie_id.in_(ids),
                         Metadonnee.valeur.isnot(None), Metadonnee.valeur != "")
                 .distinct())
    for (cle,) in presentes:
        if cle:
            retenus.add(f"{PREFIXE_META}{cle}")

    retenus |= {f"{PREFIXE_LIEN}{table}" for table in tables}
    return retenus


def champs_proposables(session: Session, categorie_id: Optional[int] = None) -> list[dict]:
    """
    Champs qu'un administrateur peut ajouter comme colonne, avec leur intitulé et
    **d'où ils viennent**.

    On part des champs filtrables du moteur — tout ce qui peut être filtré peut
    être affiché — plutôt que d'une liste tenue à part, qui divergerait. Chacun
    est rangé dans son origine : ce que l'application tient, ce que ce type
    déclare attendre, ce que les règles ont écrit, et les choses que le document
    désigne. Sans cela, la liste juxtaposait des champs qu'on ne change pas au
    même endroit, sans dire lequel était lequel.
    """
    from . import filtres as moteur

    attendus = {}
    if categorie_id is not None:
        attendus = {
            regle.champ: regle.libelle
            for regle in session.query(RegleChampCategorie)
                .filter(RegleChampCategorie.categorie_id == categorie_id)
        }

    proposables = []
    for champ in moteur.champs_disponibles(session):
        cle = champ["champ"]
        # `texte` est la recherche plein texte : elle n'a pas de valeur à
        # afficher dans une cellule.
        if cle == "texte":
            continue
        if cle.startswith(moteur.PREFIXE_LIEN):
            origine = ORIGINE_LIAISON
        elif cle in attendus:
            origine = ORIGINE_ATTENDU
        elif cle.startswith(moteur.PREFIXE_META):
            origine = ORIGINE_EXTRAIT
        else:
            origine = ORIGINE_SYSTEME
        proposables.append({
            "champ": cle,
            "libelle": (attendus.get(cle) or LIBELLES_SYSTEME.get(cle)
                        or LIBELLES.get(cle) or champ["libelle"]),
            "origine": origine,
            "libelle_origine": ORIGINES[origine],
        })
    if categorie_id is not None:
        retenus = _vocabulaire_du_type(session, categorie_id)
        proposables = [c for c in proposables
                       if c["origine"] == ORIGINE_SYSTEME or c["champ"] in retenus]

    # Les champs du système en tête : ce sont les mêmes partout, et l'on sait où
    # les trouver. Le reste par origine, puis par intitulé.
    ordre = {ORIGINE_SYSTEME: 0, ORIGINE_ATTENDU: 1, ORIGINE_EXTRAIT: 2, ORIGINE_LIAISON: 3}
    proposables.sort(key=lambda c: (ordre[c["origine"]], c["libelle"].lower()))
    return proposables
