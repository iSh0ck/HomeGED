import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { definirLangue } from "../lib/langue";

// jsdom n'implémente ni le défilement ni l'observation d'intersection : sans
// ces bouchons, tout composant qui fait défiler une liste échoue pour une
// raison qui n'a rien à voir avec ce qu'on teste.
Element.prototype.scrollIntoView = vi.fn();

// La langue par défaut suit le navigateur (§22.51), et celui de jsdom annonce
// l'anglais : les tests liraient donc une interface traduite, alors qu'ils
// vérifient les textes du code. On la fixe au français — c'est aussi ce qui
// signale une régression le jour où un texte ne serait plus le bon.
beforeEach(() => definirLangue("fr"));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
