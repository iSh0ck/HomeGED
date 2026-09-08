import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Building2, ChevronDown, ChevronRight, Code2, Cog, Database, Eraser,
  FileText, KeyRound, LayoutDashboard, HardDrive, RefreshCw, ShieldAlert, Trash2, UserCog,
} from "lucide-react";
import Modal from "../../components/Modal.jsx";
import Pagination from "../../components/Pagination.jsx";
import ChampDate from "../../components/champs/ChampDate.jsx";
import Liste from "../../components/champs/Liste.jsx";
import { adminApi, api } from "../../api";
import {
  decrire, detailler, familleDe, heureDe, jourDe, libelleAction, libelleJour, libelleObjet,
} from "../../lib/journal";
import { t } from "../../lib/langue";

const PAR_PAGE_DEFAUT = 50;

/**
 * Journal d'audit (§14), en consultation seule.
 *
 * Aucune action d'édition ni de suppression n'est proposée : un journal qu'on
 * peut retoucher depuis l'interface ne prouve plus rien. L'API ne l'autorise
 * d'ailleurs pas non plus.
 *
 * L'écran raconte, il ne code pas. Chaque ligne est une phrase française datée
 * et signée ; les détails s'ouvrent en tableau de champs traduits, avec les
 * valeurs d'avant et d'après quand il s'agit d'une modification. Rien n'est
 * perdu pour autant : le code d'action exact et le JSON d'origine restent d'un
 * clic, sous « Données brutes » — c'est ce qui distingue une lecture d'une
 * réécriture.
 */
export default function JournalAdmin({ onOuvrirDocument }) {
  const [page, setPage] = useState({ total: 0, evenements: [] });
  const [choix, setChoix] = useState({ actions: [], objets: [] });
  const [filtres, setFiltres] = useState({ action: "", objet_type: "", utilisateur: "", depuis: "", jusqu_a: "" });
  const [decalage, setDecalage] = useState(0);
  const [parPage, setParPage] = useState(PAR_PAGE_DEFAUT);
  // Plusieurs lignes peuvent rester ouvertes en même temps : on compare souvent
  // deux événements, et se les faire refermer l'un après l'autre oblige à
  // mémoriser ce qu'on vient de lire.
  const [deplies, setDeplies] = useState(() => new Set());

  function basculerDetail(identifiant) {
    setDeplies((prec) => {
      const suivant = new Set(prec);
      if (suivant.has(identifiant)) suivant.delete(identifiant);
      else suivant.add(identifiant);
      return suivant;
    });
  }
  const [brut, setBrut] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [purge, setPurge] = useState(false);
  const [references, setReferences] = useState({ categories: new Map(), emetteurs: new Map() });
  // Les noms des documents que la page mentionne : le serveur les résout, parce
  // que lui seul peut le faire en une requête (§22.64).
  const nommes = { ...references, documents: page?.documents || {} };

  useEffect(() => { adminApi.auditActions().then(setChoix).catch(() => {}); }, []);

  // Le journal ne retient que des identifiants ; les noms se lisent ailleurs.
  // Sans eux, « Catégorie : nº2 » n'apprend rien à qui n'a pas la numérotation
  // en tête. Un échec ici n'empêche rien : on retombe sur le numéro seul.
  useEffect(() => {
    const enCarte = (liste) => new Map((liste || []).map((x) => [x.id, x.nom]));
    api.categories().catch(() => []).then((categories) => {
      setReferences({ categories: enCarte(categories), emetteurs: new Map() });
    });
  }, []);

  function charger() {
    setChargement(true);
    adminApi
      .audit({ ...filtres, limite: parPage, decalage })
      .then(setPage)
      .catch((e) => setErreur(e.message))
      .finally(() => setChargement(false));
  }
  useEffect(charger, [filtres, decalage, parPage]);

  function majFiltre(cle, valeur) {
    setDecalage(0); // un nouveau filtre repart de la première page
    setFiltres((prev) => ({ ...prev, [cle]: valeur }));
  }

  const filtresActifs = Object.values(filtres).some(Boolean);

  /** Actions regroupées par famille, pour que la liste déroulante se lise. */
  const actionsParFamille = useMemo(() => {
    const groupes = new Map();
    for (const code of choix.actions) {
      const famille = familleDe(code);
      if (!groupes.has(famille)) groupes.set(famille, []);
      groupes.get(famille).push(code);
    }
    for (const codes of groupes.values()) {
      codes.sort((a, b) => libelleAction(a).localeCompare(libelleAction(b)));
    }
    return [...groupes.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [choix.actions]);

  /** Événements découpés en journées : on lit un journal jour par jour. */
  const journees = useMemo(() => {
    const groupes = [];
    for (const evenement of page.evenements) {
      const cle = jourDe(evenement.date_evenement);
      if (!groupes.length || groupes[groupes.length - 1].cle !== cle) {
        groupes.push({ cle, evenements: [] });
      }
      groupes[groupes.length - 1].evenements.push(evenement);
    }
    return groupes;
  }, [page.evenements]);

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        {t("Ce qui s'est passé sur l'installation, raconté dans l'ordre : documents supprimés ou modifiés, comptes et droits, traitements relancés, corbeille vidée, connexions bloquées après trop d'essais. Cliquez une ligne pour voir le détail exact de l'événement. L'adresse de l'auteur est conservée telle quelle, pour que la trace reste lisible même après suppression de son compte ; ce journal est en consultation seule.")}
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end", marginBottom: 16 }}>
        <Filtre libelle={t("Type d'événement")}>
          <Liste
            compact
            style={{ minWidth: 230 }}
            valeur={filtres.action}
            ariaLabel={t("Filtrer par type d'événement")}
            placeholder="Tous"
            options={[
              { valeur: "", libelle: "Tous" },
              ...actionsParFamille.flatMap(([famille, codes]) =>
                codes.map((code) => ({ valeur: code, libelle: libelleAction(code), groupe: famille }))),
            ]}
            onChange={(v) => majFiltre("action", v)}
          />
        </Filtre>
        <Filtre libelle={t("Portant sur")}>
          <Liste
            compact
            style={{ minWidth: 150 }}
            valeur={filtres.objet_type}
            ariaLabel={t("Filtrer par nature d'objet")}
            placeholder="Tout"
            options={[{ valeur: "", libelle: "Tout" },
                      ...choix.objets.map((o) => ({ valeur: o, libelle: libelleObjet(o) }))]}
            onChange={(v) => majFiltre("objet_type", v)}
          />
        </Filtre>
        <Filtre libelle="Auteur">
          <input
            value={filtres.utilisateur}
            onChange={(e) => majFiltre("utilisateur", e.target.value)}
            placeholder="adresse e-mail"
            style={petitChamp}
          />
        </Filtre>
        <Filtre libelle="Du">
          <ChampDate compact style={{ width: 128 }} valeur={filtres.depuis}
                     max={filtres.jusqu_a || undefined}
                     ariaLabel={t("Début de la période")}
                     onChange={(v) => majFiltre("depuis", v)} />
        </Filtre>
        <Filtre libelle="Au">
          <ChampDate compact style={{ width: 128 }} valeur={filtres.jusqu_a}
                     min={filtres.depuis || undefined}
                     ariaLabel={t("Fin de la période")}
                     onChange={(v) => majFiltre("jusqu_a", v)} />
        </Filtre>
        {filtresActifs && (
          <button
            onClick={() => { setFiltres({ action: "", objet_type: "", utilisateur: "", depuis: "", jusqu_a: "" }); setDecalage(0); }}
            style={boutonDiscret}
          >
            Réinitialiser
          </button>
        )}
        <div style={{ flex: 1 }} />
        <button onClick={() => setPurge(true)} style={boutonDiscret}>
          <Eraser size={12} />
          Purger l'ancien
        </button>
        <button onClick={charger} style={boutonDiscret}>
          <RefreshCw size={12} />
          Rafraîchir
        </button>
      </div>

      <div style={{ fontSize: 12, color: "var(--ink-faint)", marginBottom: 8 }} className="tabular">
        {page.total} événement{page.total > 1 ? "s" : ""}
        {page.total > parPage && ` · ${decalage + 1}–${Math.min(decalage + parPage, page.total)}`}
      </div>

      {chargement ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>
      ) : page.evenements.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Aucun événement pour ces critères.")}</div>
      ) : (
        journees.map((journee) => (
          <section key={journee.cle} style={{ marginBottom: 18 }}>
            <h3 style={{
              fontSize: 12, fontWeight: 600, color: "var(--ink-soft)",
              textTransform: "capitalize", marginBottom: 6,
            }}>
              {libelleJour(journee.cle)}
              <span style={{ color: "var(--ink-faint)", fontWeight: 400, textTransform: "none" }}>
                {" "}· {journee.evenements.length} événement{journee.evenements.length > 1 ? "s" : ""}
              </span>
            </h3>

            <div style={{
              border: "1px solid var(--line)", borderRadius: "var(--radius)",
              overflow: "hidden", background: "var(--bg-panel)",
            }}>
              {journee.evenements.map((e, i) => (
                <Evenement
                  key={e.id}
                  evenement={e}
                  premier={i === 0}
                  ouvert={deplies.has(e.id)}
                  brutOuvert={brut === e.id}
                  references={nommes}
                  onOuvrir={() => basculerDetail(e.id)}
                  onBrut={() => setBrut(brut === e.id ? null : e.id)}
                  onOuvrirDocument={onOuvrirDocument}
                />
              ))}
            </div>
          </section>
        ))
      )}

      {!chargement && page.evenements.length > 0 && (
        <Pagination
          total={page.total}
          parPage={parPage}
          decalage={decalage}
          onDecalage={setDecalage}
          // Changer le nombre par page renvoie au début : rester au même
          // décalage ferait atterrir ailleurs que là où on croit être.
          onParPage={(n) => { setParPage(n); setDecalage(0); }}
        />
      )}

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {purge && (
        <PurgerJournal
          onFermer={() => setPurge(false)}
          onPurge={() => { setPurge(false); setDecalage(0); charger(); }}
        />
      )}
    </div>
  );
}

/**
 * Purge des entrées anciennes.
 *
 * On ne supprime pas une ligne choisie — ce serait retirer du journal
 * précisément ce qui gêne — mais tout ce qui précède une date. Et on ne le fait
 * pas à l'aveugle : l'API dit d'abord combien d'entrées partiraient et sur
 * quelle période, et le bouton reste inactif tant que ce chiffre n'est pas là.
 */
function PurgerJournal({ onFermer, onPurge }) {
  const [avant, setAvant] = useState(ilYAUnAn());
  const [apercu, setApercu] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  // L'aperçu suit la date : changer la coupure sans revoir ce qu'elle emporte
  // rendrait la confirmation trompeuse.
  useEffect(() => {
    let annule = false;
    setApercu(null);
    setErreur(null);
    if (!avant) return undefined;
    adminApi
      .apercuPurgeAudit(avant)
      .then((d) => !annule && setApercu(d))
      .catch((e) => !annule && setErreur(e.message));
    return () => { annule = true; };
  }, [avant]);

  async function confirmer() {
    setEnvoi(true);
    setErreur(null);
    try {
      await adminApi.purgerAudit(avant);
      onPurge();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  const rien = apercu && apercu.nombre === 0;

  return (
    <Modal titre={t("Purger les entrées anciennes")} onClose={onFermer} width={470}>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.5, marginTop: 4 }}>
        Tout ce qui précède la date choisie sera supprimé définitivement, <strong>sauf
        l'histoire des documents</strong> : celle-ci se lit depuis chaque fiche et répond
        des années plus tard à « d'où sort cette valeur ? ». Les entrées ne se suppriment
        pas une par une : un journal dont on retire une ligne ne prouve plus rien. La purge
        elle-même sera inscrite au journal, avec la date retenue et le nombre d'entrées
        perdues.
      </p>

      <label style={{ display: "block", fontSize: 12, color: "var(--ink-soft)", margin: "16px 0 4px" }}>
        {t("Supprimer tout ce qui est antérieur au")}
      </label>
      <ChampDate
        valeur={avant}
        max={new Date().toISOString().slice(0, 10)}
        ariaLabel={t("Date de coupure de la purge")}
        onChange={setAvant}
        style={{ width: 160 }}
      />

      <div style={{ marginTop: 16, minHeight: 44 }}>
        {!apercu && !erreur && (
          <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{t("Calcul de ce qui partirait…")}</div>
        )}
        {apercu && (
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <AlertTriangle size={16} color={rien ? "var(--ink-faint)" : "var(--brick)"}
                           style={{ flexShrink: 0, marginTop: 2 }} />
            <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>
              {rien ? (
                <span style={{ color: "var(--ink-soft)" }}>
                  {t("Aucune entrée n'est antérieure à cette date : il n'y a rien à supprimer.")}
                </span>
              ) : (
                <>
                  <strong>{apercu.nombre} entrée{apercu.nombre > 1 ? "s" : ""}</strong> seront
                  détruites définitivement, de {dateCourte(apercu.plus_ancien)} à{" "}
                  {dateCourte(apercu.plus_recent)}.{" "}
                  <span style={{ color: "var(--ink-faint)" }}>
                    {apercu.conserves} entrée{apercu.conserves > 1 ? "s" : ""} conservée
                    {apercu.conserves > 1 ? "s" : ""}.
                  </span>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
        <button onClick={onFermer} style={boutonDiscret}>Annuler</button>
        <button
          onClick={confirmer}
          disabled={envoi || !apercu || rien}
          style={{
            border: "none", background: "var(--brick)", color: "#fff",
            borderRadius: "var(--radius)", padding: "6px 14px", fontSize: 12.5,
            fontWeight: 600, opacity: envoi || !apercu || rien ? 0.55 : 1,
          }}
        >
          {envoi ? "Suppression…" : t("Supprimer définitivement")}
        </button>
      </div>
    </Modal>
  );
}

/** Date par défaut de la coupure : un an en arrière, un pas raisonnable. */
function ilYAUnAn() {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 1);
  return date.toISOString().slice(0, 10);
}

function dateCourte(iso) {
  if (!iso) return "?";
  const [a, m, j] = iso.slice(0, 10).split("-");
  return `${j}/${m}/${a}`;
}

/** Icône par famille : on reconnaît de loin le genre d'événement. */
const ICONES = {
  document: FileText,
  utilisateur: UserCog,
  role: KeyRound,
  auth: ShieldAlert,
  job: Cog,
  jobs: Cog,
  corbeille: Trash2,
  stockage: HardDrive,
  base: Database,
  tableau: LayoutDashboard,
  emetteur: Building2,
};

const COULEURS = {
  danger: "var(--brick)",
  attention: "var(--amber)",
  securite: "var(--brick)",
  neutre: "var(--ink-faint)",
};

/**
 * Les documents qu'un événement cite (§22.64).
 *
 * Le journal ne garde que des numéros ; la page apporte les noms, et l'on peut
 * aller voir la fiche — c'est presque toujours ce qu'on veut faire en lisant
 * « documents attachés ». Sans moyen d'y aller, le nom seul reste affiché.
 */
function DocumentsCites({ documents, onOuvrir }) {
  if (!documents?.length) return t("aucun");
  return (
    <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 6 }}>
      {documents.map((doc, rang) => (
        <span key={doc.id}>
          {rang > 0 && <span style={{ color: "var(--ink-faint)" }}>· </span>}
          {onOuvrir ? (
            <button
              onClick={() => onOuvrir(doc.id)}
              title={t("Ouvrir ce document")}
              style={{
                border: "none", background: "transparent", padding: 0,
                color: "var(--accent)", fontSize: "inherit", cursor: "pointer",
                textDecoration: "underline", textUnderlineOffset: 2,
              }}
            >
              {doc.nom}
            </button>
          ) : doc.nom}
        </span>
      ))}
    </span>
  );
}

function Evenement({ evenement, premier, ouvert, brutOuvert, references, onOuvrir, onBrut,
                     onOuvrirDocument }) {
  const { phrase, ton } = decrire(evenement, references);
  const Icone = ICONES[(evenement.action || "").split(".")[0]] || FileText;
  const couleur = COULEURS[ton] || COULEURS.neutre;
  const lignes = ouvert ? detailler(evenement.details, references) : [];

  return (
    <div style={{ borderTop: premier ? "none" : "1px solid var(--line)" }}>
      <button
        onClick={onOuvrir}
        style={{
          display: "flex", alignItems: "center", gap: 10, width: "100%",
          padding: "9px 12px", fontSize: 12.5, textAlign: "left",
          border: "none", background: "transparent", color: "var(--ink)",
          cursor: "pointer",
        }}
      >
        <span style={{ color: "var(--ink-faint)", display: "flex" }}>
          {ouvert ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </span>
        <span className="tabular" style={{ color: "var(--ink-faint)", flexShrink: 0, width: 42 }}>
          {heureDe(evenement.date_evenement)}
        </span>
        <Icone size={14} color={couleur} style={{ flexShrink: 0 }} />
        <span style={{ flex: 1, color: ton === "neutre" ? "var(--ink)" : couleur }}>
          {phrase}
        </span>
        <span style={{
          color: "var(--ink-faint)", fontSize: 11.5, maxWidth: 220,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {evenement.utilisateur ? `par ${evenement.utilisateur}` : t("par l'application")}
        </span>
      </button>

      {ouvert && (
        <div style={{ padding: "0 12px 12px 47px" }}>
          {lignes.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
              {t("Aucun détail n'a été enregistré pour cet événement.")}
            </div>
          ) : (
            <table style={{ borderCollapse: "collapse", fontSize: 12, width: "100%", maxWidth: 640 }}>
              <tbody>
                {lignes.map((ligne) => (
                  <tr key={ligne.cle} style={{ verticalAlign: "top" }}>
                    <td style={{ color: "var(--ink-faint)", padding: "3px 14px 3px 0", whiteSpace: "nowrap" }}>
                      {t(ligne.libelle)}
                    </td>
                    <td style={{ padding: "3px 0", wordBreak: "break-word" }}>
                      {ligne.type === "changement" ? (
                        <Changement ligne={ligne} />
                      ) : ligne.type === "documents" ? (
                        <DocumentsCites documents={ligne.documents}
                                        onOuvrir={onOuvrirDocument} />
                      ) : (
                        ligne.valeur
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <button onClick={onBrut} style={{ ...boutonDiscret, marginTop: 10, fontSize: 11, padding: "3px 9px" }}>
            <Code2 size={11} />
            {brutOuvert ? t("Masquer les données brutes") : t("Données brutes")}
          </button>

          {brutOuvert && (
            <pre style={{
              marginTop: 8, padding: 8, background: "var(--bg-panel-alt)",
              border: "1px solid var(--line)", borderRadius: "var(--radius)",
              fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "pre-wrap",
              overflowX: "auto", maxHeight: 260,
            }}>
{JSON.stringify({
  id: evenement.id,
  date_evenement: evenement.date_evenement,
  action: evenement.action,
  objet_type: evenement.objet_type,
  objet_id: evenement.objet_id,
  utilisateur: evenement.utilisateur,
  details: evenement.details,
}, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Passage d'une valeur à l'autre. Les champs inchangés restent affichés — les
 * masquer donnerait à croire qu'ils n'existaient pas — mais en retrait, pour que
 * l'œil aille droit à ce qui a bougé.
 */
function Changement({ ligne }) {
  if (!ligne.change) {
    return <span style={{ color: "var(--ink-faint)" }}>{ligne.apres} <span style={{ fontSize: 11 }}>(inchangé)</span></span>;
  }
  return (
    <span>
      <span style={{ color: "var(--ink-faint)", textDecoration: "line-through" }}>{ligne.avant}</span>
      <span style={{ color: "var(--ink-faint)" }}> → </span>
      <strong style={{ color: "var(--ink)", fontWeight: 600 }}>{ligne.apres}</strong>
    </span>
  );
}

function Filtre({ libelle, children }) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 11, color: "var(--ink-soft)", marginBottom: 3, fontWeight: 500 }}>
        {libelle}
      </label>
      {children}
    </div>
  );
}

const petitChamp = {
  padding: "5px 8px",
  fontSize: 12,
  border: "1px solid var(--line-strong)",
  borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)",
  color: "var(--ink)",
  fontFamily: "inherit",
  minWidth: 140,
};

const boutonDiscret = {
  display: "flex",
  alignItems: "center",
  gap: 5,
  border: "1px solid var(--line-strong)",
  background: "transparent",
  color: "var(--ink-soft)",
  borderRadius: "var(--radius)",
  padding: "5px 11px",
  fontSize: 12,
};
