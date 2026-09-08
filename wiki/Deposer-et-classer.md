# Déposer et classer

## Les dossiers de dépôt

`ocr_wait/` contient **un dossier par type de document**, créé et renommé par
l'application. Déposer un fichier dedans, c'est dire ce qu'il est.

```
ocr_wait/
├── factures/
├── banque/
├── fiches_de_paies/
└── diplomes/
```

Ces dossiers appartiennent à la GED : on y dépose, on n'y crée rien. Un fichier
posé à la racine ou dans un dossier ajouté à la main n'est pas ignoré — il part
au Centre d'analyse, section « À classer ».

*Administration → Dépôt* liste ce qui traîne où il ne devrait pas.

## Ce qui se passe ensuite

1. **empreinte** — un fichier déjà présent est reconnu comme doublon ;
2. **océrisation** — un PDF qui porte déjà du texte le garde ; un scan est
   rastérisé ;
3. **extraction** — les règles du type remplissent les champs ;
4. **rattachement** — les champs adossés à une table sont déduits du texte ;
5. **conformité** — s'il manque un champ exigé, le document part au Centre
   d'analyse ;
6. **archivage** — le PDF rejoint `storage/AAAA/MM/`.

Comptez une dizaine de secondes. *Administration → Serveur de travaux* montre où
en est chaque traitement, et pourquoi l'un a échoué.

## Les fiches simples

Une fiche n'a **pas** de dossier de dépôt : rien n'y entre tout seul. C'est le
sens de cette nature — ce qu'on y range arrive rarement et qu'aucune règle ne
saurait lire : un acte notarié, une carte grise, un entretien de véhicule.

On y crée une entrée à la main, avec ses champs, et **facultativement** un
fichier glissé dessus.

> 📸 **Capture à placer ici — `images/fiche.png`**
> La création d'une entrée dans une fiche « Entretiens » : les champs déclarés,
> le sélecteur de véhicule, le champ « factures liées », et la zone de dépôt.

## Les pièces jointes

Une facture, sa garantie et son bon de livraison sont **un seul dossier**. Depuis
un document, « Joindre une pièce » ajoute un fichier au même document plutôt que
d'en créer un autre : les champs sont remplis une fois, le classement décidé une
fois.

Une pièce se lit, se promeut en pièce principale (c'est elle que le registre
ouvre), se range dans l'ordre, ou se détache.

## Rescanner

Déposer à nouveau le même document en désignant la pièce à remplacer en fait une
**nouvelle version**. L'ancienne est conservée : on peut la relire et y revenir.

## Doublons

Un fichier dont l'empreinte est déjà connue n'est pas indexé deux fois. Le
travail le dit, et pointe le document existant.
