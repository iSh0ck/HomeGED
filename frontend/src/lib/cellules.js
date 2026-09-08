import { versFrancais } from "../components/champs/dates";
import { locale } from "./langue";

/**
 * Lecture d'une cellule du tableau (§18.1).
 *
 * Les colonnes ne sont plus codées en dur : l'API décrit celles de la catégorie
 * affichée, et il faut savoir tirer d'un document la valeur d'un champ dont on
 * ne connaît le nom qu'à l'exécution. Tout passe donc par le vocabulaire du
 * moteur de filtres — `date_document`, `meta:<cle>`, `lien:<table>` — le même
 * qui sert à filtrer et à trier.
 */

const PREFIXE_META = "meta:";

/** Valeur brute d'un champ pour un document, ou "" s'il n'en porte pas. */
export function valeurBrute(doc, champ) {
  if (!doc || !champ) return "";
  if (champ.startsWith(PREFIXE_META)) {
    const cle = champ.slice(PREFIXE_META.length);
    // Une métadonnée qui pointe une ligne d'une table vaut « usr_membres:3 » :
    // c'est le libellé résolu par l'API qu'il faut montrer, jamais l'identifiant.
    return doc.libelles_references?.[cle] ?? doc.metadonnees?.[cle] ?? "";
  }
  return doc[champ] ?? "";
}

/**
 * Valeur mise en forme pour l'affichage, selon le type déclaré par la colonne.
 *
 * Une valeur qu'on ne sait pas mettre en forme est rendue telle quelle : elle a
 * été extraite d'un vrai document, et l'afficher imparfaitement vaut toujours
 * mieux que de la faire disparaître.
 */
export function valeurAffichee(doc, colonne) {
  const brute = valeurBrute(doc, colonne.champ);
  if (brute === "" || brute === null || brute === undefined) return "";
  const texte = String(brute);
  // Une valeur écrite `2026-07-21` est une date, quel que soit le type que la
  // colonne déclare : les métadonnées extraites n'ont pas toutes une règle qui
  // annonce leur type, et personne ne lit une date à l'envers. On regarde donc
  // la valeur, pas seulement l'étiquette.
  if (colonne.type === "date" || colonne.champ.startsWith("date_") || estIso(texte)) {
    return versFrancais(texte) || texte;
  }
  if (colonne.type === "montant") return formaterMontant(texte);
  return texte;
}

/** `2026-07-21`, éventuellement suivi d'une heure : la forme rendue par l'API. */
export function estIso(valeur) {
  return /^\d{4}-\d{2}-\d{2}([T ]|$)/.test(String(valeur ?? "").trim());
}

/**
 * « 50.99 » → « 50,99 ». Le séparateur décimal français, et des milliers
 * séparés : c'est ce qui rend une colonne de montants comparable d'un coup
 * d'œil. Aucune unité n'est ajoutée — rien ne dit que le document est en euros,
 * et inventer une devise serait pire que de n'en afficher aucune.
 */
export function formaterMontant(valeur) {
  const texte = String(valeur).trim();
  const nombre = Number(texte.replace(/\s/g, "").replace(",", "."));
  if (!Number.isFinite(nombre) || texte === "") return texte;
  return nombre.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
