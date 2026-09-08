/**
 * Les thèmes de l'interface (§22.50).
 *
 * Un thème est un **fichier de données**, pas du code : une clé, un nom, une
 * description, un drapeau « sombre », et la liste des variables CSS. C'est ce
 * qui permet d'en ajouter un sans toucher à l'application — condition d'un
 * projet ouvert, où quelqu'un doit pouvoir proposer sa palette sans lire le
 * reste.
 *
 * Deux provenances, et la seconde est celle qui compte pour un foyer :
 *
 *   * **livrés** — les fichiers de `src/themes/`, embarqués à la construction.
 *     Ils existent toujours, même sans serveur ;
 *   * **ajoutés** — les fichiers déposés dans le dossier `themes/` de
 *     l'installation, que l'API sert tels quels. Aucune reconstruction : on
 *     copie un `.json`, on recharge la page.
 *
 * Un thème ajouté qui porte la clé d'un thème livré le remplace : c'est ainsi
 * qu'on retouche une palette existante sans la recopier ailleurs.
 */

// `eager` : les thèmes livrés pèsent quelques centaines d'octets et sont
// nécessaires au premier rendu. Les charger à la demande ferait clignoter
// l'interface au démarrage.
const LIVRES = Object.values(import.meta.glob("../themes/*.json", { eager: true }))
  .map((module) => module.default || module);

/** Ce qu'un fichier de thème doit porter pour être utilisable. */
export function themeValide(theme) {
  return Boolean(
    theme && typeof theme === "object"
    && typeof theme.cle === "string" && /^[a-z0-9_-]{2,32}$/.test(theme.cle)
    && theme.variables && typeof theme.variables === "object",
  );
}

/**
 * Le catalogue, thèmes ajoutés compris. `ajoutes` vient de l'API ; en son
 * absence — API muette, page ouverte hors ligne — on garde les livrés, ce qui
 * vaut mieux qu'une interface sans couleurs.
 */
export function catalogue(ajoutes = []) {
  const par_cle = new Map();
  for (const theme of LIVRES) {
    if (themeValide(theme)) par_cle.set(theme.cle, { ...theme, livre: true });
  }
  for (const theme of ajoutes || []) {
    if (themeValide(theme)) par_cle.set(theme.cle, { ...theme, livre: false });
  }
  return [...par_cle.values()];
}

/**
 * Le thème à appliquer pour une clé donnée.
 *
 * `auto` suit le réglage du système : c'est le seul cas où l'application décide
 * elle-même, et elle le fait pour la seule raison qui vaille — l'utilisateur l'a
 * déjà dit à son système d'exploitation.
 *
 * Les anciennes valeurs « clair » et « sombre » (§18.24) restent comprises :
 * un foyer ne doit pas perdre son réglage parce que le catalogue s'est enrichi.
 */
export function themeChoisi(cle, ajoutes = []) {
  const themes = catalogue(ajoutes);
  const trouver = (recherchee) => themes.find((theme) => theme.cle === recherchee);
  const clair = trouver("papier") || themes.find((theme) => !theme.sombre) || themes[0];
  const sombre = trouver("nuit") || themes.find((theme) => theme.sombre) || clair;

  if (!cle || cle === "auto") {
    const prefere = typeof window !== "undefined"
      && window.matchMedia?.("(prefers-color-scheme: dark)")?.matches;
    return prefere ? sombre : clair;
  }
  if (cle === "clair") return clair;
  if (cle === "sombre") return sombre;
  return trouver(cle) || clair;
}
