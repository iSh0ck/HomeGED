import React, { useEffect, useState } from "react";
import { RefreshCw, RotateCcw, ChevronDown, ChevronRight, Trash2, Search } from "lucide-react";
import { api, adminApi } from "../../api";
import { formaterHorodatage } from "../../lib/horodatage";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import ChoisirEtape from "../../components/ChoisirEtape.jsx";
import InspecteurDocument from "../../components/InspecteurDocument.jsx";
import Modal from "../../components/Modal.jsx";
import { referenceTache } from "../../lib/travaux";
import { t } from "../../lib/langue";

/**
 * Les états d'une tâche, dans l'ordre où on les lit : ce qui attend une décision
 * ou une action d'abord, ce qui se déroule ensuite, ce qui est derrière nous à la
 * fin (§19.10).
 *
 * Chacun porte son explication (§19.17). Un état se lit en deux mots sur une
 * pastille, mais « bloqué » et « à classer » ne disent pas d'eux-mêmes ce qui
 * s'est passé ni ce qu'on attend de vous — et c'est précisément quand une tâche
 * s'arrête qu'on a besoin de le savoir.
 */
const ETATS = () => [
  { id: "", label: "Toutes",
    aide: t("Toutes les tâches, quel que soit leur état.") },
  { id: "a_classer", label: t("À classer"), couleur: "var(--amber)",
    aide: t("Le fichier a été déposé à un endroit qu'aucun type de document ne réclame. Il n'a pas été océrisé — tant qu'on ignore ce qu'il est, le texte reconnu ne servirait à rien. Dites son type depuis le Centre d'analyse : il rejoindra le bon dossier et le traitement repartira du début.") },
  { id: "bloque", label: t("Champ manquant"), couleur: "var(--amber)",
    aide: t("Le document existe et il est lisible, mais il lui manque un champ que son type exige. Il n'apparaît pas dans le registre tant qu'il est incomplet. Complétez-le depuis le Centre d'analyse, ou corrigez la règle qui devait le trouver — la reprise automatique repassera dessus dans les cinq minutes.") },
  { id: "erreur", label: t("Échec technique"), couleur: "var(--brick)",
    aide: t("Le traitement s'est interrompu : fichier illisible, océrisation impossible. Aucun document n'a été créé. Le fichier reçu est conservé — examinez-le, puis rejouez la tâche.") },
  { id: "echec", label: t("Échec définitif"), couleur: "var(--brick)",
    aide: t("La tâche a échoué autant de fois que le palier réglé l'autorise : le serveur ne la reprendra plus tout seul. C'est le sens du palier — un document irrécupérable ne doit pas tourner pour toujours. Examinez le fichier reçu, corrigez ce qui doit l'être, puis rejouez : la tâche repart de zéro.") },
  { id: "en_attente", label: t("En attente"), couleur: "var(--ink-soft)",
    aide: t("La tâche est en file : le serveur la prendra à son passage suivant.") },
  { id: "en_cours", label: t("En cours"), couleur: "var(--amber)",
    aide: t("Le serveur y travaille en ce moment. L'océrisation est l'étape longue.") },
  { id: "termine", label: t("Terminées"), couleur: "var(--accent)",
    aide: t("Le document est indexé et complet. Ces tâches sont purgées automatiquement après le délai réglé, avec le fichier reçu qu'elles conservaient.") },
  { id: "ignore", label: "Doublons", couleur: "var(--ink-faint)",
    aide: t("Un fichier identique au bit près était déjà connu — comme document ou comme version. Rien n'a été ajouté : il n'y avait rien de neuf à enregistrer.") },
];

/**
 * Surveillance du serveur de travaux (§13) : ce qui attend, ce qui tourne, ce
 * qui a échoué et pourquoi — sans avoir à ouvrir un terminal sur le serveur.
 *
 * Le rejeu ne relance rien directement : l'API pose une demande que le serveur
 * de travaux relève à son passage suivant. L'écran se rafraîchit donc seul tant
 * qu'une demande est en attente.
 */
export default function JobsAdmin() {
  const [jobs, setJobs] = useState([]);
  const [resume, setResume] = useState({ statuts: {}, types: [], total: 0 });
  // Une seule entrée est retenue à la fois : un état **ou** un type de document.
  // Les croiser doublerait le nombre de cases sans répondre à une question qu'on
  // se pose — on cherche « ce qui est bloqué », ou « ce qui concerne les
  // factures », rarement les deux ensemble.
  const [filtre, setFiltre] = useState("");
  const [typeId, setTypeId] = useState(null);
  const [deplie, setDeplie] = useState(null);
  // Travail dont on examine le document (§18.54) : c'est ici qu'on cherche
  // pourquoi il a échoué, sans quitter l'administration.
  const [inspection, setInspection] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [selection, setSelection] = useState(() => new Set());
  const [etapes, setEtapes] = useState([]);
  const [rejeu, setRejeu] = useState(null); // { ids, possibles, titre, sousTitre }
  const [retrait, setRetrait] = useState(null); // { jobs }

  function charger() {
    adminApi.jobs(filtre || undefined, typeId || undefined).then((j) => {
      setJobs(j);
      // on ne garde en sélection que ce qui est encore affiché
      setSelection((prev) => new Set(j.filter((x) => prev.has(x.id)).map((x) => x.id)));
    }).catch((e) => setErreur(e.message)).finally(() => setChargement(false));
    adminApi.resumeJobs(typeId || undefined).then(setResume).catch(() => {});
  }
  useEffect(charger, [filtre, typeId]);
  useEffect(() => { adminApi.etapesRejeu().then(setEtapes).catch(() => {}); }, []);

  function basculer(id) {
    setSelection((prev) => {
      const suivant = new Set(prev);
      if (suivant.has(id)) suivant.delete(id);
      else suivant.add(id);
      return suivant;
    });
  }

  const selectionnes = jobs.filter((j) => selection.has(j.id));
  const toutSelectionne = jobs.length > 0 && selection.size === jobs.length;

  /** Étapes praticables pour toute la sélection : l'intersection des possibles. */
  function etapesCommunes(liste) {
    if (!liste.length) return [];
    return liste
      .map((j) => j.etapes_possibles || [])
      .reduce((acc, e) => acc.filter((x) => e.includes(x)));
  }

  function ouvrirRejeu(liste, titre) {
    const possibles = etapesCommunes(liste);
    setRejeu({
      ids: liste.map((j) => j.id),
      possibles,
      titre,
      sousTitre: liste.length === 1 ? liste[0].nom_fichier : `${liste.length} travaux sélectionnés`,
    });
  }

  async function lancerRejeu(etape) {
    if (rejeu.ids.length === 1) await adminApi.rejouerJob(rejeu.ids[0], etape);
    else {
      const r = await adminApi.actionsGroupeesJobs(rejeu.ids, "rejouer", etape);
      if (r.ignores?.length) {
        setErreur(
          `${r.traites.length} relancé(s). Ignoré(s) : ` +
            r.ignores.map((i) => `nº${i.id} (${i.motif})`).join(", ")
        );
      }
    }
    setRejeu(null);
    setSelection(new Set());
    charger();
  }

  async function supprimerSelection() {
    setErreur(null);
    try {
      const r = await adminApi.actionsGroupeesJobs([...selection], "supprimer");
      if (r.ignores?.length) setErreur(`Ignoré(s) : ${r.ignores.map((i) => `nº${i.id}`).join(", ")}`);
      setSelection(new Set());
      charger();
    } catch (e) {
      setErreur(e.message);
    }
    setRetrait(null);
  }

  // tant qu'un rejeu est en attente ou qu'un travail tourne, l'état va changer
  const enMouvement = jobs.some((j) => j.rejouer_demande || j.statut === "en_cours");
  useEffect(() => {
    if (!enMouvement) return;
    const timer = setInterval(charger, 3000);
    return () => clearInterval(timer);
  }, [enMouvement, filtre]); // eslint-disable-line react-hooks/exhaustive-deps

  async function retirer() {
    await adminApi.supprimerJob(retrait.jobs[0].id).catch((e) => setErreur(e.message));
    charger();
    setRetrait(null);
  }

  const etatCourant = ETATS().find((e) => e.id === filtre);
  // « Toutes » vaut la somme des états affichés : restreint à un type, il ne peut
  // pas annoncer le total du foyer.
  const comptesAffiches = {
    ...(resume.statuts || {}),
    "": Object.values(resume.statuts || {}).reduce((somme, n) => somme + n, 0),
  };
  // Les deux filtres se cumulent depuis le §19.17 : « ce qui est bloqué **dans**
  // les factures » est la question qu'on se pose vraiment quand un type sort du
  // lot. L'intitulé les nomme donc tous les deux.
  const typeCourant = (resume.types || []).find((type) => type.categorie_id === typeId);
  const entreeCourante = [etatCourant?.label || "Toutes",
                          typeCourant ? `· ${typeCourant.nom}` : null]
    .filter(Boolean).join(" ");

  return (
    <div style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
      <MenuTravaux
        types={resume.types || []}
        typeId={typeId}
        onType={setTypeId}
      />

      <div style={{ flex: 1, minWidth: 0 }}>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16, lineHeight: 1.5 }}>
        Chaque fichier déposé donne lieu à une tâche. <strong>{t("À classer")}</strong> : déposé
        à un endroit qu'aucun type de document ne réclame — il n'a pas été océrisé, et
        attend qu'on dise ce qu'il est. <strong>{t("En erreur")}</strong> : échec technique, le
        fichier reçu est conservé. <strong>{t("Bloqué")}</strong> : le document existe, mais il
        lui manque un champ exigé par son type.
        Les tâches terminées et les doublons sont purgés automatiquement ; ce qui appelle
        une action est conservé tant qu'il n'a pas été traité.
      </p>

      {/* Les états à l'horizontale : ils sont sept, tenus sur une ligne, et se
          lisent d'un coup d'œil — c'est ce qu'on regarde en arrivant. Le menu de
          gauche est réservé aux types de document, qui sont autant que le foyer
          en a déclaré et dont la liste, elle, s'allonge. */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        {ETATS().map((e) => {
          const actif = filtre === e.id;
          const nombre = comptesAffiches[e.id] ?? 0;
          return (
            <button
              key={e.id}
              onClick={() => setFiltre(e.id)}
              title={t(e.aide)}
              style={{
                border: "1px solid " + (actif ? "var(--accent)" : "var(--line)"),
                background: actif ? "var(--accent-soft)" : "var(--bg-panel)",
                color: "var(--ink)", borderRadius: 12, padding: "4px 11px", fontSize: 12,
              }}
            >
              {e.label}
              <span className="tabular"
                    style={{ marginLeft: 6, fontWeight: 600,
                             color: nombre ? (e.couleur || "var(--ink-soft)")
                                           : "var(--ink-faint)" }}>
                {nombre}
              </span>
            </button>
          );
        })}
      </div>

      {/* L'explication de l'état retenu, écrite et non seulement en infobulle :
          c'est quand une tâche s'arrête qu'on a besoin de savoir ce qu'on
          attend de vous, et une infobulle se découvre par hasard. */}
      {etatCourant?.id && (
        <div style={{ fontSize: 12, color: "var(--ink-soft)", lineHeight: 1.5,
                      padding: "8px 11px", marginBottom: 12,
                      background: "var(--bg-panel-alt)", borderRadius: "var(--radius)" }}>
          {t(etatCourant.aide)}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{entreeCourante}</span>
        <span className="tabular" style={{ fontSize: 12, color: "var(--ink-faint)" }}>
          {jobs.length} affichée{jobs.length > 1 ? "s" : ""}
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={charger}
          title={t("Rafraîchir")}
          style={{
            display: "flex", alignItems: "center", gap: 5,
            border: "1px solid var(--line-strong)", background: "transparent",
            color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "4px 10px", fontSize: 12,
          }}
        >
          <RefreshCw size={12} />
          Rafraîchir
        </button>
      </div>

      {selection.size > 0 && (
        <div
          style={{
            display: "flex", alignItems: "center", gap: 10, marginBottom: 12,
            padding: "8px 12px", background: "var(--accent-soft)",
            border: "1px solid var(--accent)", borderRadius: "var(--radius)",
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink)" }}>
            {selection.size} travail{selection.size > 1 ? "x" : ""} sélectionné
            {selection.size > 1 ? "s" : ""}
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => ouvrirRejeu(selectionnes, t("Reprendre les travaux sélectionnés"))}
            disabled={!selectionnes.some((j) => j.rejouable)}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              border: "1px solid var(--accent)", background: "var(--bg-panel)",
              color: "var(--accent)", borderRadius: "var(--radius)",
              padding: "4px 11px", fontSize: 12, fontWeight: 500,
              opacity: selectionnes.some((j) => j.rejouable) ? 1 : 0.5,
            }}
          >
            <RotateCcw size={12} />
            Rejouer
          </button>
          <button
            onClick={() => setRetrait({ jobs: selectionnes, groupe: true })}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              border: "1px solid var(--brick)", background: "var(--bg-panel)",
              color: "var(--brick)", borderRadius: "var(--radius)",
              padding: "4px 11px", fontSize: 12, fontWeight: 500,
            }}
          >
            <Trash2 size={12} />
            Retirer du suivi
          </button>
          <button
            onClick={() => setSelection(new Set())}
            style={{ border: "none", background: "transparent", color: "var(--ink-soft)", fontSize: 12 }}
          >
            Annuler
          </button>
        </div>
      )}

      {chargement ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>
      ) : jobs.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>
          Aucun travail {filtre ? t("dans cet état") : t("pour l'instant")}.
        </div>
      ) : (
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
          <div
            style={{
              display: "flex", alignItems: "center", gap: 10, padding: "7px 12px",
              background: "var(--bg-panel-alt)", borderBottom: "1px solid var(--line)",
            }}
          >
            <input
              type="checkbox"
              checked={toutSelectionne}
              onChange={() => setSelection(toutSelectionne ? new Set() : new Set(jobs.map((j) => j.id)))}
              aria-label={t("Tout sélectionner")}
              style={{ margin: 0 }}
            />
            <span style={{ fontSize: 11, color: "var(--ink-faint)", fontWeight: 600 }}>
              {jobs.length} travail{jobs.length > 1 ? "x" : ""}
            </span>
          </div>
          {jobs.map((job, i) => (
            <div key={job.id} style={{ borderTop: i ? "1px solid var(--line)" : "none" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px" }}>
                <input
                  type="checkbox"
                  checked={selection.has(job.id)}
                  onChange={() => basculer(job.id)}
                  aria-label={`Sélectionner ${job.nom_fichier}`}
                  style={{ margin: 0, flexShrink: 0 }}
                />
                <button
                  onClick={() => setDeplie(deplie === job.id ? null : job.id)}
                  aria-label={t("Détail du travail")}
                  style={{ border: "none", background: "transparent", color: "var(--ink-faint)", display: "flex", padding: 0 }}
                >
                  {deplie === job.id ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </button>

                <EtatJob statut={job.statut} />

                {/* Le numéro du travail, affiché et non plus seulement connu de
                    la base (§18.55) : c'est par lui qu'on désigne celui qui pose
                    problème, dans un message comme dans le journal. */}
                <code
                  title={t("Numéro de la tâche")}
                  style={{
                    fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-faint)",
                    flexShrink: 0, width: 66,
                  }}
                >
                  {referenceTache(job.id)}
                </code>

                <span style={{ flex: 1, minWidth: 0, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {job.nom_fichier}
                  {job.message_erreur && (
                    <span style={{ color: "var(--ink-faint)", fontSize: 12, marginLeft: 8 }}>
                      — {job.message_erreur}
                    </span>
                  )}
                </span>

                {job.tentatives > 1 && (
                  <span className="tabular" style={{ fontSize: 11, color: "var(--ink-faint)" }}>
                    {job.tentatives} tentatives
                  </span>
                )}

                {(job.document_id || job.fichier_disponible) && (
                  <button
                    onClick={() => setInspection(job)}
                    title={t("Examiner ce document : aperçu, texte reconnu, matrice OCR")}
                    style={{
                      display: "flex", alignItems: "center", gap: 5,
                      border: "1px solid var(--line-strong)", background: "transparent",
                      color: "var(--ink-soft)", borderRadius: "var(--radius)",
                      padding: "3px 9px", fontSize: 12,
                    }}
                  >
                    <Search size={12} />
                    Examiner
                  </button>
                )}

                {job.rejouer_demande ? (
                  <span style={{ fontSize: 11, color: "var(--amber)", fontWeight: 600 }}>{t("Rejeu demandé…")}</span>
                ) : (
                  job.rejouable && (
                    <button
                      onClick={() => ouvrirRejeu([job], t("Reprendre ce travail"))}
                      title={t("Relancer ce travail à partir d'une étape")}
                      style={{
                        display: "flex", alignItems: "center", gap: 5,
                        border: "1px solid var(--line-strong)", background: "transparent",
                        color: "var(--ink-soft)", borderRadius: "var(--radius)",
                        padding: "3px 9px", fontSize: 12,
                      }}
                    >
                      <RotateCcw size={12} />
                      Rejouer
                    </button>
                  )
                )}

                <button
                  onClick={() => setRetrait({ jobs: [job] })}
                  title={t("Retirer du suivi")}
                  style={{ border: "none", background: "transparent", color: "var(--ink-faint)", fontSize: 16, padding: "0 4px" }}
                >
                  ×
                </button>
              </div>

              {deplie === job.id && (
                <div style={{ padding: "0 12px 12px 46px", fontSize: 12, color: "var(--ink-soft)" }}>
                  <Ligne libelle={t("Dernière étape")} valeur={job.etape} />
                  <Ligne libelle={t("Créé le")} valeur={formaterHorodatage(job.date_creation)} />
                  <Ligne libelle={t("Terminé le")} valeur={formaterHorodatage(job.date_fin)} />
                  <Ligne libelle="Document" valeur={job.document_id ? `nº${job.document_id}` : "—"} />
                  <Ligne libelle={t("Fichier reçu")}
                         valeur={job.fichier_disponible
                           ? job.chemin_source
                           : `${job.chemin_source || "—"} (plus disponible)`}
                         mono />
                  {job.diagnostic && (
                    <>
                      <div style={{ marginTop: 8, fontWeight: 600, color: "var(--ink)" }}>Diagnostic</div>
                      <pre
                        style={{
                          margin: "4px 0 0", padding: 8, background: "var(--bg-panel-alt)",
                          border: "1px solid var(--line)", borderRadius: "var(--radius)",
                          fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "pre-wrap",
                          overflowX: "auto", maxHeight: 220,
                        }}
                      >
                        {job.diagnostic}
                      </pre>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      </div>

      {inspection && (
        <Modal
          titre={`Tâche ${referenceTache(inspection.id)}`}
          sousTitre={inspection.nom_fichier}
          onClose={() => setInspection(null)}
          width={1200}
        >
          {inspection.message_erreur && (
            <div style={{
              marginBottom: 12, padding: "9px 12px", borderRadius: "var(--radius)",
              background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5,
            }}>
              {inspection.message_erreur}
            </div>
          )}
          {!inspection.document_id && (
            <div style={{ fontSize: 12, color: "var(--ink-faint)", marginBottom: 10, lineHeight: 1.5 }}>
              {t("Ce travail n'a produit aucun document : il n'y a ni texte reconnu ni matrice à lire. Reste le fichier tel qu'il a été reçu — c'est en le regardant qu'on comprend en général ce qui s'est passé.")}
            </div>
          )}
          <InspecteurDocument
            documentId={inspection.document_id}
            vueInitiale="apercu"
            hauteur={520}
            chargerFichier={() =>
              // Le fichier reçu quand on l'a encore ; à défaut, le PDF archivé —
              // réécrit par l'océrisation, mais mieux que rien.
              inspection.fichier_disponible
                ? adminApi.originalBlobUrl(inspection.id)
                : api.fichierBlobUrl(inspection.document_id)
            }
          />
        </Modal>
      )}

      {retrait && (
        <ConfirmerSuppression
          intitule={retrait.jobs.length === 1
            ? `le suivi de « ${retrait.jobs[0].nom_fichier} »`
            : `le suivi de ${retrait.jobs.length} travaux`}
          consequences={[
            {
              nature: "suppression",
              libelle: `${retrait.jobs.length} ligne(s) de suivi et leur diagnostic`,
              precision: t("l'historique du traitement et le message d'erreur sont perdus"),
            },
            {
              nature: "avertissement",
              libelle: t("Les documents et les fichiers ne sont pas touchés"),
              precision: t("le fichier reçu part avec la tâche : il ne sera plus consultable ni rejouable"),
            },
          ]}
          onAnnuler={() => setRetrait(null)}
          onConfirmer={retrait.groupe ? supprimerSelection : retirer}
        />
      )}

      {rejeu && (
        <ChoisirEtape
          etapes={etapes}
          possibles={rejeu.possibles}
          titre={t(rejeu.titre)}
          sousTitre={rejeu.sousTitre}
          onAnnuler={() => setRejeu(null)}
          onValider={lancerRejeu}
        />
      )}
    </div>
  );
}

function Ligne({ libelle, valeur, mono }) {
  if (!valeur) return null;
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
      <span style={{ width: 110, color: "var(--ink-faint)", flexShrink: 0 }}>{libelle}</span>
      <span className={mono ? "tabular" : undefined} style={{ wordBreak: "break-all" }}>{valeur}</span>
    </div>
  );
}

/**
 * L'état d'une tâche sur sa ligne. Les intitulés sont ceux des filtres — un même
 * état ne doit pas s'appeler « Bloqué » ici et « Champ manquant » là —, et
 * l'infobulle porte la même explication.
 */
function EtatJob({ statut }) {
  const couleurs = {
    en_attente: { bg: "var(--line)", fg: "var(--ink-soft)" },
    en_cours: { bg: "var(--amber-soft)", fg: "var(--amber)" },
    termine: { bg: "var(--accent-soft)", fg: "var(--accent)" },
    a_classer: { bg: "var(--amber-soft)", fg: "var(--amber)" },
    bloque: { bg: "var(--amber-soft)", fg: "var(--amber)" },
    erreur: { bg: "var(--brick-soft)", fg: "var(--brick)" },
    ignore: { bg: "var(--line)", fg: "var(--ink-faint)" },
  }[statut] || { bg: "var(--line)", fg: "var(--ink-soft)" };
  const etat = ETATS().find((e) => e.id === statut);
  const styles = { ...couleurs, label: etat?.label || statut };

  return (
    <span
      title={etat?.aide}
      style={{
        fontSize: 11, fontWeight: 600, background: styles.bg, color: styles.fg,
        borderRadius: 3, padding: "2px 8px", width: 118, textAlign: "center", flexShrink: 0,
      }}
    >
      {styles.label}
    </span>
  );
}


/**
 * Menu latéral du serveur de travaux : les **types de document**, et eux seuls
 * (§19.16).
 *
 * Les états sont restés à l'horizontale : ils sont sept, connus d'avance, et
 * c'est ce qu'on regarde en arrivant. Les types, eux, sont autant que le foyer
 * en a déclaré — une liste qui s'allonge tient mieux dans une colonne que dans
 * une ligne qui finirait par déborder.
 *
 * Les compteurs viennent du serveur : les calculer ici obligerait à charger
 * toutes les tâches pour n'en afficher qu'une page, c'est-à-dire à charger
 * d'autant plus qu'il y en a — au moment précis où il y en a trop.
 */
function MenuTravaux({ types, typeId, onType }) {
  // Rien à afficher tant qu'aucune tâche n'a produit de document : un menu vide
  // prendrait de la place pour dire qu'il n'a rien à dire.
  if (types.length === 0) return null;

  const total = types.reduce((somme, type) => somme + type.nombre, 0);

  return (
    <nav style={{ width: 200, flexShrink: 0 }}>
      <Titre>{t("Type de document")}</Titre>
      {/* « Tous les types » en tête : sans lui, revenir à la vue d'ensemble
          demandait de retrouver le type sélectionné pour le décocher (§19.17). */}
      <Entree
        actif={!typeId}
        onClick={() => onType(null)}
        libelle={t("Tous les types")}
        nombre={total}
      />
      {types.map((type) => (
        <Entree
          key={type.categorie_id}
          actif={typeId === type.categorie_id}
          onClick={() => onType(typeId === type.categorie_id ? null : type.categorie_id)}
          libelle={t(type.nom)}
          nombre={type.nombre}
        />
      ))}
      <div style={{ fontSize: 10.5, color: "var(--ink-faint)", padding: "8px",
                    lineHeight: 1.45 }}>
        {t("Le choix se combine avec l'état retenu au-dessus. Une tâche n'apparaît ici qu'une fois son document créé : avant, elle n'a pas encore de type.")}
      </div>
    </nav>
  );
}

function Titre({ children }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
      color: "var(--ink-faint)", padding: "14px 8px 5px",
    }}>
      {children}
    </div>
  );
}

function Entree({ actif, onClick, libelle, nombre, couleur }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left",
        border: "none", borderLeft: `3px solid ${actif ? "var(--accent)" : "transparent"}`,
        background: actif ? "var(--accent-soft)" : "transparent",
        color: actif ? "var(--ink)" : "var(--ink-soft)", fontWeight: actif ? 600 : 400,
        padding: "6px 8px", fontSize: 12.5, borderRadius: 2,
      }}
    >
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis",
                     whiteSpace: "nowrap" }}>
        {libelle}
      </span>
      <span className="tabular"
            style={{ fontSize: 11.5, color: nombre ? (couleur || "var(--ink-soft)")
                                                   : "var(--ink-faint)" }}>
        {nombre ?? 0}
      </span>
    </button>
  );
}

