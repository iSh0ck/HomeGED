import React from "react";
import { t } from "../lib/langue";

/**
 * Ce que fait **cet écran-ci**, et ce que font les deux autres (§22.15).
 *
 * Le montage d'un type de document se joue sur trois écrans — les champs
 * attendus, les colonnes, les règles d'extraction — et rien ne disait lequel
 * fait quoi ni dans quel ordre les prendre. On y arrivait par tâtonnement, ce
 * qui est le plus sûr moyen de croire que le logiciel est compliqué.
 *
 * Trois phrases, toujours les mêmes, celle de l'écran courant en gras : on sait
 * où l'on est sans avoir à s'en souvenir. Le raccourci vers l'assemblage guidé
 * (§22.16) est là pour qui préfère être mené.
 */
const ROLES = () => [
  { cle: "champs", titre: t("Champs attendus"),
    phrase: t("ce qu'un document doit porter") },
  { cle: "colonnes", titre: t("Colonnes des tableaux"),
    phrase: t("ce qu'on voit dans le tableau") },
  { cle: "regles", titre: t("Règles d'extraction"),
    phrase: t("ce qui se remplit tout seul depuis le texte") },
];

export default function RoleEcran({ courant, onMontage }) {
  return (
    <div style={{
      display: "flex", gap: 10, alignItems: "flex-start", flexWrap: "wrap",
      padding: "10px 14px", marginBottom: 14, fontSize: 12.5, lineHeight: 1.6,
      background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
      borderRadius: "var(--radius)",
    }}>
      <div style={{ flex: "1 1 420px", minWidth: 0 }}>
        {ROLES().map((role, rang) => (
          <span key={role.cle}>
            {rang > 0 && " · "}
            <span style={{
              color: role.cle === courant ? "var(--ink)" : "var(--ink-faint)",
              fontWeight: role.cle === courant ? 600 : 400,
            }}>
              {t(role.titre)} : {t(role.phrase)}
            </span>
          </span>
        ))}
      </div>
      {onMontage && (
        <button
          onClick={onMontage}
          title={t("Tout régler pour un type, dans l'ordre")}
          style={{
            border: "1px solid var(--line-strong)", background: "var(--bg-panel)",
            color: "var(--ink-soft)", borderRadius: "var(--radius)",
            padding: "4px 10px", fontSize: 12, cursor: "pointer", flexShrink: 0,
          }}
        >
          Assembler un type
        </button>
      )}
    </div>
  );
}
