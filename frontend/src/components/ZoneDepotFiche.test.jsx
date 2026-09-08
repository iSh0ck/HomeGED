import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ZoneDepotFiche from "./ZoneDepotFiche.jsx";

/** Ce que la zone a envoyé au serveur : l'URL, et le fichier du multipart. */
let envois;

beforeEach(() => {
  envois = [];
  global.fetch = vi.fn(async (url, options) => {
    envois.push({ url: String(url), fichier: options?.body?.get?.("fichier") });
    return new Response(JSON.stringify({ ok: true, job_id: 12, categorie: "Actes" }),
                        { status: 200, headers: { "Content-Type": "application/json" } });
  });
});

const fichier = (nom = "acte.pdf") =>
  new File([new Uint8Array([1, 2, 3])], nom, { type: "application/pdf" });

describe("dépôt à la main dans une fiche simple", () => {
  it("dit où l'on est et ce qu'on peut y faire", () => {
    render(<ZoneDepotFiche categorieId={4} nom="Actes" />);
    expect(screen.getByText(/Glissez un fichier ici pour l'ajouter à « Actes »/)).toBeDefined();
  });

  it("envoie le fichier choisi à la fiche ouverte", async () => {
    const depose = vi.fn();
    render(<ZoneDepotFiche categorieId={4} nom="Actes" onDepose={depose} />);

    await userEvent.upload(screen.getByLabelText(/Ajouter un document à « Actes »/),
                           fichier("acte notarié.pdf"));

    await waitFor(() => expect(envois).toHaveLength(1));
    expect(envois[0].url).toContain("/fiches/4/documents");
    expect(envois[0].fichier.name).toBe("acte notarié.pdf");
    // le document n'existe pas encore : le serveur de travaux doit le lire
    expect(await screen.findByText(/apparaîtra ici dans quelques secondes/)).toBeDefined();
    expect(depose).toHaveBeenCalled();
  });

  it("montre le refus du serveur plutôt que de laisser croire au succès", async () => {
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify({ detail: "Format non pris en charge (attendu : .pdf)." }),
      { status: 422, headers: { "Content-Type": "application/json" } }));
    const depose = vi.fn();
    render(<ZoneDepotFiche categorieId={4} nom="Actes" onDepose={depose} />);

    await userEvent.upload(screen.getByLabelText(/Ajouter un document à « Actes »/),
                           new File(["x"], "notes.txt", { type: "text/plain" }));

    expect(await screen.findByText(/Format non pris en charge/)).toBeDefined();
    expect(depose).not.toHaveBeenCalled();
  });

  it("accepte plusieurs fichiers d'un coup", async () => {
    render(<ZoneDepotFiche categorieId={4} nom="Actes" />);

    await userEvent.upload(screen.getByLabelText(/Ajouter un document à « Actes »/),
                           [fichier("un.pdf"), fichier("deux.pdf")]);

    await waitFor(() => expect(envois).toHaveLength(2));
    expect(await screen.findByText(/2 documents reçus/)).toBeDefined();
  });
});
