import React, { useCallback, useEffect, useState } from "react";
import { ArrowLeft, AlertTriangle, CheckCircle2, Trash2 } from "lucide-react";
import { api } from "../api";
import InspecteurDocument from "../components/InspecteurDocument.jsx";
import Pagination from "../components/Pagination.jsx";
import ChampDate from "../components/champs/ChampDate.jsx";
import Liste from "../components/champs/Liste.jsx";
import { aplatirArborescence } from "../lib/arborescence";
import { referenceTache } from "../lib/travaux";
import { t } from "../lib/langue";

/**
 * Centre d'analyse (§16, §17.7) : les documents lus mais qui ne respectent pas les
 * champs exigés par leur catégorie.
 *
 * Le principe est de corriger **sur place** : chaque champ manquant est proposé
 * à la saisie, avec le document consultable juste à côté — sans quoi il faudrait
 * ouvrir le PDF ailleurs pour y lire le montant à recopier. Dès que le dernier
 * champ est renseigné, le document redevient conforme et son travail reprend
 * son cours, côté serveur.
 */
// Dix secondes : l'ordre de grandeur d'une océrisation. Plus court ferait
// travailler le serveur pour rien, plus long donnerait l'impression que l'écran
// est figé — c'est justement ce qu'on corrige.
const INTERVALLE_RELEVE = 10000;

export default function AnalysePage({ categories, onRetour, onCorrige }) {
  const [documents, setDocuments] = useState([]);
  // Travaux arrêtés faute de savoir de quel type il s'agit (§19.4). Ils sont
  // d'une autre nature que les documents incomplets : rien n'a encore été lu
  // d'eux, il n'y a donc pas de champ à corriger, seulement un type à désigner.
  const [aClasser, setAClasser] = useState([]);
  // Le Centre d'analyse se lit **par page** (§22.43) : un foyer chargé peut
  // avoir des centaines de documents à reprendre, et on les traite ligne à
  // ligne. `total` vient du serveur, pas de la longueur de la page.
  const [total, setTotal] = useState(0);
  const [parPage, setParPage] = useState(50);
  const [decalage, setDecalage] = useState(0);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(null);

  /**
   * `discret` : on relit sans remettre l'écran en « Chargement… ».
   *
   * C'est ce qui permet de rafraîchir tout seul sans que la liste ne clignote
   * sous les doigts de qui est en train de la lire (§22.32).
   */
  const charger = useCallback((discret = false) => {
    if (!discret) setChargement(true);
    // Les fichiers à classer demandent le droit « Centre d'analyse » (§22.38),
    // que les documents incomplets, eux, n'exigent pas : un compte sans ce droit
    // voit ses documents à corriger, et simplement pas cette section — plutôt
    // qu'un écran en erreur.
    Promise.all([api.analyse({ limite: parPage, decalage }),
                 api.aClasser().catch(() => [])])
      .then(([incomplets, attente]) => {
        setDocuments(incomplets.documents);
        setTotal(incomplets.total);
        setAClasser(attente);
      })
      .catch((e) => setErreur(e.message))
      .finally(() => setChargement(false));
  }, [parPage, decalage]);
  useEffect(() => charger(), [charger]);

  /**
   * Le Centre d'analyse se tient à jour tout seul (§22.32).
   *
   * C'est le seul écran qui attend quelque chose du **serveur de travaux** : un
   * dépôt met quelques secondes à devenir un document, et l'on restait devant
   * une liste vide sans savoir s'il fallait patienter ou recharger la page. Un
   * relevé toutes les dix secondes suffit — c'est l'ordre de grandeur d'une
   * océrisation, et deux requêtes courtes toutes les dix secondes ne se voient
   * nulle part.
   *
   * Il s'arrête quand l'onglet passe à l'arrière-plan : personne n'y regarde, et
   * une GED ouverte dans un onglet oublié n'a pas à réveiller le serveur.
   */
  useEffect(() => {
    const battement = setInterval(() => {
      if (!document.hidden) charger(true);
    }, INTERVALLE_RELEVE);
    const auRetour = () => { if (!document.hidden) charger(true); };
    document.addEventListener("visibilitychange", auRetour);
    return () => {
      clearInterval(battement);
      document.removeEventListener("visibilitychange", auRetour);
    };
  }, [charger]);

  // Ce qui reste à reprendre, tout compris — et non ce que cette page-ci montre.
  const restant = total + aClasser.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100dvh", background: "var(--bg-app)" }}>
      <div
        style={{
          display: "flex", alignItems: "center", gap: 16, padding: "16px 24px",
          borderBottom: "1px solid var(--line)", background: "var(--bg-panel)",
        }}
      >
        <button
          onClick={onRetour}
          style={{ display: "flex", alignItems: "center", gap: 6, border: "none", background: "transparent", color: "var(--ink-soft)", fontSize: 13 }}
        >
          <ArrowLeft size={15} />
          Retour au registre
        </button>
        <h1 style={{ fontSize: 17, marginLeft: 8 }}>{t("Centre d'analyse")}</h1>
        {restant > 0 && (
          <span
            style={{
              background: "var(--amber-soft)", color: "var(--amber)", fontWeight: 600,
              fontSize: 11, borderRadius: 10, padding: "2px 9px",
            }}
          >
            {restant} à reprendre
          </span>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 24 }} className="scrollbar-thin">
        {/* 860 px suffisaient pour un texte à lire et quelques champs à remplir.
            La vue scindée — la page d'un côté, sa matrice de l'autre — les partage
            en deux, et chaque moitié devient trop étroite pour l'usage même de
            l'écran. On rend donc les trois quarts de la largeur disponible, avec
            un plancher pour que la colonne de texte reste lisible sur un écran
            large, et l'ancienne largeur comme minimum. */}
        <div style={{ width: "min(100%, max(860px, 75vw))" }}>
          <p style={{ fontSize: 13, color: "var(--ink-soft)", marginTop: 0, marginBottom: 20 }}>
            Ces documents ont bien été lus, mais il leur manque un champ exigé par leur
            catégorie. Tant qu'ils sont incomplets, ils <strong>n'apparaissent pas dans le
            registre</strong> et ne comptent pas dans les tableaux de bord : les afficher
            classés laisserait croire que le classement est fait. Ils n'existent, pour
            l'instant, que sur cette page.
            Renseignez ce qui manque ci-dessous — le document rejoint sa catégorie dès
            qu'il est complet.
          </p>

          {erreur && (
            <div style={{ color: "var(--brick)", fontSize: 12, marginBottom: 14 }}>{erreur}</div>
          )}

          {/* Ce qui n'a pas encore de type passe en premier : rien n'en a été lu,
              c'est donc ce qui est le plus loin d'être rangé. */}
          {aClasser.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 14, marginBottom: 6 }}>
                À classer ({aClasser.length})
              </h2>
              <p style={{ fontSize: 12.5, color: "var(--ink-soft)", marginTop: 0, marginBottom: 12,
                          lineHeight: 1.5 }}>
                Ces fichiers ont été déposés à la racine, ou dans un dossier qu'aucun type
                de document ne réclame. Ils <strong>n'ont pas été océrisés</strong> : tant
                qu'on ignore de quoi il s'agit, le texte reconnu ne servirait à rien.
                Indiquez leur type — le fichier rejoint le dossier correspondant et le
                serveur reprend son travail exactement comme pour un dépôt ordinaire.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {aClasser.map((travail) => (
                  <CarteAClasser
                    key={travail.id}
                    travail={travail}
                    categories={categories}
                    onClasse={charger}
                  />
                ))}
              </div>
            </div>
          )}

          {chargement ? (
            <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>
          ) : documents.length === 0 ? (
            <div
              style={{
                display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
                padding: "60px 16px", color: "var(--ink-faint)",
              }}
            >
              {aClasser.length === 0 && <CheckCircle2 size={30} color="var(--accent)" />}
              <div style={{ fontSize: 14, color: "var(--ink)" }}>
                {aClasser.length ? t("Aucun document incomplet.") : t("Rien à reprendre.")}
              </div>
              <div style={{ fontSize: 12 }}>
                {t("Tous les documents classés respectent les champs attendus de leur catégorie.")}
              </div>
            </div>
          ) : (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {documents.map((doc) => (
                  <CarteAnalyse
                    key={doc.id}
                    doc={doc}
                    categories={categories}
                    onCorrige={() => {
                      charger();
                      onCorrige?.();
                    }}
                  />
                ))}
              </div>
              {/* La pagination n'apparaît que si elle sert : sur une poignée de
                  documents à reprendre, elle ferait du bruit pour rien. */}
              {total > parPage && (
                <div style={{ marginTop: 16 }}>
                  <Pagination
                    total={total}
                    parPage={parPage}
                    decalage={decalage}
                    onDecalage={setDecalage}
                    onParPage={(n) => { setParPage(n); setDecalage(0); }}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Un fichier déposé au mauvais endroit (§19.4).
 *
 * Une seule question, parce qu'une seule se pose : de quel type de document
 * s'agit-il ? Rien n'a encore été lu de ce fichier — pas de texte, pas de
 * métadonnée, donc aucun champ à corriger. Il reste la page telle qu'elle a été
 * déposée, et c'est en la regardant qu'on tranche.
 *
 * Le classement **déplace le fichier** dans le dossier du type, et le serveur
 * reprend le traitement depuis le début. Ce n'est pas un chemin parallèle : le
 * document suit exactement le parcours qu'il aurait suivi s'il avait été bien
 * déposé, ce qui garantit qu'un classement à la main vaut un dépôt correct.
 */
function CarteAClasser({ travail, categories, onClasse }) {
  const [choix, setChoix] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [ecart, setEcart] = useState(false);

  /**
   * Écarter un dépôt (§21.14) : ce fichier n'avait rien à faire là — un double
   * scan, une page de garde. On pouvait dire de quel type il était, jamais qu'il
   * n'en était aucun, et il restait là à appeler une action.
   */
  async function ecarter() {
    setEnvoi(true);
    setErreur(null);
    try {
      await api.ecarterTravail(travail.id);
      onClasse();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
      setEcart(false);
    }
  }

  // Seuls les types de document reçoivent des fichiers : un dossier de
  // classement n'a pas de dossier de dépôt, le proposer mènerait à un refus.
  const types = aplatirArborescence(categories).filter(
    (c) => (c.nature || "type") !== "dossier");

  async function classer() {
    if (!choix) {
      setErreur(t("Choisissez le type de document avant de classer."));
      return;
    }
    setEnvoi(true);
    setErreur(null);
    try {
      await api.classerTravail(travail.id, Number(choix));
      onClasse();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  return (
    <div style={{
      border: "1px solid var(--line)", borderLeft: "3px solid var(--amber)",
      borderRadius: "var(--radius)", background: "var(--bg-panel)", padding: 16,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <AlertTriangle size={16} color="var(--amber)" style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{travail.nom_fichier}</div>
          <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 2 }}>
            tâche {referenceTache(travail.id)}
            {travail.date_creation && ` · déposé le ${travail.date_creation.slice(0, 10)}`}
            {travail.taille_octets != null && ` · ${Math.round(travail.taille_octets / 1024)} Ko`}
          </div>
        </div>
      </div>

      {travail.fichier_disponible ? (
        <div style={{ marginTop: 12 }}>
          <InspecteurDocument
            chargerFichier={() => api.fichierAClasserBlobUrl(travail.id)}
            hauteur={420}
          />
        </div>
      ) : (
        <div style={{ fontSize: 12, color: "var(--brick)", marginTop: 10 }}>
          {t("Le fichier reçu n'est plus disponible : ce travail ne peut plus être classé.")}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "flex-end", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 220 }}>
          <label style={{ display: "block", fontSize: 11, color: "var(--ink-soft)",
                          marginBottom: 4, fontWeight: 500 }}>
            Type de document
          </label>
          <Liste
            recherchable
            valeur={choix}
            ariaLabel={`Type de document pour ${travail.nom_fichier}`}
            placeholder="— Choisir —"
            options={types.map((c) => ({
              valeur: c.id,
              libelle: `${"\u00a0".repeat(c.profondeur * 3)}${c.nom}`,
            }))}
            onChange={setChoix}
          />
        </div>
        <button
          onClick={classer}
          disabled={envoi || !travail.fichier_disponible}
          style={{
            background: "var(--accent)", color: "#fff", border: "none",
            borderRadius: "var(--radius)", padding: "7px 16px", fontSize: 13,
            fontWeight: 600, opacity: envoi ? 0.7 : 1,
          }}
        >
          {envoi ? "Classement…" : t("Classer et traiter")}
        </button>
        <button
          onClick={() => (ecart ? ecarter() : setEcart(true))}
          disabled={envoi}
          title={t("Ce fichier n'a rien à faire ici : il sera effacé du dépôt")}
          style={{
            border: `1px solid ${ecart ? "var(--brick)" : "var(--line-strong)"}`,
            background: ecart ? "var(--brick)" : "transparent",
            color: ecart ? "#fff" : "var(--ink-soft)",
            borderRadius: "var(--radius)", padding: "7px 13px", fontSize: 13,
          }}
        >
          <Trash2 size={13} style={{ verticalAlign: "-2px", marginRight: 5 }} />
          {ecart ? t("Confirmer l'écartement") : t("Écarter")}
        </button>
      </div>
      {ecart && (
        <div style={{ fontSize: 11.5, color: "var(--brick)", marginTop: 6, lineHeight: 1.45 }}>
          {t("Le fichier reçu sera effacé, et le travail restera visible dans le suivi avec la trace de qui l'a écarté. Il n'entre pas au registre, il n'y a donc pas de corbeille pour le rattraper.")}
        </div>
      )}

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}
    </div>
  );
}


function CarteAnalyse({ doc, categories, onCorrige }) {
  const [valeurs, setValeurs] = useState({});
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState(null);
  /** Construit la charge utile du PATCH à partir des seuls champs renseignés. */
  function construirePatch() {
    const patch = {};
    const metadonnees = {};
    for (const champ of doc.champs_manquants) {
      const valeur = valeurs[champ.champ];
      if (valeur === undefined || valeur === "") continue;
      if (champ.type === "metadonnee" || champ.type === "reference") metadonnees[champ.cle] = valeur;
      else if (champ.type === "categorie") patch.categorie_id = Number(valeur);
      else if (champ.type === "date") patch.date_document = valeur;
    }
    if (Object.keys(metadonnees).length) patch.metadonnees = metadonnees;
    return patch;
  }

  const [suppression, setSuppression] = useState(false);

  /**
   * Supprimer depuis le Centre d'analyse (§21.14).
   *
   * Un document incomplet n'est pas toujours à compléter : c'est parfois un
   * doublon, une page blanche, un scan raté. Il fallait jusqu'ici ouvrir le
   * registre, l'y retrouver, et le supprimer là-bas — alors que l'écran qui le
   * signale est précisément celui où l'on constate qu'il ne vaut rien.
   *
   * Il part à la corbeille comme partout ailleurs (§21.1) : rien n'est perdu.
   */
  async function supprimer() {
    setEnvoi(true);
    setErreur(null);
    try {
      await api.supprimerDocument(doc.id);
      onCorrige();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
      setSuppression(false);
    }
  }

  async function enregistrer() {
    const patch = construirePatch();
    if (!Object.keys(patch).length) {
      setErreur(t("Renseigne au moins un champ avant d'enregistrer."));
      return;
    }
    setEnvoi(true);
    setErreur(null);
    try {
      await api.patchDocument(doc.id, patch);
      onCorrige();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  return (
    <div
      style={{
        border: "1px solid var(--line)", borderLeft: "3px solid var(--amber)",
        borderRadius: "var(--radius)", background: "var(--bg-panel)", padding: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <AlertTriangle size={16} color="var(--amber)" style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{t(doc.libelle)}</div>
          <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 2 }}>
            Catégorie « {doc.categorie} » · importé le {doc.date_import?.slice(0, 10)}
            {doc.job_id && ` · tâche ${referenceTache(doc.job_id)}`}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <InspecteurDocument
          documentId={doc.id}
          chargerFichier={() => api.fichierBlobUrl(doc.id)}
        />
      </div>

      <div
        style={{
          marginTop: 14, display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 12,
        }}
      >
        {doc.champs_manquants.map((champ) => (
          <div key={champ.champ}>
            <label style={{ display: "block", fontSize: 11, color: "var(--ink-soft)", marginBottom: 4, fontWeight: 500 }}>
              {t(champ.libelle)}
            </label>
            <SaisieChamp
              champ={champ}
              valeur={valeurs[champ.champ] ?? ""}
              onChange={(v) => setValeurs({ ...valeurs, [champ.champ]: v })}
              categories={categories}
            />
          </div>
        ))}
      </div>

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 14 }}>
        <button
          onClick={() => (suppression ? supprimer() : setSuppression(true))}
          disabled={envoi}
          title={t("Mettre ce document à la corbeille")}
          style={{
            border: `1px solid ${suppression ? "var(--brick)" : "var(--line-strong)"}`,
            background: suppression ? "var(--brick)" : "transparent",
            color: suppression ? "#fff" : "var(--ink-soft)",
            borderRadius: "var(--radius)", padding: "7px 13px", fontSize: 13,
          }}
        >
          <Trash2 size={13} style={{ verticalAlign: "-2px", marginRight: 5 }} />
          {suppression ? t("Confirmer la mise à la corbeille") : "Supprimer"}
        </button>
        {suppression && (
          <span style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
            {t("Il part à la corbeille : rien n'est perdu.")}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={enregistrer}
          disabled={envoi}
          style={{
            background: "var(--accent)", color: "#fff", border: "none",
            borderRadius: "var(--radius)", padding: "7px 16px", fontSize: 13,
            fontWeight: 600, opacity: envoi ? 0.7 : 1,
          }}
        >
          {envoi ? "Enregistrement…" : t("Enregistrer et reprendre")}
        </button>
      </div>
    </div>
  );
}

/** Contrôle de saisie adapté à la nature du champ manquant. */
function SaisieChamp({ champ, valeur, onChange, categories }) {
  if (champ.type === "reference") {
    return <SaisieReference champ={champ} valeur={valeur} onChange={onChange} />;
  }
  if (champ.type === "categorie") {
    const options = aplatirArborescence(categories);
    return (
      <Liste
        valeur={valeur}
        ariaLabel={champ.libelle || champ.champ}
        options={options.map((o) => ({
          valeur: o.id,
          // l'indentation dit la profondeur dans l'arborescence, comme dans la
          // navigation : une sous-catégorie ne se lit pas comme une racine
          libelle: `${"\u00a0".repeat((o.profondeur || 0) * 3)}${o.nom}`,
        }))}
        onChange={onChange}
      />
    );
  }
  if (champ.type === "date") {
    return <ChampDate valeur={valeur} onChange={onChange} ariaLabel={t("Date du document")} />;
  }
  return (
    <input
      value={valeur}
      onChange={(e) => onChange(e.target.value)}
      placeholder={t("à recopier du document")}
      style={styleSaisie}
    />
  );
}

/**
 * Champ personnalisé adossé à une table de données (§17) : on choisit une ligne
 * existante plutôt que de recopier une valeur, ce qui garantit que la référence
 * pointe bien quelque chose.
 */
function SaisieReference({ champ, valeur, onChange }) {
  const [options, setOptions] = useState([]);
  const [erreur, setErreur] = useState(null);

  useEffect(() => {
    api
      .references(champ.source_table, null,
                  { categorieId: champ.categorie_id, champ: champ.champ })
      .then(setOptions)
      .catch((e) => setErreur(e.message));
  }, [champ.source_table, champ.categorie_id, champ.champ]);

  if (erreur) {
    return <div style={{ fontSize: 11, color: "var(--brick)" }}>Source indisponible — {erreur}</div>;
  }
  return (
    <Liste
      valeur={valeur}
      ariaLabel={t("Valeur")}
      options={options.map((o) => ({
        valeur: o.valeur,
        libelle: o.complement ? `${t(o.libelle)} — ${o.complement}` : o.libelle,
      }))}
      onChange={onChange}
    />
  );
}

const styleSaisie = {
  width: "100%",
  padding: "6px 8px",
  fontSize: 13,
  border: "1px solid var(--line-strong)",
  borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)",
  color: "var(--ink)",
  fontFamily: "inherit",
};
