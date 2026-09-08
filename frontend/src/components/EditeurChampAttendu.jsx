import React, { useEffect, useState } from "react";
import { adminApi, api } from "../api";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "./Modal.jsx";
import Liste from "./champs/Liste.jsx";
import { t } from "../lib/langue";

/**
 * L'éditeur d'un champ attendu (§22.16).
 *
 * Extrait de l'écran « Champs attendus » pour que l'assemblage guidé s'en serve
 * aussi : deux formulaires qui déclarent la même chose auraient divergé au
 * premier ajout — l'un aurait connu le type d'un champ libre, l'autre non.
 *
 * La **nature** est le premier choix, et elle commande tout le reste : un champ
 * libre qu'on nomme et qu'on type, une valeur puisée dans une table du foyer,
 * des documents de la GED, ou un champ que les règles d'extraction remplissent
 * déjà.
 */
const VIDE = { champ: "", source_table: "", libelle: "", obligatoire: true,
               identifiant: false, echeance: false, rappel_jours: null,
               deduction: "aucune", colonnes_deduction: [], colonnes_affichees: [],
               deduction_approchee: false, attache_documents: false,
               type_champ: "texte", documents_categorie_id: null,
               documents_champs: [], extraction_attendue: false, ordre: 100 };

const NATURES = () => [
  { valeur: "libre", libelle: t("Champ libre"),
    aide: t("Une valeur que vous nommez et dont vous choisissez le type — « ce qui a été fait », « kilométrage », « date d'intervention ». C'est le cas courant.") },
  { valeur: "source", libelle: t("Lié à une table"),
    aide: t("La valeur se choisit dans une table du foyer ou parmi les comptes : un véhicule, un membre, un émetteur. Elle peut aussi se déduire du texte.") },
  { valeur: "documents", libelle: t("Documents de la GED"),
    aide: t("Le champ contient des documents déjà classés, qu'on désigne au lieu de les recopier — « Factures liées », « Devis reçus ».") },
  { valeur: "existant", libelle: t("Champ déjà connu"),
    aide: t("Reprendre un champ que vos règles d'extraction remplissent déjà, ou une colonne du document comme sa date.") },
];

const DEDUCTIONS = () => [
  { valeur: "aucune", libelle: t("Ne rien déduire") },
  { valeur: "toutes", libelle: t("Toutes les colonnes cherchées doivent figurer") },
  { valeur: "une", libelle: t("Une seule colonne trouvée suffit") },
];

/** Une clé technique lisible, déduite de l'intitulé : on ne la tape plus à la main. */
function _cle(libelle) {
  return (libelle || "")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")
    .slice(0, 60);
}

export default function EditeurChampAttendu({ categorieId, nomCategorie, regle,
                                             ordreParDefaut = 100, onFerme, onEnregistre }) {
  const [edition, setEdition] = useState(() => (regle
    ? { ...regle, libelle: regle.libelle || "", source_table: regle.source_table || "",
        deduction: regle.deduction || "aucune",
        colonnes_deduction: regle.colonnes_deduction || [],
        colonnes_affichees: regle.colonnes_affichees || [],
        deduction_approchee: !!regle.deduction_approchee,
        type_champ: regle.type_champ || "texte",
        documents_categorie_id: regle.documents_categorie_id ?? null,
        documents_champs: regle.documents_champs || [],
        extraction_attendue: !!regle.extraction_attendue }
    : { ...VIDE, ordre: ordreParDefaut }));
  const [mode, setMode] = useState(() => (!regle ? "libre"
    : regle.source_table ? "source"
      : regle.attache_documents ? "documents"
        : regle.champ?.startsWith("meta:") ? "libre" : "existant"));
  const [cleReference, setCleReference] = useState(
    regle?.champ?.startsWith("meta:") ? regle.champ.replace(/^meta:/, "") : "");
  const [champs, setChamps] = useState([]);
  const [sources, setSources] = useState([]);
  const [typesChamp, setTypesChamp] = useState([]);
  const [categories, setCategories] = useState([]);
  const [colonnesParType, setColonnesParType] = useState({});
  // Ce que le **type accepté** déclare porter : c'est la liste qui a du sens
  // pour « Chercher dans », et non le vocabulaire de toute la GED (§22.19).
  const [champsDeLaCible, setChampsDeLaCible] = useState([]);
  const [dejaRegles, setDejaRegles] = useState(new Set());
  // Ce qu'une règle d'extraction remplit déjà pour ce type : c'est ce qui
  // distingue « rempli tout seul » d'une métadonnée simplement connue (§22.20).
  const [remplisParRegle, setRemplisParRegle] = useState(new Set());
  // Ce que **ce type-ci** a déjà nommé : champs attendus, colonnes de son
  // tableau, cibles de ses règles. C'est le vocabulaire qui a du sens pour lui —
  // proposer celui de toute la GED noyait « Date du document » sous les
  // véhicules et les montants d'autres types (§22.24).
  const [cibles, setCibles] = useState([]);
  const [erreur, setErreur] = useState(null);

  useEffect(() => {
    adminApi.champsDisponibles().then(setChamps).catch(() => {});
    adminApi.sourcesChamps().then(setSources).catch(() => {});
    adminApi.typesDeChamp().then(setTypesChamp).catch(() => {});
    adminApi.categories()
      .then((toutes) => setCategories(
        toutes.filter((c) => (c.nature || "type") !== "dossier")))
      .catch(() => {});
    api.colonnesCategories()
      .then((reponse) => setColonnesParType(reponse.colonnes || {}))
      .catch(() => {});
    adminApi.reglesChamps(categorieId)
      .then((r) => setDejaRegles(new Set(r.map((x) => x.champ))))
      .catch(() => {});
    adminApi.champsCibles(categorieId)
      .then((trouvees) => {
        setCibles(trouvees);
        setRemplisParRegle(new Set(
          trouvees.filter((c) => c.remplie_par_regle).map((c) => `meta:${c.champ}`)));
      })
      .catch(() => {});
  }, [categorieId]);

  // Les champs attendus du type accepté : c'est ce qu'un document de ce type
  // **porte vraiment**, et donc là où une recherche a des chances de trouver.
  useEffect(() => {
    const cible = edition.documents_categorie_id;
    if (!cible) { setChampsDeLaCible([]); return; }
    adminApi.reglesChamps(cible)
      .then((r) => setChampsDeLaCible(r.map((regle) => ({
        champ: regle.champ,
        libelle: regle.libelle_effectif || regle.libelle || regle.champ,
      }))))
      .catch(() => setChampsDeLaCible([]));
  }, [edition.documents_categorie_id]);

  /**
   * Les champs qu'on peut **reprendre** pour ce type (§22.24).
   *
   * Deux provenances, et deux seulement : les colonnes que porte tout document —
   * sa date, son classement —, et ce que ce type-ci a déjà nommé, c'est-à-dire
   * les cibles de ses règles et les colonnes de son tableau.
   *
   * Ce qui n'y est plus : le vocabulaire de **toute** la GED. Sur une fiche
   * « Entretiens », il proposait des véhicules, des émetteurs, des numéros de
   * facture — beaucoup d'entrées, aucune qui décrive un entretien. Les critères
   * de filtre `lien:` n'y ont jamais eu leur place non plus : ils rapprochent des
   * documents, ils ne sont pas des valeurs qu'un document porte.
   */
  function champsProposables() {
    const colonnes = champs
      .filter((c) => !c.champ.startsWith("meta:") && !c.champ.startsWith("lien:"))
      .filter((c) => !["texte", "statut", "nom_fichier"].includes(c.champ))
      .map((c) => ({ ...c, groupe: t("Colonnes du document") }));

    const libelles = new Map(champs.map((c) => [c.champ, c.libelle]));
    const duType = cibles
      .filter((c) => c.champ !== "date_document")
      .map((c) => ({
        champ: `meta:${c.champ}`,
        libelle: libelles.get(`meta:${c.champ}`)
          || c.champ.replace(/_/g, " ").replace(/^./, (l) => l.toUpperCase()),
        groupe: c.remplie_par_regle
          ? t("Remplis par une règle d'extraction")
          : t("Déjà utilisés pour ce type"),
      }));

    return [...colonnes, ...duType];
  }

  /**
   * Les champs sur lesquels la recherche d'un champ « documents » peut porter.
   *
   * Ceux que le type accepté déclare, en premier : chercher un numéro de facture
   * n'a de sens que si les factures en portent un. À défaut — type non choisi, ou
   * type qui ne déclare rien —, ses colonnes de tableau, puis le nom du fichier,
   * qui existe toujours.
   */
  function champsDuType(cible) {
    if (champsDeLaCible.length) {
      return [...champsDeLaCible, { champ: "nom_fichier", libelle: t("Nom du fichier") }];
    }
    const utiles = champs.filter((c) => !["texte", "statut"].includes(c.champ));
    if (!cible) return utiles.slice(0, 12);
    const dedans = new Set((colonnesParType[cible] || []).map((c) => c.champ));
    const retenus = utiles.filter((c) => dedans.has(c.champ) || c.champ === "nom_fichier");
    return retenus.length ? retenus : utiles.slice(0, 12);
  }

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const cle = cleReference.trim() || _cle(edition.libelle);
      const payload = {
        categorie_id: categorieId,
        champ: mode === "existant" ? edition.champ : `meta:${cle}`,
        source_table: mode === "source" ? edition.source_table || null : null,
        libelle: edition.libelle || null,
        obligatoire: !!edition.obligatoire,
        identifiant: !!edition.identifiant,
        echeance: !!edition.echeance,
        rappel_jours: edition.echeance ? (Number(edition.rappel_jours) || null) : null,
        deduction: mode === "source" ? edition.deduction || "aucune" : "aucune",
        colonnes_deduction: mode === "source" ? edition.colonnes_deduction || [] : [],
        colonnes_affichees: mode === "source" ? edition.colonnes_affichees || [] : [],
        deduction_approchee: mode === "source" && !!edition.deduction_approchee,
        attache_documents: mode === "documents",
        documents_categorie_id: mode === "documents"
          ? (edition.documents_categorie_id || null) : null,
        documents_champs: mode === "documents" ? (edition.documents_champs || []) : [],
        // Un champ « documents » ne se lit pas dans le texte : la question n'a
        // pas de sens pour lui.
        extraction_attendue: mode !== "documents" && !!edition.extraction_attendue,
        type_champ: mode === "libre" ? edition.type_champ || "texte" : "texte",
        ordre: Number(edition.ordre) || 100,
      };
      if (edition.id) await adminApi.modifierRegleChamp(edition.id, payload);
      else await adminApi.creerRegleChamp(payload);
      onEnregistre?.();
    } catch (err) {
      setErreur(err.message);
    }
  }

  return (
        <Modal
          titre={edition.id ? t("Modifier le champ attendu") : t("Ajouter un champ attendu")}
          sousTitre={nomCategorie ? `Catégorie « ${nomCategorie} »` : undefined}
          onClose={onFerme}
        >
          <form onSubmit={enregistrer}>
            <label style={{ ...champStyle, marginTop: 0 }}>{t("Nature du champ")}</label>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {NATURES().map((o) => (
                <button
                  key={o.valeur}
                  type="button"
                  onClick={() => setMode(o.valeur)}
                  title={t(o.aide)}
                  style={{
                    flex: "1 1 45%",
                    border: "1px solid " + (mode === o.valeur ? "var(--accent)" : "var(--line)"),
                    background: mode === o.valeur ? "var(--accent-soft)" : "var(--bg-panel)",
                    color: "var(--ink)", borderRadius: "var(--radius)",
                    padding: "6px 10px", fontSize: 12,
                  }}
                >
                  {t(o.libelle)}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                          lineHeight: 1.45 }}>
              {NATURES().find((o) => o.valeur === mode)?.aide}
            </div>

            {mode === "libre" && (
              <>
                <label style={champStyle}>{t("Intitulé")}</label>
                <input
                  required
                  autoFocus
                  aria-label={t("Intitulé du champ")}
                  value={edition.libelle}
                  onChange={(e) => setEdition({ ...edition, libelle: e.target.value })}
                  placeholder={t("ex : Ce qui a été fait")}
                  style={inputStyle}
                />

                <label style={champStyle}>{t("Type de valeur")}</label>
                <Liste
                  valeur={edition.type_champ || "texte"}
                  ariaLabel={t("Type de valeur")}
                  options={(typesChamp.length ? typesChamp : [{ valeur: "texte",
                                                                libelle: "Texte" }])
                    .map((ty) => ({ valeur: ty.valeur, libelle: ty.libelle }))}
                  onChange={(v) => setEdition({ ...edition, type_champ: v })}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                              lineHeight: 1.45 }}>
                  C'est le type qui décide de la façon dont le champ se saisit : un
                  calendrier pour une date, un champ de plusieurs lignes pour un
                  commentaire. Le champ sera enregistré sous{" "}
                  <code>meta:{cleReference.trim() || _cle(edition.libelle) || "…"}</code>.
                </div>

                <label style={champStyle}>{t("Clé de stockage (facultatif)")}</label>
                <input
                  value={cleReference}
                  aria-label={t("Clé de stockage")}
                  onChange={(e) => setCleReference(e.target.value)}
                  placeholder={_cle(edition.libelle) || t("déduite de l'intitulé")}
                  style={{ ...inputStyle, fontFamily: "var(--font-mono)" }}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                              lineHeight: 1.45 }}>
                  Le nom technique sous lequel la valeur est rangée. C'est lui qu'on écrit
                  dans une <strong>règle d'extraction</strong> (« colonne cible »), dans un
                  filtre ou dans un modèle d'export — l'intitulé, lui, peut être renommé
                  sans rien casser. Laissez vide : il est déduit de l'intitulé, ce qui
                  convient presque toujours. Deux champs d'un même type ne peuvent pas
                  porter la même clé.
                </div>
              </>
            )}

            {mode === "documents" && (
              <>
                <label style={champStyle}>{t("Intitulé")}</label>
                <input
                  required
                  autoFocus
                  aria-label={t("Intitulé du champ")}
                  value={edition.libelle}
                  onChange={(e) => setEdition({ ...edition, libelle: e.target.value })}
                  placeholder={t("ex : Factures liées")}
                  style={inputStyle}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                              lineHeight: 1.45 }}>
                  Le champ proposera de <strong>choisir des documents déjà classés</strong>,
                  qui restent où ils sont avec leurs colonnes et leurs droits. Enregistré
                  sous <code>meta:{cleReference.trim() || _cle(edition.libelle) || "…"}</code>.
                </div>

                {/* Ce que le champ accepte (§22.14). Un champ qui propose toute
                    la GED ne guide personne : « Factures liées » doit proposer
                    des factures, cherchées par leur numéro ou leur émetteur. */}
                <label style={champStyle}>{t("Type de document accepté")}</label>
                <Liste
                  valeur={edition.documents_categorie_id
                    ? String(edition.documents_categorie_id) : ""}
                  ariaLabel={t("Type de document accepté")}
                  options={[{ valeur: "", libelle: t("— tous les types —") },
                    ...categories.map((c) => ({ valeur: String(c.id), libelle: c.nom }))]}
                  onChange={(v) => setEdition({ ...edition,
                                                documents_categorie_id: v ? Number(v) : null,
                                                documents_champs: [] })}
                />

                <label style={champStyle}>{t("Chercher dans")}</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {champsDuType(edition.documents_categorie_id).map((c) => {
                    const coche = (edition.documents_champs || []).includes(c.champ);
                    return (
                      <label key={c.champ} style={{ display: "inline-flex", alignItems: "center",
                                                    gap: 5, fontSize: 12 }}>
                        <input
                          type="checkbox"
                          checked={coche}
                          onChange={(e) => setEdition({
                            ...edition,
                            documents_champs: e.target.checked
                              ? [...(edition.documents_champs || []), c.champ]
                              : (edition.documents_champs || []).filter((x) => x !== c.champ),
                          })}
                        />
                        {t(c.libelle)}
                      </label>
                    );
                  })}
                </div>
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                              lineHeight: 1.45 }}>
                  {t("Ce qu'on tape dans le sélecteur sera cherché dans ces champs-là. Rien de coché : le nom du fichier et le texte reconnu — ce qui ramène beaucoup, et rarement ce qu'on veut.")}
                </div>
              </>
            )}

            {mode === "source" ? (
              <>
                <label style={champStyle}>{t("Table servant de source")}</label>
                <Liste
                  valeur={edition.source_table || ""}
                  ariaLabel={t("Source des valeurs proposées")}
                  placeholder={t("— Choisir une source —")}
                  options={[
                    { valeur: "", libelle: t("— Choisir une source —") },
                    ...sources.map((entree) => ({
                      valeur: entree.nom, libelle: t(entree.libelle),
                      groupe: entree.systeme ? t("Comptes") : t("Tables du foyer"),
                    })),
                  ]}
                  onChange={(v) => setEdition({ ...edition, source_table: v })}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.45 }}>
                  {t("Les comptes de la GED conviennent quand la personne concernée se connecte ; une table du foyer, quand elle n'a pas de compte — un enfant, un parent dont on garde les papiers.")}
                </div>

                <Affichage
                  edition={edition}
                  setEdition={setEdition}
                  source={sources.find((entree) => entree.nom === edition.source_table)}
                />

                <label style={champStyle}>{t("Clé de stockage")}</label>
                <input
                  required
                  value={cleReference}
                  onChange={(e) => setCleReference(e.target.value)}
                  placeholder="ex : vehicule"
                  style={{ ...inputStyle, fontFamily: "var(--font-mono)" }}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4 }}>
                  Le champ sera enregistré sous <code>meta:{cleReference || "…"}</code>. La valeur
                  retenue est la ligne choisie dans la table.
                </div>

                <Deduction
                  edition={edition}
                  setEdition={setEdition}
                  source={sources.find((entree) => entree.nom === edition.source_table)}
                />
              </>
            ) : mode === "existant" ? (
              <>
                <label style={champStyle}>Champ</label>
                <Liste
                  valeur={edition.champ}
                  ariaLabel={t("Champ attendu")}
                  placeholder={t("— Choisir un champ —")}
                  options={[
                    { valeur: "", libelle: t("— Choisir un champ —") },
                    // Le champ qu'on est **en train de modifier** figure
                    // évidemment parmi les règles déjà déclarées : l'écarter
                    // comme les autres vidait la liste à l'ouverture, et il
                    // fallait refaire le choix pour corriger autre chose
                    // (§22.22).
                    ...(edition.champ && !champsProposables().some((c) => c.champ === edition.champ)
                      ? [{ valeur: edition.champ,
                           libelle: edition.libelle || edition.champ,
                           groupe: t("Déjà choisi") }]
                      : []),
                    ...champsProposables()
                      .filter((c) => !dejaRegles.has(c.champ) || c.champ === edition.champ)
                      .map((c) => ({ valeur: c.champ, libelle: c.libelle,
                                     groupe: c.groupe })),
                  ]}
                  onChange={(v) => setEdition({ ...edition, champ: v })}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                              lineHeight: 1.45 }}>
                  Seuls les champs qui concernent <strong>ce type</strong> sont proposés :
                  les colonnes que porte tout document — sa date, son classement — et ce
                  que ce type a déjà nommé, c'est-à-dire les cibles de ses règles
                  d'extraction et les colonnes de son tableau. Pour une valeur nouvelle,
                  c'est « Champ libre » qu'il faut.
                </div>

                <label style={champStyle}>{t("Intitulé affiché (facultatif)")}</label>
                <input
                  value={edition.libelle}
                  onChange={(e) => setEdition({ ...edition, libelle: e.target.value })}
                  placeholder={t("à défaut, déduit du champ")}
                  style={inputStyle}
                />
              </>
            ) : null}

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={edition.obligatoire}
                onChange={(e) => setEdition({ ...edition, obligatoire: e.target.checked })}
              />
              {t("Obligatoire (un document sans cette valeur sera signalé)")}
            </label>

            <label style={{ ...champStyle, display: "flex", alignItems: "flex-start", gap: 8 }}>
              <input
                type="checkbox"
                checked={!!edition.identifiant}
                onChange={(e) => setEdition({ ...edition, identifiant: e.target.checked })}
                style={{ marginTop: 2 }}
              />
              <span>
                Ce champ identifie le document
                <span style={{ display: "block", color: "var(--ink-faint)", fontSize: 11.5,
                               lineHeight: 1.5, marginTop: 3 }}>
                  Une facture se reconnaît à son numéro, un bulletin de paie à sa période.
                  Redéposer un document portant la même valeur l'ajoutera comme
                  <strong> version</strong> de la fiche existante, au lieu d'en créer une
                  seconde. Plusieurs champs cochés comptent ensemble : les documents ne se
                  rapprochent que s'ils s'accordent sur tous.
                </span>
              </span>
            </label>

            {/* Ce champ doit-il se remplir tout seul ? (§22.27) Sans cette
                déclaration, l'assemblage annonçait « saisi à la main » aussi bien
                pour un commentaire — c'est très bien — que pour un numéro de
                facture dont la règle manque. */}
            {mode !== "documents" && (
              <label style={{ ...champStyle, display: "flex", alignItems: "flex-start",
                              gap: 8 }}>
                <input
                  type="checkbox"
                  checked={!!edition.extraction_attendue}
                  onChange={(e) => setEdition({ ...edition,
                                                extraction_attendue: e.target.checked })}
                  style={{ marginTop: 2 }}
                />
                <span>
                  Ce champ doit être rempli par une règle d'extraction
                  <span style={{ display: "block", color: "var(--ink-faint)", fontSize: 11.5,
                                 lineHeight: 1.5, marginTop: 3 }}>
                    À cocher pour ce qui <strong>se lit sur le document</strong> — un
                    numéro, un montant, une date. L'assemblage signalera alors qu'il
                    manque une règle, et proposera de l'écrire. Laissez décoché pour ce
                    qui se saisit à la main : un commentaire, une observation.
                  </span>
                </span>
              </label>
            )}

            {/* L'échéance (§21.9). Rien n'arrive tant que personne ne l'a
                déclarée : un rappel qu'on n'a pas demandé se lit comme un bruit,
                exactement comme la déduction du §18.47. */}
            <label style={{ ...champStyle, display: "flex", alignItems: "flex-start", gap: 8 }}>
              <input
                type="checkbox"
                checked={!!edition.echeance}
                onChange={(e) => setEdition({ ...edition, echeance: e.target.checked })}
                style={{ marginTop: 2 }}
              />
              <span>
                Ce champ porte une échéance
                <span style={{ display: "block", color: "var(--ink-faint)", fontSize: 11.5,
                               lineHeight: 1.5, marginTop: 3 }}>
                  {t("Une date qui arrive à terme : fin de validité, limite de paiement, fin de garantie. Le foyer est prévenu avant qu'elle ne passe, et le document apparaît dans l'écran « Échéances ».")}
                </span>
              </span>
            </label>

            {edition.echeance && (
              <>
                <label style={champStyle}>{t("Prévenir combien de jours avant")}</label>
                <input
                  type="number"
                  min="0"
                  max="3650"
                  value={edition.rappel_jours ?? ""}
                  placeholder="30"
                  onChange={(e) => setEdition({ ...edition,
                                                rappel_jours: e.target.value })}
                  style={{ ...inputStyle, width: 140 }}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4 }}>
                  {t("Vide : trente jours — le temps de s'occuper d'une assurance ou d'un contrôle technique sans que le rappel ne devienne du bruit.")}
                </div>
              </>
            )}

            {erreur && (
              <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>
                {erreur}
              </div>
            )}

            <button type="submit" style={boutonPrimaire}>Enregistrer</button>
          </form>
        </Modal>
  );
}

/**
 * Ce qu'un champ à source cherche tout seul dans le texte d'un document (§18.47).
 *
 * Cet automatisme existait déjà, mais en dur et sans rien en dire : un champ
 * rattaché à une table voyait l'application chercher les colonnes identifiantes
 * de cette table dans chaque document. C'était juste dans le cas prévu — prénom
 * et nom pour un membre du foyer — et invisible dans tous les autres. Un
 * titulaire apparaissait sans que personne ne l'ait demandé.
 *
 * Il se déclare donc, champ par champ. Sans déclaration, le champ reste vide et
 * se remplit au Centre d'analyse, ce qui est le comportement le moins surprenant.
 */
/**
 * Ce qui se lit d'une ligne choisie (§22.59).
 *
 * Une table déclare déjà ses colonnes identifiantes, et c'est ce qui composait
 * l'affichage partout. Un réglage unique par table, donc — alors que le même
 * véhicule se lit « AA-123-BB » sous « Véhicule concerné » et
 * « Clio III · AA-123-BB » dans un sélecteur où l'on cherche la bonne voiture.
 *
 * Ce choix appartient au champ : c'est lui qui sait ce qu'on vient y chercher.
 * Rien de coché veut dire « comme la table le déclare » — l'état de tout champ
 * existant, et celui vers lequel on revient en décochant tout.
 */
function Affichage({ edition, setEdition, source }) {
  const choisies = edition.colonnes_affichees || [];
  const disponibles = source?.colonnes || [];
  const identifiantes = source?.colonnes_identifiantes || [];

  function basculer(nom) {
    setEdition({
      ...edition,
      colonnes_affichees: choisies.includes(nom)
        ? choisies.filter((c) => c !== nom)
        : [...choisies, nom],
    });
  }

  if (!source) return null;

  return (
    <div style={{ marginTop: 16 }}>
      <label style={{ ...champStyle, marginTop: 0 }}>{t("Valeurs affichées")}</label>
      {disponibles.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
          {t("Cette table n'a aucune colonne à afficher.")}
        </div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {disponibles.map((nom) => {
            // Le rang, et non une simple coche : l'ordre des colonnes compose
            // la valeur lue, et un ordre qui ne se voit pas se règle à l'aveugle
            // (§22.60). Cliquer une colonne déjà choisie la retire ; la
            // reprendre la remet en fin de file.
            const rang = choisies.indexOf(nom);
            const active = rang >= 0;
            return (
              <button
                key={nom}
                type="button"
                onClick={() => basculer(nom)}
                title={active
                  ? t("En position {rang} — cliquer pour la retirer", { rang: rang + 1 })
                  : t("Ajouter en fin de composition")}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  border: `1px solid ${active ? "var(--accent)" : "var(--line-strong)"}`,
                  background: active ? "var(--accent-soft)" : "transparent",
                  color: active ? "var(--accent)" : "var(--ink-soft)",
                  borderRadius: 12, padding: "3px 10px", fontSize: 12,
                }}
              >
                {active && (
                  <span className="tabular"
                        style={{ fontWeight: 700, fontSize: 10.5, minWidth: 9,
                                 textAlign: "center" }}>
                    {rang + 1}
                  </span>
                )}
                {nom}
              </button>
            );
          })}
        </div>
      )}
      {choisies.length > 1 && (
        <div style={{ fontSize: 11.5, color: "var(--ink-soft)", marginTop: 6 }}>
          {t("Aperçu :")}{" "}
          <span style={{ fontFamily: "var(--font-mono)" }}>{choisies.join(" - ")}</span>
        </div>
      )}
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6, lineHeight: 1.45 }}>
        {choisies.length > 0
          ? t("Dans l'ordre des numéros, séparées par un tiret — c'est ce qu'on lira dans le registre, sur la fiche et dans les menus de recherche.")
          : t("Rien de coché : ce que la table déclare, soit {colonnes}. Cochez pour choisir autre chose ici — le réglage ne vaut que pour ce champ.",
            { colonnes: identifiantes.join(" + ") || t("sa colonne d'affichage") })}
      </div>
    </div>
  );
}

function Deduction({ edition, setEdition, source }) {
  const mode = edition.deduction || "aucune";
  const choisies = edition.colonnes_deduction || [];
  const disponibles = source?.colonnes || [];
  const identifiantes = source?.colonnes_identifiantes || [];

  function changerMode(valeur) {
    setEdition({
      ...edition,
      deduction: valeur,
      // en activant, on propose les colonnes qui identifient déjà la table :
      // c'est à elles qu'on reconnaît une ligne, c'est donc là qu'il faut chercher
      colonnes_deduction: valeur !== "aucune" && choisies.length === 0
        ? identifiantes : choisies,
    });
  }

  function basculer(nom) {
    setEdition({
      ...edition,
      colonnes_deduction: choisies.includes(nom)
        ? choisies.filter((c) => c !== nom)
        : [...choisies, nom],
    });
  }

  return (
    <div style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
      <label style={{ ...champStyle, marginTop: 0 }}>{t("Déduire la valeur du document")}</label>
      <Liste
        valeur={mode}
        ariaLabel={t("Déduction automatique")}
        options={DEDUCTIONS().map((d) => ({ valeur: d.valeur, libelle: d.libelle }))}
        onChange={changerMode}
      />
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.45 }}>
        À la mise en registre, le texte du document est cherché : quand il désigne une
        ligne <strong>et une seule</strong>, le champ est rempli. Deux lignes désignées,
        ou aucune, et le champ reste vide — on ne devine pas à la place de quelqu'un.
      </div>

      {mode !== "aucune" && (
        <div style={{ marginTop: 12 }}>
          <label style={{ ...champStyle, marginTop: 0 }}>{t("Colonnes cherchées dans le document")}</label>
          {disponibles.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
              {t("Choisissez d'abord une table source.")}
            </div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {disponibles.map((nom) => {
                const active = choisies.includes(nom);
                return (
                  <button
                    key={nom}
                    type="button"
                    onClick={() => basculer(nom)}
                    style={{
                      border: `1px solid ${active ? "var(--accent)" : "var(--line-strong)"}`,
                      background: active ? "var(--accent-soft)" : "transparent",
                      color: active ? "var(--accent)" : "var(--ink-soft)",
                      borderRadius: 12, padding: "3px 10px", fontSize: 12,
                    }}
                  >
                    {nom}
                  </button>
                );
              })}
            </div>
          )}
          <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6, lineHeight: 1.45 }}>
            {mode === "toutes" ? (
              <>
                Toutes doivent figurer dans le document. Pour une personne, c'est
                <code> prenom</code> <strong>et</strong> <code>nom</code> : deux membres d'une
                même famille portent le même nom, « Dupont » seul ne désigne personne.
              </>
            ) : (
              <>
                {t("Une seule trouvée suffit. À réserver aux valeurs qui ne se répètent pas ailleurs — une immatriculation, un numéro de contrat. Sur un nom de famille, ce réglage rattacherait la mauvaise personne.")}
              </>
            )}
            {choisies.length === 0 && (
              <> Aucune colonne cochée : les colonnes identifiantes de la table
              {identifiantes.length > 0 && <> (<code>{identifiantes.join(", ")}</code>)</>} servent.</>
            )}
          </div>

          {/* La tolérance se déclare, et ne se prend jamais d'elle-même (§21.4) :
              elle rattrape un scan médiocre sur un nom, et confondrait deux
              véhicules sur une immatriculation. */}
          <label style={{ display: "flex", alignItems: "flex-start", gap: 8,
                          marginTop: 12, fontSize: 12.5 }}>
            <input
              type="checkbox"
              checked={!!edition.deduction_approchee}
              onChange={(e) => setEdition({ ...edition,
                                            deduction_approchee: e.target.checked })}
              style={{ marginTop: 2 }}
            />
            <span>
              Tolérer une lettre de différence
              <span style={{ display: "block", fontSize: 11, color: "var(--ink-faint)",
                             marginTop: 2, lineHeight: 1.45 }}>
                {t("Un scan lit « 0range » pour « Orange », « Dupond » pour « Dupont ». À réserver aux noms : sur une immatriculation ou un numéro de contrat, une lettre sépare deux lignes différentes. Les mots courts restent exacts quoi qu'il arrive.")}
              </span>
            </span>
          </label>
        </div>
      )}
    </div>
  );
}
