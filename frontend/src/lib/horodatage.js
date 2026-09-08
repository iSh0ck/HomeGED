/**
 * Lecture des dates et heures venues de l'API (§18.19).
 *
 * **Tout est enregistré en temps universel.** Les conteneurs tournent en UTC, la
 * base aussi : un horodatage rendu par l'API — `2026-09-04T19:45:12` — est donc
 * une heure UTC, écrite sans le dire. Le laisser tel quel à `new Date()` le fait
 * interpréter comme une heure **locale**, et tout se décale de deux heures l'été.
 * C'était le défaut signalé : « il y a 2 heures » sur un document déposé à
 * l'instant.
 *
 * D'où ce module, seul endroit qui sache deux choses :
 *   1. une chaîne sans fuseau vient d'UTC ;
 *   2. elle s'affiche dans le fuseau réglé par le foyer (§ Réglages généraux).
 *
 * Le fuseau est tenu dans une variable de module plutôt que dans un contexte
 * React : il est lu par des fonctions de rendu ordinaires, dans une douzaine
 * d'écrans, et le faire descendre en propriété jusqu'à chacune ne rendrait pas
 * les heures plus justes. Il change une fois au chargement, et lorsqu'un
 * administrateur l'enregistre.
 */
import { t, locale } from "./langue";

const FUSEAU_PAR_DEFAUT = "Europe/Paris";
let fuseauCourant = FUSEAU_PAR_DEFAUT;

export function definirFuseau(fuseau) {
  fuseauCourant = fuseau || FUSEAU_PAR_DEFAUT;
}

export function fuseau() {
  return fuseauCourant;
}

/**
 * `Date` à partir de ce que rend l'API. Une chaîne sans fuseau explicite est
 * comprise comme de l'UTC — c'est ce qu'elle est. Une chaîne qui porte déjà un
 * `Z` ou un décalage est respectée.
 */
export function instant(valeur) {
  if (!valeur) return null;
  if (valeur instanceof Date) return valeur;
  const texte = String(valeur).trim().replace(" ", "T");
  const porteUnFuseau = /(Z|[+-]\d{2}:?\d{2})$/.test(texte);
  const date = new Date(porteUnFuseau ? texte : `${texte}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formater(valeur, options) {
  const date = instant(valeur);
  if (!date) return "";
  return new Intl.DateTimeFormat(locale(), { timeZone: fuseauCourant, ...options }).format(date);
}

/** `04/09/2026` — le jour, dans le fuseau du foyer. */
export function formaterJour(valeur) {
  return formater(valeur, { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** `19h45` */
export function formaterHeure(valeur) {
  const texte = formater(valeur, { hour: "2-digit", minute: "2-digit", hour12: false });
  return texte.replace(":", "h");
}

/** `04/09/2026 à 19h45` */
export function formaterHorodatage(valeur) {
  const jour = formaterJour(valeur);
  return jour ? `${jour} à ${formaterHeure(valeur)}` : "";
}

/** `2026-09-04` dans le fuseau du foyer : sert à regrouper par journée. */
export function cleDuJour(valeur) {
  const date = instant(valeur);
  if (!date) return "";
  // `en-CA` rend l'ordre année-mois-jour, qui se compare et se trie tel quel.
  return new Intl.DateTimeFormat("en-CA", { timeZone: fuseauCourant }).format(date);
}

/**
 * « il y a 3 h ». Une durée écoulée ne dépend d'aucun fuseau — encore faut-il
 * partir du bon instant, ce qui était précisément le défaut.
 */
export function ilYA(valeur, { court = false } = {}) {
  const date = instant(valeur);
  if (!date) return court ? "" : t("à l'instant");
  const secondes = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (secondes < 90) return t("à l'instant");
  const minutes = Math.round(secondes / 60);
  if (minutes < 60) return t("il y a {n} min", { n: minutes });
  const heures = Math.round(minutes / 60);
  if (heures < 24) return t("il y a {n} h", { n: heures });
  const jours = Math.round(heures / 24);
  if (jours <= 7 || court) {
    return jours > 1 ? t("il y a {n} jours", { n: jours }) : t("il y a 1 jour");
  }
  return t("le {date}", { date: formaterHorodatage(valeur) });
}

/** « Aujourd'hui », « Hier », sinon « vendredi 4 septembre 2026 ». */
export function libelleJour(cle) {
  if (!cle) return t("Date inconnue");
  const maintenant = new Date();
  if (cle === cleDuJour(maintenant)) return t("Aujourd'hui");
  if (cle === cleDuJour(new Date(maintenant.getTime() - 86400000))) return t("Hier");
  const [a, m, j] = cle.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, j)).toLocaleDateString(locale(), {
    weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
}

