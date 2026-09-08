import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../api", () => ({
  adminApi: {
    champsDisponibles: vi.fn(() => Promise.resolve([
      { champ: "meta:numero_facture", libelle: "N° facture" },
      { champ: "date_document", libelle: "Date du document" },
    ])),
    sourcesChamps: vi.fn(() => Promise.resolve([
      { nom: "usr_emetteurs", libelle: "Émetteurs", colonnes: ["nom"],
        colonnes_identifiantes: ["nom"] },
    ])),
    typesDeChamp: vi.fn(() => Promise.resolve([
      { valeur: "texte", libelle: "Texte" },
      { valeur: "texte_long", libelle: "Texte long (plusieurs lignes)" },
      { valeur: "date", libelle: "Date" },
    ])),
    categories: vi.fn(() => Promise.resolve([
      { id: 2, nom: "Factures", nature: "type" },
      { id: 1, nom: "Maison", nature: "dossier" },
    ])),
    reglesChamps: vi.fn(() => Promise.resolve([])),
    // Ce qu'une règle d'extraction remplit déjà : sert à grouper la liste des
    // champs déjà connus par provenance (§22.20).
    champsCibles: vi.fn(() => Promise.resolve([
      { champ: "numero_facture", origine: "champ attendu", remplie_par_regle: true },
      { champ: "date_document", origine: "date du document", remplie_par_regle: false },
    ])),
    creerRegleChamp: vi.fn(() => Promise.resolve({ id: 9 })),
    modifierRegleChamp: vi.fn(() => Promise.resolve({ id: 9 })),
  },
  // La forme réelle : `{ colonnes: {…}, tris: {…} }`, et non un tableau.
  api: { colonnesCategories: vi.fn(() => Promise.resolve({ colonnes: {}, tris: {} })) },
}));

import { adminApi } from "../api";
import EditeurChampAttendu from "./EditeurChampAttendu.jsx";

beforeEach(() => vi.clearAllMocks());

describe("déclarer un champ attendu", () => {
  it("propose la nature d'abord : c'est elle qui commande le reste", async () => {
    render(<EditeurChampAttendu categorieId={22} onFerme={() => {}} />);

    expect(await screen.findByText("Champ libre")).toBeDefined();
    expect(screen.getByText("Lié à une table")).toBeDefined();
    expect(screen.getByText("Documents de la GED")).toBeDefined();
    expect(screen.getByText("Champ déjà connu")).toBeDefined();
  });

  it("un champ libre se nomme, se type, et sa clé se déduit de l'intitulé", async () => {
    render(<EditeurChampAttendu categorieId={22} onFerme={() => {}}
                                onEnregistre={() => {}} />);

    await userEvent.type(await screen.findByLabelText("Intitulé du champ"), "Kilométrage relevé");
    await userEvent.click(screen.getByText("Enregistrer"));

    await waitFor(() => expect(adminApi.creerRegleChamp).toHaveBeenCalled());
    const [payload] = adminApi.creerRegleChamp.mock.calls[0];
    // la clé technique ne se tape plus à la main
    expect(payload.champ).toBe("meta:kilometrage_releve");
    expect(payload.libelle).toBe("Kilométrage relevé");
    expect(payload.type_champ).toBe("texte");
  });

  it("un champ « documents » déclare ce qu'il accepte", async () => {
    render(<EditeurChampAttendu categorieId={22} onFerme={() => {}}
                                onEnregistre={() => {}} />);

    await userEvent.click(await screen.findByText("Documents de la GED"));
    await userEvent.type(screen.getByLabelText("Intitulé du champ"), "Factures liées");

    // le type accepté : un dossier ne porte aucun document, il n'est pas proposé
    await userEvent.click(screen.getByLabelText("Type de document accepté"));
    expect(screen.queryByText("Maison")).toBeNull();
    await userEvent.click(await screen.findByText("Factures"));

    await userEvent.click(screen.getByText("Enregistrer"));
    await waitFor(() => expect(adminApi.creerRegleChamp).toHaveBeenCalled());
    const [payload] = adminApi.creerRegleChamp.mock.calls[0];
    expect(payload.attache_documents).toBe(true);
    expect(payload.documents_categorie_id).toBe(2);
  });
});

describe("modifier un champ existant", () => {
  const REGLE = {
    id: 15, categorie_id: 22, champ: "meta:date", libelle: "Date",
    libelle_effectif: "Date", obligatoire: true, identifiant: false,
    deduction: "aucune", colonnes_deduction: [], deduction_approchee: false,
    echeance: false, rappel_jours: null, attache_documents: false,
    type_champ: "date", documents_categorie_id: null, documents_champs: [], ordre: 10,
  };

  it("remonte ce qui avait été paramétré", async () => {
    render(<EditeurChampAttendu categorieId={22} regle={REGLE} onFerme={() => {}} />);

    // l'intitulé, le type et la clé : rien à refaire
    expect(await screen.findByDisplayValue("Date")).toBeDefined();
    expect(screen.getByLabelText("Type de valeur").textContent).toContain("Date");
    expect(screen.getByLabelText("Clé de stockage")).toHaveProperty("value", "date");
    expect(screen.getByLabelText(/Obligatoire/i)).toHaveProperty("checked", true);
  });

  it("garde le champ choisi quand on modifie un « champ déjà connu »", async () => {
    // Il figure forcément parmi les règles déjà déclarées : l'écarter comme les
    // autres vidait la liste, et il fallait refaire le choix pour corriger autre
    // chose (§22.22).
    render(<EditeurChampAttendu categorieId={22} onFerme={() => {}} regle={{
      ...REGLE, id: 17, champ: "date_document", libelle: "", libelle_effectif: "Date",
      type_champ: "texte",
    }} />);

    const liste = await screen.findByLabelText("Champ attendu");
    await waitFor(() => expect(liste.textContent).toContain("Date du document"));
    expect(liste.textContent).not.toContain("— Choisir un champ —");
  });

  it("remonte aussi ce qu'un champ « documents » accepte", async () => {
    render(<EditeurChampAttendu categorieId={22} onFerme={() => {}} regle={{
      ...REGLE, id: 16, champ: "meta:factures_liees", libelle: "Factures liées",
      libelle_effectif: "Factures liées", obligatoire: false, type_champ: "texte",
      attache_documents: true, documents_categorie_id: 2,
      documents_champs: ["meta:numero_facture"],
    }} />);

    expect(await screen.findByDisplayValue("Factures liées")).toBeDefined();
    // le type accepté et les champs cochés doivent revenir tels quels
    expect(screen.getByLabelText("Type de document accepté").textContent)
      .toContain("Factures");
  });
});


describe("ce que « Champ déjà connu » propose", () => {
  it("s'en tient au vocabulaire de ce type, pas à celui de toute la GED", async () => {
    // Sur une fiche « Entretiens », la liste proposait des véhicules, des
    // émetteurs, des numéros de facture — beaucoup d'entrées, aucune qui décrive
    // un entretien (§22.24).
    render(<EditeurChampAttendu categorieId={22} onFerme={() => {}} />);

    await userEvent.click(await screen.findByText("Champ déjà connu"));
    const liste = screen.getByLabelText("Champ attendu");
    await userEvent.click(liste);

    // ce que ce type a déjà nommé — sous son intitulé — et les colonnes du document
    expect(await screen.findByText("N° facture")).toBeDefined();
    expect(screen.getByText("Date du document")).toBeDefined();
    // et pas les critères de lien, qui ne sont pas des valeurs d'un document
    expect(screen.queryByText(/Membres du foyer/)).toBeNull();
  });
});
