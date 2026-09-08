import React, { useCallback, useEffect, useState } from "react";
import * as Icones from "lucide-react";
import { api } from "../api";
import { Case, Repartition, Evolution, formater } from "../components/Graphiques.jsx";
import { t } from "../lib/langue";

/**
 * Affichage d'un tableau de bord : le tableau d'accueil livré avec
 * l'application, ou l'un des tableaux personnalisés composés en administration.
 *
 * La page ne connaît aucun indicateur en particulier — elle rend ce que l'API
 * lui renvoie. Ajouter un indicateur ne demande donc aucune modification ici.
 */
export default function DashboardPage({ tableauId, onOuvrirRegistre, onOuvrirAnalyse }) {
  const [tableau, setTableau] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(null);

  const charger = useCallback(() => {
    setChargement(true);
    setErreur(null);
    api
      .donneesTableau(tableauId)
      .then(setTableau)
      .catch((e) => setErreur(e.message))
      .finally(() => setChargement(false));
  }, [tableauId]);
  useEffect(charger, [charger]);

  if (chargement && !tableau) {
    return <div style={{ padding: 28, fontSize: 13, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>;
  }
  if (erreur) {
    return <div style={{ padding: 28, fontSize: 13, color: "var(--brick)" }}>{erreur}</div>;
  }

  const cases = tableau.widgets.filter((w) => w.type === "nombre" || w.type === "somme");
  const graphiques = tableau.widgets.filter((w) => w.type === "repartition" || w.type === "evolution");

  /**
   * Ce sur quoi un indicateur mène — et **il ne mène presque nulle part**
   * (§22.43).
   *
   * Les cases ouvraient le registre en y posant les filtres de l'indicateur.
   * Sur « Documents », cela voulait dire « le registre entier, sans catégorie » :
   * on quittait une vue d'ensemble pour une autre, sans avoir rien demandé, et
   * l'écran d'où l'on venait se perdait. Un tableau de bord se lit, il ne se
   * traverse pas.
   *
   * Reste la seule porte qui mène ailleurs qu'au registre : « À reprendre »
   * ouvre le Centre d'analyse, où l'on va effectivement faire quelque chose.
   */
  function suivreLien(widget) {
    if (widget.lien?.vers === "analyse") return () => onOuvrirAnalyse?.();
    return undefined;
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }} className="scrollbar-thin">
      <div style={{ maxWidth: 1100 }}>
        <h1 style={{ fontSize: 20 }}>{tableau.nom}</h1>
        {tableau.description && (
          <p style={{ fontSize: 13, color: "var(--ink-soft)", marginTop: 4, marginBottom: 20 }}>
            {t(tableau.description)}
          </p>
        )}

        {tableau.widgets.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--ink-faint)", padding: "40px 0" }}>
            {t("Ce tableau de bord ne contient encore aucun indicateur.")}
          </div>
        )}

        {cases.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))",
              gap: 12, marginBottom: 20,
            }}
          >
            {cases.map((widget) => (
              <CaseIndicateur key={widget.id} widget={widget} onClick={suivreLien(widget)} />
            ))}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
          {graphiques.map((widget) => (
            <Panneau key={widget.id} widget={widget} onOuvrirRegistre={onOuvrirRegistre} />
          ))}
        </div>
      </div>
    </div>
  );
}

function CaseIndicateur({ widget, onClick }) {
  if (widget.erreur) return <PanneauErreur widget={widget} compact />;
  const Icone = Icones[widget.icone] || Icones.Hash;
  return (
    <Case
      titre={t(widget.titre)}
      valeur={widget.valeur}
      unite={widget.unite}
      icone={Icone}
      accent={widget.accent}
      sousTitre={widget.sous_titre}
      onClick={onClick}
    />
  );
}

function Panneau({ widget, onOuvrirRegistre }) {
  const largeur = Math.min(Math.max(widget.largeur || 2, 1), 4);
  const contenu = widget.erreur ? (
    <PanneauErreur widget={widget} />
  ) : widget.type === "repartition" ? (
    <Repartition
      points={widget.points}
      unite={widget.unite}
      // Un graphique du tableau de bord ne mène nulle part non plus (§22.43) :
      // il montre une répartition, il n'est pas un chemin vers le registre.
      onSelection={undefined}
    />
  ) : (
    <Evolution points={widget.points} unite={widget.unite} onSelection={undefined} />
  );

  return (
    <section
      style={{
        gridColumn: `span ${largeur}`,
        background: "var(--bg-panel)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        padding: "14px 16px 16px",
      }}
    >
      <h2 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>{t(widget.titre)}</h2>
      {contenu}
      {widget.total != null && (
        <div className="tabular" style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 8 }}>
          Total : {formater(widget.total, widget.unite)}
        </div>
      )}
    </section>
  );
}

/**
 * Bornes d'une période de la série, pour ouvrir le registre exactement sur la
 * colonne cliquée. La clé vaut « 2026-01 » au mois, « 2026 » à l'année.
 */
function bornesDeLaPeriode(cle, granularite) {
  if (granularite === "annee") return [`${cle}-01-01`, `${cle}-12-31`];
  const [annee, mois] = cle.split("-").map(Number);
  const dernier = new Date(Date.UTC(annee, mois, 0)).getUTCDate();
  const deuxChiffres = (n) => String(n).padStart(2, "0");
  return [`${cle}-01`, `${annee}-${deuxChiffres(mois)}-${deuxChiffres(dernier)}`];
}


function PanneauErreur({ widget, compact }) {
  return (
    <div
      style={{
        background: "var(--brick-soft)", border: "1px solid var(--brick)",
        borderRadius: "var(--radius)", padding: compact ? "12px 14px" : 14,
        fontSize: 12, color: "var(--brick)",
      }}
    >
      <strong>{t(widget.titre)}</strong>
      <div style={{ marginTop: 4 }}>{widget.erreur}</div>
    </div>
  );
}
