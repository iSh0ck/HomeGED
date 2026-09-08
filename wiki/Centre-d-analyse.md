# Le Centre d'analyse

C'est la liste de ce qui attend quelque chose de vous. Deux natures s'y côtoient,
et elles ne demandent pas le même geste.

> 📸 **Capture à placer ici — `images/centre-analyse.png`**
> Le Centre d'analyse avec ses deux sections : « À classer » en haut, et un
> document incomplet en dessous avec son aperçu et le champ manquant.

## Les documents incomplets

Il leur manque un champ que leur type **exige**. Tant qu'ils sont incomplets, ils
n'apparaissent **pas** au registre et ne comptent pas dans les tableaux de bord :
les afficher classés laisserait croire que le classement est fait.

L'écran montre la page à gauche, les champs à remplir à droite. Dès qu'il est
complet, le document rejoint sa catégorie — sans retraitement.

Un champ adossé à une table (émetteur, véhicule) se choisit dans une liste ; les
autres se saisissent selon leur type — un calendrier pour une date, un montant
pour un montant.

## Les fichiers à classer

Ils ont été déposés à la racine de `ocr_wait/`, ou dans un dossier qu'aucun type
ne réclame. Ils **n'ont pas été océrisés** : tant qu'on ignore de quoi il s'agit,
le texte reconnu ne servirait à rien.

Une seule question se pose — de quel type est-ce ? — et c'est la seule que
l'écran pose. « Examiner » ouvre le fichier tel qu'il a été déposé.

Un fichier qui n'a rien à faire là — un double scan, une page de garde — s'écarte
sans être classé.

> Ces deux actions demandent le droit général **Centre d'analyse**.

## L'écran se tient à jour tout seul

Un dépôt met quelques secondes à devenir un document. La liste se relit toutes
les dix secondes, sans clignoter, et s'arrête quand l'onglet passe à
l'arrière-plan. Le compteur de la barre du haut suit le même rythme.

## Pourquoi un document revient-il ici après coup ?

Parce qu'un **champ attendu a été ajouté** à son type. La conformité est
recalculée pour toute la catégorie quand ses champs changent : des documents déjà
rangés peuvent redevenir incomplets. C'est voulu — sans quoi une exigence
nouvelle ne s'appliquerait qu'aux documents à venir.
