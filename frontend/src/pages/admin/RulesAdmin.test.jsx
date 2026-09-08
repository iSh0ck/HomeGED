import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const REGLE = {
  id: 51, profil_id: 1, nom: "Numéro de facture", champ_cible: "numero_facture",
  pattern: "(?i)facture\\s*n°\\s*([A-Z0-9-]+)", fonction: "", parametre: "",
  type_champ: "texte", priorite: 100, actif: true,
};

vi.mock("../../api", () => ({
  adminApi: {
    categories: vi.fn(() => Promise.resolve([{ id: 2, nom: "Factures", nature: "type" }])),
    jeuxExtraction: vi.fn(() => Promise.resolve([
      { id: 1, nom: "Factures (générique)", categorie_id: 2, generique: true,
        actif: true, priorite: 100, nb_regles: 1 },
    ])),
    regles: vi.fn(() => Promise.resolve([REGLE])),
    champsCibles: vi.fn(() => Promise.resolve([
      { champ: "numero_facture", origine: "champ attendu", remplie_par_regle: true,
        regles: [{ id: 51, nom: "Numéro de facture", profil_id: 1 }] },
    ])),
    fonctionsExtraction: vi.fn(() => Promise.resolve([])),
    modifierRegle: vi.fn(() => Promise.resolve({})),
    creerRegle: vi.fn(() => Promise.resolve({})),
  },
  api: {},
}));

import RulesAdmin from "./RulesAdmin.jsx";

beforeEach(() => vi.clearAllMocks());

describe("l'écran des règles d'extraction", () => {
  it("nomme chaque règle par sa référence", async () => {
    render(<RulesAdmin />);
    // « la R-0051 ne trouve plus rien » se dit ; « la deuxième de la liste », non
    expect(await screen.findByText("R-0051")).toBeDefined();
  });

  it("dit en clair comment le motif est lu, et le change", async () => {
    render(<RulesAdmin />);

    await userEvent.click(await screen.findByLabelText("Modifier"));
    const drapeaux = await screen.findByLabelText("Drapeaux de l'expression régulière");
    // la règle porte (?i) : la liste doit le montrer, pas le laisser deviner
    expect(drapeaux.textContent).toContain("sans tenir compte de la casse");

    await userEvent.click(drapeaux);
    await userEvent.click(await screen.findByText(/casse ignorée, ligne par ligne/));

    // le drapeau est **remplacé** : deux groupes à la suite seraient une erreur
    const motif = screen.getByDisplayValue(/^\(\?i/);
    await waitFor(() => expect(motif.value.startsWith("(?im)")).toBe(true));
    expect(motif.value).not.toContain("(?i)(?im)");
  });

  it("ouvre la règle voulue quand on arrive depuis l'assemblage", async () => {
    render(<RulesAdmin contexte={{ categorieId: 2, jeuId: 1, regleId: 51 }} />);

    // on arrive **sur** la règle, formulaire ouvert : c'est là qu'on la corrige
    expect(await screen.findByText("Modifier la règle")).toBeDefined();
    expect(screen.getByDisplayValue("Numéro de facture")).toBeDefined();
  });
});
