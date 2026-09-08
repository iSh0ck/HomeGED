import React, { useState } from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import Liste from "./champs/Liste.jsx";
import { t } from "../lib/langue";

/**
 * Pagination numérotée.
 *
 * Deux boutons « Précédent » / « Suivant » suffisent tant qu'il y a trois pages ;
 * passé quelques centaines d'entrées, ils obligent à cliquer cinquante fois pour
 * atteindre le début de l'historique. Ce composant donne donc les numéros, les
 * extrémités, le nombre d'éléments par page, et — quand le nombre de pages
 * dépasse la dizaine — un accès direct par numéro.
 *
 * Les numéros sont fenêtrés autour de la page courante : au-delà, la liste
 * deviendrait elle-même illisible. Les ellipses marquent ce qui est sauté.
 */
export default function Pagination({
  total,
  parPage,
  decalage,
  onDecalage,
  onParPage,
  options = [25, 50, 100, 200],
}) {
  const [saut, setSaut] = useState("");

  const pages = Math.max(1, Math.ceil(total / parPage));
  const courante = Math.floor(decalage / parPage);
  const aller = (page) => onDecalage(Math.min(Math.max(0, page), pages - 1) * parPage);

  function sauter(e) {
    e.preventDefault();
    const numero = Number(saut);
    if (Number.isInteger(numero) && numero >= 1 && numero <= pages) {
      aller(numero - 1);
      setSaut("");
    }
  }

  // Rien à paginer : on n'affiche que le choix du nombre par page, et seulement
  // s'il peut encore servir.
  if (total <= options[0] && pages === 1) return null;

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      flexWrap: "wrap", gap: 8, marginTop: 16,
    }}>
      <Bouton onClick={() => aller(0)} disabled={courante === 0} label={t("Première page")}>
        <ChevronsLeft size={13} />
      </Bouton>
      <Bouton onClick={() => aller(courante - 1)} disabled={courante === 0} label={t("Page précédente")}>
        <ChevronLeft size={13} />
      </Bouton>

      {fenetre(courante, pages).map((page, i) =>
        page === null ? (
          <span key={`saut${i}`} style={{ color: "var(--ink-faint)", fontSize: 12, padding: "0 2px" }}>
            …
          </span>
        ) : (
          <Bouton
            key={page}
            onClick={() => aller(page)}
            actif={page === courante}
            label={`Page ${page + 1}`}
          >
            <span className="tabular">{page + 1}</span>
          </Bouton>
        )
      )}

      <Bouton onClick={() => aller(courante + 1)} disabled={courante >= pages - 1} label={t("Page suivante")}>
        <ChevronRight size={13} />
      </Bouton>
      <Bouton onClick={() => aller(pages - 1)} disabled={courante >= pages - 1} label={t("Dernière page")}>
        <ChevronsRight size={13} />
      </Bouton>

      <span className="tabular" style={{ fontSize: 11.5, color: "var(--ink-faint)", marginLeft: 4 }}>
        {decalage + 1}–{Math.min(decalage + parPage, total)} sur {total}
      </span>

      {onParPage && (
        <label style={{ fontSize: 11.5, color: "var(--ink-faint)", display: "flex", alignItems: "center", gap: 5 }}>
          par page
          <Liste
            compact
            valeur={parPage}
            ariaLabel={t("Nombre de lignes par page")}
            options={options.map((n) => ({ valeur: n, libelle: String(n) }))}
            onChange={(v) => onParPage(Number(v))}
            style={{ width: 74 }}
          />
        </label>
      )}

      {pages > 10 && (
        <form onSubmit={sauter} style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <label style={{ fontSize: 11.5, color: "var(--ink-faint)" }} htmlFor="saut-page">
            aller à
          </label>
          <input
            id="saut-page"
            value={saut}
            onChange={(e) => setSaut(e.target.value.replace(/\D/g, ""))}
            inputMode="numeric"
            placeholder={String(courante + 1)}
            style={{
              width: 52, padding: "3px 6px", fontSize: 11.5, textAlign: "center",
              border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
              background: "var(--bg-panel-alt)", color: "var(--ink)", fontFamily: "inherit",
            }}
          />
        </form>
      )}
    </div>
  );
}

/**
 * Numéros à afficher : les deux premières pages, les deux dernières, et deux
 * voisines de part et d'autre de la courante. `null` marque une ellipse.
 */
function fenetre(courante, pages) {
  if (pages <= 9) return [...Array(pages).keys()];

  const retenues = new Set([0, 1, pages - 2, pages - 1]);
  for (let page = courante - 2; page <= courante + 2; page += 1) {
    if (page >= 0 && page < pages) retenues.add(page);
  }

  const triees = [...retenues].sort((a, b) => a - b);
  const avecEllipses = [];
  triees.forEach((page, i) => {
    if (i && page - triees[i - 1] > 1) avecEllipses.push(null);
    avecEllipses.push(page);
  });
  return avecEllipses;
}

function Bouton({ children, onClick, disabled, actif, label }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-current={actif ? "page" : undefined}
      title={label}
      style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        minWidth: 26, height: 26, padding: "0 6px",
        border: `1px solid ${actif ? "var(--accent)" : "var(--line-strong)"}`,
        background: actif ? "var(--accent)" : "transparent",
        color: actif ? "#fff" : "var(--ink-soft)",
        borderRadius: "var(--radius)", fontSize: 12,
        fontWeight: actif ? 600 : 400,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.4 : 1,
        transition: "background 140ms, border-color 140ms, color 140ms",
      }}
    >
      {children}
    </button>
  );
}
