import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AlerteModale from "./AlerteModale.jsx";

describe("fenêtre d'alerte", () => {
  const rendre = (proprietes = {}) => {
    const onFermer = vi.fn();
    render(<AlerteModale titre="Connexion refusée" message="Email ou mot de passe incorrect"
                         onFermer={onFermer} {...proprietes} />);
    return onFermer;
  };

  it("s'annonce comme une alerte, avec son titre et son message", () => {
    rendre();
    const fenetre = screen.getByRole("alertdialog", { name: "Connexion refusée" });
    expect(fenetre).toBeDefined();
    expect(screen.getByText("Email ou mot de passe incorrect")).toBeDefined();
  });

  it("se ferme par le bouton OK, qui a le focus d'emblée", async () => {
    const utilisateur = userEvent.setup();
    const onFermer = rendre();

    const bouton = screen.getByRole("button", { name: "OK" });
    expect(document.activeElement).toBe(bouton);

    await utilisateur.click(bouton);
    expect(onFermer).toHaveBeenCalled();
  });

  it("se ferme aussi à la touche Échap", async () => {
    const utilisateur = userEvent.setup();
    const onFermer = rendre();

    await utilisateur.keyboard("{Escape}");
    // un message qu'on ne peut pas fermer est une impasse, pas une information
    expect(onFermer).toHaveBeenCalled();
  });
});
