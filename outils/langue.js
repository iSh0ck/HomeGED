#!/usr/bin/env node
/**
 * Ce qui est traduisible, et ce qui ne l'est pas encore (§22.51).
 *
 *   node outils/langue.js            — l'état de chaque langue
 *   node outils/langue.js en         — les textes qui manquent en anglais
 *   node outils/langue.js en --json  — le squelette à compléter, prêt à coller
 *
 * La clé de traduction **est** le texte français : ce script relève donc tous
 * les appels `t("…")` du code et les compare au dictionnaire de chaque langue.
 * Deux conséquences utiles : un texte français corrigé apparaît aussitôt comme
 * « manquant » (la correspondance est cassée, et il faut le savoir), et une
 * entrée qui ne correspond plus à aucun appel apparaît comme « inutilisée ».
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = join(dirname(fileURLToPath(import.meta.url)), "..");
const RACINE = join(BASE, "frontend", "src");
const SERVEUR = join(BASE, "app");

function fichiers(dossier) {
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom);
    if (statSync(chemin).isDirectory()) return fichiers(chemin);
    return /\.jsx?$/.test(nom) && !nom.includes(".test.") ? [chemin] : [];
  });
}

/** Les textes passés à `t("…")`. Les guillemets simples et les gabarits sont
 *  volontairement ignorés : une clé doit être une chaîne littérale, sans quoi
 *  elle n'est pas relevable — et une clé qu'on ne relève pas ne se traduit pas. */
function clesDuCode() {
  const trouvees = new Set();
  for (const chemin of fichiers(RACINE)) {
    const source = readFileSync(chemin, "utf-8");
    for (const trouve of source.matchAll(/\bt\(\s*"((?:[^"\\]|\\.)*)"/g)) {
      trouvees.add(trouve[1].replace(/\\"/g, '"'));
    }
  }
  return [...trouvees].sort((a, b) => a.localeCompare(b, "fr"));
}

/** Les textes d'affichage que le serveur envoie déjà écrits : intitulés de
 *  réglages, libellés de droits, motifs de refus. L'écran les repasse par t(),
 *  ils comptent donc comme des clés au même titre que celles du code React.
 *
 *  Python recolle les littéraux adjacents ("a " "b" vaut "ab") : le relevé doit
 *  faire de même, sinon on cherche à traduire des moitiés de phrase. */
const CHAMPS = "libelle|aide|description|titre|intitule|detail|message|texte|resume|phrase|conseil|explication";
const CHAINE = String.raw`"(?:[^"\\]|\\.)*"(?:\s*"(?:[^"\\]|\\.)*")*`;

function recoller(brut) {
  return [...brut.matchAll(/"((?:[^"\\]|\\.)*)"/g)]
    .map((m) => m[1].replace(/\\"/g, '"').replace(/\\n/g, "\n"))
    .join("");
}

function affichable(texte) {
  return texte.length >= 3
    && /[A-Za-zÀ-ÿ]{3}/.test(texte)
    && !/^(https?:|\/|\{)/.test(texte)
    && !/^[A-Z][a-z]+[A-Z]/.test(texte);  // AlertTriangle : un nom d'icône, pas une phrase
}

/** Les tables d'affichage du serveur marquées `@traduit-a-la-lecture` : leurs
 *  chaînes sont passées positionnellement (`Champ("", "Nom du foyer", …)`) ou
 *  en tuples, formes qu'aucun motif nom=valeur ne relève. Le bloc entier est
 *  donc pris tel quel, du marqueur jusqu'au retour en colonne zéro.
 *
 *  Le bloc est lu d'un seul tenant, sans découpage en lignes : Python recolle
 *  les littéraux adjacents, et une aide de trois lignes est *une* phrase. */
function techniqueSeulement(texte) {
  // Une clé de réglage, un identifiant de fuseau, un nom de colonne : ce sont
  // des valeurs manipulées, jamais des phrases lues. Le critère est l'absence
  // d'espace — une phrase qui cite une URL reste une phrase.
  return !/\s/.test(texte) && (/\//.test(texte) || /_/.test(texte));
}

function clesDesTablesDuServeur(source) {
  const trouvees = new Set();
  const lignes = source.split("\n");
  for (let i = 0; i < lignes.length; i += 1) {
    if (!lignes[i].includes("@traduit-a-la-lecture")) continue;
    let fin = i + 2;
    // Le bloc s'arrête quand une instruction reprend en colonne zéro.
    while (fin < lignes.length && !(/^\S/.test(lignes[fin]) && !/^[)\]}]/.test(lignes[fin]))) {
      fin += 1;
    }
    const bloc = lignes.slice(i + 1, fin).join("\n");
    for (const trouve of bloc.matchAll(new RegExp(CHAINE, "g"))) {
      const texte = recoller(trouve[0]);
      if (affichable(texte) && !techniqueSeulement(texte)) trouvees.add(texte);
    }
  }
  return trouvees;
}

/** Une chaîne recollée à une valeur au moment de l'exécution ne peut pas être
 *  une clé : « Colonnes absentes : » + la liste ne se retrouvera jamais telle
 *  quelle dans un dictionnaire. On ne la relève donc pas — la relever ferait
 *  traduire une phrase qui resterait en français. */
function concatenee(source, fin) {
  return /^\s*\+/.test(source.slice(fin));
}

function clesDuServeur() {
  const MOTIFS = [
    new RegExp(String.raw`"(?:${CHAMPS})"\s*:\s*(${CHAINE})`, "g"),
    new RegExp(String.raw`\b(?:${CHAMPS})\s*=\s*(${CHAINE})`, "g"),
    new RegExp(String.raw`"[a-z_.]+"\s*:\s*("[A-ZÀ-Þ](?:[^"\\]|\\.)*"(?:\s*"(?:[^"\\]|\\.)*")*)`, "g"),
    // `HTTPException(400, "…")` : le détail passé sans être nommé. C'est la
    // moitié des refus du serveur, et ils s'affichent comme les autres.
    new RegExp(String.raw`HTTPException\(\s*(?:status_code\s*=\s*)?\d{3}\s*,\s*(${CHAINE})`, "g"),
  ];
  const trouvees = new Set();
  for (const nom of readdirSync(SERVEUR).filter((n) => n.endsWith(".py"))) {
    const source = readFileSync(join(SERVEUR, nom), "utf-8");
    for (const motif of MOTIFS) {
      for (const trouve of source.matchAll(motif)) {
        const texte = recoller(trouve[1]);
        if (affichable(texte) && !concatenee(source, trouve.index + trouve[0].length)) {
          trouvees.add(texte);
        }
      }
    }
    for (const texte of clesDesTablesDuServeur(source)) trouvees.add(texte);
  }
  return trouvees;
}

/** Les dictionnaires d'intitulés que le code traduit **à la lecture**.
 *
 *  Un `t()` posé sur la valeur d'une constante de module la figerait dans la
 *  langue de départ ; ces tables restent donc en français et c'est l'accesseur
 *  qui traduit. L'outil ne peut pas le deviner : on le lui dit, en marquant le
 *  bloc d'un `@traduit-a-la-lecture` juste au-dessus.
 *
 *  Seules les **valeurs** comptent : une clé de dictionnaire ne s'affiche pas,
 *  et les propriétés techniques (ton, icône, couleur) non plus. */
const PROPRIETES_MUETTES = new Set(["ton", "icone", "couleur", "opacite", "nature",
  "valeur", "cle", "source", "type", "champs", "format"]);

function clesDesDictionnaires() {
  const trouvees = new Set();
  for (const chemin of fichiers(RACINE)) {
    const lignes = readFileSync(chemin, "utf-8").split("\n");
    for (let i = 0; i < lignes.length; i += 1) {
      if (!lignes[i].includes("@traduit-a-la-lecture")) continue;
      let debut = i + 1;
      while (debut < lignes.length && !/[[{]/.test(lignes[debut])) debut += 1;
      let profondeur = 0;
      for (let j = debut; j < lignes.length; j += 1) {
        for (const c of lignes[j]) {
          if (c === "{" || c === "[") profondeur += 1;
          if (c === "}" || c === "]") profondeur -= 1;
        }
        const ligne = lignes[j];
        for (const trouve of ligne.matchAll(/"((?:[^"\\]|\\.)*)"/g)) {
          const suite = ligne.slice(trouve.index + trouve[0].length);
          if (/^\s*:/.test(suite)) continue;                       // une clé
          const avant = ligne.slice(0, trouve.index);
          const propriete = /([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$/.exec(avant);
          if (propriete && PROPRIETES_MUETTES.has(propriete[1])) continue;
          const texte = trouve[1].replace(/\\"/g, '"');
          if (affichable(texte)) trouvees.add(texte);
        }
        if (profondeur <= 0 && j > debut - 1) break;
      }
    }
  }
  return trouvees;
}

/** Les thèmes livrés portent un nom et une description, affichés dans « Mon
 *  compte ». Ce sont des fichiers de données, pas du code : aucun t() ne les
 *  entoure, et l'écran les traduit à la lecture. */
function clesDesThemes() {
  const dossier = join(RACINE, "themes");
  const trouvees = new Set();
  for (const nom of readdirSync(dossier).filter((n) => n.endsWith(".json"))) {
    const theme = JSON.parse(readFileSync(join(dossier, nom), "utf-8"));
    for (const texte of [theme.nom, theme.description]) {
      if (texte && affichable(texte)) trouvees.add(texte);
    }
  }
  return trouvees;
}

function langues() {
  const dossier = join(RACINE, "langues");
  return readdirSync(dossier)
    .filter((n) => n.endsWith(".json"))
    .map((n) => JSON.parse(readFileSync(join(dossier, n), "utf-8")));
}

const cles = [...new Set([...clesDuCode(), ...clesDuServeur(), ...clesDesDictionnaires(), ...clesDesThemes()])]
  .sort((a, b) => a.localeCompare(b, "fr"));
const voulue = process.argv[2];
const enJson = process.argv.includes("--json");

if (!voulue) {
  console.log(`${cles.length} texte(s) traduisible(s) dans l'interface.\n`);
  console.log("langue        traduits   manquants   inutilisés");
  for (const langue of langues()) {
    const textes = langue.textes || {};
    const traduits = cles.filter((c) => textes[c]).length;
    const inutilises = Object.keys(textes).filter((c) => !cles.includes(c)).length;
    console.log(`${(langue.nom || langue.cle).padEnd(14)}${String(traduits).padStart(8)}`
      + `${String(cles.length - traduits).padStart(12)}${String(inutilises).padStart(13)}`);
  }
  console.log("\nUn texte non traduit s'affiche en français : rien ne casse jamais.");
  console.log("Un nouveau texte se rend traduisible en l'écrivant t(\"…\").");
  process.exit(0);
}

const langue = langues().find((l) => l.cle === voulue);
if (!langue) {
  console.error(`Langue « ${voulue} » inconnue.`);
  process.exit(1);
}
const manquants = cles.filter((c) => !(langue.textes || {})[c]);
if (enJson) {
  console.log(JSON.stringify(Object.fromEntries(manquants.map((c) => [c, ""])), null, 2));
} else {
  console.log(`${manquants.length} texte(s) à traduire en ${langue.nom} :\n`);
  for (const cle of manquants) console.log("  " + cle);
}
