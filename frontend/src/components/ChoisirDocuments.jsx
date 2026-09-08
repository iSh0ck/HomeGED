import React, { useEffect, useState } from "react";
import { Eye, Search, X } from "lucide-react";
import { api } from "../api";
import Modal from "./Modal.jsx";
import InspecteurDocument from "./InspecteurDocument.jsx";
import { t } from "../lib/langue";

/**
 * Un champ dont le contenu est **une liste de documents de la GED** (§22.11).
 *
 * Sous « Entretiens », on note ce qui a été fait sur le véhicule et l'on y
 * attache les factures correspondantes — déjà classées, avec leurs propres
 * colonnes et leurs propres droits. On ne les recopie pas : on les désigne.
 *
 * La recherche part au serveur : filtrer sur les cent premiers chargés mentirait
 * sur ce que la GED contient. Ce qui est déjà choisi reste affiché au-dessus,
 * dans l'ordre — c'est celui dans lequel on les relira.
 *
 * Deux économies, et la même raison — un foyer accumule des milliers de
 * documents (§22.26) : sans rien taper, la liste montre **le dernier mois**, ce
 * qu'on attache étant presque toujours récent ; et la recherche ne part qu'à
 * partir de **trois caractères**, « fa » ramenant la moitié de la GED pour rien.
 */
export default function ChoisirDocuments({ valeur = [], onChange, ariaLabel,
                                          categorieId, champ, sauf = null }) {
  const [terme, setTerme] = useState("");
  const [resultats, setResultats] = useState([]);
  const [chargement, setChargement] = useState(false);
  // Ce que la liste montre : un extrait récent, ou un résultat de recherche. Les
  // confondre ferait croire qu'un document cherché n'existe pas.
  const [extraitRecent, setExtraitRecent] = useState(true);
  const [minimum, setMinimum] = useState(3);
  const [ouvert, setOuvert] = useState(false);
  // Le document qu'on regarde avant de le choisir (§22.21) : un numéro de
  // facture ne dit pas toujours si c'est la bonne — la page, si.
  const [apercu, setApercu] = useState(null);

  // Ce que le champ **accepte** (§22.14) : le type déclaré, cherché dans les
  // champs déclarés. Un champ qui propose toute la GED ne guide personne — et
  // c'est le serveur qui borne, l'écran ne fait que montrer.
  //
  // La liste s'ouvre **avant même de taper** quand le champ est borné : sur un
  // type précis, les derniers documents sont souvent ceux qu'on cherche.
  useEffect(() => {
    if (!categorieId || !champ) { setResultats([]); return undefined; }
    const cherche = terme.trim();
    // Une ou deux lettres ne déclenchent rien : ni requête, ni attente. La liste
    // reste celle du dernier mois, et l'on dit ce qu'il manque pour chercher.
    const interroge = cherche.length === 0 || cherche.length >= minimum;
    if (!interroge) return undefined;
    let vivant = true;
    setChargement(true);
    const minuterie = setTimeout(() => {
      api.attachables(categorieId, champ, cherche, sauf)
        .then((reponse) => {
          if (!vivant) return;
          setResultats(reponse.documents || []);
          setExtraitRecent(reponse.recents !== false);
          if (reponse.minimum_recherche) setMinimum(reponse.minimum_recherche);
        })
        .catch(() => vivant && setResultats([]))
        .finally(() => vivant && setChargement(false));
    }, cherche ? 200 : 0);
    return () => { vivant = false; clearTimeout(minuterie); };
  }, [terme, categorieId, champ, sauf, minimum]);

  const choisis = valeur || [];
  const dejaLa = new Set(choisis.map((d) => d.id));

  return (
    <div>
      {choisis.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          {choisis.map((doc) => (
            <div key={doc.id} style={{ display: "flex", alignItems: "center", gap: 6,
                                       fontSize: 12, padding: "2px 0" }}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", overflow: "hidden",
                               textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {doc.libelle || doc.nom_fichier}
                  {doc.categorie && (
                    <span style={{ color: "var(--ink-faint)" }}> · {doc.categorie}</span>
                  )}
                </span>
                {(doc.details || []).length > 0 && (
                  <span style={{ display: "block", color: "var(--ink-soft)", fontSize: 11.5 }}>
                    {doc.details.map((d) => `${t(d.libelle)} : ${d.valeur}`).join(" · ")}
                  </span>
                )}
              </span>
              <button
                type="button"
                onClick={() => setApercu(doc)}
                title={`Voir ${doc.libelle || doc.nom_fichier}`}
                aria-label={`Voir ${doc.libelle || doc.nom_fichier}`}
                style={{ border: "none", background: "transparent",
                         color: "var(--ink-faint)", cursor: "pointer", padding: 2 }}
              >
                <Eye size={12} />
              </button>
              <button
                type="button"
                onClick={() => onChange(choisis.filter((d) => d.id !== doc.id))}
                aria-label={`Retirer ${doc.libelle || doc.nom_fichier}`}
                style={{ border: "none", background: "transparent",
                         color: "var(--ink-faint)", cursor: "pointer", padding: 2 }}
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 6,
                    border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
                    padding: "5px 8px", background: "var(--bg-panel-alt)" }}>
        <Search size={12} color="var(--ink-faint)" />
        <input
          value={terme}
          aria-label={ariaLabel || t("Chercher un document à attacher")}
          placeholder={t("Chercher parmi les documents acceptés…")}
          onFocus={() => setOuvert(true)}
          onChange={(e) => setTerme(e.target.value)}
          style={{ flex: 1, border: "none", background: "transparent", outline: "none",
                   fontSize: 12.5, fontFamily: "inherit", color: "var(--ink)" }}
        />
      </div>

      {apercu && (
        <Modal
          titre={apercu.libelle || apercu.nom_fichier}
          sousTitre={apercu.categorie}
          onClose={() => setApercu(null)}
          width={900}
        >
          <InspecteurDocument
            documentId={apercu.id}
            vueInitiale="apercu"
            hauteur={520}
            chargerFichier={() => api.fichierBlobUrl(apercu.id)}
          />
        </Modal>
      )}

      {(ouvert || terme.trim()) && (
        <div className="scrollbar-thin"
             style={{ maxHeight: 180, overflowY: "auto", marginTop: 4,
                      border: "1px solid var(--line)", borderRadius: "var(--radius)" }}>
          {/* Ce que la liste montre, dit avant elle : un extrait récent n'est pas
              un résultat de recherche, et le confondre fait croire qu'un document
              n'existe pas (§22.26). */}
          <div style={{ fontSize: 11, color: "var(--ink-faint)", padding: "5px 8px",
                        borderBottom: "1px solid var(--line)", lineHeight: 1.45 }}>
            {terme.trim().length > 0 && terme.trim().length < minimum
              ? `Encore ${minimum - terme.trim().length} caractère(s) pour chercher `
                + `dans toute la GED.`
              : extraitRecent
                ? t("Documents ajoutés depuis un mois. Tapez au moins ")
                  + `${minimum} caractères pour chercher au-delà.`
                : t("Résultats de la recherche.")}
          </div>
          {chargement && resultats.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "6px 8px" }}>
              Recherche…
            </div>
          )}
          {!chargement && resultats.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "6px 8px" }}>
              {extraitRecent
                ? t("Aucun document ajouté ce mois-ci — cherchez par son intitulé.")
                : t("Aucun document ne correspond.")}
            </div>
          )}
          {resultats.filter((d) => !dejaLa.has(d.id)).map((doc) => (
            <div key={doc.id} style={{ display: "flex", alignItems: "flex-start" }}>
            <button
              type="button"
              onClick={() => {
                onChange([...choisis, {
                  id: doc.id,
                  libelle: doc.libelle || doc.nom_fichier,
                  categorie: doc.categorie,
                  nom_fichier: doc.nom_fichier,
                  details: doc.details || [],
                }]);
                setTerme("");
                setOuvert(false);
              }}
              style={{ flex: 1, minWidth: 0, textAlign: "left", border: "none",
                       background: "transparent", color: "var(--ink)", fontSize: 12,
                       padding: "5px 8px", cursor: "pointer" }}
            >
              {doc.libelle || doc.nom_fichier}
              {doc.categorie && (
                <span style={{ color: "var(--ink-faint)" }}> · {doc.categorie}</span>
              )}
              {/* Ce que l'administration a coché dans « Chercher dans » : c'est
                  ce qui distingue deux factures du même mois, et donc ce qu'il
                  faut lire pour choisir (§22.19). */}
              {(doc.details || []).length > 0 && (
                <span style={{ display: "block", color: "var(--ink-soft)", fontSize: 11.5,
                               marginTop: 1 }}>
                  {doc.details.map((d) => `${t(d.libelle)} : ${d.valeur}`).join(" · ")}
                </span>
              )}
            </button>
            {/* Regarder avant de choisir (§22.21) : deux factures du même mois se
                distinguent parfois sur la page, et pas dans leurs valeurs. */}
            <button
              type="button"
              onClick={() => setApercu(doc)}
              title={`Voir ${doc.libelle || doc.nom_fichier}`}
              aria-label={`Voir ${doc.libelle || doc.nom_fichier}`}
              style={{ border: "none", background: "transparent", color: "var(--ink-faint)",
                       padding: "6px 8px", cursor: "pointer", flexShrink: 0 }}
            >
              <Eye size={13} />
            </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
