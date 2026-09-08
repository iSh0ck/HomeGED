import React from "react";
import { Pencil, Trash2, Plus } from "lucide-react";
import { useReordonnable, PoigneeOrdre } from "./Reordonnable.jsx";
import { PoigneeColonne, useLargeursColonnes } from "./champs/LargeursColonnes.jsx";
import { t } from "../lib/langue";

/**
 * Tableau des écrans d'administration.
 *
 * `reordonnable` ajoute une colonne de poignées et rend les lignes déplaçables
 * à la main (§18.46) : `{ onDeplacer(de, vers), groupeDe(index), libelleDe(ligne) }`.
 * L'absence de cette propriété laisse le tableau exactement tel qu'il était.
 *
 * `actions` se pose **à gauche du bouton d'ajout** : ce qui se fait sur le
 * tableau entier se lit au même endroit que ce qui s'y ajoute (§22.36).
 *
 * Les colonnes s'élargissent à la souris (§22.34) et gardent leur largeur d'une
 * visite à l'autre. `cle` dit sous quel nom : à défaut, les intitulés des
 * colonnes en tiennent lieu — deux écrans aux colonnes identiques sont de toute
 * façon le même tableau, et deux écrans différents ne se marcheront pas dessus.
 */
export default function AdminTable({ colonnes, lignes, onAjouter, onModifier, onSupprimer,
                                     libelleAjout, reordonnable, cle, actions = null }) {
  const { largeurs, commencer, oublier } = useLargeursColonnes(
    `admin.${cle || colonnes.map((c) => c.key).join("-")}`);
  const reordre = useReordonnable({
    nombre: lignes.length,
    actif: !!reordonnable,
    onDeplacer: reordonnable?.onDeplacer ?? (() => {}),
    groupeDe: reordonnable?.groupeDe ?? (() => null),
  });
  return (
    <div>
      {(onAjouter || actions) && (
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center",
                      gap: 8, marginBottom: 12 }}>
          {actions}
          {onAjouter && (
            <button onClick={onAjouter} style={boutonAjout}>
              <Plus size={14} />
              {libelleAjout}
            </button>
          )}
        </div>
      )}

      <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr>
              {reordonnable && <th style={{ ...thStyle, width: 28 }} aria-label="Ordre" />}
              {colonnes.map((c) => (
                <th
                  key={c.key}
                  style={{
                    ...thStyle, position: "relative",
                    width: largeurs[c.key] || undefined,
                    minWidth: largeurs[c.key] || undefined,
                    maxWidth: largeurs[c.key] || undefined,
                  }}
                >
                  {c.label}
                  <PoigneeColonne champ={c.key} largeur={largeurs[c.key]}
                                  commencer={commencer} oublier={oublier} />
                </th>
              ))}
              <th style={{ ...thStyle, width: 70 }} />
            </tr>
          </thead>
          <tbody>
            {lignes.length === 0 && (
              <tr>
                <td colSpan={colonnes.length + (reordonnable ? 2 : 1)} style={{ padding: 20, textAlign: "center", color: "var(--ink-faint)" }}>
                  {t("Rien pour l'instant.")}
                </td>
              </tr>
            )}
            {lignes.map((ligne, i) => {
              const proprietes = reordonnable ? reordre.proprietesLigne(i) : {};
              return (
              <tr
                key={ligne.id ?? i}
                {...proprietes}
                style={{ borderTop: "1px solid var(--line)", ...(proprietes.style || {}) }}
              >
                {reordonnable && (
                  <td style={{ ...tdStyle, paddingRight: 0 }}>
                    <PoigneeOrdre
                      {...reordre.proprietesPoignee(i, reordonnable.libelleDe?.(ligne) ?? "")}
                    />
                  </td>
                )}
                {colonnes.map((c) => (
                  <td key={c.key} style={tdStyle}>
                    {c.render ? c.render(ligne) : ligne[c.key]}
                  </td>
                ))}
                <td style={{ ...tdStyle, textAlign: "right", whiteSpace: "nowrap" }}>
                  {onModifier && (
                    <button onClick={() => onModifier(ligne)} style={iconBtn} aria-label="Modifier">
                      <Pencil size={13} />
                    </button>
                  )}
                  {onSupprimer && (
                    <button onClick={() => onSupprimer(ligne)} style={iconBtn} aria-label="Supprimer">
                      <Trash2 size={13} color="var(--brick)" />
                    </button>
                  )}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const thStyle = {
  textAlign: "left",
  padding: "8px 12px",
  background: "var(--bg-panel-alt)",
  color: "var(--ink-soft)",
  fontSize: 11,
  fontWeight: 600,
};
const tdStyle = { padding: "8px 12px", verticalAlign: "middle" };
const iconBtn = { border: "none", background: "transparent", padding: 4, cursor: "pointer" };
const boutonAjout = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  background: "var(--accent)",
  color: "#fff",
  border: "none",
  borderRadius: "var(--radius)",
  padding: "7px 12px",
  fontSize: 13,
  fontWeight: 500,
};
