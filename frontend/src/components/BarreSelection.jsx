import React from "react";
import { Pencil, X, CheckSquare, Link2, Trash2 } from "lucide-react";
import { t } from "../lib/langue";

/**
 * Barre d'outils de la sélection (§18.3).
 *
 * Elle n'apparaît que lorsqu'une ligne est cochée : une barre d'actions
 * toujours visible mais presque toujours inactive apprend surtout à ne plus la
 * regarder. Elle dit ce qui est sélectionné, et ce qu'on peut en faire.
 *
 * La sélection **traverse les pages** : on coche trois factures ici, deux plus
 * loin, et la barre les compte toutes. D'où le rappel du nombre : c'est le seul
 * endroit où l'on voit ce qu'on emmène.
 *
 * C'est aussi d'ici que l'on supprime. Le tableau, lui, ne porte plus aucune
 * action sur ses lignes : une icône de suppression au bout d'une rangée se
 * clique par accident, et d'autant plus facilement qu'on visait la ligne d'à
 * côté.
 */
export default function BarreSelection({ nombre, onModifier, onSupprimer, onEffacer,
                                        onRattacher }) {
  if (!nombre) return null;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "8px 16px",
      background: "var(--accent-soft)",
      borderBottom: "1px solid var(--line)",
    }}>
      <CheckSquare size={15} color="var(--accent)" style={{ flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: "var(--ink)", fontWeight: 500 }}>
        {nombre} fiche{nombre > 1 ? "s" : ""} sélectionnée{nombre > 1 ? "s" : ""}
      </span>

      <button onClick={onModifier} style={boutonPrimaire}>
        <Pencil size={13} />
        {nombre > 1 ? t("Modifier les fiches") : t("Modifier la fiche")}
      </button>

      {/* Rattacher (§22.4) : le geste naturel est de cocher les papiers qui se
          répondent, puis de le dire. Chercher l'autre document dans une fenêtre
          demanderait de le retrouver alors qu'on vient de le voir. */}
      {nombre > 1 && onRattacher && (
        <button onClick={onRattacher} style={boutonSecondaire}
                title={t("Relier ces fiches entre elles : un contrat et son avenant, une facture et son litige")}>
          <Link2 size={13} />
          {t("Rattacher entre elles")}
        </button>
      )}

      {onSupprimer && (
        <button onClick={onSupprimer} style={boutonDanger}>
          <Trash2 size={13} />
          Supprimer
        </button>
      )}

      <button onClick={onEffacer} style={boutonSecondaire}>
        <X size={13} />
        Tout décocher
      </button>

      {nombre > 1 && (
        <span style={{ fontSize: 11.5, color: "var(--ink-faint)", marginLeft: "auto" }}>
          {t("Les fiches s'enchaînent : enregistrer passe à la suivante.")}
        </span>
      )}
    </div>
  );
}

const commun = {
  display: "inline-flex", alignItems: "center", gap: 6,
  borderRadius: "var(--radius)", padding: "5px 11px", fontSize: 12.5,
};

const boutonPrimaire = {
  ...commun, border: "none", background: "var(--accent)", color: "#fff", fontWeight: 600,
};

const boutonSecondaire = {
  ...commun, border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)",
};

const boutonDanger = {
  ...commun, border: "1px solid var(--brick)", background: "transparent",
  color: "var(--brick)",
};
