import React, { useEffect, useState } from "react";
import { Play, Zap } from "lucide-react";
import { adminApi, api } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import Liste from "../../components/champs/Liste.jsx";
import EditeurCriteres from "../../components/EditeurCriteres.jsx";
import { aplatirArborescence } from "../../lib/arborescence";
import { formaterHorodatage, ilYA } from "../../lib/horodatage";
import { t } from "../../lib/langue";

const VIDE = { nom: "", declencheur: "document_depose", categorie_id: null,
               conditions: [], actions: [], actif: true, ordre: 100 };

/**
 * Les automatisations « quand… alors… » (§21.8).
 *
 * Le workflow d'EzGED enchaîne des étapes et des tâches. Pour une maison, la même
 * idée tient en une phrase : quand un document arrive et que telle condition est
 * vraie, faire ceci. Tout se règle ici — rien n'est écrit dans le code pour un
 * type de document en particulier.
 *
 * Deux choses rendent l'ensemble utilisable, et elles ont autant compté que le
 * moteur : on peut **essayer** une règle sur un document sans rien enregistrer,
 * et le journal dit ce qui s'est déclenché — **y compris ce qui n'a rien fait**,
 * qui est la question qu'on se pose le plus souvent.
 */
export default function AutomatisationsAdmin() {
  const [regles, setRegles] = useState([]);
  const [catalogue, setCatalogue] = useState({ declencheurs: [], actions: [] });
  const [categories, setCategories] = useState([]);
  const [colonnes, setColonnes] = useState({});
  const [edition, setEdition] = useState(null);
  const [suppression, setSuppression] = useState(null);
  const [journal, setJournal] = useState([]);
  const [erreur, setErreur] = useState(null);

  function charger() {
    adminApi.automatisations().then(setRegles).catch((e) => setErreur(e.message));
    adminApi.journalAutomatisations().then(setJournal).catch(() => {});
  }
  useEffect(() => {
    charger();
    adminApi.catalogueAutomatisations().then(setCatalogue).catch(() => {});
    adminApi.categories().then(setCategories).catch(() => {});
    api.colonnesCategories().then((r) => setColonnes(r.colonnes || {})).catch(() => {});
  }, []);

  const types = categories.filter((c) => (c.nature || "type") !== "dossier");
  const champsProposes = (categorieId) => {
    const liste = colonnes[String(categorieId)] || colonnes.defaut || [];
    return [{ champ: "texte", libelle: t("Texte du document"), filtre: "texte", type: "texte" },
            ...liste];
  };

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const charge = { ...edition, nom: edition.nom.trim() };
      if (edition.id) await adminApi.modifierAutomatisation(edition.id, charge);
      else await adminApi.creerAutomatisation(charge);
      setEdition(null);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.55,
                  marginBottom: 16, maxWidth: 700 }}>
        <strong>Quand</strong> quelque chose arrive, <strong>si</strong> les conditions sont
        réunies, <strong>alors</strong> faire ceci. Les conditions parlent le même langage
        que les filtres du registre : tout ce qui se filtre se teste. Une règle peut
        s'essayer sur un document sans rien enregistrer.
      </p>

      {erreur && (
        <div style={{ fontSize: 12.5, color: "var(--brick)", marginBottom: 12 }}>{erreur}</div>
      )}

      <AdminTable
        libelleAjout={t("Nouvelle automatisation")}
        onAjouter={() => setEdition({ ...VIDE })}
        onModifier={(r) => setEdition(r)}
        onSupprimer={setSuppression}
        lignes={regles}
        colonnes={[
          { key: "nom", label: "Nom" },
          { key: "declencheur", label: "Quand",
            render: (r) => catalogue.declencheurs.find((d) => d.cle === r.declencheur)
              ?.libelle || r.declencheur },
          { key: "categorie", label: "Type",
            render: (r) => r.categorie || <Discret>tous</Discret> },
          { key: "conditions", label: "Conditions",
            render: (r) => (r.conditions.length
              ? `${r.conditions.length} condition${r.conditions.length > 1 ? "s" : ""}`
              : <Discret>aucune</Discret>) },
          { key: "actions", label: "Alors",
            render: (r) => r.actions.map((a) => catalogue.actions.find(
              (c) => c.cle === a.type)?.libelle || a.type).join(" · ") },
          { key: "actif", label: "Active",
            render: (r) => (r.actif ? "oui" : <Discret>non</Discret>) },
        ]}
      />

      <h3 style={{ fontSize: 14, margin: "24px 0 6px" }}>{t("Ce qui s'est déclenché")}</h3>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", marginBottom: 10 }}>
        {t("Les examens sans suite y figurent aussi : « pourquoi cette règle n'a rien fait » est la question qu'on se pose le plus souvent.")}
      </p>
      {journal.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>
          {t("Rien ne s'est encore déclenché.")}
        </div>
      ) : (
        <AdminTable
          lignes={journal}
          colonnes={[
            { key: "date", label: "Quand",
              render: (l) => (
                <span title={formaterHorodatage(l.date)}>{ilYA(l.date)}</span>
              ) },
            { key: "automatisation", label: t("Règle") },
            { key: "document_id", label: "Document",
              render: (l) => (l.document_id ? `nº${l.document_id}` : <Discret>—</Discret>) },
            { key: "agi", label: "Effet",
              render: (l) => (l.agi
                ? <span style={{ color: "var(--accent)" }}>
                    {(l.detail?.faits || []).join(" · ") || "agi"}
                  </span>
                : <Discret>
                    {l.detail?.conditions_reunies === false
                      ? t("conditions non réunies") : t("aucune action")}
                  </Discret>) },
          ]}
        />
      )}

      {edition && (
        <Modal titre={edition.id ? t("Modifier l'automatisation") : t("Nouvelle automatisation")}
               onClose={() => setEdition(null)} width={760}>
          <form onSubmit={enregistrer}>
            <label style={{ ...champStyle, marginTop: 0 }}>Nom</label>
            <input required value={edition.nom} style={inputStyle}
                   onChange={(e) => setEdition({ ...edition, nom: e.target.value })} />

            <label style={champStyle}>Quand</label>
            <Liste
              valeur={edition.declencheur}
              ariaLabel={t("Déclencheur")}
              options={catalogue.declencheurs.map((d) => ({ valeur: d.cle,
                                                            libelle: d.libelle }))}
              onChange={(v) => setEdition({ ...edition, declencheur: v })}
            />
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                          lineHeight: 1.45 }}>
              {catalogue.declencheurs.find((d) => d.cle === edition.declencheur)?.description}
            </div>

            <label style={champStyle}>{t("Sur quel type de document")}</label>
            <Liste
              valeur={edition.categorie_id ?? ""}
              ariaLabel={t("Type de document")}
              options={[{ valeur: "", libelle: "— tous —" },
                        ...aplatirArborescence(types).map((c) => ({
                          valeur: c.id, libelle: c.nom }))]}
              onChange={(v) => setEdition({ ...edition,
                                            categorie_id: v ? Number(v) : null })}
            />

            <label style={champStyle}>{t("Si (toutes les conditions)")}</label>
            <EditeurCriteres
              criteres={edition.conditions || []}
              champs={champsProposes(edition.categorie_id)}
              categories={categories}
              onChange={(conditions) => setEdition({ ...edition, conditions })}
            />
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4 }}>
              {t("Aucune condition : la règle s'applique à tout ce que le déclencheur amène.")}
            </div>

            <label style={champStyle}>Alors</label>
            <EditeurActions
              actions={edition.actions || []}
              catalogue={catalogue.actions}
              types={types}
              onChange={(actions) => setEdition({ ...edition, actions })}
            />

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={edition.actif}
                     onChange={(e) => setEdition({ ...edition, actif: e.target.checked })} />
              Active
            </label>

            {edition.id && <Essai regleId={edition.id} />}

            <button type="submit" style={boutonPrimaire}>Enregistrer</button>
          </form>
        </Modal>
      )}

      {suppression && (
        <ConfirmerSuppression
          intitule={`l'automatisation « ${suppression.nom} »`}
          consequences={[{ libelle: t("son journal d'exécutions") }]}
          onConfirmer={async () => {
            await adminApi.supprimerAutomatisation(suppression.id);
            setSuppression(null);
            charger();
          }}
          onAnnuler={() => setSuppression(null)}
        />
      )}
    </div>
  );
}

/** Les actions, composées à partir du catalogue que le serveur déclare. */
function EditeurActions({ actions, catalogue, types, onChange }) {
  function ajouter(type) {
    if (!type) return;
    onChange([...actions, { type }]);
  }
  function changer(index, cle, valeur) {
    onChange(actions.map((a, i) => (i === index ? { ...a, [cle]: valeur } : a)));
  }

  return (
    <div>
      {actions.map((action, index) => {
        const details = catalogue.find((c) => c.cle === action.type);
        return (
          <div key={index} style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                                    padding: "9px 12px", marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Zap size={13} color="var(--accent)" />
              <strong style={{ fontSize: 12.5 }}>{details?.libelle || action.type}</strong>
              <div style={{ flex: 1 }} />
              <button type="button"
                      onClick={() => onChange(actions.filter((_, i) => i !== index))}
                      style={{ border: "none", background: "transparent",
                               color: "var(--brick)", fontSize: 11.5 }}>
                retirer
              </button>
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", margin: "3px 0 6px",
                          lineHeight: 1.45 }}>
              {details?.description}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {(details?.parametres || []).map((p) => (
                p.type === "booleen" ? (
                  <label key={p.cle} style={{ display: "flex", alignItems: "center", gap: 6,
                                              fontSize: 12 }}>
                    <input type="checkbox" checked={!!action[p.cle]}
                           onChange={(e) => changer(index, p.cle, e.target.checked)} />
                    {t(p.libelle)}
                  </label>
                ) : p.type === "categorie" ? (
                  <div key={p.cle} style={{ width: 220 }}>
                    <Liste
                      valeur={action[p.cle] ?? ""}
                      ariaLabel={t(p.libelle)}
                      options={[{ valeur: "", libelle: `— ${t(p.libelle)} —` },
                                ...types.map((c) => ({ valeur: c.id, libelle: c.nom }))]}
                      onChange={(v) => changer(index, p.cle, v ? Number(v) : null)}
                    />
                  </div>
                ) : (
                  <input
                    key={p.cle}
                    value={action[p.cle] || ""}
                    placeholder={`${t(p.libelle)}${p.exemple ? ` (ex. ${p.exemple})` : ""}`}
                    aria-label={t(p.libelle)}
                    onChange={(e) => changer(index, p.cle, e.target.value)}
                    style={{ ...inputStyle, width: 220, marginTop: 0 }}
                  />
                )
              ))}
            </div>
          </div>
        );
      })}

      <Liste
        valeur=""
        ariaLabel={t("Ajouter une action")}
        options={[{ valeur: "", libelle: t("— ajouter une action —") },
                  ...catalogue.map((c) => ({ valeur: c.cle, libelle: c.libelle }))]}
        onChange={ajouter}
      />
    </div>
  );
}

/**
 * Essayer la règle sur un document, sans rien enregistrer.
 *
 * Écrire une automatisation puis attendre le prochain dépôt pour savoir si elle
 * mord est la même boucle décourageante que celle des règles d'extraction.
 */
function Essai({ regleId }) {
  const [documentId, setDocumentId] = useState("");
  const [resultat, setResultat] = useState(null);
  const [erreur, setErreur] = useState(null);

  async function essayer() {
    setErreur(null);
    setResultat(null);
    try {
      setResultat(await adminApi.essayerAutomatisation(regleId, Number(documentId)));
    } catch (e) {
      setErreur(e.message);
    }
  }

  return (
    <div style={{ marginTop: 14, padding: "10px 12px", border: "1px solid var(--line)",
                  borderRadius: "var(--radius)", background: "var(--bg-panel-alt)" }}>
      <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 6 }}>
        {t("Essayer sur un document — rien n'est enregistré.")}
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          value={documentId}
          placeholder={t("nº du document")}
          aria-label={t("Numéro du document d'essai")}
          onChange={(e) => setDocumentId(e.target.value)}
          style={{ ...inputStyle, width: 150, marginTop: 0 }}
        />
        <button type="button" onClick={essayer} disabled={!documentId}
                style={{ display: "inline-flex", alignItems: "center", gap: 6,
                         border: "1px solid var(--line-strong)", background: "transparent",
                         color: "var(--ink-soft)", borderRadius: "var(--radius)",
                         padding: "6px 12px", fontSize: 12.5 }}>
          <Play size={13} />
          Essayer
        </button>
      </div>
      {erreur && <div style={{ fontSize: 12, color: "var(--brick)", marginTop: 6 }}>{erreur}</div>}
      {resultat && (
        <div style={{ fontSize: 12.5, marginTop: 8,
                      color: resultat.conditions_reunies ? "var(--accent)" : "var(--ink-soft)" }}>
          {resultat.conditions_reunies
            ? (resultat.faits.length
              ? <>Conditions réunies — aurait fait : {resultat.faits.join(" · ")}.</>
              : <>Conditions réunies, mais aucune action n'aurait eu d'effet (valeur déjà
                  remplie ?).</>)
            : t("Conditions non réunies sur ce document.")}
        </div>
      )}
    </div>
  );
}

function Discret({ children }) {
  return <span style={{ color: "var(--ink-faint)" }}>{children}</span>;
}
