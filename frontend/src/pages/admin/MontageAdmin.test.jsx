import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../api", () => ({
  adminApi: {
    categories: vi.fn(() => Promise.resolve([
      { id: 2, nom: "Factures", nature: "type" },
      { id: 1, nom: "Maison", nature: "dossier" },
    ])),
    reglesChamps: vi.fn(() => Promise.resolve([
      { id: 11, champ: "meta:montant_ttc", libelle_effectif: "Montant TTC",
        obligatoire: true, type_champ: "montant", deduction: "aucune",
        extraction_attendue: true },
      { id: 12, champ: "meta:emetteur", libelle_effectif: "Émetteur", obligatoire: true,
        source_table: "usr_emetteurs", deduction: "une" },
      // déclaré comme devant se lire sur le document, et rien ne le lit
      { id: 13, champ: "meta:numero_facture", libelle_effectif: "N° facture",
        obligatoire: false, type_champ: "texte", deduction: "aucune",
        extraction_attendue: true },
      // celui-ci se saisit à la main, et c'est très bien
      { id: 14, champ: "meta:commentaire", libelle_effectif: "Commentaire",
        obligatoire: false, type_champ: "texte_long", deduction: "aucune" },
    ])),
    // La **forme réelle** de la réponse, et non un tableau commode : c'est
    // exactement ce qui a manqué la première fois — l'écran est tombé en
    // service sur « s.filter is not a function » pendant que le test passait.
    colonnesCategorie: vi.fn(() => Promise.resolve({
      configurees: [{ champ: "meta:montant_ttc", libelle: null, largeur: null,
                      visible: true }],
      effectives: [{ champ: "meta:montant_ttc", libelle: "Montant TTC" }],
      disponibles: [{ champ: "meta:emetteur", libelle: "Émetteur" }],
      tri: { champ: null, sens: null },
      tri_effectif: { champ: "date_import", sens: "desc" },
      fiche: { champs_masques: [] },
    })),
    champsCibles: vi.fn(() => Promise.resolve([
      { champ: "montant_ttc", origine: "champ attendu", remplie_par_regle: true,
        regles: [{ id: 31, nom: "Montant TTC", profil_id: 5 }] },
      { champ: "date_document", origine: "date du document", remplie_par_regle: false,
        regles: [] },
    ])),
    enregistrerColonnes: vi.fn(() => Promise.resolve({ ok: true })),
    // L'éditeur de champ, ouvert depuis l'assemblage, charge son vocabulaire.
    champsDisponibles: vi.fn(() => Promise.resolve([])),
    sourcesChamps: vi.fn(() => Promise.resolve([
      { nom: "usr_emetteurs", libelle: "Émetteurs", colonnes: ["nom"],
        colonnes_identifiantes: ["nom"] },
    ])),
    typesDeChamp: vi.fn(() => Promise.resolve([{ valeur: "texte", libelle: "Texte" }])),
    supprimerRegleChamp: vi.fn(() => Promise.resolve({ ok: true })),
  },
  api: { colonnesCategories: vi.fn(() => Promise.resolve({ colonnes: {} })) },
}));

import { adminApi } from "../../api";
import MontageAdmin from "./MontageAdmin.jsx";

beforeEach(() => vi.clearAllMocks());

describe("assembler un type de document", () => {
  it("montre les quatre étapes, dans l'ordre où l'on y pense", async () => {
    render(<MontageAdmin />);

    expect(await screen.findByText("Ce que le document porte")).toBeDefined();
    expect(screen.getByText("Ce qu'on voit dans le tableau")).toBeDefined();
    expect(screen.getByText("Ce qui se remplit tout seul")).toBeDefined();
    expect(screen.getByText(/Ce qui arrive à terme/)).toBeDefined();
  });

  it("ne propose pas d'assembler un dossier : il ne porte aucun document", async () => {
    render(<MontageAdmin />);
    await screen.findByText("Ce que le document porte");
    expect(screen.queryByText("Maison")).toBeNull();
  });

  it("dit ce qui est déjà fait et ce qui manque", async () => {
    render(<MontageAdmin />);

    expect(await screen.findByText("4 champ(s) déclaré(s)")).toBeDefined();
    expect(screen.getByText("1 colonne(s)")).toBeDefined();
    // « N° facture » attend une règle et n'en a pas : c'est un réglage qui manque
    expect(screen.getByText("1 règle(s) à écrire")).toBeDefined();
  });

  it("coche une colonne sans quitter l'écran", async () => {
    render(<MontageAdmin />);

    // La case porte l'intitulé du champ : c'est ainsi qu'on la désigne à l'écran.
    const emetteur = await screen.findByLabelText("Émetteur");
    await userEvent.click(emetteur);

    await waitFor(() => expect(adminApi.enregistrerColonnes).toHaveBeenCalled());
    const [, envoyees] = adminApi.enregistrerColonnes.mock.calls[0];
    expect(envoyees.map((c) => c.champ)).toContain("meta:emetteur");
  });

  it("dit que chaque choix est enregistré, et le confirme", async () => {
    // Sans cela on cherche un bouton « Enregistrer » qui n'existe pas, et l'on
    // n'ose pas quitter la page (§22.25).
    render(<MontageAdmin />);
    expect(await screen.findByText(/Chaque choix est enregistré aussitôt/)).toBeDefined();

    await userEvent.click(await screen.findByLabelText("Émetteur"));
    expect(await screen.findByText("Colonne ajoutée")).toBeDefined();
  });

  it("renvoie aux règles d'extraction quand il faut y écrire", async () => {
    const ouvrir = vi.fn();
    render(<MontageAdmin onOuvrirEcran={ouvrir} />);

    await userEvent.click(await screen.findByText(/Ouvrir les règles d'extraction/));
    // avec le type en cours : y revenir à la main est le pas perdu qui fait
    // renoncer (§22.20)
    expect(ouvrir).toHaveBeenCalledWith("regles", { categorieId: 2 });
  });
});


describe("ce qui se remplit tout seul (§22.27)", () => {
  it("distingue une règle qui manque d'un champ qu'on saisit", async () => {
    render(<MontageAdmin />);

    await screen.findByText("Ce qui se remplit tout seul");
    // déclaré comme devant se lire, et rien ne le lit — l'icône et le texte
    // vivent dans le même élément, d'où le matcher souple
    expect(await screen.findByText(/règle à écrire/)).toBeDefined();
    // déclaré nulle part : il se saisit, et personne n'a à s'en inquiéter
    expect(screen.getByText("saisi à la main")).toBeDefined();
  });

  it("propose d'écrire la règle manquante, sur le bon champ", async () => {
    const ouvrir = vi.fn();
    render(<MontageAdmin onOuvrirEcran={ouvrir} />);

    await userEvent.click(await screen.findByTitle(/Écrire la règle qui remplira/));
    expect(ouvrir).toHaveBeenCalledWith("regles",
      { categorieId: 2, champCible: "numero_facture" });
  });
});


describe("aller à ce qui remplit un champ (§22.28)", () => {
  it("ouvre la règle elle-même, dans son jeu", async () => {
    const ouvrir = vi.fn();
    render(<MontageAdmin onOuvrirEcran={ouvrir} />);

    // « Montant TTC » est rempli par la règle nº31 : le raccourci y mène
    await userEvent.click(await screen.findByTitle(/Ouvrir la règle « Montant TTC »/));
    expect(ouvrir).toHaveBeenCalledWith("regles",
      { categorieId: 2, jeuId: 5, regleId: 31, champCible: undefined });
  });

  it("mais ouvre le champ quand c'est une déduction : elle se règle sur lui", async () => {
    const ouvrir = vi.fn();
    render(<MontageAdmin onOuvrirEcran={ouvrir} />);

    // « Émetteur » se déduit d'une table : rien à corriger dans les règles
    await userEvent.click(await screen.findByTitle(/la déduction se règle sur lui/));
    expect(ouvrir).not.toHaveBeenCalled();
    expect(await screen.findByText(/Modifier le champ attendu/)).toBeDefined();
  });
});

/**
 * Décocher une colonne, et que cela tienne (§22.87).
 *
 * Un champ attendu déclaré par le type **s'invite** dans le tableau quand rien
 * ne le mentionne — c'est voulu : une exigence ajoutée après coup doit se voir.
 * Décocher retirait la ligne, et l'invitation la remettait au chargement
 * suivant : la décision qu'on venait de prendre ne tenait pas.
 */
describe("ce qu'on voit dans le tableau", () => {
  it("dit ce que le tableau montre, et non ce qui est configuré", async () => {
    // `date_document` est déclaré, jamais réglé, et pourtant affiché : la case
    // le donnait pour absent.
    adminApi.reglesChamps.mockResolvedValueOnce([
      { id: 11, champ: "meta:montant_ttc", libelle_effectif: "Montant TTC",
        obligatoire: true, type_champ: "montant", deduction: "aucune" },
      // Déclaré, jamais réglé comme colonne, et pourtant affiché.
      { id: 15, champ: "date_document", libelle_effectif: "Date du document",
        obligatoire: true, type_champ: "date", deduction: "aucune" },
    ]);
    adminApi.colonnesCategorie.mockResolvedValueOnce({
      configurees: [{ champ: "meta:montant_ttc", libelle: null, largeur: null, visible: true }],
      effectives: [{ champ: "meta:montant_ttc", libelle: "Montant TTC" },
                   { champ: "date_document", libelle: "Date du document" }],
      disponibles: [],
      tri: { champ: null, sens: null },
      tri_effectif: { champ: "date_import", sens: "desc" },
      fiche: { champs_masques: [] },
    });
    render(<MontageAdmin contexte={{ categorieId: 2 }} />);

    const case_ = await screen.findByLabelText("Date du document");
    expect(case_.checked).toBe(true);
  });

  it("masque au lieu d'effacer, pour que la décision tienne", async () => {
    const utilisateur = userEvent.setup();
    adminApi.reglesChamps.mockResolvedValueOnce([
      { id: 11, champ: "meta:montant_ttc", libelle_effectif: "Montant TTC",
        obligatoire: true, type_champ: "montant", deduction: "aucune" },
      // Déclaré, jamais réglé comme colonne, et pourtant affiché.
      { id: 15, champ: "date_document", libelle_effectif: "Date du document",
        obligatoire: true, type_champ: "date", deduction: "aucune" },
    ]);
    adminApi.colonnesCategorie.mockResolvedValueOnce({
      configurees: [{ champ: "meta:montant_ttc", libelle: null, largeur: null, visible: true }],
      effectives: [{ champ: "meta:montant_ttc", libelle: "Montant TTC" },
                   { champ: "date_document", libelle: "Date du document" }],
      disponibles: [],
      tri: { champ: null, sens: null },
      tri_effectif: { champ: "date_import", sens: "desc" },
      fiche: { champs_masques: [] },
    });
    render(<MontageAdmin contexte={{ categorieId: 2 }} />);

    await utilisateur.click(await screen.findByLabelText("Date du document"));

    const [, envoyees] = adminApi.enregistrerColonnes.mock.calls.at(-1);
    const posee = envoyees.find((c) => c.champ === "date_document");
    expect(posee, "la ligne doit rester, masquée").toBeDefined();
    expect(posee.visible).toBe(false);
  });
});
