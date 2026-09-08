import { describe, it, expect } from "vitest";
import { cheminDeLaVue, vueDuChemin } from "./navigation";

/**
 * Les chemins servent à deux choses qui n'ont rien à voir : ouvrir deux onglets,
 * et donner à un proxy en amont quelque chose à filtrer. La seconde est la plus
 * exigeante — un chemin qui changerait de forme rendrait muette une règle de
 * filtrage écrite ailleurs.
 */
describe("chemins de l'application", () => {
  it("l'administration a son propre chemin, filtrable en amont", () => {
    expect(cheminDeLaVue("admin")).toBe("/admin");
    expect(vueDuChemin("/admin")).toBe("admin");
  });

  it("l'accueil est la racine", () => {
    expect(cheminDeLaVue("accueil")).toBe("/");
    expect(vueDuChemin("/")).toBe("accueil");
  });

  it("une barre oblique finale ne change rien", () => {
    expect(vueDuChemin("/analyse/")).toBe("analyse");
  });

  it("le registre n'a pas d'adresse propre : il se rejoint depuis l'accueil", () => {
    // Une adresse de plus n'apporterait qu'une entrée d'historique ; les chemins
    // servent à ouvrir un second onglet et à filtrer en amont, pas à nommer
    // chaque écran.
    expect(cheminDeLaVue("registre")).toBe("/");
    expect(vueDuChemin("/registre")).toBe("accueil");
  });

  it("un chemin inconnu ramène à l'accueil plutôt qu'à un écran vide", () => {
    // il peut venir d'un marque-page d'une version antérieure
    expect(vueDuChemin("/ancienne-page")).toBe("accueil");
    expect(vueDuChemin("")).toBe("accueil");
  });

  it("chaque écran a un chemin, et un seul", () => {
    const ecrans = ["accueil", "admin", "analyse"];
    const chemins = ecrans.map(cheminDeLaVue);
    expect(new Set(chemins).size).toBe(ecrans.length);
    for (const ecran of ecrans) expect(vueDuChemin(cheminDeLaVue(ecran))).toBe(ecran);
  });
});
