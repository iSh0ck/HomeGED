import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Sidebar from "./Sidebar.jsx";

// Deux racines : l'une regroupe des sous-catégories, l'autre non.
const CATEGORIES = [
  { id: 1, nom: "Maison", parent_id: null, ordre: 10 },
  { id: 2, nom: "Assurance", parent_id: 1, ordre: 10 },
  { id: 3, nom: "Énergie", parent_id: 1, ordre: 20 },
  { id: 4, nom: "Impôts", parent_id: null, ordre: 20 },
];

function rendre(proprietes = {}) {
  const surFiltre = vi.fn();
  render(
    <Sidebar
      categories={CATEGORIES}
      vues={[]}
      tableaux={[]}
      onFiltreCategorie={surFiltre}
      {...proprietes}
    />,
  );
  return surFiltre;
}

describe("navigation par catégories", () => {
  it("ne filtre pas sur une racine qui regroupe des sous-catégories", async () => {
    const utilisateur = userEvent.setup();
    const surFiltre = rendre();

    await utilisateur.click(screen.getByRole("button", { name: "Maison" }));

    expect(surFiltre).not.toHaveBeenCalled();
    // …mais elle s'est dépliée : ses enfants sont désormais atteignables.
    expect(screen.getByRole("button", { name: "Assurance" })).toBeDefined();
  });

  it("laisse filtrer une racine sans sous-catégorie", async () => {
    const utilisateur = userEvent.setup();
    const surFiltre = rendre();

    await utilisateur.click(screen.getByRole("button", { name: "Impôts" }));

    expect(surFiltre).toHaveBeenCalledWith(4);
  });

  it("ne désélectionne pas la catégorie déjà affichée", async () => {
    const utilisateur = userEvent.setup();
    const surFiltre = rendre({ filtreCategorie: 4 });

    await utilisateur.click(screen.getByRole("button", { name: "Impôts" }));

    // Auparavant, ce second clic renvoyait vers tous les documents du foyer,
    // sans que personne ne l'ait demandé.
    expect(surFiltre).not.toHaveBeenCalled();
  });

  it("filtre bien sur une sous-catégorie", async () => {
    const utilisateur = userEvent.setup();
    const surFiltre = rendre();

    await utilisateur.click(screen.getByRole("button", { name: "Maison" }));
    await utilisateur.click(screen.getByRole("button", { name: "Énergie" }));

    expect(surFiltre).toHaveBeenCalledWith(3);
  });
});
