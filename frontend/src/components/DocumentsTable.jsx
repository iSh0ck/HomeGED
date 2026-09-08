import React, { useEffect, useMemo, useRef, useState } from "react";
import Pagination from "./Pagination.jsx";
import { ArrowUp, ArrowDown, FileText, X, AlertTriangle, Hand } from "lucide-react";
import ColumnFilter, { estActif } from "./ColumnFilter.jsx";
import { valeurAffichee } from "../lib/cellules";
import { PoigneeColonne, useLargeursColonnes } from "./champs/LargeursColonnes.jsx";
import { PastilleVersions } from "./VersionsDocument.jsx";
import { t } from "../lib/langue";

const OPTIONS_STATUT = () => [
  { value: "", label: "Tous" },
  { value: "traite", label: t("Traité") },
  { value: "en_attente", label: t("En attente") },
  { value: "ocr_en_cours", label: t("OCR en cours") },
  { value: "erreur", label: "Erreur" },
];

// Colonnes du registre quand l'API n'a rien dit (premier rendu, catégorie
// inconnue). Le tableau n'attend pas la réponse pour s'afficher.
const COLONNES_PAR_DEFAUT = () => [
  { champ: "categorie", libelle: t("Catégorie"), filtre: "reference", source: "categories" },
  { champ: "date_document", libelle: "Date", filtre: "date", type: "date" },
  { champ: "statut", libelle: "Statut", filtre: "statut" },
];

const MARGE_COLONNE = 16;
const LARGEUR_CASE = 38;      // colonne des cases à cocher

// Trois étages de superposition (§22.56). Les cases des lignes et celle de
// l'en-tête portaient le même rang ; à égalité, c'est l'ordre du document qui
// tranche, et les lignes — écrites après — se peignaient par-dessus la case
// « tout sélectionner ». Elle suivait bien le défilement, elle était recouverte.
const Z_CORPS_COLLE = 1;      // cellule de corps collée au bord gauche
const Z_ENTETE = 2;           // rangées d'intitulés et de filtres
const Z_ANGLE = 3;            // l'angle des deux : collé en haut ET à gauche

/**
 * Registre des documents.
 *
 * **Les colonnes appartiennent à la catégorie affichée** (§18.1) : une facture
 * se lit en une ligne — émetteur, numéro, date, montant, titulaire — là où un
 * courrier n'a que faire de ces colonnes. Elles sont décrites par l'API, y
 * compris le contrôle de recherche à afficher sous chaque en-tête : ajouter une
 * colonne ne demande pas une ligne de code ici.
 *
 * Le tableau défile latéralement quand elles sont nombreuses ; la case à cocher
 * reste accrochée au bord gauche, sans quoi on perdrait de vue la ligne qu'on
 * a cochée.
 *
 * **Aucune action ne vit sur la ligne** : une icône de suppression au bout d'une
 * rangée se clique par accident, et se clique d'autant plus facilement qu'on
 * visait la ligne d'à côté. Ce qu'on fait d'un document se décide depuis sa
 * fiche, ou depuis la barre d'outils une fois la sélection faite — deux endroits
 * où l'on sait sur quoi l'on agit.
 */
export default function DocumentsTable({
  documents,
  colonnes,
  selectedId,
  onSelect,
  filtres,
  onFiltresChange,
  // Périmètre de la vue : ce que les listes de recherche doivent refléter.
  categorieId,
  recherche,
  tri,
  // Tri d'ouverture de la catégorie : le cycle des en-têtes y revient (§18.49).
  triDefaut = { colonne: "date_import", sens: "desc" },
  onTriChange,
  total = 0,
  decalage = 0,
  parPage = 50,
  onPage,
  onParPage,
  // Sélection multiple (§18.3) : gérée par le parent, qui la conserve d'une
  // page à l'autre — on constitue une sélection en parcourant le registre.
  selection = [],
  onSelectionChange,
  onVersions,
  // Ce qui explique la liste — ou permet d'y ajouter — avant qu'on la lise : le
  // fil des branches parcourues, la zone de dépôt d'une fiche simple (§22.1).
  enTete = null,
}) {
  const COLONNES = colonnes?.length ? colonnes : COLONNES_PAR_DEFAUT();
  const selectionnables = onSelectionChange != null;
  const selectionnes = useMemo(() => new Set(selection), [selection]);
  // Dernière ligne cliquée : c'est depuis elle que Maj étend la sélection.
  // Une référence et non un état : la changer ne doit pas redessiner le tableau.
  const ancre = useRef(null);
  // Les largeurs tirées à la souris (§22.34), rangées par catégorie : les
  // colonnes d'une facture ne sont pas celles d'un contrat, et une largeur
  // commune aux deux ne conviendrait à aucun des deux.
  const { largeurs, commencer, oublier } = useLargeursColonnes(
    `registre.${categorieId ?? "tout"}`);

  /**
   * Les intitulés de colonne restent visibles pendant le défilement, et la
   * rangée de filtres reste **collée sous eux** (§22.45).
   *
   * Les deux rangées sont `sticky`, mais la seconde doit savoir de combien
   * descendre : sa hauteur était écrite en dur (30 px), ce qui ne vaut que pour
   * une densité et une taille de police données. Ailleurs, elle recouvrait les
   * intitulés ou laissait un interstice par lequel les documents défilaient.
   * On mesure donc la rangée plutôt que de la deviner — et on la remesure quand
   * la densité du foyer ou la largeur des colonnes change.
   */
  const rangeeIntitules = useRef(null);
  const [hauteurIntitules, setHauteurIntitules] = useState(30);
  useEffect(() => {
    const noeud = rangeeIntitules.current;
    if (!noeud) return undefined;
    const mesurer = () => setHauteurIntitules(noeud.getBoundingClientRect().height || 30);
    mesurer();
    // `ResizeObserver` manque à l'environnement de test : la mesure initiale
    // suffit alors, et l'écran réel garde le suivi.
    if (typeof ResizeObserver === "undefined") return undefined;
    const observateur = new ResizeObserver(mesurer);
    observateur.observe(noeud);
    return () => observateur.disconnect();
  }, []);

  function majFiltre(col, filtre) {
    const suivant = { ...filtres };
    if (filtre) suivant[col.champ] = filtre;
    else delete suivant[col.champ];
    onFiltresChange(suivant);
  }

  // Le tri est effectué par la base : il porte sur tout le registre, pas
  // seulement sur la page reçue — trier n'a de sens que sur l'ensemble.
  const documentsTries = documents;

  /**
   * Cycle de tri d'une colonne : croissant, décroissant, puis **retour au tri
   * par défaut** de la catégorie (§18.49).
   *
   * Sans ce troisième temps, une colonne cliquée par curiosité restait le tri du
   * registre pour le reste de la visite, et rien ne permettait de revenir à
   * l'ordre d'origine sinon deviner lequel c'était. Le cycle se referme donc sur
   * lui-même.
   */
  function basculerTri(colonne) {
    if (tri.colonne !== colonne) return onTriChange?.({ colonne, sens: "asc" });
    if (tri.sens === "asc") return onTriChange?.({ colonne, sens: "desc" });
    onTriChange?.({ ...triDefaut });
  }

  /** Le tri en cours est-il celui d'origine ? L'en-tête le dit en clair. */
  const triEstParDefaut =
    tri.colonne === triDefaut.colonne && tri.sens === triDefaut.sens;

  function basculerLigne(id) {
    if (!selectionnables) return;
    const suivant = selectionnes.has(id)
      ? selection.filter((x) => x !== id)
      : [...selection, id];
    onSelectionChange(suivant);
    ancre.current = id;
  }

  /**
   * Clic sur une ligne.
   *
   * Un clic simple **remplace** la sélection : la ligne cliquée devient la
   * seule retenue, la précédente est relâchée. C'est ce qu'on attend d'un clic
   * dans une liste, et c'est ce qui permet d'enchaîner — on parcourt le
   * registre, la barre d'outils suit ce qu'on regarde. Recliquer une ligne déjà
   * retenue la relâche : le même geste défait ce qu'il vient de faire.
   *
   * Les deux gestes habituels s'y ajoutent, parce qu'ils ne coûtent rien et que
   * leur absence surprend : Ctrl (ou ⌘) ajoute ou retire une ligne sans toucher
   * au reste, Maj étend jusqu'à la précédente — c'est ainsi qu'on prend dix
   * factures qui se suivent sans cocher dix cases.
   */
  function cliquerLigne(evenement, doc, index) {
    if (!selectionnables) {
      onSelect(doc.id);
      return;
    }

    // Recliquer une ligne retenue la relâche, et referme sa fiche : le même
    // geste défait ce qu'il vient de faire. Sans quoi il n'y aurait aucune
    // façon de revenir à une sélection vide en cliquant.
    if (selectionnes.has(doc.id) && !evenement.shiftKey) {
      onSelectionChange(selection.filter((id) => id !== doc.id));
      if (doc.id === selectedId) onSelect(null);
      ancre.current = null;
      return;
    }

    if (evenement.ctrlKey || evenement.metaKey) {
      onSelect(doc.id);
      onSelectionChange([...selection, doc.id]);
      ancre.current = doc.id;
      return;
    }

    onSelect(doc.id);
    if (evenement.shiftKey && ancre.current != null) {
      const depart = documentsTries.findIndex((d) => d.id === ancre.current);
      if (depart !== -1) {
        const [a, b] = depart < index ? [depart, index] : [index, depart];
        const plage = documentsTries.slice(a, b + 1).map((d) => d.id);
        onSelectionChange([...selection.filter((id) => !plage.includes(id)), ...plage]);
        return;
      }
    }
    onSelectionChange([doc.id]);
    ancre.current = doc.id;
  }

  const idsPage = documentsTries.map((d) => d.id);
  const toutePageCochee = idsPage.length > 0 && idsPage.every((id) => selectionnes.has(id));

  function basculerPage() {
    if (!selectionnables) return;
    // On n'agit que sur la page affichée : cocher la case d'en-tête ne doit pas
    // embarquer des documents qu'on n'a pas vus.
    onSelectionChange(
      toutePageCochee
        ? selection.filter((id) => !idsPage.includes(id))
        : [...selection, ...idsPage.filter((id) => !selectionnes.has(id))]
    );
  }

  const nbFiltresActifs = Object.values(filtres).filter(estActif).length;


  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      {/* Le défilement latéral vit ici : l'en-tête reste collé en haut (sticky
          vertical) tout en suivant le défilement horizontal, ce qu'un conteneur
          extérieur ne permettrait pas. */}
      <div style={{ flex: 1, overflow: "auto" }} className="scrollbar-thin">
        <table style={{
          borderCollapse: "separate", borderSpacing: 0, fontSize: 13,
          width: "max-content", minWidth: "100%",
        }}>
          <thead>
            <tr ref={rangeeIntitules}>
              {selectionnables && (
                <th style={{ ...enteteStyle, ...colleeGauche, zIndex: Z_ANGLE,
                             width: LARGEUR_CASE, padding: "9px 0 6px 14px" }}>
                  <input
                    type="checkbox"
                    checked={toutePageCochee}
                    onChange={basculerPage}
                    aria-label={t("Tout sélectionner sur cette page")}
                    title={t("Tout sélectionner sur cette page")}
                    style={{ cursor: "pointer" }}
                  />
                </th>
              )}
              {COLONNES.map((col) => (
                <th
                  key={col.champ}
                  onClick={() => col.champ && basculerTri(col.champ)}
                  title={
                    tri.colonne !== col.champ
                      ? `Trier par ${t(col.libelle)}`
                      : tri.sens === "asc"
                        ? t("Inverser le tri")
                        : t("Revenir au tri par défaut")
                  }
                  style={{
                    ...enteteStyle,
                    cursor: "pointer",
                    // **Pas de `position: relative` ici** (§22.47) : il écrasait
                    // le `sticky` de l'en-tête, et les intitulés de colonne
                    // s'en allaient au défilement pendant que la rangée de
                    // filtres, elle, restait collée. `sticky` sert de repère aux
                    // enfants positionnés absolument tout aussi bien que
                    // `relative` — la poignée de redimensionnement (§22.34), qui
                    // avait amené ce `relative`, reste donc en place.
                    // La largeur tirée à la souris l'emporte sur celle réglée en
                    // administration : elle vient de qui regarde, et sur son
                    // écran à lui (§22.34).
                    width: largeurs[col.champ] || undefined,
                    minWidth: largeurs[col.champ] || col.largeur || undefined,
                    maxWidth: largeurs[col.champ] || undefined,
                  }}
                >
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    {t(col.libelle)}
                    {estActif(filtres[col.champ]) && (
                      <span
                        title={t("Filtre actif sur cette colonne")}
                        style={{
                          width: 5, height: 5, borderRadius: "50%",
                          background: "var(--accent)", flexShrink: 0,
                        }}
                      />
                    )}
                    {tri.colonne === col.champ && (
                      <span
                        style={{ display: "inline-flex", opacity: triEstParDefaut ? 0.55 : 1 }}
                        title={triEstParDefaut ? t("Tri par défaut de cette catégorie") : undefined}
                      >
                        {tri.sens === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
                      </span>
                    )}
                  </span>
                  <PoigneeColonne champ={col.champ} largeur={largeurs[col.champ]}
                                  commencer={commencer} oublier={oublier} />
                </th>
              ))}
            </tr>
            <tr>
              {selectionnables && (
                <th style={{ ...enteteFiltreStyle, top: hauteurIntitules,
                             ...colleeGauche, zIndex: Z_ANGLE, padding: "0 0 8px" }} />
              )}
              {COLONNES.map((col) => (
                <th
                  key={col.champ}
                  onClick={(e) => e.stopPropagation()}
                  style={{ ...enteteFiltreStyle, top: hauteurIntitules }}
                >
                  <ColumnFilter
                    col={colonneFiltrable(col)}
                    filtre={filtres[col.champ]}
                    onChange={(filtre) => majFiltre(col, filtre)}
                    contexte={filtres}
                    categorieId={categorieId}
                    recherche={recherche}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {documentsTries.length === 0 && (
              <tr>
                <td colSpan={COLONNES.length + (selectionnables ? 1 : 0)} style={{ padding: 0 }}>
                  <div style={{
                    display: "flex", flexDirection: "column", alignItems: "center",
                    justifyContent: "center", gap: 10,
                    color: "var(--ink-faint)", padding: "48px 16px",
                  }}>
                    <FileText size={28} />
                    <div style={{ fontSize: 13 }}>
                      {nbFiltresActifs > 0
                        ? t("Aucun document ne correspond à ces filtres.")
                        : t("Aucun document ne correspond à cette vue.")}
                    </div>
                    {nbFiltresActifs > 0 && (
                      <button
                        onClick={() => onFiltresChange({})}
                        style={{
                          display: "flex", alignItems: "center", gap: 4,
                          border: "1px solid var(--line-strong)", background: "transparent",
                          borderRadius: "var(--radius)", padding: "5px 10px",
                          fontSize: 12, color: "var(--ink-soft)",
                        }}
                      >
                        <X size={12} />
                        {t("Réinitialiser les filtres")}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )}
            {documentsTries.map((doc, index) => {
              const ouvert = doc.id === selectedId;
              const coche = selectionnes.has(doc.id);
              // Cochée ou ouverte, une ligne retenue se voit. La barre de
              // gauche distingue celle dont la fiche est affichée : on sait
              // ainsi laquelle des lignes retenues on est en train de lire.
              const fond = coche || ouvert ? "var(--accent-soft)" : "var(--bg-panel)";
              return (
                <tr
                  key={doc.id}
                  onClick={(e) => cliquerLigne(e, doc, index)}
                  aria-selected={coche}
                  style={{
                    cursor: "pointer",
                    background: fond,
                    borderLeft: ouvert ? "3px solid var(--accent)" : "3px solid transparent",
                    userSelect: "none",   // Maj+clic sélectionnerait le texte
                  }}
                >
                  {selectionnables && (
                    <td
                      style={{ ...celluleStyle, ...colleeGauche, zIndex: Z_CORPS_COLLE,
                               background: fond, padding: "9px 0 9px 14px" }}
                      onClick={(e) => { e.stopPropagation(); basculerLigne(doc.id); }}
                    >
                      <input
                        type="checkbox"
                        checked={coche}
                        onChange={() => basculerLigne(doc.id)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`Sélectionner le document ${doc.id}`}
                        style={{ cursor: "pointer" }}
                      />
                    </td>
                  )}
                  {COLONNES.map((col, rang) => (
                    <Cellule
                      key={col.champ}
                      doc={doc}
                      colonne={col}
                      premiere={rang === 0}
                      largeur={largeurs[col.champ] || col.largeur}
                      onVersions={onVersions}
                    />
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pied de tableau : hors du conteneur défilant, il reste en place quand
          on se déplace latéralement — une pagination qui glisse hors de l'écran
          est une pagination qu'on ne trouve plus. */}
      {total > 0 && (
        <div style={{
          padding: "6px 16px 10px", borderTop: "1px solid var(--line)",
          background: "var(--bg-panel)", flexShrink: 0,
        }}>
          <Pagination
            total={total}
            parPage={parPage}
            decalage={decalage}
            onDecalage={(d) => onPage?.(d)}
            onParPage={onParPage}
          />
        </div>
      )}
    </div>
  );
}

/**
 * Traduit une colonne de l'API en ce qu'attend le champ de recherche. Le statut
 * est le seul dont les valeurs sont connues d'avance : elles vivent ici, dans
 * l'interface qui les affiche, plutôt que d'être répétées par l'API.
 */
function colonneFiltrable(col) {
  if (col.filtre === "statut") {
    return { ...col, key: col.champ, filtre: "liste", options: OPTIONS_STATUT() };
  }
  return { ...col, key: col.champ };
}

function Cellule({ doc, colonne, premiere, largeur, onVersions }) {
  // Toutes les colonnes sont alignées à gauche, montants compris (§18.15) : une
  // exception d'alignement décale l'intitulé de son champ de recherche et de ses
  // valeurs, et l'œil qui descend la colonne perd son repère.
  const style = { ...celluleStyle };

  if (colonne.champ === "statut") {
    return (
      <td style={style}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Statut value={doc.statut} />
          {doc.champs_manquants?.length > 0 && (
            <AlertTriangle
              size={13}
              color="var(--amber)"
              aria-label={t("Document incomplet")}
              title={`Champs attendus manquants : ${doc.champs_manquants
                .map((c) => c.libelle)
                .join(", ")}`}
            />
          )}
        </span>
      </td>
    );
  }

  const texte = valeurAffichee(doc, colonne);
  // Un texte court garde le comportement d'avant — une ligne, sans césure : la
  // très grande majorité des cellules tient sur une ligne, et les faire toutes
  // passer par le repliement les décalerait les unes des autres.
  // Une largeur imposée — réglée en administration ou tirée à la souris — doit
  // s'imposer **aussi au corps du tableau** (§22.86). Une cellule en
  // `nowrap` sans borne pousse sa colonne à la largeur de son contenu : on
  // tirait le bord vers la gauche, et la colonne revenait aussitôt. C'est le
  // corps qui commandait, pas la poignée.
  if (largeur) {
    style.maxWidth = largeur;
    style.overflow = "hidden";
  }
  const long = typeof texte === "string" && (texte.length > SEUIL_LONG || texte.includes("\n"));
  const contenu = texte === "" ? <Vide /> : (long ? (
    // Une largeur **maximale** est indispensable : sans elle, la boîte se pose
    // sur une seule ligne, rien ne la contraint, et le repliement ne mord pas —
    // la colonne s'étirait donc à la largeur du texte (§22.71). Celle que la
    // colonne déclare, ou celle qu'on a tirée à la souris, sinon un repli qui
    // laisse quatre lignes lisibles.
    //
    // L'infobulle porte le texte entier : tronquer sans jamais donner accès au
    // reste, c'est cacher.
    // La boîte occupe **la cellule**, et non une largeur fixe (§22.89) : le
    // repli se faisait à 340 px quelle que soit la colonne, et le texte revenait
    // à la ligne bien avant son bord. C'est la cellule qui porte la borne — elle
    // seule connaît la largeur que la colonne a fini par prendre.
    <span style={valeurLongueStyle} title={texte}>
      {texte}
    </span>
  ) : (largeur && typeof texte === "string" ? (
    // Coupé net plutôt que d'élargir la colonne, et l'infobulle porte le tout :
    // c'est la largeur demandée qui commande, pas la valeur la plus longue.
    <span style={valeurCoupeeStyle} title={texte}>{texte}</span>
  ) : texte));
  if (long) {
    style.whiteSpace = "normal";
    style.verticalAlign = "top";
    style.maxWidth = largeur || LARGEUR_TEXTE_LONG;
  }
  const numerique = colonne.type === "montant" || colonne.type === "entier"
                    || colonne.type === "date" || colonne.champ.startsWith("date_");

  if (premiere) {
    // La première colonne porte l'icône : c'est par elle qu'on repère une ligne
    // en parcourant le tableau des yeux. La pastille des versions s'y range
    // aussi — c'est le seul signe qu'un document a une histoire (§18.36).
    return (
      <td style={style}>
        <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          {/* Deux façons d'entrer, deux histoires (§22.68) : la main a vu le
              document et lui a dit son type ; le dossier surveillé l'a pris tout
              seul. L'icône le dit d'un coup d'œil, comme celle de liaison. */}
          {doc.depot_manuel ? (
            <Hand size={14} color="var(--accent)" style={{ flexShrink: 0 }}
                  aria-label={t("Déposé à la main")}
                  title={t("Déposé à la main dans l'application, et non par le dossier surveillé")} />
          ) : (
            <FileText size={14} color="var(--ink-faint)" style={{ flexShrink: 0 }} />
          )}
          {contenu}
          <PastilleVersions nombre={doc.nb_versions} onClick={() => onVersions?.(doc.id)} />
        </span>
      </td>
    );
  }
  return <td style={style} className={numerique ? "tabular" : undefined}>{contenu}</td>;
}

const enteteStyle = {
  position: "sticky",
  top: 0,
  zIndex: Z_ENTETE,
  background: "var(--bg-panel-alt)",
  borderBottom: "1px solid var(--line)",
  textAlign: "left",
  padding: `9px ${MARGE_COLONNE}px 6px`,
  fontWeight: 600,
  color: "var(--ink-soft)",
  fontSize: 12,
  userSelect: "none",
  whiteSpace: "nowrap",
};

const enteteFiltreStyle = {
  position: "sticky",
  // `top` est posé à la main par le tableau : c'est la hauteur **mesurée** de la
  // rangée d'intitulés (§22.45). Elle était écrite en dur à 30 px, ce qui ne
  // vaut que pour une densité et une taille de police données — ailleurs, la
  // rangée de filtres recouvrait les intitulés ou laissait passer les documents
  // par-dessous en défilant.
  zIndex: Z_ENTETE,
  background: "var(--bg-panel-alt)",
  borderBottom: "1px solid var(--line-strong)",
  // Resserré depuis que les champs ne sont plus encadrés (§18.14) : le
  // soulignement se suffit à lui-même, la marge qui aérait les boîtes n'a plus
  // d'objet.
  padding: `0 ${MARGE_COLONNE}px 5px`,
  fontWeight: 400,
  verticalAlign: "top",
};

// Colonne accrochée au bord gauche pendant le défilement latéral. Le `zIndex`
// se pose au cas par cas, sur chaque cellule : voir les trois étages en tête.
const colleeGauche = { position: "sticky", left: 0 };

// Marge horizontale unique pour l'en-tête, la rangée de filtres et le corps du
// tableau : les filtres avaient 10 px là où les colonnes en ont 16, et chaque
// champ de recherche apparaissait décalé par rapport à son intitulé.
const celluleStyle = {
  // La hauteur vient du réglage de densité du foyer (§18.24).
  padding: `var(--cellule-hauteur, 9px) ${MARGE_COLONNE}px`,
  verticalAlign: "middle",
  borderBottom: "1px solid var(--line)",
  whiteSpace: "nowrap",
};

// Un commentaire de trois lignes poussait sa colonne à la largeur du texte, et
// le reste du tableau sortait de l'écran (§22.67). La valeur revient donc à la
// ligne, et s'arrête à quatre — au-delà, une ligne de tableau n'est plus une
// ligne. La cellule reste **large de ce que la colonne veut bien** : c'est la
// largeur réglée en administration, ou celle tirée à la souris, qui commande.
const LIGNES_MAX = 4;
// Au-delà, on replie. En deçà, la cellule garde sa ligne unique : la très grande
// majorité y tient, et les faire toutes passer par le repliement les décalerait
// les unes des autres.
const SEUIL_LONG = 40;
// La largeur d'un texte replié quand la colonne n'en déclare aucune. Assez pour
// quatre lignes lisibles, assez peu pour laisser voir les colonnes suivantes.
const LARGEUR_TEXTE_LONG = 340;

const valeurCoupeeStyle = {
  display: "block",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const valeurLongueStyle = {
  display: "-webkit-box",
  WebkitLineClamp: LIGNES_MAX,
  WebkitBoxOrient: "vertical",
  overflow: "hidden",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  // Toute la cellule, et rien de plus : c'est elle qui sait ce que la colonne
  // mesure une fois le tableau posé (§22.89).
  maxWidth: "100%",
};

function Vide() {
  return <span style={{ color: "var(--ink-faint)" }}>—</span>;
}

function Statut({ value }) {
  const styles = {
    traite: { bg: "var(--accent-soft)", fg: "var(--accent)", label: t("Traité") },
    en_attente: { bg: "var(--amber-soft)", fg: "var(--amber)", label: t("En attente") },
    ocr_en_cours: { bg: "var(--amber-soft)", fg: "var(--amber)", label: t("OCR en cours") },
    erreur: { bg: "var(--brick-soft)", fg: "var(--brick)", label: "Erreur" },
  }[value] || { bg: "var(--line)", fg: "var(--ink-soft)", label: value };

  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        background: styles.bg,
        color: styles.fg,
        borderRadius: 3,
        padding: "2px 8px",
      }}
    >
      {styles.label}
    </span>
  );
}
