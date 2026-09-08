# Organiser le classement

**Le classement ne se devine pas : il se déclare.** C'est le principe dont tout
le reste découle.

## Trois natures de catégorie

| Nature | Ce qu'elle fait | Exemple |
|---|---|---|
| **Dossier** | Organise. Ne porte aucun document, aucune colonne, aucune règle. Il se déroule, c'est tout. | *Maison*, *Administratif* |
| **Type de document** | Porte les documents et tout ce qui les décrit : dossier de dépôt, colonnes, champs attendus, règles. | *Factures*, *Banque* |
| **Fiche simple** | Des entrées saisies à la main, avec ou sans fichier. Rien n'y entre tout seul. | *Entretiens*, *Contrats verbaux* |

Un type a **son dossier de dépôt** sous `ocr_wait/`, créé et renommé par
l'application. On y dépose ; on n'y crée rien.

> 📸 **Capture à placer ici — `images/categories.png`**
> L'écran Catégories : l'arborescence avec les trois natures distinguées, et le
> formulaire de création montrant le choix de la nature et du parent.

## L'ordre dans lequel monter un classement

Il n'est imposé par aucun écran, mais il évite de revenir en arrière :

1. **Les tables du foyer** (*Base de données*) — émetteurs, membres, véhicules :
   ce sont elles que les champs viendront désigner ;
2. **Les dossiers**, puis les **types** qu'ils contiennent ;
3. **Les champs attendus** de chaque type — ce que le document doit porter ;
4. **Les jeux de règles** et leurs règles — ce qui remplit ces champs ;
5. **Les colonnes** du tableau — ce qu'on veut voir dans la liste ;
6. **Les vues**, les **rôles**, les **tableaux de bord**.

## Assembler un type

*Administration → Assembler un type* réunit les quatre étapes sur un seul écran,
avec l'état de chacune :

* **ce que le document porte** — les champs attendus, obligatoires ou non ;
* **ce qui se remplit tout seul** — pour chaque champ, si sa règle est en place
  ou reste à écrire, avec un bouton pour l'écrire ;
* **ce que le tableau montre** — les colonnes ;
* **les règles** — l'accès direct au jeu du type en cours.

> 📸 **Capture à placer ici — `images/montage.png`**
> L'écran « Assembler un type » sur *Factures*, montrant un champ dont la règle
> est en place et un autre « à paramétrer » avec son bouton.

## Les champs attendus

Un champ attendu dit ce qu'un document de ce type **doit** porter. Un document
auquel il en manque un n'entre pas au registre : il attend au Centre d'analyse.

| Réglage | Ce qu'il décide |
|---|---|
| **Obligatoire** | S'il manque, le document est incomplet. |
| **Identifiant naturel** | Ce qui désigne le document pour un humain (numéro de facture). |
| **Type** | Texte, date, montant, nombre, oui/non — décide de la saisie et de l'affichage. |
| **Source** | Une table du foyer : la valeur se choisit dans une liste au lieu d'être recopiée. |
| **Déduction** | Comment la chercher dans le texte (voir [Règles d'extraction](Regles-d-extraction)). |
| **Attache des documents** | Le champ contient d'autres documents de la GED — « factures liées » sur un entretien. |
| **Échéance et rappel** | Le champ porte une date qui doit prévenir avant d'arriver. |

## Les colonnes

*Administration → Colonnes des tableaux*, par type. Ce qui n'est pas configuré est
**déduit** de ce que portent les documents : une catégorie neuve n'est jamais
vide. « Propager » applique les colonnes d'un type à tous ceux de son dossier.

Chacun peut ensuite **régler la largeur** en tirant le bord d'un intitulé ; c'est
retenu par poste, pas par compte : cela dépend de l'écran.

## Reprendre un classement ailleurs

*Administration → Configuration du foyer* exporte tout ce qui décrit le
classement — arborescence, natures, dossiers de dépôt, tris, jeux de règles,
champs attendus, colonnes, vues, rôles, tables — **sans les documents**. L'import
complète sans écraser, ou remplace si on le demande.
