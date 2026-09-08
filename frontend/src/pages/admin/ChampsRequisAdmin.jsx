import React, { useEffect, useState } from "react";
import { adminApi, api } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import { champStyle } from "../../components/Modal.jsx";
import EditeurChampAttendu from "../../components/EditeurChampAttendu.jsx";
import RoleEcran from "../../components/RoleEcran.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import { aplatirArborescence } from "../../lib/arborescence";
import Liste from "../../components/champs/Liste.jsx";
import { deplacer } from "../../components/Reordonnable.jsx";
import { t } from "../../lib/langue";


/**
 * Champs attendus par catégorie (§15) : chaque catégorie déclare ce qu'un
 * document doit porter, et si c'est obligatoire ou facultatif.
 *
 * La liste des champs proposés vient de l'API : elle inclut les champs du
 * document et toutes les métadonnées déjà extraites. Rien n'est codé en dur,
 * une nouvelle règle d'extraction devient donc exigible immédiatement.
 */
export default function ChampsRequisAdmin({ onMontage }) {
  const [categories, setCategories] = useState([]);
  const [categorieId, setCategorieId] = useState(null);
  const [regles, setRegles] = useState([]);
  const [champs, setChamps] = useState([]);
  const [sources, setSources] = useState([]);
  // La **nature** du champ, choisie d'abord : c'est elle qui décide de tout le
  // reste du formulaire (§22.12). Un booléen « lié à une table » ne suffisait
  // plus dès qu'il a fallu déclarer une valeur nouvelle ou des documents.
  const [edition, setEdition] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [suppression, setSuppression] = useState(null);

  useEffect(() => {
    adminApi.categories().then((toutes) => {
      // Un dossier organise mais ne porte aucun document (§19.1) : il n'a donc
      // ni colonnes ni champs attendus, et le proposer ici ne mènerait qu'à un
      // réglage sans effet — ou à un refus de l'API.
      const c = toutes.filter((categorie) => (categorie.nature || "type") !== "dossier");
      setCategories(c);
      if (c.length && categorieId === null) setCategorieId(c[0].id);
    }).catch((e) => setErreur(e.message));
    adminApi.champsDisponibles().then(setChamps).catch(() => {});
    // Sources possibles : les tables du foyer **et** les comptes de la GED — on
    // rattache aussi bien un document à un véhicule qu'à la personne qui le
    // possède (§17.27).
    adminApi.sourcesChamps().then(setSources).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function charger() {
    if (!categorieId) return;
    adminApi.reglesChamps(categorieId).then(setRegles).catch((e) => setErreur(e.message));
  }
  useEffect(charger, [categorieId]);

  // L'enregistrement d'un champ vit dans `EditeurChampAttendu` depuis le
  // §22.16 : deux formulaires qui déclarent la même chose auraient divergé.

  /** Charge utile complète attendue par PUT : ce qui n'est pas renvoyé est perdu. */
  const charge = (regle, modifications = {}) => ({
    categorie_id: regle.categorie_id ?? categorieId,
    champ: regle.champ,
    source_table: regle.source_table || null,
    sources: regle.sources || [],
    libelle: regle.libelle || null,
    obligatoire: !!regle.obligatoire,
    identifiant: !!regle.identifiant,
    echeance: !!regle.echeance,
    rappel_jours: regle.rappel_jours ?? null,
    attache_documents: !!regle.attache_documents,
    type_champ: regle.type_champ || "texte",
    documents_categorie_id: regle.documents_categorie_id ?? null,
    documents_champs: regle.documents_champs || [],
    ordre: regle.ordre,
    ...modifications,
  });

  /**
   * Déplace un champ attendu dans la catégorie affichée. Cet ordre est celui
   * dans lequel les champs se présentent — sur la fiche, dans le Centre
   * d'analyse et dans la liste de ce qui manque à un document.
   */
  async function deplacerLigne(de, vers) {
    const reordonne = deplacer(regles, de, vers);
    setErreur(null);
    try {
      for (const [position, r] of reordonne.entries()) {
        const rang = (position + 1) * 10;
        if (r.ordre === rang) continue;
        await adminApi.modifierRegleChamp(r.id, charge(r, { ordre: rang }));
      }
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function supprimer() {
    await adminApi.supprimerRegleChamp(suppression.id).catch((e) => setErreur(e.message));
    charger();
    setSuppression(null);
  }

  const nomCategorie = categories.find((c) => c.id === categorieId)?.nom;
  const dejaRegles = new Set(regles.filter((r) => r.id !== edition?.id).map((r) => r.champ));

  return (
    <div>
      <RoleEcran courant="champs" onMontage={onMontage} />
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        Chaque catégorie décrit ce qu'un document doit porter : une facture attend un
        émetteur, un montant et une date ; un contrat attend un employeur et une date de
        début. Un champ manquant alors qu'il est obligatoire signale un document à
        reprendre, sans empêcher son indexation.
        <br />
        <span style={{ color: "var(--ink-faint)" }}>
          Il s'agit ici de ce qu'on <strong>exige</strong> d'un document. Ce qu'on
          <strong> lit</strong> dedans se règle dans « Règles d'extraction ».
        </span>
      </p>

      <label style={{ ...champStyle, marginTop: 0 }}>{t("Catégorie")}</label>
      <Liste
        valeur={categorieId ?? ""}
        ariaLabel={t("Catégorie dont on règle les champs attendus")}
        style={{ maxWidth: 320 }}
        options={aplatirArborescence(categories).map((c) => ({
          valeur: c.id,
          libelle: `${"\u00a0".repeat(c.profondeur * 3)}${c.nom}`,
        }))}
        onChange={(v) => setCategorieId(Number(v))}
      />

      <div style={{ marginTop: 20 }}>
        <AdminTable
          libelleAjout={t("Ajouter un champ attendu")}
          // Un champ neuf se range en dernier ; sa place se règle ensuite en le
          // faisant glisser, ce qui vaut mieux qu'un nombre à deviner.
          onAjouter={() => setEdition({ ordre: (regles.length + 1) * 10 })}
          onModifier={(r) => setEdition(r)}
          onSupprimer={setSuppression}
          lignes={regles}
          reordonnable={{
            onDeplacer: deplacerLigne,
            libelleDe: (r) => `le champ « ${r.libelle_effectif} »`,
          }}
          colonnes={[
            { key: "libelle_effectif", label: t("Champ attendu") },
            {
              key: "champ",
              label: "Source",
              render: (r) => (
                <code style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-faint)" }}>
                  {r.champ}
                </code>
              ),
            },
            {
              key: "source_table",
              label: t("Source des valeurs"),
              render: (r) =>
                r.source_table ? (
                  <span style={{ fontSize: 12 }}>
                    {sources.find((source) => source.nom === r.source_table)?.libelle || r.source_table}
                  </span>
                ) : (
                  <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>saisie libre</span>
                ),
            },
            {
              key: "obligatoire",
              label: "Exigence",
              render: (r) =>
                r.obligatoire ? (
                  <span style={{ color: "var(--brick)", fontWeight: 600, fontSize: 12 }}>Obligatoire</span>
                ) : (
                  <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>Facultatif</span>
                ),
            },
            {
              key: "deduction",
              label: t("Déduit du document"),
              render: (r) =>
                !r.deduction || r.deduction === "aucune" ? (
                  <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>—</span>
                ) : (
                  <span style={{ fontSize: 12 }} title={
                    r.deduction === "toutes"
                      ? t("Rattaché quand toutes les colonnes cherchées figurent dans le document")
                      : t("Rattaché dès qu'une colonne cherchée figure dans le document")
                  }>
                    {(r.colonnes_deduction || []).join(" + ") || "colonnes identifiantes"}
                    {r.deduction === "une" && (
                      <span style={{ color: "var(--ink-faint)" }}> (une suffit)</span>
                    )}
                  </span>
                ),
            },
            {
              key: "identifiant",
              label: t("Identifie le document"),
              render: (r) =>
                r.identifiant ? (
                  <span style={{ color: "var(--accent)", fontWeight: 600, fontSize: 12 }}>
                    Oui
                  </span>
                ) : (
                  <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>—</span>
                ),
            },
          ]}
        />
      </div>

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {suppression && (
        <ConfirmerSuppression
          typeObjet={"regle_champ"}
          identifiant={suppression.id}
          intitule={`« ${suppression.libelle_effectif} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimer}
        />
      )}

      {edition && (
        <EditeurChampAttendu
          categorieId={categorieId}
          nomCategorie={nomCategorie}
          regle={edition.id ? edition : null}
          ordreParDefaut={edition.ordre}
          onFerme={() => setEdition(null)}
          onEnregistre={() => { setEdition(null); charger(); }}
        />
      )}
    </div>
  );
}
