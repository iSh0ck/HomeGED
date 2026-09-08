import React from "react";
import { describe, expect, it, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { renderHook, act } from "@testing-library/react";

import { PoigneeMetadonnees, useLargeurMetadonnees } from "./LargeurMetadonnees.jsx";

/**
 * La colonne des métadonnées, qu'on élargit à la souris (§22.69).
 *
 * jsdom ne calcule aucune mise en page : ce qu'il peut affirmer, et qui suffit à
 * empêcher la régression, c'est que le geste déplace bien la largeur, dans le
 * bon sens, entre ses bornes — et qu'elle se retrouve d'une session à l'autre.
 */
describe("largeur des métadonnées", () => {
  beforeEach(() => window.localStorage.removeItem("homeged.largeurMetadonnees"));

  const tirer = (resultat, de, vers) => {
    act(() => resultat.current.commencer({
      preventDefault: () => {}, clientX: de,
    }));
    act(() => { fireEvent.mouseMove(window, { clientX: vers }); });
    act(() => { fireEvent.mouseUp(window); });
  };

  it("part de 380 px et s'élargit quand on tire vers la gauche", () => {
    const { result } = renderHook(() => useLargeurMetadonnees());
    expect(result.current.largeur).toBe(380);

    // La colonne est ancrée à droite : tirer le trait vers la gauche l'élargit.
    tirer(result, 800, 700);
    expect(result.current.largeur).toBe(480);
  });

  it("se rétrécit quand on tire vers la droite, sans passer sous son minimum", () => {
    const { result } = renderHook(() => useLargeurMetadonnees());
    tirer(result, 800, 900);
    expect(result.current.largeur).toBe(280);

    tirer(result, 800, 1600);
    expect(result.current.largeur).toBe(240);   // borné : une colonne illisible ne sert à rien
  });

  it("se retrouve à la session suivante, et se rend d'un double-clic", () => {
    const premier = renderHook(() => useLargeurMetadonnees());
    tirer(premier.result, 800, 640);
    expect(premier.result.current.largeur).toBe(540);

    // Un autre montage relit ce qui a été rangé : c'est un confort de poste.
    const second = renderHook(() => useLargeurMetadonnees());
    expect(second.result.current.largeur).toBe(540);

    act(() => second.result.current.oublier());
    expect(second.result.current.largeur).toBe(380);
  });

  it("porte un trait qu'on peut viser à la souris", () => {
    render(<PoigneeMetadonnees commencer={() => {}} oublier={() => {}} />);
    const trait = screen.getByRole("separator");
    // Viser une bordure d'un pixel est un exercice, pas un geste.
    expect(Number.parseInt(trait.style.width, 10)).toBeGreaterThanOrEqual(7);
    expect(trait.style.cursor).toBe("col-resize");
  });
});
