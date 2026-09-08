/**
 * Les drapeaux d'une expression régulière (§22.30).
 *
 * Un motif peut commencer par un groupe de drapeaux — `(?i)`, `(?m)`, `(?im)` —
 * qui change la façon dont **tout** le motif est lu. Python ne les accepte qu'en
 * tête ; écrits ailleurs, ils font une erreur de syntaxe.
 *
 * Les deux fonctions vivent ici et nulle part ailleurs : l'écran des règles les
 * lit et les écrit, et une chaîne recomposée à deux endroits finit par diverger
 * — l'un accepterait `(?mi)` que l'autre ne saurait plus relire.
 */

/** Le groupe de drapeaux en tête du motif, ou "" s'il n'y en a pas. */
export function drapeauxDe(motif) {
  const trouve = /^\(\?([aiLmsux]+)\)/.exec(motif || "");
  if (!trouve) return "";
  // Rangés dans le même ordre que ce que l'écran propose : `(?mi)` et `(?im)`
  // font la même chose, et l'on ne veut pas de deux libellés pour un seul état.
  const lettres = [...new Set(trouve[1].split(""))].sort().join("");
  return `(?${lettres})`;
}

/** Le motif sans son groupe de drapeaux — ce qu'on montre à qui l'écrit. */
export function motifSansDrapeaux(motif) {
  return (motif || "").replace(/^\(\?[aiLmsux]+\)/, "");
}

/**
 * Le motif avec ces drapeaux-là, et eux seuls.
 *
 * `drapeaux` vaut "" (aucun) ou un groupe complet, `(?i)` par exemple. On
 * remplace au lieu d'ajouter : deux groupes à la suite ne sont pas une double
 * précaution, c'est une erreur de syntaxe.
 */
export function avecDrapeaux(motif, drapeaux) {
  const nu = motifSansDrapeaux(motif);
  return drapeaux ? `${drapeaux}${nu}` : nu;
}
