import React from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import DocumentsTable from "./DocumentsTable.jsx";

/**
 * Alignement de la rangée de recherche.
 *
 * Le défaut corrigé ici datait de la première version : les cellules de filtres
 * avaient 10 px de marge horizontale là où l'en-tête et le corps du tableau en
 * ont 16. Chaque champ de recherche apparaissait donc décalé de 6 px par rapport
 * à la colonne qu'il filtre.
 *
 * jsdom ne calcule aucune mise en page — il ne peut pas dire si « c'est
 * aligné ». Ce qu'il peut affirmer, et qui suffit à empêcher la régression,
 * c'est que les trois rangées déclarent la même marge.
 */
describe("tableau des documents", () => {
  const rendre = () => render(
    <DocumentsTable
      documents={[]}
      filtres={{}}
      onFiltresChange={() => {}}
      tri={{ colonne: "date_import", sens: "desc" }}
      onTriChange={() => {}}
      total={0}
      decalage={0}
      parPage={50}
    />,
  );

  const margeHorizontale = (element) => {
    const parties = element.style.padding.split(" ");
    return parties.length > 1 ? parties[1] : parties[0];
  };

  it("aligne les champs de recherche sur les colonnes qu'ils filtrent", () => {
    rendre();
    const rangees = screen.getAllByRole("row");
    const enTetes = rangees[0].querySelectorAll("th");
    const filtres = rangees[1].querySelectorAll("th");

    expect(filtres).toHaveLength(enTetes.length);
    for (let i = 0; i < enTetes.length; i += 1) {
      expect(margeHorizontale(filtres[i])).toBe(margeHorizontale(enTetes[i]));
    }
  });

  it("garde une rangée de filtres régulière malgré des contrôles différents", () => {
    rendre();
    // Les colonnes sont filtrées tantôt par un champ texte, tantôt par une date,
    // tantôt par une liste fermée. Ces contrôles n'ont pas la même nature ; ils
    // doivent malgré tout occuper la même hauteur, sinon la rangée ondule.
    //
    // On ne regarde que les hauteurs exprimées en pixels : une hauteur relative
    // (« 100% ») est celle d'un champ interne, qui épouse déjà le cadre.
    const rangeeFiltres = screen.getAllByRole("row")[1];
    const hauteurs = new Set(
      [...rangeeFiltres.querySelectorAll("*")]
        .map((element) => element.style?.height)
        .filter((hauteur) => hauteur && hauteur.endsWith("px")),
    );
    expect(hauteurs.size).toBeGreaterThan(0);
    // 22 px depuis que les champs ne sont plus encadrés (§18.14) : ce test a
    // d'ailleurs attrapé l'oubli — la liste déroulante était restée à 26.
    expect([...hauteurs]).toEqual(["22px"]);
  });
});

describe("filtres de colonne", () => {
  it("propose comme date le format écrit ici, jj/mm/aaaa", () => {
    render(
      <DocumentsTable
        documents={[]} filtres={{}} onFiltresChange={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={0} decalage={0} parPage={50}
      />,
    );
    expect(screen.getByPlaceholderText("jj/mm/aaaa")).toBeDefined();
  });
});

/**
 * Colonnes propres à la catégorie (§18.1) et sélection multiple (§18.3).
 */
describe("colonnes de la catégorie", () => {
  const COLONNES = [
    { champ: "fournisseur", libelle: "Émetteur", filtre: "reference", source: "fournisseurs" },
    { champ: "meta:numero_facture", libelle: "N° facture", filtre: "texte", type: "texte" },
    { champ: "date_document", libelle: "Émise le", filtre: "date", type: "date" },
    { champ: "meta:montant_ttc", libelle: "Montant TTC", filtre: "texte",
      type: "montant", alignement: "droite" },
    { champ: "meta:titulaire", libelle: "Titulaire", filtre: "texte", type: "texte" },
  ];

  const FACTURE = {
    id: 7,
    fournisseur: "Orange",
    categorie: "Factures",
    date_document: "2026-07-21",
    statut: "traite",
    metadonnees: { numero_facture: "FR-001", montant_ttc: "50.99",
                   titulaire: "sys_utilisateurs:13" },
    libelles_references: { titulaire: "Jean Dupont" },
  };

  const rendre = (extra = {}) => render(
    <DocumentsTable
      documents={[FACTURE]}
      colonnes={COLONNES}
      filtres={{}}
      onFiltresChange={() => {}}
      onSelect={() => {}}
      tri={{ colonne: "date_import", sens: "desc" }}
      onTriChange={() => {}}
      total={1}
      decalage={0}
      parPage={50}
      {...extra}
    />,
  );

  it("garde les intitulés de colonne collés en haut pendant le défilement", () => {
    // La poignée de redimensionnement (§22.34) avait fait passer les cellules
    // d'intitulé en `position: relative`, ce qui écrasait leur `sticky` : les
    // intitulés s'en allaient au défilement pendant que la rangée de filtres,
    // elle, restait collée (§22.47). Les deux rangées doivent tenir ensemble.
    rendre();
    const intitule = screen.getAllByTitle(/Trier par/)[0];
    expect(intitule.style.position).toBe("sticky");
    expect(intitule.style.top).toBe("0px");
  });

  it("affiche les colonnes décrites par l'API, et rien d'autre", () => {
    rendre();
    for (const libelle of ["Émetteur", "N° facture", "Émise le", "Montant TTC", "Titulaire"]) {
      expect(screen.getByText(libelle)).toBeDefined();
    }
    // « Catégorie » n'appartient pas au tableau des factures : on est déjà dedans
    expect(screen.queryByText("Catégorie")).toBeNull();
  });

  it("lit les métadonnées, et préfère le libellé d'une référence à son identifiant", () => {
    rendre();
    expect(screen.getByText("FR-001")).toBeDefined();
    expect(screen.getByText("Jean Dupont")).toBeDefined();
    expect(screen.queryByText("sys_utilisateurs:13")).toBeNull();
  });

  it("met en forme les dates et les montants à la française", () => {
    rendre();
    expect(screen.getByText("21/07/2026")).toBeDefined();
    expect(screen.getByText("50,99")).toBeDefined();
  });

  it("ne montre aucune case à cocher quand la sélection n'est pas proposée", () => {
    rendre();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("retient la ligne cliquée, et relâche la précédente", () => {
    // Le geste attendu dans une liste : un clic simple remplace la sélection.
    const AUTRE = { ...FACTURE, id: 9, fournisseur: "EDF" };
    let recu = null;
    render(
      <DocumentsTable
        documents={[FACTURE, AUTRE]} colonnes={COLONNES} filtres={{}}
        onFiltresChange={() => {}} onSelect={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={2} decalage={0} parPage={50}
        selection={[7]} onSelectionChange={(s) => { recu = s; }}
      />,
    );
    fireEvent.click(screen.getByText("EDF"));
    expect(recu).toEqual([9]);
  });

  it("relâche une ligne déjà retenue quand on la reclique", () => {
    let recu = null;
    const ouvertures = [];
    render(
      <DocumentsTable
        documents={[FACTURE]} colonnes={COLONNES} filtres={{}}
        onFiltresChange={() => {}} onSelect={(id) => ouvertures.push(id)}
        selectedId={7}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={1} decalage={0} parPage={50}
        selection={[7]} onSelectionChange={(s) => { recu = s; }}
      />,
    );
    fireEvent.click(screen.getByText("Orange"));
    expect(recu).toEqual([]);
    // la fiche ouverte se referme avec elle : le geste défait ce qu'il a fait
    expect(ouvertures).toEqual([null]);
  });

  it("ne relâche qu'elle-même, laissant le reste de la sélection en place", () => {
    const AUTRE = { ...FACTURE, id: 9, fournisseur: "EDF" };
    let recu = null;
    render(
      <DocumentsTable
        documents={[FACTURE, AUTRE]} colonnes={COLONNES} filtres={{}}
        onFiltresChange={() => {}} onSelect={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={2} decalage={0} parPage={50}
        selection={[7, 9]} onSelectionChange={(s) => { recu = s; }}
      />,
    );
    fireEvent.click(screen.getByText("Orange"));
    expect(recu).toEqual([9]);
  });

  it("ajoute une ligne à la sélection avec Ctrl, sans perdre les autres", () => {
    const AUTRE = { ...FACTURE, id: 9, fournisseur: "EDF" };
    let recu = null;
    render(
      <DocumentsTable
        documents={[FACTURE, AUTRE]} colonnes={COLONNES} filtres={{}}
        onFiltresChange={() => {}} onSelect={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={2} decalage={0} parPage={50}
        selection={[7]} onSelectionChange={(s) => { recu = s; }}
      />,
    );
    fireEvent.click(screen.getByText("EDF"), { ctrlKey: true });
    expect(recu).toEqual([7, 9]);
  });

  it("ouvre la fiche de la ligne cliquée", () => {
    const ouvertures = [];
    rendre({
      selection: [], onSelectionChange: () => {}, onSelect: (id) => ouvertures.push(id),
    });
    fireEvent.click(screen.getByText("Orange"));
    expect(ouvertures).toEqual([7]);
  });

  it("coche une ligne sans ouvrir la fiche", () => {
    const choisies = [];
    const ouvertures = [];
    rendre({
      selection: [],
      onSelectionChange: (s) => choisies.push(s),
      onSelect: (id) => ouvertures.push(id),
    });
    const cases = screen.getAllByRole("checkbox");
    fireEvent.click(cases[1]);          // la première est celle de l'en-tête
    expect(choisies).toEqual([[7]]);
    expect(ouvertures).toHaveLength(0);
  });

  it("coche toute la page d'un seul geste, et la décoche de même", () => {
    let recu = null;
    const { rerender } = render(
      <DocumentsTable
        documents={[FACTURE]} colonnes={COLONNES} filtres={{}}
        onFiltresChange={() => {}} onSelect={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={1} decalage={0} parPage={50}
        selection={[]} onSelectionChange={(s) => { recu = s; }}
      />,
    );
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(recu).toEqual([7]);

    rerender(
      <DocumentsTable
        documents={[FACTURE]} colonnes={COLONNES} filtres={{}}
        onFiltresChange={() => {}} onSelect={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={1} decalage={0} parPage={50}
        selection={[7]} onSelectionChange={(s) => { recu = s; }}
      />,
    );
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(recu).toEqual([]);
  });

  it("garde la case à cocher accrochée au bord pendant le défilement latéral", () => {
    // Le tableau défile dès que les colonnes sont nombreuses : sans cet
    // ancrage, on perdrait de vue la ligne qu'on vient de cocher.
    rendre({ selection: [], onSelectionChange: () => {} });
    const enTetes = screen.getAllByRole("row")[0].querySelectorAll("th");
    expect(enTetes[0].style.position).toBe("sticky");
    expect(enTetes[0].style.left).toBe("0px");
  });

  it("garde la case « tout sélectionner » au-dessus des lignes qui défilent", () => {
    // Elle était collée en haut **et** à gauche, comme il faut, mais au même
    // rang de superposition que les cases des lignes. À égalité, c'est l'ordre
    // du document qui tranche : les lignes passaient par-dessus, et la case
    // paraissait ne pas suivre l'en-tête (§22.56).
    rendre({ selection: [], onSelectionChange: () => {} });
    const angle = screen.getAllByRole("row")[0].querySelectorAll("th")[0];
    expect(angle.style.top).toBe("0px");

    const premiereLigne = screen.getAllByRole("row").at(-1);
    const caseDeLigne = premiereLigne.querySelectorAll("td")[0];
    expect(caseDeLigne.style.position).toBe("sticky");
    expect(Number(angle.style.zIndex)).toBeGreaterThan(Number(caseDeLigne.style.zIndex));
  });

  it("ne pose aucune action sur la ligne", () => {
    // Une icône de suppression au bout d'une rangée se clique par accident, et
    // d'autant plus facilement qu'on visait la ligne d'à côté. Ce qu'on fait
    // d'un document se décide depuis sa fiche ou depuis la barre d'outils.
    rendre({ selection: [], onSelectionChange: () => {} });
    expect(screen.queryByText("Actions")).toBeNull();
    expect(screen.queryByLabelText("Supprimer ce document")).toBeNull();
    expect(screen.queryByLabelText("Consulter ce document")).toBeNull();
  });

  it("aligne toutes les colonnes à gauche, montants compris", () => {
    // Première tentative : les montants alignés à droite, comme dans un tableur.
    // L'utilisateur a tranché — « pas d'exception ». Et il a raison sur le fond :
    // l'intitulé se retrouvait à un bout de la colonne, son champ de recherche à
    // l'autre, et l'œil qui descend perdait son repère.
    rendre();
    const enTetes = screen.getAllByRole("row")[0].querySelectorAll("th");
    for (const enTete of enTetes) {
      expect(enTete.style.textAlign === "" || enTete.style.textAlign === "left").toBe(true);
    }
    const cadres = screen.getAllByRole("row")[1].querySelectorAll(".filtre-colonne");
    for (const cadre of cadres) {
      expect(cadre.style.flexDirection).not.toBe("row-reverse");
    }
  });

  it("ne dessine plus de cadre autour des champs de recherche", () => {
    // Encadrés, ils pesaient autant que l'en-tête : cinq boîtes en rang qui
    // réclamaient l'attention avant les documents.
    rendre();
    const cadre = screen.getAllByRole("row")[1].querySelector(".filtre-colonne");
    // `border` composite ne rend plus rien dès qu'un côté diffère : on regarde
    // les côtés, qui disent exactement ce qu'on veut vérifier.
    expect(cadre.style.borderTopStyle).toBe("none");
    expect(cadre.style.borderLeftStyle).toBe("none");
    expect(cadre.style.borderBottom).toContain("1px solid");
    expect(cadre.style.background).toBe("transparent");
  });

  it("écrit une date à la française même quand la colonne ne l'annonce pas", () => {
    // Les métadonnées extraites n'ont pas toutes une règle qui déclare leur
    // type ; personne ne lit pour autant une date à l'envers.
    render(
      <DocumentsTable
        documents={[{ id: 8, metadonnees: { date_echeance: "2026-03-09" }, statut: "traite" }]}
        colonnes={[{ champ: "meta:date_echeance", libelle: "Échéance", filtre: "texte", type: "texte" }]}
        filtres={{}} onFiltresChange={() => {}} onSelect={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }} onTriChange={() => {}}
        total={1} decalage={0} parPage={50}
      />,
    );
    expect(screen.getByText("09/03/2026")).toBeDefined();
  });
});

/**
 * Textes longs et origine du dépôt (§22.67, §22.68).
 */
describe("ce qu'une cellule montre", () => {
  const COLONNES = [
    { champ: "meta:commentaire", libelle: "Commentaire", filtre: "texte", type: "texte" },
    { champ: "meta:montant_ttc", libelle: "Montant TTC", filtre: "texte", type: "montant" },
  ];
  const LONG = "Révision complète : distribution, courroie, galets tendeurs, "
    + "pompe à eau, vidange et filtres. Contrôle des plaquettes avant et arrière.";
  const DOC = {
    id: 7, categorie: "Entretiens", statut: "traite",
    metadonnees: { commentaire: "court", montant_ttc: "50.99" },
    libelles_references: {},
  };

  const rendre = (documents) => render(
    <DocumentsTable
      documents={documents}
      colonnes={COLONNES}
      filtres={{}}
      onFiltresChange={() => {}}
      tri={{ colonne: "date_import", sens: "desc" }}
      onTriChange={() => {}}
      total={documents.length}
      decalage={0}
      parPage={50}
    />,
  );

  it("replie un texte long au lieu d'étirer sa colonne", () => {
    // Un commentaire de trois lignes poussait sa colonne à la largeur du texte,
    // et le reste du tableau sortait de l'écran.
    rendre([{ ...DOC, metadonnees: { ...DOC.metadonnees, commentaire: LONG } }]);
    const cellule = screen.getByTitle(LONG);
    expect(cellule.style.webkitLineClamp).toBe("4");
    expect(cellule.style.overflow).toBe("hidden");

    // **La largeur maximale est la condition du repliement** (§22.71) : sans
    // elle, la boîte se pose sur une seule ligne, rien ne la contraint, et la
    // colonne s'étire quand même. jsdom ne calcule aucune mise en page — il ne
    // peut pas dire « ça se replie » ; ce qu'il peut affirmer, c'est que la
    // borne existe, et c'est justement elle qui manquait.
    //
    // Elle est portée par la **cellule**, et la valeur en occupe toute la
    // largeur (§22.89) : bornée en pixels sur la valeur elle-même, le texte
    // revenait à la ligne à 340 px quelle que soit la colonne.
    expect(Number.parseInt(cellule.closest("td").style.maxWidth, 10)).toBeGreaterThan(0);
    expect(cellule.style.maxWidth).toBe("100%");

    // Tronquer sans donner accès au reste, c'est cacher : l'infobulle porte tout.
    expect(cellule.getAttribute("title")).toBe(LONG);
  });

  it("coupe une valeur courte plutôt que d'élargir la colonne", () => {
    // Une cellule en `nowrap` sans borne pousse sa colonne à la largeur de son
    // contenu : on tirait le bord vers la gauche et la colonne revenait aussitôt
    // (§22.86). C'est la largeur demandée qui commande, pas la valeur la plus
    // longue — et l'infobulle porte le tout.
    const valeur = "AC-2026-000123456789";
    render(
      <DocumentsTable
        documents={[{ ...DOC, metadonnees: { ...DOC.metadonnees, commentaire: valeur } }]}
        colonnes={[{ ...COLONNES[0], largeur: 90 }, COLONNES[1]]}
        filtres={{}}
        onFiltresChange={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }}
        onTriChange={() => {}}
        total={1}
        decalage={0}
        parPage={50}
      />,
    );
    const cellule = screen.getByTitle(valeur);
    expect(cellule.style.textOverflow).toBe("ellipsis");
    expect(cellule.closest("td").style.maxWidth).toBe("90px");
    expect(cellule.closest("td").style.overflow).toBe("hidden");
  });

  it("respecte la largeur que la colonne déclare", () => {
    // Une colonne réglée ou tirée à la souris commande : le repli ne s'impose
    // qu'à défaut.
    render(
      <DocumentsTable
        documents={[{ ...DOC, metadonnees: { ...DOC.metadonnees, commentaire: LONG } }]}
        colonnes={[{ ...COLONNES[0], largeur: 220 }, COLONNES[1]]}
        filtres={{}}
        onFiltresChange={() => {}}
        tri={{ colonne: "date_import", sens: "desc" }}
        onTriChange={() => {}}
        total={1}
        decalage={0}
        parPage={50}
      />,
    );
    expect(screen.getByTitle(LONG).closest("td").style.maxWidth).toBe("220px");
    expect(screen.getByTitle(LONG).style.maxWidth).toBe("100%");
  });

  it("laisse les valeurs courtes sur une ligne, comme avant", () => {
    rendre([DOC]);
    expect(screen.queryByTitle("court")).toBeNull();
  });

  it("distingue d'un coup d'œil ce qui a été déposé à la main", () => {
    rendre([{ ...DOC, depot_manuel: true }]);
    expect(screen.getByLabelText("Déposé à la main")).toBeDefined();
  });

  it("ne marque rien quand l'origine est inconnue", () => {
    // La tâche qui portait la trace a pu être purgée : inventer « automatique »
    // serait pire que se taire.
    rendre([{ ...DOC, depot_manuel: null }]);
    expect(screen.queryByLabelText("Déposé à la main")).toBeNull();
  });
});
