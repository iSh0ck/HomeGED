import React, { useState } from "react";
import { t, locale } from "../lib/langue";

/**
 * Briques de visualisation du tableau de bord, en SVG écrit à la main : aucune
 * dépendance de graphique n'est ajoutée au projet.
 *
 * Trois principes tenus partout :
 *
 * - **Une seule teinte par graphique.** Une répartition compare une grandeur
 *   entre des entités, pas des identités : colorer chaque barre différemment
 *   ferait croire à une signification qui n'existe pas. Un camaïeu de couleurs
 *   est le défaut le plus courant des tableaux de bord.
 * - **Les valeurs sont écrites**, pas seulement dessinées : la couleur ne porte
 *   jamais seule une information, et le chiffre exact reste lisible.
 * - **Axes et grilles en retrait**, marques fines, extrémités arrondies côté
 *   valeur et ancrées à la ligne de base — c'est la donnée qui doit ressortir.
 */

// Une fonction : le format suit la langue, qui peut changer sans recharger.
const formateur = () => new Intl.NumberFormat(locale(), { maximumFractionDigits: 2 });

export function formater(valeur, unite) {
  const nombre = formateur().format(valeur ?? 0);
  return unite ? `${nombre} ${unite}` : nombre;
}

/* ------------------------------------------------------------------ */
/* Case chiffrée                                                       */
/* ------------------------------------------------------------------ */

/**
 * Un chiffre seul se lit mieux qu'un graphique à une valeur : pas de tracé,
 * juste l'icône, le nombre et ce qu'il désigne. L'accent « alerte » s'accompagne
 * toujours de son icône et de son libellé, jamais de la couleur seule.
 */
export function Case({ titre, valeur, unite, icone: Icone, accent, sousTitre, onClick }) {
  const alerte = accent === "amber" && (valeur ?? 0) > 0;
  const interactif = Boolean(onClick);

  return (
    <div
      onClick={onClick}
      role={interactif ? "button" : undefined}
      tabIndex={interactif ? 0 : undefined}
      onKeyDown={(e) => interactif && (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onClick())}
      style={{
        background: "var(--bg-panel)",
        border: `1px solid ${alerte ? "var(--amber)" : "var(--line)"}`,
        borderRadius: "var(--radius)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        cursor: interactif ? "pointer" : "default",
        minHeight: 96,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 7, color: alerte ? "var(--amber)" : "var(--ink-faint)" }}>
        {Icone && <Icone size={15} />}
        <span style={{ fontSize: 12, fontWeight: 500, color: alerte ? "var(--amber)" : "var(--ink-soft)" }}>
          {titre}
        </span>
      </div>
      <div
        className="tabular"
        style={{
          fontSize: 28, fontWeight: 600, lineHeight: 1.1,
          color: alerte ? "var(--amber)" : "var(--ink)",
        }}
      >
        {formater(valeur, unite)}
      </div>
      {sousTitre && (
        <div style={{ fontSize: 11, color: "var(--ink-faint)" }}>{sousTitre}</div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Répartition — barres horizontales                                   */
/* ------------------------------------------------------------------ */

/**
 * Barres horizontales plutôt que verticales : les libellés sont du texte de
 * longueur variable (« Direction générale des finances publiques »), qui se lit
 * à l'horizontale sans rotation ni troncature.
 */
export function Repartition({ points, unite, onSelection }) {
  const [survol, setSurvol] = useState(null);
  if (!points?.length) return <Vide />;

  const maximum = Math.max(...points.map((p) => p.valeur), 1);
  const hauteurLigne = 26;

  return (
    <div style={{ position: "relative" }}>
      {points.map((point, i) => {
        const largeur = Math.max((point.valeur / maximum) * 100, point.valeur > 0 ? 1.5 : 0);
        const actif = survol === i;
        return (
          <div
            key={point.cle ?? point.libelle}
            onMouseEnter={() => setSurvol(i)}
            onMouseLeave={() => setSurvol(null)}
            onClick={() => onSelection?.(point)}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              height: hauteurLigne, cursor: onSelection ? "pointer" : "default",
            }}
          >
            <span
              title={t(point.libelle)}
              style={{
                width: 132, flexShrink: 0, fontSize: 12,
                color: actif ? "var(--ink)" : "var(--ink-soft)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                textAlign: "right",
              }}
            >
              {t(point.libelle)}
            </span>
            <div style={{ flex: 1, minWidth: 0, height: 14, position: "relative" }}>
              {/* la piste situe la barre dans le maximum, sans concurrencer la donnée */}
              <div style={{ position: "absolute", inset: 0, background: "var(--bg-panel-alt)", borderRadius: 4 }} />
              <div
                style={{
                  position: "absolute", top: 0, bottom: 0, left: 0, width: `${largeur}%`,
                  background: "var(--data)", opacity: actif ? 1 : 0.9,
                  borderRadius: "0 4px 4px 0",   // extrémité arrondie côté valeur
                  transition: "opacity 120ms",
                }}
              />
            </div>
            <span
              className="tabular"
              style={{ width: 78, flexShrink: 0, fontSize: 12, textAlign: "right", color: "var(--ink)" }}
            >
              {formater(point.valeur, unite)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Évolution — colonnes                                                */
/* ------------------------------------------------------------------ */

/**
 * Colonnes et non courbe : les périodes sont discrètes et souvent à zéro. Une
 * ligne tracerait une pente entre deux mois vides, suggérant une progression
 * continue qui n'a pas eu lieu.
 */
export function Evolution({ points, unite, onSelection }) {
  const [survol, setSurvol] = useState(null);
  if (!points?.length) return <Vide />;

  const hauteur = 170;
  const margeHaute = 18;
  const hauteurAxe = 20;
  const maximum = Math.max(...points.map((p) => p.valeur), 1);
  const largeurColonne = 100 / points.length;
  // au-delà d'une douzaine de colonnes, un libellé sur deux suffit à situer
  const pasLibelle = points.length > 14 ? 3 : points.length > 8 ? 2 : 1;

  return (
    <div style={{ position: "relative" }}>
      <div style={{ position: "relative", height: hauteur }}>
        {[0, 0.5, 1].map((part) => (
          <div
            key={part}
            style={{
              position: "absolute", left: 0, right: 0,
              bottom: hauteurAxe + part * (hauteur - hauteurAxe - margeHaute),
              borderTop: "1px solid var(--line)", opacity: part === 0 ? 1 : 0.5,
            }}
          >
            <span
              className="tabular"
              style={{ position: "absolute", right: 0, top: -14, fontSize: 10, color: "var(--ink-faint)" }}
            >
              {part > 0 ? formater(Math.round(maximum * part * 100) / 100) : ""}
            </span>
          </div>
        ))}

        <div style={{ position: "absolute", inset: `${margeHaute}px 0 ${hauteurAxe}px 0`, display: "flex", alignItems: "flex-end" }}>
          {points.map((point, i) => (
            <div
              key={point.cle}
              onMouseEnter={() => setSurvol(i)}
              onMouseLeave={() => setSurvol(null)}
              onClick={() => point.valeur > 0 && onSelection?.(point)}
              title={onSelection && point.valeur > 0 ? t("Voir ces documents") : undefined}
              style={{
                width: `${largeurColonne}%`, height: "100%", display: "flex",
                alignItems: "flex-end", justifyContent: "center",
                cursor: onSelection && point.valeur > 0 ? "pointer" : "default",
              }}
            >
              <div
                style={{
                  width: "calc(100% - 4px)",           // 2px de respiration de chaque côté
                  height: `${(point.valeur / maximum) * 100}%`,
                  minHeight: point.valeur > 0 ? 2 : 0,
                  background: "var(--data)",
                  opacity: survol === null || survol === i ? 1 : 0.55,
                  borderRadius: "4px 4px 0 0",         // extrémité arrondie côté valeur
                  transition: "opacity 120ms",
                }}
              />
            </div>
          ))}
        </div>

        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: hauteurAxe, display: "flex" }}>
          {points.map((point, i) => (
            <div
              key={point.cle}
              style={{
                width: `${largeurColonne}%`, textAlign: "center", fontSize: 10,
                color: survol === i ? "var(--ink)" : "var(--ink-faint)",
                overflow: "hidden", whiteSpace: "nowrap", paddingTop: 4,
              }}
            >
              {i % pasLibelle === 0 || survol === i ? point.libelle : ""}
            </div>
          ))}
        </div>
      </div>

      {survol !== null && (
        <div
          style={{
            position: "absolute", top: 0,
            left: `calc(${(survol + 0.5) * largeurColonne}% )`,
            transform: "translateX(-50%)",
            background: "var(--bg-panel)", border: "1px solid var(--line-strong)",
            borderRadius: "var(--radius)", padding: "4px 9px", fontSize: 11,
            boxShadow: "var(--shadow-panel)", pointerEvents: "none", whiteSpace: "nowrap",
          }}
        >
          <strong>{points[survol].libelle}</strong>{" "}
          <span className="tabular">{formater(points[survol].valeur, unite)}</span>
        </div>
      )}
    </div>
  );
}

function Vide() {
  return (
    <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "24px 0", textAlign: "center" }}>
      {t("Aucune donnée sur cette période.")}
    </div>
  );
}
