# Premiers pas

## Se connecter

Ouvrez **http://\<la machine\>:8081**. Le compte administrateur a été créé à
l'installation ; les autres comptes sont créés depuis l'administration.

> 📸 **Capture à placer ici — `images/connexion.png`**
> L'écran de connexion : le panneau de présentation à gauche (nom du foyer), le
> formulaire à droite.

Si votre compte exige la double authentification, un second écran demande le code
à six chiffres de votre application d'authentification.

## Déposer un premier document

Trois façons, selon ce que vous avez sous la main :

1. **Le dossier de dépôt** — copiez le fichier dans `ocr_wait/<type>/`, par
   exemple `ocr_wait/factures/`. C'est la voie normale, celle d'un scanner
   configuré une fois pour toutes.
2. **Depuis une fiche** — les fiches simples ont une bande « Glissez un fichier
   ici ».
3. **Joint à un document existant** — ouvrez le document, « Joindre une pièce ».

Comptez une dizaine de secondes : le fichier est océrisé, ses champs sont
extraits, il est archivé et apparaît au registre.

> 📸 **Capture à placer ici — `images/depot.png`**
> Le dossier `ocr_wait/` vu depuis l'explorateur de fichiers, avec un dossier par
> type de document.

## Le retrouver

* **La barre de recherche**, en haut : tapez trois lettres. Elle cherche dans le
  texte du document, l'émetteur, le nom du fichier, les champs extraits et les
  choses désignées — « Clio » retrouve la facture du garage qui ne contient
  pourtant nulle part ce mot.
* **La navigation**, à gauche : dossiers et types de document.
* **Les filtres de colonne**, sous les intitulés du tableau.

## Si le document n'apparaît pas

Il est probablement au **Centre d'analyse** : il lui manque un champ que son type
exige, ou son type n'a pas pu être déterminé. Le compteur « à reprendre » de la
barre du haut le signale.

Voir [Le Centre d'analyse](Centre-d-analyse).

## Sur téléphone

L'interface s'adapte : la navigation devient un tiroir (bouton en haut à gauche),
les fenêtres prennent l'écran entier, les tableaux défilent latéralement. Le
dépôt depuis un téléphone passe par une fiche ou par une pièce jointe.

> 📸 **Capture à placer ici — `images/telephone.png`**
> Deux copies d'écran de téléphone côte à côte : le registre avec le tiroir
> fermé, et le tiroir ouvert par-dessus.
