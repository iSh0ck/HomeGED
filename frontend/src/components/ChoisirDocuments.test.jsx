import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../api", () => ({
  api: {
    attachables: vi.fn(() => Promise.resolve({
      recents: true, jours_recents: 30, minimum_recherche: 3,
      documents: [
        { id: 51, libelle: "Factures · 2026-03-23", categorie: "Factures",
          nom_fichier: "facture_mars.pdf",
          details: [{ libelle: "N° facture", valeur: "F-2026-777" },
                    { libelle: "Émetteur", valeur: "Orange" }] },
        { id: 52, libelle: "Factures · 2026-04-21", categorie: "Factures",
          nom_fichier: "facture_avril.pdf", details: [] },
      ],
    })),
    fichierBlobUrl: vi.fn(() => Promise.resolve("blob:document")),
    documentTexte: vi.fn(() => Promise.resolve({ texte: "" })),
  },
}));

import { api } from "../api";
import ChoisirDocuments from "./ChoisirDocuments.jsx";

beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:document");
  URL.revokeObjectURL = vi.fn();
});

describe("choisir des documents pour un champ", () => {
  it("montre ce que l'administration a coché, sous chaque proposition", async () => {
    render(<ChoisirDocuments categorieId={22} champ="meta:factures_liees"
                             onChange={() => {}} />);

    await userEvent.click(screen.getByLabelText(/Chercher un document/i));
    // c'est ce qui distingue deux factures du même mois (§22.19)
    expect(await screen.findByText(/N° facture : F-2026-777 · Émetteur : Orange/))
      .toBeDefined();
  });

  it("la recherche est bornée par la déclaration, pas par la GED entière", async () => {
    render(<ChoisirDocuments categorieId={22} champ="meta:factures_liees" sauf={7}
                             onChange={() => {}} />);

    await waitFor(() => expect(api.attachables).toHaveBeenCalledWith(
      22, "meta:factures_liees", "", 7));
  });

  it("laisse regarder un document avant de le choisir", async () => {
    render(<ChoisirDocuments categorieId={22} champ="meta:factures_liees"
                             onChange={() => {}} />);

    await userEvent.click(screen.getByLabelText(/Chercher un document/i));
    await userEvent.click(await screen.findByLabelText("Voir Factures · 2026-03-23"));

    // la page s'ouvre par-dessus : un numéro ne dit pas toujours si c'est la bonne
    expect(await screen.findByText("Aperçu")).toBeDefined();
    await waitFor(() => expect(api.fichierBlobUrl).toHaveBeenCalledWith(51));
  });

  it("montre le dernier mois sans rien taper, et le dit", async () => {
    render(<ChoisirDocuments categorieId={22} champ="meta:factures_liees"
                             onChange={() => {}} />);

    await userEvent.click(screen.getByLabelText(/Chercher un document/i));
    // un extrait récent n'est pas un résultat de recherche : le confondre ferait
    // croire qu'un document cherché n'existe pas (§22.26)
    expect(await screen.findByText(/Documents ajoutés depuis un mois/)).toBeDefined();
  });

  it("n'interroge pas le serveur pour une ou deux lettres", async () => {
    render(<ChoisirDocuments categorieId={22} champ="meta:factures_liees"
                             onChange={() => {}} />);

    const champRecherche = screen.getByLabelText(/Chercher un document/i);
    await userEvent.click(champRecherche);
    await waitFor(() => expect(api.attachables).toHaveBeenCalledTimes(1));

    await userEvent.type(champRecherche, "fa");
    expect(await screen.findByText(/Encore 1 caractère/)).toBeDefined();
    // toujours un seul appel : « fa » ramènerait la moitié de la GED pour rien
    expect(api.attachables).toHaveBeenCalledTimes(1);
  });

  it("choisir ferme la liste et retient le document", async () => {
    const change = vi.fn();
    render(<ChoisirDocuments categorieId={22} champ="meta:factures_liees"
                             onChange={change} />);

    await userEvent.click(screen.getByLabelText(/Chercher un document/i));
    await userEvent.click(await screen.findByText(/Factures · 2026-04-21/));

    expect(change).toHaveBeenCalledWith([expect.objectContaining({ id: 52 })]);
  });
});
