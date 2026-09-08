/**
 * Référence d'une tâche du serveur de travaux (§18.55).
 *
 * Le numéro existe en base depuis toujours ; ce qui manquait, c'est une forme
 * unique sous laquelle le dire. Écrite ici et nulle part ailleurs : deux écrans
 * la composaient chacun de son côté, et ils ont aussitôt divergé — `T-0014` au
 * serveur de travaux, « travail nº14 » au Centre d'analyse, pour la même tâche.
 *
 * Six chiffres : c'est un numéro qu'on recopie dans un message ou qu'on cherche
 * des yeux dans une liste, et sa longueur ne doit pas changer en cours de route.
 * Un compteur qui passe de 9 999 à 10 000 décalerait toute une colonne.
 */
export function referenceTache(id) {
  if (id === null || id === undefined || id === "") return "";
  return `T-${String(id).padStart(6, "0")}`;
}


/**
 * Référence d'une règle d'extraction (§22.20).
 *
 * Même besoin que pour une tâche, et donc même forme : un numéro qu'on se cite
 * — « la R-0042 ne trouve plus rien » — sans avoir à décrire la règle. Quatre
 * chiffres suffisent : un foyer en écrit quelques dizaines, pas des milliers, et
 * une référence courte se retient.
 */
export function referenceRegle(id) {
  if (id === null || id === undefined || id === "") return "";
  return `R-${String(id).padStart(4, "0")}`;
}
