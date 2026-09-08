import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App.jsx";
import { AuthProvider } from "./auth/AuthContext.jsx";

/**
 * Le test le plus simple, et celui qui aurait évité trois écrans blancs : est-ce
 * que l'application se monte ? Un import oublié, un composant renommé, une API
 * de React qui change de version majeure — tout cela échoue ici plutôt que chez
 * l'utilisateur.
 */
describe("montage de l'application", () => {
  beforeEach(() => {
    // Personne n'est connecté : l'API répond 401 à la reprise de session.
    global.fetch = vi.fn(async () => new Response("{}", { status: 401 }));
  });

  it("affiche l'écran de connexion quand aucune session n'existe", async () => {
    render(<AuthProvider><App /></AuthProvider>);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Se connecter" })).toBeDefined();
    });
    expect(screen.getByLabelText(/Adresse e-mail/i)).toBeDefined();
    expect(screen.getByText(/Le classeur du foyer/)).toBeDefined();
  });
});

describe("erreur de connexion", () => {
  it("annonce un refus d'authentification dans une fenêtre à acquitter", async () => {
    const utilisateur = userEvent.setup();
    global.fetch = vi.fn(async (url, options) => {
      if (String(url).includes("/auth/login") && options?.method === "POST") {
        return new Response(JSON.stringify({ detail: "Email ou mot de passe incorrect" }),
                            { status: 401, headers: { "Content-Type": "application/json" } });
      }
      return new Response("{}", { status: 401 });
    });

    render(<AuthProvider><App /></AuthProvider>);
    await waitFor(() => expect(screen.getByRole("button", { name: "Se connecter" })).toBeDefined());

    await utilisateur.type(screen.getByLabelText(/Adresse e-mail/i), "marie@foyer.fr");
    await utilisateur.type(screen.getByLabelText("Mot de passe"), "mauvais");
    await utilisateur.click(screen.getByRole("button", { name: "Se connecter" }));

    const fenetre = await screen.findByRole("alertdialog");
    expect(fenetre.textContent).toContain("Email ou mot de passe incorrect");

    await utilisateur.click(screen.getByRole("button", { name: "OK" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});
