import { describe, expect, it } from "vitest";

import { decrire, detailler } from "./journal";

/**
 * Lecture d'une modification de réglage dans le journal (§18.33).
 *
 * L'entrée recevait l'état complet du foyer — dix-neuf réglages dont dix-huit
 * inchangés. La ligne ne disait donc pas ce qui avait changé, ce qui est
 * exactement ce qu'on demande à un journal.
 */
const evenement = (avant, apres, libelles = {}) => ({
  action: "reglages.modification",
  details: { avant, apres, libelles },
});

describe("journal des réglages", () => {
  it("dit lequel a changé, et de quoi à quoi", () => {
    const { phrase } = decrire(evenement(
      { duree_session_heures: "8" },
      { duree_session_heures: "12" },
      { duree_session_heures: "Durée d'une session" },
    ));
    expect(phrase).toContain("Durée d'une session");
    expect(phrase).toContain("8");
    expect(phrase).toContain("12");
  });

  it("se contente de compter quand le lot en porte plusieurs", () => {
    const { phrase } = decrire(evenement(
      { theme: "clair", densite: "normale" },
      { theme: "sombre", densite: "compacte" },
    ));
    expect(phrase).toBe("2 réglages modifiés");
  });

  it("retombe sur la clé quand l'intitulé manque", () => {
    // Un réglage retiré depuis, ou une entrée écrite avant que les intitulés
    // ne voyagent : la ligne doit rester lisible.
    const { phrase } = decrire(evenement({ densite: "normale" }, { densite: "compacte" }));
    expect(phrase).toContain("Densite");
  });

  it("détaille chaque réglage touché, avec son intitulé", () => {
    const lignes = detailler({
      avant: { theme: "clair", densite: "normale" },
      apres: { theme: "sombre", densite: "compacte" },
      libelles: { theme: "Thème", densite: "Densité du tableau" },
    });
    const themes = lignes.find((l) => l.cle === "theme");
    expect(themes.libelle).toBe("Thème");
    expect(themes.avant).toBe("clair");
    expect(themes.apres).toBe("sombre");
    expect(themes.change).toBe(true);

    // « libelles » sert à nommer les lignes : il ne doit pas s'afficher comme
    // une donnée modifiée de plus.
    expect(lignes.some((l) => l.cle === "libelles")).toBe(false);
    expect(lignes).toHaveLength(2);
  });
});

describe("les documents que le journal cite (§22.64)", () => {
  it("nomme le document modifié quand la page le connaît", () => {
    const evenement = { action: "document.modification", objet_type: "document", objet_id: 108 };
    expect(decrire(evenement).phrase).toBe("Document nº108 modifié");
    expect(decrire(evenement, { documents: { 108: "facture EDF.pdf" } }).phrase)
      .toBe("Document nº108 modifié (facture EDF.pdf)");
  });

  it("dit « Document(s) attaché(s) » plutôt qu'un code recomposé", () => {
    // Sans phrase déclarée, le repli composait « Un document attaches » à partir
    // du code de l'action — exact, illisible.
    const evenement = {
      action: "document.attaches", objet_type: "document", objet_id: 9,
      details: { champ: "meta:factures_liees", documents: [41, 42] },
    };
    const refs = { documents: { 41: "EDF · F-777", 42: "Norauto · F-812" } };
    expect(decrire(evenement, refs).phrase)
      .toBe("Documents attachés sous « factures liees » : EDF · F-777 · Norauto · F-812");
    expect(decrire({ ...evenement, details: { champ: "meta:factures_liees", documents: [] } })
      .phrase).toBe("Aucun document attaché sous « factures liees »");
  });

  it("nomme la création d'une fiche pour ce qu'elle est", () => {
    const evenement = {
      action: "document.creation_manuelle", objet_type: "document", objet_id: 12,
      details: { nom_fichier: "Distribution", categorie: "Entretiens" },
    };
    expect(decrire(evenement).phrase).toBe("Création de la fiche « Distribution »");
  });

  it("rend les documents cités atteignables, et non un numéro nu", () => {
    // « Documents 108 » ne dit rien et ne mène nulle part : la ligne porte
    // désormais de quoi les nommer **et** ouvrir leur fiche.
    const lignes = detailler({ champ: "meta:factures_liees", documents: [41, 42] },
                             { documents: { 41: "EDF · F-777" } });
    const ligne = lignes.find((l) => l.cle === "documents");
    expect(ligne.type).toBe("documents");
    expect(ligne.documents).toEqual([
      { id: 41, nom: "EDF · F-777" },
      { id: 42, nom: "nº42" },
    ]);
  });
});
