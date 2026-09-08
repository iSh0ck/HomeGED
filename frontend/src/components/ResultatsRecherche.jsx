import React from "react";
import { FileText, Search } from "lucide-react";
import { libelleDocument, sousTitreDocument } from "../lib/document";
import { t } from "../lib/langue";

/**
 * Les résultats de la recherche globale (§21.2).
 *
 * Un tableau n'aurait pas convenu : ses colonnes sont celles d'un type de
 * document, et une recherche traverse les types. Surtout, il ne dirait pas
 * **pourquoi** un document sort — or c'est la première question qu'on se pose
 * en voyant apparaître une pièce sans rapport apparent avec le mot tapé. Chaque
 * résultat porte donc ses raisons : « Émetteur : Orange », « Concerne : Renault
 * Clio », « Texte du document ».
 *
 * Les résultats sont groupés par classement, parce qu'on reconnaît d'abord la
 * sorte de papier qu'on cherchait.
 */
export default function ResultatsRecherche({ resultats, terme, chargement,
                                             selectedId, onSelect, perimetre }) {
  if (chargement) {
    return <Message>{t("Recherche…")}</Message>;
  }
  if (!resultats) {
    return (
      <Message>
        {t("Tapez au moins trois caractères. La recherche traverse l'émetteur, les champs extraits, le nom du fichier, le classement, le texte des documents et les choses qu'ils concernent.")}
      </Message>
    );
  }
  if (resultats.length === 0) {
    return (
      <Message>
        {perimetre !== "tout"
          ? t("Rien ne correspond à « {terme} » dans ce périmètre — essayez « Toute la GED ».", { terme })
          : t("Rien ne correspond à « {terme} ».", { terme })}
      </Message>
    );
  }

  // Groupés par classement : on reconnaît d'abord la sorte de papier cherchée.
  const groupes = [];
  for (const resultat of resultats) {
    const nom = resultat.document.categorie || t("Sans classement");
    const groupe = groupes.find((g) => g.nom === nom);
    if (groupe) groupe.lignes.push(resultat);
    else groupes.push({ nom, lignes: [resultat] });
  }

  return (
    <div style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "14px 20px" }}
         className="scrollbar-thin">
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 14,
                    fontSize: 12.5, color: "var(--ink-soft)" }}>
        <Search size={14} color="var(--ink-faint)" />
        {resultats.length} résultat{resultats.length > 1 ? "s" : ""} pour « {terme} »
      </div>

      {groupes.map((groupe) => (
        <div key={groupe.nom} style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-faint)",
                        marginBottom: 6 }}>
            {groupe.nom} · {groupe.lignes.length}
          </div>
          <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                        overflow: "hidden" }}>
            {groupe.lignes.map((resultat, index) => {
              const doc = resultat.document;
              const actif = doc.id === selectedId;
              return (
                <button
                  key={doc.id}
                  onClick={() => onSelect?.(doc.id)}
                  style={{
                    display: "flex", alignItems: "flex-start", gap: 10, width: "100%",
                    textAlign: "left", padding: "9px 12px", border: "none",
                    borderBottom: index < groupe.lignes.length - 1
                      ? "1px solid var(--line)" : "none",
                    background: actif ? "var(--accent-soft)" : "transparent",
                    color: "var(--ink)", cursor: "pointer",
                  }}
                >
                  <FileText size={14} color="var(--ink-faint)"
                            style={{ marginTop: 2, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, overflow: "hidden",
                                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {libelleDocument(doc)}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--ink-faint)",
                                  overflow: "hidden", textOverflow: "ellipsis",
                                  whiteSpace: "nowrap" }}>
                      {sousTitreDocument(doc)}
                    </div>
                    {/* Pourquoi ce document sort : sans cela, une pièce sans
                        rapport apparent ressemble à une erreur du moteur. */}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                      {resultat.raisons.map((raison) => (
                        <span
                          key={raison.source}
                          title={raison.extrait || undefined}
                          style={{
                            fontSize: 10.5, color: "var(--ink-soft)",
                            border: "1px solid var(--line)", borderRadius: 9,
                            padding: "1px 7px", background: "var(--bg-panel-alt)",
                          }}
                        >
                          {t(raison.libelle)}
                          {raison.extrait && (
                            <span style={{ color: "var(--ink-faint)" }}>
                              {" · "}{raison.extrait.length > 40
                                ? `${raison.extrait.slice(0, 40)}…` : raison.extrait}
                            </span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function Message({ children }) {
  return (
    <div style={{ flex: 1, padding: "24px 22px", fontSize: 12.5, color: "var(--ink-faint)",
                  lineHeight: 1.55, maxWidth: 620 }}>
      {children}
    </div>
  );
}
