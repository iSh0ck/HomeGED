/**
 * Manipulation de l'arborescence des catégories, à partir de la liste plate
 * renvoyée par l'API (chaque catégorie porte son `parent_id`).
 *
 * Une catégorie dont le parent est absent de la liste — supprimé, ou masqué à
 * cet utilisateur par ses droits — est toujours traitée comme une racine, pour
 * qu'elle reste visible plutôt que d'être silencieusement perdue.
 */

/** Arbre imbriqué : chaque nœud reçoit un tableau `enfants`, trié par nom. */
export function construireArbre(categories) {
  const parId = new Map(categories.map((c) => [c.id, { ...c, enfants: [] }]));
  const racines = [];
  for (const noeud of parId.values()) {
    const parent = noeud.parent_id != null ? parId.get(noeud.parent_id) : null;
    if (parent) parent.enfants.push(noeud);
    else racines.push(noeud);
  }
  // L'ordre voulu par l'administrateur prime ; l'alphabet ne départage que les
  // catégories de même rang.
  const trier = (noeuds) => {
    noeuds.sort((a, b) => (a.ordre ?? 100) - (b.ordre ?? 100) || a.nom.localeCompare(b.nom));
    noeuds.forEach((n) => trier(n.enfants));
    return noeuds;
  };
  return trier(racines);
}

/**
 * Liste plate dans l'ordre de l'arborescence, chaque entrée annotée de sa
 * `profondeur` — pour afficher la hiérarchie dans un tableau ou un `<select>`.
 */
export function aplatirArborescence(categories) {
  const resultat = [];
  const parcourir = (noeuds, profondeur) => {
    for (const noeud of noeuds) {
      const { enfants, ...reste } = noeud;
      resultat.push({ ...reste, profondeur });
      parcourir(enfants, profondeur + 1);
    }
  };
  parcourir(construireArbre(categories), 0);
  return resultat;
}

/**
 * Identifiants interdits comme parent d'une catégorie : elle-même et toute sa
 * descendance, sans quoi on créerait une boucle dans l'arborescence.
 */
export function idsInterdits(categories, categorieId) {
  if (!categorieId) return new Set();
  const interdits = new Set([categorieId]);
  let ajout = true;
  while (ajout) {
    ajout = false;
    for (const c of categories) {
      if (c.parent_id != null && interdits.has(c.parent_id) && !interdits.has(c.id)) {
        interdits.add(c.id);
        ajout = true;
      }
    }
  }
  return interdits;
}
