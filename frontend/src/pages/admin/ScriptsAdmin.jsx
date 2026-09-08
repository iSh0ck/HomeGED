import React, { useEffect, useState } from "react";
import { AlertTriangle, History, Play, Plus, Trash2 } from "lucide-react";
import { adminApi } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import { t } from "../../lib/langue";

const EXEMPLE = `def executer(contexte):
    ""t("Le point d'entrée. Ce qu'il rend est affiché ci-dessous.")""
    lignes = contexte.get("lignes", [])
    return ft("{len(lignes)} ligne(s) reçue(s)")
`;

/**
 * Le mode développeur (§21.14).
 *
 * La porte de sortie universelle : ce qu'aucun écran ne prévoit et qu'on ne va
 * pas coder pour un foyer. L'écran commence donc par **dire ce que cela pose**,
 * et ne montre l'éditeur qu'ensuite : un interrupteur qu'on arme sans savoir ce
 * qu'il ouvre n'est pas un choix, c'est un piège.
 */
export default function ScriptsAdmin() {
  const [etat, setEtat] = useState({ mode_actif: false, scripts: [], duree_max: 60 });
  const [edition, setEdition] = useState(null);
  const [resultat, setResultat] = useState(null);
  const [contexte, setContexte] = useState("{}");
  const [erreur, setErreur] = useState(null);
  // Ce qui a déjà tourné (§22.43). Le serveur le gardait depuis le §21.14 — « un
  // script a tourné » sans trace ne serait qu'une rumeur — mais rien ne le
  // montrait. C'est pourtant la contrepartie du mode développeur : ce qu'on
  // s'autorise doit se relire.
  const [executions, setExecutions] = useState([]);
  const [historique, setHistorique] = useState(false);

  function charger() {
    adminApi.scripts().then(setEtat).catch((e) => setErreur(e.message));
    adminApi.executionsScript().then(setExecutions).catch(() => setExecutions([]));
  }
  useEffect(charger, []);

  async function basculer() {
    setErreur(null);
    try {
      await adminApi.enregistrerReglages({ mode_developpeur: etat.mode_actif ? "0" : "1" });
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const charge = { nom: edition.nom, description: edition.description, code: edition.code };
      if (edition.id) await adminApi.modifierScript(edition.id, charge);
      else await adminApi.creerScript(charge);
      setEdition(null);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function lancer(script) {
    setErreur(null);
    setResultat({ script, sortie: t("Exécution…") });
    try {
      let donnees = {};
      try {
        donnees = JSON.parse(contexte || "{}");
      } catch {
        throw new Error(t("Le contexte doit être un objet JSON — « {\"lignes\": [1, 2]} »."));
      }
      const bilan = await adminApi.executerScript(script.id, { contexte: donnees });
      setResultat({ script, ...bilan });
    } catch (err) {
      setResultat(null);
      setErreur(err.message);
    }
  }

  return (
    <div>
      <h2 style={{ fontSize: 16, margin: "0 0 6px" }}>{t("Scripts (mode développeur)")}</h2>

      {/* Ce que le mode pose, dit avant tout le reste. */}
      <div style={{
        display: "flex", gap: 10, padding: "10px 14px", borderRadius: "var(--radius)",
        background: etat.mode_actif ? "var(--brick-soft)" : "var(--bg-panel-alt)",
        border: "1px solid var(--line)", fontSize: 12.5, lineHeight: 1.55, maxWidth: 780,
      }}>
        <AlertTriangle size={16} color="var(--brick)" style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>{etat.mode_actif
            ? t("Le mode développeur est armé.")
            : t("Le mode développeur est éteint.")}</strong>{" "}
          Un script est du code exécuté par le service : qui peut en écrire un peut faire
          ce que le service peut faire, et ce qu'on lui donne peut en ressortir. Son accès
          réseau n'est pas bloqué.
          <div style={{ marginTop: 6, color: "var(--ink-soft)" }}>
            Ce qui l'encadre : un seul point d'entrée <code>executer(contexte)</code>, un
            contexte explicite, un processus séparé arrêté au bout de {etat.duree_max}{" "}
            secondes, <strong>aucun accès à la base</strong> — un script rend un texte, il
            ne modifie rien —, et chaque exécution journalisée.
          </div>
          {/* L'interrupteur est ici, sous ce qu'il implique — c'est la règle du
              §21.14 : « il dit les risques avant d'être armé ». Le chercher dans
              une liste de trente-cinq réglages revenait à l'armer sans les
              avoir lus. Il reste aussi dans les réglages généraux, à sa place
              d'exploitation. */}
          <button
            onClick={basculer}
            style={{
              marginTop: 10, display: "inline-flex", alignItems: "center", gap: 6,
              border: "1px solid " + (etat.mode_actif ? "var(--brick)" : "var(--line-strong)"),
              background: etat.mode_actif ? "var(--brick)" : "transparent",
              color: etat.mode_actif ? "#fff" : "var(--ink)",
              borderRadius: "var(--radius)", padding: "5px 12px", fontSize: 12.5,
              fontWeight: 600, cursor: "pointer",
            }}
          >
            {etat.mode_actif ? t("Désarmer le mode développeur") : t("J'ai lu, armer le mode")}
          </button>
        </div>
      </div>

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {etat.mode_actif && (
        <>
          <div style={{ display: "flex", justifyContent: "flex-end", margin: "14px 0 8px" }}>
            <button onClick={() => setEdition({ nom: "", description: "", code: EXEMPLE })}
                    style={boutonPrimaire}>
              <Plus size={13} /> Nouveau script
            </button>
          </div>

          <AdminTable
            colonnes={[
              { key: "nom", label: "Nom" },
              { key: "description", label: t("Ce qu'il fait"),
                render: (s) => (
                  <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>
                    {s.description || "—"}
                  </span>
                ) },
              { key: "par", label: t("Écrit par") },
              { key: "actions", label: "", render: (s) => (
                <span style={{ display: "flex", gap: 6 }}>
                  <button onClick={() => lancer(s)} title={t("Exécuter maintenant")}
                          style={boutonDiscret}>
                    <Play size={12} /> Exécuter
                  </button>
                  <button onClick={() => setEdition({ ...s })} style={boutonDiscret}>
                    Modifier
                  </button>
                  <button
                    onClick={async () => { await adminApi.supprimerScript(s.id); charger(); }}
                    title={t("Supprimer ce script")} style={boutonDiscret}>
                    <Trash2 size={12} />
                  </button>
                </span>
              ) },
            ]}
            lignes={etat.scripts}
          />

          {/* L'historique se déplie : il compte peu de lignes le jour où l'on
              écrit un script, et beaucoup trois mois plus tard. */}
          <div style={{ margin: "14px 0 4px" }}>
            <button onClick={() => setHistorique((v) => !v)} style={boutonDiscret}>
              <History size={12} />
              {historique ? "Masquer" : "Voir"} les exécutions passées ({executions.length})
            </button>
          </div>
          {historique && (
            executions.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "4px 2px" }}>
                {t("Aucun script n'a encore été exécuté.")}
              </div>
            ) : (
              <AdminTable
                cle="scripts.executions"
                colonnes={[
                  { key: "date", label: "Quand" },
                  { key: "script", label: "Script",
                    render: (e) => (etat.scripts.find((s) => s.id === e.script_id)?.nom
                                    || `nº${e.script_id}`) },
                  { key: "par", label: "Par", render: (e) => e.par || "—" },
                  { key: "duree_ms", label: t("Durée"),
                    render: (e) => (e.duree_ms != null ? `${e.duree_ms} ms` : "—") },
                  { key: "reussite", label: t("Résultat"), render: (e) => (
                    <span style={{ color: e.reussite ? "var(--accent)" : "var(--brick)" }}>
                      {e.reussite ? t("réussi") : (e.erreur || t("échec")).split("\n")[0].slice(0, 80)}
                    </span>
                  ) },
                ]}
                lignes={executions}
              />
            )
          )}

          <label style={champStyle}>{t("Contexte donné au script (JSON)")}</label>
          <input value={contexte} aria-label={t("Contexte donné au script")}
                 onChange={(e) => setContexte(e.target.value)}
                 style={{ ...inputStyle, fontFamily: "var(--font-mono)" }} />
          <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4 }}>
            {t("C'est tout ce que le script recevra : il ne va pas se servir, on lui donne.")}
          </div>
        </>
      )}

      {resultat && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 4 }}>
            {resultat.script?.nom}
            {resultat.duree_ms != null && ` — ${resultat.duree_ms} ms`}
          </div>
          <pre style={{
            margin: 0, padding: 12, background: "var(--bg-panel-alt)",
            border: "1px solid var(--line)", borderRadius: "var(--radius)",
            fontSize: 12, whiteSpace: "pre-wrap", maxHeight: 320, overflow: "auto",
            color: resultat.erreur ? "var(--brick)" : "var(--ink)",
          }} className="scrollbar-thin">
            {resultat.erreur || resultat.sortie}
          </pre>
        </div>
      )}

      {edition && (
        <Modal titre={edition.id ? `Modifier « ${edition.nom} »` : t("Nouveau script")}
               onClose={() => setEdition(null)} width={860}>
          <form onSubmit={enregistrer}>
            <label style={{ ...champStyle, marginTop: 0 }}>Nom</label>
            <input required value={edition.nom} style={inputStyle}
                   onChange={(e) => setEdition({ ...edition, nom: e.target.value })} />

            <label style={champStyle}>{t("Ce qu'il fait")}</label>
            <input value={edition.description || ""} style={inputStyle}
                   onChange={(e) => setEdition({ ...edition, description: e.target.value })} />

            <label style={champStyle}>Code</label>
            <textarea
              value={edition.code}
              aria-label={t("Code du script")}
              onChange={(e) => setEdition({ ...edition, code: e.target.value })}
              rows={18}
              style={{ ...inputStyle, fontFamily: "var(--font-mono)", fontSize: 12.5 }}
            />
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4 }}>
              Le script doit définir <code>def executer(contexte):</code>. Ce qu'il rend est
              affiché ; il n'a accès ni à la base ni aux fichiers du foyer.
            </div>

            <button type="submit" style={{ ...boutonPrimaire, marginTop: 14 }}>
              Enregistrer
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}

const boutonDiscret = {
  display: "inline-flex", alignItems: "center", gap: 4, border: "1px solid var(--line-strong)",
  background: "transparent", color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "2px 8px", fontSize: 11.5, cursor: "pointer",
};
