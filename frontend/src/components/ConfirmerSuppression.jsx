import React, { useEffect, useState } from "react";
import { AlertTriangle, Trash2, Link2Off, Info } from "lucide-react";
import { api } from "../api";
import Modal from "./Modal.jsx";
import { t } from "../lib/langue";

/**
 * Confirmation de suppression.
 *
 * Une fenêtre qui demande seulement « Êtes-vous sûr ? » ne renseigne sur rien :
 * on valide sans savoir ce qu'on emporte. Celle-ci interroge l'API pour dire ce
 * que la suppression entraîne réellement — combien de documents seront
 * déclassés, quelles vues disparaîtront, quels droits seront perdus — en
 * distinguant trois natures :
 *
 *   ce qui **disparaît** avec l'objet ;
 *   ce qui **survit mais perd son lien** ;
 *   ce qui **resterait incohérent** sans que la base ne l'empêche.
 *
 * Le bouton reste inactif tant que ces conséquences ne sont pas affichées :
 * confirmer sans les avoir vues serait exactement ce qu'on veut éviter.
 */
export default function ConfirmerSuppression({
  typeObjet,
  identifiant,
  intitule,
  administrateur = true,
  // conséquences fournies directement, pour les objets sans calcul dédié
  // (une ligne de table, un fichier de la corbeille, un travail du suivi)
  consequences: consequencesFournies,
  onAnnuler,
  onConfirmer,
}) {
  const [impact, setImpact] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    if (!typeObjet) {
      setImpact({ objet: intitule, consequences: consequencesFournies || [] });
      return undefined;
    }
    let annule = false;
    api
      .impactSuppression(typeObjet, identifiant, administrateur)
      .then((d) => !annule && setImpact(d))
      .catch((e) => !annule && setErreur(e.message));
    return () => { annule = true; };
  }, [typeObjet, identifiant, administrateur, intitule, consequencesFournies]);

  async function confirmer() {
    setEnvoi(true);
    setErreur(null);
    try {
      await onConfirmer();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  const consequences = impact?.consequences ?? [];
  const pretes = Boolean(impact) || Boolean(erreur);

  return (
    <Modal titre={t("Confirmer la suppression")} onClose={onAnnuler} width={470}>
      <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
        <AlertTriangle size={18} color="var(--brick)" style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.5 }}>
          Vous êtes sur le point de supprimer{" "}
          <strong style={{ color: "var(--ink)" }}>{impact?.objet || intitule}</strong>.
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        {!impact && !erreur && (
          <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
            {t("Analyse des conséquences…")}
          </div>
        )}

        {impact && consequences.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>
            {t("Rien d'autre n'est touché.")}
          </div>
        )}

        {consequences.length > 0 && (
          <>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-faint)", marginBottom: 8 }}>
              {t("Ce que cela entraîne")}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {consequences.map((c, i) => (
                <Consequence key={i} consequence={c} />
              ))}
            </div>
          </>
        )}
      </div>

      {erreur && (
        <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 14 }}>{erreur}</div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 22 }}>
        <button onClick={onAnnuler} style={boutonSecondaire}>{t("Annuler")}</button>
        <button
          onClick={confirmer}
          disabled={envoi || !pretes}
          style={{ ...boutonDanger, opacity: envoi || !pretes ? 0.6 : 1 }}
        >
          {envoi ? "Suppression…" : t("Supprimer définitivement")}
        </button>
      </div>
    </Modal>
  );
}

function Consequence({ consequence }) {
  const style = {
    suppression: { Icone: Trash2, couleur: "var(--brick)" },
    detachement: { Icone: Link2Off, couleur: "var(--amber)" },
    avertissement: { Icone: Info, couleur: "var(--ink-faint)" },
  }[consequence.nature] || { Icone: Info, couleur: "var(--ink-faint)" };
  const { Icone, couleur } = style;

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
      <Icone size={13} color={couleur} style={{ flexShrink: 0, marginTop: 2 }} />
      <div style={{ fontSize: 12 }}>
        <span style={{ color: "var(--ink)" }}>{t(consequence.libelle)}</span>
        {consequence.precision && (
          <span style={{ color: "var(--ink-faint)" }}> — {consequence.precision}</span>
        )}
      </div>
    </div>
  );
}

const boutonSecondaire = {
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "8px 14px", fontSize: 13,
};

const boutonDanger = {
  border: "none", background: "var(--brick)", color: "#fff",
  borderRadius: "var(--radius)", padding: "8px 14px", fontSize: 13, fontWeight: 600,
};
