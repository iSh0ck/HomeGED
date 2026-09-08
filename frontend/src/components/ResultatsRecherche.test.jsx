import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ResultatsRecherche from "./ResultatsRecherche.jsx";

const RESULTATS = [
  {
    document: { id: 1, nom_fichier: "a.pdf", categorie: "Factures", fournisseur: "Orange",
                date_document: "2026-07-21", date_import: "2026-07-01T10:00:00",
                statut: "traite", metadonnees: {}, libelles_references: {} },
    score: 10,
    raisons: [{ source: "fournisseur", libelle: "Émetteur", extrait: "Orange" }],
  },
  {
    document: { id: 2, nom_fichier: "b.pdf", categorie: "Cartes grises", fournisseur: null,
                date_document: null, date_import: "2026-07-02T10:00:00",
                statut: "traite", metadonnees: {}, libelles_references: {} },
    score: 6,
    raisons: [{ source: "chose", libelle: "Concerne", extrait: "Renault Clio" }],
  },
];

describe("résultats de recherche", () => {
  it("groupe par classement : on reconnaît d'abord la sorte de papier", () => {
    render(<ResultatsRecherche resultats={RESULTATS} terme="clio" />);

    expect(screen.getByText(/Factures · 1/)).toBeDefined();
    expect(screen.getByText(/Cartes grises · 1/)).toBeDefined();
  });

  it("dit pourquoi chaque document sort", () => {
    // sans cela, une pièce sans rapport apparent ressemble à une erreur du moteur
    render(<ResultatsRecherche resultats={RESULTATS} terme="clio" />);

    expect(screen.getByText(/Concerne/)).toBeDefined();
    expect(screen.getByText(/Renault Clio/)).toBeDefined();
  });

  it("un clic ouvre le document", async () => {
    const choisir = vi.fn();
    render(<ResultatsRecherche resultats={RESULTATS} terme="clio" onSelect={choisir} />);

    // un document se désigne par ce qu'on en a extrait, pas par son nom de
    // fichier — c'est déjà le cas partout ailleurs dans l'interface
    await userEvent.click(screen.getByText("Cartes grises", { selector: "div" }));
    expect(choisir).toHaveBeenCalledWith(2);
  });

  it("propose d'élargir quand le périmètre a pu tout écarter", () => {
    render(<ResultatsRecherche resultats={[]} terme="clio" perimetre="classement" />);
    expect(screen.getByText(/Toute la GED/)).toBeDefined();
  });
});
