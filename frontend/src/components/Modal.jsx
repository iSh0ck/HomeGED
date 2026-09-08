import React, { useRef } from "react";
import { X } from "lucide-react";

/**
 * Fenêtre modale.
 *
 * Elle arrive en deux temps : le voile se pose, le panneau monte légèrement.
 * Sans ce décalage, la fenêtre surgit et l'œil doit retrouver seul d'où elle
 * vient ; avec lui, on suit le mouvement. Les deux durées sont courtes (160 et
 * 220 ms) : on ne fait jamais attendre devant une confirmation.
 */
export default function Modal({ titre, sousTitre, onClose, children, width = 460 }) {
  // Sur un téléphone, une fenêtre centrée avec des marges perd le peu de place
  // disponible : elle prend l'écran entier (§22.52).
  const compact = typeof window !== "undefined" && window.innerWidth < 820;
  // Le clic sur le voile ferme la fenêtre — mais seulement si le geste a
  // *commencé* sur le voile. Sans cette précaution, sélectionner du texte dans
  // un champ et relâcher le bouton hors de la fenêtre la refermait, avec la
  // saisie en cours : le navigateur émet alors un `click` sur l'ancêtre commun
  // des deux extrémités du geste, c'est-à-dire sur le voile. Le geste le plus
  // banal — attraper un mot d'un peu trop loin — faisait perdre le travail.
  const debutSurLeVoile = useRef(false);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="apparition-voile"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(34, 40, 31, 0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 60,
      }}
      onMouseDown={(e) => { debutSurLeVoile.current = e.target === e.currentTarget; }}
      onClick={(e) => {
        if (e.target === e.currentTarget && debutSurLeVoile.current) onClose();
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        // Les deux classes sur un même élément : elles étaient sur deux
        // attributs `className` successifs, et React ne garde que le dernier —
        // l'animation d'apparition ne jouait donc plus.
        className="apparition scrollbar-thin"
        style={{
          animationDuration: "220ms",
          width,
          // Une fenêtre large doit rester dans l'écran : sans plafond, la
          // fenêtre d'examen (1200 px) débordait sur un portable.
          maxWidth: compact ? "100vw" : "94vw",
          maxHeight: compact ? "100dvh" : "85vh",
          overflowY: "auto",
          ...(compact ? { width: "100vw", height: "100dvh", borderRadius: 0 } : {}),
          background: "var(--bg-panel)",
          borderRadius: "var(--radius)",
          boxShadow: "var(--shadow-panel)",
          padding: 24,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2 style={{ fontSize: 17 }}>{titre}</h2>
            {sousTitre && (
              <p style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 4 }}>{sousTitre}</p>
            )}
          </div>
          <button type="button" onClick={onClose} style={{ border: "none", background: "transparent" }}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const champStyle = {
  display: "block",
  fontSize: 12,
  color: "var(--ink-soft)",
  marginBottom: 4,
  marginTop: 14,
};

export const inputStyle = {
  width: "100%",
  padding: "8px 10px",
  fontSize: 13,
  border: "1px solid var(--line-strong)",
  borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)",
  color: "var(--ink)",
};

export const boutonPrimaire = {
  marginTop: 20,
  width: "100%",
  background: "var(--accent)",
  color: "#fff",
  border: "none",
  borderRadius: "var(--radius)",
  padding: "10px 0",
  fontSize: 13,
  fontWeight: 600,
};
