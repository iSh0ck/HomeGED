import { describe, it, expect } from "vitest";
import { avecDrapeaux, drapeauxDe, motifSansDrapeaux } from "./regex";

describe("les drapeaux d'une expression régulière", () => {
  it("se lisent en tête du motif", () => {
    expect(drapeauxDe("(?i)facture\\s*n°")).toBe("(?i)");
    expect(drapeauxDe("(?im)^\\s*n° de facture")).toBe("(?im)");
    expect(drapeauxDe("\\b([0-3]\\d)")).toBe("");
  });

  it("se rangent toujours dans le même ordre", () => {
    // `(?mi)` et `(?im)` font la même chose : deux libellés pour un seul état
    // rendraient la liste incompréhensible.
    expect(drapeauxDe("(?mi)x")).toBe("(?im)");
  });

  it("se remplacent, ils ne s'ajoutent pas", () => {
    // deux groupes à la suite ne sont pas une double précaution, c'est une
    // erreur de syntaxe
    expect(avecDrapeaux("(?i)facture", "(?im)")).toBe("(?im)facture");
    expect(avecDrapeaux("(?im)facture", "")).toBe("facture");
    expect(avecDrapeaux("facture", "(?i)")).toBe("(?i)facture");
  });

  it("laissent le motif lisible quand on veut le montrer nu", () => {
    expect(motifSansDrapeaux("(?im)^ligne$")).toBe("^ligne$");
    expect(motifSansDrapeaux("^ligne$")).toBe("^ligne$");
  });
});
