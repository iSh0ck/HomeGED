import React, { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import AdminTable from "./AdminTable.jsx";
import { deplacer } from "./Reordonnable.jsx";

/**
 * Le glisser-déposer remplace deux flèches par ligne (§18.46). Ce qu'on
 * surveille ici : qu'il déplace bien à l'endroit lâché, qu'il reste utilisable
 * au clavier, et qu'il ne fasse pas sauter un élément d'un groupe à l'autre.
 */

const TRANSFERT = () => ({ setData: vi.fn(), dropEffect: "", effectAllowed: "" });

function poignees() {
  return screen.getAllByTitle("Glisser pour déplacer — ou flèches haut et bas");
}

function lignes() {
  return screen.getAllByRole("row").slice(1);   // la première est l'en-tête
}

function Tableau({ onDeplacer, groupeDe }) {
  const donnees = [
    { id: 1, nom: "Alpha", groupe: "a" },
    { id: 2, nom: "Bravo", groupe: "a" },
    { id: 3, nom: "Charlie", groupe: "a" },
    { id: 4, nom: "Delta", groupe: "b" },
  ];
  return (
    <AdminTable
      lignes={donnees}
      colonnes={[{ key: "nom", label: "Nom" }]}
      reordonnable={{
        onDeplacer,
        groupeDe: groupeDe ?? ((index) => donnees[index].groupe),
        libelleDe: (l) => l.nom,
      }}
    />
  );
}

describe("deplacer", () => {
  it("déplace l'élément à la place visée, sans permuter les deux", () => {
    // Une permutation donnerait ["d","b","c","a"] : ce n'est pas ce qu'on voit
    // quand on lâche un élément trois rangs plus bas.
    expect(deplacer(["a", "b", "c", "d"], 0, 3)).toEqual(["b", "c", "d", "a"]);
  });

  it("laisse la liste d'origine intacte", () => {
    const origine = ["a", "b"];
    deplacer(origine, 0, 1);
    expect(origine).toEqual(["a", "b"]);
  });
});

describe("réordonner par glisser-déposer", () => {
  it("lâcher une ligne sur une autre la déplace à cette place", () => {
    const onDeplacer = vi.fn();
    render(<Tableau onDeplacer={onDeplacer} />);

    fireEvent.dragStart(poignees()[0], { dataTransfer: TRANSFERT() });
    fireEvent.dragOver(lignes()[2], { dataTransfer: TRANSFERT() });
    fireEvent.drop(lignes()[2], { dataTransfer: TRANSFERT() });

    expect(onDeplacer).toHaveBeenCalledWith(0, 2);
  });

  it("refuse le dépôt dans un autre groupe", () => {
    const onDeplacer = vi.fn();
    render(<Tableau onDeplacer={onDeplacer} />);

    fireEvent.dragStart(poignees()[0], { dataTransfer: TRANSFERT() });
    fireEvent.drop(lignes()[3], { dataTransfer: TRANSFERT() });

    expect(onDeplacer).not.toHaveBeenCalled();
  });

  it("ne déplace rien quand on lâche une ligne sur elle-même", () => {
    const onDeplacer = vi.fn();
    render(<Tableau onDeplacer={onDeplacer} />);

    fireEvent.dragStart(poignees()[1], { dataTransfer: TRANSFERT() });
    fireEvent.drop(lignes()[1], { dataTransfer: TRANSFERT() });

    expect(onDeplacer).not.toHaveBeenCalled();
  });

  it("les flèches du clavier font le même travail que le glissement", () => {
    // Sans cela, régler l'ordre deviendrait impossible sans souris.
    const onDeplacer = vi.fn();
    render(<Tableau onDeplacer={onDeplacer} />);

    fireEvent.keyDown(poignees()[1], { key: "ArrowUp" });
    expect(onDeplacer).toHaveBeenCalledWith(1, 0);

    fireEvent.keyDown(poignees()[1], { key: "ArrowDown" });
    expect(onDeplacer).toHaveBeenLastCalledWith(1, 2);
  });

  it("le clavier s'arrête aux bornes du groupe", () => {
    const onDeplacer = vi.fn();
    render(<Tableau onDeplacer={onDeplacer} />);

    fireEvent.keyDown(poignees()[0], { key: "ArrowUp" });       // déjà en haut
    fireEvent.keyDown(poignees()[2], { key: "ArrowDown" });     // dernier de son groupe
    expect(onDeplacer).not.toHaveBeenCalled();
  });

  it("la poignée nomme ce qu'elle déplace", () => {
    render(<Tableau onDeplacer={() => {}} />);
    expect(screen.getByLabelText("Déplacer Charlie")).toBeInTheDocument();
  });

  it("un tableau ordinaire n'a ni poignée ni colonne supplémentaire", () => {
    render(
      <AdminTable lignes={[{ id: 1, nom: "Alpha" }]} colonnes={[{ key: "nom", label: "Nom" }]} />
    );
    expect(screen.queryByTitle("Glisser pour déplacer — ou flèches haut et bas")).toBeNull();
  });

  it("le déplacement se voit à l'écran pendant qu'on tire", () => {
    function Liste() {
      const [ordre, setOrdre] = useState(["Alpha", "Bravo"]);
      return (
        <AdminTable
          lignes={ordre.map((nom, i) => ({ id: i + 1, nom }))}
          colonnes={[{ key: "nom", label: "Nom" }]}
          reordonnable={{ onDeplacer: (de, vers) => setOrdre(deplacer(ordre, de, vers)) }}
        />
      );
    }
    render(<Liste />);
    fireEvent.keyDown(poignees()[1], { key: "ArrowUp" });
    expect(lignes()[0]).toHaveTextContent("Bravo");
  });
});
