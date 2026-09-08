import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import BarriereErreur from "./BarriereErreur.jsx";

/**
 * Barrière d'erreur.
 *
 * Ce qu'elle remplace : la page blanche. Trois fois sur ce projet, une exception
 * pendant le rendu a emporté l'application entière, et le symptôme rapporté a
 * toujours été le même — « plus rien ne charge ». Ces tests vérifient donc
 * qu'il reste quelque chose à lire, et quelque chose à cliquer.
 */
describe("barrière d'erreur", () => {
  beforeEach(() => {
    // React écrit lui-même l'erreur attrapée : sans ce silence, la sortie des
    // tests ressemble à un échec alors que tout se passe comme prévu.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  function Casse({ quand = true }) {
    if (quand) throw new Error("colonne introuvable");
    return <div>écran rétabli</div>;
  }

  it("laisse un message et le détail technique plutôt qu'une page blanche", () => {
    render(
      <BarriereErreur titre="Le registre s'est interrompu">
        <Casse />
      </BarriereErreur>,
    );
    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText("Le registre s'est interrompu")).toBeDefined();
    expect(screen.getByText(/colonne introuvable/)).toBeDefined();
    expect(screen.getByText(/vos documents sont en base/)).toBeDefined();
  });

  it("n'entoure rien tant que tout va bien", () => {
    const { container } = render(
      <BarriereErreur><div id="contenu">le registre</div></BarriereErreur>,
    );
    // Aucune enveloppe : la mise en page du parent reste intacte, ce qui est la
    // condition pour poser la barrière partout sans rien déplacer.
    expect(container.firstChild.id).toBe("contenu");
  });

  it("permet de réessayer, et l'écran revient s'il refonctionne", () => {
    function Ecran() {
      const [casse, setCasse] = React.useState(true);
      // le bouton « Réessayer » remonte les enfants : on simule une cause qui a
      // disparu entre-temps
      React.useEffect(() => { setCasse(false); }, []);
      return (
        <BarriereErreur titre="Interrompu">
          <Casse quand={casse} />
        </BarriereErreur>
      );
    }
    render(<Ecran />);
    expect(screen.getByText("Interrompu")).toBeDefined();
    fireEvent.click(screen.getByText("Réessayer"));
    expect(screen.getByText("écran rétabli")).toBeDefined();
  });

  it("propose de revenir à l'accueil quand on lui dit comment", () => {
    const retours = [];
    render(
      <BarriereErreur titre="Interrompu" onReprendre={() => retours.push(1)}>
        <Casse />
      </BarriereErreur>,
    );
    fireEvent.click(screen.getByText("Revenir à l'accueil"));
    expect(retours).toHaveLength(1);
  });
});
