import React from "react";
import { Eye, X } from "lucide-react";

/**
 * Bandeau de consultation sous une autre identité (§18.50).
 *
 * Il occupe toute la largeur, en haut, dans une couleur qui n'est celle
 * d'aucun autre élément. Ce n'est pas une coquetterie : pendant une
 * consultation, tout l'écran ment sur qui vous êtes. Il faut que la seule chose
 * qui ne mente pas soit impossible à manquer, et que le moyen d'en sortir soit
 * toujours à portée — y compris quand l'écran, replié sur les droits du compte
 * consulté, n'affiche plus le bouton d'administration.
 */
export default function BandeauConsultation({ consultation, onQuitter }) {
  if (!consultation) return null;
  const nom = [consultation.prenom, consultation.nom].filter(Boolean).join(" ")
    || consultation.email;

  return (
    <div
      role="status"
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "7px 14px", fontSize: 12.5,
        background: "var(--ambre, #8a6d1f)", color: "#fff",
        borderBottom: "1px solid rgba(0,0,0,0.2)",
      }}
    >
      <Eye size={14} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1, minWidth: 0 }}>
        Vous consultez le registre en tant que <strong>{nom}</strong> — lecture seule.
        Aucune modification n'est possible tant que cette consultation dure.
      </span>
      <button
        onClick={onQuitter}
        style={{
          display: "inline-flex", alignItems: "center", gap: 5,
          border: "1px solid rgba(255,255,255,0.5)", background: "transparent",
          color: "#fff", borderRadius: "var(--radius)", padding: "3px 9px", fontSize: 12,
        }}
      >
        <X size={12} />
        Quitter
      </button>
    </div>
  );
}
