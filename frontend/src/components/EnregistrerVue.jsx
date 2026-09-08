import React, { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "./Modal.jsx";
import { aplatirArborescence } from "../lib/arborescence";
import { decrireCritere } from "../lib/criteres";
import Liste from "./champs/Liste.jsx";
import { t } from "../lib/langue";

/**
 * Enregistrement des filtres courants sous forme de vue réutilisable (§9.B).
 * Les critères ne sont pas ressaisis : ce sont exactement ceux du tableau, au
 * format du moteur de filtres. La vue est rattachée à une catégorie, qui
 * détermine seulement où elle apparaît dans la navigation.
 */
export default function EnregistrerVue({
  criteres, categories, colonnes = [],
  categorieParDefaut, onClose, onEnregistrer,
}) {
  const [nom, setNom] = useState("");
  const [detailsOuverts, setDetailsOuverts] = useState(false);
  const [categorieId, setCategorieId] = useState(categorieParDefaut ?? "");
  const [partagee, setPartagee] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  async function soumettre(e) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      await onEnregistrer({
        nom,
        categorie_id: categorieId === "" ? null : Number(categorieId),
        criteres,
        partagee,
        ordre: 100,
      });
      onClose();
    } catch (err) {
      setErreur(err.message);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Modal titre={t("Enregistrer cette vue")} onClose={onClose}>
      <form onSubmit={soumettre}>
        <label style={champStyle}>{t("Nom de la vue")}</label>
        <input
          required
          autoFocus
          value={nom}
          onChange={(e) => setNom(e.target.value)}
          placeholder={t("ex : Factures EDF de l'année")}
          style={inputStyle}
        />

        <label style={champStyle}>{t("Rattacher à")}</label>
        <Liste
          valeur={categorieId}
          ariaLabel={t("Catégorie de rattachement de la vue")}
          options={[
            { valeur: "", libelle: t("Aucune catégorie (vue générale)") },
            ...aplatirArborescence(categories).map((c) => ({
              valeur: c.id,
              libelle: `${"\u00a0".repeat(c.profondeur * 3)}${c.nom}`,
            })),
          ]}
          onChange={setCategorieId}
        />
        <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4 }}>
          {t("Détermine uniquement l'endroit où la vue apparaît dans la navigation.")}
        </div>

        <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={partagee} onChange={(e) => setPartagee(e.target.checked)} />
          {t("Partager avec les autres comptes")}
        </label>

        <div style={{ marginTop: 14 }}>
          {/* Replié par défaut, comme le détail d'un travail : c'est un
              repère, qu'on déplie quand on veut vérifier ce qu'on mémorise. */}
          <button
            type="button"
            onClick={() => setDetailsOuverts((ouvert) => !ouvert)}
            disabled={criteres.length === 0}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              border: "none", background: "transparent", padding: 0,
              fontSize: 11, fontWeight: 600, color: "var(--ink-soft)",
              cursor: criteres.length ? "pointer" : "default",
            }}
          >
            {criteres.length > 0 &&
              (detailsOuverts ? <ChevronDown size={13} /> : <ChevronRight size={13} />)}
            Critères mémorisés ({criteres.length})
          </button>

          {criteres.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 6 }}>
              {t("Aucun filtre actif : la vue affichera tous les documents.")}
            </div>
          )}

          {detailsOuverts && criteres.length > 0 && (
            <div style={{
              display: "flex", flexDirection: "column", gap: 3, marginTop: 8,
              padding: "8px 10px", background: "var(--bg-panel-alt)",
              borderRadius: "var(--radius)",
            }}>
              {criteres.map((critere, i) => {
                const lu = decrireCritere(critere, { categories, colonnes });
                return (
                  <div key={i} style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                    <span style={{ fontWeight: 500, color: "var(--ink)" }}>{lu.champ}</span>{" "}
                    {lu.operateur}
                    {lu.valeur && <> <strong style={{ color: "var(--ink)" }}>{lu.valeur}</strong></>}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

        <button type="submit" disabled={envoi} style={boutonPrimaire}>
          {envoi ? "Enregistrement…" : t("Enregistrer la vue")}
        </button>
      </form>
    </Modal>
  );
}
