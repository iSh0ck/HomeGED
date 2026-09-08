# Thèmes et langues

Les deux fonctionnent de la même façon : **un fichier JSON déposé dans un
dossier**. Rien à recompiler, rien à redémarrer — on copie, on recharge la page.

## Thèmes

Cinq sont livrés :

| Thème | Pour |
|---|---|
| **Papier** | Le thème d'origine, chemise cartonnée sur papier crème. |
| **Nuit** | Les mêmes teintes en sombre, pour travailler le soir. |
| **Ardoise** | Sombre et froid ; les couleurs d'état ressortent davantage. |
| **Sépia** | Clair et chaud, contraste doux, pour un écran très lumineux. |
| **Contraste élevé** | Noir sur blanc, traits marqués : vue fatiguée, plein soleil. |

Le foyer en choisit un dans *Administration → Réglages généraux → Affichage* ;
**chacun peut le remplacer** depuis *Mon compte*. La couleur d'accent, elle,
reste au foyer : elle fait partie de son identité.

> 📸 **Capture à placer ici — `images/themes-choix.png`**
> Le sélecteur de thème dans « Mon compte », avec les cinq vignettes et leur
> description.

### Ajouter un thème

Créez `themes/mon-theme.json` :

```json
{
  "cle": "mon-theme",
  "nom": "Mon thème",
  "description": "Ce qu'on gagne à l'utiliser, en une phrase.",
  "sombre": false,
  "accent_par_defaut": "#3e5c46",
  "variables": {
    "--bg-app": "#eae7dd",
    "--bg-panel": "#fffdf8",
    "--bg-panel-alt": "#f4f1e8",
    "--ink": "#22281f",
    "--ink-soft": "#5b5f52",
    "--ink-faint": "#8a8d7d",
    "--amber": "#c68a34",
    "--amber-soft": "#f2e2c4",
    "--brick": "#a23b2e",
    "--brick-soft": "#f0d9d3",
    "--data": "#2e7d51",
    "--data-soft": "#d7e8dd",
    "--line": "#d8d3c4",
    "--line-strong": "#b9b39f",
    "--shadow-panel": "0 12px 32px -12px rgba(34, 40, 31, 0.35)"
  }
}
```

Rechargez la page : il apparaît dans les réglages et dans les profils.

* `sombre: true` fait éclaircir la couleur d'accent pour qu'elle tienne sur un
  fond foncé.
* Un thème dont la `cle` reprend celle d'un thème livré **le remplace** : c'est
  ainsi qu'on retouche *Papier* sans le recopier ailleurs.
* Un fichier mal formé est ignoré, avec un avertissement dans
  `docker compose logs api`. Il n'est jamais servi à moitié.

**Ce qu'il faut respecter** : le texte doit rester lisible sur son fond. Un thème
clair avec `--ink` clair est parfaitement accepté par l'application, et
parfaitement illisible.

## Langues

Le **français est la langue d'origine** : les textes sont dans le code. Une
traduction est un dictionnaire du français vers une autre langue ; ce qu'elle ne
couvre pas s'affiche en français, jamais en vide.

L'anglais est livré. Le foyer choisit dans *Réglages généraux → Affichage*,
chacun peut choisir la sienne depuis *Mon compte*, et « Automatique » suit la
langue du navigateur.

### Ajouter une langue

Créez `langues/es.json` :

```json
{
  "cle": "es",
  "nom": "Español",
  "textes": {
    "Rechercher": "Buscar",
    "Registre documentaire": "Registro documental",
    "Enregistrer": "Guardar"
  }
}
```

Rechargez la page. Les textes absents restent en français.

### Savoir ce qui reste à traduire

```bash
node outils/langue.js          # l'état de chaque langue
node outils/langue.js en       # la liste des textes manquants
node outils/langue.js en --json > /tmp/a-traduire.json
```

L'outil relève tous les appels `t("…")` du code et les compare aux
dictionnaires. Il signale aussi les entrées **inutilisées** — un texte français
corrigé casse la correspondance, et c'est ainsi qu'on s'en aperçoit.

### Traduire davantage d'écrans

Tous les textes ne sont pas encore enveloppés dans `t(…)`. Pour en ajouter un :

```jsx
// avant
<button title="Ranger les pièces">Ranger</button>
// après
<button title={t("Ranger les pièces")}>{t("Ranger")}</button>
```

avec `import { t } from "../lib/langue";` en tête du fichier. La clé **est** le
texte français : il n'y a pas de nom à inventer, et un texte non traduit reste
lisible.

## Contribuer

Un thème ou une traduction sont les contributions les plus simples à ce projet :
elles ne demandent de lire aucun code. Placez le fichier dans
`frontend/src/themes/` ou `frontend/src/langues/` pour qu'il soit livré avec
l'application, plutôt que dans les dossiers de l'installation.
