"""
Proposer une règle à partir de ce qu'on montre sur le document (§21.5, bêta).

L'écran des règles demande une expression régulière écrite à l'aveugle : on
décrit avec des symboles ce qu'on a sous les yeux, on enregistre, on relance un
traitement, et l'on découvre que le motif ne prend rien. C'est la boucle la plus
décourageante du projet, et celle qui décide si l'extraction sera un jour réglée.

Ici, on **montre** la valeur sur la page et le module en déduit une règle :

  * la **forme** de la valeur donne le motif — une date ne s'attrape pas comme un
    montant, ni un numéro de contrat comme une raison sociale ;
  * les mots qui **précèdent** la valeur sur sa ligne donnent l'ancre. C'est elle
    qui fait la règle : « le nombre qui suit *Total TTC* » vaut pour toutes les
    factures de cet émetteur, là où « le nombre à cet endroit de la page » ne vaut
    que pour celle-ci.

Rien n'est enregistré : le module **propose**, et rend ce que la proposition
extrait du document qu'on regarde. C'est ce qui permet de vérifier avant
d'écrire, plutôt qu'après.
"""
import re
from typing import Optional

# Ce à quoi ressemble la valeur montrée, et comment l'attraper ailleurs. L'ordre
# compte : « 2026 » est un entier, « 02/04/2026 » une date.
FORMES = [
    ("date", re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$"),
     r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})", "date_normalisee", "date"),
    ("date_iso", re.compile(r"^\d{4}-\d{2}-\d{2}$"),
     r"(\d{4}-\d{2}-\d{2})", None, "date"),
    ("montant", re.compile(r"^\d[\d  .]*[.,]\d{1,2}\s*€?$"),
     r"([\d  .]*\d[.,]\d{1,2})", "nombre_normalise", "montant"),
    ("entier", re.compile(r"^\d[\d  ]*$"),
     r"([\d  ]*\d)", "chiffres_seuls", "entier"),
    ("reference", re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/.]{2,}$"),
     r"([A-Za-z0-9][A-Za-z0-9\-_/.]*)", None, "texte"),
]
# Repli : tout ce qui reste sur la ligne après l'ancre. Large, mais l'ancre le
# borne — et une proposition trop étroite ne prendrait rien sur le document
# suivant, ce qui est le défaut qu'on cherche justement à corriger.
MOTIF_LIBRE = r"(.+?)\s*$"

# Au-delà, l'ancre cesse d'être un repère : c'est une phrase, et elle ne se
# répétera pas à l'identique d'un document à l'autre.
MOTS_ANCRE = 3


def _forme(valeur: str) -> tuple:
    """(nom, motif, fonction conseillée, type de champ) pour la valeur montrée."""
    propre = (valeur or "").strip()
    for nom, expression, motif, fonction, type_champ in FORMES:
        if expression.match(propre):
            return nom, motif, fonction, type_champ
    return "libre", MOTIF_LIBRE, None, "texte"


def _ligne_contenant(texte: str, valeur: str) -> Optional[str]:
    """La ligne du document où la valeur apparaît — c'est là qu'est son ancre."""
    for ligne in (texte or "").splitlines():
        if valeur in ligne:
            return ligne
    return None


def _ancre_deduite(ligne: str, valeur: str) -> str:
    """
    Les derniers mots avant la valeur, sur sa ligne.

    On s'arrête à trois : au-delà, l'ancre devient une phrase, et une phrase ne
    se répète pas à l'identique d'un document à l'autre. On retire aussi le
    deux-points final, que le motif rendra facultatif — certains émetteurs le
    mettent, d'autres non.
    """
    avant = ligne[:ligne.find(valeur)] if valeur in ligne else ligne
    mots = [m for m in re.split(r"\s+", avant.strip()) if m]
    return " ".join(mots[-MOTS_ANCRE:]).rstrip(":").strip()


def _motif_ancre(ancre: str) -> str:
    """
    L'ancre en expression, avec des espaces souples et un deux-points facultatif.

    Un scan sépare « Total TTC » par un espace, deux, ou une tabulation ; exiger
    l'espace exact ferait échouer la règle sur le document suivant.
    """
    morceaux = [re.escape(m) for m in ancre.split() if m]
    return r"\s+".join(morceaux) + r"\s*:?\s*"


def proposer(texte: str, valeur: str, ancre: Optional[str] = None,
             champ_cible: Optional[str] = None) -> dict:
    """
    Propose une règle pour la valeur montrée, et dit ce qu'elle extrait.

    `ancre` peut être imposée par celui qui règle — il voit l'intitulé, et le
    module ne voit qu'une suite de caractères. Sans elle, on la déduit de la
    ligne.
    """
    valeur = (valeur or "").strip()
    if not valeur:
        return {"erreur": "Rien n'a été désigné sur le document."}

    forme, motif, fonction, type_champ = _forme(valeur)
    ligne = _ligne_contenant(texte, valeur)
    ancre_retenue = (ancre or "").strip() or (_ancre_deduite(ligne, valeur) if ligne else "")

    if ancre_retenue:
        pattern = _motif_ancre(ancre_retenue) + motif
    else:
        # Sans ancre, le motif doit se suffire : un motif libre attraperait
        # n'importe quelle ligne. On refuse plutôt que de proposer une règle qui
        # remplira le champ avec le premier texte venu.
        if motif is MOTIF_LIBRE:
            return {"erreur": "Aucun intitulé ne précède cette valeur sur sa ligne. "
                              "Désignez aussi le mot qui l'annonce : c'est lui qui "
                              "permettra de la retrouver sur les autres documents."}
        pattern = motif

    essai = _essayer(pattern, texte)
    return {
        "pattern": pattern,
        "fonction": fonction,
        "type_champ": type_champ,
        "forme": forme,
        "ancre": ancre_retenue,
        "champ_cible": champ_cible,
        "trouve": essai is not None,
        # ce que la règle extrait **de ce document-ci** : c'est la vérification
        # qui manquait, et elle a lieu avant d'enregistrer quoi que ce soit
        "valeur_extraite": essai,
        "conforme": _equivalent(essai, valeur),
    }


def _equivalent(extrait: Optional[str], montre: str) -> bool:
    """
    L'extraction correspond-elle à ce qui a été montré ?

    Pas une égalité stricte : on clique un mot entier — « 174.00€ », « FR-001 : »
    — et le motif, lui, s'arrête à la valeur. Exiger le caractère près ferait dire
    « ce n'est pas ce que vous avez désigné » à une règle parfaitement juste, et
    l'on n'oserait plus s'y fier.
    """
    if extrait is None:
        return False
    propre = lambda v: re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", v or "").casefold()
    a, b = propre(extrait), propre(montre)
    return bool(a) and (a == b or a in b or b in a)


def _essayer(pattern: str, texte: str) -> Optional[str]:
    try:
        trouve = re.search(pattern, texte or "", re.IGNORECASE | re.MULTILINE)
    except re.error:
        return None
    if not trouve:
        return None
    return trouve.group(1) if trouve.groups() else trouve.group(0)
