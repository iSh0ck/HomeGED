import React, { useEffect, useRef } from "react";
import { AlertTriangle, Clock, WifiOff } from "lucide-react";

/**
 * Message qui doit être vu, et acquitté.
 *
 * Un bandeau se lit ou ne se lit pas : il apparaît au bord de l'écran, souvent
 * hors du regard, et l'on peut continuer sans l'avoir remarqué. Pour les deux
 * cas qui empêchent d'aller plus loin — la connexion refusée et l'application
 * qui ne joint plus son serveur — cela ne suffit pas : on reste devant un écran
 * qui ne réagit pas sans savoir pourquoi.
 *
 * D'où cette fenêtre, avec un unique bouton. Elle interrompt, ce qui est le but,
 * mais reste refermable de trois façons — le bouton, la touche Échap, un clic à
 * côté : un message qu'on ne peut pas fermer est une impasse, pas une
 * information.
 *
 * `ton` choisit l'icône et la couleur : `attente` pour ce qui se résoudra tout
 * seul (un verrouillage temporaire), `reseau` pour une panne de liaison,
 * `erreur` pour le reste.
 */
export default function AlerteModale({ titre, message, ton = "erreur", onFermer }) {
  const bouton = useRef(null);

  useEffect(() => {
    // Le bouton prend le focus : on peut acquitter au clavier sans chercher
    // la souris, et un lecteur d'écran annonce la fenêtre.
    bouton.current?.focus();
    const auClavier = (e) => { if (e.key === "Escape") onFermer?.(); };
    document.addEventListener("keydown", auClavier);
    return () => document.removeEventListener("keydown", auClavier);
  }, [onFermer]);

  const { Icone, couleur, fond } = APPARENCE[ton] || APPARENCE.erreur;
  const debutSurLeVoile = useRef(false);

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-label={titre}
      // Même précaution que dans `Modal` : un geste qui commence dans la fenêtre
      // et se termine dehors ne doit pas la fermer.
      onMouseDown={(e) => { debutSurLeVoile.current = e.target === e.currentTarget; }}
      onClick={(e) => {
        if (e.target === e.currentTarget && debutSurLeVoile.current) onFermer();
      }}
      className="apparition-voile"
      style={{
        position: "fixed", inset: 0, zIndex: 90,
        background: "rgba(34, 40, 31, 0.45)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="apparition"
        style={{
          width: "100%", maxWidth: 420, background: "var(--bg-panel)",
          borderTop: `3px solid ${couleur}`, borderRadius: "var(--radius)",
          boxShadow: "0 20px 48px -24px rgba(34, 40, 31, 0.5)",
          padding: "22px 24px", animationDuration: "180ms",
        }}
      >
        <div style={{ display: "flex", gap: 12 }}>
          <span style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            width: 34, height: 34, borderRadius: "50%", background: fond,
            color: couleur, flexShrink: 0,
          }}>
            <Icone size={18} />
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 style={{ fontSize: 15 }}>{titre}</h2>
            <p style={{ fontSize: 13, color: "var(--ink-soft)", marginTop: 6, lineHeight: 1.55 }}>
              {message}
            </p>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
          <button
            ref={bouton}
            onClick={onFermer}
            style={{
              border: "none", background: "var(--accent)", color: "#fff",
              borderRadius: "var(--radius)", padding: "8px 22px",
              fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
}

const APPARENCE = {
  erreur: { Icone: AlertTriangle, couleur: "var(--brick)", fond: "var(--brick-soft)" },
  attente: { Icone: Clock, couleur: "var(--amber)", fond: "var(--amber-soft)" },
  reseau: { Icone: WifiOff, couleur: "var(--brick)", fond: "var(--brick-soft)" },
};
