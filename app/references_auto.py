"""
Remplissage automatique des champs adossés à une table de données (§17.18, §18.47).

Une catégorie peut exiger un champ dont les valeurs viennent d'une table du
foyer — le titulaire d'une facture parmi les membres, le véhicule concerné par
un contrôle technique. Ces valeurs sont, la plupart du temps, **écrites dans le
document** : une facture d'électricité porte le nom de son titulaire, une carte
grise porte l'immatriculation.

Ce module les y cherche — **mais seulement quand un administrateur l'a
demandé**. C'est le sens du §18.47 : la déduction se déclare champ par champ,
dans « Champs attendus », et un champ qui ne la déclare pas reste vide. Un
rattachement que personne n'a demandé se lit comme une erreur même quand il est
juste, parce qu'on ne peut pas le vérifier sans relire le document.

Ce qu'un champ déclare :

  * `deduction = 'aucune'` — rien n'est cherché (le défaut) ;
  * `deduction = 'toutes'` — la ligne n'est retenue que si **toutes** les
    colonnes cherchées figurent dans le document. Pour un membre du foyer, c'est
    le prénom **et** le nom : deux personnes d'une même famille portent le même
    nom, et « Dupont » seul ne désigne personne ;
  * `deduction = 'une'` — une seule colonne trouvée suffit. Ce qui convient à
    une immatriculation ou un numéro de contrat, qui ne se répètent pas ailleurs.
  * `colonnes_deduction` — les colonnes cherchées. Vide : les colonnes
    identifiantes de la table source, qui sont déjà ce à quoi on la reconnaît ;
  * `deduction_approchee` — tolérer une lettre de différence (§21.4). Un OCR lit
    « 0range » pour « Orange » ; mais sur une immatriculation, la même tolérance
    confondrait deux véhicules. Elle se déclare donc, et ne se prend jamais.

Ce qui reste vrai quel que soit le réglage, parce qu'un rattachement faux est
pire qu'un rattachement absent — il ne se voit pas, alors qu'un champ vide se
réclame :

  * **une seule correspondance** : si deux membres du foyer sont nommés dans le
    même document, on ne devine pas lequel est le titulaire ;
  * **jamais d'écrasement** : une valeur déjà présente, saisie à la main ou
    corrigée, n'est pas retouchée ;
  * **libellés courts ignorés** : moins de trois caractères, la coïncidence est
    trop probable.
"""
import logging
import re
import unicodedata

from sqlalchemy.orm import Session

from . import base_donnees, conformite
from .db import Document, Metadonnee, RegleChampCategorie
from .filtres import PREFIXE_META

log = logging.getLogger(__name__)

LONGUEUR_MINIMALE = 3
# En dessous, la tolérance ne s'applique pas : sur un mot de quatre lettres, une
# différence sur une seule en fait souvent un autre mot.
LONGUEUR_APPROCHEE = 5


def _sans_accents(texte: str) -> str:
    """
    Compare sur une forme dépouillée : un scan rend « Hélène » aussi bien que
    « Helene » selon la qualité de l'océrisation, et l'on ne veut pas manquer le
    rattachement pour un accent.
    """
    decompose = unicodedata.normalize("NFD", texte or "")
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").casefold()


def _mentionne(texte_normalise: str, libelle: str, approche: bool = False) -> bool:
    """
    Le libellé apparaît-il dans le texte, comme mot entier ?

    `approche` autorise **une** différence de caractère par mot d'au moins
    LONGUEUR_APPROCHEE lettres (§21.4) : un OCR lit « 0range » pour « Orange »,
    « Hélene » pour « Hélène », et le rattachement échouait sur un pixel. La
    tolérance ne se prend jamais d'elle-même — elle se déclare champ par champ,
    parce que sur une immatriculation elle confondrait deux véhicules.
    """
    motif = _sans_accents(libelle).strip()
    if len(motif) < LONGUEUR_MINIMALE:
        return False
    # `\b` ne suffit pas pour un libellé de plusieurs mots dont les espaces
    # peuvent varier dans un scan : on tolère n'importe quelle suite d'espaces.
    morceaux = [re.escape(mot) for mot in motif.split()]
    if re.search(r"\b" + r"\s+".join(morceaux) + r"\b", texte_normalise) is not None:
        return True
    return approche and _mentionne_approche(texte_normalise, motif)


def _mentionne_approche(texte_normalise: str, motif: str) -> bool:
    """
    Le libellé se retrouve-t-il à une lettre près ?

    On compare mot à mot avec les mots du texte de longueur voisine, et l'on
    exige la même différence pour **chaque** mot du libellé : « Jean Dupond »
    rattrape « Jean Dupont », mais « Dupont » seul ne rattrape pas « Dupond »
    d'une autre ligne — c'est la suite des mots qui fait la reconnaissance.
    """
    attendus = motif.split()
    if len(motif.replace(" ", "")) < LONGUEUR_APPROCHEE:
        return False   # sur un libellé court, une lettre en fait souvent un autre

    mots = re.findall(r"\w+", texte_normalise)
    for depart in range(len(mots) - len(attendus) + 1):
        fenetre = mots[depart:depart + len(attendus)]
        ecarts = 0
        for attendu, lu in zip(attendus, fenetre):
            if attendu == lu:
                continue
            # Un mot court doit tomber juste : « Jean » et « Yann » ne sont pas
            # le même prénom, quand « Dupont » et « Dupond » sont le même nom mal
            # lu. La tolérance se dépense donc sur les mots assez longs pour
            # qu'une lettre ne les change pas de sens…
            if len(attendu) < LONGUEUR_APPROCHEE or not _proches(attendu, lu):
                ecarts = 99
                break
            ecarts += 1
        # …et une seule fois pour tout le libellé : deux mots mal lus, ce n'est
        # plus une reconnaissance, c'est une devinette.
        if ecarts <= 1:
            return True
    return False


def _proches(attendu: str, lu: str) -> bool:
    """Deux mots à une substitution, une insertion ou une suppression près."""
    if attendu == lu:
        return True
    if abs(len(attendu) - len(lu)) > 1:
        return False
    # Distance de Levenshtein bornée à 1 : au-delà, on ne reconnaît plus, on
    # devine — et un rattachement faux ne se voit pas, alors qu'un champ vide
    # se réclame.
    if len(attendu) == len(lu):
        return sum(1 for a, b in zip(attendu, lu) if a != b) <= 1
    court, long = (attendu, lu) if len(attendu) < len(lu) else (lu, attendu)
    for position in range(len(long)):
        if long[:position] + long[position + 1:] == court:
            return True
    return False


MODES = ("aucune", "toutes", "une")


def _colonnes_cherchees(regle) -> list[str]:
    """Colonnes déclarées sur le champ ; vide = celles qui identifient la table."""
    return [c.strip() for c in (regle.colonnes_deduction or "").split(",") if c.strip()]


def _lignes_designees(session: Session, source: str, regle, texte: str) -> list[tuple]:
    """
    Lignes de `source` que le document désigne, selon ce que le champ déclare.
    Rend une liste de `(source, identifiant, [valeurs reconnues])`.
    """
    demandees = _colonnes_cherchees(regle)
    if demandees:
        lignes = base_donnees.valeurs_des_colonnes(session, source, demandees)
    else:
        lignes = {identifiant: {str(rang): valeur for rang, valeur in enumerate(valeurs)}
                  for identifiant, valeurs in
                  base_donnees.valeurs_identifiantes(session, source).items()}

    approche = bool(getattr(regle, "deduction_approchee", False))
    designees = []
    for identifiant, valeurs in lignes.items():
        reconnues = [v for v in valeurs.values() if _mentionne(texte, v, approche)]
        if not reconnues:
            continue
        # « toutes » exige que rien ne manque ; « une » se contente d'une trouvaille.
        if regle.deduction == "toutes" and len(reconnues) != len(valeurs):
            continue
        designees.append((source, identifiant, list(valeurs.values())))
    return designees


def remplir(session: Session, document: Document) -> dict:
    """
    Remplit les champs à source de ce document quand le texte désigne une ligne
    et une seule, **et** que le champ déclare une déduction. Rend
    `{champ: libellé}` pour ce qui a été rattaché.
    """
    if not document.categorie_id or not document.texte_ocr:
        return {}

    regles = [
        regle for regle in session.query(RegleChampCategorie).filter(
            RegleChampCategorie.categorie_id == document.categorie_id)
        if conformite.sources_de(regle) and (regle.deduction or "aucune") != "aucune"
    ]
    if not regles:
        return {}

    texte = _sans_accents(document.texte_ocr)
    remplis = {}

    for regle in regles:
        if not regle.champ.startswith(PREFIXE_META):
            continue
        cle = regle.champ[len(PREFIXE_META):]
        existante = next((m for m in document.metadonnees if m.cle == cle), None)
        if existante and (existante.valeur or "").strip():
            continue      # déjà renseigné : on ne retouche pas

        # Un champ peut puiser dans plusieurs sources (§17.28) : on cherche dans
        # toutes, et l'on n'écrit que si **une seule** ligne, toutes sources
        # confondues, est désignée par le document.
        trouvees = []
        for source in conformite.sources_de(regle):
            try:
                trouvees += _lignes_designees(session, source, regle, texte)
            except Exception:
                log.exception(f"Source « {source} » illisible pour le champ {regle.champ}")

        if len(trouvees) != 1:
            # zéro : le document ne le dit pas. Plusieurs : il en dit trop pour
            # qu'on choisisse à la place de quelqu'un.
            continue

        source, identifiant, valeurs = trouvees[0]
        valeur = f"{source}{base_donnees.SEPARATEUR_SOURCE}{identifiant}"
        if existante:
            existante.valeur = valeur
        else:
            # `append` et non `session.add(Metadonnee(document_id=...))` : la
            # collection du document est déjà chargée (on l'a lue trois lignes
            # plus haut), et un `flush` n'y ajoute pas ce qui a été inséré par la
            # seule clé étrangère. Le contrôle de conformité, qui suit dans la
            # même session, lisait alors un document encore dépourvu de la
            # valeur qu'on venait de déduire : travail bloqué, statut
            # « incomplet », alors que le registre — session neuve — l'affichait.
            document.metadonnees.append(Metadonnee(cle=cle, valeur=valeur))
        remplis[cle] = " ".join(valeurs)

    return remplis
