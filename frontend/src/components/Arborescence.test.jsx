import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Arborescence, { FilRepli } from "./Arborescence.jsx";

const BRANCHES = [
  { valeur: "2026", libelle: "2026", nombre: 48,
    critere: { champ: "date_document", operateur: "entre",
               valeur: ["2026-01-01", "2026-12-31"] } },
  { valeur: "2025", libelle: "2025", nombre: 1,
    critere: { champ: "date_document", operateur: "entre",
               valeur: ["2025-01-01", "2025-12-31"] } },
];

describe("registre replié en arborescence", () => {
  it("annonce chaque branche et ce qu'elle contient", () => {
    render(<Arborescence champ="date_document" libelle="Date du document"
                         branches={BRANCHES} />);

    expect(screen.getByText("2026")).toBeDefined();
    expect(screen.getByText("48 documents")).toBeDefined();
    // un seul document ne prend pas de « s »
    expect(screen.getByText("1 document")).toBeDefined();
  });

  it("descendre rend le critère de la branche, pas seulement son nom", async () => {
    const descendre = vi.fn();
    render(<Arborescence champ="date_document" branches={BRANCHES}
                         onDescendre={descendre} />);

    await userEvent.click(screen.getByTitle(/documents de « 2026 »/));
    expect(descendre).toHaveBeenCalledWith(expect.objectContaining({
      critere: expect.objectContaining({ operateur: "entre" }),
    }));
  });

  it("dit quand il n'y a rien à replier, plutôt que d'afficher le vide", () => {
    render(<Arborescence champ="meta:titulaire" branches={[]} />);
    expect(screen.getByText(/Aucun document ne porte de valeur/)).toBeDefined();
  });

  it("le fil montre le chemin et permet d'en sortir", async () => {
    const remonter = vi.fn();
    render(<FilRepli chemin={[{ champ: "date_document", valeur: "2026", libelle: "2026" }]}
                     onRemonter={remonter} />);

    await userEvent.click(screen.getByText("Tout"));
    expect(remonter).toHaveBeenCalledWith(-1);
  });
});
