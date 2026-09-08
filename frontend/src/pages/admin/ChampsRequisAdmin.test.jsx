import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const REGLE = {
  id: 15, categorie_id: 22, champ: "meta:date", libelle: "Date",
  libelle_effectif: "Date", obligatoire: true, identifiant: false,
  deduction: "aucune", colonnes_deduction: [], deduction_approchee: false,
  echeance: false, rappel_jours: null, attache_documents: false,
  type_champ: "date", documents_categorie_id: null, documents_champs: [], ordre: 10,
};

vi.mock("../../api", () => ({
  adminApi: {
    categories: vi.fn(() => Promise.resolve([{ id: 22, nom: "Entretiens", nature: "fiche" }])),
    champsDisponibles: vi.fn(() => Promise.resolve([])),
    sourcesChamps: vi.fn(() => Promise.resolve([])),
    typesDeChamp: vi.fn(() => Promise.resolve([
      { valeur: "texte", libelle: "Texte" }, { valeur: "date", libelle: "Date" },
    ])),
    reglesChamps: vi.fn(() => Promise.resolve([REGLE])),
    champsCibles: vi.fn(() => Promise.resolve([])),
    creerRegleChamp: vi.fn(() => Promise.resolve({})),
    modifierRegleChamp: vi.fn(() => Promise.resolve({})),
  },
  api: { colonnesCategories: vi.fn(() => Promise.resolve({ colonnes: {}, tris: {} })) },
}));

import ChampsRequisAdmin from "./ChampsRequisAdmin.jsx";

beforeEach(() => vi.clearAllMocks());

describe("les champs attendus d'une catégorie", () => {
  it("ouvre la modification sur ce qui avait été paramétré", async () => {
    render(<ChampsRequisAdmin />);

    await userEvent.click(await screen.findByLabelText("Modifier"));

    // Ce qui a été réglé doit revenir tel quel : refaire le paramétrage à chaque
    // correction, c'est perdre ce qu'on venait ajuster.
    expect(await screen.findByDisplayValue("Date")).toBeDefined();
    expect(screen.getByLabelText("Clé de stockage")).toHaveProperty("value", "date");
    expect(screen.getByLabelText("Type de valeur").textContent).toContain("Date");
  });
});
