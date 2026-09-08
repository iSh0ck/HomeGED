import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ExporterSelection from "./ExporterSelection.jsx";
import { ajouterModele } from "../lib/modelesExport";

/**
 * Les modèles d'arborescence gardés (§22.83), et la façon de les retrouver
 * (§22.84).
 *
 * Une pile sous le formulaire se lisait tant qu'il y en avait trois ; à douze,
 * elle poussait l'aperçu et le bouton hors de vue. Ils tiennent dans un menu.
 */
describe("fenêtre d'export d'une sélection", () => {
  beforeEach(() => {
    window.localStorage.removeItem("homeged.modelesExport");
    global.fetch = vi.fn(async (url) => {
      const chemin = String(url);
      const json = (corps) => new Response(JSON.stringify(corps),
        { status: 200, headers: { "Content-Type": "application/json" } });
      if (chemin.includes("/exports-modele/trous")) {
        return json({ trous: { annee: "L'année du document" },
                      modele_dossier: "{annee}/{type}", modele_nom: "{nom_fichier}" });
      }
      if (chemin.includes("/exports-modele/apercu")) {
        return json({ total: 9, exemples: ["2026/Factures/edf.pdf"] });
      }
      return json([]);   // la liste des demandes
    });
  });

  const rendre = () => render(
    <ExporterSelection criteres={[]} categorieId={2} onFermer={() => {}} />,
  );

  it("propose de garder le modèle réglé, une fois l'aperçu connu", async () => {
    rendre();
    expect(await screen.findByTitle(/Retrouver ce réglage la prochaine fois/)).toBeDefined();
  });

  it("ne propose plus de garder ce qui l'est déjà", async () => {
    ajouterModele({ dossier: "{annee}/{type}", nom: "{nom_fichier}",
                    exemple: "2026/Factures/edf.pdf" });
    rendre();
    await screen.findByLabelText("Modèles gardés");
    expect(screen.queryByTitle(/Retrouver ce réglage la prochaine fois/)).toBeNull();
  });

  it("range les modèles gardés dans un menu, et non en pile", async () => {
    // À douze modèles, une pile pousse l'aperçu hors de vue.
    for (const rang of [1, 2, 3]) {
      ajouterModele({ dossier: `{annee}/${rang}`, nom: "{nom_fichier}",
                      exemple: `2026/${rang}/edf.pdf` });
    }
    rendre();
    const menu = await screen.findByLabelText("Modèles gardés");
    expect(menu).toBeDefined();
    // Rien n'est déployé tant qu'on ne l'ouvre pas.
    expect(screen.queryByText(/2026\/2\/edf\.pdf/)).toBeNull();
  });

  it("reprend le modèle choisi, et l'oublie quand on le demande", async () => {
    const utilisateur = userEvent.setup();
    ajouterModele({ dossier: "{type}", nom: "{champ:emetteur}",
                    exemple: "Factures/EDF.pdf" });
    rendre();

    await utilisateur.click(await screen.findByLabelText("Modèles gardés"));
    await utilisateur.click(await screen.findByText(/Factures\/EDF\.pdf/));
    await waitFor(() => expect(
      screen.getByLabelText("Modèle de dossiers").value).toBe("{type}"));

    // On n'oublie que ce qu'on a sous les yeux : le modèle en cours.
    await utilisateur.click(screen.getByLabelText("Oublier ce modèle"));
    await waitFor(() => expect(screen.queryByLabelText("Modèles gardés")).toBeNull());
  });
});
