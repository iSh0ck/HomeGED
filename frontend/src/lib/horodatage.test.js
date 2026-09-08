import { afterEach, describe, expect, it } from "vitest";

import {
  cleDuJour, definirFuseau, formaterHeure, formaterHorodatage, formaterJour, ilYA, instant,
} from "./horodatage";

/**
 * Lecture des horodatages (§18.19).
 *
 * Le défaut signalé : les heures affichées étaient celles de Greenwich. Tout
 * est enregistré en temps universel, et les chaînes rendues par l'API ne le
 * disent pas — `new Date()` les prenait donc pour des heures locales, et tout se
 * décalait de deux heures l'été.
 */
describe("horodatage", () => {
  afterEach(() => definirFuseau("Europe/Paris"));

  it("comprend une chaîne sans fuseau comme du temps universel", () => {
    expect(instant("2026-09-04T19:45:12").toISOString()).toBe("2026-09-04T19:45:12.000Z");
    expect(instant("2026-09-04 19:45:12").toISOString()).toBe("2026-09-04T19:45:12.000Z");
    // et respecte celle qui porte déjà son fuseau
    expect(instant("2026-09-04T19:45:12Z").toISOString()).toBe("2026-09-04T19:45:12.000Z");
  });

  it("affiche l'heure de Paris, pas celle de Greenwich", () => {
    definirFuseau("Europe/Paris");
    expect(formaterHeure("2026-09-04T19:45:00")).toBe("21h45");   // été : UTC+2
    expect(formaterHeure("2026-01-15T19:45:00")).toBe("20h45");   // hiver : UTC+1
  });

  it("suit le fuseau réglé par le foyer", () => {
    definirFuseau("America/Montreal");
    expect(formaterHeure("2026-09-04T19:45:00")).toBe("15h45");
    definirFuseau("UTC");
    expect(formaterHeure("2026-09-04T19:45:00")).toBe("19h45");
  });

  it("range sous la bonne journée ce qui se passe tard le soir", () => {
    // 23 h 30 à Paris, c'est 21 h 30 UTC le même jour ; mais 22 h 30 UTC un
    // 4 septembre, c'est déjà le 5 à Paris. Découper la chaîne à la main, comme
    // le faisait le journal, rangeait ces événements sous la veille.
    definirFuseau("Europe/Paris");
    expect(cleDuJour("2026-09-04T22:30:00")).toBe("2026-09-05");
    expect(formaterJour("2026-09-04T22:30:00")).toBe("05/09/2026");
  });

  it("compose la date et l'heure", () => {
    definirFuseau("Europe/Paris");
    expect(formaterHorodatage("2026-09-04T19:45:00")).toBe("04/09/2026 à 21h45");
  });

  it("mesure une durée écoulée depuis le bon instant", () => {
    const ilYAUneHeure = new Date(Date.now() - 3600 * 1000)
      .toISOString().replace("Z", "").slice(0, 19);
    expect(ilYA(ilYAUneHeure)).toBe("il y a 1 h");
    expect(ilYA(new Date().toISOString())).toBe("à l'instant");
  });

  it("ne rend rien plutôt que « Invalid Date » sur une valeur absente", () => {
    expect(formaterHorodatage(null)).toBe("");
    expect(formaterJour(undefined)).toBe("");
    expect(instant("n'importe quoi")).toBeNull();
  });
});
