import React from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("../api", () => ({
  api: {
    // Le Centre d'analyse répond par page depuis le §22.43 : la liste et son
    // total, comme le registre.
    analyse: vi.fn(() => Promise.resolve({ documents: [], total: 0 })),
    aClasser: vi.fn(() => Promise.resolve([])),
    references: vi.fn(() => Promise.resolve([])),
  },
}));

import { api } from "../api";
import AnalysePage from "./AnalysePage.jsx";

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => vi.useRealTimers());

describe("le centre d'analyse", () => {
  it("se tient à jour tout seul", async () => {
    // C'est le seul écran qui attend quelque chose du serveur de travaux : un
    // dépôt met quelques secondes à devenir un document, et l'on restait devant
    // une liste vide sans savoir s'il fallait patienter ou recharger (§22.32).
    render(<AnalysePage categories={[]} onRetour={() => {}} />);
    await waitFor(() => expect(api.analyse).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(10000);
    await waitFor(() => expect(api.analyse).toHaveBeenCalledTimes(2));
    expect(api.aClasser).toHaveBeenCalledTimes(2);
  });

  it("ne relève rien quand l'onglet est en arrière-plan", async () => {
    render(<AnalysePage categories={[]} onRetour={() => {}} />);
    await waitFor(() => expect(api.analyse).toHaveBeenCalledTimes(1));

    // une GED ouverte dans un onglet oublié n'a pas à réveiller le serveur
    const cache = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    await vi.advanceTimersByTimeAsync(30000);
    expect(api.analyse).toHaveBeenCalledTimes(1);
    cache.mockRestore();
  });

  it("le relevé ne remet pas l'écran en chargement", async () => {
    render(<AnalysePage categories={[]} onRetour={() => {}} />);
    await waitFor(() => expect(api.analyse).toHaveBeenCalledTimes(1));
    // l'écran d'attente ne doit pas revenir sous les doigts de qui lit la liste
    await waitFor(() => expect(screen.queryByText(/Chargement/)).toBeNull());

    await vi.advanceTimersByTimeAsync(10000);
    expect(screen.queryByText(/Chargement/)).toBeNull();
  });
});
