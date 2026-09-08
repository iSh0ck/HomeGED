import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("../api", () => ({
  api: { texteOcr: vi.fn() },
}));

import { api } from "../api";
import GrilleOcr from "./GrilleOcr.jsx";

/**
 * Texte océrisé en grille (§18.37).
 *
 * C'est la matière première des règles d'extraction : tant qu'on ne l'a pas sous
 * les yeux, écrire une expression revient à deviner ce que la machine a lu.
 */
describe("grille du texte reconnu", () => {
  beforeEach(() => vi.clearAllMocks());

  const TEXTE = {
    document_id: 7,
    longueur: 60,
    vide: false,
    lignes: [
      { numero: 1, debut: 0, texte: "n° de facture : 05C060T853" },
      { numero: 2, debut: 27, texte: "" },
      { numero: 3, debut: 28, texte: "TOTAL TTC : 116,52 EUR" },
    ],
  };

  it("place chaque caractère dans sa propre case", async () => {
    // C'est tout l'objet de la matrice : savoir qu'un numéro commence colonne 16
    // et non « quelque part après le deux-points ».
    api.texteOcr.mockResolvedValue(TEXTE);
    const { container } = render(<GrilleOcr documentId={7} />);
    await screen.findByText("60 caractères · 3 lignes");

    const premiereLigne = container.querySelectorAll("tbody tr")[0];
    const cases = [...premiereLigne.querySelectorAll("td")];
    expect(cases[0].textContent).toBe("n");
    expect(cases[1].textContent).toBe("°");
    // un espace se voit — l'OCR en sème, et ce sont eux qui font échouer un motif
    expect(cases[2].textContent).toBe("·");
  });

  it("donne la position d'un caractère dans le texte entier", async () => {
    // C'est ce dont une expression parle : un décalage, pas une impression.
    api.texteOcr.mockResolvedValue(TEXTE);
    render(<GrilleOcr documentId={7} />);
    await screen.findByText("60 caractères · 3 lignes");

    expect(screen.getByTitle("L3 C0 · position 28")).toBeDefined();
    expect(screen.getByTitle("Position 28 dans le texte entier").textContent.trim()).toBe("3");
  });

  it("surligne ce qu'on cherche, case par case", async () => {
    api.texteOcr.mockResolvedValue(TEXTE);
    const { container } = render(<GrilleOcr documentId={7} />);
    await screen.findByText("60 caractères · 3 lignes");

    fireEvent.change(screen.getByPlaceholderText("surligner…"), { target: { value: "ttc" } });
    const surlignes = [...container.querySelectorAll("td")]
      .filter((c) => c.style.background.includes("amber"));
    expect(surlignes.map((c) => c.textContent).join("")).toBe("TTC");
  });

  it("dit clairement qu'un document n'a produit aucun texte", async () => {
    // Un scan trop pâle donne ce résultat, et aucune règle n'y lira jamais rien :
    // mieux vaut le dire que de laisser chercher une expression fautive.
    api.texteOcr.mockResolvedValue({ document_id: 7, longueur: 0, vide: true, lignes: [] });
    render(<GrilleOcr documentId={7} />);
    expect(await screen.findByText(/aucun texte/)).toBeDefined();
  });
});
