/**
 * Les langues de l'interface (§22.51).
 *
 * **La clé de traduction est le texte français lui-même.** `t("Enregistrer")`
 * cherche « Enregistrer » dans le dictionnaire de la langue active, et rend le
 * français si elle ne l'y trouve pas. Ce choix a trois conséquences, toutes
 * voulues :
 *
 *   * **rien ne casse jamais.** Une phrase non traduite s'affiche en français,
 *     là où une clé inventée afficherait « registre.entete.titre » ;
 *   * **un fichier de langue se lit sans le code.** C'est un dictionnaire
 *     français → autre langue, que quelqu'un peut compléter sans rien connaître
 *     du projet — condition pour qu'une traduction arrive de l'extérieur ;
 *   * **on ne renomme jamais une clé.** Corriger une faute dans le français
 *     casse la correspondance : c'est le prix, et `outils/langue.js` liste ce
 *     qui n'est plus traduit pour qu'on s'en aperçoive.
 *
 * Deux provenances, comme pour les thèmes : les fichiers livrés dans
 * `src/langues/`, et ceux déposés dans le dossier `langues/` de l'installation,
 * que l'API sert. Déposer `es.json` suffit à ajouter l'espagnol.
 */

const LIVREES = Object.values(import.meta.glob("../langues/*.json", { eager: true }))
  .map((module) => module.default || module);

// Le français est la langue d'origine : ses textes sont dans le code, elle n'a
// donc pas de dictionnaire. La déclarer ici lui donne quand même un nom et une
// place dans le menu.
const ORIGINE = { cle: "fr", nom: "Français", textes: {} };

let ajoutees = [];
let active = ORIGINE;
let dictionnaire = {};
const abonnes = new Set();

export function langueValide(langue) {
  return Boolean(
    langue && typeof langue === "object"
    && typeof langue.cle === "string" && /^[a-z0-9_-]{2,32}$/.test(langue.cle)
    && langue.textes && typeof langue.textes === "object",
  );
}

/** Les langues disponibles : l'origine, les livrées, celles déposées. */
export function languesDisponibles() {
  const par_cle = new Map([[ORIGINE.cle, { ...ORIGINE, livree: true }]]);
  for (const langue of LIVREES) {
    if (langueValide(langue)) par_cle.set(langue.cle, { ...langue, livree: true });
  }
  for (const langue of ajoutees) {
    if (langueValide(langue)) par_cle.set(langue.cle, { ...langue, livree: false });
  }
  return [...par_cle.values()];
}

/** Enregistre les langues reçues de l'API. */
export function poserLanguesAjoutees(langues) {
  ajoutees = Array.isArray(langues) ? langues.filter(langueValide) : [];
  // La langue active peut venir d'un fichier déposé : on la relit.
  definirLangue(active.cle);
  return ajoutees;
}

/**
 * Choisit la langue. `auto` suit le navigateur — la seule fois où l'application
 * décide seule, et pour la bonne raison : l'utilisateur l'a déjà dit ailleurs.
 */
export function definirLangue(cle) {
  // Rien de demandé : on garde la langue en cours. Un appel qui reçoit
  // `undefined` — un réglage pas encore chargé, un profil sans préférence — ne
  // doit pas faire basculer l'interface sous les yeux de qui lit. Seul « auto »,
  // demandé explicitement, suit le navigateur.
  if (cle === undefined || cle === null || cle === "") return active.cle;

  const disponibles = languesDisponibles();
  let voulue = cle;
  if (voulue === "auto") {
    const navigateur = typeof navigator !== "undefined"
      ? (navigator.language || "fr").slice(0, 2).toLowerCase() : "fr";
    voulue = disponibles.some((l) => l.cle === navigateur) ? navigateur : ORIGINE.cle;
  }
  active = disponibles.find((l) => l.cle === voulue) || ORIGINE;
  dictionnaire = active.textes || {};
  if (typeof document !== "undefined") {
    document.documentElement.lang = active.cle;
  }
  for (const abonne of abonnes) abonne(active.cle);
  return active.cle;
}

export function langueActive() {
  return active.cle;
}

// Une langue ne dit pas seulement les mots : elle dit aussi « 1 234,56 » ou
// « 1,234.56 », « 04/09/2026 » ou « 09/04/2026 ». `en-GB` plutôt que `en-US`
// pour garder le jour devant le mois : le reste de l'écran le suppose.
const REGIONS = { fr: "fr-FR", en: "en-GB" };

/** L'étiquette BCP-47 à donner à Intl pour la langue active. */
export function locale() {
  return REGIONS[active.cle] || active.cle;
}

/** S'abonner aux changements de langue : rend de quoi se désabonner. */
export function surChangementDeLangue(fonction) {
  abonnes.add(fonction);
  return () => abonnes.delete(fonction);
}

/**
 * Traduit. `defaut` n'existe que pour les textes construits — sinon la clé
 * **est** le français, et c'est elle qu'on affiche à défaut de mieux.
 *
 * `valeurs` remplace les marques `{nom}` : « {nombre} documents » devient
 * « 3 documents ». Les marques survivent à la traduction, ce qui laisse
 * l'ordre des mots libre — l'anglais ne place pas toujours le nombre en tête.
 */
export function t(cle, valeurs = null) {
  let texte = dictionnaire[cle] ?? cle;
  if (valeurs) {
    for (const [nom, valeur] of Object.entries(valeurs)) {
      texte = texte.split(`{${nom}}`).join(String(valeur));
    }
  }
  return texte;
}
