"""
Routes réservées aux administrateurs : gestion des catégories (avec leur
regex de classement automatique), des règles d'extraction, des utilisateurs,
et des rôles/droits par catégorie.
"""
import json
import logging
import os
import re
import secrets
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, ConfigDict

from .db import (
    get_session, Categorie, ColonneCategorie, ExportArchive, ProfilExtraction,
    RegleExtraction, Utilisateur,
    Role, DroitCategorie,
    RegleChampCategorie, Job, Document, JournalAudit, TableDonnees,
    DroitGeneral, DroitVue, DroitBranche, VueEnregistree, Automatisation,
    TableauDeBord, RattachementType, Script, ExecutionScript, LienType,
    ids_categorie_et_descendants,
)
from . import audit, auth, base_donnees, categories as natures, colonnes, config, conformite
from . import automatisations
from . import liens_type
from . import rattachements
from . import scripts
from . import courriel
from . import groupes
from . import droits
from . import depots, export, impact
from . import configuration, extraction_fonctions, limitation, modeles, otp
from . import references_auto, reglages, supervision
from . import filtres as moteur_filtres
from . import recherche as moteur_recherche
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)

def exiger_acces_administration(user: Utilisateur = Depends(auth.get_current_user)) -> Utilisateur:
    """
    Porte d'entrée de l'administration (§19.12).

    Elle s'ouvre à un administrateur, et à quiconque porte **au moins un** droit
    général : sans cela, donner le seul droit « serveur de travaux » à quelqu'un
    ne lui donnerait accès à rien — la porte serait fermée avant la pièce.

    Ce que chaque écran exige en propre est vérifié écran par écran, par
    `exiger(...)` ci-dessous. Cette garde-là ne fait qu'écarter ceux qui n'ont
    rien à y faire du tout.
    """
    if user.est_admin or any(droits.general(user, d) for d in droits.GENERAUX):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Réservé à l'administration")


def exiger(droit: str):
    """
    Dépendance FastAPI exigeant un droit général précis sur un point d'entrée.

    Écrite ainsi — une fabrique de dépendance — pour que le droit soit **déclaré
    à côté de la route**, lisible d'un coup d'œil au-dessus de la fonction, et
    non enfoui dans son corps. Un contrôle qu'on ne voit pas en lisant la route
    est un contrôle qu'on oublie d'ajouter à la suivante.
    """
    def dependance(user: Utilisateur = Depends(auth.get_current_user)) -> Utilisateur:
        try:
            droits.exiger_general(user, droit)
        except droits.DroitRefuse as refus:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(refus))
        return user
    return dependance


router = APIRouter(prefix="/admin", tags=["admin"],
                   dependencies=[Depends(exiger_acces_administration)])


def _valider_regex(pattern: Optional[str], libelle: str = "L'expression régulière") -> None:
    """
    Refuse une regex que Python ne sait pas compiler. Sans ce contrôle, le motif
    invalide est accepté puis appliqué par le worker sur chaque document
    importé, où il fait échouer l'extraction complète (cf. app/regex_engine.py).
    """
    if not pattern:
        return
    try:
        re.compile(pattern)
    except re.error as erreur:
        raise HTTPException(status_code=422, detail=f"{libelle} est invalide : {erreur}")


def _compter_admins_actifs(session: Session, sauf_id: Optional[int] = None) -> int:
    query = session.query(Utilisateur).filter_by(est_admin=True, actif=True)
    if sauf_id is not None:
        query = query.filter(Utilisateur.id != sauf_id)
    return query.count()


def _refuser_perte_dernier_admin(session: Session, utilisateur: Utilisateur) -> None:
    """
    Empêche de supprimer, désactiver ou rétrograder le dernier administrateur
    actif : sans lui, plus personne ne peut accéder à l'administration et le
    compte initial n'est recréé que si la table `utilisateurs` est vide.
    """
    if not (utilisateur.est_admin and utilisateur.actif):
        return
    if _compter_admins_actifs(session, sauf_id=utilisateur.id) == 0:
        raise HTTPException(
            status_code=409,
            detail="Ce compte est le dernier administrateur actif : nomme un autre "
                   "administrateur avant de le supprimer, le désactiver ou le rétrograder.",
        )


# ------------------------------------------------------------
# Les émetteurs
# ------------------------------------------------------------

# `usr_emetteurs` est une **table du foyer** comme les autres, tenue depuis
# l'écran « Base de données » (§18.32). Elle n'a plus rien de particulier depuis
# le §21.12 : un type qui veut un émetteur déclare un champ attendu qui y puise,
# et gagne du même coup la déduction, le rattachement, le repli et les droits par
# branche — tout ce que l'exception codée en dur ne savait pas faire.


# ------------------------------------------------------------
# Catégories (classement automatique par regex)
# ------------------------------------------------------------

class CategorieIn(BaseModel):
    nom: str
    # « dossier » (organise), « type » (porte les documents et reçoit les dépôts)
    # ou « fiche » (porte des documents, mais n'en reçoit que déposés à la main)
    # — §19.1 et §22.1.
    nature: str = natures.TYPE
    # Dossier de dépôt sous `ocr_wait/` (§19.2). Vide : déduit du nom pour un
    # type, ignoré pour un dossier de classement.
    dossier_depot: Optional[str] = None
    ordre: int = 100             # ordre d'affichage dans la navigation
    parent_id: Optional[int] = None


class CategorieOut(CategorieIn):
    id: int

    model_config = ConfigDict(from_attributes=True)


def _refuser_si(controle) -> None:
    """
    Traduit un refus de cohérence (§19.1) en réponse HTTP. Le message vient du
    module qui tient la règle : il explique quoi faire, pas seulement ce qui est
    interdit.
    """
    try:
        controle()
    except natures.NatureRefusee as refus:
        raise HTTPException(status_code=400, detail=str(refus))


def _attribuer_depot(session: Session, categorie: Categorie,
                     souhaite: Optional[str], ancien: Optional[str] = None) -> None:
    """
    Fixe le dossier de dépôt du type, et met le disque en accord (§19.2).

    Le renommage **déplace ce qui attendait** dans l'ancien dossier : sans cela,
    un fichier déposé la veille ne serait plus jamais lu. Une panne du système de
    fichiers n'annule pas l'enregistrement — le serveur de travaux repasse et
    recrée ce qui manque à chaque entretien ; refuser la modification pour un
    dossier absent bloquerait l'administration sur un incident réparable.
    """
    try:
        retenu = depots.attribuer(session, categorie, souhaite)
    except depots.DepotRefuse as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    try:
        if retenu:
            depots.renommer(ancien, retenu)
        elif ancien:
            log.info(f"« {categorie.nom} » devient un dossier de classement : "
                     f"son dossier de dépôt {ancien} est conservé et sera signalé.")
    except Exception:
        log.exception("Le dossier de dépôt n'a pas pu être mis en place sur le disque")


# `_valider_table_source` a disparu au §22.1 : plus aucune catégorie ne s'adosse
# à une table du foyer. La fiche de liaison le faisait, et c'est précisément ce
# qui la rendait inutilisable — il fallait une table, un champ qui y puise et un
# document qui le remplisse avant qu'elle ne montre quoi que ce soit. La fiche
# **simple** qui la remplace ne s'adosse à rien : on y glisse un fichier, on
# remplit les valeurs.


def _nature_validee(nature: Optional[str]) -> str:
    try:
        return natures.valider_nature(nature)
    except natures.NatureRefusee as refus:
        raise HTTPException(status_code=400, detail=str(refus))


def _verifier_parent(categorie_id: Optional[int], parent_id: Optional[int], session: Session) -> None:
    """
    Empêche de créer une boucle dans l'arborescence : une catégorie ne peut pas
    être son propre parent, ni descendre d'une de ses sous-catégories.
    """
    if parent_id is None:
        return
    if not session.query(Categorie).filter_by(id=parent_id).first():
        raise HTTPException(status_code=404, detail="Catégorie parente introuvable")
    if categorie_id is None:
        return
    if parent_id in ids_categorie_et_descendants(session, categorie_id):
        raise HTTPException(
            status_code=400,
            detail="Une catégorie ne peut pas être rattachée à elle-même ou à une de ses sous-catégories",
        )


@router.get("/categories", response_model=list[CategorieOut], dependencies=[Depends(exiger("reglages"))])
def lister(session: Session = Depends(get_session)):
    return session.query(Categorie).order_by(Categorie.ordre, Categorie.nom).all()


def _tracer(session: Session, utilisateur, action: str, objet_type: str,
            objet_id, details: dict) -> None:
    """
    Trace un changement de **configuration** (§22.48).

    Les documents, les comptes et les exports étaient tracés ; le classement, non.
    Un champ attendu disparu ne se datait donc pas, ne s'attribuait pas, et ne
    s'expliquait pas — on l'a constaté à nos dépens. Ce qui décide de la façon
    dont le foyer range ses papiers mérite exactement le même journal que ce
    qu'on y range.
    """
    audit.journaliser(session, utilisateur, action, objet_type, objet_id, details=details)


@router.post("/categories", response_model=CategorieOut, dependencies=[Depends(exiger("reglages"))])
def creer(categorie: CategorieIn, session: Session = Depends(get_session),
          utilisateur: Utilisateur = Depends(auth.get_current_user)):
    _verifier_parent(None, categorie.parent_id, session)
    donnees = categorie.model_dump()
    donnees["nature"] = _nature_validee(categorie.nature)
    _refuser_si(lambda: natures.verifier_parent(session, categorie.parent_id))
    souhaite = donnees.pop("dossier_depot", None)
    obj = Categorie(**donnees)
    session.add(obj)
    session.flush()
    _attribuer_depot(session, obj, souhaite)
    _tracer(session, utilisateur, "categorie.creation", "categorie", obj.id,
            {"nom": obj.nom, "nature": obj.nature, "parent_id": obj.parent_id,
             "dossier_depot": obj.dossier_depot})
    session.commit()
    session.refresh(obj)
    return obj


@router.put("/categories/{categorie_id}", response_model=CategorieOut, dependencies=[Depends(exiger("reglages"))])
def modifier(categorie_id: int, categorie: CategorieIn, session: Session = Depends(get_session),
             utilisateur: Utilisateur = Depends(auth.get_current_user)):
    obj = session.get(Categorie, categorie_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    _verifier_parent(categorie_id, categorie.parent_id, session)
    donnees = categorie.model_dump()
    donnees["nature"] = _nature_validee(categorie.nature)
    _refuser_si(lambda: natures.verifier_parent(session, categorie.parent_id))
    _refuser_si(lambda: natures.verifier_changement(session, obj, donnees["nature"]))
    souhaite = donnees.pop("dossier_depot", None)
    ancien_depot = obj.dossier_depot
    avant = {"nom": obj.nom, "nature": obj.nature, "parent_id": obj.parent_id,
             "dossier_depot": ancien_depot}
    for cle, valeur in donnees.items():
        setattr(obj, cle, valeur)
    _attribuer_depot(session, obj, souhaite, ancien=ancien_depot)
    _tracer(session, utilisateur, "categorie.modification", "categorie", obj.id,
            {"avant": avant, "apres": {"nom": obj.nom, "nature": obj.nature,
                                       "parent_id": obj.parent_id,
                                       "dossier_depot": obj.dossier_depot}})
    session.commit()
    session.refresh(obj)
    return obj


@router.delete("/categories/{categorie_id}", dependencies=[Depends(exiger("reglages"))])
def supprimer(categorie_id: int, session: Session = Depends(get_session),
              utilisateur: Utilisateur = Depends(auth.get_current_user)):
    obj = session.get(Categorie, categorie_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    # L'état est relevé **avant** la suppression : après, il n'y a plus rien à
    # décrire, et c'est précisément ce qu'on voudra relire.
    # Le dossier de dépôt part avec le type (§22.88) : le laisser en place ferait
    # croire à un point d'entrée vivant que plus rien ne réclame. Il reste s'il
    # contient encore des fichiers — ceux-là n'ont pas été lus.
    sort_du_depot = depots.retirer(obj.dossier_depot)
    _tracer(session, utilisateur, "categorie.suppression", "categorie", obj.id,
            {"nom": obj.nom, "nature": obj.nature, "parent_id": obj.parent_id,
             "dossier_depot": obj.dossier_depot, "depot": sort_du_depot})
    session.delete(obj)
    session.commit()
    return {"ok": True, "depot": sort_du_depot}


# ------------------------------------------------------------
# Colonnes du tableau, par catégorie (§18.1)
# ------------------------------------------------------------

class ColonneTableauIn(BaseModel):
    champ: str
    libelle: Optional[str] = None
    largeur: Optional[int] = None
    visible: bool = True


@router.get("/categories/{categorie_id}/colonnes", dependencies=[Depends(exiger("reglages"))])
def lister_colonnes(categorie_id: int, session: Session = Depends(get_session)):
    """
    Ce qui est configuré pour cette catégorie, et ce qui s'affiche réellement.

    Les deux sont renvoyés : sans les colonnes déduites, l'écran de réglage
    n'aurait rien à proposer tant que rien n'est configuré — or c'est justement
    l'état de départ de toute catégorie.
    """
    if not session.get(Categorie, categorie_id):
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    reglages = (
        session.query(ColonneCategorie)
        .filter(ColonneCategorie.categorie_id == categorie_id)
        .order_by(ColonneCategorie.ordre, ColonneCategorie.id)
        .all()
    )
    return {
        "configurees": [
            {"champ": c.champ, "libelle": c.libelle, "largeur": c.largeur, "visible": c.visible}
            for c in reglages
        ],
        "effectives": colonnes.pour_categorie(session, categorie_id),
        "disponibles": colonnes.champs_proposables(session, categorie_id),
        # Tri d'ouverture (§18.49) : ce que la catégorie déclare, et ce qui
        # s'applique réellement une fois l'héritage résolu. Les deux, pour la
        # même raison que les colonnes — l'écran doit pouvoir montrer ce qui a
        # lieu même quand rien n'est déclaré.
        "tri": {"champ": session.get(Categorie, categorie_id).tri_champ,
                "sens": session.get(Categorie, categorie_id).tri_sens},
        "tri_effectif": colonnes.tri_pour(session, categorie_id),
        # Ce que la fiche d'un document de ce type montre en plus du tableau
        # (§19.21) : ce réglage vit ici parce qu'il commande les mêmes colonnes.
        "fiche": {"champs_masques":
                  bool(session.get(Categorie, categorie_id).fiche_champs_masques)},
    }


@router.post("/categories/{categorie_id}/colonnes/propager", dependencies=[Depends(exiger("reglages"))])
def propager_colonnes(
    categorie_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Applique les colonnes et le tri de ce type à tous les types de son dossier (§19.7).

    Remplace l'héritage retiré au même paragraphe, et ne s'y substitue pas
    exactement : **c'est une copie, faite une fois, à la demande**. Les types
    touchés gardent ensuite leur vie propre — modifier celui-ci ne les changera
    plus. C'est tout l'intérêt : un réglage qu'on déclenche se voit dans le
    journal et se défait type par type, là où un héritage se découvrait au
    mauvais moment.

    Tous les types du dossier sont servis, y compris ceux qui avaient déjà leurs
    colonnes : écraser est le sens même de l'action — s'en abstenir la rendrait
    inutile dès la seconde fois, c'est-à-dire précisément quand on cherche à
    harmoniser.
    """
    source = session.get(Categorie, categorie_id)
    if not source:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    _refuser_si(lambda: natures.exiger_type(session, categorie_id, "de colonnes"))
    if not source.parent_id:
        raise HTTPException(
            status_code=400,
            detail=f"« {source.nom} » n'est dans aucun dossier : il n'y a personne à qui "
                   f"appliquer ces colonnes.")

    modele = (session.query(ColonneCategorie)
              .filter(ColonneCategorie.categorie_id == categorie_id)
              .order_by(ColonneCategorie.ordre, ColonneCategorie.id).all())
    if not modele:
        raise HTTPException(
            status_code=400,
            detail="Ce type n'a pas de colonnes configurées : enregistrez-les d'abord.")

    familles = ids_categorie_et_descendants(session, source.parent_id)
    cibles = [c for c in session.query(Categorie).filter(Categorie.id.in_(familles))
              if c.id != categorie_id and natures.porte_des_documents(c)]
    if not cibles:
        raise HTTPException(
            status_code=400,
            detail="Ce dossier ne contient aucun autre type de document.")

    for cible in cibles:
        session.query(ColonneCategorie).filter(
            ColonneCategorie.categorie_id == cible.id).delete(synchronize_session=False)
        for rang, ligne in enumerate(modele):
            session.add(ColonneCategorie(
                categorie_id=cible.id, champ=ligne.champ, libelle=ligne.libelle,
                largeur=ligne.largeur, visible=ligne.visible, ordre=rang))
        cible.tri_champ = source.tri_champ
        cible.tri_sens = source.tri_sens

    audit.journaliser(session, user, "categorie.colonnes_propagees", "categorie", categorie_id,
                      details={"depuis": source.nom, "vers": [c.nom for c in cibles],
                               "colonnes": [ligne.champ for ligne in modele]})
    session.commit()
    return {"ok": True, "types": [c.nom for c in cibles]}


class TriIn(BaseModel):
    champ: Optional[str] = None      # vide : la catégorie hérite
    sens: Optional[str] = None       # 'asc' | 'desc'


@router.put("/categories/{categorie_id}/tri", dependencies=[Depends(exiger("reglages"))])
def enregistrer_tri(
    categorie_id: int,
    payload: TriIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Tri d'ouverture du registre pour cette catégorie (§18.49).

    Un champ vide n'efface pas le tri, il le rend à l'héritage : le parent, puis
    le réglage général du foyer. C'est la même façon de revenir en arrière que
    pour les colonnes — on retire ce qu'on a déclaré, on ne déclare pas le
    contraire.
    """
    categorie = session.get(Categorie, categorie_id)
    if not categorie:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    _refuser_si(lambda: natures.exiger_type(session, categorie_id, "de tri propre"))

    champ = (payload.champ or "").strip() or None
    sens = (payload.sens or "").strip().lower() or None
    if sens and sens not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="Le sens du tri vaut « asc » ou « desc ».")
    if champ:
        try:
            moteur_filtres.valider_champ(session, champ)
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=400, detail=str(erreur))
    elif sens:
        # un sens sans colonne ne trie rien : le refuser vaut mieux que
        # l'enregistrer et laisser chercher pourquoi il ne se passe rien
        raise HTTPException(
            status_code=400,
            detail="Choisissez une colonne à trier, ou laissez le tri hérité.")

    categorie.tri_champ = champ
    categorie.tri_sens = sens if champ else None
    audit.journaliser(session, user, "categorie.tri", "categorie", categorie_id,
                      details={"champ": champ, "sens": categorie.tri_sens})
    session.commit()
    return {"tri_effectif": colonnes.tri_pour(session, categorie_id)}


class OptionsFicheIn(BaseModel):
    champs_masques: bool = False


@router.put("/categories/{categorie_id}/fiche", dependencies=[Depends(exiger("reglages"))])
def enregistrer_options_fiche(
    categorie_id: int,
    payload: OptionsFicheIn,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Les colonnes retirées du tableau se voient-elles sur la fiche ? (§19.21)

    Le réglage a d'abord été posé dans le profil de chacun, et c'était la
    mauvaise porte : retirer une colonne est une décision d'administration, prise
    pour un type et pour tout le foyer. Laisser chacun la contourner de son côté
    rendait le réglage d'administration illisible — deux personnes n'avaient plus
    la même fiche sous les yeux.

    Il se règle donc là où l'on règle les colonnes, et pour le même type.
    """
    categorie = session.get(Categorie, categorie_id)
    if not categorie:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    _refuser_si(lambda: natures.exiger_type(session, categorie_id, "de colonnes"))

    categorie.fiche_champs_masques = bool(payload.champs_masques)
    audit.journaliser(session, user, "categorie.fiche", "categorie", categorie_id,
                      details={"champs_masques": categorie.fiche_champs_masques})
    session.commit()
    return {"champs_masques": categorie.fiche_champs_masques}


@router.put("/categories/{categorie_id}/colonnes", dependencies=[Depends(exiger("reglages"))])
def enregistrer_colonnes(
    categorie_id: int,
    liste: list[ColonneTableauIn],
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Remplace la configuration d'une catégorie. L'ordre reçu **est** l'ordre
    affiché : le rang dans la liste devient `ordre`, ce qui évite de faire
    manipuler des numéros à qui ne veut que déplacer une colonne.

    Une liste vide n'est pas une erreur : elle rend la catégorie à ses colonnes
    déduites, ce qui est la façon la plus simple de revenir en arrière.

    **Et une liste vide est acceptée même sur un dossier** (§22.47). Le refus
    porte sur ce qu'on *pose* : un dossier organise le classement, il n'affiche
    aucun tableau. Mais l'appliquer aussi au retrait enfermait dans un état qu'on
    ne pouvait plus quitter — des colonnes héritées d'avant la nature des
    catégories (§19.1) restaient là, impossibles à recréer *et* impossibles à
    enlever. Un garde-fou qui empêche de réparer n'est pas un garde-fou.
    """
    if not session.get(Categorie, categorie_id):
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    if liste:
        _refuser_si(lambda: natures.exiger_type(session, categorie_id, "de colonnes"))

    vus = set()
    for colonne in liste:
        champ = (colonne.champ or "").strip()
        if not champ:
            raise HTTPException(status_code=400, detail="Une colonne sans champ n'a rien à afficher")
        if champ in vus:
            raise HTTPException(status_code=400, detail=f"La colonne « {champ} » est présente deux fois")
        vus.add(champ)
        try:
            moteur_filtres.valider_champ(session, champ)
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=400, detail=str(erreur))

    session.query(ColonneCategorie).filter(
        ColonneCategorie.categorie_id == categorie_id
    ).delete(synchronize_session=False)
    for rang, colonne in enumerate(liste):
        session.add(ColonneCategorie(
            categorie_id=categorie_id,
            champ=colonne.champ.strip(),
            libelle=(colonne.libelle or "").strip() or None,
            largeur=colonne.largeur,
            visible=colonne.visible,
            ordre=rang,
        ))
    audit.journaliser(session, user, "categorie.colonnes", "categorie", categorie_id,
                      details={"colonnes": [c.champ for c in liste if c.visible]})
    session.commit()
    return {"effectives": colonnes.pour_categorie(session, categorie_id)}


# ------------------------------------------------------------
# Règles d'extraction (champs remplis automatiquement)
# ------------------------------------------------------------

class JeuIn(BaseModel):
    """Jeu de règles d'extraction, propre à un type de document (§19.6)."""
    categorie_id: int
    nom: str
    reconnaissance: Optional[str] = None
    generique: bool = False
    actif: bool = True
    priorite: int = 100


class JeuOut(JeuIn):
    id: int
    nb_regles: int = 0

    model_config = ConfigDict(from_attributes=True)


def _serialize_jeu(profil: ProfilExtraction, nb_regles: int = 0) -> JeuOut:
    return JeuOut(
        id=profil.id, categorie_id=profil.categorie_id, nom=profil.nom,
        reconnaissance=profil.reconnaissance,
        generique=bool(profil.generique), actif=bool(profil.actif),
        priorite=profil.priorite, nb_regles=nb_regles,
    )


def _valider_jeu(payload: "JeuIn", session: Session, jeu_id: Optional[int] = None) -> None:
    """
    Un jeu doit pouvoir être choisi, et un seul doit pouvoir l'être à défaut.

    Trois refus, chacun contre un réglage qui ne ferait rien sans le dire :
    un jeu attaché à un dossier de classement (il ne reçoit aucun document), un
    jeu ni générique ni reconnaissable (il ne s'appliquerait jamais), et un
    second jeu générique sur le même type (on ne saurait pas lequel sert de
    repli).
    """
    _refuser_si(lambda: natures.exiger_type(session, payload.categorie_id,
                                            "de règles d'extraction"))
    motif = (payload.reconnaissance or "").strip()
    if motif:
        _valider_regex(motif, "L'expression de reconnaissance")
    elif not payload.generique:
        raise HTTPException(
            status_code=422,
            detail="Sans expression de reconnaissance, ce jeu ne serait jamais choisi. "
                   "Donnez-lui une expression, ou faites-en le jeu générique du type.")

    if payload.generique:
        autre = (session.query(ProfilExtraction)
                 .filter(ProfilExtraction.categorie_id == payload.categorie_id,
                         ProfilExtraction.generique.is_(True),
                         ProfilExtraction.id != (jeu_id or 0))
                 .first())
        if autre:
            raise HTTPException(
                status_code=409,
                detail=f"« {autre.nom} » est déjà le jeu générique de ce type. Il ne peut "
                       f"y en avoir qu'un : c'est celui qui s'applique quand aucun autre "
                       f"n'est reconnu.")


@router.get("/jeux-extraction", response_model=list[JeuOut], dependencies=[Depends(exiger("reglages"))])
def lister_jeux(categorie_id: Optional[int] = None, session: Session = Depends(get_session)):
    query = session.query(ProfilExtraction)
    if categorie_id:
        query = query.filter(ProfilExtraction.categorie_id == categorie_id)
    profils = query.order_by(ProfilExtraction.categorie_id,
                             ProfilExtraction.priorite, ProfilExtraction.id).all()
    comptes = dict(
        session.query(RegleExtraction.profil_id, func.count(RegleExtraction.id))
        .group_by(RegleExtraction.profil_id).all())
    return [_serialize_jeu(p, comptes.get(p.id, 0)) for p in profils]


@router.post("/jeux-extraction", response_model=JeuOut, dependencies=[Depends(exiger("reglages"))])
def creer_jeu(payload: JeuIn, session: Session = Depends(get_session),
              utilisateur: Utilisateur = Depends(auth.get_current_user)):
    _valider_jeu(payload, session)
    profil = ProfilExtraction(**payload.model_dump())
    session.add(profil)
    session.flush()
    _tracer(session, utilisateur, "jeu_extraction.creation", "jeu_extraction", profil.id,
            {"nom": profil.nom, "categorie_id": profil.categorie_id,
             "reconnaissance": profil.reconnaissance})
    session.commit()
    session.refresh(profil)
    return _serialize_jeu(profil)


@router.put("/jeux-extraction/{jeu_id}", response_model=JeuOut, dependencies=[Depends(exiger("reglages"))])
def modifier_jeu(jeu_id: int, payload: JeuIn, session: Session = Depends(get_session),
                 utilisateur: Utilisateur = Depends(auth.get_current_user)):
    profil = session.get(ProfilExtraction, jeu_id)
    if not profil:
        raise HTTPException(status_code=404, detail="Jeu de règles introuvable")
    _valider_jeu(payload, session, jeu_id)
    _tracer(session, utilisateur, "jeu_extraction.modification", "jeu_extraction", profil.id,
            {"avant": {"nom": profil.nom, "actif": profil.actif,
                       "reconnaissance": profil.reconnaissance},
             "apres": {"nom": payload.nom, "actif": payload.actif,
                       "reconnaissance": payload.reconnaissance}})
    for cle, valeur in payload.model_dump().items():
        setattr(profil, cle, valeur)
    session.commit()
    session.refresh(profil)
    return _serialize_jeu(profil, len(profil.regles))


@router.delete("/jeux-extraction/{jeu_id}", dependencies=[Depends(exiger("reglages"))])
def supprimer_jeu(jeu_id: int, session: Session = Depends(get_session),
                  utilisateur: Utilisateur = Depends(auth.get_current_user)):
    """Le jeu part avec ses règles : elles n'existaient que par lui."""
    profil = session.get(ProfilExtraction, jeu_id)
    if not profil:
        raise HTTPException(status_code=404, detail="Jeu de règles introuvable")
    nombre = len(profil.regles)
    _tracer(session, utilisateur, "jeu_extraction.suppression", "jeu_extraction", profil.id,
            {"nom": profil.nom, "categorie_id": profil.categorie_id,
             "regles_supprimees": nombre,
             # Les règles partent avec lui : les nommer est le seul moyen de
             # savoir, plus tard, ce qui a disparu.
             "regles": [{"nom": r.nom, "champ_cible": r.champ_cible,
                         "pattern": r.pattern, "fonction": r.fonction}
                        for r in profil.regles]})
    session.delete(profil)
    session.commit()
    return {"ok": True, "regles_supprimees": nombre}


class RegleIn(BaseModel):
    profil_id: int
    nom: str
    champ_cible: str
    # Facultatif depuis §18.35 : une règle peut s'appuyer sur une fonction prête
    # à l'emploi (« première date », « montant TTC ») qui cherche d'elle-même.
    pattern: Optional[str] = None
    fonction: Optional[str] = None
    # Valeur dont la fonction a besoin (§21.4) : les jours d'une échéance, le
    # séparateur d'une concaténation.
    parametre: Optional[str] = None
    type_champ: str = "texte"
    priorite: int = 100
    actif: bool = True


class RegleOut(RegleIn):
    id: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/regles", response_model=list[RegleOut], dependencies=[Depends(exiger("reglages"))])
def lister_regles(profil_id: Optional[int] = None, session: Session = Depends(get_session)):
    """
    Les règles d'un jeu. Sans jeu précisé, toutes — ce qui ne sert qu'au
    diagnostic : l'écran, lui, en montre un jeu à la fois, et c'est le but du
    §19.6 (« ça permettrait d'en avoir moins à l'écran »).
    """
    query = session.query(RegleExtraction)
    if profil_id:
        query = query.filter(RegleExtraction.profil_id == profil_id)
    return query.order_by(RegleExtraction.priorite, RegleExtraction.id).all()


def _valider_regle(regle: "RegleIn") -> None:
    """
    Une règle doit pouvoir trouver quelque chose : une expression, une fonction
    qui cherche, ou les deux. Sans l'un ni l'autre, elle ne s'appliquerait
    jamais — et rien à l'écran ne dirait pourquoi.
    """
    motif = (regle.pattern or "").strip()
    fonction = (regle.fonction or "").strip() or None

    if fonction and not extraction_fonctions.connue(fonction):
        raise HTTPException(
            status_code=422,
            detail=f"Fonction « {fonction} » inconnue "
                   f"(attendu : {', '.join(sorted(extraction_fonctions.CATALOGUE))}).")
    # Un paramètre attendu et manquant se dirait autrement : la règle
    # s'appliquerait sans rien rendre, et l'écran n'en montrerait pas la raison.
    if extraction_fonctions.attend_un_parametre(fonction) and not (regle.parametre or "").strip():
        details = extraction_fonctions.CATALOGUE[fonction]["parametre"]
        raise HTTPException(
            status_code=422,
            detail=f"La fonction « {extraction_fonctions.CATALOGUE[fonction]['libelle']} » "
                   f"attend une valeur : {details['libelle'].lower()} "
                   f"(exemple : « {details['exemple']} »).")
    if fonction == "ajouter_jours" and (regle.parametre or "").strip():
        try:
            int(regle.parametre.strip())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Le décalage s'exprime en nombre de jours : « 30 », ou « -7 » "
                       "pour reculer.")
    if motif:
        _valider_regex(motif, "Le motif de la règle")
    elif not extraction_fonctions.est_extracteur(fonction):
        raise HTTPException(
            status_code=422,
            detail="Sans expression régulière, choisissez une fonction qui cherche "
                   "d'elle-même — « Première date du document » ou « Montant TTC ». "
                   "Les autres ne font que transformer ce qu'une expression a trouvé.")


@router.get("/regles/champs-cibles", dependencies=[Depends(exiger("reglages"))])
def champs_cibles(categorie_id: Optional[int] = None,
                  session: Session = Depends(get_session)):
    """
    Ce qu'une règle peut remplir, pour ce type de document (§21.11).

    La colonne cible se tapait à l'aveugle : une faute de frappe créait une
    métadonnée jumelle — `montant_ttc` et `montant_tt` — que rien ne signalait,
    et l'on cherchait ensuite pourquoi la colonne restait vide. Les propositions
    viennent de ce que le foyer a déjà nommé :

      * les **champs attendus** du type — ce qu'un administrateur a déclaré ;
      * ses **colonnes de tableau** — ce qu'il a choisi de montrer ;
      * les cibles des **autres règles** du type, y compris celles d'un autre jeu ;
      * `date_document`, qui n'est pas une métadonnée mais la date du document
        elle-même : c'est le seul nom que le moteur traite à part.

    Rien n'est imposé : le champ reste libre, un nouveau nom s'écrit toujours.
    Proposer n'est pas restreindre — c'est éviter de deviner.
    """
    from .filtres import PREFIXE_META

    propositions: dict[str, str] = {}

    def ajouter(cle: str, origine: str):
        propre = (cle or "").strip()
        if propre and propre not in propositions:
            propositions[propre] = origine

    ajouter("date_document", "date du document")

    champs = session.query(RegleChampCategorie)
    colonnes_type = session.query(ColonneCategorie)
    regles = (session.query(RegleExtraction)
              .join(ProfilExtraction, RegleExtraction.profil_id == ProfilExtraction.id))
    if categorie_id:
        champs = champs.filter(RegleChampCategorie.categorie_id == categorie_id)
        colonnes_type = colonnes_type.filter(ColonneCategorie.categorie_id == categorie_id)
        # Les jeux de **ce type** — génériques ou non : c'est un jeu générique
        # qui remplit la plupart des champs, et l'exclure faisait dire « saisi à
        # la main » de ce que la machine écrivait déjà (§22.16). Ceux d'un autre
        # type, en revanche, ne s'appliquent pas ici : les compter envoyait le
        # raccourci « aller à la règle » vers la règle d'un voisin (§22.28).
        regles = regles.filter(or_(ProfilExtraction.categorie_id == categorie_id,
                                   ProfilExtraction.categorie_id.is_(None)))

    for regle in champs:
        if regle.champ.startswith(PREFIXE_META):
            ajouter(regle.champ[len(PREFIXE_META):], "champ attendu")
    for colonne in colonnes_type:
        if colonne.champ.startswith(PREFIXE_META):
            ajouter(colonne.champ[len(PREFIXE_META):], "colonne du tableau")
    # Ce qu'une règle vise, indépendamment de l'origine retenue : un champ
    # attendu **et** ciblé par une règle garde « champ attendu » comme origine —
    # c'est ce qui se lit le mieux dans la liste —, mais l'écran d'assemblage a
    # besoin de savoir qu'il se remplit tout seul (§22.16).
    # Et **quelles** règles le visent : savoir qu'un champ se remplit tout seul
    # ne dit pas où aller quand il se remplit mal (§22.28). Une seule suffit à
    # ouvrir le bon écran ; les autres sont rendues pour que l'appelant puisse le
    # dire s'il y en a plusieurs.
    cibles_de_regles: dict[str, list] = {}
    for regle in regles:
        ajouter(regle.champ_cible, "déjà ciblé par une règle")
        if regle.champ_cible:
            cibles_de_regles.setdefault(regle.champ_cible.strip(), []).append(
                {"id": regle.id, "nom": regle.nom, "profil_id": regle.profil_id})

    return [{"champ": cle, "origine": origine,
             "remplie_par_regle": cle in cibles_de_regles,
             "regles": cibles_de_regles.get(cle, [])}
            for cle, origine in propositions.items()]


@router.get("/regles/fonctions", dependencies=[Depends(exiger("reglages"))])
def lister_fonctions_extraction():
    """Fonctions proposées dans l'écran des règles (§18.35)."""
    return extraction_fonctions.decrire()


# Où vivent les documents importés pour apprendre une règle (§22.35). Sous le
# dossier des dépôts manuels, seul endroit où l'API écrive un fichier reçu — et
# purgé par le serveur de travaux : ce sont des brouillons, pas des archives.
DOSSIER_APPRENTISSAGE = "apprentissage"


def _dossier_apprentissage() -> Path:
    return Path(config.DEPOTS_MANUELS_FOLDER) / DOSSIER_APPRENTISSAGE


@router.get("/regles/exemples", dependencies=[Depends(exiger("reglages"))])
def exemples_de_documents(q: str = "", categorie_id: Optional[int] = None,
                          limite: int = 20, session: Session = Depends(get_session)):
    """
    Les documents sur lesquels apprendre une règle (§22.35, §22.36, §22.37).

    Le périmètre est **le type en cours d'édition**, quand il est donné : neuf
    fois sur dix, la règle qu'on écrit pour « Factures » se montre sur une
    facture, et voir passer les bulletins de paie ne rend service à personne.
    Sans `categorie_id`, c'est toute la GED — l'écran laisse élargir d'un clic,
    parce que le document qu'on a sous la main n'est pas toujours rangé là où la
    règle servira.

    Mêmes économies que les autres sélecteurs (§22.26) : **le dernier mois** sans
    rien taper, et une recherche à partir de trois caractères.

    La recherche est celle de la recherche globale (§21.2) — **peu importe la
    colonne** : l'émetteur, le nom du fichier, le classement, les champs
    extraits, le texte reconnu et les choses désignées. Chercher « Clio » doit
    ramener la facture du garage, qui ne contient nulle part ce mot-là.

    Quand une recherche ne donne rien **dans le type**, la réponse dit combien de
    documents elle aurait trouvés ailleurs : sans ce nombre, « aucun résultat »
    laisse croire que le document n'existe pas, alors qu'il est à un clic.
    """
    terme = (q or "").strip()
    assez = len(terme) >= 3
    plafond = max(1, min(limite, 50))
    ids_du_type = None
    if categorie_id is not None:
        if not session.get(Categorie, categorie_id):
            raise HTTPException(status_code=404, detail="Catégorie introuvable")
        ids_du_type = ids_categorie_et_descendants(session, categorie_id)

    def vivants():
        query = session.query(Document.id).filter(Document.date_suppression.is_(None))
        return query.filter(Document.categorie_id.in_(ids_du_type)) if ids_du_type else query

    ailleurs = 0
    if assez:
        trouvailles = moteur_recherche.chercher(session, vivants(), terme, limite=plafond)
        if not trouvailles and ids_du_type:
            # Rien ici : reste à dire si c'est « nulle part » ou « pas ici ».
            ailleurs = len(moteur_recherche.chercher(
                session,
                session.query(Document.id).filter(Document.date_suppression.is_(None)),
                terme, limite=plafond))
        identifiants = [t["document_id"] for t in trouvailles]
        par_id = {d.id: d for d in session.query(Document)
                  .options(joinedload(Document.categorie))
                  .filter(Document.id.in_(identifiants))} if identifiants else {}
        # L'ordre est celui du moteur — le plus pertinent d'abord — et non celui
        # de la base : le remettre par date perdrait tout le classement.
        trouves = [par_id[i] for i in identifiants if i in par_id]
    else:
        query = (session.query(Document)
                 .options(joinedload(Document.categorie))
                 .filter(Document.date_suppression.is_(None),
                         Document.date_import >= datetime.now() - timedelta(days=30)))
        if ids_du_type:
            query = query.filter(Document.categorie_id.in_(ids_du_type))
        trouves = (query.order_by(Document.date_import.desc(), Document.id.desc())
                   .limit(plafond).all())

    return {
        "recents": not assez,
        "jours_recents": 30,
        "minimum_recherche": 3,
        "ailleurs": ailleurs,
        "documents": [{"id": d.id, "nom_fichier": d.nom_fichier,
                       "categorie": d.categorie.nom if d.categorie else None,
                       "date_document": str(d.date_document) if d.date_document else None,
                       "date_import": d.date_import.isoformat(timespec="seconds")
                       if d.date_import else None}
                      for d in trouves],
    }


@router.post("/regles/exemple-importe", dependencies=[Depends(exiger("reglages"))])
def importer_un_exemple(fichier: UploadFile = File(...),
                        session: Session = Depends(get_session),
                        utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Océrise un fichier **sans l'archiver**, pour apprendre une règle dessus
    (§22.35).

    Le cas est celui d'un papier qu'on vient de recevoir et dont aucun exemplaire
    n'est encore dans la GED : écrire la règle d'abord évite de déposer un
    document pour le voir mal lu, corriger, redéposer.

    Rien n'entre au registre : le fichier est océrisé dans un dossier de passage,
    on en rend le texte et la position des mots, et le serveur de travaux efface
    ce dossier au bout de deux heures. C'est un brouillon, pas une archive.
    """
    from . import apercus, mots, worker
    from .ocr import extraire_texte, ocr_to_searchable_pdf

    nom = os.path.basename(fichier.filename or "").strip()
    extension = os.path.splitext(nom)[1].lower()
    if extension not in config.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Format non pris en charge (attendu : "
                   f"{', '.join(sorted(config.SUPPORTED_EXTENSIONS))}).")

    jeton = secrets.token_urlsafe(16)
    dossier = _dossier_apprentissage() / jeton
    dossier.mkdir(parents=True, exist_ok=True)
    recu = dossier / f"recu{extension}"
    try:
        # Même plafond que tout autre dépôt (§22.38) : un fichier reçu est un
        # fichier reçu, et rien ne justifie qu'une porte de l'administration
        # laisse remplir le disque quand les autres comptent les octets.
        taille = 0
        with open(recu, "wb") as sortie:
            while morceau := fichier.file.read(1024 * 1024):
                taille += len(morceau)
                if taille > config.TAILLE_MAX_DEPOT:
                    sortie.close()
                    shutil.rmtree(dossier, ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux (limite : "
                               f"{config.TAILLE_MAX_DEPOT // (1024 * 1024)} Mo).")
                sortie.write(morceau)
    except HTTPException:
        raise
    except OSError as erreur:
        shutil.rmtree(dossier, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Écriture impossible : {erreur}")

    lisible = dossier / "lisible.pdf"
    try:
        ocr_to_searchable_pdf(str(recu), str(lisible),
                              **worker.reglages_traitement(session))
        texte = extraire_texte(str(lisible))
        page = mots.lire(str(lisible)) or {"largeur": 0, "hauteur": 0, "mots": []}
        apercus.rendre(str(lisible), dossier / "apercu.png")
    except Exception as erreur:      # noqa: BLE001 — on rend l'échec, on ne le masque pas
        shutil.rmtree(dossier, ignore_errors=True)
        log.exception("Océrisation de l'exemple impossible")
        raise HTTPException(status_code=422,
                            detail=f"Ce fichier n'a pas pu être lu : {erreur}")

    # Un papier du foyer a été lu par le serveur : cela se journalise, même si
    # rien n'entre au registre.
    audit.journaliser(session, utilisateur, "regle.exemple_importe", "regle", None,
                      details={"nom_fichier": nom})
    session.commit()
    return {"jeton": jeton, "nom_fichier": nom, "texte": texte, "page": page}


@router.get("/regles/exemple-importe/{jeton}/apercu", dependencies=[Depends(exiger("reglages"))])
def apercu_exemple_importe(jeton: str):
    """L'image de la page importée, pour y désigner la valeur à la souris."""
    from . import apercus

    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", jeton or ""):
        raise HTTPException(status_code=404, detail="Exemple introuvable")
    dossier = _dossier_apprentissage() / jeton
    image = dossier / "apercu.png"
    if not image.is_file():
        lisible = dossier / "lisible.pdf"
        if not lisible.is_file():
            raise HTTPException(status_code=404,
                                detail="Cet exemple a expiré. Réimportez le fichier.")
        if not apercus.rendre(str(lisible), image):
            raise HTTPException(status_code=404, detail="Aperçu indisponible.")
    return FileResponse(str(image), media_type="image/png")


class ApprentissageIn(BaseModel):
    # L'un ou l'autre : un document du registre, ou le texte d'un exemple qu'on
    # vient d'importer et qui n'entrera pas dans la GED (§22.35).
    document_id: Optional[int] = None
    texte: Optional[str] = None
    valeur: str
    # L'intitulé qui annonce la valeur. Facultatif : sans lui on le déduit de la
    # ligne, mais celui qui règle **voit** le document et sait mieux.
    ancre: Optional[str] = None
    champ_cible: Optional[str] = None


@router.post("/regles/apprendre", dependencies=[Depends(exiger("reglages"))])
def apprendre_une_regle(payload: ApprentissageIn, session: Session = Depends(get_session)):
    """
    Propose une règle à partir d'une valeur désignée sur un document (§21.5, bêta).

    Rien n'est enregistré : on rend la proposition **et ce qu'elle extrait de ce
    document-ci**. C'est la vérification qui manquait — elle avait lieu après
    l'enregistrement et après un retraitement, ce qui décourageait d'essayer.
    """
    from . import apprentissage

    if payload.document_id:
        document = session.get(Document, payload.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document introuvable")
        texte = document.texte_ocr or ""
    elif payload.texte:
        texte = payload.texte
    else:
        raise HTTPException(status_code=422,
                            detail="Indiquez un document du registre ou importez un exemple.")
    proposition = apprentissage.proposer(texte, payload.valeur,
                                         payload.ancre, payload.champ_cible)
    if "erreur" in proposition:
        raise HTTPException(status_code=422, detail=proposition["erreur"])
    return proposition


@router.post("/regles", response_model=RegleOut, dependencies=[Depends(exiger("reglages"))])
def creer_regle(regle: RegleIn, session: Session = Depends(get_session),
                utilisateur: Utilisateur = Depends(auth.get_current_user)):
    if not session.get(ProfilExtraction, regle.profil_id):
        raise HTTPException(status_code=404, detail="Jeu de règles introuvable")
    _valider_regle(regle)
    obj = RegleExtraction(**regle.model_dump())
    session.add(obj)
    session.flush()
    _tracer(session, utilisateur, "regle_extraction.creation", "regle_extraction", obj.id,
            {"nom": obj.nom, "profil_id": obj.profil_id, "champ_cible": obj.champ_cible,
             "pattern": obj.pattern, "fonction": obj.fonction})
    session.commit()
    session.refresh(obj)
    return obj


@router.put("/regles/{regle_id}", response_model=RegleOut, dependencies=[Depends(exiger("reglages"))])
def modifier_regle(regle_id: int, regle: RegleIn, session: Session = Depends(get_session),
                   utilisateur: Utilisateur = Depends(auth.get_current_user)):
    obj = session.get(RegleExtraction, regle_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Règle introuvable")
    _valider_regle(regle)
    avant = {"nom": obj.nom, "champ_cible": obj.champ_cible, "pattern": obj.pattern,
             "fonction": obj.fonction, "actif": obj.actif}
    for cle, valeur in regle.model_dump().items():
        setattr(obj, cle, valeur)
    _tracer(session, utilisateur, "regle_extraction.modification", "regle_extraction", obj.id,
            {"avant": avant,
             "apres": {"nom": obj.nom, "champ_cible": obj.champ_cible,
                       "pattern": obj.pattern, "fonction": obj.fonction, "actif": obj.actif}})
    session.commit()
    session.refresh(obj)
    return obj


@router.delete("/regles/{regle_id}", dependencies=[Depends(exiger("reglages"))])
def supprimer_regle(regle_id: int, session: Session = Depends(get_session),
                    utilisateur: Utilisateur = Depends(auth.get_current_user)):
    obj = session.get(RegleExtraction, regle_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Règle introuvable")
    _tracer(session, utilisateur, "regle_extraction.suppression", "regle_extraction", obj.id,
            {"nom": obj.nom, "profil_id": obj.profil_id, "champ_cible": obj.champ_cible,
             "pattern": obj.pattern, "fonction": obj.fonction})
    session.delete(obj)
    session.commit()
    return {"ok": True}


# ------------------------------------------------------------
# Règles de champs par catégorie (§15)
#
# Chaque catégorie déclare les champs attendus sur ses documents. `champ`
# reprend le vocabulaire du moteur de filtres, ce qui rend le dispositif
# générique : toute métadonnée extraite (`meta:<cle>`) devient exigible sans
# modification du code.
# ------------------------------------------------------------

class RegleChampIn(BaseModel):
    categorie_id: int
    champ: str
    source_table: Optional[str] = None   # première source (compatibilité)
    sources: list[str] = []              # toutes les sources du champ (§17.28)
    libelle: Optional[str] = None
    obligatoire: bool = True
    # Ce champ identifie-t-il un document de cette catégorie ? (§18.40) C'est ce
    # qui permet de reconnaître la même pièce redéposée, et donc de l'ajouter
    # comme version plutôt que comme fiche nouvelle.
    identifiant: bool = False
    # Déduction automatique depuis le texte du document (§18.47). Rien n'est
    # déduit tant qu'un administrateur ne l'a pas déclaré ici.
    deduction: str = "aucune"          # 'aucune' | 'toutes' | 'une'
    colonnes_deduction: list[str] = []  # colonnes cherchées ; vide = les identifiantes
    # Ce qui se lit de la ligne choisie (§22.59). Vide : les colonnes
    # identifiantes de la table, comme avant.
    colonnes_affichees: list[str] = []
    # Tolérer une lettre de différence entre le document et la table (§21.4) :
    # utile sur un nom, dangereux sur une immatriculation.
    deduction_approchee: bool = False
    # Ce champ porte-t-il une date qui arrive à terme, et combien de jours avant
    # veut-on être prévenu ? (§21.9)
    echeance: bool = False
    rappel_jours: Optional[int] = None
    # Le champ contient des **documents de la GED**, choisis dans une liste
    # (§22.11) : « Factures liées », « Devis reçus ». Il ne se saisit pas, il se
    # remplit en piochant dans ce qui est déjà classé.
    attache_documents: bool = False
    # Comment le champ se saisit (§22.12) : texte, texte_long, date, nombre,
    # montant, booleen. Sans lui, l'écran devinait d'après le nom de la clé.
    type_champ: str = "texte"
    # Ce qu'un champ « documents » accepte (§22.14) : le type qu'on peut y
    # attacher, et les champs où la recherche cherche. Vides : tout type,
    # recherche sur le nom et le texte reconnu.
    documents_categorie_id: Optional[int] = None
    documents_champs: list[str] = []
    # Ce champ attend-il une règle d'extraction ? (§22.27) C'est ce qui distingue
    # « saisi à la main » de « règle à écrire » dans l'écran d'assemblage.
    extraction_attendue: bool = False
    ordre: int = 100


class RegleChampOut(RegleChampIn):
    id: int
    libelle_effectif: str

    model_config = ConfigDict(from_attributes=True)


def _serialize_regle_champ(regle: RegleChampCategorie) -> RegleChampOut:
    return RegleChampOut(
        id=regle.id, categorie_id=regle.categorie_id, champ=regle.champ,
        source_table=regle.source_table,
        sources=conformite.sources_de(regle),
        libelle=regle.libelle, obligatoire=bool(regle.obligatoire),
        # `identifiant` doit repartir avec le reste : l'écran d'administration
        # renvoie la règle entière quand on en modifie un morceau. Absent d'ici,
        # il revenait à `False` et effaçait en silence le critère de versionnage.
        identifiant=bool(regle.identifiant),
        deduction=regle.deduction or "aucune",
        colonnes_deduction=[c.strip() for c in (regle.colonnes_deduction or "").split(",")
                            if c.strip()],
        colonnes_affichees=[c.strip() for c in (regle.colonnes_affichees or "").split(",")
                            if c.strip()],
        deduction_approchee=bool(regle.deduction_approchee),
        echeance=bool(regle.echeance),
        rappel_jours=regle.rappel_jours,
        attache_documents=bool(regle.attache_documents),
        type_champ=regle.type_champ or "texte",
        documents_categorie_id=regle.documents_categorie_id,
        documents_champs=[c.strip() for c in (regle.documents_champs or "").split(",")
                          if c.strip()],
        extraction_attendue=bool(regle.extraction_attendue),
        ordre=regle.ordre,
        libelle_effectif=regle.libelle or conformite.libelle_par_defaut(regle.champ),
    )


def _valider_sources(payload: "RegleChampIn", champ: str, session: Session) -> dict:
    """
    Valide les sources d'un champ et rend `{source_table, sources}`.

    Un champ peut en déclarer plusieurs (§17.28) : le titulaire d'une facture
    peut être un compte de la GED ou une personne du foyer qui n'en a pas. La
    première déclarée compte double — c'est elle qui interprète une valeur
    enregistrée sans préfixe, avant que les sources multiples n'existent.

    `source_table` reste accepté seul, pour ne pas casser ce qui l'utilise.
    """
    declarees = [s.strip() for s in (payload.sources or []) if s and s.strip()]
    if not declarees and payload.source_table:
        declarees = [payload.source_table.strip()]
    if not declarees:
        return {"source_table": None, "sources": None}

    validees = [_valider_source(source, champ, session) for source in declarees]
    return {"source_table": validees[0], "sources": ",".join(validees)}


def _valider_deduction(payload: "RegleChampIn", sources: dict, session: Session) -> dict:
    """
    Valide ce que le champ déclare chercher dans les documents (§18.47), et rend
    `{deduction, colonnes_deduction}`.

    Deux refus, tous deux pour éviter un réglage qui ne ferait rien sans le dire :
    un mode inconnu, et une déduction demandée sur un champ qui n'a aucune source
    où chercher. Une colonne absente de toutes les sources est refusée pour la
    même raison — elle serait ignorée en silence.
    """
    mode = (payload.deduction or "aucune").strip()
    if mode not in references_auto.MODES:
        raise HTTPException(400, f"Mode de déduction inconnu : « {mode} ».")
    if mode == "aucune":
        return {"deduction": "aucune", "colonnes_deduction": None}

    declarees = [c.strip() for c in (payload.colonnes_deduction or []) if c and c.strip()]
    tables = [t for t in (sources.get("sources") or "").split(",") if t]
    if not tables:
        raise HTTPException(
            400, "La déduction automatique demande une table source où chercher.")

    if declarees:
        connues = set()
        for table in tables:
            connues |= {c["nom"] for c in base_donnees.colonnes(session, table)}
        inconnues = [c for c in declarees if c not in connues]
        if inconnues:
            raise HTTPException(
                400, "Colonnes absentes des tables sources : " + ", ".join(inconnues))

    return {"deduction": mode, "colonnes_deduction": ",".join(declarees) or None}


def _valider_affichage(payload: "RegleChampIn", sources: dict, session: Session) -> dict:
    """
    Valide ce qui se lit de la ligne choisie (§22.59), et rend
    `{colonnes_affichees}`.

    Vide veut dire « comme la table le déclare » : c'est l'état de tout champ
    existant, et celui vers lequel on revient en décochant tout. Une colonne
    absente des sources est refusée plutôt qu'ignorée — un réglage qui ne fait
    rien sans le dire se cherche longtemps.
    """
    declarees = [c.strip() for c in (payload.colonnes_affichees or []) if c and c.strip()]
    if not declarees:
        return {"colonnes_affichees": None}

    tables = [t for t in (sources.get("sources") or "").split(",") if t]
    if not tables:
        raise HTTPException(
            400, "Choisir les valeurs affichées demande une table source.")

    connues = set()
    for table in tables:
        connues |= {c["nom"] for c in base_donnees.colonnes(session, table)}
    inconnues = [c for c in declarees if c not in connues]
    if inconnues:
        raise HTTPException(
            400, "Colonnes absentes des tables sources : " + ", ".join(inconnues))

    return {"colonnes_affichees": ",".join(declarees)}


def _valider_source(source_table: Optional[str], champ: str, session: Session) -> Optional[str]:
    """
    Une table source ne se déclare que sur un champ `meta:` : les champs propres
    au document (émetteur, date...) ont déjà leur propre nature.

    Une seule sorte de source : une table de données du foyer (§18.13). Les
    comptes de connexion l'ont été un temps ; ils ne le sont plus, parce qu'une
    table du système ne se règle pas depuis l'administration et qu'un autre foyer
    aurait hérité de ce couplage sans pouvoir y toucher.
    """
    if not source_table:
        return None
    if not champ.startswith(moteur_filtres.PREFIXE_META):
        raise HTTPException(
            status_code=422,
            detail="Une table source ne peut être associée qu'à un champ personnalisé (meta:…).",
        )
    if not base_donnees.est_table_donnees(session, source_table.strip()):
        raise HTTPException(
            status_code=422,
            detail=f"« {source_table} » n'est pas une table de données utilisable comme source.",
        )
    return source_table.strip()


def _valider_champ(champ: str, session: Session) -> str:
    """
    Vérifie qu'on exige un champ qui existe réellement. Sans ce contrôle, une
    faute de frappe créerait une règle jamais satisfaite, et bloquerait tous les
    documents de la catégorie.
    """
    champ = (champ or "").strip()
    if not champ:
        raise HTTPException(status_code=422, detail="Le champ est obligatoire")
    connus = {c["champ"] for c in moteur_filtres.champs_disponibles(session)}
    if champ not in connus and not champ.startswith(moteur_filtres.PREFIXE_META):
        raise HTTPException(
            status_code=422,
            detail=f"Champ « {champ} » inconnu. Champs disponibles : {', '.join(sorted(connus))}",
        )
    return champ


@router.get("/types-de-champ", dependencies=[Depends(exiger("reglages"))])
def lister_types_de_champ():
    """Ce qu'un champ libre peut être (§22.12) : c'est le type qui décide de la
    façon dont il se saisit et se relit."""
    return [{"valeur": cle, "libelle": libelle}
            for cle, libelle in conformite.TYPES_CHAMP.items()]


@router.get("/champs-disponibles", dependencies=[Depends(exiger("reglages"))])
def lister_champs_disponibles(session: Session = Depends(get_session)):
    """
    Champs sur lesquels une règle peut porter, métadonnées extraites comprises :
    l'interface d'administration n'a ainsi aucune liste codée en dur.
    """
    return moteur_filtres.champs_disponibles(session)


@router.get("/regles-champs", response_model=list[RegleChampOut], dependencies=[Depends(exiger("reglages"))])
def lister_regles_champs(categorie_id: Optional[int] = None, session: Session = Depends(get_session)):
    query = session.query(RegleChampCategorie)
    if categorie_id is not None:
        query = query.filter_by(categorie_id=categorie_id)
    regles = query.order_by(RegleChampCategorie.categorie_id, RegleChampCategorie.ordre).all()
    return [_serialize_regle_champ(r) for r in regles]


def _rendre_conformite(session: Session, categorie_id: Optional[int]) -> None:
    """
    Repose l'état de conformité des documents d'une catégorie (§22.41).

    Changer les champs attendus rend non conformes des documents déjà indexés,
    sans que personne ne repasse dessus — c'est précisément le cas qui
    interdisait de se fier au statut, et donc ce qui obligeait à tout recalculer
    à chaque lecture. Le recalcul est ciblé : cette catégorie et ses
    sous-catégories, une requête, pas un document à la fois.
    """
    if not categorie_id:
        return
    ids = ids_categorie_et_descendants(session, categorie_id)
    changes = conformite.recalculer(session, ids)
    session.commit()
    if changes:
        log.info("Conformité reposée sur %s document(s) de la catégorie %s",
                 changes, categorie_id)


@router.post("/regles-champs", response_model=RegleChampOut, dependencies=[Depends(exiger("reglages"))])
def creer_regle_champ(payload: RegleChampIn, session: Session = Depends(get_session),
                      utilisateur: Utilisateur = Depends(auth.get_current_user)):
    if not session.get(Categorie, payload.categorie_id):
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    _refuser_si(lambda: natures.exiger_type(session, payload.categorie_id, "de champs attendus"))
    champ = _valider_champ(payload.champ, session)
    sources = _valider_sources(payload, champ, session)
    if session.query(RegleChampCategorie).filter_by(
        categorie_id=payload.categorie_id, champ=champ
    ).first():
        raise HTTPException(status_code=409, detail="Ce champ est déjà réglé pour cette catégorie")

    obj = RegleChampCategorie(**{
        **payload.model_dump(exclude={"sources", "colonnes_deduction", "colonnes_affichees",
                                     "type_champ", "documents_champs"}),
        "type_champ": conformite.valider_type(payload.type_champ),
        "documents_champs": ",".join(payload.documents_champs) or None,
        "champ": champ, **sources, **_valider_deduction(payload, sources, session),
        **_valider_affichage(payload, sources, session)})
    session.add(obj)
    session.flush()
    _tracer(session, utilisateur, "champ_attendu.creation", "champ_attendu", obj.id,
            {"categorie_id": obj.categorie_id, "champ": obj.champ, "libelle": obj.libelle,
             "obligatoire": bool(obj.obligatoire), "source_table": obj.source_table,
             "deduction": obj.deduction})
    session.commit()
    session.refresh(obj)
    _rendre_conformite(session, obj.categorie_id)
    return _serialize_regle_champ(obj)


@router.put("/regles-champs/{regle_id}", response_model=RegleChampOut, dependencies=[Depends(exiger("reglages"))])
def modifier_regle_champ(regle_id: int, payload: RegleChampIn,
                         session: Session = Depends(get_session),
                         utilisateur: Utilisateur = Depends(auth.get_current_user)):
    obj = session.get(RegleChampCategorie, regle_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Règle introuvable")
    if not session.get(Categorie, payload.categorie_id):
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    _refuser_si(lambda: natures.exiger_type(session, payload.categorie_id, "de champs attendus"))
    champ = _valider_champ(payload.champ, session)

    doublon = session.query(RegleChampCategorie).filter(
        RegleChampCategorie.categorie_id == payload.categorie_id,
        RegleChampCategorie.champ == champ,
        RegleChampCategorie.id != regle_id,
    ).first()
    if doublon:
        raise HTTPException(status_code=409, detail="Ce champ est déjà réglé pour cette catégorie")

    sources = _valider_sources(payload, champ, session)
    avant = {"champ": obj.champ, "libelle": obj.libelle,
             "obligatoire": bool(obj.obligatoire), "source_table": obj.source_table,
             "deduction": obj.deduction}
    for cle, valeur in {**payload.model_dump(exclude={"sources", "colonnes_deduction",
                                                     "colonnes_affichees",
                                                     "type_champ", "documents_champs"}),
                        "type_champ": conformite.valider_type(payload.type_champ),
                        "documents_champs": ",".join(payload.documents_champs) or None,
                        "champ": champ, **sources,
                        **_valider_deduction(payload, sources, session),
                        **_valider_affichage(payload, sources, session)}.items():
        setattr(obj, cle, valeur)
    _tracer(session, utilisateur, "champ_attendu.modification", "champ_attendu", obj.id,
            {"avant": avant,
             "apres": {"champ": obj.champ, "libelle": obj.libelle,
                       "obligatoire": bool(obj.obligatoire),
                       "source_table": obj.source_table, "deduction": obj.deduction}})
    session.commit()
    session.refresh(obj)
    _rendre_conformite(session, obj.categorie_id)
    return _serialize_regle_champ(obj)


@router.delete("/regles-champs/{regle_id}", dependencies=[Depends(exiger("reglages"))])
def supprimer_regle_champ(regle_id: int, session: Session = Depends(get_session),
                          utilisateur: Utilisateur = Depends(auth.get_current_user)):
    obj = session.get(RegleChampCategorie, regle_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Règle introuvable")
    categorie_id = obj.categorie_id
    # Relevé avant l'effacement : c'est ce relevé qui manquait le jour où un
    # champ attendu a disparu sans qu'on puisse dire quand ni par qui (§22.48).
    _tracer(session, utilisateur, "champ_attendu.suppression", "champ_attendu", obj.id,
            {"categorie_id": categorie_id, "champ": obj.champ, "libelle": obj.libelle,
             "obligatoire": bool(obj.obligatoire), "source_table": obj.source_table,
             "sources": obj.sources, "deduction": obj.deduction,
             "colonnes_deduction": obj.colonnes_deduction,
             "colonnes_affichees": obj.colonnes_affichees,
             "deduction_approchee": bool(obj.deduction_approchee),
             "ordre": obj.ordre, "identifiant": bool(obj.identifiant)})
    session.delete(obj)
    session.commit()
    # Un champ retiré rend conformes des documents qui ne l'étaient pas : sans ce
    # recalcul, ils resteraient au Centre d'analyse sans qu'on sache pourquoi.
    _rendre_conformite(session, categorie_id)
    return {"ok": True}


# ------------------------------------------------------------
# Utilisateurs
# ------------------------------------------------------------

class UtilisateurIn(BaseModel):
    email: str
    # Exigés d'un compte ordinaire, facultatifs pour un administrateur (§17.20) :
    # la règle est appliquée par `_verifier_identite`, pas par le type.
    nom: Optional[str] = None
    prenom: Optional[str] = None
    mot_de_passe: Optional[str] = None  # requis à la création, optionnel en modification
    est_admin: bool = False
    actif: bool = True
    otp_impose: bool = False   # l'administrateur exige la double authentification
    role_ids: list[int] = []


class UtilisateurOut(BaseModel):
    id: int
    email: str
    nom: Optional[str] = None
    prenom: Optional[str] = None
    nom_affiche: str           # « Prénom Nom », ou l'adresse à défaut
    est_admin: bool
    actif: bool
    roles: list[str]
    otp_actif: bool = False    # l'utilisateur l'a configurée
    otp_impose: bool = False   # un administrateur l'exige

    model_config = ConfigDict(from_attributes=True)


def _verifier_identite(payload: "UtilisateurIn") -> None:
    """
    Un compte ordinaire doit porter un prénom et un nom : ce sont eux qui
    permettent de le reconnaître dans le foyer, et de rapprocher un document
    d'une personne. Un administrateur en est dispensé — c'est un rôle de
    gestion, pas une personne du foyer, et son adresse suffit à le désigner.
    """
    if payload.est_admin:
        return
    for champ, valeur in (("prénom", payload.prenom), ("nom", payload.nom)):
        if not (valeur or "").strip():
            raise HTTPException(
                status_code=422,
                detail=f"Le {champ} est obligatoire pour un compte non administrateur.",
            )


def _serialize_utilisateur(u: Utilisateur) -> UtilisateurOut:
    return UtilisateurOut(
        id=u.id, email=u.email, nom=u.nom, prenom=u.prenom, nom_affiche=u.nom_affiche,
        est_admin=u.est_admin, actif=u.actif,
        roles=[r.nom for r in u.roles],
        otp_actif=bool(u.otp_actif), otp_impose=bool(u.otp_impose),
    )


@router.get("/utilisateurs", response_model=list[UtilisateurOut], dependencies=[Depends(exiger("comptes"))])
def lister_utilisateurs(session: Session = Depends(get_session)):
    utilisateurs = (session.query(Utilisateur).options(joinedload(Utilisateur.roles))
                    .order_by(Utilisateur.nom, Utilisateur.email).all())
    return [_serialize_utilisateur(u) for u in utilisateurs]


@router.post("/consultation/{utilisateur_id}", dependencies=[Depends(exiger("comptes"))])
def ouvrir_consultation(
    utilisateur_id: int,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Ouvre une consultation du registre sous l'identité d'un autre compte (§18.50).

    Régler des droits sans pouvoir vérifier ce qu'ils donnent à voir, c'est
    régler à l'aveugle. Cette consultation est **en lecture seule** et dure une
    demi-heure ; le jeton rendu ne vaut que pour l'administrateur qui l'a
    demandé, et n'ouvre pas de session.

    Tracé ici, une fois : le journal doit dire qui a consulté qui, et quand.
    """
    if not user.est_admin:
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")

    cible = session.get(Utilisateur, utilisateur_id)
    if not cible:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    if not cible.actif:
        raise HTTPException(
            status_code=400,
            detail="Ce compte est désactivé : il ne verrait rien, et cela ne prouverait rien.")
    if cible.id == user.id:
        raise HTTPException(
            status_code=400, detail="C'est déjà ce que vous voyez.")

    audit.journaliser(session, user, "consultation.ouverte", "utilisateur", cible.id,
                      details={"compte": cible.email,
                               "duree_minutes": auth.DUREE_CONSULTATION_MINUTES})
    session.commit()
    return {
        "jeton": auth.creer_token_consultation(cible.email, user.id),
        "utilisateur": {"id": cible.id, "email": cible.email,
                        "nom": cible.nom, "prenom": cible.prenom,
                        "est_admin": bool(cible.est_admin)},
        "duree_minutes": auth.DUREE_CONSULTATION_MINUTES,
    }


@router.post("/utilisateurs", response_model=UtilisateurOut, dependencies=[Depends(exiger("comptes"))])
def creer_utilisateur(payload: UtilisateurIn, session: Session = Depends(get_session),
                     auteur: Utilisateur = Depends(auth.require_admin)):
    if session.query(Utilisateur).filter_by(email=payload.email).first():
        raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")
    if not payload.mot_de_passe:
        raise HTTPException(status_code=422, detail="Un mot de passe est requis à la création")
    _verifier_identite(payload)

    utilisateur = Utilisateur(
        email=payload.email,
        nom=(payload.nom or "").strip() or None,
        prenom=(payload.prenom or "").strip() or None,
        mot_de_passe_hash=auth.hash_mot_de_passe(payload.mot_de_passe),
        est_admin=payload.est_admin,
        actif=payload.actif,
        otp_impose=payload.otp_impose,
    )
    if payload.role_ids:
        utilisateur.roles = session.query(Role).filter(Role.id.in_(payload.role_ids)).all()

    session.add(utilisateur)
    session.flush()
    # jamais le mot de passe, ni son empreinte : le journal est consultable
    audit.journaliser(session, auteur, "utilisateur.creation", "utilisateur", utilisateur.id,
                      details={"email": utilisateur.email, "nom": utilisateur.nom_affiche,
                               "est_admin": utilisateur.est_admin, "actif": utilisateur.actif,
                               "roles": [r.nom for r in utilisateur.roles]})
    session.commit()
    session.refresh(utilisateur)
    return _serialize_utilisateur(utilisateur)


@router.post("/utilisateurs/{utilisateur_id}/otp/reinitialiser", response_model=UtilisateurOut, dependencies=[Depends(exiger("comptes"))])
def reinitialiser_double_authentification(utilisateur_id: int,
                                          session: Session = Depends(get_session),
                                          auteur: Utilisateur = Depends(auth.require_admin)):
    """
    Retire le second facteur d'un compte : le téléphone est perdu et les codes
    de secours avec.

    C'est un pouvoir réel — il ramène le compte au mot de passe seul — donc il
    est journalisé nommément. Si la double authentification est imposée sur ce
    compte, l'exigence demeure : l'utilisateur devra en appairer une nouvelle
    à sa prochaine connexion, et n'aura accès à rien d'autre d'ici là.
    """
    utilisateur = session.get(Utilisateur, utilisateur_id)
    if not utilisateur:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    utilisateur.otp_actif = False
    utilisateur.otp_secret = None
    utilisateur.otp_codes_secours = None
    audit.journaliser(session, auteur, "utilisateur.otp_reinitialise", "utilisateur", utilisateur.id,
                      details={"email": utilisateur.email,
                               "reste_imposee": bool(utilisateur.otp_impose)})
    session.commit()
    session.refresh(utilisateur)
    return _serialize_utilisateur(utilisateur)


@router.put("/utilisateurs/{utilisateur_id}", response_model=UtilisateurOut, dependencies=[Depends(exiger("comptes"))])
def modifier_utilisateur(utilisateur_id: int, payload: UtilisateurIn,
                        session: Session = Depends(get_session),
                        auteur: Utilisateur = Depends(auth.require_admin)):
    utilisateur = session.get(Utilisateur, utilisateur_id)
    if not utilisateur:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    doublon = session.query(Utilisateur).filter(
        Utilisateur.email == payload.email, Utilisateur.id != utilisateur_id
    ).first()
    if doublon:
        raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")

    # rétrograder ou désactiver le dernier administrateur actif = plus aucun
    # accès possible à l'administration
    if not payload.est_admin or not payload.actif:
        _refuser_perte_dernier_admin(session, utilisateur)

    avant = {"email": utilisateur.email, "nom": utilisateur.nom_affiche,
             "est_admin": utilisateur.est_admin, "actif": utilisateur.actif,
             "otp_impose": utilisateur.otp_impose,
             "roles": [r.nom for r in utilisateur.roles]}

    _verifier_identite(payload)
    utilisateur.email = payload.email
    utilisateur.nom = (payload.nom or "").strip() or None
    utilisateur.prenom = (payload.prenom or "").strip() or None
    utilisateur.est_admin = payload.est_admin
    utilisateur.actif = payload.actif
    utilisateur.otp_impose = payload.otp_impose
    if payload.mot_de_passe:
        utilisateur.mot_de_passe_hash = auth.hash_mot_de_passe(payload.mot_de_passe)
    utilisateur.roles = session.query(Role).filter(Role.id.in_(payload.role_ids)).all()

    session.flush()
    audit.journaliser(session, auteur, "utilisateur.modification", "utilisateur", utilisateur.id,
                      details={"avant": avant,
                               "apres": {"email": utilisateur.email, "nom": utilisateur.nom_affiche,
                                         "est_admin": utilisateur.est_admin, "actif": utilisateur.actif,
                                         "otp_impose": utilisateur.otp_impose,
                                         "roles": [r.nom for r in utilisateur.roles]},
                               "mot_de_passe_change": bool(payload.mot_de_passe)})
    session.commit()
    session.refresh(utilisateur)
    return _serialize_utilisateur(utilisateur)


@router.delete("/utilisateurs/{utilisateur_id}", dependencies=[Depends(exiger("comptes"))])
def supprimer_utilisateur(utilisateur_id: int, session: Session = Depends(get_session),
                         auteur: Utilisateur = Depends(auth.require_admin)):
    utilisateur = session.get(Utilisateur, utilisateur_id)
    if not utilisateur:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    _refuser_perte_dernier_admin(session, utilisateur)
    audit.journaliser(session, auteur, "utilisateur.suppression", "utilisateur", utilisateur.id,
                      details={"email": utilisateur.email, "nom": utilisateur.nom_affiche,
                               "est_admin": utilisateur.est_admin,
                               "roles": [r.nom for r in utilisateur.roles]})
    session.delete(utilisateur)
    session.commit()
    return {"ok": True}


# ------------------------------------------------------------
# Rôles et droits par catégorie
# ------------------------------------------------------------

class DroitIn(BaseModel):
    """Ce qu'un rôle peut faire sur une catégorie (§19.12), action par action."""
    categorie_id: int
    peut_voir: bool = True
    peut_modifier: bool = False
    peut_deposer: bool = False
    peut_telecharger: bool = True
    peut_supprimer: bool = False
    peut_gerer_versions: bool = False


class RoleIn(BaseModel):
    nom: str
    description: Optional[str] = None


class DroitOut(DroitIn):
    model_config = ConfigDict(from_attributes=True)


class RoleOut(BaseModel):
    id: int
    nom: str
    description: Optional[str] = None
    droits: list[DroitOut]
    # Droits hors catégorie (§19.12) : Centre d'analyse, serveur de travaux…
    generaux: list[str] = []
    # Vues enregistrées réservées à ce rôle. Vide : aucune restriction posée.
    vues: list[int] = []
    # Branches auxquelles ce rôle est restreint (§21.7). Vide : aucune.
    branches: list[dict] = []

    model_config = ConfigDict(from_attributes=True)


def _serialize_role(r: Role) -> RoleOut:
    return RoleOut(
        id=r.id, nom=r.nom, description=r.description,
        generaux=sorted(d.droit for d in r.droits_generaux),
        vues=sorted(d.vue_id for d in r.droits_vue),
        branches=[{"champ": d.champ, "valeur": d.valeur}
                  for d in sorted(r.droits_branche, key=lambda x: (x.champ, x.valeur))],
        droits=[DroitOut(categorie_id=d.categorie_id, peut_voir=d.peut_voir,
                         peut_modifier=d.peut_modifier, peut_deposer=d.peut_deposer,
                         peut_telecharger=d.peut_telecharger, peut_supprimer=d.peut_supprimer,
                         peut_gerer_versions=d.peut_gerer_versions)
                for d in r.droits_categorie],
    )


@router.get("/roles", response_model=list[RoleOut], dependencies=[Depends(exiger("comptes"))])
def lister_roles(session: Session = Depends(get_session)):
    roles = session.query(Role).options(joinedload(Role.droits_categorie)).order_by(Role.nom).all()
    return [_serialize_role(r) for r in roles]


@router.post("/roles", response_model=RoleOut, dependencies=[Depends(exiger("comptes"))])
def creer_role(payload: RoleIn, session: Session = Depends(get_session),
               auteur: Utilisateur = Depends(auth.require_admin)):
    if session.query(Role).filter_by(nom=payload.nom).first():
        raise HTTPException(status_code=409, detail="Ce rôle existe déjà")
    role = Role(nom=payload.nom, description=payload.description)
    session.add(role)
    session.flush()
    audit.journaliser(session, auteur, "role.creation", "role", role.id, details={"nom": role.nom})
    session.commit()
    session.refresh(role)
    return _serialize_role(role)


@router.delete("/roles/{role_id}", dependencies=[Depends(exiger("comptes"))])
def supprimer_role(role_id: int, session: Session = Depends(get_session),
                   auteur: Utilisateur = Depends(auth.require_admin)):
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rôle introuvable")
    audit.journaliser(session, auteur, "role.suppression", "role", role.id,
                      details={"nom": role.nom,
                               "comptes_concernes": [u.email for u in role.utilisateurs]})
    session.delete(role)
    session.commit()
    return {"ok": True}


class BrancheIn(BaseModel):
    champ: str
    valeur: str


class DroitsRole(BaseModel):
    """Les droits d'un rôle, en un seul envoi : ils se lisent et se règlent ensemble."""
    categories: list[DroitIn] = []
    generaux: list[str] = []
    vues: list[int] = []
    # Restrictions par branche (§21.7) : « ce rôle ne voit que 2025 et 2026 ».
    branches: list[BrancheIn] = []


@router.put("/roles/{role_id}/droits", response_model=RoleOut,
            dependencies=[Depends(exiger("comptes"))])
def definir_droits(role_id: int, payload: DroitsRole,
                   session: Session = Depends(get_session),
                   auteur: Utilisateur = Depends(auth.get_current_user)):
    """
    Remplace **entièrement** les droits du rôle (§19.12).

    Tout en un seul envoi, et non trois : les trois axes se règlent sur le même
    écran, et un enregistrement partiel laisserait un rôle à moitié changé si le
    second appel échouait.

    Une catégorie sans ligne n'est pas « interdite » : elle est **héritée** de
    son dossier. C'est ce qui permet d'ouvrir un dossier sans revenir cocher
    chacun de ses types à chaque type ajouté.
    """
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Rôle introuvable")

    inconnus = [d for d in payload.generaux if d not in droits.GENERAUX]
    if inconnus:
        raise HTTPException(
            status_code=422,
            detail=f"Droits généraux inconnus : {', '.join(inconnus)}.")

    avant = {
        "categories": [{"categorie_id": d.categorie_id, "peut_voir": d.peut_voir,
                        "peut_modifier": d.peut_modifier, "peut_deposer": d.peut_deposer,
                        "peut_telecharger": d.peut_telecharger,
                        "peut_supprimer": d.peut_supprimer,
                        "peut_gerer_versions": d.peut_gerer_versions}
                       for d in role.droits_categorie],
        "generaux": sorted(d.droit for d in role.droits_generaux),
        "vues": sorted(d.vue_id for d in role.droits_vue),
        "branches": sorted((d.champ, d.valeur) for d in role.droits_branche),
    }
    audit.journaliser(session, auteur, "role.droits_modifies", "role", role.id,
                      details={"role": role.nom, "avant": avant,
                               "apres": payload.model_dump()})

    # Une branche déclarée sur un champ qui n'existe pas ne se manifesterait
    # qu'à l'usage — et sous la forme d'un registre vide, ce qui ne se
    # diagnostique pas.
    for branche in payload.branches:
        try:
            groupes.champ_valide(session, branche.champ)
        except moteur_filtres.FiltreInvalide as erreur:
            raise HTTPException(status_code=422, detail=str(erreur))

    session.query(DroitCategorie).filter_by(role_id=role_id).delete()
    session.query(DroitGeneral).filter_by(role_id=role_id).delete()
    session.query(DroitVue).filter_by(role_id=role_id).delete()
    session.query(DroitBranche).filter_by(role_id=role_id).delete()
    for droit in payload.categories:
        session.add(DroitCategorie(role_id=role_id, **droit.model_dump()))
    for nom in sorted(set(payload.generaux)):
        session.add(DroitGeneral(role_id=role_id, droit=nom))
    for vue_id in sorted(set(payload.vues)):
        if session.get(VueEnregistree, vue_id):
            session.add(DroitVue(role_id=role_id, vue_id=vue_id))
    for champ, valeur in sorted({(b.champ.strip(), str(b.valeur).strip())
                                 for b in payload.branches if b.champ and b.valeur}):
        session.add(DroitBranche(role_id=role_id, champ=champ, valeur=valeur))
    session.commit()
    session.refresh(role)
    return _serialize_role(role)


@router.get("/droits/catalogue", dependencies=[Depends(exiger("comptes"))])
def catalogue_des_droits():
    """
    Ce qui existe comme droit, tel que le code le déclare (§19.12).

    L'écran des rôles s'en sert pour composer sa grille : une liste tenue à
    l'écran finirait par proposer un droit que rien ne vérifie, ou en oublier un
    que le code exige.
    """
    return {
        "actions": [{"cle": cle, "libelle": libelle}
                    for cle, (_, libelle) in droits.ACTIONS.items()],
        "generaux": [{"cle": cle, "libelle": libelle}
                     for cle, libelle in droits.GENERAUX.items()],
    }


# ------------------------------------------------------------
# Journal d'audit (§14)
#
# Aucune entrée n'est modifiable, et aucune ne se supprime individuellement :
# un journal dont on peut retirer *une* ligne ne prouve plus rien, puisque
# c'est précisément celle qui gêne qui disparaîtrait.
#
# Seule concession, pour que le journal ne grossisse pas indéfiniment : une
# purge en bloc de tout ce qui précède une date. Elle ne permet pas de choisir
# ce qu'on efface, elle coupe la queue de l'historique — et elle est
# elle-même journalisée, avec la date retenue et le nombre d'entrées perdues.
# La trace de l'effacement survit à l'effacement.
# ------------------------------------------------------------

class EvenementAuditOut(BaseModel):
    id: int
    date_evenement: Optional[str] = None
    utilisateur: Optional[str] = None      # e-mail conservé même si le compte est supprimé
    action: str
    objet_type: str
    objet_id: Optional[int] = None
    details: Optional[dict] = None


class PageAuditOut(BaseModel):
    total: int
    evenements: list[EvenementAuditOut]
    # Les noms des documents que cette page mentionne (§22.64). Le journal ne
    # retient que des identifiants — c'est ce qui le rend fiable, un nom change —
    # mais « Document nº108 modifié » n'apprend rien à qui n'a pas la
    # numérotation en tête. On les résout ici, en une requête pour la page.
    documents: dict[int, str] = {}


def _serialize_evenement(evenement: JournalAudit) -> EvenementAuditOut:
    details = None
    if evenement.details:
        try:
            details = json.loads(evenement.details)
        except (ValueError, TypeError):
            details = {"brut": evenement.details}
    return EvenementAuditOut(
        id=evenement.id,
        date_evenement=evenement.date_evenement.isoformat(timespec="seconds")
        if evenement.date_evenement else None,
        utilisateur=evenement.utilisateur_email,
        action=evenement.action,
        objet_type=evenement.objet_type,
        objet_id=evenement.objet_id,
        details=details,
    )


@router.get("/audit/actions", dependencies=[Depends(exiger("journal"))])
def lister_actions_auditees(session: Session = Depends(get_session)):
    """Actions et types d'objets réellement présents dans le journal, pour les filtres."""
    return {
        "actions": sorted(a for (a,) in session.query(JournalAudit.action).distinct() if a),
        "objets": sorted(o for (o,) in session.query(JournalAudit.objet_type).distinct() if o),
    }


def _jour_ou_422(valeur: str):
    """Une date AAAA-MM-JJ, ou une erreur qui dit ce qui était attendu."""
    from datetime import datetime
    try:
        return datetime.strptime(valeur.strip(), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422,
                            detail=f"Date « {valeur} » attendue au format AAAA-MM-JJ")


def _purgeables(session: Session, jour):
    """
    Entrées que la purge peut emporter.

    **L'histoire des documents en est exclue** (§17.24) : elle se lit depuis la
    fiche de chaque document, par tous ceux qui y ont accès, et sert à répondre
    des années plus tard à « d'où sort cette valeur ? ». La purge existe pour
    empêcher le journal d'enfler indéfiniment, pas pour amputer les documents de
    leur passé — et ces entrées-là sont peu nombreuses au regard du reste.
    """
    return (
        session.query(JournalAudit)
        .filter(JournalAudit.date_evenement < jour)
        .filter(JournalAudit.objet_type != "document")
    )


class ApercuPurgeOut(BaseModel):
    """Ce que la purge emporterait, avant qu'on ne la déclenche."""
    avant: str
    nombre: int
    plus_ancien: Optional[str] = None
    plus_recent: Optional[str] = None
    conserves: int


def _borne_de_purge(avant: str):
    """
    Valide la date de coupure. Elle ne peut pas dépasser aujourd'hui : les
    événements du jour — dont la purge elle-même — doivent survivre, sinon
    l'opération effacerait sa propre trace.
    """
    from datetime import datetime
    jour = _jour_ou_422(avant)
    minuit = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if jour > minuit:
        raise HTTPException(
            status_code=422,
            detail="La date de coupure ne peut pas être postérieure à aujourd'hui : "
                   "les événements du jour sont toujours conservés.",
        )
    return jour


@router.get("/audit/purge-apercu", response_model=ApercuPurgeOut, dependencies=[Depends(exiger("journal"))])
def apercu_purge_audit(avant: str, session: Session = Depends(get_session)):
    """
    Ce que la purge emporterait : combien d'entrées, et sur quelle période.
    Consulté avant confirmation — on ne valide pas une suppression en bloc sans
    savoir ce qu'elle contient.

    L'histoire des documents n'y figure pas : elle est conservée quoi qu'il
    arrive (cf. `_purgeables`).
    """
    jour = _borne_de_purge(avant)
    concernes = _purgeables(session, jour)
    nombre = concernes.count()
    plus_ancien = plus_recent = None
    if nombre:
        bornes = concernes.with_entities(
            func.min(JournalAudit.date_evenement), func.max(JournalAudit.date_evenement)
        ).one()
        plus_ancien = bornes[0].isoformat(timespec="seconds") if bornes[0] else None
        plus_recent = bornes[1].isoformat(timespec="seconds") if bornes[1] else None
    return ApercuPurgeOut(
        avant=jour.strftime("%Y-%m-%d"),
        nombre=nombre,
        plus_ancien=plus_ancien,
        plus_recent=plus_recent,
        conserves=session.query(JournalAudit).count() - nombre,
    )


@router.delete("/audit", dependencies=[Depends(exiger("journal"))])
def purger_journal_audit(avant: str, session: Session = Depends(get_session),
                         utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Supprime définitivement toutes les entrées antérieures à la date donnée.

    L'ordre compte : on relève d'abord ce qu'on va perdre, on supprime, puis on
    journalise. La trace de la purge porte une date postérieure à la coupure,
    elle échappe donc à sa propre suppression — c'est ce qui empêche d'effacer
    l'historique sans laisser de trace.
    """
    jour = _borne_de_purge(avant)
    concernes = _purgeables(session, jour)
    nombre = concernes.count()
    plus_ancien = None
    if nombre:
        premier = concernes.with_entities(func.min(JournalAudit.date_evenement)).scalar()
        plus_ancien = premier.isoformat(timespec="seconds") if premier else None

    concernes.delete(synchronize_session=False)
    audit.journaliser(session, utilisateur, "audit.purge", "journal",
                      details={"avant": jour.strftime("%Y-%m-%d"),
                               "entrees_supprimees": nombre,
                               "plus_ancienne_supprimee": plus_ancien})
    session.commit()
    return {"supprimes": nombre}


@router.get("/audit", response_model=PageAuditOut, dependencies=[Depends(exiger("journal"))])
def lister_journal_audit(
    action: Optional[str] = None,
    objet_type: Optional[str] = None,
    objet_id: Optional[int] = None,
    utilisateur: Optional[str] = None,
    depuis: Optional[str] = None,     # AAAA-MM-JJ inclus
    jusqu_a: Optional[str] = None,    # AAAA-MM-JJ inclus
    limite: int = 100,
    decalage: int = 0,
    session: Session = Depends(get_session),
):
    """Journal filtrable et paginé. `total` porte sur le filtre, pas sur la page."""
    from datetime import timedelta

    query = session.query(JournalAudit)
    if action:
        query = query.filter(JournalAudit.action == action)
    if objet_type:
        query = query.filter(JournalAudit.objet_type == objet_type)
    if objet_id is not None:
        query = query.filter(JournalAudit.objet_id == objet_id)
    if utilisateur:
        query = query.filter(JournalAudit.utilisateur_email.like(f"%{utilisateur.strip()}%"))

    for valeur, borne in ((depuis, "depuis"), (jusqu_a, "jusqu_a")):
        if not valeur:
            continue
        jour = _jour_ou_422(valeur)
        if borne == "depuis":
            query = query.filter(JournalAudit.date_evenement >= jour)
        else:
            # borne incluse : tout ce qui s'est passé pendant la journée indiquée
            query = query.filter(JournalAudit.date_evenement < jour + timedelta(days=1))

    total = query.count()
    evenements = (
        query.order_by(JournalAudit.date_evenement.desc(), JournalAudit.id.desc())
        .offset(max(0, decalage))
        .limit(max(1, min(limite, 500)))
        .all()
    )
    lignes = [_serialize_evenement(e) for e in evenements]
    return PageAuditOut(total=total, evenements=lignes,
                        documents=_documents_cites(session, lignes))


def _documents_cites(session: Session, evenements: list) -> dict[int, str]:
    """
    `{id: libellé}` pour tout document que cette page nomme (§22.64).

    Deux endroits le citent : l'objet de l'événement lui-même, et les listes
    d'identifiants que certains détails portent — « documents attachés » en tient
    une. Un document détruit depuis n'a plus de nom : il est simplement absent, et
    l'écran retombe sur son numéro.
    """
    besoins: set[int] = set()
    for evenement in evenements:
        if evenement.objet_type == "document" and evenement.objet_id:
            besoins.add(int(evenement.objet_id))
        for valeur in (evenement.details or {}).values() if isinstance(evenement.details, dict) else []:
            if isinstance(valeur, list):
                besoins |= {int(v) for v in valeur if isinstance(v, int)}
    if not besoins:
        return {}
    return {d.id: d.nom_fichier for d in session.query(Document)
            .filter(Document.id.in_(besoins))}


# ------------------------------------------------------------
# Serveur de travaux (§13)
#
# Suivi des traitements sans avoir à ouvrir un terminal sur le serveur :
# ce qui est en attente, en cours, terminé, en erreur ou bloqué, la raison de
# l'échec, et de quoi relancer.
# ------------------------------------------------------------

# Étapes proposées au rejeu, de la plus coûteuse à la plus légère. Elles
# reprennent les étapes du worker ; « empreinte » signifie « tout refaire depuis
# le fichier source », ce qui n'est possible que si ce fichier existe encore.
ETAPES_REJEU = [
    {"etape": "empreinte", "libelle": "Tout reprendre depuis le fichier source",
     "description": "Nécessite le fichier d'origine (travaux en erreur, fichier en quarantaine)."},
    {"etape": "ocr", "libelle": "Depuis l'OCR",
     "description": "Réocérise le PDF archivé, puis rejoue la suite. Long."},
    {"etape": "extraction", "libelle": "Depuis l'extraction du texte",
     "description": "Relit le texte du PDF sans refaire l'OCR."},
    {"etape": "regles", "libelle": "Depuis les règles d'extraction",
     "description": "Réapplique regex d'émetteur, de catégorie et de champs. Immédiat."},
    {"etape": "conformite", "libelle": "Depuis le contrôle des champs attendus",
     "description": "Recontrôle seulement les champs exigés par la catégorie."},
]
ETAPES_VALIDES = {e["etape"] for e in ETAPES_REJEU}
# `echec` en fait partie : l'abandon est celui de la **machine**, pas celui de
# l'utilisateur (§21.15). Demander un rejeu est un geste délibéré — on a corrigé
# quelque chose —, et il remet les compteurs à zéro.
STATUTS_REJOUABLES = {"erreur", "bloque", "termine", "echec"}


class JobOut(BaseModel):
    id: int
    nom_fichier: str
    statut: str
    etape: Optional[str] = None
    etape_demandee: Optional[str] = None
    tentatives: int
    document_id: Optional[int] = None
    message_erreur: Optional[str] = None
    diagnostic: Optional[str] = None
    chemin_source: Optional[str] = None
    # Le fichier reçu est-il encore consultable ? (§18.53) L'écran s'en sert pour
    # proposer — ou non — l'aperçu de l'original.
    fichier_disponible: bool = False
    rejouer_demande: bool
    rejouable: bool
    etapes_possibles: list[str] = []
    date_creation: Optional[str] = None
    date_fin: Optional[str] = None


def _etapes_possibles(job: Job) -> list[str]:
    """
    Étapes depuis lesquelles ce travail précis peut repartir.

    Sans document produit, il n'y a rien à réanalyser : seule une reprise
    complète depuis le fichier source a un sens. À l'inverse, un travail ayant
    produit un document ne peut repartir « depuis le fichier source » que si
    celui-ci existe encore — après un import réussi, il a été consommé.
    """
    if job.statut not in STATUTS_REJOUABLES:
        return []
    # Le fichier reçu est conservé tant que le travail existe (§18.53) : une
    # reprise complète est donc désormais possible même après un import réussi,
    # ce qui n'était le cas que des échecs mis en quarantaine.
    depuis_le_fichier = ["empreinte"] if _fichier_conserve(job) else []
    if not job.document_id:
        return depuis_le_fichier
    return depuis_le_fichier + ["ocr", "extraction", "regles", "conformite"]


def _fichier_conserve(job: Job) -> Optional[Path]:
    """Le fichier d'origine du travail, s'il est encore là."""
    if not job.chemin_source:
        return None
    chemin = Path(job.chemin_source)
    return chemin if chemin.is_file() else None


@router.get("/jobs/etapes", dependencies=[Depends(exiger("travaux"))])
def lister_etapes_rejeu():
    """Étapes de traitement proposées au rejeu, avec leur coût relatif."""
    return ETAPES_REJEU


def _serialize_job(job: Job) -> JobOut:
    return JobOut(
        id=job.id, nom_fichier=job.nom_fichier, statut=job.statut,
        etape=job.etape, etape_demandee=job.etape_demandee,
        tentatives=job.tentatives or 0, document_id=job.document_id,
        message_erreur=job.message_erreur, diagnostic=job.diagnostic,
        chemin_source=job.chemin_source, fichier_disponible=_fichier_conserve(job) is not None,
        rejouer_demande=bool(job.rejouer_demande),
        # rejouable dès que le traitement est arrêté : un travail terminé se
        # réanalyse utilement après modification d'une regex ou d'un champ attendu.
        # Un doublon ignoré, lui, n'a rien à reprendre.
        rejouable=job.statut in STATUTS_REJOUABLES,
        etapes_possibles=_etapes_possibles(job),
        date_creation=job.date_creation.isoformat(timespec="seconds") if job.date_creation else None,
        date_fin=job.date_fin.isoformat(timespec="seconds") if job.date_fin else None,
    )


# ------------------------------------------------------------
# Le mode développeur (§21.14)
#
# La porte de sortie universelle, autorisée sous condition d'un mode déclaré.
# Réservé aux administrateurs, et refusé tant que l'interrupteur n'est pas armé :
# masquer un bouton ne protège de rien, le contrôle est ici.
# ------------------------------------------------------------

class ScriptIn(BaseModel):
    nom: str
    description: Optional[str] = None
    code: str


class ContexteIn(BaseModel):
    """Ce qu'on donne au script. Explicite, et visible à l'écran avant de lancer."""
    contexte: dict = {}


def _exiger_mode_developpeur(session: Session) -> None:
    try:
        scripts.exiger_mode_actif(session)
    except scripts.ScriptRefuse as refus:
        raise HTTPException(status_code=409, detail=str(refus))


@router.get("/scripts", dependencies=[Depends(exiger("reglages"))])
def lister_scripts(session: Session = Depends(get_session)):
    """
    Les scripts, et l'état du mode. L'état est rendu même quand le mode est
    éteint : c'est ce qui permet à l'écran d'expliquer pourquoi rien ne se lance.
    """
    return {
        "mode_actif": scripts.mode_actif(session),
        "duree_max": scripts.DUREE_MAX,
        "scripts": [{
            "id": s.id, "nom": s.nom, "description": s.description, "code": s.code,
            "date_modification": (s.date_modification or s.date_creation).isoformat(
                timespec="seconds"),
            "par": s.utilisateur.nom_affiche if s.utilisateur else None,
        } for s in session.query(Script).order_by(Script.nom).all()],
    }


@router.post("/scripts", dependencies=[Depends(exiger("reglages"))])
def creer_script(corps: ScriptIn, session: Session = Depends(get_session),
                 utilisateur: Utilisateur = Depends(auth.require_admin)):
    _exiger_mode_developpeur(session)
    try:
        code = scripts.valider(corps.code)
    except scripts.ScriptRefuse as refus:
        raise HTTPException(status_code=422, detail=str(refus))
    if not corps.nom.strip():
        raise HTTPException(status_code=422, detail="Un script se nomme.")

    script = Script(nom=corps.nom.strip(), description=(corps.description or "").strip() or None,
                    code=code, utilisateur_id=utilisateur.id)
    session.add(script)
    audit.journaliser(session, utilisateur, "script.creation", "script", None,
                      details={"nom": script.nom})
    session.commit()
    session.refresh(script)
    return {"ok": True, "id": script.id}


@router.put("/scripts/{script_id}", dependencies=[Depends(exiger("reglages"))])
def modifier_script(script_id: int, corps: ScriptIn,
                    session: Session = Depends(get_session),
                    utilisateur: Utilisateur = Depends(auth.require_admin)):
    _exiger_mode_developpeur(session)
    script = session.get(Script, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Script introuvable")
    try:
        script.code = scripts.valider(corps.code)
    except scripts.ScriptRefuse as refus:
        raise HTTPException(status_code=422, detail=str(refus))
    script.nom = corps.nom.strip() or script.nom
    script.description = (corps.description or "").strip() or None
    script.date_modification = datetime.now()
    audit.journaliser(session, utilisateur, "script.modification", "script", script.id,
                      details={"nom": script.nom})
    session.commit()
    return {"ok": True}


@router.delete("/scripts/{script_id}", dependencies=[Depends(exiger("reglages"))])
def supprimer_script(script_id: int, session: Session = Depends(get_session),
                     utilisateur: Utilisateur = Depends(auth.require_admin)):
    script = session.get(Script, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Script introuvable")
    audit.journaliser(session, utilisateur, "script.suppression", "script", script.id,
                      details={"nom": script.nom})
    session.delete(script)
    session.commit()
    return {"ok": True}


@router.post("/scripts/{script_id}/executer", dependencies=[Depends(exiger("reglages"))])
def executer_script(script_id: int, corps: ContexteIn,
                    session: Session = Depends(get_session),
                    utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Lance le script et rend ce qu'il a écrit.

    L'exécution est **journalisée quoi qu'il arrive** : c'est la contrepartie du
    mode, et « un script a tourné » sans trace ne serait qu'une rumeur.
    """
    _exiger_mode_developpeur(session)
    script = session.get(Script, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Script introuvable")

    bilan = scripts.executer(script.code, corps.contexte)
    trace = ExecutionScript(
        script_id=script.id, utilisateur_id=utilisateur.id,
        duree_ms=bilan["duree_ms"], reussite=bilan["reussite"],
        sortie=bilan["sortie"], erreur=bilan["erreur"])
    session.add(trace)
    audit.journaliser(session, utilisateur, "script.execution", "script", script.id,
                      details={"nom": script.nom, "reussite": bilan["reussite"],
                               "duree_ms": bilan["duree_ms"]})
    session.commit()
    return bilan


@router.get("/scripts/executions", dependencies=[Depends(exiger("reglages"))])
def historique_executions(limite: int = 30, session: Session = Depends(get_session)):
    lignes = (session.query(ExecutionScript)
              .options(joinedload(ExecutionScript.utilisateur))
              .order_by(ExecutionScript.id.desc())
              .limit(max(1, min(limite, 200))).all())
    return [{
        "id": e.id, "script_id": e.script_id, "reussite": bool(e.reussite),
        "duree_ms": e.duree_ms, "erreur": e.erreur,
        "date": e.date_execution.isoformat(timespec="seconds") if e.date_execution else None,
        "par": e.utilisateur.nom_affiche if e.utilisateur else None,
    } for e in lignes]


# ------------------------------------------------------------
# Les rapprochements déclarés sur un type (§22.8)
#
# Un dossier porte un numéro, repris sur le devis, le bon de commande, le bon de
# livraison : ouvrir l'un montre les autres. Déclaré ici, jamais deviné — c'est
# ce qui distingue ce rapprochement de celui retiré au §22.7.
# ------------------------------------------------------------

class LienTypeIn(BaseModel):
    categorie_id: int
    champ_source: str
    champ_cible: str
    categorie_cible_id: Optional[int] = None
    libelle: Optional[str] = None


@router.get("/liens-types", dependencies=[Depends(exiger("reglages"))])
def lister_liens_types(categorie_id: Optional[int] = None,
                       session: Session = Depends(get_session)):
    noms = {c.id: c.nom for c in session.query(Categorie)}
    query = session.query(LienType)
    if categorie_id:
        query = query.filter(or_(LienType.categorie_id == categorie_id,
                                 LienType.categorie_cible_id == categorie_id))
    return [{
        "id": lien.id,
        "categorie_id": lien.categorie_id, "categorie": noms.get(lien.categorie_id),
        "categorie_cible_id": lien.categorie_cible_id,
        "categorie_cible": noms.get(lien.categorie_cible_id),
        "champ_source": lien.champ_source, "champ_cible": lien.champ_cible,
        "libelle": lien.libelle,
    } for lien in query.order_by(LienType.id).all()]


@router.post("/liens-types", dependencies=[Depends(exiger("reglages"))])
def declarer_lien_type(corps: LienTypeIn, session: Session = Depends(get_session),
                       utilisateur: Utilisateur = Depends(auth.require_admin)):
    try:
        lien = liens_type.declarer(session, corps.categorie_id, corps.champ_source.strip(),
                                   corps.champ_cible.strip(), corps.categorie_cible_id,
                                   corps.libelle)
    except liens_type.LienRefuse as refus:
        raise HTTPException(status_code=422, detail=str(refus))
    audit.journaliser(session, utilisateur, "lien_type.declare", "categorie",
                      lien.categorie_id,
                      details={"champ_source": lien.champ_source,
                               "champ_cible": lien.champ_cible,
                               "vers": lien.categorie_cible_id})
    session.commit()
    return {"ok": True, "id": lien.id}


@router.delete("/liens-types/{lien_id}", dependencies=[Depends(exiger("reglages"))])
def retirer_lien_type(lien_id: int, session: Session = Depends(get_session),
                      utilisateur: Utilisateur = Depends(auth.require_admin)):
    lien = session.get(LienType, lien_id)
    if not lien:
        raise HTTPException(status_code=404, detail="Rapprochement introuvable")
    audit.journaliser(session, utilisateur, "lien_type.retire", "categorie",
                      lien.categorie_id, details={"champ_source": lien.champ_source})
    session.delete(lien)
    session.commit()
    return {"ok": True}


# ------------------------------------------------------------
# Ce que l'on autorise à rattacher (§22.4)
#
# Tant que rien n'est déclaré, tout est permis : un réglage vide ne doit pas
# interdire une fonction, sans quoi personne ne comprendrait pourquoi le bouton
# refuse. Dès qu'une paire existe, elles seules le sont — c'est le moment où l'on
# décide que ce foyer relie des contrats à des avenants, et rien d'autre.
# ------------------------------------------------------------

class PaireRattachementIn(BaseModel):
    categorie_a: int
    categorie_b: int
    libelle: Optional[str] = None


@router.get("/rattachements-types", dependencies=[Depends(exiger("reglages"))])
def lister_paires_rattachement(session: Session = Depends(get_session)):
    noms = {c.id: c.nom for c in session.query(Categorie)}
    return {
        "libre": not rattachements.paires_declarees(session),
        "paires": [{
            "id": p.id,
            "categorie_a": p.categorie_a, "nom_a": noms.get(p.categorie_a),
            "categorie_b": p.categorie_b, "nom_b": noms.get(p.categorie_b),
            "libelle": p.libelle,
        } for p in rattachements.paires_declarees(session)],
    }


@router.post("/rattachements-types", dependencies=[Depends(exiger("reglages"))])
def declarer_paire_rattachement(corps: PaireRattachementIn,
                                session: Session = Depends(get_session),
                                utilisateur: Utilisateur = Depends(auth.require_admin)):
    try:
        paire = rattachements.declarer(session, corps.categorie_a, corps.categorie_b,
                                       corps.libelle)
    except rattachements.RattachementRefuse as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    audit.journaliser(session, utilisateur, "rattachement.paire_declaree", "categorie",
                      paire.categorie_a, details={"avec": paire.categorie_b,
                                                  "libelle": paire.libelle})
    session.commit()
    return {"ok": True, "id": paire.id}


@router.delete("/rattachements-types/{paire_id}", dependencies=[Depends(exiger("reglages"))])
def retirer_paire_rattachement(paire_id: int, session: Session = Depends(get_session),
                               utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Retirer la **dernière** paire rouvre tout : c'est la contrepartie assumée de
    « rien de déclaré veut dire tout permis ». Les liens déjà posés restent — ils
    disent quelque chose de vrai sur ces documents-là.
    """
    paire = session.get(RattachementType, paire_id)
    if not paire:
        raise HTTPException(status_code=404, detail="Paire introuvable")
    audit.journaliser(session, utilisateur, "rattachement.paire_retiree", "categorie",
                      paire.categorie_a, details={"avec": paire.categorie_b})
    session.delete(paire)
    session.commit()
    return {"ok": True}


@router.get("/jobs", response_model=list[JobOut], dependencies=[Depends(exiger("travaux"))])
def lister_jobs(statut: Optional[str] = None, categorie_id: Optional[int] = None,
                limite: int = 200, session: Session = Depends(get_session)):
    """
    Les travaux, filtrés par état ou par type de document (§19.10).

    Le type vient du document produit : un travail qui n'en a pas encore — « à
    classer », ou en erreur avant l'indexation — n'appartient à aucun type. Il se
    retrouve par son état, ce qui est précisément l'information utile à son sujet.
    """
    query = session.query(Job)
    if statut:
        query = query.filter(Job.statut == statut)
    if categorie_id:
        query = query.filter(Job.document_id.in_(
            select(Document.id).where(Document.categorie_id == categorie_id)))
    jobs = query.order_by(Job.date_creation.desc(), Job.id.desc()).limit(max(1, min(limite, 1000))).all()
    return [_serialize_job(j) for j in jobs]


@router.get("/jobs/{job_id}/fichier", dependencies=[Depends(exiger("travaux"))])
def telecharger_original(job_id: int, session: Session = Depends(get_session)):
    """
    Le fichier reçu, tel qu'il a été déposé (§18.53).

    Ce n'est pas le PDF archivé : celui-ci a été océrisé puis compressé, donc
    réécrit. Quand un travail échoue avant l'indexation, c'est même la seule
    chose qui reste à regarder — et c'est en la regardant qu'on comprend
    pourquoi il a échoué.
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Travail introuvable")
    chemin = _fichier_conserve(job)
    if not chemin:
        raise HTTPException(
            status_code=404,
            detail="Le fichier d'origine n'est plus disponible : le travail a été purgé "
                   "ou déposé avant la mise en place de leur conservation.")
    # Servi **pour être regardé**, pas téléchargé : le type MIME est celui du
    # fichier, et la disposition « inline ». Avec `application/octet-stream` et
    # un nom de pièce jointe, le navigateur refusait de l'afficher dans
    # l'inspecteur et le déposait dans les téléchargements — sous le nom de
    # l'URL d'objet, c'est-à-dire sans extension. On garde le nom d'origine dans
    # l'en-tête : il sert si l'on choisit tout de même d'enregistrer la page.
    return FileResponse(
        str(chemin), media_type=config.type_mime(chemin),
        headers={"Content-Disposition":
                 f'inline; filename="{config.nom_pour_entete(job.nom_fichier or chemin.name)}"'})


@router.get("/jobs/resume", dependencies=[Depends(exiger("travaux"))])
def resumer_jobs(categorie_id: Optional[int] = None,
                 session: Session = Depends(get_session)):
    """
    Combien de travaux, par état et par type de document (§19.10).

    `categorie_id` restreint le **compte par état** à ce type : les pastilles
    doivent dire combien de tâches sont bloquées *dans les factures* quand on
    regarde les factures, sinon elles annoncent un nombre qui ne correspond pas à
    la liste affichée (§19.17). Le compte par type, lui, reste global — c'est le
    menu qui sert à changer de type, il doit continuer de tous les montrer.

    Compté ici, en deux requêtes groupées, et non à l'écran : compter côté
    interface obligerait à charger tous les travaux pour n'en afficher qu'une
    page — c'est-à-dire à charger d'autant plus qu'il y en a, au moment précis où
    il y en a trop.

    Les états sont rendus dans un ordre qui a du sens à lire : d'abord ce qui
    attend une décision ou une action, ensuite ce qui se déroule, enfin ce qui
    est derrière nous.
    """
    query = session.query(Job.statut, func.count())
    if categorie_id:
        query = query.filter(Job.document_id.in_(
            select(Document.id).where(Document.categorie_id == categorie_id)))
    comptes = dict(query.group_by(Job.statut).all())
    etats = ("a_classer", "bloque", "erreur", "en_attente", "en_cours", "termine", "ignore")

    par_type = (session.query(Categorie.id, Categorie.nom, func.count(Job.id))
                .join(Document, Document.categorie_id == Categorie.id)
                .join(Job, Job.document_id == Document.id)
                .group_by(Categorie.id, Categorie.nom)
                .order_by(Categorie.ordre, Categorie.nom)
                .all())

    return {
        "statuts": {etat: int(comptes.get(etat, 0)) for etat in etats},
        "total": sum(int(n) for n in comptes.values()),
        "types": [{"categorie_id": identifiant, "nom": nom, "nombre": int(nombre)}
                  for identifiant, nom, nombre in par_type],
    }


def _demander_rejeu(session: Session, job: Job, etape: Optional[str],
                    utilisateur: Utilisateur) -> None:
    """Pose la demande de rejeu sur un travail, après validation de l'étape."""
    if job.statut not in STATUTS_REJOUABLES:
        raise HTTPException(status_code=409, detail=f"Un travail « {job.statut} » n'a rien à rejouer.")

    possibles = _etapes_possibles(job)
    if not possibles:
        # Un travail sans document produit **et** sans fichier reçu n'a plus rien
        # d'où repartir. Le dire vaut mieux que d'échouer sur une liste vide.
        raise HTTPException(
            status_code=409,
            detail=f"Le travail nº{job.id} n'a plus ni document ni fichier reçu : "
                   f"il n'y a rien à rejouer. Redéposez le fichier.")
    etape = etape or possibles[0]
    if etape not in ETAPES_VALIDES:
        raise HTTPException(status_code=422, detail=f"Étape « {etape} » inconnue")
    if etape not in possibles:
        raise HTTPException(
            status_code=409,
            detail=f"Le travail nº{job.id} ne peut pas repartir de « {etape} » "
                   f"(étapes possibles : {', '.join(possibles)}).",
        )

    job.rejouer_demande = True
    job.etape_demandee = etape
    # Un rejeu demandé à la main repart de zéro (§21.15) : c'est ce qui rouvre la
    # porte à un travail abandonné, et ce qui redonne sa chance à la reprise
    # automatique quand une règle vient d'être corrigée.
    job.tentatives = 0
    job.reprises_auto = 0
    audit.journaliser(session, utilisateur, "job.rejeu_demande", "job", job.id,
                      details={"nom_fichier": job.nom_fichier,
                               "statut_precedent": job.statut, "etape": etape})


@router.post("/jobs/{job_id}/rejouer", response_model=JobOut, dependencies=[Depends(exiger("travaux"))])
def rejouer_job(job_id: int, etape: Optional[str] = None,
                session: Session = Depends(get_session),
                utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Demande le rejeu d'un travail. L'API n'a accès ni au dossier surveillé ni au
    dossier de quarantaine : elle pose un drapeau que le serveur de travaux
    relève à son passage suivant, lequel réanalyse le document existant ou
    reprend le fichier en quarantaine selon le cas.
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Travail introuvable")
    _demander_rejeu(session, job, etape, utilisateur)
    session.commit()
    session.refresh(job)
    return _serialize_job(job)


class ActionGroupeeIn(BaseModel):
    ids: list[int]
    action: str                      # 'rejouer' | 'supprimer'
    etape: Optional[str] = None      # pour 'rejouer'


@router.post("/jobs/actions", dependencies=[Depends(exiger("travaux"))])
def actions_groupees(payload: ActionGroupeeIn, session: Session = Depends(get_session),
                     utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Applique une action à plusieurs travaux d'un coup.

    Chaque travail est traité indépendamment : ceux qui ne s'y prêtent pas (un
    doublon qu'on tente de rejouer, par exemple) sont signalés avec leur motif,
    sans faire échouer l'ensemble de la demande.
    """
    if payload.action not in {"rejouer", "supprimer"}:
        raise HTTPException(status_code=422, detail=f"Action « {payload.action} » inconnue")
    if not payload.ids:
        raise HTTPException(status_code=422, detail="Aucun travail sélectionné")

    traites, ignores = [], []
    for job_id in payload.ids:
        job = session.get(Job, job_id)
        if not job:
            ignores.append({"id": job_id, "motif": "Travail introuvable"})
            continue
        try:
            if payload.action == "rejouer":
                _demander_rejeu(session, job, payload.etape, utilisateur)
            else:
                efface = _effacer_le_fichier_recu(job)
                audit.journaliser(session, utilisateur, "job.suppression", "job", job.id,
                                  details={"nom_fichier": job.nom_fichier,
                                           "statut": job.statut,
                                           "fichier_recu_efface": efface})
                session.delete(job)
            traites.append(job_id)
        except HTTPException as erreur:
            ignores.append({"id": job_id, "motif": erreur.detail})

    session.commit()
    return {"traites": traites, "ignores": ignores}


def _effacer_le_fichier_recu(job: Job) -> bool:
    """
    Efface le fichier reçu conservé avec ce travail (§18.53).

    La fenêtre de confirmation l'annonce depuis toujours — « le fichier reçu part
    avec la tâche » — mais la suppression ne retirait que la ligne : le fichier
    attendait le balayage des orphelins du serveur de travaux, jusqu'à cinq
    minutes plus tard. Une promesse tenue en différé est une promesse qu'on ne
    peut pas vérifier ; elle l'est maintenant à l'instant du clic. Le balayage
    reste en place pour ce qu'un arrêt brutal aurait laissé derrière.

    Le dossier effacé est **celui du travail et lui seul** : son chemin est
    recomposé à partir de l'identifiant, jamais lu depuis la base — une valeur
    de `chemin_source` pointant ailleurs ne doit pas devenir un ordre
    d'effacement.
    """
    racine = Path(config.TRAVAUX_FOLDER).resolve()
    dossier = racine / str(job.id)
    if not dossier.is_dir():
        return False
    try:
        shutil.rmtree(dossier)
        return True
    except OSError:
        log.exception("Le fichier reçu du travail %s n'a pas pu être effacé", job.id)
        return False


@router.delete("/jobs/{job_id}", dependencies=[Depends(exiger("travaux"))])
def supprimer_job(job_id: int, session: Session = Depends(get_session),
                  utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Retire une ligne du suivi, **et le fichier reçu qu'elle conservait**.

    Le document, lui, n'est pas touché : il vit sa vie dans le registre, avec son
    PDF archivé. Ce qui disparaît est le fichier tel qu'il a été déposé — donc la
    possibilité de rejouer ce travail.
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Travail introuvable")
    efface = _effacer_le_fichier_recu(job)
    audit.journaliser(session, utilisateur, "job.suppression", "job", job.id,
                      details={"nom_fichier": job.nom_fichier, "statut": job.statut,
                               "fichier_recu_efface": efface})
    session.delete(job)
    session.commit()
    return {"ok": True, "fichier_recu_efface": efface}


# ------------------------------------------------------------
# Corbeille des fichiers archivés
#
# Le worker y déplace les PDF de `storage/` que plus aucun document ne
# référence, plutôt que de les effacer. Ce contenu n'est visible que des
# administrateurs : ce sont des documents du foyer, sortis du registre mais
# pas encore détruits, et les droits par catégorie ne s'y appliquent plus
# (l'entrée qui les portait n'existe plus).
#
# Seul ce sous-dossier est monté en écriture pour l'API (cf. docker-compose) :
# vider la corbeille ne donne aucun accès aux archives elles-mêmes.
# ------------------------------------------------------------

class FichierCorbeilleOut(BaseModel):
    chemin: str          # relatif à la corbeille, sert d'identifiant
    nom: str
    taille: int
    date_suppression: str
    # D'où vient ce fichier (§22.63). Un nom et une taille ne disent pas ce
    # qu'on s'apprête à détruire : « facture_9079093031.pdf, 15 Ko » peut être
    # un doublon sans intérêt comme la seule copie d'une facture d'électricité.
    # Le journal d'audit garde la chaîne — `chemin_corbeille` mène au chemin
    # d'origine, qui mène au document —, on la remonte.
    origine: Optional[str] = None      # 'document' | 'orphelin' | None si perdue
    document_id: Optional[int] = None
    document: Optional[str] = None     # ce que le document s'appelait
    chemin_origine: Optional[str] = None
    par: Optional[str] = None          # qui l'a mis là


def _dossier_corbeille() -> Path:
    return Path(config.CORBEILLE_FOLDER)


def _fichier_corbeille(chemin_relatif: str) -> Path:
    """
    Résout un chemin fourni par le client à l'intérieur de la corbeille.

    Le chemin vient d'une requête : il est résolu puis vérifié comme étant bien
    *sous* la corbeille, sinon un `../../` permettrait de lire ou d'effacer
    n'importe quel fichier accessible au conteneur.
    """
    racine = _dossier_corbeille().resolve()
    try:
        cible = (racine / chemin_relatif).resolve()
    except OSError:
        raise HTTPException(status_code=400, detail="Chemin invalide")
    if not cible.is_relative_to(racine) or not cible.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable dans la corbeille")
    return cible


class StockageOut(BaseModel):
    documents: int
    taille_totale: int          # somme des tailles connues, en octets
    compresses: int
    a_reprendre: int            # archives jamais passées par l'optimiseur
    niveau: int                 # PDF_OPTIMISATION en vigueur
    lot: int                    # nombre repris à chaque cycle du serveur de travaux


# ------------------------------------------------------------
# Sauvegarde (§22.49)
#
# L'écran ne fait pas la sauvegarde : c'est le serveur de travaux qui l'exécute,
# lui seul ayant les archives sous la main. L'API montre où l'on en est et
# permet d'en déclencher une tout de suite — le geste qu'on fait avant une
# opération risquée, et celui qui prouve que le réglage marche.
# ------------------------------------------------------------

@router.get("/sauvegardes", dependencies=[Depends(exiger("travaux"))])
def etat_des_sauvegardes(session: Session = Depends(get_session)):
    """Où en est la copie de secours, et ce qu'il y a sur le disque."""
    from . import sauvegarde

    dossier = reglages.lire(session, "sauvegarde_dossier") or "/data/sauvegardes"
    alerte = max(1, reglages.entier(session, "sauvegarde_alerte_jours") or 3)
    return {
        "active": reglages.booleen(session, "sauvegarde_active"),
        "dossier": dossier,
        "heures": reglages.entier(session, "sauvegarde_heures") or 24,
        "garder": reglages.entier(session, "sauvegarde_garder") or 7,
        "avec_archives": reglages.booleen(session, "sauvegarde_archives"),
        "alerte_jours": alerte,
        **sauvegarde.etat(dossier, alerte),
        "sauvegardes": sauvegarde.lister(dossier),
    }


@router.post("/sauvegardes", dependencies=[Depends(exiger("travaux"))])
def sauvegarder_maintenant(session: Session = Depends(get_session),
                           utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Fait une sauvegarde tout de suite, sans attendre le rythme réglé.

    C'est le geste qu'on fait **avant** une opération risquée — une reprise de
    configuration, une mise à jour — et c'est aussi ce qui prouve que le réglage
    fonctionne : une sauvegarde qu'on n'a jamais vue aboutir n'en est pas une.
    """
    from . import sauvegarde

    dossier = reglages.lire(session, "sauvegarde_dossier") or "/data/sauvegardes"
    try:
        bilan = sauvegarde.executer(
            dossier, avec_archives=reglages.booleen(session, "sauvegarde_archives"),
            mot_de_passe=reglages.lire(session, "sauvegarde_mot_de_passe") or None)
    except sauvegarde.SauvegardeImpossible as erreur:
        _tracer(session, utilisateur, "sauvegarde.echec", "sauvegarde", None,
                {"erreur": str(erreur)[:300], "dossier": dossier, "a_la_demande": True})
        session.commit()
        raise HTTPException(status_code=500, detail=f"Sauvegarde impossible : {erreur}")
    efface = sauvegarde.purger(dossier, max(1, reglages.entier(session, "sauvegarde_garder") or 7))
    _tracer(session, utilisateur, "sauvegarde.faite", "sauvegarde", None,
            {**bilan, "anciennes_effacees": efface, "a_la_demande": True})
    session.commit()
    return bilan


@router.delete("/sauvegardes/{nom}", dependencies=[Depends(exiger("travaux"))])
def supprimer_une_sauvegarde(nom: str, session: Session = Depends(get_session),
                             utilisateur: Utilisateur = Depends(auth.require_admin)):
    """Efface une sauvegarde nommée. Le nom est un dossier, jamais un chemin."""
    from . import sauvegarde

    if not re.fullmatch(r"[0-9A-Za-z_.\-]{1,64}", nom or ""):
        raise HTTPException(status_code=400, detail="Nom de sauvegarde invalide")
    dossier = reglages.lire(session, "sauvegarde_dossier") or "/data/sauvegardes"
    racine = sauvegarde.dossier_racine(dossier).resolve()
    cible = (racine / nom).resolve()
    # Une sauvegarde chiffrée est un fichier, pas un dossier (§22.65) : on efface
    # l'un ou l'autre, et la marque en clair part avec l'archive.
    chiffree = (racine / f"{nom}{sauvegarde.SUFFIXE_CHIFFRE}").resolve()
    if cible.is_relative_to(racine) and cible.is_dir():
        shutil.rmtree(cible, ignore_errors=True)
    elif chiffree.is_relative_to(racine) and chiffree.is_file():
        chiffree.unlink(missing_ok=True)
        Path(f"{chiffree}.txt").unlink(missing_ok=True)
    else:
        raise HTTPException(status_code=404, detail="Sauvegarde introuvable")
    _tracer(session, utilisateur, "sauvegarde.suppression", "sauvegarde", None, {"nom": nom})
    session.commit()
    return {"ok": True}


# ------------------------------------------------------------
# Export de l'archive (§17.30)
#
# L'archive contient tous les PDF du foyer, rangés selon leur classement. C'est
# le fichier le plus sensible que l'application puisse produire, et il échappe à
# tout contrôle une fois sorti. Trois précautions, donc :
#
#   le mot de passe est redemandé, et le second facteur avec s'il est actif —
#   une session ouverte sur un poste laissé sans surveillance ne doit pas suffire ;
#   l'archive ne se télécharge **qu'une fois** ;
#   non téléchargée, elle s'efface d'elle-même.
# ------------------------------------------------------------

class DemandeExportIn(BaseModel):
    mot_de_passe: str
    code_otp: Optional[str] = None


class ExportOut(BaseModel):
    jeton: str
    documents: int
    absents: int
    taille_octets: int
    expire_le: str


@router.post("/export", response_model=ExportOut, dependencies=[Depends(exiger("exporter_archive"))])
def demander_export(payload: DemandeExportIn, request: Request,
                    session: Session = Depends(get_session),
                    auteur: Utilisateur = Depends(auth.require_admin)):
    """Vérifie l'identité, construit l'archive, et rend un jeton à usage unique."""
    if not auth.verifier_mot_de_passe(payload.mot_de_passe, auteur.mot_de_passe_hash):
        raise HTTPException(status_code=400, detail="Mot de passe incorrect")

    if auteur.otp_actif:
        code = (payload.code_otp or "").strip()
        if not code:
            raise HTTPException(status_code=400,
                                detail="Code de double authentification requis.")
        reste = otp.consommer_code_secours(auteur.otp_codes_secours, code)
        if reste is not None:
            auteur.otp_codes_secours = reste
        elif not otp.verifier(auteur.otp_secret, code):
            raise HTTPException(status_code=400, detail="Code refusé.")

    # Ménage d'abord : une archive oubliée est une copie complète du foyer qui
    # traîne, et personne ne pense à la supprimer.
    export.purger(session, config.EXPORT_FOLDER)

    jeton = secrets.token_urlsafe(24)
    chemin = os.path.join(
        config.EXPORT_FOLDER,
        f"homeged-{datetime.now():%Y%m%d-%H%M%S}-{jeton[:8]}.zip",
    )
    try:
        bilan = export.construire(session, chemin)
    except Exception as erreur:
        log.exception("Export impossible")
        raise HTTPException(status_code=500, detail=f"Export impossible : {erreur}")

    expiration = datetime.now() + timedelta(
        minutes=reglages.entier(session, "expiration_export_minutes")
                or config.EXPORT_DUREE_MINUTES)
    session.add(ExportArchive(
        jeton=jeton, utilisateur_id=auteur.id, chemin=chemin,
        taille_octets=bilan["taille_octets"], documents=bilan["documents"],
        date_expiration=expiration,
    ))
    audit.journaliser(session, auteur, "export.demande", "archive",
                      details={"documents": bilan["documents"], "absents": bilan["absents"],
                               "taille_octets": bilan["taille_octets"],
                               "adresse": limitation.adresse_client(request)})
    session.commit()

    return ExportOut(jeton=jeton, documents=bilan["documents"], absents=bilan["absents"],
                     taille_octets=bilan["taille_octets"],
                     expire_le=expiration.isoformat(timespec="seconds"))


@router.get("/export/{jeton}", dependencies=[Depends(exiger("exporter_archive"))])
def telecharger_export(jeton: str, request: Request,
                       session: Session = Depends(get_session),
                       auteur: Utilisateur = Depends(auth.require_admin)):
    """
    Sert l'archive, une fois et une seule.

    Le jeton est invalidé **avant** l'envoi : un téléchargement interrompu ne
    donne pas droit à un second essai. C'est volontairement sévère — un lien qui
    resterait valable serait une copie de la GED entière à disposition de qui
    remettrait la main dessus. Il reste possible d'en redemander une, en
    prouvant à nouveau son identité.
    """
    archive = session.query(ExportArchive).filter_by(jeton=jeton).one_or_none()
    if not archive or archive.date_telechargement is not None:
        raise HTTPException(status_code=404, detail="Archive introuvable ou déjà téléchargée")
    if archive.date_expiration < datetime.now():
        raise HTTPException(status_code=410, detail="Archive expirée : demandez-en une nouvelle")
    if archive.utilisateur_id and archive.utilisateur_id != auteur.id:
        raise HTTPException(status_code=403, detail="Cette archive a été demandée par un autre compte")
    if not os.path.exists(archive.chemin):
        raise HTTPException(status_code=410, detail="Archive introuvable sur le disque")

    chemin, nom = archive.chemin, os.path.basename(archive.chemin)
    archive.date_telechargement = datetime.now()
    audit.journaliser(session, auteur, "export.telecharge", "archive",
                      details={"documents": archive.documents,
                               "taille_octets": archive.taille_octets,
                               "adresse": limitation.adresse_client(request)})
    session.commit()

    # Le fichier est retiré du disque dès l'envoi terminé : la ligne conserve la
    # trace, le contenu ne survit pas.
    return FileResponse(chemin, media_type="application/zip", filename=nom,
                        background=BackgroundTask(_effacer, chemin))


def _effacer(chemin: str) -> None:
    try:
        if os.path.exists(chemin):
            os.remove(chemin)
    except OSError:
        log.exception(f"Archive {chemin} non effacée")


@router.get("/stockage", response_model=StockageOut, dependencies=[Depends(exiger("travaux"))])
def etat_du_stockage(session: Session = Depends(get_session)):
    """
    Ce que pèsent les archives et où en est leur compression (§17.8).

    Les tailles sont lues en base, pas sur le disque : l'API monte `storage/` en
    lecture seule et n'a pas à le parcourir à chaque affichage. Elles sont
    renseignées à l'archivage et remises à jour par la reprise.
    """
    total = session.query(func.coalesce(func.sum(Document.taille_octets), 0)).scalar() or 0
    return StockageOut(
        documents=session.query(Document).count(),
        taille_totale=int(total),
        compresses=session.query(Document).filter(Document.date_compression.isnot(None)).count(),
        a_reprendre=session.query(Document).filter(Document.date_compression.is_(None)).count(),
        niveau=config.PDF_OPTIMISATION,
        lot=config.COMPRESSION_LOT,
    )


class EssaiCourrielIn(BaseModel):
    adresse: str


@router.post("/courriel/essai", dependencies=[Depends(exiger("reglages"))])
def essayer_le_courriel(payload: EssaiCourrielIn, session: Session = Depends(get_session),
                        user: Utilisateur = Depends(auth.get_current_user)):
    """
    Un envoi d'essai (§21.10).

    Sans lui, on ne saurait jamais si le SMTP est correctement réglé avant la
    première échéance — c'est-à-dire au pire moment. Le message d'erreur est rendu
    tel que le serveur l'a dit : « ça n'a pas marché » n'aide personne à régler un
    SMTP, et c'est précisément là qu'on a besoin de savoir si c'est le port, le
    mot de passe ou le certificat.
    """
    adresse = (payload.adresse or "").strip() or (user.email or "")
    if "@" not in adresse:
        raise HTTPException(status_code=422, detail="Indiquez une adresse de destination.")
    try:
        courriel.essayer(session, adresse)
    except courriel.EnvoiImpossible as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))
    audit.journaliser(session, user, "courriel.essai", "reglage", None,
                      details={"adresse": adresse})
    session.commit()
    return {"ok": True, "adresse": adresse}


@router.post("/courriel/resumer", dependencies=[Depends(exiger("reglages"))])
def envoyer_les_resumes(session: Session = Depends(get_session),
                        utilisateur: Utilisateur = Depends(auth.get_current_user)):
    """
    Envoie tout de suite les résumés en attente, sans attendre le cycle.

    Le délai du palier est ignoré, le reste non : on veut savoir si le message
    part, pas court-circuiter la règle.
    """
    bilan = courriel.resumer(session, forcer=True)
    # Un envoi vers les boîtes du foyer se journalise : c'est une sortie hors de
    # l'application, comme un export (§22.48).
    _tracer(session, utilisateur, "courriel.resumes_envoyes", "courriel", None, bilan)
    session.commit()
    return bilan


# ------------------------------------------------------------
# Les automatisations « quand… alors… » (§21.8)
# ------------------------------------------------------------

class AutomatisationIn(BaseModel):
    nom: str
    declencheur: str
    categorie_id: Optional[int] = None
    conditions: list[dict] = []
    actions: list[dict] = []
    actif: bool = True
    ordre: int = 100


def _serialiser_automatisation(regle: Automatisation) -> dict:
    import json as _json

    def lire(brut):
        try:
            valeur = _json.loads(brut or "[]")
            return valeur if isinstance(valeur, list) else []
        except (ValueError, TypeError):
            return []

    return {"id": regle.id, "nom": regle.nom, "declencheur": regle.declencheur,
            "categorie_id": regle.categorie_id,
            "categorie": regle.categorie.nom if regle.categorie else None,
            "conditions": lire(regle.conditions), "actions": lire(regle.actions),
            "actif": bool(regle.actif), "ordre": regle.ordre}


@router.get("/automatisations/catalogue", dependencies=[Depends(exiger("reglages"))])
def catalogue_automatisations():
    """
    Ce qui existe comme déclencheur et comme action, tel que le code le déclare.

    L'écran s'en sert pour composer ses formulaires : une liste tenue à l'écran
    finirait par proposer une action que le moteur ne sait pas exécuter.
    """
    return automatisations.decrire()


@router.get("/automatisations", dependencies=[Depends(exiger("reglages"))])
def lister_automatisations(session: Session = Depends(get_session)):
    regles = (session.query(Automatisation)
              .order_by(Automatisation.ordre, Automatisation.id).all())
    return [_serialiser_automatisation(r) for r in regles]


@router.get("/automatisations/journal", dependencies=[Depends(exiger("reglages"))])
def journal_automatisations(limite: int = 100, automatisation_id: Optional[int] = None,
                            document_id: Optional[int] = None,
                            session: Session = Depends(get_session)):
    """
    Ce qui s'est déclenché, et pourquoi.

    Les examens **sans suite** y figurent aussi : « pourquoi cette règle n'a rien
    fait » est la question qu'on se pose le plus souvent.
    """
    return automatisations.journal(session, max(1, min(limite, 500)),
                                   automatisation_id, document_id)


def _valider_automatisation(session: Session, payload: AutomatisationIn) -> None:
    try:
        automatisations.valider(session, payload.declencheur, payload.conditions,
                                payload.actions)
    except automatisations.AutomatisationInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))
    if payload.categorie_id and not session.get(Categorie, payload.categorie_id):
        raise HTTPException(status_code=404, detail="Catégorie introuvable")


@router.post("/automatisations", dependencies=[Depends(exiger("reglages"))])
def creer_automatisation(payload: AutomatisationIn, session: Session = Depends(get_session),
                         user: Utilisateur = Depends(auth.get_current_user)):
    import json as _json

    _valider_automatisation(session, payload)
    regle = Automatisation(
        nom=payload.nom.strip(), declencheur=payload.declencheur,
        categorie_id=payload.categorie_id,
        conditions=_json.dumps(payload.conditions, ensure_ascii=False),
        actions=_json.dumps(payload.actions, ensure_ascii=False),
        actif=payload.actif, ordre=payload.ordre)
    if not regle.nom:
        raise HTTPException(status_code=422, detail="Le nom est obligatoire")
    session.add(regle)
    audit.journaliser(session, user, "automatisation.creation", "automatisation", None,
                      details={"nom": regle.nom, "declencheur": regle.declencheur})
    session.commit()
    session.refresh(regle)
    return _serialiser_automatisation(regle)


@router.put("/automatisations/{regle_id}", dependencies=[Depends(exiger("reglages"))])
def modifier_automatisation(regle_id: int, payload: AutomatisationIn,
                            session: Session = Depends(get_session),
                            user: Utilisateur = Depends(auth.get_current_user)):
    import json as _json

    regle = session.get(Automatisation, regle_id)
    if not regle:
        raise HTTPException(status_code=404, detail="Automatisation introuvable")
    _valider_automatisation(session, payload)
    regle.nom = payload.nom.strip()
    regle.declencheur = payload.declencheur
    regle.categorie_id = payload.categorie_id
    regle.conditions = _json.dumps(payload.conditions, ensure_ascii=False)
    regle.actions = _json.dumps(payload.actions, ensure_ascii=False)
    regle.actif = payload.actif
    regle.ordre = payload.ordre
    audit.journaliser(session, user, "automatisation.modification", "automatisation",
                      regle.id, details={"nom": regle.nom})
    session.commit()
    session.refresh(regle)
    return _serialiser_automatisation(regle)


@router.delete("/automatisations/{regle_id}", dependencies=[Depends(exiger("reglages"))])
def supprimer_automatisation(regle_id: int, session: Session = Depends(get_session),
                             user: Utilisateur = Depends(auth.get_current_user)):
    regle = session.get(Automatisation, regle_id)
    if not regle:
        raise HTTPException(status_code=404, detail="Automatisation introuvable")
    audit.journaliser(session, user, "automatisation.suppression", "automatisation",
                      regle.id, details={"nom": regle.nom})
    session.delete(regle)
    session.commit()
    return {"ok": True}


@router.post("/automatisations/{regle_id}/essayer", dependencies=[Depends(exiger("reglages"))])
def essayer_automatisation(regle_id: int, document_id: int,
                           session: Session = Depends(get_session)):
    """
    Passe la règle sur un document **sans rien enregistrer**.

    Écrire une automatisation puis attendre le prochain dépôt pour savoir si elle
    mord est la même boucle décourageante que celle des règles d'extraction
    (§21.5). On l'essaie donc, et l'on annule.
    """
    regle = session.get(Automatisation, regle_id)
    document = session.get(Document, document_id)
    if not regle or not document:
        raise HTTPException(status_code=404, detail="Automatisation ou document introuvable")
    try:
        bilan = automatisations.executer(session, regle.declencheur, document)
        reunies = automatisations._conditions_reunies(session, regle, document)
        faits = next((b["faits"] for b in bilan if b["automatisation"] == regle.nom), [])
        return {"conditions_reunies": reunies, "faits": faits}
    finally:
        # Rien n'est gardé : ni les valeurs posées, ni les lignes de journal.
        session.rollback()


# ------------------------------------------------------------
# L'intégrité des archives (§21.3)
# ------------------------------------------------------------

@router.get("/integrite", dependencies=[Depends(exiger("travaux"))])
def etat_integrite(session: Session = Depends(get_session)):
    """
    Ce que valent les fichiers archivés : combien ont été relus, combien ne
    correspondent plus, lesquels.

    Nommer les documents concernés plutôt que d'annoncer un nombre : un compteur
    d'altérations sans les pièces en cause n'apprend rien qu'on puisse suivre.
    """
    from . import integrite

    return integrite.resume(session)


@router.post("/integrite/controler", dependencies=[Depends(exiger("travaux"))])
def controler_integrite_maintenant(lot: int = 50, session: Session = Depends(get_session),
                                   user: Utilisateur = Depends(auth.get_current_user)):
    """
    Lance un contrôle tout de suite, sans attendre le cycle de maintenance.

    C'est le geste qu'on fait après un incident — un disque remplacé, une
    sauvegarde restaurée : on veut savoir maintenant, pas cette nuit.
    """
    from . import integrite

    bilan = integrite.controler(session, max(1, min(lot, 500)))
    if bilan["anomalies"]:
        audit.journaliser(session, user, "integrite.anomalie", "document",
                          details={"documents": bilan["anomalies"][:50]})
    session.commit()
    return bilan


# ------------------------------------------------------------
# La corbeille des documents, vue de l'administration (§21.1)
#
# Celle de chacun ne montre que ses propres suppressions, et plus rien dès qu'on
# les en a retirées. Celle-ci montre **tout**, y compris ce que les autres ont
# écarté — c'est le second filet, celui qui rattrape le geste de trop. Elle est
# la seule d'où l'on efface pour de bon.
# ------------------------------------------------------------

class DocumentSupprimeOut(BaseModel):
    id: int
    nom_fichier: str
    categorie: Optional[str] = None
    date_suppression: str
    supprime_par: Optional[str] = None
    masquee: bool = False


def _serialiser_supprime(doc: Document) -> DocumentSupprimeOut:
    return DocumentSupprimeOut(
        id=doc.id, nom_fichier=doc.nom_fichier,
        categorie=doc.categorie.nom if doc.categorie else None,
        date_suppression=doc.date_suppression.isoformat(timespec="seconds"),
        supprime_par=doc.supprime_par.nom_affiche if doc.supprime_par else None,
        masquee=bool(doc.corbeille_masquee))


@router.get("/documents-supprimes", response_model=list[DocumentSupprimeOut],
            dependencies=[Depends(exiger("travaux"))])
def lister_documents_supprimes(session: Session = Depends(get_session)):
    """Tous les documents en corbeille, du plus récemment jeté au plus ancien."""
    documents = (session.query(Document)
                 .filter(Document.date_suppression.isnot(None))
                 .order_by(Document.date_suppression.desc())
                 .limit(1000).all())
    return [_serialiser_supprime(d) for d in documents]


@router.post("/documents-supprimes/{document_id}/restaurer",
             dependencies=[Depends(exiger("travaux"))])
def restaurer_document_admin(document_id: int, session: Session = Depends(get_session),
                             user: Utilisateur = Depends(auth.get_current_user)):
    """
    Remet un document à sa place, y compris un que son auteur avait retiré de sa
    propre corbeille : c'est précisément ce qu'on attend de ce second filet.
    """
    doc = session.get(Document, document_id)
    if not doc or doc.date_suppression is None:
        raise HTTPException(status_code=404, detail="Document introuvable dans la corbeille")
    doc.date_suppression = None
    doc.supprime_par_id = None
    doc.corbeille_masquee = False
    audit.journaliser(session, user, "document.restauration", "document", doc.id,
                      details={"nom_fichier": doc.nom_fichier, "par_administration": True})
    session.commit()
    return {"ok": True, "id": doc.id}


@router.delete("/documents-supprimes/{document_id}",
               dependencies=[Depends(exiger("travaux"))])
def effacer_document_definitivement(document_id: int, session: Session = Depends(get_session),
                                    user: Utilisateur = Depends(auth.get_current_user)):
    """
    Efface la fiche pour de bon. Le fichier n'est pas détruit ici : plus aucun
    document ne le référencera, le serveur de travaux le déplacera au passage
    suivant dans `storage/.corbeille/`, d'où il faut encore une décision humaine
    pour le perdre. Deux filets, parce que ce geste-ci ne se défait pas.
    """
    doc = session.get(Document, document_id)
    if not doc or doc.date_suppression is None:
        raise HTTPException(status_code=404, detail="Document introuvable dans la corbeille")
    audit.journaliser(session, user, "document.suppression_definitive", "document", doc.id,
                      details={"nom_fichier": doc.nom_fichier,
                               "chemin_stockage": doc.chemin_stockage,
                               "hash_sha256": doc.hash_sha256})
    session.delete(doc)
    session.commit()
    return {"ok": True}


def _origines_de_la_corbeille(session: Session) -> tuple[dict, dict]:
    """
    Ce que le journal sait des fichiers en corbeille (§22.63).

    Deux relevés, et deux seulement — pas un par fichier : la mise en corbeille
    d'un orphelin, qui relie le chemin de la corbeille au chemin d'origine ; et
    la suppression définitive d'un document, qui relie ce chemin d'origine au
    document qu'il portait.

    On rend `{chemin_corbeille: chemin_origine}` et
    `{chemin_origine: {document_id, document, par}}`.
    """
    def lire(ligne) -> dict:
        # `details` est du texte en base : le journal est fait pour être relu
        # tel quel, et une entrée illisible ne doit pas emporter la liste.
        try:
            valeur = json.loads(ligne.details) if ligne.details else {}
        except (ValueError, TypeError):
            return {}
        return valeur if isinstance(valeur, dict) else {}

    vers_origine: dict[str, str] = {}
    for ligne in (session.query(JournalAudit)
                  .filter(JournalAudit.action == "stockage.orphelin_en_corbeille")
                  .order_by(JournalAudit.id.desc())):
        details = lire(ligne)
        corbeille, origine = details.get("chemin_corbeille"), details.get("chemin_origine")
        if corbeille and origine:
            vers_origine.setdefault(str(corbeille), str(origine))

    documents: dict[str, dict] = {}
    for ligne in (session.query(JournalAudit)
                  .filter(JournalAudit.action == "document.suppression_definitive")
                  .order_by(JournalAudit.id.desc())):
        details = lire(ligne)
        chemin = details.get("chemin_stockage")
        if chemin:
            documents.setdefault(str(chemin), {
                "document_id": ligne.objet_id,
                "document": details.get("nom_fichier"),
                "par": ligne.utilisateur_email,
            })
    return vers_origine, documents


class PageCorbeilleFichiersOut(BaseModel):
    """`total` porte sur la corbeille entière, pas sur la page (§22.90)."""
    total: int
    octets: int
    fichiers: list[FichierCorbeilleOut]


@router.get("/corbeille", response_model=PageCorbeilleFichiersOut,
            dependencies=[Depends(exiger("travaux"))])
def lister_corbeille(limite: int = 25, decalage: int = 0,
                     session: Session = Depends(get_session)):
    """
    Fichiers en attente dans la corbeille, du plus récemment mis au plus ancien.

    Le dossier est lu en entier — il faut bien trier par date et compter — mais
    seule une page est rendue (§22.90) : quelques milliers de fichiers en attente
    de destruction faisaient une réponse que l'écran mettait un temps certain à
    poser. Le total et la taille suivent, pour qu'on sache ce qui reste.
    """
    import datetime

    racine = _dossier_corbeille()
    if not racine.is_dir():
        return PageCorbeilleFichiersOut(total=0, octets=0, fichiers=[])
    vers_origine, documents = _origines_de_la_corbeille(session)
    fichiers = []
    for chemin in racine.rglob("*"):
        if not chemin.is_file():
            continue
        info = chemin.stat()
        relatif = str(chemin.relative_to(racine))
        # Le journal a écrit le chemin absolu tel que le serveur de travaux le
        # voyait : on rapproche par la fin, qui est stable.
        absolu = next((c for c in vers_origine if c.endswith(relatif)), None)
        origine_chemin = vers_origine.get(absolu) if absolu else None
        venu_du_document = documents.get(origine_chemin) if origine_chemin else None
        fichiers.append(FichierCorbeilleOut(
            chemin=relatif,
            nom=chemin.name,
            taille=info.st_size,
            date_suppression=datetime.datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
            origine=("document" if venu_du_document else "orphelin" if origine_chemin else None),
            chemin_origine=origine_chemin,
            **(venu_du_document or {}),
        ))
    fichiers.sort(key=lambda f: f.date_suppression, reverse=True)
    debut = max(0, decalage)
    return PageCorbeilleFichiersOut(
        total=len(fichiers),
        octets=sum(f.taille for f in fichiers),
        fichiers=fichiers[debut:debut + max(1, min(limite, 200))])


@router.get("/corbeille/fichier", dependencies=[Depends(exiger("travaux"))])
def telecharger_fichier_corbeille(chemin: str):
    """Récupération d'un fichier avant destruction définitive."""
    cible = _fichier_corbeille(chemin)
    return FileResponse(cible, media_type="application/pdf", filename=cible.name)


@router.delete("/corbeille/fichier", dependencies=[Depends(exiger("travaux"))])
def supprimer_fichier_corbeille(chemin: str, session: Session = Depends(get_session),
                                utilisateur: Utilisateur = Depends(auth.require_admin)):
    """Destruction définitive d'un fichier de la corbeille."""
    cible = _fichier_corbeille(chemin)
    try:
        cible.unlink()
    except OSError as erreur:
        raise HTTPException(status_code=500, detail=f"Suppression impossible : {erreur}")
    audit.journaliser(session, utilisateur, "corbeille.suppression_definitive", "fichier",
                      details={"chemin": chemin})
    session.commit()
    return {"ok": True}


@router.post("/corbeille/vider", dependencies=[Depends(exiger("travaux"))])
def vider_corbeille(session: Session = Depends(get_session),
                    utilisateur: Utilisateur = Depends(auth.require_admin)):
    """Destruction définitive de tout le contenu de la corbeille."""
    racine = _dossier_corbeille()
    if not racine.is_dir():
        return {"ok": True, "fichiers_supprimes": 0}

    supprimes, echecs = 0, []
    for chemin in sorted(racine.rglob("*"), key=lambda c: len(c.parts), reverse=True):
        try:
            if chemin.is_file():
                chemin.unlink()
                supprimes += 1
            elif chemin.is_dir():
                chemin.rmdir()
        except OSError:
            echecs.append(str(chemin.relative_to(racine)))

    audit.journaliser(session, utilisateur, "corbeille.vidage", "corbeille",
                      details={"fichiers_supprimes": supprimes, "echecs": echecs})
    session.commit()
    return {"ok": True, "fichiers_supprimes": supprimes, "echecs": echecs}


# ------------------------------------------------------------
# Administration de la base (§17)
#
# Consultation de toutes les tables ; modification des seules tables de données
# créées ici. Voir app/base_donnees.py pour le détail de cette frontière et les
# raisons qui la motivent.
# ------------------------------------------------------------

class ColonneIn(BaseModel):
    nom: str
    type: str = "texte"
    obligatoire: bool = False


class TableIn(BaseModel):
    nom: str
    libelle: str
    description: Optional[str] = None
    colonnes: list[ColonneIn] = []


class LigneIn(BaseModel):
    valeurs: dict


def _executer(operation, session: Session):
    """
    Transforme un refus en 422, plutôt qu'en erreur serveur.

    Deux sortes de refus, et l'utilisateur n'a pas à savoir laquelle : celui que
    l'application formule elle-même (`OperationRefusee`), et **celui que la base
    oppose** — un doublon sur une colonne unique, une valeur qu'un changement de
    type ne sait pas convertir. Le second remontait en 500 : l'écran annonçait une
    panne là où il s'agissait d'une donnée à corriger, et le motif restait dans
    les journaux du serveur.
    """
    try:
        return operation()
    except base_donnees.OperationRefusee as erreur:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(erreur))
    except SQLAlchemyError as erreur:
        session.rollback()
        raise HTTPException(status_code=422, detail=_message_base(erreur))


def _message_base(erreur: Exception) -> str:
    """
    Traduit ce que dit MariaDB en une phrase qui indique quoi faire.

    Le message d'origine est conservé en fin de phrase quand il n'est pas
    reconnu : mieux vaut une formulation technique qu'un « une erreur est
    survenue » qui n'apprend rien et qu'on ne peut pas rapporter.
    """
    original = getattr(erreur, "orig", erreur)
    code = None
    arguments = getattr(original, "args", ())
    if arguments and isinstance(arguments[0], int):
        code = arguments[0]
    texte = str(original)

    if code == 1062:      # Duplicate entry 'X' for key 'Y'
        valeur = re.search(r"Duplicate entry '([^']*)'", texte)
        precision = f" « {valeur.group(1)} »" if valeur else ""
        return (f"Cette valeur{precision} existe déjà, et cette colonne doit rester unique. "
                f"Corrigez la ligne, ou retirez la contrainte d'unicité.")
    if code in (1292, 1366, 1265):    # valeur incompatible avec le type
        valeur = re.search(r"value: '([^']*)'", texte) or re.search(r"'([^']*)'", texte)
        precision = f" « {valeur.group(1)} »" if valeur else ""
        return (f"Une valeur existante{precision} ne se convertit pas dans ce type. "
                f"La table n'a pas été modifiée : corrigez cette valeur d'abord.")
    if code == 1451:      # ligne référencée ailleurs
        return ("D'autres données s'appuient sur cette ligne : elle ne peut pas être "
                "supprimée telle quelle.")
    if code == 1406:      # valeur trop longue
        return "Une valeur dépasse la longueur permise par ce type de colonne."
    return f"La base a refusé l'opération : {texte[:300]}"


@router.get("/base/types-colonnes", dependencies=[Depends(exiger("donnees"))])
def lister_types_colonnes():
    """Types utilisables pour une colonne. Liste fermée : aucun SQL libre n'est accepté."""
    return sorted(base_donnees.TYPES_COLONNES)


# ------------------------------------------------------------
# Dépôt : ce qui s'y trouve sans y avoir sa place (§19.5)
# ------------------------------------------------------------

@router.get("/depots/anomalies", dependencies=[Depends(exiger("travaux"))])
def lister_anomalies_depot(session: Session = Depends(get_session)):
    """
    Ce qui traîne dans le dépôt : dossiers qu'aucun type ne réclame, fichiers
    qu'aucun traitement ne prendra, fichiers en attente au mauvais endroit.

    Les droits posés sur l'arborescence empêchent déjà l'essentiel — personne ne
    crée à la racine. Mais un partage monté en écriture totale, ou un dépôt fait
    par root, passe outre : ce qui ne peut pas être interdit doit être visible.
    """
    return {"racine": config.OCR_WAIT_FOLDER, "entrees": depots.anomalies(session)}


class RangementDemande(BaseModel):
    chemin: str                 # relatif à la racine du dépôt
    categorie_id: int


@router.post("/depots/ranger", dependencies=[Depends(exiger("travaux"))])
def ranger_fichier_egare(
    demande: RangementDemande,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Déplace un fichier égaré dans le dossier de dépôt d'un type.

    Rien d'autre : le fichier devient un dépôt ordinaire, que le serveur de
    travaux relève comme tout autre. C'est le même principe qu'au §19.4 — il n'y
    a pas deux façons d'entrer dans le registre.
    """
    categorie = session.get(Categorie, demande.categorie_id)
    if not categorie:
        raise HTTPException(status_code=404, detail="Type de document introuvable")
    _refuser_si(lambda: natures.exiger_type(session, categorie.id, "de document"))
    if not categorie.dossier_depot:
        raise HTTPException(status_code=400,
                            detail=f"« {categorie.nom} » n'a pas de dossier de dépôt.")
    try:
        source = depots.chemin_sous_la_racine(demande.chemin)
    except depots.DepotRefuse as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    depots.creer(categorie.dossier_depot)
    destination = depots.chemin(categorie.dossier_depot) / source.name
    if destination.exists():
        destination = destination.with_name(
            f"{destination.stem}_{int(time.time())}{destination.suffix}")
    try:
        shutil.move(str(source), str(destination))
    except OSError as erreur:
        raise HTTPException(status_code=500, detail=f"Déplacement impossible : {erreur}")

    audit.journaliser(session, user, "depot.range", "depot", None,
                      details={"fichier": source.name, "categorie": categorie.nom})
    session.commit()
    return {"ok": True, "destination": categorie.dossier_depot}


class RetraitDemande(BaseModel):
    chemin: str


@router.post("/depots/retirer", dependencies=[Depends(exiger("travaux"))])
def retirer_du_depot(
    demande: RetraitDemande,
    session: Session = Depends(get_session),
    user: Utilisateur = Depends(auth.get_current_user),
):
    """
    Sort du dépôt ce qui n'a pas à y être : un fichier part à la corbeille, un
    dossier vide est supprimé.

    Un fichier n'est **jamais détruit** ici : il rejoint la corbeille, d'où il
    reste récupérable le temps de la rétention. Ce qui traîne dans le dépôt a pu
    y être mis par erreur — la destruction est une décision qui se prend en
    connaissance de cause, pas au détour d'un ménage.

    Un dossier non vide n'est pas supprimé : on ne sait pas ce qu'il contient, et
    l'administrateur doit d'abord en traiter les fichiers.
    """
    try:
        cible = depots.chemin_sous_la_racine(demande.chemin)
    except depots.DepotRefuse as refus:
        raise HTTPException(status_code=400, detail=str(refus))
    if cible == Path(config.OCR_WAIT_FOLDER).resolve():
        raise HTTPException(status_code=400, detail="La racine du dépôt ne se retire pas.")

    if cible.is_dir():
        if any(cible.iterdir()):
            raise HTTPException(
                status_code=400,
                detail="Ce dossier n'est pas vide : traitez d'abord ce qu'il contient.")
        try:
            cible.rmdir()
        except OSError as erreur:
            raise HTTPException(status_code=500, detail=f"Suppression impossible : {erreur}")
        audit.journaliser(session, user, "depot.dossier_retire", "depot", None,
                          details={"dossier": demande.chemin})
        session.commit()
        return {"ok": True, "corbeille": False}

    if not cible.is_file():
        raise HTTPException(status_code=404, detail="Introuvable")

    corbeille = Path(config.CORBEILLE_FOLDER)
    corbeille.mkdir(parents=True, exist_ok=True)
    destination = corbeille / cible.name
    if destination.exists():
        destination = destination.with_name(
            f"{destination.stem}_{int(time.time())}{destination.suffix}")
    try:
        shutil.move(str(cible), str(destination))
    except OSError as erreur:
        raise HTTPException(status_code=500, detail=f"Mise en corbeille impossible : {erreur}")

    audit.journaliser(session, user, "depot.retire", "depot", None,
                      details={"fichier": cible.name})
    session.commit()
    return {"ok": True, "corbeille": True}


@router.get("/sources-champs", dependencies=[Depends(exiger("reglages"))])
def lister_sources_champs(session: Session = Depends(get_session)):
    """
    Sources de valeurs proposables pour un champ personnalisé : les tables de
    données du foyer, et elles seules (§18.13).

    Les comptes de connexion l'étaient aussi. Ils ne le sont plus : `sys_utilisateurs`
    n'est pas une table de données, ses colonnes ne se règlent pas depuis
    l'administration, et un foyer qui reprendrait l'application héritait de ce
    couplage sans pouvoir y toucher. Les deux notions ne se recouvrent d'ailleurs
    pas — un enfant reçoit des factures sans avoir de compte, un compte peut
    n'être qu'un accès partagé. Ce qu'il faut désigner, ce sont des **personnes** ;
    elles vivent dans une table du foyer, modifiable comme les autres.

    Les valeurs déjà enregistrées vers un compte ont été rapprochées du membre
    correspondant par la migration 031.
    """
    sources = []
    for table in session.query(TableDonnees).order_by(TableDonnees.libelle).all():
        try:
            noms = [c["nom"] for c in base_donnees.colonnes(session, table.nom_table)
                    if c["nom"] != "id"]
            identifiantes = base_donnees.colonnes_identifiantes(session, table.nom_table)
        except Exception:
            # une table déclarée mais disparue ne doit pas emporter l'écran
            noms, identifiantes = [], []
        sources.append({
            "nom": table.nom_table, "libelle": table.libelle, "systeme": False,
            # de quoi proposer les colonnes cherchées par une déduction (§18.47)
            "colonnes": noms, "colonnes_identifiantes": identifiantes,
        })
    return sources


# ------------------------------------------------------------
# Réglages généraux (§18.19) et supervision (§18.18)
# ------------------------------------------------------------

@router.get("/reglages", dependencies=[Depends(exiger("reglages"))])
def lire_reglages_admin(session: Session = Depends(get_session)):
    return {
        # Les secrets ne repartent pas vers l'écran (§21.10) : il montre qu'ils
        # existent, pas leur valeur.
        "valeurs": reglages.tous(session, masquer_secrets=True),
        "champs": reglages.decrire(),
        "groupes": [{"cle": cle, "libelle": libelle, "description": description}
                    for cle, libelle, description in reglages.GROUPES],
        "fuseaux": reglages.fuseaux_proposables(),
    }


@router.put("/reglages", dependencies=[Depends(exiger("reglages"))])
def enregistrer_reglages(
    valeurs: dict,
    session: Session = Depends(get_session),
    utilisateur: Utilisateur = Depends(auth.get_current_user),
):
    """
    Enregistre un lot de réglages. Tout est validé avant que rien ne soit écrit :
    un fuseau horaire inconnu rendrait toutes les heures illisibles d'un coup.

    **Le journal ne consigne que ce qui a bougé**, avec l'ancienne et la nouvelle
    valeur. Il recevait auparavant l'état complet — dix-neuf réglages dont
    dix-huit inchangés —, si bien que relire l'entrée ne disait rien de ce qui
    avait changé : exactement l'inverse de ce qu'on lui demande. Un lot qui ne
    change rien ne laisse plus de trace du tout ; un journal qui consigne des
    non-événements se relit mal.
    """
    avant = reglages.tous(session, masquer_secrets=True)
    try:
        resultat = reglages.enregistrer(session, valeurs)
    except reglages.ReglageInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))

    touches = [cle for cle in valeurs
               if cle in resultat and avant.get(cle) != resultat.get(cle)]
    if touches:
        audit.journaliser(
            session, utilisateur, "reglages.modification", "reglages", None,
            details={
                "avant": {cle: avant.get(cle) for cle in touches},
                "apres": {cle: resultat.get(cle) for cle in touches},
                # Les intitulés voyagent avec l'événement : « duree_session_heures »
                # ne se relit pas, et le réglage peut être renommé — voire retiré —
                # entre le moment où on le change et celui où on relit le journal.
                "libelles": {cle: reglages.CONNUS[cle].libelle
                             for cle in touches if cle in reglages.CONNUS},
            })
    session.commit()
    return resultat


# ------------------------------------------------------------
# Configuration : la sortir, la reprendre, partir d'un modèle (§18.26)
# ------------------------------------------------------------

@router.get("/configuration", dependencies=[Depends(exiger("reglages"))])
def exporter_configuration(avec_donnees: bool = False,
                           session: Session = Depends(get_session)):
    """
    Rend la configuration du foyer : classement, règles, colonnes, vues, tableaux
    de bord, tables de données. Ni comptes, ni documents, ni journal.

    `avec_donnees` emporte en plus le **contenu** des tables du foyer (membres,
    véhicules) : c'est ce qu'il faut pour déménager son installation, et ce qu'il
    ne faut pas pour publier un modèle.
    """
    return configuration.exporter(session, avec_donnees=avec_donnees)


@router.get("/configuration/modeles", dependencies=[Depends(exiger("reglages"))])
def lister_modeles():
    """Modèles livrés avec l'application : de quoi démarrer sans partir de rien."""
    return modeles.lister()


@router.post("/configuration/import", dependencies=[Depends(exiger("reglages"))])
def importer_configuration(
    payload: dict,
    session: Session = Depends(get_session),
    utilisateur: Utilisateur = Depends(auth.get_current_user),
):
    """
    Applique une configuration : celle d'un fichier, ou celle d'un modèle livré.

    Deux modes, et c'est l'administrateur qui tranche : **compléter** (ce qui
    existe est laissé intact) ou **remplacer** (la configuration existante est
    effacée d'abord, refusé s'il y a des documents).
    """
    donnees = payload.get("configuration")
    if not donnees and payload.get("modele"):
        try:
            donnees = modeles.charger(payload["modele"])
        except KeyError:
            raise HTTPException(status_code=404, detail="Modèle inconnu.")
    if not donnees:
        raise HTTPException(status_code=422, detail="Aucune configuration à importer.")

    try:
        bilan = configuration.importer(session, donnees,
                                       remplacer=bool(payload.get("remplacer")))
    except configuration.ImportRefuse as erreur:
        raise HTTPException(status_code=400, detail=str(erreur))
    except reglages.ReglageInvalide as erreur:
        raise HTTPException(status_code=422, detail=str(erreur))

    audit.journaliser(session, utilisateur, "configuration.import", "configuration", None,
                      details={"mode": "remplacer" if payload.get("remplacer") else "completer",
                               "modele": payload.get("modele"), **bilan})
    session.commit()
    return bilan


@router.get("/supervision", dependencies=[Depends(exiger("travaux"))])
def lire_supervision(session: Session = Depends(get_session)):
    """
    Relevé de l'état de la machine et du service, en lecture seule (§18.18).

    Mesuré sans accès au démon Docker : monter son socket dans l'API lui
    donnerait l'équivalent de root sur l'hôte, prix déraisonnable pour afficher
    des pourcentages.
    """
    return supervision.etat(session)


@router.get("/base/tables", dependencies=[Depends(exiger("donnees"))])
def lister_tables_base(session: Session = Depends(get_session)):
    return base_donnees.lister_tables(session)


@router.get("/base/tables/{nom_table}/colonnes", dependencies=[Depends(exiger("donnees"))])
def lister_colonnes_base(nom_table: str, session: Session = Depends(get_session)):
    return _executer(lambda: base_donnees.colonnes(session, nom_table), session)


@router.get("/base/tables/{nom_table}/lignes", dependencies=[Depends(exiger("donnees"))])
def lire_lignes_base(nom_table: str, limite: int = 50, decalage: int = 0,
                     recherche: Optional[str] = None, session: Session = Depends(get_session)):
    return _executer(
        lambda: base_donnees.lire_lignes(session, nom_table, limite, decalage, recherche), session
    )


@router.post("/base/tables", dependencies=[Depends(exiger("donnees"))])
def creer_table_base(payload: TableIn, session: Session = Depends(get_session),
                     utilisateur: Utilisateur = Depends(auth.require_admin)):
    nom = _executer(lambda: base_donnees.creer_table(
        session, payload.nom, payload.libelle,
        [c.model_dump() for c in payload.colonnes], payload.description,
    ), session)
    audit.journaliser(session, utilisateur, "base.table_creee", "table", None,
                      details={"table": nom, "libelle": payload.libelle,
                               "colonnes": [c.model_dump() for c in payload.colonnes]})
    session.commit()
    return {"ok": True, "nom_table": nom}


class AffichageTableIn(BaseModel):
    libelle: Optional[str] = None
    description: Optional[str] = None
    colonne_libelle: Optional[str] = None
    # liste séparée par des virgules, dans l'ordre voulu : « prenom,nom »
    colonnes_identifiantes: Optional[str] = None


@router.put("/base/tables/{nom_table}", dependencies=[Depends(exiger("donnees"))])
def regler_affichage_table(nom_table: str, payload: AffichageTableIn,
                           session: Session = Depends(get_session),
                           utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Règle la façon dont une table se donne à lire (§18.13).

    Ces réglages existaient en base mais n'étaient posés que par une migration :
    un autre foyer héritait de choix qu'il ne pouvait pas revoir. Ils se règlent
    maintenant ici — c'est ce qui décide qu'une personne s'affiche « Lucas
    DURAND » et non « DURAND », et ce que l'on cherche dans le texte d'un
    document pour lui rattacher une facture.
    """
    resultat = _executer(lambda: base_donnees.regler_affichage(
        session, nom_table, payload.libelle, payload.description,
        payload.colonne_libelle, payload.colonnes_identifiantes,
    ), session)
    audit.journaliser(session, utilisateur, "base.affichage_regle", "table", None,
                      details={"table": nom_table, **resultat})
    session.commit()
    return resultat


@router.post("/base/tables/{nom_table}/colonnes", dependencies=[Depends(exiger("donnees"))])
def ajouter_colonne_base(nom_table: str, payload: ColonneIn, session: Session = Depends(get_session),
                         utilisateur: Utilisateur = Depends(auth.require_admin)):
    _executer(lambda: base_donnees.ajouter_colonne(
        session, nom_table, payload.nom, payload.type, payload.obligatoire), session)
    audit.journaliser(session, utilisateur, "base.colonne_ajoutee", "table", None,
                      details={"table": nom_table, "colonne": payload.model_dump()})
    session.commit()
    return {"ok": True}


class ModificationColonneIn(BaseModel):
    nouveau_nom: Optional[str] = None
    type: Optional[str] = None
    obligatoire: Optional[bool] = None


class ReglageColonneIn(BaseModel):
    libelle: Optional[str] = None
    source_table: Optional[str] = None


class UniciteIn(BaseModel):
    colonnes: list[str] = []
    contrainte: Optional[str] = None     # nom de la contrainte à remplacer/retirer


@router.put("/base/tables/{nom_table}/colonnes/{nom_colonne}", dependencies=[Depends(exiger("donnees"))])
def modifier_colonne_base(nom_table: str, nom_colonne: str, payload: ModificationColonneIn,
                          session: Session = Depends(get_session),
                          utilisateur: Utilisateur = Depends(auth.require_admin)):
    """Renomme une colonne, change son type ou son caractère obligatoire (§18.32)."""
    resultat = _executer(lambda: base_donnees.modifier_colonne(
        session, nom_table, nom_colonne, payload.nouveau_nom, payload.type, payload.obligatoire,
    ), session)
    audit.journaliser(session, utilisateur, "base.colonne_modifiee", "table", None,
                      details={"table": nom_table, "colonne": nom_colonne, **resultat})
    session.commit()
    return resultat


@router.get("/base/tables/{nom_table}/colonnes/{nom_colonne}/impact", dependencies=[Depends(exiger("donnees"))])
def impact_colonne_base(nom_table: str, nom_colonne: str,
                        session: Session = Depends(get_session)):
    """Ce qu'une suppression emporterait : une confirmation aveugle ne protège de rien."""
    return _executer(lambda: base_donnees.impact_colonne(session, nom_table, nom_colonne), session)


@router.delete("/base/tables/{nom_table}/colonnes/{nom_colonne}", dependencies=[Depends(exiger("donnees"))])
def supprimer_colonne_base(nom_table: str, nom_colonne: str,
                           session: Session = Depends(get_session),
                           utilisateur: Utilisateur = Depends(auth.require_admin)):
    impact = _executer(
        lambda: base_donnees.supprimer_colonne(session, nom_table, nom_colonne), session)
    audit.journaliser(session, utilisateur, "base.colonne_supprimee", "table", None,
                      details={"table": nom_table, **impact})
    session.commit()
    return impact


@router.put("/base/tables/{nom_table}/colonnes/{nom_colonne}/reglage", dependencies=[Depends(exiger("donnees"))])
def regler_colonne_base(nom_table: str, nom_colonne: str, payload: ReglageColonneIn,
                        session: Session = Depends(get_session),
                        utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Intitulé lisible et **liaison vers une autre table** (§18.32) : c'est ainsi
    qu'une colonne « propriétaire » cesse d'être un texte libre pour désigner une
    ligne de « Membres du foyer ».
    """
    resultat = _executer(lambda: base_donnees.regler_colonne(
        session, nom_table, nom_colonne, payload.libelle, payload.source_table), session)
    audit.journaliser(session, utilisateur, "base.colonne_reglee", "table", None,
                      details={"table": nom_table, **resultat})
    session.commit()
    return resultat


@router.get("/base/tables/{nom_table}/unicite", dependencies=[Depends(exiger("donnees"))])
def lire_unicite_base(nom_table: str, session: Session = Depends(get_session)):
    return _executer(lambda: base_donnees.cles_uniques(session, nom_table), session)


@router.put("/base/tables/{nom_table}/unicite", dependencies=[Depends(exiger("donnees"))])
def definir_unicite_base(nom_table: str, payload: UniciteIn,
                         session: Session = Depends(get_session),
                         utilisateur: Utilisateur = Depends(auth.require_admin)):
    """
    Déclare l'identifiant naturel d'une table — ce qui, pour un humain, désigne
    la ligne sans ambiguïté. `id` reste la clé primaire dans tous les cas.
    """
    resultat = _executer(lambda: base_donnees.definir_unicite(
        session, nom_table, payload.colonnes, payload.contrainte), session)
    audit.journaliser(session, utilisateur, "base.unicite_modifiee", "table", None,
                      details={"table": nom_table, **resultat})
    session.commit()
    return resultat


@router.delete("/base/tables/{nom_table}", dependencies=[Depends(exiger("donnees"))])
def supprimer_table_base(nom_table: str, session: Session = Depends(get_session),
                         utilisateur: Utilisateur = Depends(auth.require_admin)):
    """Supprime une table de données et tout son contenu. Irréversible, donc journalisé."""
    nombre = _executer(lambda: base_donnees.supprimer_table(session, nom_table), session)
    audit.journaliser(session, utilisateur, "base.table_supprimee", "table", None,
                      details={"table": nom_table, "lignes_perdues": nombre})
    session.commit()
    return {"ok": True, "lignes_supprimees": nombre}


@router.post("/base/tables/{nom_table}/lignes", dependencies=[Depends(exiger("donnees"))])
def inserer_ligne_base(nom_table: str, payload: LigneIn, session: Session = Depends(get_session),
                       utilisateur: Utilisateur = Depends(auth.require_admin)):
    ligne_id = _executer(lambda: base_donnees.inserer_ligne(session, nom_table, payload.valeurs), session)
    audit.journaliser(session, utilisateur, "base.ligne_creee", "table", ligne_id,
                      details={"table": nom_table, "valeurs": payload.valeurs})
    session.commit()
    return {"ok": True, "id": ligne_id}


@router.put("/base/tables/{nom_table}/lignes/{ligne_id}", dependencies=[Depends(exiger("donnees"))])
def modifier_ligne_base(nom_table: str, ligne_id: int, payload: LigneIn,
                        session: Session = Depends(get_session),
                        utilisateur: Utilisateur = Depends(auth.require_admin)):
    avant = _executer(lambda: base_donnees.lire_ligne(session, nom_table, ligne_id), session)
    _executer(lambda: base_donnees.modifier_ligne(session, nom_table, ligne_id, payload.valeurs), session)
    audit.journaliser(session, utilisateur, "base.ligne_modifiee", "table", ligne_id,
                      details={"table": nom_table, "avant": avant, "apres": payload.valeurs})
    session.commit()
    return {"ok": True}


@router.delete("/base/tables/{nom_table}/lignes/{ligne_id}", dependencies=[Depends(exiger("donnees"))])
def supprimer_ligne_base(nom_table: str, ligne_id: int, session: Session = Depends(get_session),
                         utilisateur: Utilisateur = Depends(auth.require_admin)):
    avant = _executer(lambda: base_donnees.supprimer_ligne(session, nom_table, ligne_id), session)
    audit.journaliser(session, utilisateur, "base.ligne_supprimee", "table", ligne_id,
                      details={"table": nom_table, "valeurs": avant})
    session.commit()
    return {"ok": True}


# ------------------------------------------------------------
# Surveillance des connexions (§14, protection contre la force brute)
#
# Le décompte des échecs vit en mémoire de l'API : cet écran donne l'état
# courant et permet de lever un verrou, tandis que le journal d'audit conserve
# l'historique, lui, à travers les redémarrages.
# ------------------------------------------------------------

class DeverrouillageIn(BaseModel):
    cle: str


@router.get("/connexions", dependencies=[Depends(exiger("comptes"))])
def surveiller_connexions(session: Session = Depends(get_session)):
    """
    Sources actuellement suivies (verrouillées d'abord, puis celles qui
    approchent du seuil), et les derniers verrouillages enregistrés au journal.
    """
    from .api import limiteur_connexion

    historique = (
        session.query(JournalAudit)
        .filter(JournalAudit.action == "auth.verrouillage")
        .order_by(JournalAudit.date_evenement.desc(), JournalAudit.id.desc())
        .limit(50)
        .all()
    )
    lignes = []
    for evenement in historique:
        try:
            details = json.loads(evenement.details) if evenement.details else {}
        except (ValueError, TypeError):
            details = {}
        lignes.append({
            "date": evenement.date_evenement.isoformat(timespec="seconds")
            if evenement.date_evenement else None,
            "adresse": details.get("adresse", ""),
            "identifiant": details.get("identifiant_tente"),
        })

    return {
        "reglages": {
            "max_tentatives": config.LOGIN_MAX_TENTATIVES,
            "fenetre_secondes": config.LOGIN_FENETRE_SECONDES,
            "verrouillage_secondes": config.LOGIN_VERROUILLAGE_SECONDES,
        },
        "entrees": limiteur_connexion.etats(),
        "historique": lignes,
    }


@router.post("/connexions/deverrouiller", dependencies=[Depends(exiger("comptes"))])
def deverrouiller_connexion(payload: DeverrouillageIn, session: Session = Depends(get_session),
                            utilisateur: Utilisateur = Depends(auth.require_admin)):
    """Lève le verrou d'une source et remet son compteur à zéro."""
    from .api import limiteur_connexion

    if not limiteur_connexion.deverrouiller(payload.cle):
        raise HTTPException(status_code=404, detail="Cette source n'est plus suivie.")
    audit.journaliser(session, utilisateur, "auth.deverrouillage", "connexion",
                      details={"cle": payload.cle})
    session.commit()
    return {"ok": True}


@router.post("/connexions/tout-deverrouiller", dependencies=[Depends(exiger("comptes"))])
def tout_deverrouiller(session: Session = Depends(get_session),
                       utilisateur: Utilisateur = Depends(auth.require_admin)):
    from .api import limiteur_connexion

    nombre = limiteur_connexion.tout_deverrouiller()
    audit.journaliser(session, utilisateur, "auth.deverrouillage", "connexion",
                      details={"sources_liberees": nombre})
    session.commit()
    return {"ok": True, "sources_liberees": nombre}


# ------------------------------------------------------------
# Tableaux de bord personnalisés
#
# La composition est réservée aux administrateurs : un tableau partagé
# s'affiche chez tout le monde. Les indicateurs sont validés à l'enregistrement
# — une description fautive découverte à l'affichage serait pénible à corriger.
# ------------------------------------------------------------

class TableauIn(BaseModel):
    nom: str
    description: Optional[str] = None
    widgets: list[dict] = []
    partage: bool = True
    ordre: int = 100


def _valider_widgets(widgets: list[dict], session: Session) -> str:
    from . import statistiques

    if not isinstance(widgets, list):
        raise HTTPException(status_code=422, detail="Les indicateurs doivent être une liste.")
    identifiants = set()
    for position, widget in enumerate(widgets, 1):
        if not isinstance(widget, dict):
            raise HTTPException(status_code=422, detail=f"Indicateur nº{position} illisible.")
        if not (widget.get("titre") or "").strip():
            raise HTTPException(status_code=422, detail=f"L'indicateur nº{position} n'a pas de titre.")
        identifiant = widget.get("id") or f"w{position}"
        if identifiant in identifiants:
            raise HTTPException(status_code=422, detail=f"Deux indicateurs portent l'identifiant « {identifiant} ».")
        identifiants.add(identifiant)
        widget["id"] = identifiant

        # les champs des filtres sont vérifiés même sans valeur : `appliquer()`
        # ignore un filtre vide, une faute de frappe passerait donc inaperçue
        for critere in widget.get("filtres") or []:
            try:
                moteur_filtres.valider_champ(session, (critere or {}).get("champ"))
            except moteur_filtres.FiltreInvalide as erreur:
                raise HTTPException(
                    status_code=422,
                    detail=f"Indicateur « {widget.get('titre')} » : {erreur}",
                )

        # calcul à blanc : la description doit être exploitable dès maintenant
        try:
            statistiques.calculer(session, session.query(Document.id), widget)
        except statistiques.IndicateurInvalide as erreur:
            raise HTTPException(
                status_code=422,
                detail=f"Indicateur « {widget.get('titre')} » : {erreur}",
            )
        except HTTPException:
            raise
        except Exception as erreur:
            # une description mal formée reste une faute de saisie, pas une
            # panne : on l'explique plutôt que de renvoyer une erreur serveur
            raise HTTPException(
                status_code=422,
                detail=f"Indicateur « {widget.get('titre')} » inexploitable : {erreur}",
            )
    return json.dumps(widgets, ensure_ascii=False)


@router.get("/tableaux-de-bord", dependencies=[Depends(exiger("tableaux_partages"))])
def lister_tableaux_admin(session: Session = Depends(get_session)):
    tableaux = session.query(TableauDeBord).order_by(TableauDeBord.ordre, TableauDeBord.nom).all()
    return [{
        "id": t.id, "nom": t.nom, "description": t.description,
        "partage": bool(t.partage), "ordre": t.ordre,
        "widgets": json.loads(t.widgets) if t.widgets else [],
    } for t in tableaux]


@router.post("/tableaux-de-bord", dependencies=[Depends(exiger("tableaux_partages"))])
def creer_tableau(payload: TableauIn, session: Session = Depends(get_session),
                  utilisateur: Utilisateur = Depends(auth.require_admin)):
    if not payload.nom.strip():
        raise HTTPException(status_code=422, detail="Le nom du tableau est obligatoire.")
    tableau = TableauDeBord(
        nom=payload.nom.strip(), description=(payload.description or "").strip() or None,
        widgets=_valider_widgets(payload.widgets, session), partage=payload.partage,
        ordre=payload.ordre, utilisateur_id=utilisateur.id,
    )
    session.add(tableau)
    session.flush()
    audit.journaliser(session, utilisateur, "tableau.creation", "tableau_de_bord", tableau.id,
                      details={"nom": tableau.nom, "indicateurs": len(payload.widgets)})
    session.commit()
    session.refresh(tableau)
    return {"id": tableau.id, "ok": True}


@router.put("/tableaux-de-bord/{tableau_id}", dependencies=[Depends(exiger("tableaux_partages"))])
def modifier_tableau(tableau_id: int, payload: TableauIn, session: Session = Depends(get_session),
                     utilisateur: Utilisateur = Depends(auth.require_admin)):
    tableau = session.get(TableauDeBord, tableau_id)
    if not tableau:
        raise HTTPException(status_code=404, detail="Tableau de bord introuvable")
    if not payload.nom.strip():
        raise HTTPException(status_code=422, detail="Le nom du tableau est obligatoire.")

    tableau.nom = payload.nom.strip()
    tableau.description = (payload.description or "").strip() or None
    tableau.widgets = _valider_widgets(payload.widgets, session)
    tableau.partage = payload.partage
    tableau.ordre = payload.ordre
    audit.journaliser(session, utilisateur, "tableau.modification", "tableau_de_bord", tableau.id,
                      details={"nom": tableau.nom, "indicateurs": len(payload.widgets)})
    session.commit()
    return {"ok": True}


@router.delete("/tableaux-de-bord/{tableau_id}", dependencies=[Depends(exiger("tableaux_partages"))])
def supprimer_tableau(tableau_id: int, session: Session = Depends(get_session),
                      utilisateur: Utilisateur = Depends(auth.require_admin)):
    tableau = session.get(TableauDeBord, tableau_id)
    if not tableau:
        raise HTTPException(status_code=404, detail="Tableau de bord introuvable")
    audit.journaliser(session, utilisateur, "tableau.suppression", "tableau_de_bord", tableau.id,
                      details={"nom": tableau.nom})
    session.delete(tableau)
    session.commit()
    return {"ok": True}


# ------------------------------------------------------------
# Conséquences d'une suppression
# ------------------------------------------------------------

@router.get("/impact-suppression", dependencies=[Depends(exiger("comptes"))])
def impact_suppression(type_objet: str, identifiant: str,
                       session: Session = Depends(get_session)):
    """
    Ce qu'emporte réellement la suppression d'un objet, pour que la confirmation
    dise autre chose que « Êtes-vous sûr ? ».
    """
    try:
        return impact.calculer(session, type_objet, identifiant)
    except impact.ObjetIntrouvable as erreur:
        raise HTTPException(status_code=404, detail=str(erreur))
    except (TypeError, ValueError) as erreur:
        raise HTTPException(status_code=422, detail=f"Demande illisible : {erreur}")
