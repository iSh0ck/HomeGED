import { versFrancais } from "../components/champs/dates";
import { estIso } from "./cellules";
import { t } from "./langue";

/**
 * Lecture humaine d'un critère de filtre (§18.52).
 *
 * Les critères sont enregistrés dans le vocabulaire du moteur de filtres —
 * `{champ: "categorie", operateur: "egal", valeur: 2}` — qui est fait pour être
 * exécuté, pas pour être lu. Affiché tel quel, cela donnait « categorie est 2 » :
 * exact, et inutilisable. Personne ne sait ce qu'est la catégorie 2, et
 * l'enregistrement d'une vue est justement le moment où l'on veut vérifier ce
 * que l'on mémorise.
 *
 * Ce module traduit, et rien d'autre : les intitulés viennent des colonnes de la
 * catégorie affichée (celles-là mêmes que l'administrateur a réglées), les
 * valeurs des référentiels déjà chargés par l'application. Aucun libellé n'est
 * réinventé ici, sans quoi ils divergeraient du reste de l'écran.
 */

const PREFIXE_META = "meta:";

/** @traduit-a-la-lecture */
export const LIBELLES_OPERATEUR = {
  contient: "contient",
  egal: "est",
  commence_par: "commence par",
  avant: "avant le",
  apres: "après le",
  entre: "entre",
  vide: "non renseigné",
  non_vide: "renseigné",
};

/** Intitulés des champs du document, quand aucune colonne ne les nomme. */
/** @traduit-a-la-lecture */
const LIBELLES = {
  categorie: "Catégorie",
  date_document: "Date du document",
  date_import: "Déposé le",
  nom_fichier: "Fichier",
  statut: "Statut",
  texte: "Texte du document",
};

/** « meta:montant_ttc » → « Montant ttc » : à défaut de mieux, c'est lisible. */
function libelleParDefaut(champ) {
  if (LIBELLES[champ]) return t(LIBELLES[champ]);
  if (champ.startsWith(PREFIXE_META)) {
    const cle = champ.slice(PREFIXE_META.length).replace(/_/g, " ");
    return cle.charAt(0).toUpperCase() + cle.slice(1);
  }
  return champ;
}

export function libelleDuChamp(champ, colonnes = []) {
  const colonne = colonnes.find((c) => c.champ === champ);
  return colonne?.libelle || libelleParDefaut(champ);
}

/** Une valeur unique, rendue lisible selon le champ qu'elle qualifie. */
function libelleDeLaValeur(champ, valeur, { categories = [] } = {}) {
  if (valeur === null || valeur === undefined || valeur === "") return "";
  const texte = String(valeur);

  if (champ === "categorie") {
    return categories.find((c) => String(c.id) === texte)?.nom || texte;
  }
  if (estIso(texte)) return versFrancais(texte) || texte;
  return texte;
}

/**
 * Rend `{champ, operateur, valeur}` en toutes lettres.
 * `valeur` vaut `""` pour les opérateurs qui n'en prennent pas — « renseigné »
 * se suffit à lui-même.
 */
export function decrireCritere(critere, referentiels = {}) {
  const { colonnes = [] } = referentiels;
  const valeurs = Array.isArray(critere.valeur) ? critere.valeur : [critere.valeur];
  const sansValeur = critere.operateur === "vide" || critere.operateur === "non_vide";

  return {
    champ: libelleDuChamp(critere.champ, colonnes),
    operateur: t(LIBELLES_OPERATEUR[critere.operateur] || critere.operateur),
    valeur: sansValeur
      ? ""
      : valeurs.map((v) => libelleDeLaValeur(critere.champ, v, referentiels))
          .filter((v) => v !== "")
          .join(" → "),
  };
}


/**
 * Le même critère en une ligne : « Catégorie est Factures ».
 *
 * Écrit pour la liste des vues (§19.8), où l'on veut lire d'un coup d'œil ce
 * qu'une vue retient sans avoir à l'ouvrir.
 */
export function decrireCritereEnTexte(critere, referentiels = {}) {
  const { champ, operateur, valeur } = decrireCritere(critere, referentiels);
  return [champ, operateur, valeur].filter(Boolean).join(" ");
}
