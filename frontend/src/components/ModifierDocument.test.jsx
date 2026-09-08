import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../api", () => ({
  api: {
    prendreVerrou: vi.fn(),
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
import ModifierDocument from "./ModifierDocument.jsx";

const DOC = {
  id: 4, nom_fichier: "facture.pdf", fournisseur: "Orange", categorie: "Factures",
  categorie_id: 2, date_document: "2026-07-21", statut: "traite",
  metadonnees: {}, champs_attendus: [], libelles_references: {},
};

/**
 * Verrou de modification (§17.21) : ce que voit celui qui arrive second.
 *
 * Deux personnes du foyer ouvrent la même facture. La seconde doit comprendre
 * ce qui se passe — un refus muet la laisserait croire à une panne, et écraser
 * le travail de l'autre serait pire encore.
 */
describe("fenêtre de modification", () => {
  beforeEach(() => vi.clearAllMocks());

  const rendre = () => render(
    <ModifierDocument doc={DOC} categories={[]} fournisseurs={[]}
                      onFerme={() => {}} onEnregistre={() => {}} />,
  );

  it("annonce qui détient la fiche quand le verrou est refusé", async () => {
    api.prendreVerrou.mockRejectedValue(
      new Error("Document en cours de modification par Claire Martin. Réessayez dans quelques minutes."));
    rendre();

    expect(await screen.findByText("Document en cours de modification")).toBeDefined();
    expect(screen.getByText(/Claire Martin/)).toBeDefined();
    expect(screen.getByText(/se libère de lui-même/)).toBeDefined();
    // et le formulaire n'est pas proposé : on ne saisit pas dans le vide
    expect(screen.queryByText("Enregistrer")).toBeNull();
  });

  it("laisse écrire quand le verrou est obtenu", async () => {
    api.prendreVerrou.mockResolvedValue({ jusqu_a: "2026-09-04T20:00:00" });
    rendre();

    expect(await screen.findByText(/Vous modifiez ce document/)).toBeDefined();
    expect(screen.getByText("Enregistrer")).toBeDefined();
  });
});

describe("la date du document prend sa place déclarée (§22.77)", () => {
  const avecChamps = (champs) => ({
    ...DOC, categorie_id: 2, champs_attendus: champs,
  });

  beforeEach(() => {
    vi.clearAllMocks();
    // Le formulaire n'apparaît qu'une fois le verrou obtenu : sans lui, on
    // saisirait dans le vide.
    api.prendreVerrou.mockResolvedValue({ jusqu_a: "2026-09-08T20:00:00" });
  });

  it("s'affiche dans l'ordre que l'administration a déclaré", async () => {
    // Elle s'affichait dans un bloc figé en tête de formulaire, avant tous les
    // champs du type : elle avait l'air ajoutée par l'application alors qu'elle
    // est un champ attendu comme les autres.
    render(
      <ModifierDocument
        doc={avecChamps([
          { champ: "meta:emetteur", libelle: "Émetteur", obligatoire: true,
            type_champ: "texte", sources: [] },
          { champ: "date_document", libelle: "Date du document", obligatoire: true,
            type_champ: "date", sources: [] },
          { champ: "meta:titulaire", libelle: "Titulaire", obligatoire: false,
            type_champ: "texte", sources: [] },
        ])}
        categories={[]}
        onFerme={() => {}}
        onEnregistre={() => {}}
      />,
    );
    await screen.findByText("Enregistrer");
    // Un champ obligatoire porte son astérisque : on compare les intitulés nus.
    const intitules = [...document.querySelectorAll("label")]
      .map((n) => n.textContent.replace(/\s*\*\s*$/, "").trim())
      .filter((texte) => ["Émetteur", "Date du document", "Titulaire"].includes(texte));
    expect(intitules).toEqual(["Émetteur", "Date du document", "Titulaire"]);
  });

  it("ne s'affiche pas quand le type ne la déclare pas", async () => {
    render(
      <ModifierDocument
        doc={avecChamps([
          { champ: "meta:commentaire", libelle: "Commentaire", obligatoire: false,
            type_champ: "texte", sources: [] },
        ])}
        categories={[]}
        onFerme={() => {}}
        onEnregistre={() => {}}
      />,
    );
    await screen.findByText("Enregistrer");
    expect(screen.queryByLabelText("Date du document")).toBeNull();
  });
});
