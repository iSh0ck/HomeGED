import { describe, expect, it } from "vitest";

import { formaterMontant, valeurAffichee, valeurBrute } from "./cellules";

/**
 * Lecture d'une cellule (§18.1). Les colonnes n'étant plus codées en dur, tirer
 * la bonne valeur d'un document est devenu une opération à part entière — et
 * c'est là que se logent les erreurs silencieuses : une colonne vide se
 * remarque, une colonne qui affiche un identifiant se lit sans se voir.
 */
describe("valeur d'une cellule", () => {
  const doc = {
    fournisseur: "Orange",
    date_document: "2026-07-21",
    metadonnees: { montant_ttc: "50.99", titulaire: "usr_membres:3", numero_facture: "FR-001" },
    libelles_references: { titulaire: "Marie Martin" },
  };

  it("lit un champ du document comme une métadonnée", () => {
    expect(valeurBrute(doc, "fournisseur")).toBe("Orange");
    expect(valeurBrute(doc, "meta:numero_facture")).toBe("FR-001");
  });

  it("préfère toujours le libellé d'une référence à sa valeur stockée", () => {
    expect(valeurBrute(doc, "meta:titulaire")).toBe("Marie Martin");
  });

  it("rend une chaîne vide pour un champ absent, jamais « undefined »", () => {
    expect(valeurBrute(doc, "meta:inexistant")).toBe("");
    expect(valeurBrute(doc, "categorie")).toBe("");
    expect(valeurBrute(null, "fournisseur")).toBe("");
  });

  it("met les dates au format français", () => {
    expect(valeurAffichee(doc, { champ: "date_document", type: "date" })).toBe("21/07/2026");
  });

  it("laisse passer une date que l'on ne sait pas relire", () => {
    // Mieux vaut afficher imparfaitement une valeur extraite d'un vrai document
    // que de la faire disparaître.
    const bancal = { date_document: "juillet 2026" };
    expect(valeurAffichee(bancal, { champ: "date_document", type: "date" })).toBe("juillet 2026");
  });

  it("reconnaît une date à sa forme, pas seulement à son étiquette", () => {
    const colonne = { champ: "meta:date_echeance", type: "texte" };
    expect(valeurAffichee({ metadonnees: { date_echeance: "2026-03-09" } }, colonne))
      .toBe("09/03/2026");
    // et ne défigure pas ce qui n'en est pas une
    expect(valeurAffichee({ metadonnees: { date_echeance: "FR-2026-03" } }, colonne))
      .toBe("FR-2026-03");
  });

  it("écrit les montants avec la virgule décimale et sans inventer de devise", () => {
    expect(formaterMontant("50.99")).toBe("50,99");
    // l'espace des milliers varie selon la version d'ICU : on la normalise
    expect(formaterMontant("1234.5").replace(/\s/g, " ")).toBe("1 234,50");
    expect(formaterMontant("gratuit")).toBe("gratuit");
    expect(formaterMontant("")).toBe("");
  });
});
