# Comptes et droits

## Le principe

Un compte n'a par lui-même aucun droit : il porte des **rôles**, et ce sont les
rôles qui donnent des droits. Les rôles **s'additionnent** — un compte qui en
porte deux a l'union de leurs droits.

## Trois axes

### 1. Les droits généraux

Ce qui ne dépend d'aucune catégorie : *Centre d'analyse*, *Serveur de travaux*,
*Tables de données*, *Vues enregistrées*, *Tableaux de bord partagés*, *Export de
l'archive*, *Export d'une sélection*, *Journal d'audit*, *Réglages et
classement*, *Comptes, rôles et droits*.

Accéder à l'administration demande **au moins un** de ces droits ; chaque écran
exige ensuite le sien.

### 2. Les droits par catégorie

Six actions, séparément, pour chaque catégorie : **voir**, **modifier**,
**déposer**, **télécharger**, **supprimer**, **gérer les versions**.

Séparées parce qu'elles ne vont pas ensemble : on peut vouloir qu'un adolescent
voie les factures sans pouvoir les télécharger, ou qu'un comptable dépose sans
pouvoir supprimer.

### 3. Les restrictions par branche

Limiter un compte à *ses* documents : les factures dont il est le titulaire, les
papiers de son véhicule. La restriction porte sur un champ et ses valeurs.

Deux règles, et elles découlent de « les rôles s'additionnent » :
* un rôle **sans aucune ligne** sur un champ n'y met aucune restriction ;
* sinon, les valeurs des rôles s'ajoutent.

> 📸 **Capture à placer ici — `images/roles.png`**
> L'écran Rôles & droits : la grille des six actions par catégorie, et l'onglet
> des droits généraux.

## Double authentification

Chacun peut l'activer depuis *Mon compte*. Un administrateur peut **l'imposer** à
un compte, ou à tout le foyer (*Réglages généraux → Sécurité*).

Des **codes de secours** sont donnés à l'activation : ce sont eux qui évitent de
s'enfermer dehors avec un téléphone perdu. Leur usage est journalisé — c'est le
signe d'un téléphone perdu, ou de quelqu'un d'autre qui entre.

## Consulter sous l'identité de quelqu'un

*Administration → Utilisateurs → Consulter comme* ouvre le registre tel que ce
compte le voit. **Lecture seule**, trente minutes, nominatif, journalisé : c'est
la seule façon fiable de vérifier qu'un jeu de droits fait ce qu'on croit.

## Sessions

*Mon compte → Appareils connectés* liste les sessions ouvertes et permet de les
fermer. Changer son mot de passe ferme **toutes** les autres.
