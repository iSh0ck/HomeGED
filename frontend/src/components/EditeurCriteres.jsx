import React from "react";
import { Plus, X } from "lucide-react";
import Liste from "./champs/Liste.jsx";
import ChampDate from "./champs/ChampDate.jsx";
import { LIBELLES_OPERATEUR } from "../lib/criteres";
import { t } from "../lib/langue";

/**
 * Édition des critères d'une vue enregistrée (§19.8).
 *
 * Jusqu'ici, les critères d'une vue ne se modifiaient qu'en refaisant la
 * recherche dans le registre, puis en réenregistrant la vue sous le même nom.
 * Corriger une vue partagée demandait donc de reconstituer une recherche qu'on
 * n'avait pas forcément faite soi-même — et l'écran d'administration, qui
 * proposait de la renommer et de la déplacer, laissait croire qu'il permettait
 * tout le reste.
 *
 * Ce composant ne réinvente aucun vocabulaire : les champs et leurs opérateurs
 * viennent de l'API (`/admin/champs-disponibles`), c'est-à-dire du moteur qui
 * les applique. Une liste tenue ici finirait par diverger de ce qu'il accepte,
 * et l'on écrirait des vues refusées à l'enregistrement.
 */

/** Opérateurs qui n'attendent aucune valeur : « renseigné » se suffit à lui-même. */
const SANS_VALEUR = new Set(["vide", "non_vide"]);

const STATUTS = () => [
  { valeur: "traite", libelle: t("Traité") },
  { valeur: "incomplet", libelle: "Incomplet" },
  { valeur: "en_attente", libelle: t("En attente") },
  { valeur: "ocr_en_cours", libelle: t("Océrisation en cours") },
  { valeur: "erreur", libelle: "Erreur" },
];

export default function EditeurCriteres({
  criteres = [], onChange, champs = [], categories = [],
  libelleVide = t("Aucun critère : la vue montrera tous les documents."),
  aide = t("Les critères se cumulent : un document doit tous les satisfaire pour apparaître dans la vue."),
}) {
  const descriptionDe = (nom) => champs.find((c) => c.champ === nom);

  function modifier(index, modifications) {
    onChange(criteres.map((c, i) => (i === index ? { ...c, ...modifications } : c)));
  }

  function changerChamp(index, nom) {
    const description = descriptionDe(nom);
    const operateurs = description?.operateurs || ["contient"];
    // L'opérateur en place peut ne rien vouloir dire sur le nouveau champ —
    // « avant le » sur un nom de fichier. On garde le sien s'il reste valable,
    // le premier proposé sinon, plutôt que de laisser un critère que l'API
    // refusera à l'enregistrement.
    const actuel = criteres[index]?.operateur;
    modifier(index, {
      champ: nom,
      operateur: operateurs.includes(actuel) ? actuel : operateurs[0],
      valeur: "",
    });
  }

  function ajouter() {
    const premier = champs[0];
    onChange([...criteres, {
      champ: premier?.champ || "texte",
      operateur: premier?.operateurs?.[0] || "contient",
      valeur: "",
    }]);
  }

  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {criteres.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{libelleVide}</div>
        )}

        {criteres.map((critere, index) => {
          const description = descriptionDe(critere.champ);
          const operateurs = description?.operateurs || ["contient"];
          return (
            <div key={index} style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
              <div style={{ flex: "1 1 34%", minWidth: 150 }}>
                <Liste
                  recherchable
                  valeur={critere.champ}
                  ariaLabel={`Champ du critère ${index + 1}`}
                  options={champs.map((c) => ({
                    valeur: c.champ, libelle: c.libelle, groupe: c.groupe,
                  }))}
                  onChange={(v) => changerChamp(index, v)}
                />
              </div>
              <div style={{ flex: "0 0 130px" }}>
                <Liste
                  valeur={critere.operateur || operateurs[0]}
                  ariaLabel={`Opérateur du critère ${index + 1}`}
                  options={operateurs.map((o) => ({
                    valeur: o, libelle: t(LIBELLES_OPERATEUR[o] || o),
                  }))}
                  onChange={(v) => modifier(index, { operateur: v, valeur: "" })}
                />
              </div>
              <div style={{ flex: "1 1 34%", minWidth: 150 }}>
                <ValeurDuCritere
                  critere={critere}
                  description={description}
                  categories={categories}
                  onChange={(valeur) => modifier(index, { valeur })}
                />
              </div>
              <button
                type="button"
                onClick={() => onChange(criteres.filter((_, i) => i !== index))}
                aria-label={`Retirer le critère ${index + 1}`}
                style={{
                  border: "none", background: "transparent", color: "var(--ink-faint)",
                  padding: "6px 2px", flexShrink: 0,
                }}
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={ajouter}
        style={{
          display: "flex", alignItems: "center", gap: 5, marginTop: 10,
          border: "1px solid var(--line-strong)", background: "transparent",
          color: "var(--ink-soft)", borderRadius: "var(--radius)",
          padding: "4px 10px", fontSize: 12,
        }}
      >
        <Plus size={12} />
        Ajouter un critère
      </button>

      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.45 }}>
        {aide}
      </div>
    </div>
  );
}

/** Le contrôle de saisie qui convient à ce que le champ attend. */
function ValeurDuCritere({ critere, description, categories, onChange }) {
  if (SANS_VALEUR.has(critere.operateur)) {
    return (
      <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "7px 0" }}>
        aucune valeur attendue
      </div>
    );
  }

  const type = description?.type;

  if (critere.operateur === "entre") {
    // Deux dates, et l'API les attend dans cet ordre : un intervalle écrit à
    // l'envers ne ramènerait rien, sans rien dire.
    const bornes = Array.isArray(critere.valeur) ? critere.valeur : ["", ""];
    return (
      <div style={{ display: "flex", gap: 4 }}>
        <ChampDate valeur={bornes[0] || ""} ariaLabel={t("Début de l'intervalle")}
                   onChange={(v) => onChange([v, bornes[1] || ""])} />
        <ChampDate valeur={bornes[1] || ""} ariaLabel={t("Fin de l'intervalle")}
                   onChange={(v) => onChange([bornes[0] || "", v])} />
      </div>
    );
  }

  if (type === "date") {
    return <ChampDate valeur={critere.valeur || ""} ariaLabel={t("Valeur du critère")}
                      onChange={onChange} />;
  }

  if (type === "reference") {
    const source = critere.champ === "categorie" ? categories : [];
    return (
      <Liste
        recherchable
        valeur={critere.valeur ?? ""}
        ariaLabel={t("Valeur du critère")}
        placeholder="— Choisir —"
        options={source.map((o) => ({ valeur: String(o.id), libelle: o.nom }))}
        onChange={onChange}
      />
    );
  }

  if (critere.champ === "statut") {
    return (
      <Liste valeur={critere.valeur ?? ""} ariaLabel={t("Valeur du critère")}
             placeholder="— Choisir —" options={STATUTS()} onChange={onChange} />
    );
  }

  return (
    <input
      value={critere.valeur ?? ""}
      onChange={(e) => onChange(e.target.value)}
      aria-label={t("Valeur du critère")}
      style={{
        width: "100%", border: "1px solid var(--line-strong)", background: "transparent",
        color: "var(--ink)", borderRadius: "var(--radius)", padding: "6px 9px",
        fontSize: 12.5, fontFamily: "inherit",
      }}
    />
  );
}
