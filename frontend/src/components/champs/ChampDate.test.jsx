import React, { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ChampDate from "./ChampDate.jsx";
import { versIso, versFrancais } from "./dates";

describe("conversion des dates", () => {
  it("refuse une date qui n'existe pas au lieu de la décaler", () => {
    // `new Date(2026, 1, 31)` rendrait le 3 mars sans rien dire : c'est
    // exactement le genre de silence qui fait enregistrer une mauvaise date.
    expect(versIso("31/02/2026")).toBe("");
    expect(versIso("29/02/2026")).toBe("");
    expect(versIso("29/02/2024")).toBe("2024-02-29");
  });

  it("parle ISO à l'API et français à l'écran", () => {
    expect(versIso("04/09/2026")).toBe("2026-09-04");
    expect(versFrancais("2026-09-04")).toBe("04/09/2026");
  });
});

describe("champ de date", () => {
  it("accepte la saisie au clavier et pose les barres obliques", async () => {
    const utilisateur = userEvent.setup();
    const surChangement = vi.fn();
    render(<ChampDate valeur="" onChange={surChangement} />);

    await utilisateur.type(screen.getByRole("textbox"), "04092026");

    expect(screen.getByRole("textbox")).toHaveValue("04/09/2026");
    expect(surChangement).toHaveBeenLastCalledWith("2026-09-04");
  });

  it("ouvre le calendrier et rend la date choisie au format de l'API", async () => {
    const utilisateur = userEvent.setup();
    const surChangement = vi.fn();
    render(<ChampDate valeur="2026-09-04" onChange={surChangement} />);

    await utilisateur.click(screen.getByLabelText("Ouvrir le calendrier"));
    expect(screen.getByRole("dialog", { name: "Calendrier" })).toBeDefined();

    await utilisateur.click(screen.getByRole("button", { name: "12" }));
    expect(surChangement).toHaveBeenLastCalledWith("2026-09-12");
  });

  it("laisse choisir un mois puis une année sans faire défiler douze fois", async () => {
    const utilisateur = userEvent.setup();
    render(<ChampDate valeur="2026-09-04" onChange={() => {}} />);

    await utilisateur.click(screen.getByLabelText("Ouvrir le calendrier"));
    await utilisateur.click(screen.getByRole("button", { name: "Choisir un mois" }));
    expect(screen.getByRole("button", { name: "janv." })).toBeDefined();

    await utilisateur.click(screen.getByRole("button", { name: "Choisir une année" }));
    expect(screen.getByRole("button", { name: "2020" })).toBeDefined();
  });

  it("revient à la valeur connue quand la saisie reste incomplète", async () => {
    const utilisateur = userEvent.setup();
    function Cadre() {
      const [valeur] = useState("2026-09-04");
      return <ChampDate valeur={valeur} onChange={() => {}} />;
    }
    render(<Cadre />);
    const champ = screen.getByRole("textbox");

    await utilisateur.clear(champ);
    await utilisateur.type(champ, "04/09");
    await utilisateur.tab();

    expect(champ).toHaveValue("04/09/2026");
  });
});
