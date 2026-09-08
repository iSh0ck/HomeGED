import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ApprentissageRegle from "./ApprentissageRegle.jsx";

const DOCUMENTS = [{ id: 7, nom_fichier: "facture.pdf", categorie: "Factures",
                     fournisseur: "Orange", date_document: "2026-04-02",
                     date_import: "2026-04-03T10:00:00", statut: "traite",
                     metadonnees: {}, libelles_references: {} }];

const MOTS = {
  largeur: 562, hauteur: 795,
  mots: [
    { texte: "Total", x: 0.6, y: 0.5, l: 0.05, h: 0.015 },
    { texte: "TTC", x: 0.66, y: 0.5, l: 0.04, h: 0.015 },
    { texte: "174.00", x: 0.83, y: 0.5, l: 0.07, h: 0.015 },
  ],
};

let envois;
let perimetres;

beforeEach(() => {
  envois = [];
  perimetres = [];
  URL.createObjectURL = vi.fn(() => "blob:page");
  URL.revokeObjectURL = vi.fn();
  global.fetch = vi.fn(async (url, options) => {
    const chemin = String(url);
    envois.push({
      chemin,
      // Le dépôt d'un exemple part en multipart : seul le JSON se relit ici.
      corps: typeof options?.body === "string" ? JSON.parse(options.body) : null,
    });
    if (chemin.includes("/regles/exemples")) {
      const url = new URL(chemin, "http://x");
      const categorie = url.searchParams.get("categorie_id");
      perimetres.push(categorie);
      const q = url.searchParams.get("q") || "";
      // « zorglub » n'existe pas dans le type, mais ailleurs dans la GED : c'est
      // le cas qui doit proposer d'élargir plutôt que de dire « rien ».
      const trouve = !q || q === "orange" || (q === "zorglub" && !categorie);
      return new Response(JSON.stringify({
        recents: q.length < 3, jours_recents: 30, minimum_recherche: 3,
        ailleurs: q === "zorglub" && categorie ? 2 : 0,
        documents: trouve ? DOCUMENTS : [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.includes("/exemple-importe")) {
      if (chemin.endsWith("/apercu")) {
        return { ok: true, status: 200, blob: async () => new Blob(["png"]) };
      }
      return new Response(JSON.stringify({
        jeton: "abc123", nom_fichier: "nouveau.pdf", texte: "Total TTC : 174.00", page: MOTS,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.includes("/mots")) {
      return new Response(JSON.stringify(MOTS),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.includes("/apercu")) {
      return { ok: true, status: 200, blob: async () => new Blob(["png"]) };
    }
    if (chemin.includes("/apprendre")) {
      return new Response(JSON.stringify({
        pattern: "Total\\s+TTC\\s*:?\\s*([\\d ]*\\d[.,]\\d{1,2})",
        fonction: "nombre_normalise", type_champ: "montant", forme: "montant",
        ancre: "Total TTC", trouve: true, valeur_extraite: "174.00", conforme: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify(DOCUMENTS), {
      status: 200, headers: { "Content-Type": "application/json", "X-Total-Count": "1" } });
  });
});

describe("apprentissage d'une règle", () => {
  it("montre les mots du document, cliquables", async () => {
    render(<ApprentissageRegle categorieId={2} categorieNom="Factures" onFermer={() => {}} />);
    expect(await screen.findByLabelText("Choisir « 174.00 »")).toBeDefined();
  });

  it("désigne une valeur puis son intitulé, et propose une règle vérifiée", async () => {
    render(<ApprentissageRegle categorieId={2} categorieNom="Factures" onFermer={() => {}} />);

    await userEvent.click(await screen.findByLabelText("Choisir « 174.00 »"));
    await userEvent.click(screen.getByRole("button", { name: "Son intitulé" }));
    await userEvent.click(screen.getByLabelText("Choisir « Total »"));
    await userEvent.click(screen.getByLabelText("Choisir « TTC »"));
    await userEvent.click(screen.getByRole("button", { name: /Proposer une règle/ }));

    // ce qui part au serveur : la valeur et son intitulé, remis dans l'ordre de
    // la page et non dans celui des clics
    await waitFor(() => expect(envois.some((e) => e.chemin.includes("/apprendre"))).toBe(true));
    const envoi = envois.find((e) => e.chemin.includes("/apprendre"));
    expect(envoi.corps.valeur).toBe("174.00");
    expect(envoi.corps.ancre).toBe("Total TTC");

    // et la vérification s'affiche avant tout enregistrement
    expect(await screen.findByText(/elle extrait bien/i)).toBeDefined();
  });

  it("la proposition remplit le formulaire, elle ne l'enregistre pas", async () => {
    const utiliser = vi.fn();
    render(<ApprentissageRegle categorieId={2} categorieNom="Factures" onFermer={() => {}}
                        onUtiliser={utiliser} />);

    await userEvent.click(await screen.findByLabelText("Choisir « 174.00 »"));
    await userEvent.click(screen.getByRole("button", { name: /Proposer une règle/ }));
    await userEvent.click(await screen.findByText("Utiliser cette règle"));

    expect(utiliser).toHaveBeenCalledWith(expect.objectContaining({
      fonction: "nombre_normalise", type_champ: "montant",
    }));
  });

  it("ne cherche qu'à partir de trois caractères, et montre le dernier mois avant", async () => {
    render(<ApprentissageRegle categorieId={2} categorieNom="Factures" onFermer={() => {}} />);
    await screen.findByLabelText("Choisir « 174.00 »");
    expect(screen.getByText(/Documents ajoutés dans « Factures » depuis un mois/)).toBeDefined();

    await userEvent.type(screen.getByLabelText("Chercher un document d'exemple"), "or");
    // deux lettres : rien ne part au serveur, et l'on dit ce qui manque
    expect(await screen.findByText(/Encore 1 caractère/)).toBeDefined();
    expect(envois.filter((e) => e.chemin.includes("q=or")).length).toBe(0);

    await userEvent.type(screen.getByLabelText("Chercher un document d'exemple"), "ange");
    await waitFor(() => expect(
      envois.some((e) => e.chemin.includes("/regles/exemples") && e.chemin.includes("q=orange"))
    ).toBe(true));
  });

  it("importe un document absent de la GED et apprend dessus son texte", async () => {
    render(<ApprentissageRegle categorieId={2} categorieNom="Factures" onFermer={() => {}} />);
    await screen.findByLabelText("Choisir « 174.00 »");

    await userEvent.click(screen.getByRole("button", { name: "Document à importer" }));
    const fichier = new File(["%PDF"], "nouveau.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("Importer un document d'exemple"), fichier);

    // la page importée remplace celle du registre, et l'on y clique de même
    await waitFor(() => expect(
      envois.some((e) => e.chemin.includes("/exemple-importe/abc123/apercu"))).toBe(true));
    await userEvent.click(await screen.findByLabelText("Choisir « 174.00 »"));
    await userEvent.click(screen.getByRole("button", { name: /Proposer une règle/ }));

    const envoi = await waitFor(() => {
      const trouve = envois.find((e) => e.chemin.includes("/apprendre"));
      expect(trouve).toBeDefined();
      return trouve;
    });
    // rien n'est entré au registre : c'est le texte de l'exemple qui part
    expect(envoi.corps.document_id).toBe(null);
    expect(envoi.corps.texte).toContain("174.00");
  });

  it("cherche d'abord dans le type, et propose d'élargir quand il n'a rien", async () => {
    render(<ApprentissageRegle categorieId={2} categorieNom="Factures" onFermer={() => {}} />);
    await screen.findByLabelText("Choisir « 174.00 »");
    // le premier relevé porte le type en cours d'édition, pas toute la GED
    expect(perimetres[0]).toBe("2");

    await userEvent.type(screen.getByLabelText("Chercher un document d'exemple"), "zorglub");
    const elargir = await screen.findByText(/2 documents ailleurs dans la GED/);

    await userEvent.click(elargir);
    await waitFor(() => expect(perimetres.at(-1)).toBe(null));
    expect(await screen.findByText(/Résultats de la recherche dans toute la GED/)).toBeDefined();
  });
});
