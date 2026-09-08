import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import Modal from "./Modal.jsx";

/**
 * Fermeture d'une fenêtre au clic sur le voile (§18.21).
 *
 * Le défaut signalé : sélectionner du texte dans un champ, relâcher le bouton
 * un peu trop loin, et la fenêtre se refermait avec la saisie en cours. Le
 * navigateur émet en effet un `click` sur l'ancêtre commun des deux extrémités
 * du geste — ici le voile — même si le geste a commencé dans la fenêtre.
 */
describe("fenêtre modale", () => {
  const rendre = (onClose) => {
    const rendu = render(
      <Modal titre="Une fenêtre" onClose={onClose}>
        <input aria-label="saisie" defaultValue="du texte à sélectionner" />
      </Modal>,
    );
    return { rendu, voile: screen.getByRole("dialog") };
  };

  it("se ferme quand le clic commence et finit sur le voile", () => {
    const onClose = vi.fn();
    const { voile } = rendre(onClose);
    fireEvent.mouseDown(voile);
    fireEvent.click(voile);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("reste ouverte quand le geste a commencé dans la fenêtre", () => {
    const onClose = vi.fn();
    const { voile } = rendre(onClose);
    // on attrape un mot dans le champ…
    fireEvent.mouseDown(screen.getByLabelText("saisie"));
    // …et on relâche hors de la fenêtre : le `click` remonte alors au voile
    fireEvent.click(voile);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("reste ouverte au clic dans son propre contenu", () => {
    const onClose = vi.fn();
    rendre(onClose);
    fireEvent.click(screen.getByLabelText("saisie"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("se ferme par son bouton de fermeture", () => {
    const onClose = vi.fn();
    rendre(onClose);
    fireEvent.click(screen.getByRole("button"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
