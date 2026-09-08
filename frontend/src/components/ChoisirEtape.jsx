import React, { useState } from "react";
import Modal, { boutonPrimaire } from "./Modal.jsx";
import { t } from "../lib/langue";

/**
 * Choix de l'étape à partir de laquelle reprendre un ou plusieurs travaux.
 *
 * Les étapes sont ordonnées de la plus coûteuse à la plus légère, et chacune
 * annonce ce qu'elle refait : reprendre au contrôle des champs est immédiat,
 * repartir de l'OCR peut demander plusieurs dizaines de secondes par document.
 * Seules les étapes réellement praticables pour la sélection sont proposées.
 */
export default function ChoisirEtape({ etapes, possibles, titre, sousTitre, onAnnuler, onValider }) {
  const disponibles = etapes.filter((e) => possibles.includes(e.etape));
  const [choix, setChoix] = useState(disponibles[disponibles.length - 1]?.etape ?? null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState(null);

  async function valider() {
    setEnvoi(true);
    setErreur(null);
    try {
      await onValider(choix);
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  return (
    <Modal titre={titre} sousTitre={sousTitre} onClose={onAnnuler} width={470}>
      {disponibles.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-soft)", marginTop: 8 }}>
          {t("Aucune étape n'est commune à la sélection. Les travaux qui ont produit un document se réanalysent, ceux qui ont échoué se reprennent depuis leur fichier source : relance-les séparément.")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 10 }}>
          {disponibles.map((e) => (
            <button
              key={e.etape}
              type="button"
              onClick={() => setChoix(e.etape)}
              style={{
                textAlign: "left",
                border: "1px solid " + (choix === e.etape ? "var(--accent)" : "var(--line)"),
                background: choix === e.etape ? "var(--accent-soft)" : "var(--bg-panel)",
                borderRadius: "var(--radius)",
                padding: "9px 12px",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>{t(e.libelle)}</div>
              <div style={{ fontSize: 11, color: "var(--ink-soft)", marginTop: 2 }}>{t(e.description)}</div>
            </button>
          ))}
        </div>
      )}

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 12 }}>{erreur}</div>}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
        <button
          type="button"
          onClick={onAnnuler}
          style={{
            border: "1px solid var(--line-strong)", background: "transparent",
            color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "8px 14px", fontSize: 13,
          }}
        >
          Annuler
        </button>
        <button
          type="button"
          onClick={valider}
          disabled={!choix || envoi}
          style={{ ...boutonPrimaire, marginTop: 0, width: "auto", opacity: !choix || envoi ? 0.6 : 1 }}
        >
          {envoi ? "Envoi…" : "Relancer"}
        </button>
      </div>
    </Modal>
  );
}
