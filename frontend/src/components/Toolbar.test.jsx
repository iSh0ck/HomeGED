import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import Toolbar from "./Toolbar.jsx";

/**
 * Ce que la barre du registre propose, et à qui (§22.82).
 *
 * Le bouton « Exporter » regardait `est_admin` alors que l'API, elle, vérifie le
 * droit `exporter_selection`. On pouvait donc accorder ce droit à un compte qui
 * ne voyait jamais le bouton — le droit existait, il ne servait à rien. Masquer
 * un bouton ne protège de rien : le contrôle reste côté serveur. Ce que ces
 * tests fixent, c'est que les deux disent la même chose.
 */
describe("barre du registre", () => {
  const rendre = (user) => render(
    <Toolbar
      total={3}
      user={user}
      onExporter={() => {}}
      onOuvrirCompte={() => {}}
      onLogout={() => {}}
      onOuvrirAdmin={() => {}}
      onActualiser={() => {}}
    />,
  );

  const bouton = () => screen.queryByTitle(/Sortir ces documents dans une archive/);

  it("propose l'export à qui porte le droit, administrateur ou non", () => {
    rendre({ nom: "Camille", est_admin: false, droits: ["exporter_selection"] });
    expect(bouton()).not.toBeNull();
  });

  it("ne le propose pas à qui ne le porte pas", () => {
    rendre({ nom: "Camille", est_admin: false, droits: ["analyser"] });
    expect(bouton()).toBeNull();
  });

  it("le propose à un administrateur, qui porte tous les droits généraux", () => {
    // `/moi` rend la liste complète pour un administrateur : la barre n'a pas à
    // traiter ce cas à part.
    rendre({ nom: "Admin", est_admin: true, droits: ["exporter_selection", "comptes"] });
    expect(bouton()).not.toBeNull();
  });

  it("ne suppose rien d'un compte dont les droits n'ont pas encore été lus", () => {
    rendre({ nom: "Camille", est_admin: true });
    expect(bouton()).toBeNull();
  });
});
