import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DocumentPanel from "./DocumentPanel.jsx";

const DOCUMENT = {
  id: 7, nom_fichier: "facture.pdf", statut: "traite", nb_versions: 3,
  categorie: "Factures", date_document: "2026-04-02",
  metadonnees: { titulaire: "usr_membres:4" },
  champs_fiche: [
    { cle: "montant_ttc", libelle: "Montant TTC", valeur: "40,99", masquee: false },
    { cle: "titulaire", libelle: "Titulaire", valeur: null, masquee: false },
  ],
};

// Ce qu'on a rattaché à la main (§22.4) : ce qui ne partage aucune valeur avec
// ce document mais lui répond quand même.
const RATTACHES = [
  { document_id: 21, libelle: "Avenant nº2", categorie: "Contrats",
    nom_fichier: "avenant.pdf", intitule: "avenant" },
];

// Ce que les déclarations de type rapprochent (§22.8) : un dossier et ses
// pièces, reliés par un numéro que quelqu'un a désigné.
let RAPPROCHES = [];

// Les pièces du document (§22.2). La principale est celle que le registre ouvre ;
// les autres ont été jointes à la main.
const PIECES = [
  { id: 31, nom_fichier: "facture.pdf", ordre: 1, principale: true, taille_octets: 4096 },
  { id: 32, nom_fichier: "garantie.pdf", ordre: 2, principale: false },
];

/** Ce que le panneau a demandé au serveur, dans l'ordre. */
let appels;

function servir(pieces = PIECES) {
  global.fetch = vi.fn(async (url, options) => {
    appels.push(String(url));
    const chemin = String(url);
    if (chemin.endsWith("/versions")) {
      return new Response(JSON.stringify([]),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.endsWith("/pieces") && (options?.method || "GET") === "GET") {
      return new Response(JSON.stringify(pieces),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.endsWith("/rapprochements")) {
      return new Response(JSON.stringify({ rapprochements: RAPPROCHES }),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.endsWith("/rattachements")) {
      return new Response(JSON.stringify({ rattachements: RATTACHES }),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.includes("/documents?")) {
      return new Response(JSON.stringify([{ id: 11, nom_fichier: "carte_grise.pdf",
                                            categorie: "Véhicules", nb_versions: 1 }]),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (chemin.includes("/apercu") || chemin.includes("/fichier")) {
      // pas une `Response` : celle de Node refuse le Blob de jsdom. L'appelant
      // n'en lit que `ok` et `blob()`.
      return { ok: true, status: 200, blob: async () => new Blob(["png"]) };
    }
    return new Response(JSON.stringify(DOCUMENT),
                        { status: 200, headers: { "Content-Type": "application/json" } });
  });
}

beforeEach(() => {
  appels = [];
  URL.createObjectURL = vi.fn(() => "blob:vignette");
  URL.revokeObjectURL = vi.fn();
  servir();
});

describe("panneau d'un document", () => {
  it("montre les pièces du document côte à côte", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    // une tuile par pièce : c'est le dossier qu'on regarde, pas un seul papier
    expect(await screen.findByText("facture.pdf")).toBeDefined();
    expect(screen.getByText("garantie.pdf")).toBeDefined();
    expect(screen.getByText("Pièce principale")).toBeDefined();
    expect(screen.getAllByText(/· jointe/)).toHaveLength(1);
  });

  it("ne charge aucun document entier en vignettes", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await screen.findByText("Pièce principale");
    // chaque tuile demande son image, jamais le PDF : c'est tout l'intérêt du
    // mode. L'image part après le rendu de la tuile — on l'attend plutôt que de
    // parier sur l'ordre des micro-tâches.
    await waitFor(() => expect(appels.some((u) => u.includes("/apercu"))).toBe(true));
    expect(appels.some((u) => /\/documents\/\d+\/fichier/.test(u))).toBe(false);
  });

  it("les champs vides du type restent affichés", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByLabelText(/Document lié par/));
    expect(await screen.findByText("Titulaire")).toBeDefined();
  });
});

describe("la barre d'outils d'une pièce", () => {
  it("n'apparaît qu'une fois une pièce choisie", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await screen.findByText("garantie.pdf");
    expect(screen.queryByTitle(/Lire cette pièce/)).toBeNull();

    await userEvent.click(screen.getByText("garantie.pdf"));
    expect(screen.getByTitle(/Lire cette pièce/)).toBeDefined();
    expect(screen.getByTitle(/Ce que l'on sait de cette pièce/)).toBeDefined();
  });

  it("« Voir » est un lien : le clic molette ouvre un onglet", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByText("garantie.pdf"));
    const voir = screen.getByTitle(/Lire cette pièce/);
    // un `<button>` ne s'ouvre pas dans un onglet, quoi qu'on lui fasse
    expect(voir.tagName).toBe("A");
    await waitFor(() => expect(voir.getAttribute("href")).toBeTruthy());
    expect(voir.getAttribute("target")).toBe("_blank");
  });

  it("propose de retirer une pièce à un administrateur, et à lui seul", async () => {
    const { unmount } = render(
      <DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);
    await userEvent.click(await screen.findByText("garantie.pdf"));
    expect(screen.queryByTitle(/Détacher cette pièce/)).toBeNull();
    unmount();

    render(<DocumentPanel documentId={7} onClose={() => {}} estAdmin
                          modeParDefaut="miniature" />);
    await userEvent.click(await screen.findByText("garantie.pdf"));
    await userEvent.click(screen.getByTitle(/Détacher cette pièce/));

    await waitFor(() => expect(
      global.fetch.mock.calls.some(([url, options]) =>
        String(url).endsWith("/documents/7/pieces/32") && options?.method === "DELETE")
    ).toBe(true));
  });

  it("ne propose pas de retirer la seule pièce d'un document", async () => {
    servir([PIECES[0]]);
    render(<DocumentPanel documentId={7} onClose={() => {}} estAdmin
                          modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByText("facture.pdf"));
    expect(screen.queryByTitle(/Détacher cette pièce/)).toBeNull();
  });

  it("désigne une autre pièce comme principale", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByText("garantie.pdf"));
    await userEvent.click(screen.getByTitle(/Faire de cette pièce la principale/));

    await waitFor(() => expect(
      global.fetch.mock.calls.some(([url, options]) =>
        String(url).endsWith("/documents/7/pieces/32/principale")
        && options?.method === "PUT")
    ).toBe(true));
  });
});

describe("joindre une pièce", () => {
  it("envoie le fichier au document ouvert", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    const champ = await screen.findByLabelText("Joindre une pièce à ce document");
    await userEvent.upload(champ, new File(["x"], "bon.pdf", { type: "application/pdf" }));

    await waitFor(() => expect(
      global.fetch.mock.calls.some(([url, options]) =>
        String(url).endsWith("/documents/7/pieces") && options?.method === "POST")
    ).toBe(true));
  });

  it("demande au dépôt si le fichier est une pièce ou un rescan (§22.3)", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    // le cas courant d'abord : on joint, on ne remplace pas
    const choix = await screen.findByLabelText("Ce que devient le fichier déposé");
    expect(choix.textContent).toContain("nouvelle pièce");

    await userEvent.click(choix);
    await userEvent.click(await screen.findByText(/nouvelle version de « garantie.pdf »/));
    await userEvent.upload(screen.getByLabelText("Joindre une pièce à ce document"),
                           new File(["x"], "garantie_v2.pdf", { type: "application/pdf" }));

    await waitFor(() => {
      const envoi = global.fetch.mock.calls.find(([url, options]) =>
        String(url).endsWith("/documents/7/pieces") && options?.method === "POST");
      expect(envoi).toBeDefined();
      expect(envoi[1].body.get("remplace_piece_id")).toBe("32");
    });
  });
});

describe("les pastilles d'une vignette", () => {
  it("annonce qu'un document a été redéposé, et ouvre ses dépôts", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    const pastille = await screen.findByLabelText(/3 dépôts pour ce document/);
    await userEvent.click(pastille);
    expect(await screen.findByText("Versions de ce document")).toBeDefined();
  });

  it("marque les pièces jointes à la main, et elles seules", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await screen.findByText("garantie.pdf");
    // la principale est là de plein droit : elle ne porte pas la pastille
    expect(screen.getAllByLabelText(/Document lié par/)).toHaveLength(1);
  });
});

describe("les liens déclarés sur la vue (§22.5)", () => {
  const LIENS_DE_VUE = [
    { vue_id: 3, champ_source: "meta:titulaire", champ_cible: "meta:titulaire",
      libelle: "Ses factures" },
  ];

  it("montre les documents que le lien désigne, et propose d'y aller", async () => {
    const suivre = vi.fn();
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature"
                          liensDeVue={LIENS_DE_VUE} onSuivreLien={suivre} />);

    // le lien a été **déclaré** par quelqu'un : c'est le seul rapprochement
    // encore affiché, le rapprochement automatique ayant quitté l'écran.
    // Depuis le §22.73 la vignette se désigne au lieu d'emmener sur sa fiche.
    expect(await screen.findByTitle(/Choisir ce document/)).toBeDefined();

    await userEvent.click(screen.getAllByLabelText(/Document lié par/)[0]);
    expect(await screen.findByText("Continuer vers")).toBeDefined();
    await userEvent.click(screen.getByText("Ses factures"));
    expect(suivre).toHaveBeenCalledWith(LIENS_DE_VUE[0], "usr_membres:4");
  });

  it("ne montre rien de tel quand la vue ne déclare aucun lien", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await screen.findByText("facture.pdf");
    expect(screen.queryByTitle(/Choisir ce document/)).toBeNull();
  });
});

describe("ce qui est rattaché à la main (§22.4)", () => {
  it("le montre dans le volet de détail", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByLabelText(/Document lié par/));
    expect(await screen.findByText("Rattaché à la main")).toBeDefined();
    expect(screen.getByText(/Avenant nº2/)).toBeDefined();
    // le rapprochement automatique, lui, a disparu de l'écran
    expect(screen.queryByText("Ce que ce document concerne")).toBeNull();
  });

  it("détache, et le dit au serveur", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByLabelText(/Document lié par/));
    await userEvent.click(await screen.findByLabelText("Détacher Avenant nº2"));

    await waitFor(() => expect(
      global.fetch.mock.calls.some(([url, options]) =>
        String(url).endsWith("/documents/7/rattachements/21")
        && options?.method === "DELETE")
    ).toBe(true));
    expect(screen.queryByText(/Avenant nº2/)).toBeNull();
  });
});


describe("les rapprochements déclarés sur le type (§22.8)", () => {
  it("montre en tuiles ce que la déclaration rassemble", async () => {
    RAPPROCHES = [{
      libelle: "Pièces du dossier", champ: "meta:numero_dossier", valeur: "D-2026-1234",
      documents: [{ id: 51, libelle: "Devis nº12", categorie: "Devis",
                    nom_fichier: "devis.pdf", nb_versions: 1 }],
    }];
    try {
      render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

      // la tuile porte l'intitulé de la déclaration : on sait **pourquoi** ces
      // deux documents se retrouvent côte à côte
      expect(await screen.findByTitle(/Choisir ce document/)).toBeDefined();
      expect(screen.getByLabelText(/Pièces du dossier/)).toBeDefined();
    } finally {
      RAPPROCHES = [];
    }
  });

  it("ne montre rien tant que rien n'est déclaré", async () => {
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);

    await screen.findByText("facture.pdf");
    expect(screen.queryByTitle(/Choisir ce document/)).toBeNull();
  });
});

// Une entrée de fiche simple (§19.1) : saisie à la main, sans fichier, avec un
// champ « documents de la GED » qui en désigne d'autres.
const FICHE = {
  id: 9, nom_fichier: "2026-09-06 — Distribution", statut: "traite", nb_versions: 1,
  categorie: "Entretiens", a_un_fichier: false,
  metadonnees: { commentaire: "Distribution" },
  champs_fiche: [{ cle: "commentaire", libelle: "Commentaire",
                   valeur: "Distribution", masquee: false }],
};

const ATTACHES = [
  { champ: "meta:factures_liees", libelle: "Factures liées",
    documents: [
      { id: 41, libelle: "EDF · F-2026-777", categorie: "Factures",
        nom_fichier: "edf.pdf" },
      { id: 42, libelle: "Norauto · F-2026-812", categorie: "Factures",
        nom_fichier: "norauto.pdf" },
    ] },
];

function servirFiche({ fichier = false, attaches = ATTACHES } = {}) {
  global.fetch = vi.fn(async (url) => {
    const chemin = String(url);
    const json = (corps) => new Response(JSON.stringify(corps),
      { status: 200, headers: { "Content-Type": "application/json" } });
    if (chemin.endsWith("/versions")) return json([]);
    if (chemin.endsWith("/pieces")) return json([]);
    if (chemin.endsWith("/rapprochements")) return json({ rapprochements: [] });
    if (chemin.endsWith("/rattachements")) return json({ rattachements: [] });
    if (chemin.endsWith("/attaches")) return json({ attaches });
    if (chemin.includes("/apercu") || chemin.includes("/fichier")) {
      return { ok: true, status: 200, blob: async () => new Blob(["png"]) };
    }
    return json({ ...FICHE, a_un_fichier: fichier });
  });
}

describe("une fiche simple sans fichier (§22.58)", () => {
  it("ne montre aucune vignette, et ne réclame aucun aperçu", async () => {
    // La tuile de repli demandait la première page d'un fichier qui n'existe
    // pas : l'écran répondait « Page non rendue » sur une entrée parfaitement
    // normale.
    servirFiche({ attaches: [] });
    render(<DocumentPanel documentId={9} onClose={() => {}} modeParDefaut="miniature" />);

    await screen.findByText(/rien ne lui est rattaché/);
    expect(screen.queryByText("Page non rendue")).toBeNull();
    expect(global.fetch.mock.calls.some(([url]) => String(url).includes("/apercu"))).toBe(false);
  });

  it("montre à la place les documents que ses champs désignent, avec leur lien", async () => {
    servirFiche();
    render(<DocumentPanel documentId={9} onClose={() => {}} modeParDefaut="miniature" />);

    expect(await screen.findByText("EDF · F-2026-777")).toBeDefined();
    expect(screen.getByText("Norauto · F-2026-812")).toBeDefined();
    // Le nom du champ porte la pastille : « Factures liées » dit ce qui les
    // rapproche, « lié » ne dirait rien.
    expect(screen.getAllByLabelText(/Factures liées/)).toHaveLength(2);
  });

  it("montre sa vignette dès qu'un fichier lui a été joint", async () => {
    servirFiche({ fichier: true, attaches: [] });
    render(<DocumentPanel documentId={9} onClose={() => {}} modeParDefaut="miniature" />);

    await waitFor(() => expect(
      global.fetch.mock.calls.some(([url]) => String(url).includes("/apercu"))).toBe(true));
  });
});

describe("un document lié se regarde sans quitter la fiche (§22.73)", () => {
  it("le désigne au lieu d'emmener sur sa fiche", async () => {
    // Cliquer une vignette voisine quittait la fiche pour la sienne : on venait
    // souvent la regarder, pas la remplacer.
    servirFiche();
    let ouvert = null;
    render(<DocumentPanel documentId={9} onClose={() => {}} modeParDefaut="miniature"
                          onOuvrirDocument={(id) => { ouvert = id; }} />);

    await userEvent.click(await screen.findByText("EDF · F-2026-777"));
    expect(ouvert).toBeNull();
    expect(await screen.findByTitle("Ce que ce document porte")).toBeDefined();
    expect(screen.getByTitle(/Lire ce document ici/)).toBeDefined();
  });

  it("le lit dans la fiche, et non dans un onglet (§22.78)", async () => {
    // « Voir » ouvrait un onglet : on quittait l'écran pour vérifier un montant,
    // ce qui est exactement ce qu'on ne voulait plus.
    servirFiche();
    render(<DocumentPanel documentId={9} onClose={() => {}} modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByText("EDF · F-2026-777"));
    await userEvent.click(screen.getByTitle(/Lire ce document ici/));

    expect(await screen.findByText(/Vous lisez/)).toBeDefined();
    expect(screen.getByText("Revenir au document")).toBeDefined();

    // Le panneau charge **lui-même** le fichier de ce qu'il lit (§22.81) : la
    // grille de vignettes en préparait un pour son propre bouton, mais elle se
    // démonte en passant en visionneuse et révoquait son URL au passage — on se
    // retrouvait devant un cadre vide.
    await waitFor(() => expect(
      global.fetch.mock.calls.some(([url]) => String(url).includes("/documents/41/fichier")),
    ).toBe(true));
    // Le plein écran reste offert sous la visionneuse, et il ouvre bien le
    // document lié — pas celui de la fiche.
    expect(screen.getByText("Ouvrir le PDF en plein écran").closest("a")
      .getAttribute("target")).toBe("_blank");
  });

  it("garde le chemin vers sa fiche, en le disant", async () => {
    servirFiche();
    let ouvert = null;
    render(<DocumentPanel documentId={9} onClose={() => {}} modeParDefaut="miniature"
                          onOuvrirDocument={(id) => { ouvert = id; }} />);

    await userEvent.click(await screen.findByText("EDF · F-2026-777"));
    await userEvent.click(screen.getByTitle("Quitter cette fiche pour la sienne"));
    expect(ouvert).toBe(41);
  });

  it("dit ce que le document porte, sans aller le chercher", async () => {
    servirFiche({ attaches: [{
      champ: "meta:factures_liees", libelle: "Factures liées",
      documents: [{ id: 41, libelle: "EDF · F-2026-777", categorie: "Factures",
                    nom_fichier: "edf.pdf", date_document: "2026-03-23",
                    details: [{ libelle: "Montant TTC", valeur: "84,20" }] }],
    }] });
    render(<DocumentPanel documentId={9} onClose={() => {}} modeParDefaut="miniature" />);

    await userEvent.click(await screen.findByText("EDF · F-2026-777"));
    await userEvent.click(screen.getByTitle("Ce que ce document porte"));
    expect(screen.getByText(/Montant TTC : 84,20/)).toBeDefined();
  });
});

describe("« Voir » et sa seconde façon (§22.74)", () => {
  it("garde son geste : le clic ouvre la pièce dans le panneau", async () => {
    servir();
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);
    await userEvent.click(await screen.findByText("garantie.pdf"));

    // Rien de plus n'est proposé tant qu'on ne l'a pas demandé : une option qui
    // s'impose est une option qu'on subit.
    expect(screen.queryByText(/plein écran, dans un onglet/)).toBeNull();

    const voir = screen.getByTitle(/Lire cette pièce/);
    expect(voir.tagName).toBe("A");          // un lien : le clic molette ouvre un onglet
    expect(voir.getAttribute("href")).toBeTruthy();
  });

  it("ne montre l'ouverture plein écran que si on la demande", async () => {
    servir();
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);
    await userEvent.click(await screen.findByText("garantie.pdf"));

    await userEvent.click(screen.getByLabelText("Autres façons d'ouvrir"));
    const plein = await screen.findByText(/plein écran, dans un onglet/);
    expect(plein.closest("a").getAttribute("target")).toBe("_blank");
  });

  it("referme le menu quand on s'en va", async () => {
    servir();
    render(<DocumentPanel documentId={7} onClose={() => {}} modeParDefaut="miniature" />);
    await userEvent.click(await screen.findByText("garantie.pdf"));
    await userEvent.click(screen.getByLabelText("Autres façons d'ouvrir"));
    await screen.findByText(/plein écran, dans un onglet/);

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByText(/plein écran, dans un onglet/)).toBeNull();
  });
});
