import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ColumnFilter from "./ColumnFilter.jsx";

const COLONNE_STATUT = {
  key: "statut", label: "Statut", champ: "statut", filtre: "liste",
  options: [
    { value: "", label: "Tous" },
    { value: "traite", label: "Traité" },
    { value: "erreur", label: "Erreur" },
  ],
};

describe("liste de filtre d'une colonne", () => {
  beforeEach(() => {
    // L'API ne renvoie que les valeurs réellement présentes : ici, un seul
    // statut, parce que tous les documents de la vue sont traités.
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify([{ valeur: "traite", libelle: "traite", profondeur: 0 }]),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  });

  it("ne propose que les valeurs présentes dans la vue", async () => {
    const utilisateur = userEvent.setup();
    render(<ColumnFilter col={COLONNE_STATUT} filtre={null} onChange={() => {}} contexte={{}} />);

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await utilisateur.click(screen.getByRole("button"));

    const entrees = screen.getAllByRole("option").map((o) => o.textContent.trim());
    expect(entrees).toEqual(["Tous", "Traité"]);
    expect(entrees).not.toContain("Erreur");
  });

  it("interroge l\'API dans le périmètre de la vue affichée", async () => {
    render(
      <ColumnFilter
        col={COLONNE_STATUT} filtre={null} onChange={() => {}}
        contexte={{ fournisseur: { operateur: "egal", valeur: "5" } }}
        categorieId={3}
        recherche="facture"
      />,
    );
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());

    const url = decodeURIComponent(global.fetch.mock.calls[0][0]);
    expect(url).toContain("champ=statut");
    expect(url).toContain("categorie_id=3");
    expect(url).toContain("q=facture");
    expect(url).toContain('"champ":"fournisseur"');
  });
});

const COLONNE_TEXTE = { key: "emetteur", label: "Émetteur", champ: "emetteur", filtre: "texte" };

describe("suggestions d'une colonne de texte", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify([
        { valeur: "EDF", libelle: "EDF", profondeur: 0 },
        { valeur: "Orange", libelle: "Orange", profondeur: 0 },
        { valeur: "Veolia", libelle: "Veolia", profondeur: 0 },
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  });

  it("suit la souris : l'entrée survolée devient l'entrée surlignée", async () => {
    // Le surlignage marquait l'entrée choisie au clavier, et rien ne bougeait
    // à la souris : on cliquait sans savoir sur quoi (§22.56). Un seul repère,
    // qui suit celui des deux qu'on est en train d'utiliser.
    const utilisateur = userEvent.setup();
    render(<ColumnFilter col={COLONNE_TEXTE} filtre={null} onChange={() => {}} contexte={{}} />);

    await utilisateur.click(screen.getByRole("textbox"));
    const orange = await screen.findByText("Orange");

    const surlignage = (texte) => screen.getByText(texte).closest("button").style.background;
    expect(surlignage("EDF")).toContain("accent-soft");
    expect(surlignage("Orange")).toBe("transparent");

    await utilisateur.hover(orange);
    expect(surlignage("Orange")).toContain("accent-soft");
    expect(surlignage("EDF")).toBe("transparent");
  });
});
