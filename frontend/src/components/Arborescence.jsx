import React from "react";
import { ChevronLeft, ChevronRight, FolderTree, Layers } from "lucide-react";
import { t } from "../lib/langue";

/**
 * Le registre replié en arborescence (§21.6).
 *
 * Un tableau plat de trois cents lignes se filtre colonne par colonne. Replié
 * sur un critère — l'année, l'émetteur, le véhicule concerné — il se parcourt :
 * on descend « 2026 », puis « EDF », et l'on est arrivé.
 *
 * Une branche n'est **qu'un filtre** : la choisir ajoute son critère à la liste,
 * et rien ne change pour les droits, la recherche ou la pagination. C'est aussi
 * pourquoi le dernier niveau rend la main au tableau : il n'y a rien à réinventer.
 */
export default function Arborescence({ champ, libelle, branches, chargement,
                                       chemin = [], onDescendre, onRemonter }) {
  return (
    <div style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "16px 20px" }}
         className="scrollbar-thin">
      <FilRepli chemin={chemin} onRemonter={onRemonter} />

      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 12,
                    fontSize: 12.5, color: "var(--ink-soft)" }}>
        <Layers size={14} color="var(--ink-faint)" />
        Replié par <strong>{libelle || champ}</strong>
        {branches && <span style={{ color: "var(--ink-faint)" }}>
          {" "}· {branches.length} branche{branches.length > 1 ? "s" : ""}
        </span>}
      </div>

      {chargement && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>
      )}

      {branches?.length === 0 && !chargement && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)", lineHeight: 1.5,
                      maxWidth: 520 }}>
          {t("Aucun document ne porte de valeur pour ce champ à cet endroit. Choisissez un autre repli, ou revenez au tableau.")}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        {(branches || []).map((branche) => (
          <button
            key={branche.valeur}
            onClick={() => onDescendre?.(branche)}
            title={`Voir les documents de « ${t(branche.libelle)} »`}
            style={{
              width: 218, textAlign: "left", padding: "10px 12px",
              border: "1px solid var(--line)", borderRadius: "var(--radius)",
              background: "var(--bg-panel)", color: "var(--ink)", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 10,
            }}
          >
            <FolderTree size={14} color="var(--ink-faint)" style={{ flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis",
                            whiteSpace: "nowrap" }}>
                {t(branche.libelle)}
              </div>
              <div className="tabular"
                   style={{ fontSize: 11.5, color: "var(--accent)", marginTop: 2 }}>
                {branche.nombre} document{branche.nombre > 1 ? "s" : ""}
              </div>
            </div>
            <ChevronRight size={14} color="var(--ink-faint)" />
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Le chemin parcouru dans le repli. Sans lui, une liste filtrée sur « 2026 » puis
 * « EDF » ressemble à un registre incomplet : on ne voit pas ce qui l'a réduite,
 * ni comment revenir.
 */
export function FilRepli({ chemin, onRemonter, fin = null }) {
  if (!chemin?.length) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap",
                  marginBottom: 12, fontSize: 12.5 }}>
      <button
        onClick={() => onRemonter?.(-1)}
        style={lienStyle}
      >
        <ChevronLeft size={13} />
        Tout
      </button>
      {chemin.map((etape, index) => (
        <React.Fragment key={`${etape.champ}-${etape.valeur}`}>
          <ChevronRight size={12} color="var(--ink-faint)" />
          {index === chemin.length - 1 && fin === null ? (
            <span style={{ color: "var(--ink)", fontWeight: 500 }}>{t(etape.libelle)}</span>
          ) : (
            <button onClick={() => onRemonter?.(index)} style={lienStyle}>
              {t(etape.libelle)}
            </button>
          )}
        </React.Fragment>
      ))}
      {fin}
    </div>
  );
}

const lienStyle = {
  display: "inline-flex", alignItems: "center", gap: 3, border: "none",
  background: "transparent", color: "var(--accent)", fontSize: 12.5, padding: 0,
  cursor: "pointer",
};
