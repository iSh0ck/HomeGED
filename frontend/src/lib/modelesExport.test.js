import { describe, expect, it, beforeEach } from "vitest";

import {
  ajouterModele, lireModeles, modeleConnu, retirerModele,
} from "./modelesExport";

/**
 * Les modèles d'arborescence qu'on garde sous la main (§22.83).
 *
 * Sans nom : un modèle **est** sa valeur. Lui demander un intitulé obligerait à
 * inventer « export compta v2 » pour se rappeler de quoi il s'agit, alors que
 * les deux lignes le disent mieux — et l'exemple gardé avec lui achève de le
 * reconnaître.
 */
describe("modèles d'export gardés", () => {
  beforeEach(() => window.localStorage.removeItem("homeged.modelesExport"));

  const compta = { dossier: "{annee}/{type}", nom: "{champ:emetteur}",
                   exemple: "2026/Factures/EDF.pdf" };

  it("garde un modèle avec sa valeur et son exemple, et rien d'autre", () => {
    ajouterModele(compta);
    expect(lireModeles()).toEqual([compta]);
  });

  it("met le plus récent en tête, sans garder deux fois le même", () => {
    ajouterModele(compta);
    ajouterModele({ dossier: "{type}", nom: "{nom_fichier}", exemple: "Factures/a.pdf" });
    // Le même que le premier, avec l'exemple du jour : il remonte, il ne double pas.
    ajouterModele({ ...compta, exemple: "2026/Factures/Orange.pdf" });

    const gardes = lireModeles();
    expect(gardes).toHaveLength(2);
    expect(gardes[0].exemple).toBe("2026/Factures/Orange.pdf");
    expect(gardes[1].dossier).toBe("{type}");
  });

  it("sait dire ce qui est déjà gardé, pour ne pas le proposer deux fois", () => {
    ajouterModele(compta);
    const gardes = lireModeles();
    expect(modeleConnu(gardes, compta.dossier, compta.nom)).toBe(true);
    expect(modeleConnu(gardes, "{annee}", compta.nom)).toBe(false);
  });

  it("s'oublie", () => {
    ajouterModele(compta);
    expect(retirerModele(compta)).toEqual([]);
    expect(lireModeles()).toEqual([]);
  });

  it("ne casse pas sur un stockage abîmé", () => {
    // On relit ce qu'on a écrit, mais on ne fait pas confiance à ce qu'on relit.
    window.localStorage.setItem("homeged.modelesExport", "{pas du json");
    expect(lireModeles()).toEqual([]);
    window.localStorage.setItem("homeged.modelesExport", '[{"dossier":1},{"nom":"x"}]');
    expect(lireModeles()).toEqual([]);
  });
});

