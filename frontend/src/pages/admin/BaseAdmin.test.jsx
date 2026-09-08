import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../api", () => ({
  adminApi: {
    tablesBase: vi.fn(() => Promise.resolve([
      { nom: "usr_membres", libelle: "Membres du foyer", modifiable: true, nb_lignes: 3 },
      { nom: "usr_emetteurs", libelle: "Émetteurs", modifiable: true, nb_lignes: 7 },
      { nom: "sys_utilisateurs", libelle: "Comptes", modifiable: false, nb_lignes: 2 },
    ])),
    typesColonnes: vi.fn(() => Promise.resolve(["texte", "entier"])),
    colonnesBase: vi.fn(() => Promise.resolve([])),
    lignesBase: vi.fn(() => Promise.resolve({ lignes: [], colonnes: ["id", "nom"], total: 0 })),
  },
}));

import BaseAdmin from "./BaseAdmin";

/** Le fond « accent » marque la table ouverte : c'est le seul repère visuel. */
function estSelectionnee(bouton) {
  return bouton.style.background.includes("accent-soft");
}

describe("l'écran des tables de données", () => {
  it("n'en sélectionne aucune tant qu'on n'a rien choisi", async () => {
    render(<BaseAdmin />);
    const membres = await screen.findByRole("button", { name: /Membres du foyer/ });
    const emetteurs = screen.getByRole("button", { name: /Émetteurs/ });
    const comptes = screen.getByRole("button", { name: /Comptes/ });
    expect([membres, emetteurs, comptes].filter(estSelectionnee)).toHaveLength(0);
  });

  it("n'en sélectionne qu'une à la fois, celle sur laquelle on a cliqué", async () => {
    render(<BaseAdmin />);
    const membres = await screen.findByRole("button", { name: /Membres du foyer/ });
    await userEvent.click(membres);
    await waitFor(() => expect(estSelectionnee(membres)).toBe(true));
    expect(estSelectionnee(screen.getByRole("button", { name: /Émetteurs/ }))).toBe(false);
    expect(estSelectionnee(screen.getByRole("button", { name: /^Comptes/ }))).toBe(false);
  });
});
