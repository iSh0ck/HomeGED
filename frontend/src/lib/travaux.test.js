import { describe, it, expect } from "vitest";
import { referenceRegle, referenceTache } from "./travaux";

/**
 * La référence d'une tâche se recopie dans un message et se cherche des yeux
 * dans une liste : sa forme ne doit ni varier d'un écran à l'autre, ni changer
 * de longueur en cours de route.
 */
describe("référence d'une tâche", () => {
  it("garde six chiffres, quel que soit le numéro", () => {
    expect(referenceTache(14)).toBe("T-000014");
    expect(referenceTache(1)).toBe("T-000001");
    // le passage de 9 999 à 10 000 ne doit pas décaler une colonne entière
    expect(referenceTache(9999)).toHaveLength(referenceTache(10000).length);
  });

  it("ne déborde pas au-delà de six chiffres", () => {
    expect(referenceTache(1234567)).toBe("T-1234567");
  });

  it("rend une chaîne vide quand il n'y a pas de tâche", () => {
    // une fiche peut n'être rattachée à aucune : afficher « T-000000 » mentirait
    expect(referenceTache(null)).toBe("");
    expect(referenceTache(undefined)).toBe("");
  });
});

describe("référence d'une règle d'extraction", () => {
  it("tient sur quatre chiffres : elle se cite, elle ne se décrit pas", () => {
    expect(referenceRegle(42)).toBe("R-0042");
    expect(referenceRegle(7)).toBe("R-0007");
  });

  it("ne rend rien pour une règle qui n'existe pas encore", () => {
    expect(referenceRegle(null)).toBe("");
    expect(referenceRegle(undefined)).toBe("");
  });
});
