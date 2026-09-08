import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { t } from "../../lib/langue";

/**
 * Un champ de saisie **libre**, avec des suggestions (§22.29).
 *
 * Le `<datalist>` natif faisait le travail et rien d'autre : sa fenêtre
 * appartient au système, ne se met pas en forme, et sous Windows elle affiche
 * une liste grise sans rapport avec le reste de l'écran. Le même défaut que le
 * `<select>` natif, réglé de la même façon (voir `Liste.jsx`) — et la fenêtre
 * est posée à la racine du document, pour ne pas être coupée par le bord d'une
 * fenêtre modale.
 *
 * Ce qu'il ne fait **pas** : restreindre. Un nom nouveau s'écrit toujours ; les
 * suggestions viennent de ce que le foyer a déjà nommé, elles évitent de taper à
 * l'aveugle sans transformer le champ en liste fermée (§21.11).
 */
export default function SaisieSuggeree({
  valeur, onChange, suggestions = [], placeholder, ariaLabel, required = false,
  style,
}) {
  const [ouvert, setOuvert] = useState(false);
  const [cadre, setCadre] = useState(null);
  const zone = useRef(null);

  const visibles = useMemo(() => {
    const terme = (valeur || "").trim().toLowerCase();
    if (!terme) return suggestions;
    return suggestions.filter((s) => s.valeur.toLowerCase().includes(terme));
  }, [suggestions, valeur]);

  useEffect(() => {
    if (!ouvert) return undefined;
    const placer = () => {
      const bord = zone.current?.getBoundingClientRect();
      if (!bord) return;
      const dessous = window.innerHeight - bord.bottom - 12;
      const dessus = bord.top - 12;
      const versLeHaut = dessous < 180 && dessus > dessous;
      setCadre({
        left: bord.left, largeur: bord.width,
        haut: versLeHaut ? undefined : bord.bottom + 4,
        bas: versLeHaut ? window.innerHeight - bord.top + 4 : undefined,
        hauteurMax: Math.max(120, versLeHaut ? dessus : dessous),
      });
    };
    placer();
    const auClic = (e) => {
      if (zone.current?.contains(e.target)) return;
      if (e.target.closest?.("[data-suggestions]")) return;
      setOuvert(false);
    };
    window.addEventListener("scroll", placer, true);
    window.addEventListener("resize", placer);
    document.addEventListener("mousedown", auClic);
    return () => {
      window.removeEventListener("scroll", placer, true);
      window.removeEventListener("resize", placer);
      document.removeEventListener("mousedown", auClic);
    };
  }, [ouvert]);

  return (
    <div ref={zone} style={{ position: "relative" }}>
      <input
        required={required}
        value={valeur || ""}
        aria-label={ariaLabel}
        placeholder={placeholder}
        onFocus={() => setOuvert(true)}
        onChange={(e) => { onChange?.(e.target.value); setOuvert(true); }}
        onKeyDown={(e) => { if (e.key === "Escape") setOuvert(false); }}
        style={style}
      />

      {ouvert && cadre && visibles.length > 0 && createPortal(
        <div
          className="apparition scrollbar-thin"
          data-suggestions=""
          style={{
            position: "fixed", left: cadre.left, top: cadre.haut, bottom: cadre.bas,
            minWidth: cadre.largeur, maxWidth: Math.max(cadre.largeur, 360),
            maxHeight: cadre.hauteurMax, overflowY: "auto", zIndex: 3000,
            background: "var(--bg-panel)", border: "1px solid var(--line)",
            borderRadius: "var(--radius)", padding: 3,
            boxShadow: "0 14px 32px -16px rgba(34, 40, 31, 0.45)",
            animationDuration: "120ms",
          }}
        >
          {visibles.map((s) => (
            <button
              key={s.valeur}
              type="button"
              onClick={() => { onChange?.(s.valeur); setOuvert(false); }}
              style={{
                display: "flex", alignItems: "baseline", gap: 8, width: "100%",
                border: "none", background: "transparent", textAlign: "left",
                borderRadius: "var(--radius)", padding: "5px 8px", cursor: "pointer",
                color: "var(--ink)", fontSize: 12,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "var(--accent-soft)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
                {s.valeur}
              </span>
              {s.aide && (
                <span style={{ color: "var(--ink-faint)", fontSize: 11 }}>{t(s.aide)}</span>
              )}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}
