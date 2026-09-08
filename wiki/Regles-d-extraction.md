# Règles d'extraction

Une règle lit une valeur dans le texte océrisé d'un document et la range dans un
champ : le numéro d'une facture, sa date, son montant.

## Comment c'est organisé

* Un **jeu de règles** appartient à un type de document. Un type peut en avoir
  plusieurs — un par émetteur, par exemple — et le jeu **générique** sert quand
  aucun autre n'est reconnu.
* Une **règle** vise un champ (`meta:montant_ttc`), avec une expression
  régulière, ou une fonction prête à l'emploi (« première date trouvée »).
* Un **champ attendu**, lui, dit ce que le type *exige*. Une règle qui remplit un
  champ qu'aucun type n'attend ne sert à rien ; un champ attendu qu'aucune règle
  ne remplit se saisit à la main.

> 📸 **Capture à placer ici — `images/regles.png`**
> L'écran « Règles d'extraction » : le choix du type et du jeu, la liste des
> règles avec leur référence (R-0042), leur champ cible et leur motif.

## Écrire une règle

*Administration → Règles d'extraction → Nouvelle règle*

| Champ | Ce qu'on y met |
|---|---|
| **Nom** | Ce que la règle cherche, en français. « Montant TTC (total à payer) ». |
| **Champ cible** | Où ranger la valeur : `meta:montant_ttc`. |
| **Expression** | Le motif. Le **premier groupe** `( … )` est la valeur retenue. |
| **Drapeaux** | `(?i)` ignore la casse — presque toujours ce qu'il faut sur de l'océrisé. `(?im)` ajoute le mode ligne par ligne. |
| **Fonction** | Une normalisation : `nombre_normalise`, `date_normalisee`. |
| **Priorité** | La plus petite gagne quand plusieurs règles visent le même champ. |

Exemple, pour un montant :

```
(?i)(?:total|montant)\s*(?:à\s*payer|ttc)\s*:?\s*([0-9]{1,3}(?:[  ][0-9]{3})*[.,][0-9]{2})
```

## L'apprendre en la montrant *(bêta)*

Écrire une expression régulière à l'aveugle est la boucle la plus décourageante :
on décrit avec des symboles ce qu'on a sous les yeux, on enregistre, on relance
un traitement, et l'on découvre que le motif ne prend rien.

*Règles d'extraction → **Apprendre depuis un document***

1. Choisissez un document — dans la GED, ou **importez-en un** qui n'y est pas
   encore (il est lu puis effacé, il n'entre pas au registre) ;
2. cliquez **la valeur** sur la page ;
3. cliquez **l'intitulé qui l'annonce** — c'est lui qui permettra de la retrouver
   ailleurs ;
4. la règle proposée s'affiche **avec ce qu'elle extrait de ce document-ci**.

Elle reste modifiable avant enregistrement : la vérification a lieu avant, pas
après un retraitement complet.

> 📸 **Capture à placer ici — `images/apprentissage.png`**
> La fenêtre « Apprendre une règle en la montrant » : les deux onglets (document
> de la GED / document à importer), la page avec des mots encadrés, et
> l'expression proposée en bas avec « elle extrait bien 174.00 ».

## La déduction : sans expression régulière

Pour un champ adossé à une **table du foyer** — l'émetteur, un véhicule, un
membre — il n'y a pas de motif à écrire : la liste des valeurs *est* le
dictionnaire. Le champ déclare comment chercher :

| Réglage | Quand l'employer |
|---|---|
| **aucune** | Le défaut : on ne cherche rien. |
| **toutes** | La ligne n'est retenue que si **toutes** les colonnes cherchées figurent — prénom **et** nom pour un membre du foyer. |
| **une** | Une seule colonne suffit — une immatriculation, un nom d'émetteur. |
| **tolérance approchée** | Rattrape « 0range » lu pour « Orange ». À ne pas activer sur une immatriculation. |

Trois garde-fous s'appliquent toujours : une seule correspondance possible, jamais
d'écrasement d'une valeur saisie à la main, et les libellés de moins de trois
caractères ignorés.

## Vérifier qu'une règle marche

* Le **Centre d'analyse** montre les documents à qui il manque un champ.
* *Administration → Serveur de travaux* → « Rejouer » relance l'extraction sur un
  document existant, après correction d'une règle.
* Le **journal d'audit** garde la trace de toute création, modification ou
  suppression de règle.
