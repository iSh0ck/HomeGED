import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../api", () => ({
  adminApi: {
    tableaux: vi.fn(() => Promise.resolve([
      { id: 3, nom: "Suivi des dépenses", description: "Ce que le foyer paie",
        partage: true, ordre: 10,
        widgets: [{ id: "w1", type: "nombre", titre: "Documents de l'année" }] },
    ])),
    modifierTableau: vi.fn(() => Promise.resolve({})),
    creerTableau: vi.fn(() => Promise.resolve({})),
    supprimerTableau: vi.fn(() => Promise.resolve({})),
  },
  api: {
    categories: vi.fn(() => Promise.resolve([])),
    // La **forme réelle** de la réponse, et non un bouchon commode : c'est
    // exactement ce qui manquait la première fois — l'écran tombait sur un
    // `map` d'indéfini pendant que le test croyait avoir bouchonné.
    optionsIndicateurs: vi.fn(() => Promise.resolve({
      types: [{ type: "nombre", libelle: "Nombre de documents" }],
      periodes: [{ type: "tout", libelle: "Depuis toujours" }],
      groupements: [{ champ: "categorie", libelle: "Type de document" }],
      champs: [{ champ: "texte", libelle: "Texte du document", type: "texte_integral",
                 operateurs: ["contient"] }],
      dates: [{ champ: "date_document", libelle: "Date du document" }],
    })),
  },
}));

import TableauxAdmin from "./TableauxAdmin.jsx";

/**
 * Modifier un tableau de bord (§22.85).
 *
 * L'écran tombait sur « Cannot read properties of undefined (reading 'length') »
 * dès qu'on ouvrait un tableau : le paramètre du rappel avait été renommé au
 * §22.54 et le corps répandait toujours `t`, la fonction de traduction. L'état
 * d'édition se retrouvait vide, et ses indicateurs indéfinis.
 */
describe("l'écran des tableaux de bord", () => {
  it("ouvre un tableau avec ses indicateurs", async () => {
    const utilisateur = userEvent.setup();
    render(<TableauxAdmin />);

    // La ligne s'ouvre par son bouton, pas par son texte.
    await screen.findByText("Suivi des dépenses");
    await utilisateur.click(screen.getAllByLabelText("Modifier")[0]);

    // Le nom rempli, et le décompte d'indicateurs : les deux venaient de l'objet
    // répandu, et les deux manquaient.
    expect(await screen.findByDisplayValue("Suivi des dépenses")).toBeDefined();
    expect(screen.getByText(/Indicateurs \(1\)/)).toBeDefined();
  });
});
