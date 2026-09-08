import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SaisieSuggeree from "./SaisieSuggeree.jsx";

const CIBLES = [
  { valeur: "montant_ttc", aide: "champ attendu" },
  { valeur: "numero_facture", aide: "déjà ciblé par une règle" },
];

describe("un champ libre avec des suggestions", () => {
  it("propose ce qui est déjà nommé, avec sa provenance", async () => {
    render(<SaisieSuggeree ariaLabel="Colonne cible" valeur="" suggestions={CIBLES}
                           onChange={() => {}} />);

    await userEvent.click(screen.getByLabelText("Colonne cible"));
    expect(await screen.findByText("montant_ttc")).toBeDefined();
    expect(screen.getByText("déjà ciblé par une règle")).toBeDefined();
  });

  it("filtre à la frappe", async () => {
    const change = vi.fn();
    const { rerender } = render(
      <SaisieSuggeree ariaLabel="Colonne cible" valeur="" suggestions={CIBLES}
                      onChange={change} />);

    await userEvent.type(screen.getByLabelText("Colonne cible"), "num");
    rerender(<SaisieSuggeree ariaLabel="Colonne cible" valeur="num" suggestions={CIBLES}
                             onChange={change} />);
    expect(await screen.findByText("numero_facture")).toBeDefined();
    expect(screen.queryByText("montant_ttc")).toBeNull();
  });

  it("n'enferme pas : un nom nouveau s'écrit toujours", async () => {
    const change = vi.fn();
    render(<SaisieSuggeree ariaLabel="Colonne cible" valeur="" suggestions={CIBLES}
                           onChange={change} />);

    await userEvent.type(screen.getByLabelText("Colonne cible"), "k");
    expect(change).toHaveBeenCalledWith("k");
  });

  it("choisir une suggestion la reprend telle quelle", async () => {
    const change = vi.fn();
    render(<SaisieSuggeree ariaLabel="Colonne cible" valeur="" suggestions={CIBLES}
                           onChange={change} />);

    await userEvent.click(screen.getByLabelText("Colonne cible"));
    await userEvent.click(await screen.findByText("montant_ttc"));
    expect(change).toHaveBeenCalledWith("montant_ttc");
  });
});
