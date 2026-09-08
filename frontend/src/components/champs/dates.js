/**
 * Conversions de dates entre ce que l'utilisateur écrit et ce que l'API attend.
 *
 * L'API parle ISO (`2026-09-04`), les Français écrivent `04/09/2026`. Tout le
 * reste du projet manipule l'ISO ; la conversion vit ici, en un seul endroit,
 * et sans dépendance : `Date` suffit dès lors qu'on ne lui demande pas de
 * comprendre un format localisé — ce qu'elle fait mal et différemment selon les
 * navigateurs.
 */

/** @traduit-a-la-lecture */
export const JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
/** @traduit-a-la-lecture */
export const MOIS = [
  "janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];

/** `2026-09-04` → `04/09/2026`. Rend "" si l'entrée n'est pas une date ISO. */
export function versFrancais(iso) {
  const parties = /^(\d{4})-(\d{2})-(\d{2})$/.exec((iso || "").slice(0, 10));
  return parties ? `${parties[3]}/${parties[2]}/${parties[1]}` : "";
}

/**
 * `04/09/2026` → `2026-09-04`. Rend "" si la saisie n'est pas encore complète
 * ou si la date n'existe pas (le 31 février se refuse au lieu de glisser au
 * 3 mars, comme le ferait `new Date`).
 */
export function versIso(francais) {
  const parties = /^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/.exec((francais || "").trim());
  if (!parties) return "";
  const [, jour, mois, annee] = parties.map(Number);
  if (mois < 1 || mois > 12 || jour < 1 || jour > joursDuMois(annee, mois - 1)) return "";
  return `${annee}-${String(mois).padStart(2, "0")}-${String(jour).padStart(2, "0")}`;
}

export function joursDuMois(annee, mois) {
  return new Date(annee, mois + 1, 0).getDate();
}

/** Indice du jour de la semaine, lundi = 0 — l'ordre du calendrier français. */
export function premierJourDeGrille(annee, mois) {
  return (new Date(annee, mois, 1).getDay() + 6) % 7;
}

export function isoDuJour(date = new Date()) {
  return [date.getFullYear(),
          String(date.getMonth() + 1).padStart(2, "0"),
          String(date.getDate()).padStart(2, "0")].join("-");
}

/** Grille de 6 semaines : les jours du mois, précédés/suivis de `null`. */
export function grilleDuMois(annee, mois) {
  const cases = Array(premierJourDeGrille(annee, mois)).fill(null);
  for (let jour = 1; jour <= joursDuMois(annee, mois); jour += 1) cases.push(jour);
  while (cases.length % 7 !== 0) cases.push(null);
  return cases;
}
