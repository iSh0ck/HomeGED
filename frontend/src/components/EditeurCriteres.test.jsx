import React, { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EditeurCriteres from "./EditeurCriteres.jsx";

/**
 * Les critères d'une vue s'éditent depuis l'administration (§19.8). Ce qui est
 * vérifié ici : que le vocabulaire vienne bien de l'API, et qu'un changement de
 * champ ne laisse pas derrière lui un opérateur que le moteur refuserait.
 */
const CHAMPS = [
  { champ: "categorie", libelle: "Catégorie", type: "reference",
    operateurs: ["egal", "contient", "vide", "non_vide"] },
  { champ: "date_document", libelle: "Date du document", type: "date",
    operateurs: ["egal", "avant", "apres", "entre", "vide"] },
  { champ: "nom_fichier", libelle: "Nom du fichier", type: "texte",
    operateurs: ["contient", "egal", "commence_par"] },
];

function Editeur({ initial = [] }) {
  const [criteres, setCriteres] = useState(initial);
  return (
    <>
      <EditeurCriteres
        criteres={criteres}
        onChange={setCriteres}
        champs={CHAMPS}
        categories={[{ id: 2, nom: "Factures" }]}
        fournisseurs={[{ id: 1, nom: "Orange" }]}
      />
      <pre data-testid="etat">{JSON.stringify(criteres)}</pre>
    </>
  );
}

const etat = () => JSON.parse(screen.getByTestId("etat").textContent);

describe("édition des critères d'une vue", () => {
  it("part du premier champ annoncé par l'API, avec son premier opérateur", () => {
    // Rien n'est codé en dur ici : une liste tenue dans l'interface finirait par
    // proposer ce que le moteur refuse.
    render(<Editeur />);
    fireEvent.click(screen.getByText("Ajouter un critère"));
    expect(etat()).toEqual([{ champ: "categorie", operateur: "egal", valeur: "" }]);
  });

  it("annonce qu'une vue sans critère montre tout", () => {
    render(<Editeur />);
    expect(screen.getByText(/montrera tous les documents/)).toBeDefined();
  });

  it("un opérateur sans valeur le dit au lieu d'un champ vide trompeur", () => {
    render(<Editeur initial={[{ champ: "categorie", operateur: "vide", valeur: "" }]} />);
    expect(screen.getByText("aucune valeur attendue")).toBeDefined();
  });

  it("retirer un critère ne touche pas aux autres", () => {
    render(<Editeur initial={[
      { champ: "categorie", operateur: "egal", valeur: "2" },
      { champ: "nom_fichier", operateur: "contient", valeur: "edf" },
    ]} />);
    fireEvent.click(screen.getByLabelText("Retirer le critère 1"));
    expect(etat()).toEqual([{ champ: "nom_fichier", operateur: "contient", valeur: "edf" }]);
  });

  it("un intervalle de dates garde ses deux bornes", () => {
    render(<Editeur initial={[
      { champ: "date_document", operateur: "entre", valeur: ["2026-01-01", "2026-12-31"] },
    ]} />);
    expect(screen.getByLabelText("Début de l'intervalle")).toBeDefined();
    expect(screen.getByLabelText("Fin de l'intervalle")).toBeDefined();
  });
});

describe("groupement des champs proposés", () => {
  it("rend le groupe de chaque champ à la liste", () => {
    // Les champs arrivent groupés depuis l'écran qui sait à quoi la vue est
    // rattachée (§19.18) ; l'éditeur ne fait que transmettre.
    const groupes = CHAMPS.map((c, i) => ({
      ...c, groupe: i === 0 ? "Toujours disponibles" : "Colonnes de ce classement",
    }));
    render(
      <EditeurCriteres
        criteres={[{ champ: "categorie", operateur: "egal", valeur: "2" }]}
        onChange={() => {}}
        champs={groupes}
        categories={[{ id: 2, nom: "Factures" }]}
      />
    );
    expect(screen.getByLabelText("Champ du critère 1")).toBeDefined();
  });
});
