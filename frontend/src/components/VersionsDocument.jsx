import React, { useEffect, useState } from "react";
import { Download, History, Trash2 } from "lucide-react";
import { api } from "../api";
import Modal from "./Modal.jsx";
import ConfirmerSuppression from "./ConfirmerSuppression.jsx";
import { formaterHorodatage, ilYA } from "../lib/horodatage";
import { t } from "../lib/langue";

/**
 * Versions d'un document (§18.36).
 *
 * Un document du foyer n'est pas figé : on rescanne une facture mal cadrée, on
 * reçoit la version corrigée d'un avis. Chaque dépôt s'ajoute à la même fiche,
 * et cette fenêtre montre lesquels — avec leur date, ce qui est souvent la seule
 * chose qui les distingue.
 *
 * Chaque version s'ouvre : une version qu'on ne peut pas lire ne serait qu'une
 * ligne de journal. Seul un administrateur en supprime une, et jamais la
 * dernière — l'API le refuse, et la fenêtre le dit avant.
 */
export default function VersionsDocument({ documentId, estAdmin, onFermer, onChangement }) {
  const [versions, setVersions] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [suppression, setSuppression] = useState(null);

  function charger() {
    api.versionsDocument(documentId)
      .then(setVersions)
      .catch((e) => setErreur(e.message));
  }
  useEffect(charger, [documentId]);

  async function ouvrir(version) {
    setErreur(null);
    try {
      const url = await api.fichierVersionBlobUrl(documentId, version.id);
      const lien = document.createElement("a");
      lien.href = url;
      lien.target = "_blank";
      lien.rel = "noreferrer";
      lien.click();
      // On ne révoque pas tout de suite : l'onglet qui vient de s'ouvrir lit
      // encore l'URL. Une minute suffit largement, et le navigateur nettoie le
      // reste à la fermeture de la page.
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      setErreur(e.message);
    }
  }

  return (
    <Modal titre={t("Versions de ce document")} onClose={onFermer} width={540}>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55, marginTop: 2 }}>
        {t("Chaque dépôt de ce document est conservé. La version courante est celle que la fiche affiche ; les précédentes restent consultables — un scan raté se corrige en redéposant, sans rien perdre.")}
      </p>

      {versions === null && !erreur && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 16 }}>{t("Chargement…")}</div>
      )}

      {versions && (
        <div style={{ marginTop: 16, border: "1px solid var(--line)", borderRadius: "var(--radius)" }}>
          {versions.map((version, index) => (
            <div key={version.id} style={{
              display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
              borderBottom: index < versions.length - 1 ? "1px solid var(--line)" : "none",
              background: version.courante ? "var(--accent-soft)" : "transparent",
            }}>
              <History size={14} color={version.courante ? "var(--accent)" : "var(--ink-faint)"}
                       style={{ flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: "var(--ink)" }}>
                  {formaterHorodatage(version.date_depot)}
                  {version.courante && (
                    <span style={{
                      marginLeft: 7, fontSize: 10.5, color: "var(--accent)",
                      border: "1px solid var(--accent)", borderRadius: 8, padding: "0 6px",
                    }}>
                      courante
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
                  {version.nom_fichier} · {taille(version.taille_octets)} · {ilYA(version.date_depot)}
                  {version.par ? ` · déposé par ${version.par}` : ""}
                </div>
              </div>

              {version.fichier_present ? (
                <button onClick={() => ouvrir(version)} style={bouton} title={t("Ouvrir cette version")}>
                  <Download size={12} />
                  Ouvrir
                </button>
              ) : (
                <span style={{ fontSize: 11.5, color: "var(--amber)" }}>fichier absent</span>
              )}

              {estAdmin && versions.length > 1 && (
                <button
                  onClick={() => setSuppression(version)}
                  title={t("Supprimer cette version")}
                  style={{ ...bouton, borderColor: "var(--brick)", color: "var(--brick)" }}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {versions && versions.length === 1 && (
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 10, lineHeight: 1.5 }}>
          {t("Un seul dépôt pour l'instant. Redéposer le même document — rescanné, corrigé — en ajoutera un ici plutôt que de créer une seconde fiche.")}
        </div>
      )}

      {erreur && (
        <div style={{ marginTop: 14, fontSize: 12.5, color: "var(--brick)" }}>{erreur}</div>
      )}

      {suppression && (
        <ConfirmerSuppression
          intitule={`la version du ${formaterHorodatage(suppression.date_depot)}`}
          consequences={[
            {
              nature: "suppression",
              libelle: `${suppression.nom_fichier} sera détruit`,
              precision: t("le fichier de cette version part avec elle"),
            },
            ...(suppression.courante ? [{
              nature: "avertissement",
              libelle: t("C'est la version courante"),
              precision: t("la plus récente des restantes prendra sa place sur la fiche"),
            }] : []),
          ]}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={async () => {
            await api.supprimerVersion(documentId, suppression.id);
            setSuppression(null);
            charger();
            onChangement?.();
          }}
        />
      )}
    </Modal>
  );
}

/**
 * Pastille annonçant plusieurs versions. Discrète mais présente : c'est le seul
 * signe qu'un document a une histoire, et sans elle personne n'irait la chercher.
 */
export function PastilleVersions({ nombre, onClick, taille: dimension = 13 }) {
  if (!nombre || nombre < 2) return null;
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title={`${nombre} versions de ce document`}
      aria-label={`${nombre} versions de ce document`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 3,
        border: "1px solid var(--line-strong)", background: "transparent",
        color: "var(--ink-soft)", borderRadius: 9, padding: "0 5px",
        fontSize: 10.5, lineHeight: 1.6, flexShrink: 0,
      }}
    >
      <History size={dimension - 3} />
      {nombre}
    </button>
  );
}

function taille(octets) {
  if (octets == null) return "taille inconnue";
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} Ko`;
  return `${(octets / (1024 * 1024)).toFixed(1)} Mo`;
}

const bouton = {
  display: "inline-flex", alignItems: "center", gap: 5,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "4px 9px", fontSize: 11.5, flexShrink: 0,
};
