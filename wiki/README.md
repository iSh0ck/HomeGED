# Le wiki de HomeGED

Ces pages sont écrites pour être publiées **telles quelles** dans le wiki GitHub
du dépôt.

## Les publier

```bash
git clone https://github.com/<vous>/<le dépôt>.wiki.git /tmp/wiki
cp wiki/*.md /tmp/wiki/
cp -r wiki/images /tmp/wiki/          # une fois les captures ajoutées
cd /tmp/wiki && git add -A && git commit -m "Wiki HomeGED" && git push
```

Les liens internes suivent la convention GitHub : `[Installation](Installation)`
désigne la page `Installation.md`. `Home.md` est la page d'accueil.

## Les captures d'écran

Chaque page porte des emplacements de la forme :

> 📸 **Capture à placer ici — `images/registre.png`**
> ce qui doit y apparaître.

Placez le fichier dans `wiki/images/` sous ce nom exact, puis remplacez le bloc
par `![Le registre](images/registre.png)`.

**Ce qu'il faut vérifier avant de capturer** — ces images vivront longtemps :

* pas de données réelles : ni nom, ni adresse, ni numéro de compte. Le modèle
  « Foyer complet » et quelques documents fabriqués suffisent ;
* la même largeur de fenêtre partout (1440 px est un bon choix), sauf pour les
  captures de téléphone ;
* le thème *Papier* par défaut, sauf sur la page des thèmes ;
* les compteurs cohérents entre les captures : un « 3 à reprendre » sur l'une et
  « 0 » sur l'autre se remarque.

## Liste des captures attendues

| Fichier | Page | Ce qu'on doit y voir |
|---|---|---|
| `accueil.png` | Home | Le tableau de bord d'accueil, cases et graphiques |
| `registre.png` | README | Le registre avec navigation, filtres, fiche ouverte |
| `analyse.png` | README | Un document incomplet en cours de correction |
| `tableau-de-bord.png` | README | Les quatre cases et les deux graphiques |
| `admin-champs.png` | README | L'écran « Assembler un type » |
| `themes.png` | README | Deux thèmes côte à côte |
| `connexion.png` | Premiers pas | L'écran de connexion |
| `depot.png` | Premiers pas | Les dossiers de dépôt dans l'explorateur |
| `telephone.png` | Premiers pas | Le registre sur téléphone, tiroir ouvert et fermé |
| `fiche.png` | Déposer et classer | La création d'une entrée de fiche |
| `centre-analyse.png` | Centre d'analyse | Les deux sections de l'écran |
| `recherche.png` | Chercher | Des résultats avec le « pourquoi » de chacun |
| `vues.png` | Chercher | Les vues enregistrées dans la navigation |
| `categories.png` | Organiser le classement | L'arborescence et les trois natures |
| `montage.png` | Organiser le classement | « Assembler un type » avec un champ à paramétrer |
| `regles.png` | Règles d'extraction | La liste des règles d'un jeu |
| `apprentissage.png` | Règles d'extraction | La fenêtre d'apprentissage visuel |
| `roles.png` | Comptes et droits | La grille des six actions par catégorie |
| `otp.png` | Mon compte | L'appairage et les codes de secours |
| `mon-compte.png` | Mon compte | La section Affichage |
| `sauvegarde.png` | Sauvegarde | L'état et la liste des sauvegardes |
| `installation.png` | Installation | Le choix du modèle de classement |
| `tentatives-connexion.png` | Sécurité avancée | Une adresse verrouillée |
| `themes-choix.png` | Thèmes et langues | Le sélecteur de thème |
