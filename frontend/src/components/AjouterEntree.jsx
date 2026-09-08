import React, { useEffect, useState } from "react";
import { api } from "../api";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "./Modal.jsx";
import { SaisieChamp, Champ } from "./ModifierDocument.jsx";
import ChoisirDocuments from "./ChoisirDocuments.jsx";
import ZoneDepot from "./ZoneDepot.jsx";
import { t } from "../lib/langue";

/**
 * Ajouter une entrée à la main dans une fiche simple (§22.7, §22.10).
 *
 * Une fiche simple sert à noter ce qu'un foyer garde et qui n'a pas toujours de
 * papier : un contrat verbal, un entretien de véhicule, le code d'un cadenas. Le
 * fichier reste possible et **facultatif** : on le glisse ensuite, ou jamais.
 *
 * Le formulaire ne montre **que les champs déclarés** par la fiche. Pas de case
 * « Intitulé » ni de « Date » ajoutées d'office : elles n'ont de sens que pour
 * certains usages, et les imposer à tous obligerait à remplir ce qui ne veut
 * rien dire ici. Une fiche qui ne déclare rien ne peut donc rien recevoir — et
 * l'écran dit où aller le déclarer plutôt que d'inventer deux cases.
 */
export default function AjouterEntree({ categorieId, nomCategorie, onFerme, onCreee }) {
  const [champs, setChamps] = useState(null);
  const [valeurs, setValeurs] = useState({});
  // Ce que l'entrée retiendra de chaque valeur de table (§22.61). Vide pour un
  // champ veut dire « tout ce que l'administrateur propose ».
  const [affichages, setAffichages] = useState({});
  const [attaches, setAttaches] = useState({});
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  // Le papier, quand il y en a un (§22.13). Il n'est pas envoyé tout de suite :
  // l'entrée n'existe pas encore, et un fichier déposé avant elle n'aurait nulle
  // part où aller.
  const [fichier, setFichier] = useState(null);

  useEffect(() => {
    api.champsCategorie(categorieId)
      .then((r) => setChamps(r.champs || []))
      .catch((e) => { setChamps([]); setErreur(e.message); });
  }, [categorieId]);

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    setEnvoi(true);
    try {
      const creee = await api.creerEntree({
        categorie_id: categorieId,
        valeurs: Object.fromEntries(
          Object.entries(valeurs).filter(([, v]) => v !== "" && v != null)),
        affichages,
      });
      // Les documents attachés se posent une fois l'entrée créée : ce sont des
      // liens vers des fiches existantes, pas des valeurs de formulaire.
      for (const [champ, choisis] of Object.entries(attaches)) {
        if (choisis?.length) {
          await api.definirAttaches(creee.id, champ, choisis.map((d) => d.id));
        }
      }
      if (fichier) await api.joindrePiece(creee.id, fichier);
      onCreee?.(creee);
    } catch (err) {
      setErreur(err.message);
      setEnvoi(false);
    }
  }

  const rien = champs !== null && champs.length === 0;

  return (
    <Modal titre={`Ajouter une entrée dans « ${nomCategorie} »`}
           sousTitre={t("Le fichier est facultatif : glissez-le ensuite, ou jamais")}
           onClose={onFerme} width={540}>
      {champs === null && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>
      )}

      {rien && (
        <div style={{ fontSize: 12.5, lineHeight: 1.55, color: "var(--ink)" }}>
          <strong>« {nomCategorie} » ne déclare aucun champ.</strong> Il n'y a donc rien à
          saisir : une entrée porte ce que sa fiche attend, et c'est à vous de dire ce que
          c'est — un commentaire, une date d'entretien, un numéro de dossier.
          <div style={{ marginTop: 8, color: "var(--ink-soft)" }}>
            Déclarez-les dans <strong>{t("Administration → Champs attendus")}</strong>, puis
            revenez ici.
          </div>
        </div>
      )}

      {champs !== null && champs.length > 0 && (
        <form onSubmit={enregistrer}>
          {champs.map((champ) => (
            <Champ key={champ.champ} label={t(champ.libelle)} obligatoire={champ.obligatoire}>
              {champ.attache_documents ? (
                <ChoisirDocuments
                  valeur={attaches[champ.champ] || []}
                  ariaLabel={t(champ.libelle)}
                  categorieId={categorieId}
                  champ={champ.champ}
                  onChange={(liste) =>
                    setAttaches((courant) => ({ ...courant, [champ.champ]: liste }))}
                />
              ) : (
                <SaisieChamp
                  champ={champ}
                  valeur={valeurs[champ.champ] || ""}
                  onChange={(v) =>
                    setValeurs((courant) => ({ ...courant, [champ.champ]: v }))}
                  affichage={affichages[champ.champ]}
                  onAffichage={(colonnes) => setAffichages((courant) => ({
                    ...courant, [champ.champ]: colonnes,
                  }))}
                />
              )}
            </Champ>
          ))}

          {/* Le papier est **facultatif** : on note d'abord, il arrive ensuite,
              ou jamais. Le proposer ici évite d'avoir à rouvrir la fiche quand on
              l'a déjà sous la main. */}
          <label style={champStyle}>{t("Document (facultatif)")}</label>
          {fichier ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5,
                          padding: "8px 12px", background: "var(--bg-panel-alt)",
                          border: "1px solid var(--line)", borderRadius: "var(--radius)" }}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis",
                             whiteSpace: "nowrap" }}>{fichier.name}</span>
              <button type="button" onClick={() => setFichier(null)}
                      style={{ border: "none", background: "transparent",
                               color: "var(--ink-faint)", fontSize: 11.5, cursor: "pointer" }}>
                Retirer
              </button>
            </div>
          ) : (
            <ZoneDepot
              invitation={t("Glissez un document ici pour le joindre à cette entrée")}
              ariaLabel={t("Joindre un document à cette entrée")}
              // Rien ne part au serveur : l'entrée n'existe pas encore. On garde
              // le fichier et on l'enverra juste après sa création.
              envoyer={async (choisi) => setFichier(choisi)}
              succes={() => t("Il sera joint à l'entrée dès qu'elle sera créée.")}
            />
          )}

          {erreur && (
            <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>
          )}

          <button type="submit" disabled={envoi} style={{ ...boutonPrimaire, marginTop: 14 }}>
            {envoi ? "Enregistrement…" : "Ajouter"}
          </button>
        </form>
      )}

      {rien && erreur && (
        <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>
      )}
    </Modal>
  );
}
