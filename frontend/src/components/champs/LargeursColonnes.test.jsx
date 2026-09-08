import React from "react";
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import AdminTable from "../AdminTable.jsx";

const COLONNES = [{ key: "nom", label: "Nom" }, { key: "etat", label: "État" }];
const LIGNES = [{ id: 1, nom: "Facture", etat: "Active" }];

beforeEach(() => window.localStorage.clear());

describe("des colonnes qu'on élargit à la souris", () => {
  it("offre une poignée par colonne", () => {
    render(<AdminTable cle="essai" colonnes={COLONNES} lignes={LIGNES} />);

    expect(screen.getByLabelText("Ajuster la largeur de la colonne nom")).toBeDefined();
    expect(screen.getByLabelText("Ajuster la largeur de la colonne etat")).toBeDefined();
  });

  it("retient la largeur d'une visite à l'autre", () => {
    const { unmount } = render(
      <AdminTable cle="essai" colonnes={COLONNES} lignes={LIGNES} />);

    const poignee = screen.getByLabelText("Ajuster la largeur de la colonne nom");
    fireEvent.mouseDown(poignee, { clientX: 100 });
    fireEvent.mouseMove(window, { clientX: 260 });
    fireEvent.mouseUp(window);

    // c'est un confort propre à ce poste : il se range dans le navigateur, pas
    // sur le serveur (§22.34)
    const range = JSON.parse(window.localStorage.getItem("homeged.colonnes.admin.essai"));
    expect(range.nom).toBeGreaterThan(100);

    unmount();
    render(<AdminTable cle="essai" colonnes={COLONNES} lignes={LIGNES} />);
    const entete = screen.getByText("Nom").closest("th");
    expect(entete.style.width).toBe(`${range.nom}px`);
  });

  it("un double-clic rend à la colonne sa largeur naturelle", () => {
    window.localStorage.setItem("homeged.colonnes.admin.essai", '{"nom":300}');
    render(<AdminTable cle="essai" colonnes={COLONNES} lignes={LIGNES} />);
    expect(screen.getByText("Nom").closest("th").style.width).toBe("300px");

    fireEvent.doubleClick(screen.getByLabelText("Ajuster la largeur de la colonne nom"));
    expect(screen.getByText("Nom").closest("th").style.width).toBe("");
  });

  it("ne se fie pas à ce qu'elle relit", () => {
    // un stockage bricolé à la main ne doit pas casser un tableau
    window.localStorage.setItem("homeged.colonnes.admin.essai", '{"nom":"énorme"}');
    render(<AdminTable cle="essai" colonnes={COLONNES} lignes={LIGNES} />);
    expect(screen.getByText("Nom").closest("th").style.width).toBe("");
  });
});
