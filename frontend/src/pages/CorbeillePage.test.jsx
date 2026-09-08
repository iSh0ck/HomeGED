import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CorbeillePage from "./CorbeillePage.jsx";

const DOCUMENTS = [
  { id: 4, nom_fichier: "facture.pdf", libelle: "Facture Orange", categorie: "Factures",
    fournisseur: "Orange", date_suppression: "2026-09-05T10:00:00", supprime_par: "Lucas",
    masquee: false },
];

let appels;

beforeEach(() => {
  appels = [];
  global.fetch = vi.fn(async (url, options) => {
    appels.push(`${options?.method || "GET"} ${url}`);
    // La corbeille rend une **page** depuis le §22.90 : `{total, documents}`.
    // Le total porte sur la corbeille entière, pas sur ce qui est affiché.
    const corps = String(url).includes("/corbeille?")
      ? { total: DOCUMENTS.length, documents: DOCUMENTS }
      : DOCUMENTS;
    return new Response(JSON.stringify(corps),
                        { status: 200, headers: { "Content-Type": "application/json" } });
  });
});

describe("ma corbeille", () => {
  it("dit ce qui attend, et depuis quand", async () => {
    render(<CorbeillePage onRetour={() => {}} />);

    expect(await screen.findByText("Facture Orange")).toBeDefined();
    expect(screen.getByText(/Factures/)).toBeDefined();
  });

  it("restaure un document à sa place", async () => {
    const change = vi.fn();
    render(<CorbeillePage onRetour={() => {}} onChangement={change} />);

    await userEvent.click(await screen.findByText("Restaurer"));
    await waitFor(() => expect(
      appels.some((a) => a === "POST /api/corbeille/4/restaurer")).toBe(true));
    expect(change).toHaveBeenCalled();
  });

  it("« retirer » ne détruit pas : il masque", async () => {
    // une corbeille qui détruit au second clic n'est plus un filet
    render(<CorbeillePage onRetour={() => {}} />);

    await userEvent.click(await screen.findByText("Retirer"));
    await waitFor(() => expect(
      appels.some((a) => a === "DELETE /api/corbeille/4")).toBe(true));
  });
});

/**
 * Une corbeille qui se parcourt (§22.90).
 *
 * La liste s'arrêtait à 500 sans le dire : au-delà, les plus anciens n'étaient
 * plus récupérables depuis cet écran, et rien ne signalait qu'ils existaient.
 */
describe("la corbeille se pagine", () => {
  const beaucoup = Array.from({ length: 25 }, (_, rang) => ({
    ...DOCUMENTS[0], id: 100 + rang, libelle: `Document ${rang}`,
  }));

  beforeEach(() => {
    appels = [];
    global.fetch = vi.fn(async (url, options) => {
      appels.push(`${options?.method || "GET"} ${url}`);
      return new Response(JSON.stringify({ total: 120, documents: beaucoup }),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    });
  });

  it("demande une page, et dit combien il en reste en tout", async () => {
    render(<CorbeillePage onRetour={() => {}} />);

    await screen.findByText("Document 0");
    expect(appels.some((a) => a.includes("/corbeille?limite=25&decalage=0"))).toBe(true);
    // Le total porte sur la corbeille entière : c'est ce qu'on vient y chercher.
    expect(screen.getByText(/120/)).toBeDefined();
  });

  it("va chercher la page suivante", async () => {
    const utilisateur = userEvent.setup();
    render(<CorbeillePage onRetour={() => {}} />);

    await screen.findByText("Document 0");
    await utilisateur.click(screen.getByLabelText("Page suivante"));

    await waitFor(() => expect(
      appels.some((a) => a.includes("decalage=25"))).toBe(true));
  });
});
