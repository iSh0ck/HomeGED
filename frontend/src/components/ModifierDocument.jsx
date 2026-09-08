import React, { useEffect, useRef, useState } from "react";
import { Lock, ShieldAlert } from "lucide-react";
import { api } from "../api";
import Modal from "./Modal.jsx";
import Liste from "./champs/Liste.jsx";
import ChoisirDocuments from "./ChoisirDocuments.jsx";
import ChampDate from "./champs/ChampDate.jsx";
import { aplatirArborescence } from "../lib/arborescence";
import { libelleDocument } from "../lib/document";
import { t } from "../lib/langue";

// Le verrou vaut cinq minutes côté API : on le prolonge à mi-parcours, pour
// qu'une saisie longue ne se retrouve pas invalidée au moment d'enregistrer.
const PROLONGATION_MS = 2 * 60 * 1000;

/**
 * Fenêtre de modification d'un document.
 *
 * La fiche est en lecture seule ; c'est ici, et seulement ici, qu'on écrit. Ce
 * n'est pas une contrainte gratuite : l'ouverture prend un **verrou** sur le
 * document, ce qui empêche deux personnes du foyer de corriger la même facture
 * en même temps et d'effacer mutuellement leur travail sans le savoir.
 *
 * Le verrou est prolongé tant que la fenêtre reste ouverte, et rendu à sa
 * fermeture — y compris quand on ferme l'onglet, autant que le navigateur nous
 * en laisse l'occasion. S'il ne l'est pas, il expire de lui-même : un document
 * ne reste jamais bloqué.
 */
export default function ModifierDocument({
  doc, categories, onFerme, onEnregistre,
  // Modification en série (§18.4) : `progression` situe la fiche dans la
  // sélection ({ rang, total }), `onPasser` laisse en sauter une sans y toucher.
  progression, onPasser,
}) {
  const [verrou, setVerrou] = useState(null);      // null = en cours d'obtention
  const [refus, setRefus] = useState(null);
  const [valeurs, setValeurs] = useState(() => ({
    categorie_id: doc.categorie_id ?? "",
    date_document: doc.date_document || "",
    metadonnees: { ...doc.metadonnees },
    // Ce que cette entrée retient de chaque valeur de table (§22.61). Vide pour
    // un champ veut dire « tout ce que l'administrateur propose ».
    affichages: { ...(doc.affichages || {}) },
  }));
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState(null);
  const relache = useRef(false);
  // Le contenu des champs qui attachent des documents (§22.11). Chargé à part :
  // ce sont des liens vers des fiches existantes, pas des valeurs de formulaire.
  const [attaches, setAttaches] = useState({});

  // --- prise et entretien du verrou
  useEffect(() => {
    let vivant = true;
    api
      .prendreVerrou(doc.id)
      .then((v) => { if (vivant) setVerrou(v); })
      .catch((e) => { if (vivant) setRefus(e.message); });

    const minuterie = setInterval(() => {
      api.prendreVerrou(doc.id).catch(() => {});
    }, PROLONGATION_MS);

    // Fermeture de l'onglet : on tente de rendre le verrou. Si le navigateur ne
    // nous en laisse pas le temps, l'expiration s'en chargera.
    const auDepart = () => { api.rendreVerrou(doc.id).catch(() => {}); };
    window.addEventListener("beforeunload", auDepart);

    return () => {
      vivant = false;
      clearInterval(minuterie);
      window.removeEventListener("beforeunload", auDepart);
      if (!relache.current) api.rendreVerrou(doc.id).catch(() => {});
    };
  }, [doc.id]);

  useEffect(() => {
    api.attaches(doc.id)
      .then((r) => setAttaches(Object.fromEntries(
        (r.attaches || []).map((champ) => [champ.champ, champ.documents]))))
      .catch(() => {});
  }, [doc.id]);

  function definirMeta(cle, valeur) {
    setValeurs((v) => ({ ...v, metadonnees: { ...v.metadonnees, [cle]: valeur } }));
  }

  async function enregistrer(evenement) {
    evenement.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      await api.patchDocument(doc.id, {
        categorie_id: valeurs.categorie_id === "" ? null : Number(valeurs.categorie_id),
        date_document: valeurs.date_document || null,
        metadonnees: {
          ...valeurs.metadonnees,
          // La date corrigée à la main est recopiée dans la métadonnée qui la
          // double (§22.79) : c'est elle que le rejeu consulte, et la laisser à
          // l'ancienne valeur ferait revenir la date d'avant cinq minutes plus
          // tard. Écrire par cette porte pose « corrigé à la main » du même coup.
          ...("date_document" in valeurs.metadonnees
            ? { date_document: valeurs.date_document || "" } : {}),
        },
        affichages: valeurs.affichages,
      });
      // Les documents attachés partent après la fiche : ils portent sur elle,
      // et la fiche doit exister dans l'état qu'on vient d'enregistrer.
      for (const [champ, choisis] of Object.entries(attaches)) {
        await api.definirAttaches(doc.id, champ, (choisis || []).map((d) => d.id));
      }
      relache.current = true;
      await api.rendreVerrou(doc.id).catch(() => {});
      onEnregistre?.();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  if (refus) {
    return (
      <Modal titre={t("Document en cours de modification")} onClose={onFerme} width={430}>
        <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
          <ShieldAlert size={18} color="var(--amber)" style={{ flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.55 }}>
            {refus}
            <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-faint)" }}>
              {t("Le verrou se libère de lui-même après quelques minutes d'inactivité.")}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>
          <button onClick={onFerme} style={boutonSecondaire}>Fermer</button>
        </div>
      </Modal>
    );
  }

  const attendus = doc.champs_attendus || [];
  // Métadonnées présentes mais non déclarées par la catégorie : elles restent
  // modifiables, sinon une valeur extraite deviendrait intouchable.
  const cles = attendus.filter((c) => c.champ.startsWith("meta:")).map((c) => c.champ.slice(5));
  // `date_document` fait exception (§22.79). Une règle qui la cible écrit **deux
  // choses** : la colonne du document, pour le tri et la recherche, et une
  // métadonnée du même nom — celle-ci porte « corrigé à la main », le garde-fou
  // sans lequel le rejeu automatique écraserait une date qu'on vient de corriger
  // (§18.45). Elle a sa raison d'être, mais pas sa case : on se retrouvait avec
  // « Date du document » et « date document », deux champs pour une valeur.
  const autres = Object.keys(valeurs.metadonnees)
    .filter((c) => !cles.includes(c) && c !== "date_document");

  const enSerie = Boolean(progression && progression.total > 1);
  const reste = enSerie && progression.rang < progression.total;

  return (
    <Modal
      titre={enSerie
        ? `Modifier — fiche ${progression.rang} sur ${progression.total}`
        : t("Modifier le document")}
      onClose={onFerme}
      width={520}
    >
      {enSerie && (
        <div style={{ marginTop: 4, marginBottom: 10 }}>
          <div style={{
            fontSize: 12, color: "var(--ink-soft)", marginBottom: 6,
            display: "flex", justifyContent: "space-between", gap: 10,
          }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {libelleDocument(doc)}
            </span>
            <span className="tabular" style={{ flexShrink: 0, color: "var(--ink-faint)" }}>
              {progression.rang} / {progression.total}
            </span>
          </div>
          {/* Une barre plutôt qu'un simple compteur : on veut voir d'un coup
              d'œil ce qu'il reste à traiter avant de s'engager dans la série. */}
          <div style={{ height: 3, borderRadius: 2, background: "var(--line)" }}>
            <div style={{
              height: "100%", borderRadius: 2, background: "var(--accent)",
              width: `${Math.round((progression.rang / progression.total) * 100)}%`,
            }} />
          </div>
        </div>
      )}

      <div style={{
        display: "flex", alignItems: "center", gap: 7, fontSize: 11.5,
        color: verrou ? "var(--accent)" : "var(--ink-faint)", marginTop: 2,
      }}>
        <Lock size={12} />
        {verrou ? t("Vous modifiez ce document ; personne d'autre ne peut le faire pendant ce temps.")
                : t("Prise du verrou…")}
      </div>

      <form onSubmit={enregistrer} style={{ marginTop: 16 }}>
        <Champ label={t("Catégorie")}>
          <Liste
            valeur={valeurs.categorie_id}
            ariaLabel={t("Catégorie")}
            placeholder={t("Non classé")}
            options={[{ valeur: "", libelle: t("Non classé") },
                      ...aplatirArborescence(categories || []).map((c) => ({
                        valeur: c.id,
                        libelle: `${" ".repeat(c.profondeur * 3)}${c.nom}`,
                      }))]}
            onChange={(v) => setValeurs((x) => ({ ...x, categorie_id: v }))}
          />
        </Champ>

        {/* Plus de champ « Émetteur » ici (§21.12) : c'est un champ attendu
            comme un autre, rendu plus bas avec ceux du type — et il ne s'affiche
            que si ce type en déclare un. */}

        {/* En modification en série (§18.4), le serveur ne détaille pas les
            champs du type : la date garde alors sa case, elle vaut pour tout
            document. */}
        {attendus.length === 0 && (
          <Champ label={t("Date du document")}>
            <ChampDate
              valeur={valeurs.date_document}
              ariaLabel={t("Date du document")}
              onChange={(v) => setValeurs((x) => ({ ...x, date_document: v }))}
            />
          </Champ>
        )}

        {attendus.map((champ) => {
          // La date du document n'est pas une métadonnée mais une colonne du
          // document. Elle s'affiche donc **à sa place**, dans l'ordre que
          // l'administration a déclaré (§22.77), et non dans un bloc figé en
          // tête de formulaire — où elle avait l'air ajoutée par l'application
          // alors qu'elle est un champ attendu comme les autres.
          if (champ.champ === "date_document") {
            return (
              <Champ key="date_document" label={t(champ.libelle)}
                     obligatoire={champ.obligatoire}>
                <ChampDate
                  valeur={valeurs.date_document}
                  ariaLabel={t(champ.libelle)}
                  onChange={(v) => setValeurs((x) => ({ ...x, date_document: v }))}
                />
              </Champ>
            );
          }
          if (!champ.champ.startsWith("meta:")) return null;
          const cle = champ.champ.slice(5);
          // Un champ qui attache des documents ne se saisit pas : on pioche dans
          // ce qui est déjà classé (§22.11).
          if (champ.attache_documents) {
            return (
              <Champ key={cle} label={t(champ.libelle)} obligatoire={champ.obligatoire}>
                <ChoisirDocuments
                  valeur={attaches[champ.champ] || []}
                  ariaLabel={t(champ.libelle)}
                  categorieId={doc.categorie_id}
                  champ={champ.champ}
                  sauf={doc.id}
                  onChange={(liste) =>
                    setAttaches((courant) => ({ ...courant, [champ.champ]: liste }))}
                />
              </Champ>
            );
          }
          return (
            <Champ key={cle} label={t(champ.libelle)} obligatoire={champ.obligatoire}>
              <SaisieChamp
                champ={champ}
                valeur={valeurs.metadonnees[cle] ?? ""}
                onChange={(v) => definirMeta(cle, v)}
                affichage={valeurs.affichages[champ.champ]}
                onAffichage={(colonnes) => setValeurs((v) => ({
                  ...v, affichages: { ...v.affichages, [champ.champ]: colonnes },
                }))}
              />
            </Champ>
          );
        })}

        {autres.map((cle) => (
          <Champ key={cle} label={cle.replace(/_/g, " ")}>
            <input
              value={valeurs.metadonnees[cle] ?? ""}
              onChange={(e) => definirMeta(cle, e.target.value)}
              style={saisieStyle}
            />
          </Champ>
        ))}

        {erreur && (
          <div style={{
            marginTop: 12, padding: "8px 11px", borderRadius: "var(--radius)",
            background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5,
          }}>
            {erreur}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <button type="button" onClick={onFerme} style={boutonSecondaire}>
            {enSerie ? t("Arrêter") : "Annuler"}
          </button>
          {enSerie && reste && (
            <button type="button" onClick={onPasser} style={boutonSecondaire}>
              Passer
            </button>
          )}
          <button type="submit" disabled={envoi || !verrou}
                  style={{ ...boutonPrimaire, opacity: envoi || !verrou ? 0.6 : 1 }}>
            {envoi ? "Enregistrement…" : reste ? t("Enregistrer et suivant") : "Enregistrer"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * Le contrôle dépend de ce que la catégorie déclare : liste, date ou texte.
 *
 * Un champ peut puiser dans **plusieurs sources** (§17.28) — les comptes de la
 * GED et les personnes du foyer sans compte, par exemple. Les entrées sont donc
 * regroupées par source, et leur valeur porte celle-ci en préfixe :
 * `usr_membres:3`. Sans ce préfixe, la ligne nº3 de deux sources différentes
 * serait indiscernable.
 *
 * La recherche est toujours proposée, et repart chercher côté serveur à chaque
 * frappe : une source peut être courte aujourd'hui et longue demain, et le
 * filtrage local ne verrait alors que les premières entrées chargées.
 */
export function SaisieChamp({ champ, valeur, onChange, affichage, onAffichage }) {
  const [options, setOptions] = useState(null);
  const [recherche, setRecherche] = useState("");
  const sources = champ.sources?.length ? champ.sources : [champ.source_table].filter(Boolean);

  useEffect(() => {
    if (!sources.length) return undefined;
    let annule = false;
    const minuterie = setTimeout(() => {
      Promise.all(sources.map((source) =>
        api.references(source, recherche,
                       { categorieId: champ.categorie_id, champ: champ.champ })
          .then((lignes) => lignes.map((o) => ({ source, ...o })))
          .catch(() => [])))
        .then((lots) => { if (!annule) setOptions(lots.flat()); });
    }, recherche ? 180 : 0);   // un court délai pendant la frappe, immédiat à l'ouverture
    return () => { annule = true; clearTimeout(minuterie); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(sources), recherche]);

  if (sources.length) {
    return (
      <>
        <Liste
          recherchable
          valeur={valeur}
          ariaLabel={t(champ.libelle)}
          placeholder={options ? "— Choisir —" : "Chargement…"}
          onRecherche={setRecherche}
          options={[
            { valeur: "", libelle: t("— Aucun —") },
            ...(options || []).map((o) => ({
              valeur: `${o.source}:${o.valeur}`,
              libelle: o.complement ? `${t(o.libelle)} — ${o.complement}` : o.libelle,
              groupe: sources.length > 1 ? t(LIBELLES_SOURCE[o.source] || o.source) : undefined,
            })),
          ]}
          onChange={onChange}
        />
        <ColonnesMontrees
          palette={champ.colonnes_affichees || []}
          choisies={affichage}
          onChange={onAffichage}
        />
      </>
    );
  }
  // Le **type déclaré** commande, et le nom du champ ne sert plus qu'à défaut :
  // deviner d'après « date_facture » marchait, deviner d'après « echeance » non
  // (§22.12).
  const type = champ.type_champ || (/date/.test(champ.champ) ? "date" : "texte");
  if (type === "date") {
    return <ChampDate valeur={valeur} ariaLabel={t(champ.libelle)} onChange={onChange} />;
  }
  if (type === "texte_long") {
    return (
      <textarea
        value={valeur}
        aria-label={t(champ.libelle)}
        rows={4}
        onChange={(e) => onChange(e.target.value)}
        style={{ ...saisieStyle, resize: "vertical", lineHeight: 1.5 }}
      />
    );
  }
  if (type === "booleen") {
    return (
      <Liste
        valeur={valeur === "" ? "" : String(valeur)}
        ariaLabel={t(champ.libelle)}
        options={[{ valeur: "", libelle: t("— Non renseigné —") },
                  { valeur: "oui", libelle: "Oui" }, { valeur: "non", libelle: "Non" }]}
        onChange={onChange}
      />
    );
  }
  if (type === "nombre" || type === "montant") {
    return (
      <input
        value={valeur}
        aria-label={t(champ.libelle)}
        inputMode="decimal"
        placeholder={type === "montant" ? "0,00" : ""}
        onChange={(e) => onChange(e.target.value)}
        // Aligné à gauche comme les autres champs du formulaire (§22.76) : dans
        // un tableau, aligner les montants à droite fait tomber les unités les
        // unes sous les autres ; dans un formulaire, il n'y a qu'une valeur, et
        // la coller au bord droit l'éloigne de son intitulé sans rien apporter.
        // Les chiffres gardent leur chasse fixe, qui, elle, sert toujours.
        style={{ ...saisieStyle, fontVariantNumeric: "tabular-nums" }}
      />
    );
  }
  return <input value={valeur} aria-label={t(champ.libelle)}
                onChange={(e) => onChange(e.target.value)} style={saisieStyle} />;
}

// Intitulés des sources connues. Une source inconnue s'affiche par son nom
// technique plutôt que de disparaître.
/** @traduit-a-la-lecture */
const LIBELLES_SOURCE = {
  sys_utilisateurs: "Comptes de la GED",
  usr_membres: "Membres du foyer",
};

/**
 * Ce que cette ligne-ci montre de la valeur choisie (§22.61).
 *
 * L'administrateur décide de ce qu'une valeur de table peut donner à lire
 * (§22.59) ; celui qui saisit décide de ce qui mérite la place d'une colonne
 * sur **cette entrée-là**. Le modèle du véhicule éclaire une ligne d'entretien
 * et encombre la suivante — c'est un jugement, pas un réglage de foyer.
 *
 * Rien n'apparaît quand il n'y a rien à arbitrer : palette d'une seule colonne,
 * ou champ sans table source.
 */
function ColonnesMontrees({ palette, choisies, onChange }) {
  if (!onChange || palette.length < 2) return null;
  // Vide veut dire « tout » : c'est l'état de toute entrée existante, et il ne
  // faut pas qu'il se lise comme « rien de coché ».
  const retenues = choisies && choisies.length ? choisies : palette;

  function basculer(nom) {
    const suite = retenues.includes(nom)
      ? retenues.filter((c) => c !== nom)
      : palette.filter((c) => retenues.includes(c) || c === nom);
    // Tout décocher n'a pas de sens : la colonne n'aurait plus rien à montrer.
    onChange(suite.length ? suite : palette);
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6,
                  marginTop: 5 }}>
      <span style={{ fontSize: 11, color: "var(--ink-faint)" }}>{t("Montrer :")}</span>
      {palette.map((nom) => {
        const active = retenues.includes(nom);
        return (
          <button
            key={nom}
            type="button"
            onClick={() => basculer(nom)}
            title={active ? t("Retirer de la colonne") : t("Montrer dans la colonne")}
            style={{
              border: `1px solid ${active ? "var(--accent)" : "var(--line-strong)"}`,
              background: active ? "var(--accent-soft)" : "transparent",
              color: active ? "var(--accent)" : "var(--ink-faint)",
              borderRadius: 10, padding: "1px 8px", fontSize: 11,
            }}
          >
            {nom}
          </button>
        );
      })}
    </div>
  );
}


export function Champ({ label, obligatoire, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: "block", fontSize: 12, color: "var(--ink-soft)", marginBottom: 4 }}>
        {label}
        {obligatoire && <span style={{ color: "var(--brick)" }} title="Obligatoire"> *</span>}
      </label>
      {children}
    </div>
  );
}

const saisieStyle = {
  width: "100%", padding: "8px 10px", fontSize: 13,
  border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)", color: "var(--ink)", fontFamily: "inherit",
};

const boutonPrimaire = {
  border: "none", background: "var(--accent)", color: "#fff",
  borderRadius: "var(--radius)", padding: "8px 14px", fontSize: 13, fontWeight: 600,
  cursor: "pointer",
};

const boutonSecondaire = {
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "8px 14px", fontSize: 13, cursor: "pointer",
};
