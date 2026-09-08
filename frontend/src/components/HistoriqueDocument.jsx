import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, History } from "lucide-react";
import { api } from "../api";
import Modal from "./Modal.jsx";
import Pagination from "./Pagination.jsx";
import { decrire, detailler, heureDe, jourDe, libelleJour } from "../lib/journal";
import { t } from "../lib/langue";

// Un document qui a beaucoup vécu ne doit pas produire une fenêtre sans fin :
// on en montre dix à la fois, du plus récent au dépôt. Dix plutôt que vingt-cinq
// parce qu'une fenêtre modale est courte : au-delà, on fait défiler pour rien.
const PAR_PAGE_DEFAUT = 10;

/**
 * Historique d'un document, ouvert depuis sa fiche.
 *
 * Le journal général est réservé à l'administration ; celui-ci montre ce qui est
 * arrivé à **ce** document, à toute personne qui a déjà le droit de le
 * consulter. Il n'apprend donc rien de plus sur le reste de l'archive — sinon
 * qui a modifié quoi, et quand, ce qui est précisément ce qu'on cherche quand on
 * se demande d'où sort une valeur.
 *
 * Même principe de lecture que le journal d'audit (§16.6) : **une ligne par
 * événement**, qui tient sur une ligne, et le détail au déroulé. Tout afficher
 * d'emblée rendait la liste illisible dès la troisième correction ; ne rien
 * montrer aurait obligé à ouvrir chaque entrée pour savoir laquelle regarder.
 * La ligne annonce donc les champs touchés, le déroulé donne leurs valeurs.
 *
 * La mise en forme réutilise le vocabulaire du journal (`lib/journal.js`) :
 * deux vocabulaires pour une même donnée finiraient par diverger.
 */
export default function HistoriqueDocument({ documentId, categories, onFermer }) {
  const [page, setPage] = useState(null);          // { total, evenements }
  const [erreur, setErreur] = useState(null);
  // Un ensemble, et non une seule ligne : ouvrir un détail ne doit pas refermer
  // celui d'à côté. On compare souvent deux modifications entre elles, et se les
  // faire reprendre l'une après l'autre oblige à mémoriser ce qu'on vient de lire.
  const [deplies, setDeplies] = useState(() => new Set());

  function basculer(identifiant) {
    setDeplies((prec) => {
      const suivant = new Set(prec);
      if (suivant.has(identifiant)) suivant.delete(identifiant);
      else suivant.add(identifiant);
      return suivant;
    });
  }
  const [decalage, setDecalage] = useState(0);
  const [parPage, setParPage] = useState(PAR_PAGE_DEFAUT);

  // Les entrées écrites avant §17.22 ne contiennent que des identifiants
  // (« categorie_id: 2 »). On les résout ici pour qu'elles restent lisibles —
  // les nouvelles, elles, portent directement « Factures ».
  const references = {
    categories: new Map((categories || []).map((c) => [c.id, c.nom])),
  };

  useEffect(() => {
    let annule = false;
    api
      .journalDocument(documentId, { limite: parPage, decalage })
      // Changer de page repart de lignes fermées : les identifiants d'une page
      // ne disent rien de la suivante.
      .then((p) => { if (!annule) { setPage(p); setDeplies(new Set()); } })
      .catch((e) => { if (!annule) setErreur(e.message); });
    return () => { annule = true; };
  }, [documentId, decalage, parPage]);

  const evenements = page?.evenements;

  return (
    <Modal titre={t("Historique du document")} onClose={onFermer} width={540}>
      {erreur && <div style={{ color: "var(--brick)", fontSize: 12.5 }}>{erreur}</div>}
      {!evenements && !erreur && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 12 }}>{t("Chargement…")}</div>
      )}

      {evenements?.length === 0 && (
        <div style={{ fontSize: 12.5, color: "var(--ink-soft)", marginTop: 12, lineHeight: 1.5 }}>
          {t("Rien à raconter : ce document n'a pas été modifié depuis son arrivée.")}
        </div>
      )}

      {page && page.total > 0 && (
        <div className="tabular" style={{
          fontSize: 11.5, color: "var(--ink-faint)", marginTop: 8,
        }}>
          {/* Le total seulement : la tranche affichée (« 1–10 sur 26 ») est déjà
              donnée par la pagination, en bas. La répéter ici ferait deux
              sources pour une même information. */}
          {page.total} événement{page.total > 1 ? "s" : ""}
        </div>
      )}

      {evenements?.length > 0 && (
        <div style={{ marginTop: 4 }}>
          {evenements.map((evenement, index) => {
            const jour = jourDe(evenement.date_evenement);
            const nouveauJour = jour !== jourDe(evenements[index - 1]?.date_evenement);
            return (
              <React.Fragment key={evenement.id}>
                {nouveauJour && (
                  <div style={{
                    fontSize: 11, fontWeight: 600, color: "var(--ink-faint)",
                    textTransform: "capitalize", margin: "14px 0 4px",
                  }}>
                    {libelleJour(jour)}
                  </div>
                )}
                <Evenement
                  evenement={evenement}
                  references={references}
                  premier={nouveauJour}
                  ouvert={deplies.has(evenement.id)}
                  onBasculer={() => basculer(evenement.id)}
                />
              </React.Fragment>
            );
          })}
        </div>
      )}

      {page && page.total > parPage && (
        <Pagination
          total={page.total}
          parPage={parPage}
          decalage={decalage}
          onDecalage={setDecalage}
          onParPage={(n) => { setParPage(n); setDecalage(0); }}
          options={[10, 25, 50, 100]}
        />
      )}
    </Modal>
  );
}

function Evenement({ evenement, references, premier, ouvert, onBasculer }) {
  // `objet_id` omis à dessein : on est déjà dans la fiche de ce document,
  // répéter son numéro à chaque ligne n'apprend rien.
  const { phrase } = decrire({ ...evenement, objet_type: "document", objet_id: null });
  const lignes = detailler(evenement.details, references);
  const changements = lignes.filter((l) => l.type === "changement" && l.change);
  const depliable = lignes.length > 0;

  return (
    <div style={{ borderTop: premier ? "none" : "1px solid var(--line)" }}>
      <button
        onClick={depliable ? onBasculer : undefined}
        aria-expanded={depliable ? ouvert : undefined}
        style={{
          display: "flex", alignItems: "flex-start", gap: 8, width: "100%",
          border: "none", background: "transparent", padding: "8px 2px",
          textAlign: "left", cursor: depliable ? "pointer" : "default",
        }}
      >
        <span style={{ color: "var(--ink-faint)", display: "flex", paddingTop: 1, width: 14 }}>
          {depliable && (ouvert ? <ChevronDown size={13} /> : <ChevronRight size={13} />)}
        </span>
        <span className="tabular" style={{
          fontSize: 11.5, color: "var(--ink-faint)", flexShrink: 0, width: 40, paddingTop: 1,
        }}>
          {heureDe(evenement.date_evenement)}
        </span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 12.5, color: "var(--ink)" }}>{phrase}</span>
          {/* Aperçu : ce qui a bougé, sans les valeurs. De quoi savoir si cette
              ligne est celle qu'on cherche, sans l'ouvrir. */}
          {changements.length > 0 && (
            <span style={{ display: "block", fontSize: 11.5, color: "var(--ink-soft)", marginTop: 2 }}>
              {changements.map((c) => c.libelle).join(", ")}
            </span>
          )}
          <span style={{ display: "block", fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}>
            {evenement.auteur || "l'application"}
          </span>
        </span>
      </button>

      {ouvert && (
        <div style={{ padding: "0 2px 12px 62px" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
            <tbody>
              {lignes.map((ligne) => (
                <tr key={ligne.cle} style={{ verticalAlign: "top" }}>
                  <td style={{
                    color: "var(--ink-faint)", padding: "3px 12px 3px 0", whiteSpace: "nowrap",
                  }}>
                    {t(ligne.libelle)}
                  </td>
                  {ligne.type === "changement" ? (
                    <>
                      <td style={{
                        padding: "3px 8px 3px 0", color: "var(--ink-faint)",
                        textDecoration: ligne.change ? "line-through" : "none",
                        wordBreak: "break-word", width: "40%",
                      }}>
                        {ligne.avant}
                      </td>
                      <td style={{ padding: "3px 0", wordBreak: "break-word" }}>
                        {ligne.change
                          ? <strong style={{ fontWeight: 600 }}>{ligne.apres}</strong>
                          : <span style={{ color: "var(--ink-faint)" }}>inchangé</span>}
                      </td>
                    </>
                  ) : (
                    <td colSpan={2} style={{ padding: "3px 0", wordBreak: "break-word" }}>
                      {ligne.valeur}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Icône d'ouverture, posée dans la fiche du document. */
export function BoutonHistorique({ onClick }) {
  return (
    <button
      onClick={onClick}
      aria-label={t("Historique des modifications")}
      title={t("Historique des modifications")}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        border: "1px solid var(--accent)", background: "transparent",
        color: "var(--accent)", borderRadius: "var(--radius)",
        padding: "7px 12px", fontSize: 13, fontWeight: 500, cursor: "pointer",
      }}
    >
      <History size={15} />
      Historique
    </button>
  );
}
