"""
Fonctions d'extraction prêtes à l'emploi (§18.35).

Écrire une expression régulière pour attraper une date ou un montant est le
passage obligé du projet, et le plus ingrat : chaque foyer réécrit les mêmes
motifs, avec les mêmes oublis — l'année sur deux chiffres, l'espace insécable
des milliers, la virgule décimale, le « € » collé au nombre.

Deux familles, et la distinction compte :

* les **extracteurs** (`premiere_date`, `montant_ttc`) portent leur propre
  recherche : ils se passent d'expression. Donnez-leur une expression tout de
  même, et ils travailleront sur ce qu'elle a trouvé — utile pour restreindre la
  zone du document ;
* les **transformateurs** (`chiffres_seuls`, `sans_espaces`) ne cherchent rien :
  ils nettoient ce qu'une expression a trouvé.

Certaines fonctions demandent en plus un **paramètre** (§21.4) : le nombre de
jours d'une échéance, le séparateur d'une concaténation. Sans lui, il aurait
fallu une fonction par valeur possible — « +30 jours », « +45 jours »… —,
c'est-à-dire coder en dur ce qui doit se régler.

Chacune est écrite pour ce que produit un OCR, pas pour du texte propre : les
espaces insécables, le « O » pris pour un zéro dans les milliers, les points
décimaux à la place des virgules.
"""
import re
from datetime import datetime
from typing import Optional

# Séparateurs de milliers rencontrés en sortie d'OCR : espace ordinaire,
# insécable, fine insécable, apostrophe (usage suisse).
ESPACES = "    '"

# Au-delà, ce n'est plus un montant mais un numéro : un SIRET, un numéro de TVA,
# une référence client. Une facture de foyer n'atteint pas le milliard.
PLAFOND_MONTANT = 1_000_000_000
# Et sans centimes, la barre est bien plus basse : un nombre nu à sept chiffres
# est un numéro de commande, pas le total d'une facture de foyer.
PLAFOND_SANS_DECIMALES = 1_000_000

_MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}

_DATE_NUMERIQUE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_LETTRES = re.compile(
    r"\b(\d{1,2})\s+([a-zéèêûôîç]+)\s+(\d{4})\b", re.IGNORECASE)

_MONTANT = re.compile(rf"(\d[\d{ESPACES}]*(?:[.,]\d{{1,2}})?)")
# Les intitulés vont du plus sûr au plus faible, et le premier qui rend quelque
# chose l'emporte. Sur une facture, « Total TTC » fait foi ; « TOTAL » tout court
# aussi, mais seulement si rien de mieux n'a parlé — c'est aussi l'en-tête d'une
# colonne. L'ordre est la seule façon de s'en sortir sans deviner.
_INTITULES_TTC = [
    re.compile(r"(?i)\b(?:total\s*t\.?t\.?c|montant\s*t\.?t\.?c|net\s*[àa]\s*payer|"
               r"total\s*[àa]\s*payer|montant\s*d[ûu]|total\s*g[ée]n[ée]ral)"),
    re.compile(r"(?i)\btotal\b(?!\s*(?:h\.?t|hors))"),
]

_INTITULES_HT = [
    re.compile(r"(?i)\b(?:total\s*h\.?t\.?|total\s*hors\s*taxes?)"),
    # « Montant HT » est souvent un **en-tête de colonne** : le nombre qui suit
    # est le premier prix de la ligne, pas le total. On ne s'en sert qu'à défaut.
    re.compile(r"(?i)\b(?:montant\s*h\.?t\.?|base\s*h\.?t\.?|montant\s*hors\s*taxes?)"),
]

_INTITULE_TVA = re.compile(
    r"(?i)\b(?:(?:montant|total)\s*(?:de\s*(?:la\s*)?)?t\.?v\.?a\.?|"
    r"dont\s*t\.?v\.?a\.?|t\.?v\.?a\.?\s*(?:\d{1,2}[.,]?\d*\s*%)?)"
    r"(?!\s*intracom)")
_INTITULE_ECHEANCE = re.compile(
    r"(?i)\b(?:date\s*(?:limite|d.)?\s*(?:de\s*)?(?:paiement|r[ée]glement)|"
    r"[ée]ch[ée]ance|[àa]\s*payer\s*avant|payable\s*avant|"
    r"date\s*de\s*pr[ée]l[èe]vement)")

# SIREN : 9 chiffres, SIRET : 14. L'OCR sème des espaces, on les tolère.
_SIREN = re.compile(r"(?i)(?:siren|siret|n°?\s*siret)\D{0,10}((?:\d[  .]?){9,14})")
_SIREN_NU = re.compile(r"\b(\d{3}[  .]?\d{3}[  .]?\d{3}(?:[  .]?\d{5})?)\b")
# TVA intracommunautaire : un **code pays réel**, puis 2 à 13 caractères. Sans la
# liste, « uniforme en bleu 15.00 » donnait « BLEU15 » — deux lettres et des
# chiffres suffisent à faire illusion, et il y en a partout dans une facture.
_PAYS_TVA = ("AT BE BG CY CZ DE DK EE EL ES FI FR GB HR HU IE IT LT LU LV MT NL "
             "PL PT RO SE SI SK XI")
_TVA_INTRA = re.compile(
    rf"\b((?:{'|'.join(_PAYS_TVA.split())})\s?[0-9A-Z]{{2}}\s?[0-9]{{2,11}})\b")
_IBAN = re.compile(r"\b([A-Z]{2}\s?\d{2}(?:\s?[0-9A-Z]{4}){2,7}\s?[0-9A-Z]{1,4})\b")
_TELEPHONE = re.compile(r"(?<!\d)((?:\+33|0)\s?[1-9](?:[  .-]?\d{2}){4})(?!\d)")


def _montant_annonce(texte: str, intitule) -> Optional[str]:
    """
    Le montant qui suit un intitulé, s'il y en a un. Même méthode que le TTC, à
    une réserve près : **un taux n'est pas un montant**. « TVA 20 % : 205,76 »
    annonce d'abord le taux, et prendre le premier nombre venu rendait 20,00 €
    de TVA sur une facture de 1 234 € — une valeur fausse qui ne se voit pas.
    """
    for trouve in intitule.finditer(texte or ""):
        fenetre = (texte or "")[trouve.end(): trouve.end() + 40]
        candidats = []
        for montant in _MONTANT.finditer(fenetre):
            suite = fenetre[montant.end(): montant.end() + 2].lstrip()
            if suite.startswith("%"):
                continue           # un taux n'est pas un montant
            valeur = _nombre(montant.group(1))
            # Un numéro pris pour un montant : une facture de foyer ne se compte
            # pas en milliards, mais un identifiant à onze chiffres, si.
            if valeur is None or abs(float(valeur)) >= PLAFOND_MONTANT:
                continue
            candidats.append((("." in montant.group(1) or "," in montant.group(1)), valeur))
        if not candidats:
            continue
        # Un montant à centimes l'emporte sur un entier nu : dans « MONTANT HT
        # 1 Grand brun escargot 100.00 », le « 1 » est une quantité, pas un prix.
        # Les tableaux de facture mêlent les deux dans la même ligne.
        avec_decimales = [v for a_des_decimales, v in candidats if a_des_decimales]
        return _deux_decimales(avec_decimales[0] if avec_decimales else candidats[0][1])
    return None


def _premier_annonce(texte: str, intitules: list) -> Optional[str]:
    """Le premier intitulé de la liste qui rend un montant l'emporte."""
    for intitule in intitules:
        valeur = _montant_annonce(texte, intitule)
        if valeur is not None:
            return valeur
    return None


def premiere_date(texte: str) -> Optional[str]:
    """
    La première date du texte, rendue en `aaaa-mm-jj`.

    Trois écritures reconnues, dans l'ordre où elles apparaissent : numérique
    (21/08/2026, 21.08.26), ISO (2026-08-21) et en toutes lettres (21 août 2026).
    Une année sur deux chiffres est comprise dans le siècle courant — un document
    daté de 26 est de 2026, pas de 1926 : personne ne scanne ses factures d'il y
    a cent ans.
    """
    dates = _dates_ordonnees(texte)
    return dates[0][1] if dates else None


def _valider(annee: int, mois: int, jour: int) -> Optional[str]:
    """Rend la date en ISO, ou rien si elle n'existe pas — un 31 février n'est pas une date."""
    if annee < 100:
        annee += 2000
    try:
        return datetime(annee, mois, jour).strftime("%Y-%m-%d")
    except ValueError:
        return None


def montant_ttc(texte: str) -> Optional[str]:
    """
    Le montant TTC, rendu en nombre à point décimal (`1234.56`).

    On cherche d'abord un montant **annoncé** — « Total TTC », « Net à payer »,
    puis « TOTAL » tout court —, car c'est celui qui fait foi. À défaut, le plus
    grand montant du texte : sur une facture, le total dépasse chacune de ses
    lignes. C'est une supposition, et elle est faillible ; elle vaut mieux que
    rien, et se corrige d'un clic sur la fiche.
    """
    texte = texte or ""
    annonce = _premier_annonce(texte, _INTITULES_TTC)
    if annonce is not None:
        return annonce

    # Un total s'écrit presque toujours avec ses centimes : les nombres nus d'un
    # document sont des quantités, des références, des numéros de commande. On
    # ne s'en contente qu'à défaut, et sous un plafond bien plus bas — c'est ce
    # qui évitait de rendre « COMMANDE N 16802016 » comme montant d'une facture.
    avec_decimales, entiers = [], []
    for trouve in _MONTANT.finditer(texte):
        valeur = _nombre(trouve.group(1))
        if valeur is None:
            continue
        if "." in trouve.group(1) or "," in trouve.group(1):
            avec_decimales.append(valeur)
        elif abs(float(valeur)) < PLAFOND_SANS_DECIMALES:
            entiers.append(valeur)
    montants = avec_decimales or entiers
    if not montants:
        return None
    return _deux_decimales(max(montants, key=lambda v: float(v)))


def _deux_decimales(valeur: str) -> str:
    """
    Un montant s'écrit avec ses centimes. « 120.5 » se lit mal sur une facture,
    et se compare mal à « 120.50 » quand on trie la colonne.
    """
    try:
        return f"{float(valeur):.2f}"
    except (TypeError, ValueError):
        return valeur


def _nombre(brut: str) -> Optional[str]:
    """« 1 234,56 » → « 1234.56 ». Rend rien si ce n'est pas un nombre."""
    nettoye = brut
    for espace in ESPACES:
        nettoye = nettoye.replace(espace, "")
    nettoye = nettoye.replace(",", ".")
    if nettoye.count(".") > 1:      # séparateur de milliers pris pour un décimal
        entier, _, decimales = nettoye.rpartition(".")
        nettoye = entier.replace(".", "") + "." + decimales
    try:
        return f"{float(nettoye):.2f}".rstrip("0").rstrip(".") if "." in nettoye else nettoye
    except ValueError:
        return None


def chiffres_seuls(texte: str) -> Optional[str]:
    """Ne garde que les chiffres — un numéro de client que l'OCR a semé d'espaces."""
    chiffres = re.sub(r"\D", "", texte or "")
    return chiffres or None


def sans_espaces(texte: str) -> Optional[str]:
    """Retire tous les blancs, insécables compris."""
    compact = re.sub(r"\s+", "", texte or "")
    return compact or None


def montant_ht(texte: str) -> Optional[str]:
    """
    Le montant hors taxes, à condition qu'il soit **annoncé**.

    Pas de repli sur « le plus grand montant » comme pour le TTC : un HT ne se
    devine pas, et un chiffre pris au hasard dans une facture serait pire que
    rien — il ne se verrait pas.
    """
    return _premier_annonce(texte, _INTITULES_HT)


def montant_tva(texte: str) -> Optional[str]:
    """Le montant de TVA, lui aussi seulement s'il est annoncé."""
    return _montant_annonce(texte, _INTITULE_TVA)


def derniere_date(texte: str) -> Optional[str]:
    """
    La **dernière** date du texte. Sur beaucoup de factures, la première est la
    date d'émission et la dernière l'échéance ou la date d'édition ; les deux
    fonctions existent pour qu'on puisse choisir sans écrire d'expression.
    """
    dates = _dates_ordonnees(texte)
    return dates[-1][1] if dates else None


def date_echeance(texte: str) -> Optional[str]:
    """
    La date annoncée comme échéance (« à payer avant », « date limite de
    paiement », « prélèvement le »).

    C'est la donnée dont un foyer se sert le plus : elle porte les rappels
    (§21.9). On ne la devine pas — sans intitulé, rien n'est rendu.
    """
    texte = texte or ""
    for trouve in _INTITULE_ECHEANCE.finditer(texte):
        fenetre = texte[trouve.end(): trouve.end() + 60]
        dates = _dates_ordonnees(fenetre)
        if dates:
            return dates[0][1]
    return None


def siren(texte: str) -> Optional[str]:
    """
    Le SIREN ou le SIRET de l'émetteur, chiffres seuls.

    Cherché d'abord après son intitulé, puis dans le texte à sa forme groupée
    (« 552 100 554 ») : sur beaucoup de documents, il n'est annoncé nulle part.
    C'est ce qui identifie une entreprise sans ambiguïté, là où son nom varie
    d'un en-tête à l'autre.
    """
    texte = texte or ""
    for expression in (_SIREN, _SIREN_NU):
        trouve = expression.search(texte)
        if trouve:
            chiffres = re.sub(r"\D", "", trouve.group(1))
            if len(chiffres) in (9, 14):
                return chiffres
    return None


def numero_tva(texte: str) -> Optional[str]:
    """Le numéro de TVA intracommunautaire (« FR12345678901 »), sans espaces."""
    # Longueur exigée : un IBAN commence lui aussi par « FR12 1234 » et l'on
    # rendait le début d'un compte bancaire pour un numéro de TVA. Les vrais font
    # au moins dix caractères une fois recollés.
    for trouve in _TVA_INTRA.finditer((texte or "").upper()):
        compact = trouve.group(1).replace(" ", "")
        if len(compact) >= 10:
            return compact
    return None


def iban(texte: str) -> Optional[str]:
    """
    Un IBAN, sans espaces. Le format seul est vérifié : la clé de contrôle ne
    l'est pas, un OCR qui confond 8 et B rendrait alors la valeur inutilisable
    alors qu'elle se corrige d'un clic.
    """
    # Tous les candidats, et non le premier : sur une facture d'entreprise, le
    # numéro de TVA (« FR 32 552100554 ») ressemble assez à un IBAN pour être
    # attrapé avant lui — et il est écrit plus haut.
    for trouve in _IBAN.finditer((texte or "").upper()):
        compact = re.sub(r"\s", "", trouve.group(1))
        if 15 <= len(compact) <= 34:
            return compact
    return None


def telephone(texte: str) -> Optional[str]:
    """Un numéro de téléphone français, rendu en dix chiffres collés."""
    trouve = _TELEPHONE.search(texte or "")
    if not trouve:
        return None
    chiffres = re.sub(r"\D", "", trouve.group(1))
    if chiffres.startswith("33"):
        chiffres = "0" + chiffres[2:]
    return chiffres if len(chiffres) == 10 else None


def _dates_ordonnees(texte: str) -> list:
    """Toutes les dates du texte, dans l'ordre où elles y apparaissent."""
    candidats = []
    for correspondance in _DATE_NUMERIQUE.finditer(texte or ""):
        jour, mois, annee = (int(g) for g in correspondance.groups())
        candidats.append((correspondance.start(), _valider(annee, mois, jour)))
    for correspondance in _DATE_ISO.finditer(texte or ""):
        annee, mois, jour = (int(g) for g in correspondance.groups())
        candidats.append((correspondance.start(), _valider(annee, mois, jour)))
    for correspondance in _DATE_LETTRES.finditer(texte or ""):
        jour, mois_texte, annee = correspondance.groups()
        mois = _MOIS.get(mois_texte.lower())
        if mois:
            candidats.append((correspondance.start(), _valider(int(annee), mois, int(jour))))
    return sorted((c for c in candidats if c[1]), key=lambda c: c[0])


# ------------------------------------------------------------------
# Transformateurs : ils ne cherchent rien, ils remettent en forme
# ------------------------------------------------------------------

def date_normalisee(texte: str) -> Optional[str]:
    """
    Rend en `aaaa-mm-jj` la date contenue dans ce que l'expression a trouvé,
    quelle que soit son écriture.

    C'est le `@smartdate` d'EzGED : une expression peut cerner la bonne date d'un
    document qui en porte dix, sans avoir à écrire le format dans l'expression —
    lequel change d'un émetteur à l'autre.
    """
    dates = _dates_ordonnees(texte)
    return dates[0][1] if dates else None


def nombre_normalise(texte: str) -> Optional[str]:
    """« 1 234,56 € » → « 1234.56 ». Ce que l'expression a cerné, rendu calculable."""
    trouve = _MONTANT.search(texte or "")
    if not trouve:
        return None
    valeur = _nombre(trouve.group(1))
    return _deux_decimales(valeur) if valeur is not None else None


def espaces_condenses(texte: str) -> Optional[str]:
    """
    Un seul espace là où l'OCR en a semé plusieurs, et rien aux extrémités.
    Sans cela, « Jean   DUPONT » et « Jean DUPONT » sont deux valeurs
    différentes dans un tableau qui les trie.
    """
    condense = re.sub(r"\s+", " ", (texte or "")).strip()
    return condense or None


def sans_accents(texte: str) -> Optional[str]:
    """
    Forme dépouillée, pour les valeurs qu'on compare plutôt qu'on ne lit — un
    scan rend « Hélène » ou « Helene » selon sa qualité.
    """
    import unicodedata

    decompose = unicodedata.normalize("NFD", texte or "")
    propre = "".join(c for c in decompose if unicodedata.category(c) != "Mn")
    return propre or None


def majuscules(texte: str) -> Optional[str]:
    """Tout en capitales : un code, une plaque, une référence."""
    valeur = (texte or "").strip().upper()
    return valeur or None


def ajouter_jours(texte: str, parametre: Optional[str] = None) -> Optional[str]:
    """
    Décale la date trouvée du nombre de jours donné en paramètre.

    C'est l'échéance calculée : beaucoup de factures n'annoncent pas de date
    limite mais un délai (« payable à 30 jours »). Le paramètre accepte un
    nombre négatif — un rappel se pose aussi *avant* une date.
    """
    from datetime import timedelta

    dates = _dates_ordonnees(texte)
    if not dates:
        return None
    try:
        jours = int(str(parametre or "0").strip())
    except ValueError:
        return None
    depart = datetime.strptime(dates[0][1], "%Y-%m-%d")
    return (depart + timedelta(days=jours)).strftime("%Y-%m-%d")


def concat_groupes(texte: str, parametre: Optional[str] = None,
                   groupes: Optional[tuple] = None) -> Optional[str]:
    """
    Recolle les groupes capturés par l'expression, séparés par le paramètre.

    Le `@concat` d'EzGED. Une expression peut cerner un prénom et un nom en deux
    endroits d'une même ligne ; les recoller ici évite d'écrire deux règles pour
    un seul champ. Sans groupes multiples, la valeur passe telle quelle.
    """
    if not groupes:
        return texte or None
    morceaux = [str(g).strip() for g in groupes if g and str(g).strip()]
    if not morceaux:
        return None
    separateur = parametre if parametre is not None else " "
    return separateur.join(morceaux)


# `extracteur` : la fonction sait chercher seule, l'expression devient facultative.
CATALOGUE = {
    "premiere_date": {
        "libelle": "Première date du document",
        "description": "Trouve la première date, quelle que soit son écriture — 21/08/26, "
                       "2026-08-21 ou « 21 août 2026 » — et la rend au format de la base. "
                       "Aucune expression à écrire.",
        "extracteur": True,
        "type_conseille": "date",
        "fonction": premiere_date,
    },
    "montant_ttc": {
        "libelle": "Montant TTC",
        "description": "Cherche un montant annoncé (« Total TTC », « Net à payer ») et, à "
                       "défaut, retient le plus grand montant du document. Tolère « 1 234,56 € ».",
        "extracteur": True,
        "type_conseille": "montant",
        "fonction": montant_ttc,
    },
    "montant_ht": {
        "libelle": "Montant HT",
        "description": "Le montant hors taxes, à condition qu'il soit annoncé « Total HT », "
                       "« Base HT »… Sans intitulé, rien n'est rendu : un HT ne se devine pas.",
        "extracteur": True,
        "type_conseille": "montant",
        "fonction": montant_ht,
    },
    "montant_tva": {
        "libelle": "Montant de TVA",
        "description": "Le montant de TVA annoncé (« TVA 20 % », « dont TVA »).",
        "extracteur": True,
        "type_conseille": "montant",
        "fonction": montant_tva,
    },
    "derniere_date": {
        "libelle": "Dernière date du document",
        "description": "La dernière date rencontrée. Sur beaucoup de factures, la première "
                       "est la date d'émission et la dernière l'échéance.",
        "extracteur": True,
        "type_conseille": "date",
        "fonction": derniere_date,
    },
    "date_echeance": {
        "libelle": "Date d'échéance",
        "description": "La date annoncée comme limite de paiement (« à payer avant », "
                       "« date limite de règlement », « prélèvement le »). C'est celle qui "
                       "portera les rappels.",
        "extracteur": True,
        "type_conseille": "date",
        "fonction": date_echeance,
    },
    "siren": {
        "libelle": "SIREN / SIRET",
        "description": "Le numéro d'entreprise de l'émetteur, chiffres seuls. Il identifie "
                       "une société sans ambiguïté, là où son nom varie d'un en-tête à l'autre.",
        "extracteur": True,
        "type_conseille": "texte",
        "fonction": siren,
    },
    "numero_tva": {
        "libelle": "N° de TVA intracommunautaire",
        "description": "« FR12345678901 », sans espaces.",
        "extracteur": True,
        "type_conseille": "texte",
        "fonction": numero_tva,
    },
    "iban": {
        "libelle": "IBAN",
        "description": "Un IBAN, sans espaces. Le format est vérifié, pas la clé de "
                       "contrôle : un OCR qui confond 8 et B rendrait la valeur inutilisable "
                       "alors qu'elle se corrige d'un clic.",
        "extracteur": True,
        "type_conseille": "texte",
        "fonction": iban,
    },
    "telephone": {
        "libelle": "Numéro de téléphone",
        "description": "Un numéro français, rendu en dix chiffres collés — quelle que soit "
                       "la façon dont il est écrit sur le document.",
        "extracteur": True,
        "type_conseille": "texte",
        "fonction": telephone,
    },
    "date_normalisee": {
        "libelle": "Mettre la date au bon format",
        "description": "Rend en aaaa-mm-jj la date contenue dans ce que l'expression a "
                       "trouvé, quelle qu'en soit l'écriture. Utile quand un document porte "
                       "dix dates et qu'une expression désigne la bonne.",
        "extracteur": False,
        "type_conseille": "date",
        "fonction": date_normalisee,
    },
    "nombre_normalise": {
        "libelle": "Mettre le nombre au bon format",
        "description": "« 1 234,56 € » devient « 1234.56 » : ce que l'expression a cerné, "
                       "rendu comparable et calculable.",
        "extracteur": False,
        "type_conseille": "montant",
        "fonction": nombre_normalise,
    },
    "ajouter_jours": {
        "libelle": "Décaler la date de N jours",
        "description": "Calcule une échéance à partir de la date trouvée : « payable à 30 "
                       "jours » n'annonce pas de date limite, il faut la poser. Un nombre "
                       "négatif recule — un rappel se pose aussi avant une date.",
        "extracteur": False,
        "type_conseille": "date",
        "parametre": {"libelle": "Nombre de jours", "exemple": "30", "type": "entier"},
        "fonction": ajouter_jours,
    },
    "concat_groupes": {
        "libelle": "Recoller les morceaux capturés",
        "description": "Quand l'expression capture plusieurs morceaux — un prénom et un nom, "
                       "une référence en deux parties — les recolle avec le séparateur "
                       "indiqué, au lieu d'écrire deux règles pour un seul champ.",
        "extracteur": False,
        "type_conseille": "texte",
        "parametre": {"libelle": "Séparateur", "exemple": " ", "type": "texte"},
        "fonction": concat_groupes,
    },
    "espaces_condenses": {
        "libelle": "Condenser les espaces",
        "description": "Un seul espace là où l'OCR en a semé plusieurs, et rien aux "
                       "extrémités : « Jean   DUPONT » et « Jean DUPONT » ne doivent pas "
                       "faire deux valeurs différentes dans un tableau qui les trie.",
        "extracteur": False,
        "type_conseille": "texte",
        "fonction": espaces_condenses,
    },
    "sans_accents": {
        "libelle": "Retirer les accents",
        "description": "Pour les valeurs qu'on compare plutôt qu'on ne lit : un scan rend "
                       "« Hélène » ou « Helene » selon sa qualité.",
        "extracteur": False,
        "type_conseille": "texte",
        "fonction": sans_accents,
    },
    "majuscules": {
        "libelle": "Tout en majuscules",
        "description": "Pour un code, une plaque, une référence — que la casse du document "
                       "ne fasse pas deux valeurs.",
        "extracteur": False,
        "type_conseille": "texte",
        "fonction": majuscules,
    },
    "chiffres_seuls": {
        "libelle": "Ne garder que les chiffres",
        "description": "Retire tout ce qui n'est pas un chiffre de ce que l'expression a "
                       "trouvé : « N° 026 580 4351 » devient « 0265804351 ».",
        "extracteur": False,
        "type_conseille": "texte",
        "fonction": chiffres_seuls,
    },
    "sans_espaces": {
        "libelle": "Supprimer les espaces",
        "description": "Retire les espaces de ce que l'expression a trouvé, insécables "
                       "compris — l'OCR en sème dans les numéros de série et les IBAN.",
        "extracteur": False,
        "type_conseille": "texte",
        "fonction": sans_espaces,
    },
}


def decrire() -> list[dict]:
    """Le catalogue, tel que l'écran de règles le propose."""
    return [{
        "cle": cle,
        "libelle": details["libelle"],
        "description": details["description"],
        "extracteur": details["extracteur"],
        "type_conseille": details["type_conseille"],
        # `None` quand la fonction n'attend rien : l'écran n'affiche alors aucun
        # champ, plutôt qu'un champ vide dont personne ne saurait quoi faire.
        "parametre": details.get("parametre"),
    } for cle, details in CATALOGUE.items()]


def connue(cle: Optional[str]) -> bool:
    return bool(cle) and cle in CATALOGUE


def est_extracteur(cle: Optional[str]) -> bool:
    return connue(cle) and CATALOGUE[cle]["extracteur"]


def attend_un_parametre(cle: Optional[str]) -> bool:
    return connue(cle) and CATALOGUE[cle].get("parametre") is not None


def appliquer(cle: str, texte: str, parametre: Optional[str] = None,
              groupes: Optional[tuple] = None) -> Optional[str]:
    """
    Applique une fonction du catalogue. Une clé inconnue ne rend rien.

    Le paramètre et les groupes capturés ne sont passés qu'aux fonctions qui les
    acceptent : les autres gardent leur signature d'origine, et l'on n'a pas eu à
    réécrire les quatre premières pour en ajouter douze.
    """
    if not connue(cle):
        return None
    fonction = CATALOGUE[cle]["fonction"]
    arguments = fonction.__code__.co_varnames[:fonction.__code__.co_argcount]
    extra = {}
    if "parametre" in arguments:
        extra["parametre"] = parametre
    if "groupes" in arguments:
        extra["groupes"] = groupes
    return fonction(texte, **extra)
