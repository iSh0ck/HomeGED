import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HistoriqueDocument from "./HistoriqueDocument.jsx";

const JOURNAL = [
  {
    id: 2, date_evenement: "2026-09-04T15:04:37", auteur: "marie@foyer.fr",
    action: "document.modification",
    details: {
      avant: { categorie: "Factures", titulaire: null },
      apres: { categorie: "Impôts", titulaire: "Jean Dupont" },
    },
  },
  {
    // entrée ancienne : elle ne porte qu'un identifiant
    id: 1, date_evenement: "2026-09-03T10:00:00", auteur: "admin@ged.local",
    action: "document.modification", details: { categorie_id: 2 },
  },
];

describe("historique d'un document", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify({ total: JOURNAL.length, evenements: JOURNAL }), {
        status: 200, headers: { "Content-Type": "application/json" },
      },
    ));
  });

  it("annonce d'abord les champs touchés, sans leurs valeurs", async () => {
    render(<HistoriqueDocument documentId={1} onFermer={() => {}} />);

    await waitFor(() => expect(screen.getAllByRole("button").length).toBeGreaterThan(1));
    // l'aperçu nomme ce qui a bougé…
    expect(screen.getByText("Catégorie, Titulaire")).toBeDefined();
    // …mais les valeurs restent repliées
    expect(screen.queryByText("Impôts")).toBeNull();
  });

  it("montre l'ancienne et la nouvelle valeur une fois déroulé", async () => {
    const utilisateur = userEvent.setup();
    render(<HistoriqueDocument documentId={1} onFermer={() => {}} />);

    await waitFor(() => expect(screen.getByText("Catégorie, Titulaire")).toBeDefined());
    await utilisateur.click(screen.getByText("Catégorie, Titulaire"));

    expect(screen.getByText("Factures")).toBeDefined();
    expect(screen.getByText("Impôts")).toBeDefined();
    expect(screen.getByText("Jean Dupont")).toBeDefined();
  });

  it("reste lisible sur les entrées anciennes, qui ne portent qu'un identifiant", async () => {
    const utilisateur = userEvent.setup();
    render(
      <HistoriqueDocument
        documentId={1}
        categories={[{ id: 2, nom: "Factures" }]}
        onFermer={() => {}}
      />,
    );

    await waitFor(() => expect(screen.getAllByRole("button").length).toBeGreaterThan(1));
    const lignes = screen.getAllByRole("button");
    await utilisateur.click(lignes[lignes.length - 1]);

    expect(screen.getByText("Factures")).toBeDefined();
  });
});

describe("historique volumineux", () => {
  const beaucoup = Array.from({ length: 26 }, (_, i) => ({
    id: i + 1,
    date_evenement: `2026-09-04T10:${String(i).padStart(2, "0")}:00`,
    auteur: "marie@foyer.fr",
    action: "document.modification",
    details: { avant: { titulaire: null }, apres: { titulaire: `Membre ${i}` } },
  }));

  beforeEach(() => {
    global.fetch = vi.fn(async (url) => {
      const decalage = Number(new URL(url, "http://x").searchParams.get("decalage") || 0);
      const limite = Number(new URL(url, "http://x").searchParams.get("limite") || 10);
      return new Response(JSON.stringify({
        total: beaucoup.length,
        evenements: beaucoup.slice(decalage, decalage + limite),
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
  });

  it("annonce le total et pagine au-delà d'une page", async () => {
    render(<HistoriqueDocument documentId={1} onFermer={() => {}} />);

    await waitFor(() => expect(screen.getByText(/26 événements/)).toBeDefined());
    expect(screen.getByLabelText("Page suivante")).toBeDefined();
    expect(screen.getByText("1–10 sur 26")).toBeDefined();
  });

  it("change de page sans perdre le compte", async () => {
    const utilisateur = userEvent.setup();
    render(<HistoriqueDocument documentId={1} onFermer={() => {}} />);

    await waitFor(() => expect(screen.getByLabelText("Page suivante")).toBeDefined());
    await utilisateur.click(screen.getByLabelText("Page suivante"));

    await waitFor(() => expect(screen.getByText("11–20 sur 26")).toBeDefined());
    expect(screen.getByText(/26 événements/)).toBeDefined();
  });
});

describe("plusieurs détails ouverts", () => {
  const deux = [
    {
      id: 2, date_evenement: "2026-09-04T15:00:00", auteur: "marie@foyer.fr",
      action: "document.modification",
      details: { avant: { categorie: "Factures" }, apres: { categorie: "Impôts" } },
    },
    {
      id: 1, date_evenement: "2026-09-04T14:00:00", auteur: "jean@foyer.fr",
      action: "document.modification",
      details: { avant: { titulaire: null }, apres: { titulaire: "Léa Dupont" } },
    },
  ];

  beforeEach(() => {
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify({ total: deux.length, evenements: deux }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  });

  // Une fois la ligne ouverte, le nom du champ apparaît deux fois — dans le
  // résumé et dans le tableau du détail. On vise donc les lignes par leur état
  // d'ouverture, qui est porté par `aria-expanded`, plutôt que par leur texte.
  const lignesFermees = () => screen.getAllByRole("button", { expanded: false });

  it("garde ouverte la ligne précédente quand on en déroule une autre", async () => {
    const utilisateur = userEvent.setup();
    render(<HistoriqueDocument documentId={1} onFermer={() => {}} />);

    await waitFor(() => expect(lignesFermees()).toHaveLength(2));
    await utilisateur.click(lignesFermees()[0]);
    expect(screen.getByText("Impôts")).toBeDefined();

    await utilisateur.click(lignesFermees()[0]);   // la seule encore fermée
    // la seconde s'ouvre… et la première ne s'est pas refermée
    expect(screen.getByText("Léa Dupont")).toBeDefined();
    expect(screen.getByText("Impôts")).toBeDefined();
    expect(screen.getAllByRole("button", { expanded: true })).toHaveLength(2);
  });

  it("referme celle sur laquelle on reclique, et elle seule", async () => {
    const utilisateur = userEvent.setup();
    render(<HistoriqueDocument documentId={1} onFermer={() => {}} />);

    await waitFor(() => expect(lignesFermees()).toHaveLength(2));
    await utilisateur.click(lignesFermees()[0]);
    await utilisateur.click(lignesFermees()[0]);

    const ouvertes = screen.getAllByRole("button", { expanded: true });
    await utilisateur.click(ouvertes[0]);

    expect(screen.queryByText("Impôts")).toBeNull();
    expect(screen.getByText("Léa Dupont")).toBeDefined();
  });
});
