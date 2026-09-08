import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App.jsx";
import { AuthProvider } from "./auth/AuthContext.jsx";

/**
 * Le registre de bout en bout : sélectionner, relâcher, tout décocher.
 *
 * Ces trois gestes s'articulent entre le tableau, la barre de sélection et
 * l'état tenu par `App` — trois endroits, et c'est précisément à leurs coutures
 * que se sont logés les défauts signalés. Un test au niveau des composants ne
 * les aurait pas vus : il aurait vérifié le câblage que j'écris moi-même dans le
 * test. On monte donc l'application entière, avec une API simulée.
 */

const DOCUMENTS = [
  {
    id: 1, nom_fichier: "a.pdf", date_import: "2026-07-01T10:00:00",
    fournisseur: "Orange", categorie: "Factures", categorie_id: 2,
    date_document: "2026-07-21", statut: "traite",
    metadonnees: { numero_facture: "FR-001" }, libelles_references: {},
    champs_manquants: [], champs_attendus: [],
  },
  {
    id: 2, nom_fichier: "b.pdf", date_import: "2026-07-02T10:00:00",
    fournisseur: "EDF", categorie: "Factures", categorie_id: 2,
    date_document: "2026-06-15", statut: "traite",
    metadonnees: { numero_facture: "FR-002" }, libelles_references: {},
    champs_manquants: [], champs_attendus: [],
  },
];

const COLONNES = [
  { champ: "fournisseur", libelle: "Émetteur", filtre: "reference", source: "fournisseurs" },
  { champ: "meta:numero_facture", libelle: "N° facture", filtre: "texte", type: "texte" },
  { champ: "date_document", libelle: "Émise le", filtre: "date", type: "date" },
];

function json(corps, entetes = {}) {
  return new Response(JSON.stringify(corps), {
    status: 200, headers: { "Content-Type": "application/json", ...entetes },
  });
}

/** Répond à ce dont l'application a besoin pour afficher son registre. */
function apiSimulee() {
  // Le panneau de document fabrique une URL d'objet pour afficher le PDF ;
  // jsdom n'implémente pas `createObjectURL`.
  global.URL.createObjectURL = vi.fn(() => "blob:pdf");
  global.URL.revokeObjectURL = vi.fn();

  return vi.fn(async (url) => {
    const chemin = String(url);
    if (chemin.includes("/auth/me") || chemin.includes("/moi")) {
      return json({ id: 1, email: "admin@test", nom: "Admin", est_admin: true,
                    roles: [], otp_actif: false, otp_impose: false });
    }
    if (chemin.includes("/categories/colonnes")) {
      // Forme réelle de l'API (`colonnes.toutes()`), et un défaut **plus pauvre**
      // que les colonnes du type : c'est ce qui permet de voir si l'on est
      // retombé sur « tous les documents » après avoir effacé les filtres.
      return json({ colonnes: { defaut: [COLONNES[0]], 2: COLONNES }, tris: {} });
    }
    if (chemin.includes("/categories")) {
      return json([{ id: 2, nom: "Factures", parent_id: null, ordre: 1 }]);
    }
    // Le PDF de la fiche : jsdom ne sait pas en faire grand-chose, mais la
    // requête doit aboutir pour que le panneau s'affiche.
    if (/\/documents\/\d+\/fichier/.test(chemin)) {
      return new Response(new Blob(["%PDF"]), { status: 200 });
    }
    const fiche = /\/documents\/(\d+)(\?|$)/.exec(chemin);
    if (fiche) {
      return json(DOCUMENTS.find((d) => String(d.id) === fiche[1]) || DOCUMENTS[0]);
    }
    if (chemin.includes("/documents")) return json(DOCUMENTS, { "X-Total-Count": "2" });
    if (chemin.includes("/fournisseurs")) return json([{ id: 1, nom: "Orange" }]);
    if (chemin.includes("/vues")) {
      return json([{ id: 5, nom: "Toutes les factures", categorie_id: 2, ordre: 10,
                     criteres: [{ champ: "fournisseur", operateur: "egal", valeur: "1" }],
                     partagee: true, groupement: [], modifiable: true }]);
    }
    if (chemin.includes("/analyse")) return json([]);
    // Le compteur du Centre d'analyse réunit deux appels depuis le §19.4.
    if (chemin.includes("/a-classer")) return json([]);
    // Le tableau de bord est le premier écran : sans données conformes, il lève
    // et emporte l'application entière — c'est ce que ce test a montré en
    // premier lieu.
    if (chemin.includes("/tableaux-de-bord/") && chemin.includes("/donnees")) {
      return json({ id: "accueil", nom: "Accueil", widgets: [] });
    }
    if (chemin.includes("/tableaux-de-bord")) {
      return json([{ id: "accueil", nom: "Accueil" }]);
    }
    return json({});
  });
}

async function ouvrirLeRegistre(utilisateur) {
  render(<AuthProvider><App /></AuthProvider>);
  // On arrive sur l'accueil ; on ouvre le registre en choisissant un classement
  // dans la navigation. Depuis le §21.2, la recherche n'y mène plus : elle
  // affiche ses propres résultats, qui traversent les types.
  const classement = await screen.findByText("Factures");
  await utilisateur.click(classement);
  await waitFor(() => expect(screen.getByText("Orange")).toBeDefined());
}

/**
 * L'écran affiché vient de l'adresse depuis le §18.48, et jsdom garde la même
 * adresse d'un test à l'autre : sans cette remise à zéro, un test qui ouvre le
 * registre décide de l'écran de départ du suivant.
 */
beforeEach(() => window.history.replaceState({}, "", "/"));

describe("sélection dans le registre", () => {
  beforeEach(() => { global.fetch = apiSimulee(); });

  it("retient la ligne cliquée et propose ce qu'on peut en faire", async () => {
    const utilisateur = userEvent.setup();
    await ouvrirLeRegistre(utilisateur);

    await utilisateur.click(screen.getByText("Orange"));
    expect(await screen.findByText("1 fiche sélectionnée")).toBeDefined();
    expect(screen.getByText("Modifier la fiche")).toBeDefined();
  });

  it("relâche la ligne quand on la reclique", async () => {
    const utilisateur = userEvent.setup();
    await ouvrirLeRegistre(utilisateur);

    await utilisateur.click(screen.getByText("Orange"));
    await screen.findByText("1 fiche sélectionnée");
    // La fiche ouverte porte elle aussi le nom de l'émetteur : on vise la
    // ligne, c'est-à-dire la première occurrence.
    await utilisateur.click(screen.getAllByText("Orange")[0]);
    await waitFor(() => expect(screen.queryByText("1 fiche sélectionnée")).toBeNull());
  });

  it("décocher la dernière ligne referme la fiche", async () => {
    // Le panneau restait ouvert sur un document que plus rien ne désignait, et
    // la barre d'outils disparaissait en même temps : on se retrouvait devant
    // une fiche sans aucun moyen d'agir dessus.
    const utilisateur = userEvent.setup();
    await ouvrirLeRegistre(utilisateur);

    await utilisateur.click(screen.getByText("Orange"));
    await screen.findByText("1 fiche sélectionnée");
    expect(screen.getByLabelText("Fermer le détail")).toBeDefined();

    // par la case à cocher de cette ligne-là — l'autre chemin vers une sélection
    // vide. La première case est celle de l'en-tête, la deuxième celle de la
    // ligne « Orange » : décocher n'importe quelle autre *ajouterait* une ligne,
    // et le test passerait pour une mauvaise raison.
    await utilisateur.click(screen.getByLabelText("Sélectionner le document 1"));
    await waitFor(() => expect(screen.queryByText(/fiche.? sélectionnée/)).toBeNull());
    expect(screen.queryByLabelText("Fermer le détail")).toBeNull();
  });

  it("« Tout décocher » referme aussi la fiche ouverte", async () => {
    // Sans quoi la ligne restait surlignée et son panneau ouvert : « tout
    // décocher » laissait quelque chose de coché à l'écran.
    const utilisateur = userEvent.setup();
    await ouvrirLeRegistre(utilisateur);

    await utilisateur.click(screen.getByText("Orange"));
    await screen.findByText("1 fiche sélectionnée");
    expect(screen.getByLabelText("Fermer le détail")).toBeDefined();   // la fiche est ouverte

    await utilisateur.click(screen.getByText("Tout décocher"));
    await waitFor(() => expect(screen.queryByText("1 fiche sélectionnée")).toBeNull());
    expect(screen.queryByLabelText("Fermer le détail")).toBeNull();
  });
});


/**
 * La barrière d'erreur, éprouvée sur un écran réel (§18.12).
 *
 * Ce cas n'est pas inventé : en écrivant le test ci-dessus, un simulacre qui
 * renvoyait des données incomplètes au tableau de bord a rendu l'application
 * entièrement blanche. C'est exactement ce que la barrière doit empêcher.
 */
describe("un écran qui se casse n'emporte pas les autres", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const normale = apiSimulee();
    global.fetch = vi.fn(async (url, options) => {
      // Données de tableau de bord malformées : `widgets` manque, le composant lève.
      if (String(url).includes("/tableaux-de-bord/") && String(url).includes("/donnees")) {
        return json({ id: "accueil", nom: "Accueil" });
      }
      return normale(url, options);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("montre ce qui s'est passé, et laisse de quoi s'en aller", async () => {
    const utilisateur = userEvent.setup();
    render(<AuthProvider><App /></AuthProvider>);

    expect(await screen.findByText("Ce tableau de bord s'est interrompu")).toBeDefined();
    // la barre d'outils est toujours là : on n'est pas prisonnier de l'écran cassé
    expect(screen.getByPlaceholderText(/Rechercher un document/)).toBeDefined();

    await utilisateur.click(screen.getByText("Factures"));
    expect(await screen.findByText("Orange")).toBeDefined();
  });
});


describe("effacer les filtres", () => {
  beforeEach(() => { global.fetch = apiSimulee(); });

  it("remonte au type de document, et garde ses colonnes", async () => {
    // Une vue enregistrée ne pose pas de catégorie : son filtrage vient de ses
    // critères. Effacer sans reposer le type ramenait à « tous les documents »,
    // et les colonnes propres au type disparaissaient — ce qui se lit comme une
    // perte de réglage alors qu'on voulait juste tout effacer.
    const utilisateur = userEvent.setup();
    render(<AuthProvider><App /></AuthProvider>);

    // Les vues vivent sous leur classement dans la navigation : on déplie
    // d'abord, comme le ferait quelqu'un qui cherche la sienne.
    await utilisateur.click(await screen.findByText("Factures"));
    await utilisateur.click(await screen.findByText("Toutes les factures"));
    // On interroge l'en-tête du tableau, et non n'importe quelle occurrence du
    // mot : le sélecteur « Grouper par » liste les mêmes colonnes, et l'y trouver
    // ne dirait rien de ce que le tableau affiche.
    expect(await screen.findByRole("columnheader", { name: /N° facture/ })).toBeDefined();

    await utilisateur.click(await screen.findByTitle(/Retirer tous les filtres/));

    // Les colonnes du type sont toujours là : on est remonté au type, pas à la
    // racine — où le tableau serait retombé sur ses colonnes par défaut.
    expect(await screen.findByRole("columnheader", { name: /N° facture/ })).toBeDefined();
    expect(screen.getByRole("columnheader", { name: /Émise le/ })).toBeDefined();
  });
});
