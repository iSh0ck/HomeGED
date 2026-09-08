/**
 * Chemins de l'application (§18.48).
 *
 * L'écran affiché était jusqu'ici un simple état de React : passer à
 * l'administration ne changeait pas l'adresse, et l'adresse ne disait rien de ce
 * qu'on regardait. Trois conséquences, toutes gênantes :
 *
 *   * impossible d'ouvrir l'administration dans un onglet et le registre dans un
 *     autre — c'est pourtant la façon naturelle de régler quelque chose puis
 *     d'aller en voir l'effet ;
 *   * le bouton « précédent » du navigateur quittait l'application ;
 *   * et surtout : **rien à filtrer pour un proxy en amont**. Restreindre
 *     l'accès à l'administration par adresse IP ou par mot de passe suppose un
 *     chemin à protéger. Il en existe un désormais, `/admin`, à protéger avec
 *     `/api/admin/` — la page sans l'API ne protégerait rien.
 *
 * Volontairement écrit à la main plutôt qu'avec une bibliothèque de routage :
 * cinq écrans sans paramètre d'URL, l'historique du navigateur suffit.
 */

/**
 * Écran ↔ chemin. L'accueil est la racine.
 *
 * Le registre n'en a pas : il n'est pas un écran qu'on ouvre à part, c'est le
 * cœur de l'application, et l'accueil y mène en un clic. Lui donner une adresse
 * n'apportait rien qu'une entrée d'historique de plus — les chemins existent
 * ici pour ouvrir un second onglet et pour offrir prise à un filtrage en amont,
 * or ni l'un ni l'autre ne concerne le registre.
 */
const CHEMINS = {
  accueil: "/",
  admin: "/admin",
  analyse: "/analyse",
};

export const VUE_PAR_DEFAUT = "accueil";

/** Le chemin d'un écran ; celui de l'accueil pour tout écran sans adresse propre. */
export function cheminDeLaVue(vue) {
  return CHEMINS[vue] || CHEMINS[VUE_PAR_DEFAUT];
}

export function vueDuChemin(chemin) {
  const propre = (chemin || "/").replace(/\/+$/, "") || "/";
  const trouvee = Object.entries(CHEMINS).find(([, c]) => c === propre);
  // Un chemin inconnu ramène à l'accueil plutôt qu'à un écran vide : l'adresse
  // peut venir d'un marque-page d'une version antérieure.
  return trouvee ? trouvee[0] : VUE_PAR_DEFAUT;
}

/**
 * Écrit le chemin dans la barre d'adresse sans recharger la page.
 * `remplacer` sert au premier affichage : il ne faut pas empiler une entrée
 * d'historique pour un écran que l'utilisateur n'a pas demandé.
 */
export function ecrireChemin(vue, remplacer = false) {
  const chemin = cheminDeLaVue(vue);
  if (window.location.pathname === chemin) return;
  const methode = remplacer ? "replaceState" : "pushState";
  window.history[methode]({ vue }, "", chemin);
}
