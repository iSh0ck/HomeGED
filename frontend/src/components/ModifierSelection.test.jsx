import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api", () => ({
  api: {
    document: vi.fn((id) => Promise.resolve({
      id, nom_fichier: `f${id}.pdf`, fournisseur: "Orange", categorie: "Factures",
      categorie_id: 2, date_document: "2026-07-21", statut: "traite",
      metadonnees: {}, champs_attendus: [], libelles_references: {},
    })),
    prendreVerrou: vi.fn(() => Promise.resolve({ jusqu_a: "2026-09-04T18:00:00" })),
    rendreVerrou: vi.fn(() => Promise.resolve({})),
    patchDocument: vi.fn(() => Promise.resolve({})),
    references: vi.fn(() => Promise.resolve([])),
    // Les documents attachés par un champ (§22.11) : la fenêtre les charge à
    // l'ouverture, même quand le type n'en déclare aucun.
    attaches: vi.fn(() => Promise.resolve({ attaches: [] })),
    definirAttaches: vi.fn(() => Promise.resolve({ ok: true })),
  },
}));

import { api } from "../api";
import ModifierSelection from "./ModifierSelection.jsx";

/**
 * Modification en série (§18.4).
 *
 * Le geste visé : cocher plusieurs fiches, les corriger l'une après l'autre
 * sans repasser par le tableau. Ce qui se vérifie ici, c'est qu'on sait
 * toujours où l'on en est, et que la fenêtre rend à la fin la liste de ce qui a
 * réellement été enregistré — une fiche passée n'en fait pas partie.
 */
describe("modification en série", () => {
  beforeEach(() => vi.clearAllMocks());

  const rendre = (props = {}) => render(
    <ModifierSelection
      ids={[11, 12, 13]}
      categories={[{ id: 2, nom: "Factures", parent_id: null }]}
      fournisseurs={[{ id: 1, nom: "Orange" }]}
      onFerme={() => {}}
      onEnregistre={() => {}}
      {...props}
    />,
  );

  it("situe la fiche courante dans la sélection", async () => {
    rendre();
    expect(await screen.findByText("Modifier — fiche 1 sur 3")).toBeDefined();
  });

  /**
   * Le bouton reste inactif tant que le verrou n'est pas pris : attendre son
   * activation, c'est attendre l'état où l'utilisateur peut réellement cliquer.
   */
  const attendreLeVerrou = async (libelle) => {
    const bouton = await screen.findByText(libelle);
    await waitFor(() => expect(bouton.disabled).toBe(false));
    return bouton;
  };

  it("enchaîne sur la suivante après enregistrement", async () => {
    rendre();
    await screen.findByText("Modifier — fiche 1 sur 3");
    fireEvent.click(await attendreLeVerrou("Enregistrer et suivant"));
    await waitFor(() => expect(api.patchDocument).toHaveBeenCalled());
    expect(await screen.findByText("Modifier — fiche 2 sur 3")).toBeDefined();
  });

  it("laisse passer une fiche sans y toucher", async () => {
    rendre();
    await screen.findByText("Modifier — fiche 1 sur 3");
    fireEvent.click(screen.getByText("Passer"));
    expect(await screen.findByText("Modifier — fiche 2 sur 3")).toBeDefined();
    expect(api.patchDocument).not.toHaveBeenCalled();
  });

  it("ne rend que les fiches réellement enregistrées, jamais celles passées", async () => {
    const fermetures = [];
    rendre({ ids: [11, 12], onFerme: (faites) => fermetures.push(faites) });

    await screen.findByText("Modifier — fiche 1 sur 2");
    fireEvent.click(screen.getByText("Passer"));           // la 11 reste à faire
    await screen.findByText("Modifier — fiche 2 sur 2");
    fireEvent.click(await attendreLeVerrou("Enregistrer"));   // la 12 est traitée

    await waitFor(() => expect(fermetures).toHaveLength(1));
    expect(fermetures[0]).toEqual([12]);
  });

  it("propose de sauter une fiche devenue illisible plutôt que de tout arrêter", async () => {
    api.document.mockImplementationOnce(() => Promise.reject(new Error("Document introuvable")));
    rendre();
    expect(await screen.findByText("Document introuvable")).toBeDefined();
    expect(screen.getByText("Passer à la suivante")).toBeDefined();
  });
});
