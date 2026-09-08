"""
Applique les règles regex stockées en base sur le texte OCR d'un document,
et en déduit : la catégorie (classement automatique) et les
métadonnées libres (numéro de facture, montant, IBAN, etc.) qui sont ensuite
stockées dans la table `metadonnees` (une ligne par champ trouvé ->
remplissage auto des colonnes).
"""
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .db import Document, Metadonnee, ProfilExtraction, RegleExtraction

log = logging.getLogger(__name__)


def _chercher(pattern: str, texte: str, contexte: str):
    """
    `re.search` tolérant : une regex invalide (saisie avant la mise en place de
    la validation côté admin, ou importée) est signalée et ignorée, au lieu de
    faire échouer le traitement complet du document — et donc de tous les
    documents suivants.
    """
    try:
        return re.search(pattern, texte)
    except re.error as erreur:
        log.warning(f"Regex invalide ignorée ({contexte}) : {erreur}")
        return None


def profils_du_type(session: Session, categorie_id) -> list:
    """Jeux de règles actifs d'un type, par priorité croissante puis identifiant."""
    if not categorie_id:
        return []
    return (session.query(ProfilExtraction)
            .filter(ProfilExtraction.categorie_id == categorie_id,
                    ProfilExtraction.actif.is_(True))
            .order_by(ProfilExtraction.priorite.asc(), ProfilExtraction.id.asc())
            .all())


def profil_applicable(session: Session, document: Document, texte: Optional[str] = None):
    """
    Le jeu de règles qui s'applique à ce document (§19.6).

    Parmi les jeux de son type, par priorité croissante, **le premier dont la
    reconnaissance correspond au texte l'emporte** — et il sera seul appliqué
    (décision D5). Aucun ne correspond : le jeu générique du type, s'il existe.

    Un jeu reconnu prend donc la main sur tout, y compris sur ce qu'il ne trouve
    pas : le champ reste vide et le document part au Centre d'analyse. C'est le
    choix le plus prévisible — on sait toujours quel jeu a produit une valeur, ce
    qui n'était pas vrai d'une liste unique où deux règles pouvaient se disputer
    un champ.
    """
    contenu = texte if texte is not None else (document.texte_ocr or "")
    generique = None
    for profil in profils_du_type(session, document.categorie_id):
        if profil.generique and generique is None:
            generique = profil
        motif = (profil.reconnaissance or "").strip()
        if not motif:
            continue
        if _chercher(motif, contenu, f"jeu « {profil.nom} »"):
            return profil
    return generique


# `identifier_categorie` a été retirée au §19.3 : le classement ne se devine plus
# sur le texte, il se déclare en déposant le document dans le dossier de son type.
# Ce module ne s'occupe donc plus que d'**extraire** ce que le document contient
# — il ne décide plus de sa place.


def _convertir_valeur(valeur: str, type_champ: str) -> str:
    if type_champ == "montant":
        return valeur.replace(",", ".").strip()
    if type_champ == "date":
        # Normalise vers aaaa-mm-jj. Les documents réels mélangent les
        # séparateurs (21/08/26, 24.09.2026) et écrivent souvent l'année sur
        # deux chiffres : n'accepter que jj/mm/aaaa laissait la date non
        # convertie, et la colonne `date_document` vide.
        formats = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y")
        for fmt in formats:
            try:
                return datetime.strptime(valeur.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return valeur
    return valeur.strip()


def _valeur_de_la_regle(regle, texte: str):
    """
    Ce qu'une règle tire d'un texte : une expression, une fonction, ou les deux
    (§18.35).

    Trois façons de s'en servir, et l'ordre dit laquelle :

    * une **expression seule** — le comportement d'origine, le groupe capturant
      fait la valeur ;
    * une **fonction seule** — « première date », « montant TTC » cherchent
      elles-mêmes, il n'y a pas d'expression à écrire ;
    * **les deux** — l'expression délimite la zone, la fonction en tire la
      valeur : « ne garder que les chiffres » sur ce qui suit « N° client ».

    Rend `None` quand rien n'est trouvé : c'est ce qui laisse la règle suivante
    tenter sa chance.
    """
    from . import extraction_fonctions

    a_une_fonction = extraction_fonctions.connue(regle.fonction)
    motif = (regle.pattern or "").strip()

    parametre = getattr(regle, "parametre", None)

    if not motif:
        # Sans expression, seule une fonction qui sait chercher a du sens.
        if extraction_fonctions.est_extracteur(regle.fonction):
            return extraction_fonctions.appliquer(regle.fonction, texte, parametre)
        return None

    match = _chercher(motif, texte, f"règle « {regle.nom} »")
    if not match:
        return None
    trouve = match.group(1) if match.groups() else match.group(0)
    if a_une_fonction:
        # Les groupes suivent la valeur : une fonction peut vouloir les recoller
        # (§21.4) plutôt que de se contenter du premier.
        return extraction_fonctions.appliquer(regle.fonction, trouve, parametre,
                                              match.groups() or None)
    return trouve


def appliquer_regles(document: Document, session: Session) -> None:
    """
    Applique toutes les règles actives (triées par priorité) sur document.texte_ocr,
    et remplit document.metadonnees et document.date_document.

    Elle ne touche plus à la catégorie depuis le §19.3 : celle-ci vient du dossier
    où le document a été déposé, et rien ne doit la contredire après coup.
    """
    texte = document.texte_ocr or ""

    # Le jeu de règles qui s'applique à ce document (§19.6), et lui seul.
    profil = profil_applicable(session, document, texte)
    if profil is None:
        log.info("Aucun jeu de règles pour le document %s : rien à extraire", document.id)
        return

    # Un jeu reconnu peut désigner l'émetteur — c'est ce qui le rend de nouveau
    # déductible. Jamais par-dessus un émetteur déjà choisi : celui-là a été
    # posé par quelqu'un, et une expression régulière ne le contredit pas.

    regles = (
        session.query(RegleExtraction)
        .filter(RegleExtraction.actif.is_(True),
                RegleExtraction.profil_id == profil.id)
        .order_by(RegleExtraction.priorite.asc())
        .all()
    )

    # Clés déjà remplies **par ce passage** : la première règle à renseigner un
    # champ l'emporte, conformément à la priorité (plus petit = testé en premier).
    # Sans cela, une règle de repli générique écrasait la règle ciblée passée
    # avant elle, et la priorité ne servait plus à rien. Les valeurs issues d'un
    # passage antérieur, elles, sont bien rafraîchies : c'est tout l'intérêt de
    # pouvoir rejouer l'extraction après avoir corrigé une expression.
    deja_remplies: set[str] = set()

    for regle in regles:
        if regle.champ_cible in deja_remplies:
            continue
        valeur_brute = _valeur_de_la_regle(regle, texte)
        if valeur_brute is None:
            continue
        deja_remplies.add(regle.champ_cible)
        valeur = _convertir_valeur(valeur_brute, regle.type_champ)

        # upsert dans metadonnees (une seule valeur par (document, cle))
        existant = (
            session.query(Metadonnee)
            .filter_by(document_id=document.id, cle=regle.champ_cible)
            .one_or_none()
        )
        if existant:
            # Une valeur saisie par une personne l'emporte sur une expression
            # régulière (§18.45). `regle_id` nul signale une saisie manuelle : on
            # la laisse. Sans cette précaution, le rejeu automatique des travaux
            # bloqués écraserait toutes les cinq minutes les corrections faites
            # depuis la fiche — l'inverse exact du service rendu.
            if existant.regle_id is None and (existant.valeur or "").strip():
                log.debug("« %s » gardé tel quel sur le document %s : valeur saisie à la main",
                          regle.champ_cible, document.id)
                continue
            existant.valeur = valeur
            existant.regle_id = regle.id
        else:
            # Attachée au document, et pas seulement à son identifiant : sa
            # collection peut être déjà chargée, et un `flush` ne l'y ferait pas
            # entrer — le contrôle de conformité qui suit lirait un document
            # amputé de ce qu'on vient d'extraire (voir `references_auto`).
            document.metadonnees.append(Metadonnee(
                regle_id=regle.id,
                cle=regle.champ_cible,
                valeur=valeur,
            ))

        # `date_document` est aussi **une colonne du document** : on la remplit
        # pour le tri et la recherche. La métadonnée reste, invisible à l'écran
        # (§22.79), parce que c'est elle qui porte « corrigé à la main » — sans
        # quoi le rejeu automatique écraserait toutes les cinq minutes une date
        # qu'on vient de corriger (§18.45).
        if regle.champ_cible == "date_document":
            try:
                document.date_document = datetime.strptime(valeur, "%Y-%m-%d").date()
            except ValueError:
                log.debug("Date illisible pour le document %s : %r", document.id, valeur)


