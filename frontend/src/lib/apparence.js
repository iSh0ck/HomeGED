/**
 * Application des réglages d'affichage (§18.24, §22.50).
 *
 * Le foyer choisit son thème, sa couleur d'accent et la densité de ses tableaux ;
 * ce module les pose sur le document. Tout passe par les variables CSS déjà en
 * place : aucun composant n'a besoin de savoir qu'un thème existe, il continue de
 * lire `--ink` et `--bg-panel`.
 *
 * Les palettes elles-mêmes vivent dans `src/themes/*.json` et dans le dossier
 * `themes/` de l'installation (cf. `lib/themes.js`) : ajouter une palette est un
 * fichier à déposer, pas du code à écrire.
 */
import { catalogue, themeChoisi } from "./themes";

// Toutes les variables qu'un thème peut poser. Elles sont retirées avant chaque
// application : sans cela, passer d'une palette sombre à une palette claire
// garderait les couleurs de la première pour tout ce que la seconde ne redéfinit
// pas — et l'on obtiendrait un mélange que personne n'a choisi.
const VARIABLES = [
  "--bg-app", "--bg-panel", "--bg-panel-alt",
  "--ink", "--ink-soft", "--ink-faint",
  "--accent", "--accent-soft",
  "--amber", "--amber-soft", "--brick", "--brick-soft",
  "--data", "--data-soft",
  "--line", "--line-strong", "--shadow-panel",
];

// Les thèmes déposés par le foyer, servis par l'API. Gardés ici parce que
// `appliquerApparence` est appelée de plusieurs endroits et ne doit pas avoir à
// les transporter.
let themesAjoutes = [];

/** Enregistre les thèmes reçus de l'API. Rendre la liste permet de la relire. */
export function poserThemesAjoutes(themes) {
  themesAjoutes = Array.isArray(themes) ? themes : [];
  return themesAjoutes;
}

/** Le catalogue complet, pour l'écran de réglages. */
export function themesDisponibles() {
  return catalogue(themesAjoutes);
}

/** Éclaircit une couleur hexadécimale, pour qu'elle tienne sur un fond sombre. */
export function eclaircir(hex, part = 0.35) {
  const propre = String(hex || "").replace("#", "");
  if (propre.length !== 6) return hex;
  const canaux = [0, 2, 4].map((i) => parseInt(propre.slice(i, i + 2), 16));
  const eclaircis = canaux.map((c) => Math.round(c + (255 - c) * part));
  return `#${eclaircis.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** Assombrit une couleur, pour la teinte « douce » d'un fond clair. */
export function assombrir(hex, part = 0.35) {
  const propre = String(hex || "").replace("#", "");
  if (propre.length !== 6) return hex;
  const canaux = [0, 2, 4].map((i) => parseInt(propre.slice(i, i + 2), 16));
  const assombris = canaux.map((c) => Math.round(c * (1 - part)));
  return `#${assombris.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** Mélange une couleur avec du blanc : la teinte « douce » des sélections. */
export function adoucir(hex, part = 0.72) {
  return eclaircir(hex, part);
}

/**
 * Pose les réglages sur `<html>`. Appelée au chargement et à chaque
 * enregistrement : le changement doit se voir tout de suite, pas au prochain
 * démarrage.
 */
export function appliquerApparence(reglages = {}) {
  if (typeof document === "undefined") return;
  const racine = document.documentElement;
  const theme = themeChoisi(reglages.theme || "auto", themesAjoutes);
  const sombre = Boolean(theme?.sombre);

  // On repart de la feuille de style avant d'appliquer : une palette qui ne
  // redéfinit pas tout ne doit pas hériter des couleurs de la précédente.
  for (const nom of VARIABLES) racine.style.removeProperty(nom);

  for (const [nom, valeur] of Object.entries(theme?.variables || {})) {
    if (VARIABLES.includes(nom)) racine.style.setProperty(nom, valeur);
  }
  // `data-theme` porte la clé **et** la nature : les rares règles CSS qui
  // dépendent du fond peuvent viser l'une ou l'autre.
  racine.dataset.theme = theme?.cle || "papier";
  racine.dataset.fond = sombre ? "sombre" : "clair";

  // La couleur d'accent reste celle du foyer : le thème n'en propose qu'un
  // défaut, et changer de palette ne doit pas effacer un choix explicite.
  const accent = reglages.couleur_accent || theme?.accent_par_defaut || "#3e5c46";
  racine.style.setProperty("--accent", sombre ? eclaircir(accent, 0.25) : accent);
  racine.style.setProperty("--accent-soft", sombre ? assombrir(accent, 0.55) : adoucir(accent));

  racine.dataset.densite = reglages.densite === "compacte" ? "compacte" : "normale";

  if (reglages.nom_foyer) {
    document.title = `${reglages.nom_foyer} — HomeGED`;
  } else {
    document.title = "HomeGED";
  }
}

