import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Liste from "./Liste.jsx";

const OPTIONS = [
  { valeur: "a", libelle: "Factures" },
  { valeur: "b", libelle: "Impôts" },
  { valeur: "c", libelle: "Courriers" },
];

describe("liste déroulante", () => {
  it("montre la valeur choisie plutôt que sa clé", () => {
    render(<Liste valeur="b" options={OPTIONS} onChange={() => {}} />);
    expect(screen.getByRole("button").textContent).toContain("Impôts");
  });

  it("se navigue au clavier, comme le ferait une liste native", async () => {
    const utilisateur = userEvent.setup();
    const surChangement = vi.fn();
    render(<Liste valeur="a" options={OPTIONS} onChange={surChangement} />);

    const bouton = screen.getByRole("button");
    bouton.focus();
    await utilisateur.keyboard("{ArrowDown}");   // ouvre
    await utilisateur.keyboard("{ArrowDown}");   // descend d'une entrée
    await utilisateur.keyboard("{Enter}");

    expect(surChangement).toHaveBeenCalledWith("b");
  });

  it("se referme sur Échap sans rien changer", async () => {
    const utilisateur = userEvent.setup();
    const surChangement = vi.fn();
    render(<Liste valeur="a" options={OPTIONS} onChange={surChangement} />);

    screen.getByRole("button").focus();
    await utilisateur.keyboard("{ArrowDown}");
    expect(screen.getByRole("listbox")).toBeDefined();

    await utilisateur.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(surChangement).not.toHaveBeenCalled();
  });

  it("propose un filtre au-delà de douze entrées", async () => {
    const utilisateur = userEvent.setup();
    const nombreuses = Array.from({ length: 20 }, (_, i) => ({
      valeur: String(i), libelle: `Catégorie ${i}`,
    }));
    render(<Liste valeur="0" options={nombreuses} onChange={() => {}} />);

    await utilisateur.click(screen.getByRole("button", { name: /Catégorie 0/ }));
    const filtre = screen.getByLabelText("Filtrer la liste");
    await utilisateur.type(filtre, "17");

    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option").textContent).toContain("Catégorie 17");
  });
});
