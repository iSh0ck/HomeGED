/**
 * Les modèles d'arborescence qu'on garde sous la main (§22.83).
 *
 * On règle « {annee}/{type} » et « {champ:emetteur} - {nom_fichier} » pour le
 * comptable, puis tout autre chose pour l'assurance, et l'on retape le premier
 * le mois suivant. Un modèle se garde donc, et se reprend d'un clic.
 *
 * **Sans nom.** Un modèle *est* sa valeur : lui demander un intitulé
 * obligerait à inventer « export compta v2 » pour se rappeler de quoi il
 * s'agit, alors que les deux lignes le disent mieux. L'exemple enregistré avec
 * lui — le chemin qu'un vrai document avait au moment où on l'a gardé — achève
 * de le reconnaître d'un coup d'œil.
 *
 * Rangés dans `localStorage`, comme les largeurs de colonnes (§22.34) : c'est
 * un confort de poste, il ne regarde pas les autres comptes du foyer.
 */
const CLE = "homeged.modelesExport";
const MAX = 12;   // au-delà, ce n'est plus une liste qu'on parcourt

export function lireModeles() {
  try {
    const brut = JSON.parse(window.localStorage.getItem(CLE) || "[]");
    if (!Array.isArray(brut)) return [];
    // On relit ce qu'on a écrit, mais on ne fait pas confiance à ce qu'on relit :
    // un stockage bricolé à la main ne doit pas casser la fenêtre d'export.
    return brut
      .filter((m) => m && typeof m.dossier === "string" && typeof m.nom === "string")
      .slice(0, MAX)
      .map((m) => ({
        dossier: m.dossier, nom: m.nom,
        exemple: typeof m.exemple === "string" ? m.exemple : "",
      }));
  } catch {
    return [];   // navigation privée, stockage refusé, JSON abîmé
  }
}

/**
 * Ajoute un modèle, le plus récent en tête. Un modèle déjà gardé n'est pas
 * gardé deux fois : il remonte, avec l'exemple du jour.
 */
export function ajouterModele(modele) {
  const propre = {
    dossier: String(modele.dossier ?? ""),
    nom: String(modele.nom ?? ""),
    exemple: String(modele.exemple ?? ""),
  };
  const suite = [propre, ...lireModeles().filter(
    (m) => !(m.dossier === propre.dossier && m.nom === propre.nom))].slice(0, MAX);
  ecrire(suite);
  return suite;
}

export function retirerModele(modele) {
  const suite = lireModeles().filter(
    (m) => !(m.dossier === modele.dossier && m.nom === modele.nom));
  ecrire(suite);
  return suite;
}

/** Ce modèle est-il déjà gardé ? De quoi ne pas proposer de le garder deux fois. */
export function modeleConnu(modeles, dossier, nom) {
  return (modeles || []).some((m) => m.dossier === dossier && m.nom === nom);
}

function ecrire(modeles) {
  try {
    window.localStorage.setItem(CLE, JSON.stringify(modeles));
  } catch {
    /* le confort ne se garde pas : il se réglera de nouveau, et c'est tout */
  }
}
