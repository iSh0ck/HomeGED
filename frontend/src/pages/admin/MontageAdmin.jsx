import React, { useEffect, useState } from "react";
import { AlertTriangle, Check, ChevronRight, Plus, Trash2 } from "lucide-react";
import { adminApi } from "../../api";
import Liste from "../../components/champs/Liste.jsx";
import { champStyle } from "../../components/Modal.jsx";
import EditeurChampAttendu from "../../components/EditeurChampAttendu.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import { t } from "../../lib/langue";

/**
 * Assembler un type de document (§22.16).
 *
 * Les trois écrans qui décrivent un type — champs attendus, colonnes, règles
 * d'extraction — sont rangés par **objet technique**, alors qu'on les parcourt
 * par **intention**. Configurer un type demandait donc d'aller de l'un à l'autre
 * sans que rien ne dise lequel fait quoi, ni dans quel ordre les prendre : on y
 * arrivait par tâtonnement, ce qui est le plus sûr moyen de croire qu'un
 * logiciel est compliqué.
 *
 * Cette page ne remplace pas les trois autres — elles gardent leur vue
 * transversale, utile quand on cherche « tous les types qui exigent un montant ».
 * Elle donne le **chemin** : un type, quatre étapes numérotées, et à chaque
 * étape ce qui est déjà fait et ce qui manque.
 *
 * L'ordre n'est pas décoratif. Les champs viennent d'abord parce que tout en
 * découle : les colonnes se choisissent parmi eux, les règles les remplissent,
 * l'échéance et l'identifiant sont des propriétés des champs. Commencer par les
 * colonnes, comme on le faisait souvent, revenait à choisir ce qu'on affiche
 * avant de savoir ce qu'on a.
 */
export default function MontageAdmin({ onOuvrirEcran }) {
  const [categories, setCategories] = useState([]);
  const [categorieId, setCategorieId] = useState(null);
  const [regles, setRegles] = useState([]);
  const [colonnes, setColonnes] = useState([]);
  // Ce que le tableau montre **pour de bon** (§22.87). La case disait ce qui
  // était configuré, ce qui n'est pas la même chose : un champ attendu déclaré
  // et jamais réglé s'invite dans le tableau, et la case le donnait pourtant
  // pour absent. « Ce qu'on voit dans le tableau » doit dire ce qu'on voit.
  const [effectives, setEffectives] = useState([]);
  // Ce qu'une règle d'extraction vise déjà pour ce type : c'est ce qui distingue
  // « rempli tout seul » de « saisi à la main ».
  const [cibles, setCibles] = useState([]);
  const [edition, setEdition] = useState(null);
  const [suppression, setSuppression] = useState(null);
  const [erreur, setErreur] = useState(null);
  // Ce qui vient d'être enregistré (§22.25). L'écran écrit à chaque geste : sans
  // rien dire, on cherche un bouton « Enregistrer » qui n'existe pas — et l'on
  // n'ose pas quitter la page.
  const [confirme, setConfirme] = useState(null);

  useEffect(() => {
    adminApi.categories()
      .then((toutes) => {
        // Un dossier organise mais ne porte aucun document (§19.1) : il n'a rien
        // à assembler.
        const porteuses = toutes.filter((c) => (c.nature || "type") !== "dossier");
        setCategories(porteuses);
        if (porteuses.length && categorieId === null) setCategorieId(porteuses[0].id);
      })
      .catch((e) => setErreur(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function charger() {
    if (!categorieId) return;
    adminApi.reglesChamps(categorieId).then(setRegles).catch((e) => setErreur(e.message));
    // `/admin/categories/{id}/colonnes` rend un **objet** — ce qui est
    // configuré, ce qui s'affiche effectivement, ce qui est proposable. Le
    // prendre pour un tableau faisait tomber l'écran entier sur
    // « s.filter is not a function ».
    adminApi.colonnesCategorie(categorieId)
      .then((reponse) => {
        setColonnes(reponse.configurees || []);
        setEffectives(reponse.effectives || []);
      })
      .catch(() => {});
    adminApi.champsCibles(categorieId).then(setCibles).catch(() => {});
  }
  useEffect(charger, [categorieId]);

  const categorie = categories.find((c) => c.id === categorieId);
  const visibles = new Set(effectives.map((c) => c.champ));
  const remplis = new Set(cibles.filter((c) => c.remplie_par_regle).map((c) => c.champ));
  // Quelle règle remplit quoi (§22.28) : savoir qu'un champ se remplit tout seul
  // ne dit pas où aller quand il se remplit mal.
  const reglesParChamp = new Map(cibles.map((c) => [c.champ, c.regles || []]));

  async function basculerColonne(champ, actif) {
    setErreur(null);
    // Décocher **masque**, il n'efface pas (§22.87). Un champ attendu déclaré
    // par le type s'invite dans le tableau quand rien ne le mentionne — c'est
    // voulu : une exigence ajoutée après coup doit se voir. Retirer la ligne
    // faisait donc revenir la colonne au chargement suivant, et la décision
    // qu'on venait de prendre ne tenait pas. Une ligne masquée, elle, est une
    // décision : elle dit « ce champ, on l'a vu, et on n'en veut pas ici ».
    const suite = colonnes.some((c) => c.champ === champ)
      ? colonnes.map((c) => (c.champ === champ ? { ...c, visible: actif } : c))
      : [...colonnes, { champ, libelle: null, largeur: null, visible: actif }];
    try {
      await adminApi.enregistrerColonnes(categorieId, suite.map((c, rang) => ({
        champ: c.champ, libelle: c.libelle ?? null,
        largeur: c.largeur ?? null, visible: c.visible !== false, ordre: rang,
      })));
      annoncer(actif ? t("Colonne ajoutée") : t("Colonne retirée"));
      charger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  /**
   * Ouvre ce qui remplit ce champ (§22.28).
   *
   * Une règle d'extraction : on va à **la règle**, dans son jeu, formulaire
   * ouvert. Une déduction : elle se règle sur le champ lui-même, et c'est donc
   * l'éditeur du champ qu'on ouvre. Dans les deux cas, on arrive là où la chose
   * se corrige — c'est tout ce qu'on demande à un raccourci.
   */
  function ouvrirCeQuiRemplit(regle) {
    if (regle.deduction && regle.deduction !== "aucune") {
      setEdition(regle);
      return;
    }
    const cible = regle.champ.replace(/^meta:/, "");
    const [premiere] = reglesParChamp.get(cible) || [];
    onOuvrirEcran?.("regles", {
      categorieId,
      jeuId: premiere?.profil_id,
      regleId: premiere?.id,
      champCible: premiere ? undefined : cible,
    });
  }

  /** Dit ce qui vient d'être écrit, puis s'efface : une trace, pas un bandeau. */
  function annoncer(texte) {
    setConfirme(texte);
    setTimeout(() => setConfirme((courant) => (courant === texte ? null : courant)), 2500);
  }

  async function supprimerChamp() {
    try {
      await adminApi.supprimerRegleChamp(suppression.id);
      setSuppression(null);
      annoncer(t("Champ retiré"));
      charger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  return (
    <div>
      <h2 style={{ fontSize: 16, margin: "0 0 6px" }}>{t("Assembler un type de document")}</h2>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55,
                  maxWidth: 720, marginTop: 0 }}>
        {t("Tout ce qui décrit un type, dans l'ordre où l'on y pense. Les champs d'abord : les colonnes se choisissent parmi eux, les règles les remplissent, et les échéances sont des propriétés des champs. Chaque étape reste modifiable depuis son écran habituel.")}
      </p>
      {/* Dit une fois, en tête : il n'y a pas de bouton « Enregistrer » à
          chercher, et rien ne se perd en quittant la page (§22.25). */}
      <p style={{ fontSize: 12, color: "var(--ink-faint)", lineHeight: 1.5,
                  maxWidth: 720, marginTop: 0 }}>
        <strong>{t("Chaque choix est enregistré aussitôt")}</strong> — cocher une colonne, ajouter
        ou retirer un champ prend effet immédiatement. Il n'y a rien à valider en partant.
      </p>

      <label style={{ ...champStyle, marginTop: 14 }}>{t("Type de document")}</label>
      <Liste
        valeur={categorieId ?? ""}
        ariaLabel={t("Type de document à assembler")}
        style={{ maxWidth: 320 }}
        options={categories.map((c) => ({ valeur: c.id, libelle: c.nom }))}
        onChange={(v) => setCategorieId(Number(v))}
      />

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}
      {confirme && !erreur && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 5, marginTop: 10,
                      fontSize: 12, color: "var(--accent)" }}>
          <Check size={13} /> {confirme}
        </div>
      )}

      {/* ---------------------------------------------------------------- */}
      <Etape numero={1} titre={t("Ce que le document porte")}
             resume={regles.length
               ? `${regles.length} champ(s) déclaré(s)`
               : t("aucun champ — c'est par là qu'il faut commencer")}
             fait={regles.length > 0}
             aide="Un champ attendu dit ce qu'un document de ce type doit porter. Tout le
                   reste en découle : ce qu'on affiche, ce qui se remplit tout seul, ce
                   qui arrive à terme.">
        {regles.map((r) => (
          <div key={r.id} style={ligne}>
            <span style={{ flex: 1, minWidth: 0 }}>
              {r.libelle_effectif}
              <span style={{ color: "var(--ink-faint)" }}>
                {" · "}{decrireNature(r)}
              </span>
              {r.obligatoire && (
                <span style={{ color: "var(--amber)", fontSize: 11 }}> · obligatoire</span>
              )}
            </span>
            <button onClick={() => setEdition(r)} style={boutonDiscret}>Modifier</button>
            <button onClick={() => setSuppression(r)} style={boutonDiscret}
                    aria-label={`Retirer ${r.libelle_effectif}`}>
              <Trash2 size={12} />
            </button>
          </div>
        ))}
        <button onClick={() => setEdition({ ordre: (regles.length + 1) * 10 })}
                style={{ ...boutonDiscret, marginTop: 6 }}>
          <Plus size={12} /> Ajouter un champ
        </button>
      </Etape>

      {/* ---------------------------------------------------------------- */}
      <Etape numero={2} titre={t("Ce qu'on voit dans le tableau")}
             resume={visibles.size
               ? `${visibles.size} colonne(s)`
               : t("aucune colonne réglée — le tableau se débrouille tout seul")}
             fait={visibles.size > 0}
             aide="Sans réglage, le tableau devine des colonnes à partir des champs et des
                   valeurs trouvées. Les cocher ici, c'est décider ce qu'on lit d'un coup
                   d'œil — et dans quel ordre.">
        {regles.length === 0 ? (
          <div style={vide}>{t("Déclarez d'abord des champs : il n'y a rien à afficher.")}</div>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {regles.map((r) => (
              <label key={r.id} style={{ display: "inline-flex", alignItems: "center",
                                         gap: 6, fontSize: 12.5 }}>
                <input
                  type="checkbox"
                  aria-label={r.libelle_effectif}
                  checked={visibles.has(r.champ)}
                  onChange={(e) => basculerColonne(r.champ, e.target.checked)}
                />
                {r.libelle_effectif}
              </label>
            ))}
          </div>
        )}
      </Etape>

      {/* ---------------------------------------------------------------- */}
      <Etape numero={3} titre={t("Ce qui se remplit tout seul")}
             resume={decrireTrois(regles, remplis)}
             fait={regles.length > 0 && aParametrer(regles, remplis).length === 0}
             aide="Une règle d'extraction lit le texte du document et écrit dans un champ.
                   Un champ qu'on a déclaré comme devant se remplir tout seul et qu'aucune
                   règle ne vise est un réglage qui manque — et non un champ qu'on saisira
                   à la main.">
        {regles.length === 0 ? (
          <div style={vide}>{t("Déclarez d'abord des champs : une règle écrit dans un champ.")}</div>
        ) : (
          regles.map((r) => (
            <div key={r.id} style={ligne}>
              <span style={{ flex: 1, minWidth: 0 }}>{r.libelle_effectif}</span>
              {estRempli(r, remplis) ? (
                // On va **à** la règle, pas seulement à l'écran des règles : un
                // champ qui se remplit mal se corrige là où il est écrit.
                <button
                  onClick={() => ouvrirCeQuiRemplit(r)}
                  title={decrireOuAller(r, reglesParChamp)}
                  style={{ ...boutonDiscret, border: "none", color: "var(--accent)" }}
                >
                  <Check size={12} /> {decrireRemplissage(r)}
                  <ChevronRight size={11} />
                </button>
              ) : r.extraction_attendue ? (
                <>
                  {/* Déclaré comme devant se lire sur le document, et rien ne le
                      lit : c'est un réglage qui manque, pas un choix (§22.27). */}
                  <span style={{ color: "var(--amber)", fontSize: 12,
                                 display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <AlertTriangle size={12} /> règle à écrire
                  </span>
                  <button
                    onClick={() => onOuvrirEcran?.("regles", {
                      categorieId, champCible: r.champ.replace(/^meta:/, ""),
                    })}
                    style={boutonDiscret}
                    title={`Écrire la règle qui remplira « ${r.libelle_effectif} »`}
                  >
                    <Plus size={12} /> Créer la règle
                  </button>
                </>
              ) : (
                <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>
                  saisi à la main
                </span>
              )}
            </div>
          ))
        )}
        <button onClick={() => onOuvrirEcran?.("regles", { categorieId })}
                style={{ ...boutonDiscret, marginTop: 8 }}>
          Ouvrir les règles d'extraction <ChevronRight size={12} />
        </button>
      </Etape>

      {/* ---------------------------------------------------------------- */}
      <Etape numero={4} titre={t("Ce qui arrive à terme, ce qui identifie")}
             resume={decrireQuatre(regles)}
             fait={regles.some((r) => r.echeance || r.identifiant)}
             aide="Une échéance prévient avant qu'une date ne passe. Un champ identifiant
                   reconnaît la même pièce redéposée, et en fait une version au lieu d'un
                   doublon. Les deux se règlent sur le champ, à l'étape 1.">
        {regles.filter((r) => r.echeance || r.identifiant).map((r) => (
          <div key={r.id} style={ligne}>
            <span style={{ flex: 1, minWidth: 0 }}>{r.libelle_effectif}</span>
            <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>
              {[r.echeance && `échéance, rappel ${r.rappel_jours || 30} j avant`,
                r.identifiant && t("identifie le document")].filter(Boolean).join(" · ")}
            </span>
            <button onClick={() => setEdition(r)} style={boutonDiscret}>Modifier</button>
          </div>
        ))}
        {!regles.some((r) => r.echeance || r.identifiant) && (
          <div style={vide}>
            {t("Rien de déclaré — c'est le cas courant. Une facture gagne à porter un champ identifiant (son numéro) ; un contrat, une échéance.")}
          </div>
        )}
      </Etape>

      {edition && (
        <EditeurChampAttendu
          categorieId={categorieId}
          nomCategorie={categorie?.nom}
          regle={edition.id ? edition : null}
          ordreParDefaut={edition.ordre}
          onFerme={() => setEdition(null)}
          onEnregistre={() => { setEdition(null); annoncer(t("Champ enregistré")); charger(); }}
        />
      )}

      {suppression && (
        <ConfirmerSuppression
          typeObjet="regle_champ"
          identifiant={suppression.id}
          intitule={`« ${suppression.libelle_effectif} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimerChamp}
        />
      )}
    </div>
  );
}

/** Une étape numérotée : ce qu'elle fait, où elle en est, et de quoi agir. */
function Etape({ numero, titre, resume, aide, fait, children }) {
  return (
    <section style={{ marginTop: 22, border: "1px solid var(--line)",
                      borderRadius: "var(--radius)", background: "var(--bg-panel)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "10px 14px",
                    borderBottom: "1px solid var(--line)",
                    background: "var(--bg-panel-alt)" }}>
        <span style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
          background: fait ? "var(--accent)" : "var(--line-strong)",
          color: "#fff", fontSize: 11, fontWeight: 700,
        }}>{numero}</span>
        <strong style={{ fontSize: 13.5 }}>{titre}</strong>
        <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>{resume}</span>
      </div>
      <div style={{ padding: "10px 14px" }}>
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5,
                      marginBottom: 8, maxWidth: 640 }}>
          {aide}
        </div>
        {children}
      </div>
    </section>
  );
}

/** Ce qu'est un champ, en trois mots : c'est ce qu'on lit d'abord dans la liste. */
function decrireNature(regle) {
  if (regle.attache_documents) return t("documents de la GED");
  if (regle.source_table) return `lié à ${regle.source_table}`;
  return { texte: "texte", texte_long: "texte long", date: "date", nombre: "nombre",
           montant: "montant", booleen: "oui / non" }[regle.type_champ] || "texte";
}

/** Un champ est-il rempli sans qu'on ait à écrire ? */
function estRempli(regle, remplis) {
  if (regle.deduction && regle.deduction !== "aucune") return true;
  return remplis.has(regle.champ.replace(/^meta:/, "")) || remplis.has(regle.champ);
}

/** Les champs qui attendent une règle et n'en ont pas : ce qu'il reste à faire. */
function aParametrer(regles, remplis) {
  return regles.filter((r) => r.extraction_attendue && !estRempli(r, remplis));
}

function decrireTrois(regles, remplis) {
  if (!regles.length) return "—";
  const manquantes = aParametrer(regles, remplis).length;
  if (manquantes) return `${manquantes} règle(s) à écrire`;
  const remplies = regles.filter((r) => estRempli(r, remplis)).length;
  return remplies
    ? `${remplies} champ(s) remplis automatiquement`
    : t("tout se saisit à la main");
}

/** Ce que le raccourci va ouvrir, dit avant le clic. */
function decrireOuAller(regle, reglesParChamp) {
  if (regle.deduction && regle.deduction !== "aucune") {
    return t("Ouvrir le champ : la déduction se règle sur lui");
  }
  const [premiere] = reglesParChamp.get(regle.champ.replace(/^meta:/, "")) || [];
  return premiere
    ? `Ouvrir la règle « ${premiere.nom} »`
    : t("Ouvrir les règles d'extraction");
}

function decrireRemplissage(regle) {
  if (regle.deduction && regle.deduction !== "aucune") return t("déduit du document");
  return t("règle d'extraction");
}

function decrireQuatre(regles) {
  const echeances = regles.filter((r) => r.echeance).length;
  const identifiants = regles.filter((r) => r.identifiant).length;
  if (!echeances && !identifiants) return t("rien de déclaré");
  return [echeances && `${echeances} échéance(s)`,
          identifiants && `${identifiants} champ(s) identifiant(s)`]
    .filter(Boolean).join(" · ");
}

const ligne = {
  display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "3px 0",
};

const vide = {
  fontSize: 12, color: "var(--ink-faint)", lineHeight: 1.5,
};

const boutonDiscret = {
  display: "inline-flex", alignItems: "center", gap: 4,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "2px 8px",
  fontSize: 11.5, cursor: "pointer",
};
