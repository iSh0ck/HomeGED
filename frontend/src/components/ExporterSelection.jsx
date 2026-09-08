import React, { useEffect, useRef, useState } from "react";
import { BookmarkPlus, Trash2, X } from "lucide-react";
import { api } from "../api";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "./Modal.jsx";
import { t } from "../lib/langue";
import { ajouterModele, lireModeles, retirerModele } from "../lib/modelesExport";
import Liste from "./champs/Liste.jsx";

/**
 * Sortir une sélection rangée selon un modèle (§21.13).
 *
 * L'export de secours (§17.30) sort **tout** le foyer, une fois, sous mot de
 * passe : il répond à « je ne me sers plus de la GED ». Celui-ci répond à
 * l'autre besoin, quotidien — donner au comptable les factures de l'année,
 * rangées par mois, nommées comme il les attend.
 *
 * L'archive ne se construit pas dans la fenêtre : cinq cents PDF tiennent une
 * connexion ouverte plusieurs minutes. Le serveur de travaux s'en charge, et la
 * liste des demandes dit où elles en sont — on revient chercher.
 *
 * Trois manques comblés au §22.66, tous du même genre — on travaillait sans voir :
 *
 *   * l'**aperçu** dit le chemin qu'auront trois vrais documents de la
 *     sélection. On écrivait le modèle à l'aveugle et l'on découvrait le
 *     rangement une fois l'archive construite, quelques minutes plus tard ;
 *   * le **nombre** de documents : « exporter cette sélection » ne disait pas
 *     s'il s'agissait de trois documents ou de deux mille ;
 *   * les **trous se cliquent** au lieu de se recopier, et s'insèrent là où est
 *     le curseur.
 *
 * Et l'on peut enfin **supprimer** une demande : une archive est une copie
 * complète d'une partie du foyer posée sur le disque, la laisser traîner parce
 * que rien ne permet de l'enlever était le contraire de ce qu'on veut.
 */
/** Un modèle n'a pas de nom : sa valeur le désigne, et sert donc de clé. */
const cleModele = (modele) => `${modele.dossier}|${modele.nom}`;
const etiquetteModele = (modele) => `${modele.dossier || "—"} / ${modele.nom || "—"}`;

const boutonDiscret = {
  display: "inline-flex", alignItems: "center", gap: 5,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "3px 9px",
  fontSize: 11.5, cursor: "pointer",
};

export default function ExporterSelection({ criteres, categorieId, onFermer }) {
  const [modeleDossier, setModeleDossier] = useState("{annee}/{type}");
  const [modeleNom, setModeleNom] = useState("{nom_fichier}");
  const [trous, setTrous] = useState({});
  const [demandes, setDemandes] = useState([]);
  const [apercu, setApercu] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [suppression, setSuppression] = useState(null);
  // Les modèles d'arborescence gardés sous la main (§22.83). Sans nom : un
  // modèle **est** sa valeur, et l'exemple achève de le reconnaître.
  const [modeles, setModeles] = useState(lireModeles);
  // Le modèle gardé qui correspond à ce qui est réglé, s'il y en a un : c'est
  // lui que la liste montre comme choisi, et lui seul qu'on peut oublier.
  const modeleGarde = modeles.find(
    (m) => m.dossier === modeleDossier && m.nom === modeleNom) || null;
  // Le champ où un trou cliqué doit atterrir : celui qu'on vient de quitter.
  const dernierChamp = useRef("dossier");
  const champs = { dossier: useRef(null), nom: useRef(null) };

  function charger() {
    api.exportsModele().then(setDemandes).catch(() => {});
  }

  useEffect(() => {
    api.trousExport()
      .then((r) => {
        setTrous(r.trous || {});
        setModeleDossier(r.modele_dossier || "{annee}/{type}");
        setModeleNom(r.modele_nom || "{nom_fichier}");
      })
      .catch((e) => setErreur(e.message));
    charger();
    // Les archives se construisent hors de la requête : on revient voir où elles
    // en sont plutôt que de faire attendre devant une fenêtre figée.
    const timer = setInterval(charger, 4000);
    return () => clearInterval(timer);
  }, []);

  // L'aperçu suit la frappe, après un court silence : chaque caractère tapé ne
  // vaut pas une requête, et l'on veut malgré tout voir le rangement se former.
  useEffect(() => {
    let annule = false;
    const minuterie = setTimeout(() => {
      api.apercuExportModele({
        criteres, categorie_id: categorieId ?? null,
        modele_dossier: modeleDossier, modele_nom: modeleNom,
      })
        .then((r) => { if (!annule) setApercu(r); })
        .catch(() => { if (!annule) setApercu(null); });
    }, 350);
    return () => { annule = true; clearTimeout(minuterie); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeleDossier, modeleNom, JSON.stringify(criteres), categorieId]);

  /** Insère un trou à l'endroit du curseur, dans le champ qu'on vient d'écrire. */
  function insererTrou(trou) {
    const cible = dernierChamp.current;
    const element = champs[cible].current;
    const valeur = cible === "dossier" ? modeleDossier : modeleNom;
    const poser = cible === "dossier" ? setModeleDossier : setModeleNom;
    const debut = element?.selectionStart ?? valeur.length;
    const fin = element?.selectionEnd ?? valeur.length;
    const marque = `{${trou}}`;
    poser(valeur.slice(0, debut) + marque + valeur.slice(fin));
    // Le curseur reste derrière ce qu'on vient d'insérer : on enchaîne.
    requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(debut + marque.length, debut + marque.length);
    });
  }

  async function demander() {
    setErreur(null);
    setEnvoi(true);
    try {
      await api.demanderExportModele({
        criteres, categorie_id: categorieId ?? null,
        modele_dossier: modeleDossier, modele_nom: modeleNom,
      });
      charger();
    } catch (e) {
      setErreur(e.message);
    }
    setEnvoi(false);
  }

  async function supprimer(id) {
    setSuppression(id);
    setErreur(null);
    try {
      await api.supprimerExportModele(id);
      setDemandes((liste) => liste.filter((d) => d.id !== id));
    } catch (e) {
      setErreur(e.message);
    }
    setSuppression(null);
  }

  return (
    <Modal titre={t("Exporter cette sélection")}
           sousTitre={apercu
             ? t("{n} document(s) — rangés comme vous le voulez, par le serveur",
               { n: apercu.total })
             : t("Une archive rangée comme vous la voulez, construite par le serveur")}
           onClose={onFermer} width={720}>
      <label style={{ ...champStyle, marginTop: 0 }}>{t("Dossiers")}</label>
      <input ref={champs.dossier} value={modeleDossier} aria-label={t("Modèle de dossiers")}
             onFocus={() => { dernierChamp.current = "dossier"; }}
             onChange={(e) => setModeleDossier(e.target.value)} style={inputStyle} />

      <label style={champStyle}>{t("Nom du fichier")}</label>
      <input ref={champs.nom} value={modeleNom} aria-label={t("Modèle de nom de fichier")}
             onFocus={() => { dernierChamp.current = "nom"; }}
             onChange={(e) => setModeleNom(e.target.value)} style={inputStyle} />

      {/* Les trous se cliquent : les recopier à la main était la première source
          de modèle qui ne rend rien. */}
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.8 }}>
        {t("Cliquez pour insérer :")}{" "}
        {Object.entries(trous).map(([trou, aide]) => (
          <button
            key={trou}
            type="button"
            onClick={() => insererTrou(trou)}
            title={t(aide)}
            style={{
              border: "1px solid var(--line-strong)", background: "transparent",
              color: "var(--ink-soft)", borderRadius: 10, padding: "1px 7px",
              fontSize: 11, fontFamily: "var(--font-mono)", marginRight: 4,
            }}
          >
            {`{${trou}}`}
          </button>
        ))}
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6, lineHeight: 1.5 }}>
        {t("Un trou vide disparaît du nom : l'archive est lue par quelqu'un qui n'a jamais vu vos modèles.")}
      </div>

      {/* Garder ce réglage pour la prochaine fois (§22.83). Le bouton n'apparaît
          pas quand il n'y a rien à garder — un modèle déjà gardé, ou un aperçu
          qu'on n'a pas encore. */}
      {apercu?.exemples?.length > 0 && !modeleGarde && (
        <button
          type="button"
          onClick={() => setModeles(ajouterModele({
            dossier: modeleDossier, nom: modeleNom, exemple: apercu.exemples[0],
          }))}
          style={{ ...boutonDiscret, marginTop: 10 }}
          title={t("Retrouver ce réglage la prochaine fois, sans le retaper")}
        >
          <BookmarkPlus size={12} />
          {t("Garder ce modèle")}
        </button>
      )}

      {/* Une liste déroulante et non une pile (§22.84) : douze modèles gardés
          tiennent dans un menu, pas sous un formulaire qu'on parcourt déjà.
          L'intitulé porte la valeur **et** l'exemple — un modèle n'a pas de nom,
          c'est ce qui le désigne. */}
      {modeles.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Liste
              compact
              recherchable
              valeur={modeleGarde ? cleModele(modeleGarde) : ""}
              ariaLabel={t("Modèles gardés")}
              placeholder={t("— Reprendre un modèle gardé —")}
              options={modeles.map((modele) => ({
                valeur: cleModele(modele),
                libelle: modele.exemple
                  ? `${etiquetteModele(modele)} — ${modele.exemple}`
                  : etiquetteModele(modele),
              }))}
              onChange={(cle) => {
                const choisi = modeles.find((m) => cleModele(m) === cle);
                if (!choisi) return;
                setModeleDossier(choisi.dossier);
                setModeleNom(choisi.nom);
              }}
            />
          </div>
          {/* On n'oublie que ce qu'on a sous les yeux : le modèle en cours. */}
          {modeleGarde && (
            <button
              type="button"
              onClick={() => setModeles(retirerModele(modeleGarde))}
              aria-label={t("Oublier ce modèle")}
              title={t("Oublier ce modèle")}
              style={{ border: "none", background: "transparent", padding: 2,
                       color: "var(--ink-faint)", display: "flex" }}
            >
              <X size={13} />
            </button>
          )}
        </div>
      )}

      {/* Ce que l'archive contiendra, sur de vrais documents de la sélection. */}
      <div style={{ marginTop: 12, padding: "8px 10px", background: "var(--bg-panel-alt)",
                    border: "1px solid var(--line)", borderRadius: "var(--radius)" }}>
        <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 4 }}>
          {t("Dans l'archive")}
        </div>
        {apercu?.exemples?.length ? (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, lineHeight: 1.6,
                        wordBreak: "break-all" }}>
            {apercu.exemples.map((chemin) => <div key={chemin}>{chemin}</div>)}
            {apercu.total > apercu.exemples.length && (
              <div style={{ color: "var(--ink-faint)", fontFamily: "inherit" }}>
                {t("… et {n} autre(s)", { n: apercu.total - apercu.exemples.length })}
              </div>
            )}
          </div>
        ) : (
          <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
            {apercu ? t("Aucun document dans cette sélection.") : t("Calcul de l'aperçu…")}
          </div>
        )}
      </div>

      {erreur && (
        <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>
      )}

      <button onClick={demander} disabled={envoi || apercu?.total === 0}
              style={{ ...boutonPrimaire, marginTop: 14 }}>
        {envoi ? t("Demande en cours…") : t("Demander l'archive")}
      </button>

      {demandes.length > 0 && (
        <div style={{ marginTop: 18, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 6 }}>
            {t("Vos demandes")}
          </div>
          {demandes.map((d) => (
            <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 10,
                                     fontSize: 12, padding: "3px 0" }}>
              <span style={{ color: "var(--ink-faint)", minWidth: 130 }}>
                {d.date_demande?.replace("T", " ")}
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                {d.statut === "pret" ? d.message
                  : d.statut === "erreur" ? `${t("Échec")} : ${t(d.message)}`
                    : d.statut === "en_cours" ? t("Construction en cours…")
                      : t("En attente du serveur…")}
              </span>
              {d.pret && (
                <a href={`/api/exports-modele/${d.id}/fichier`}
                   style={{ color: "var(--accent)" }}>{t("Télécharger")}</a>
              )}
              {/* Une archive est une copie complète d'une partie du foyer posée
                  sur le disque : on doit pouvoir l'enlever (§22.66). */}
              <button
                onClick={() => supprimer(d.id)}
                disabled={suppression === d.id}
                aria-label={t("Supprimer cette archive")}
                title={t("Supprimer cette archive et son fichier")}
                style={{ border: "none", background: "transparent", padding: 2,
                         color: "var(--ink-faint)", display: "flex" }}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
