"""
Modèles de configuration livrés avec l'application (§18.26).

Chaque foyer range à peu près les mêmes choses : des factures, des impôts, une
banque, une santé, un logement, parfois un véhicule. Repartir de zéro à chaque
installation serait faire retaper à chacun ce que tous ont en commun. Ces modèles
sont donc **posés d'emblée**, à charge pour l'administrateur de retirer ce qui ne
le concerne pas — plus facile que d'inventer ce qui manque.

Ils sont écrits dans le format d'export (`app/configuration.py`), et passent par
le même import : il n'existe qu'un seul chemin pour poser une configuration, ce
qui évite qu'un modèle marche là où un fichier échoue.

Les regex restent volontairement simples. Une expression trop savante attrape des
documents qu'elle ne devrait pas, et c'est plus difficile à défaire qu'un
classement manuel.
"""
import copy

# Ce que tout foyer possède, et qui sert de socle aux deux modèles.
_TABLES_PERSONNES = [
    {
        "nom_table": "usr_membres",
        "libelle": "Membres du foyer",
        "description": "Personnes auxquelles un document peut être rattaché. "
                       "Indépendantes des comptes de connexion.",
        "colonne_libelle": "nom",
        "colonnes_identifiantes": "prenom,nom",
        "colonnes": [{"nom": "nom", "type": "texte"},
                     {"nom": "prenom", "type": "texte"},
                     {"nom": "remarque", "type": "texte"}],
        "lignes": None,
    },
]

_REGLES_COMMUNES = [
    {"nom": "Numéro de facture (n° de facture : …)", "champ_cible": "numero_facture",
     "pattern": r"(?i)n[°o]\s*(?:de\s*)?facture\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/ ]{3,20})",
     "type_champ": "texte", "actif": True, "priorite": 10},
    {"nom": "Numéro de facture (facture n° …)", "champ_cible": "numero_facture",
     "pattern": r"(?i)facture\s*n[°o]\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/ ]{3,20})",
     "type_champ": "texte", "actif": True, "priorite": 20},
    {"nom": "Montant TTC (total TTC / à payer)", "champ_cible": "montant_ttc",
     "pattern": r"(?i)(?:total\s*ttc|montant\s*ttc|net\s*à\s*payer)\s*[:\-]?\s*([0-9][0-9\s.,]{0,12})",
     "type_champ": "montant", "actif": True, "priorite": 10},
    {"nom": "Montant TTC (total … €)", "champ_cible": "montant_ttc",
     "pattern": r"(?i)total\s*[:\-]?\s*([0-9][0-9\s.,]{0,12})\s*€",
     "type_champ": "montant", "actif": True, "priorite": 30},
    {"nom": "Date de facture (intitulée)", "champ_cible": "date_document",
     "pattern": r"(?i)date\s*(?:de\s*)?(?:facture|émission)?\s*[:\-]?\s*(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})",
     "type_champ": "date", "actif": True, "priorite": 10},
    {"nom": "Date du document (repli : première date trouvée)", "champ_cible": "date_document",
     "pattern": r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4})",
     "type_champ": "date", "actif": True, "priorite": 90},
    {"nom": "Numéro de client", "champ_cible": "numero_client",
     "pattern": r"(?i)n[°o]\s*(?:de\s*)?client\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/ ]{3,20})",
     "type_champ": "texte", "actif": True, "priorite": 20},
    {"nom": "IBAN", "champ_cible": "iban",
     "pattern": r"(?i)\b(FR\d{2}(?:[ ]?[A-Z0-9]{4}){5}[ ]?[A-Z0-9]{3})\b",
     "type_champ": "texte", "actif": True, "priorite": 30},
]

# Trois rôles d'exemple, du plus fermé au plus ouvert. Les droits par catégorie
# sont laissés vides : ils dépendent de l'arborescence de chaque foyer, et les
# cocher à sa place reviendrait à décider pour lui.
_ROLES_EXEMPLES = [
    {"nom": "Lecture seule",
     "description": "Consulte le registre, sans rien y changer.",
     "generaux": [], "vues": [], "categories": []},
    {"nom": "Dépôt et classement",
     "description": "Dépose, complète les fiches et suit les traitements. "
                    "Ne supprime rien et n'administre pas les comptes.",
     "generaux": ["analyser", "travaux"], "vues": [], "categories": []},
    {"nom": "Gestion complète",
     "description": "Tout le classement et les réglages, sans les comptes ni "
                    "l'export de l'archive.",
     "generaux": ["analyser", "travaux", "donnees", "vues_partagees",
                  "tableaux_partages", "reglages", "journal"],
     "vues": [], "categories": []},
]

_ESSENTIEL = {
    "format": 1,
    "categories": [
        {"nom": "Factures", "parent": None, "nature": "type", "ordre": 10},
        {"nom": "Impôts", "parent": None, "nature": "type", "ordre": 20},
        {"nom": "Banque", "parent": None, "nature": "type", "ordre": 30},
        {"nom": "Courriers", "parent": None, "nature": "type", "ordre": 90},
    ],
    # Un jeu générique par type de document (§19.6) : une règle appartient à un
    # jeu, et un jeu à un type. Écrit par report plutôt que recopié quatre fois —
    # une liste dupliquée finit toujours par diverger.
    "jeux_extraction": [
        {"categorie": nom, "nom": f"{nom} (générique)", "generique": True,
         "priorite": 1000, "regles": _REGLES_COMMUNES}
        for nom in ("Factures", "Impôts", "Banque", "Courriers")
    ],
    "champs_attendus": [
        # Le numéro identifie une facture : c'est lui qui reconnaît la même pièce
        # redéposée (§18.40). Facultatif — une facture dont l'OCR n'a pas su lire
        # le numéro reste une facture.
        {"categorie": "Factures", "champ": "meta:numero_facture", "libelle": "N° facture",
         "obligatoire": False, "identifiant": True, "ordre": 5,
         "source_table": None, "sources": None},
        {"categorie": "Factures", "champ": "meta:montant_ttc", "libelle": "Montant TTC",
         "obligatoire": True, "ordre": 10, "source_table": None, "sources": None},
        {"categorie": "Factures", "champ": "date_document", "libelle": None,
         "obligatoire": True, "ordre": 10, "source_table": None, "sources": None},
        {"categorie": "Factures", "champ": "meta:titulaire", "libelle": "Titulaire",
         "obligatoire": False, "ordre": 50,
         "source_table": "usr_membres", "sources": "usr_membres"},
    ],
    "colonnes": [
        {"categorie": "Factures", "champ": "meta:emetteur", "libelle": "Émetteur",
         "ordre": 0, "largeur": None, "visible": True},
        {"categorie": "Factures", "champ": "meta:numero_facture", "libelle": "N° facture",
         "ordre": 1, "largeur": None, "visible": True},
        {"categorie": "Factures", "champ": "date_document", "libelle": "Émise le",
         "ordre": 2, "largeur": None, "visible": True},
        {"categorie": "Factures", "champ": "meta:montant_ttc", "libelle": "Prix TTC",
         "ordre": 3, "largeur": None, "visible": True},
        {"categorie": "Factures", "champ": "meta:titulaire", "libelle": None,
         "ordre": 4, "largeur": None, "visible": True},
    ],
    "vues": [
        {"nom": "Toutes les factures sans titulaire", "categorie": "Factures",
         "criteres": [{"champ": "meta:titulaire", "operateur": "vide", "valeur": None}],
         "partagee": True, "ordre": 10},
    ],
    # Trois rôles d'exemple (§19.13), pour que personne ne parte d'une grille
    # vide : c'est en modifiant un rôle qui existe qu'on comprend ce que les six
    # actions veulent dire. Ils ne portent aucun droit de catégorie — celles-ci
    # dépendent de l'arborescence du foyer, et cocher à sa place serait décider
    # pour lui.
    "roles": _ROLES_EXEMPLES,
    "tableaux_de_bord": [],
    "tables_donnees": _TABLES_PERSONNES,
    "reglages": {},
}

# Le modèle complet reprend l'essentiel et l'étoffe. Écrit ainsi plutôt que
# recopié : deux listes de catégories qui divergent avec le temps sont deux fois
# plus de travail, et l'une des deux finit toujours par être fausse.
_COMPLET = copy.deepcopy(_ESSENTIEL)

# « Factures » cesse d'être une feuille : elle regroupe trois sortes de factures
# qui, elles, portent les documents (§19.1). Un dossier ne pouvant rien décrire,
# ce que « Factures » déclarait — colonnes et champs attendus — descend sur ses
# trois types. Écrit par report plutôt que recopié trois fois : une liste
# dupliquée finit toujours par diverger.
_SORTES_DE_FACTURES = ["Énergie", "Télécom", "Eau"]
for _entree in _COMPLET["categories"]:
    if _entree["nom"] == "Factures":
        _entree["nature"] = "dossier"

for _cle in ("champs_attendus", "colonnes"):
    _reportes = []
    for _entree in _COMPLET[_cle]:
        if _entree.get("categorie") != "Factures":
            _reportes.append(_entree)
            continue
        for _sorte in _SORTES_DE_FACTURES:
            _copie = dict(_entree)
            _copie["categorie"] = _sorte
            _reportes.append(_copie)
    _COMPLET[_cle] = _reportes

_COMPLET["categories"] += [
    {"nom": "Énergie", "parent": "Factures", "nature": "type", "ordre": 11},
    {"nom": "Télécom", "parent": "Factures", "nature": "type", "ordre": 12},
    {"nom": "Eau", "parent": "Factures", "nature": "type", "ordre": 13},
    {"nom": "Logement", "parent": None, "nature": "type", "ordre": 40},
    {"nom": "Santé", "parent": None, "nature": "type", "ordre": 50},
    {"nom": "Assurances", "parent": None, "nature": "type", "ordre": 55},
    {"nom": "Travail", "parent": None, "nature": "type", "ordre": 60},
    {"nom": "Véhicules", "parent": None, "nature": "type", "ordre": 70},
    {"nom": "Famille", "parent": None, "nature": "type", "ordre": 80},
]
_REGLES_VEHICULES = [
    {"nom": "Immatriculation (AA-123-AA)", "champ_cible": "immatriculation",
     "pattern": r"\b([A-Z]{2}-\d{3}-[A-Z]{2})\b", "type_champ": "texte",
     "actif": True, "priorite": 20},
    {"nom": "Période de paie", "champ_cible": "periode",
     "pattern": r"(?i)p[ée]riode\s*(?:du)?\s*[:\-]?\s*(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})",
     "type_champ": "date", "actif": True, "priorite": 30},
    {"nom": "Numéro de contrat", "champ_cible": "numero_contrat",
     "pattern": r"(?i)n[°o]\s*(?:de\s*)?contrat\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/ ]{3,20})",
     "type_champ": "texte", "actif": True, "priorite": 20},
]
# Le modèle complet a plus de types : chacun reçoit son jeu générique, et ceux
# qui lisent autre chose qu'une facture reçoivent en plus ce qui les concerne.
_SPECIFIQUES = {
    "Véhicules": [_REGLES_VEHICULES[0]],
    "Travail": [_REGLES_VEHICULES[1]],
    "Assurances": [_REGLES_VEHICULES[2]],
}
_COMPLET["jeux_extraction"] = [
    {"categorie": entree["nom"], "nom": f"{entree['nom']} (générique)",
     "generique": True, "priorite": 1000,
     "regles": _REGLES_COMMUNES + _SPECIFIQUES.get(entree["nom"], [])}
    for entree in _COMPLET["categories"] if entree.get("nature", "type") == "type"
]

_COMPLET["champs_attendus"] += [
    {"categorie": "Travail", "champ": "meta:titulaire", "libelle": "Titulaire",
     "obligatoire": False, "ordre": 10, "source_table": "usr_membres", "sources": "usr_membres"},
    {"categorie": "Santé", "champ": "meta:titulaire", "libelle": "Titulaire",
     "obligatoire": False, "ordre": 10, "source_table": "usr_membres", "sources": "usr_membres"},
    {"categorie": "Véhicules", "champ": "meta:vehicule", "libelle": "Véhicule concerné",
     "obligatoire": False, "ordre": 10,
     "source_table": "usr_vehicules", "sources": "usr_vehicules"},
    {"categorie": "Assurances", "champ": "meta:numero_contrat", "libelle": "N° de contrat",
     "obligatoire": False, "ordre": 10, "source_table": None, "sources": None},
]
_COMPLET["tables_donnees"] = _TABLES_PERSONNES + [
    {
        "nom_table": "usr_vehicules",
        "libelle": "Véhicules",
        "description": "Les véhicules du foyer, pour y rattacher assurances, entretiens "
                       "et contraventions.",
        "colonne_libelle": "marque",
        "colonnes_identifiantes": "marque,immatriculation",
        "colonnes": [{"nom": "marque", "type": "texte"}, {"nom": "modele", "type": "texte"},
                     {"nom": "immatriculation", "type": "texte"},
                     {"nom": "mise_en_circulation", "type": "date"},
                     {"nom": "proprietaire", "type": "texte"}],
        "lignes": None,
    },
    {
        "nom_table": "usr_contrats",
        "libelle": "Contrats et abonnements",
        "description": "Assurances, mutuelle, énergie, télécom : de quoi retrouver un "
                       "numéro de contrat sans ouvrir le document.",
        "colonne_libelle": "libelle",
        "colonnes_identifiantes": "libelle,numero",
        "colonnes": [{"nom": "libelle", "type": "texte"}, {"nom": "organisme", "type": "texte"},
                     {"nom": "numero", "type": "texte"},
                     {"nom": "date_souscription", "type": "date"},
                     {"nom": "remarque", "type": "texte"}],
        "lignes": None,
    },
    {
        "nom_table": "usr_biens",
        "libelle": "Logements et biens",
        "description": "Résidence, garage, terrain : ce à quoi rattacher un bail, une "
                       "taxe foncière ou des travaux.",
        "colonne_libelle": "libelle",
        "colonnes_identifiantes": "libelle,adresse",
        "colonnes": [{"nom": "libelle", "type": "texte"}, {"nom": "adresse", "type": "texte"},
                     {"nom": "nature", "type": "texte"}, {"nom": "remarque", "type": "texte"}],
        "lignes": None,
    },
]
_COMPLET["vues"] += [
    {"nom": "Documents de l'année", "categorie": None,
     "criteres": [{"champ": "date_document", "operateur": "apres", "valeur": "2026-01-01"}],
     "partagee": True, "ordre": 20},
]

MODELES = {
    "essentiel": {
        "libelle": "L'essentiel",
        "description": "Quatre catégories — factures, impôts, banque, courriers — les règles "
                       "de lecture d'une facture française, et les membres du foyer. De quoi "
                       "commencer sans rien avoir à retirer.",
        "configuration": _ESSENTIEL,
    },
    "complet": {
        "libelle": "Foyer complet",
        "description": "L'essentiel, plus le logement, la santé, les assurances, le travail, "
                       "les véhicules et la famille — avec les tables qui vont avec. Prévu "
                       "pour être élagué : retirer une catégorie inutile prend dix secondes, "
                       "en inventer une manquante prend dix minutes.",
        "configuration": _COMPLET,
    },
}


def lister() -> list[dict]:
    """Les modèles disponibles, avec de quoi les présenter — sans leur contenu."""
    return [{
        "cle": cle,
        "libelle": modele["libelle"],
        "description": modele["description"],
        "categories": len(modele["configuration"]["categories"]),
        "regles": sum(len(j.get("regles") or [])
                      for j in modele["configuration"]["jeux_extraction"]),
        "tables": len(modele["configuration"]["tables_donnees"]),
    } for cle, modele in MODELES.items()]


def charger(cle: str) -> dict:
    """Configuration d'un modèle. Copie profonde : l'import ne doit pas l'altérer."""
    return copy.deepcopy(MODELES[cle]["configuration"])
