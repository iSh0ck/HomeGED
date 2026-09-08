import React, { useEffect, useState } from "react";
import { FileText, ScanText, Grid3x3, FlaskConical } from "lucide-react";
import { api } from "../api";
import GrilleOcr from "./GrilleOcr.jsx";
import { t } from "../lib/langue";

/**
 * Inspecteur de document (§18.54).
 *
 * Les trois vues d'un même document — la page telle qu'elle est, le texte que la
 * machine en a tiré, ce texte case par case — et l'essai d'extraction. Réunis
 * ici parce qu'ils servent en deux endroits, pour la même question posée
 * autrement :
 *
 *   * au **Centre d'analyse**, sur un document qu'il faut compléter ;
 *   * au **serveur de travaux**, sur un travail qui a échoué — c'est là qu'on
 *     cherche pourquoi, et jusqu'ici il fallait quitter l'administration pour le
 *     savoir. Un travail sans document produit n'a ni texte ni matrice à
 *     montrer : il lui reste son fichier d'origine, conservé depuis le §18.53,
 *     et c'est déjà l'essentiel — on voit ce qui est arrivé.
 *
 * `chargerFichier` rend une URL d'objet ; l'appelant décide d'où vient le
 * fichier (l'archive du document, ou l'original conservé du travail).
 */
export default function InspecteurDocument({
  documentId, chargerFichier, hauteur = 460, vueInitiale = null,
}) {
  // Une vue à la fois : « apercu », « texte », « matrice », ou rien.
  const [vue, setVue] = useState(vueInitiale);
  const [essai, setEssai] = useState(null);
  const [pdfUrl, setPdfUrl] = useState(null);
  const [erreur, setErreur] = useState(null);

  // `pdfUrl` ne doit surtout pas figurer dans les dépendances : l'effet se
  // relancerait dès que l'URL est posée, et son nettoyage révoquerait l'URL qui
  // vient d'être créée — l'aperçu resterait gris.
  useEffect(() => {
    if (!vue) return undefined;
    let url = null;
    let annule = false;

    chargerFichier()
      .then((u) => {
        if (annule) {
          URL.revokeObjectURL(u);   // aperçu refermé entre-temps
          return;
        }
        url = u;
        setPdfUrl(u);
      })
      .catch((e) => {
        if (!annule) setErreur(e.message || t("Aperçu indisponible."));
      });

    return () => {
      annule = true;
      if (url) URL.revokeObjectURL(url);
      setPdfUrl(null);
    };
  }, [vue, documentId]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function essayer() {
    setEssai("en cours");
    try {
      setEssai(await api.testerExtraction(documentId));
    } catch (e) {
      setEssai({ erreur: e.message });
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <BoutonVue courante={vue} valeur="apercu" onChoisir={setVue} icone={FileText}>
          Aperçu
        </BoutonVue>
        {/* Sans document produit, il n'y a ni texte ni matrice : un travail qui
            a échoué avant l'indexation n'a rien laissé à lire. */}
        {documentId && (
          <>
            <BoutonVue courante={vue} valeur="texte" onChoisir={setVue} icone={ScanText}>
              Texte brut
            </BoutonVue>
            <BoutonVue courante={vue} valeur="matrice" onChoisir={setVue} icone={Grid3x3}>
              Matrice OCR
            </BoutonVue>
            <button onClick={essayer} disabled={essai === "en cours"} style={boutonApercu}>
              <FlaskConical size={12} />
              Tester l'extraction
            </button>
          </>
        )}
      </div>

      {essai && essai !== "en cours" && (
        <ResultatEssai essai={essai} onFermer={() => setEssai(null)} />
      )}

      {vue && (
        <div style={{ display: "flex", gap: 12, marginTop: 12, alignItems: "stretch", flexWrap: "wrap" }}>
          <div style={{ flex: vue === "apercu" ? "1 1 100%" : "1 1 45%", minWidth: 300 }}>
            {pdfUrl ? (
              // Pas de `type` imposé : le fichier reçu n'est pas toujours un
              // PDF — une facture scannée arrive parfois en JPEG. Le navigateur
              // lit alors le type porté par l'objet lui-même, que le serveur
              // annonce désormais correctement. Lui affirmer « application/pdf »
              // sur une image la faisait basculer en téléchargement.
              <embed
                src={pdfUrl}
                style={{ width: "100%", height: vue === "apercu" ? hauteur - 80 : hauteur,
                         border: "1px solid var(--line)", borderRadius: "var(--radius)" }}
              />
            ) : erreur ? (
              <div style={{ padding: "14px 12px", background: "var(--brick-soft)",
                            color: "var(--brick)", borderRadius: "var(--radius)", fontSize: 12 }}>
                Aperçu indisponible — {erreur}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{t("Chargement de l'aperçu…")}</div>
            )}
          </div>

          {/* La matrice prend un peu plus que la page : c'est elle qu'on lit
              caractère par caractère, l'aperçu ne sert qu'à comparer. */}
          {vue !== "apercu" && documentId && (
            <div style={{ flex: "1 1 52%", minWidth: 320 }}>
              <GrilleOcr documentId={documentId} matrice={vue === "matrice"} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BoutonVue({ courante, valeur, onChoisir, icone: Icone, children }) {
  const actif = courante === valeur;
  return (
    <button
      onClick={() => onChoisir(actif ? null : valeur)}
      aria-pressed={actif}
      style={{
        ...boutonApercu,
        borderColor: actif ? "var(--accent)" : "var(--line-strong)",
        color: actif ? "var(--accent)" : "var(--ink-soft)",
        background: actif ? "var(--accent-soft)" : "transparent",
      }}
    >
      <Icone size={12} />
      {children}
    </button>
  );
}

function ResultatEssai({ essai, onFermer }) {
  if (essai.erreur) {
    return (
      <div style={{ marginTop: 12, padding: "9px 12px", borderRadius: "var(--radius)",
                    background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5 }}>
        {essai.erreur}
      </div>
    );
  }

  const trouvees = Object.entries(essai.valeurs_retenues || {});
  return (
    <div style={{
      marginTop: 12, padding: "11px 13px", borderRadius: "var(--radius)",
      background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8,
                    flexWrap: "wrap" }}>
        <FlaskConical size={14} color="var(--ink-faint)" />
        <strong style={{ fontSize: 12.5 }}>{t("Essai d'extraction")}</strong>
        {/* Quel jeu s'applique (§19.6) : sans cette mention, on chercherait
            longtemps pourquoi une règle « ne marche pas » — elle marche, elle
            appartient simplement à un autre jeu. */}
        <span style={{ fontSize: 11.5, color: "var(--ink-soft)" }}>
          {essai.jeu
            ? `jeu « ${essai.jeu.nom} »${essai.jeu.generique ? t(" (générique)") : " (reconnu)"}`
            : t("aucun jeu de règles ne s'applique à ce type de document")}
        </span>
        <span style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
          · rien n'a été enregistré
        </span>
        <div style={{ flex: 1 }} />
        <button onClick={onFermer} style={{ ...boutonApercu, padding: "2px 8px" }}>Fermer</button>
      </div>

      {essai.texte_vide && (
        <div style={{ fontSize: 12, color: "var(--amber)", marginBottom: 8 }}>
          {t("Ce document n'a produit aucun texte : aucune règle ne pourra rien y lire.")}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-soft)", marginBottom: 4 }}>
            Valeurs retenues
          </div>
          {trouvees.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{t("Aucune.")}</div>
          )}
          {trouvees.map(([champ, valeur]) => (
            <div key={champ} style={{ fontSize: 12, color: "var(--ink)" }}>
              <code style={{ color: "var(--ink-faint)" }}>{champ}</code> : {valeur}
            </div>
          ))}
        </div>
        <div>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-soft)", marginBottom: 4 }}>
            Manque encore
          </div>
          {(essai.manquants || []).length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--accent)" }}>
              {t("Rien : la catégorie a tout ce qu'elle attend.")}
            </div>
          ) : essai.manquants.map((champ) => (
            <div key={champ.champ} style={{ fontSize: 12, color: "var(--ink)" }}>
              {t(champ.libelle)}
              {champ.obligatoire && (
                <span style={{ color: "var(--brick)", fontSize: 11 }}> · obligatoire</span>
              )}
            </div>
          ))}
        </div>
      </div>

      <details style={{ marginTop: 10 }}>
        <summary style={{ fontSize: 11.5, color: "var(--ink-soft)", cursor: "pointer" }}>
          Règle par règle ({(essai.regles || []).length})
        </summary>
        <div style={{ marginTop: 6 }}>
          {(essai.regles || []).map((regle, index) => (
            <div key={index} style={{
              display: "flex", gap: 8, alignItems: "baseline", fontSize: 11.5,
              color: regle.retenue ? "var(--ink)" : "var(--ink-faint)", padding: "1px 0",
            }}>
              <span style={{ width: 12, color: regle.retenue ? "var(--accent)" : undefined }}>
                {regle.retenue ? "✔" : regle.trouve ? "·" : "✗"}
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>{regle.regle}</span>
              <code>{regle.champ}</code>
              <span style={{ width: 160, textAlign: "right", overflow: "hidden",
                             textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {regle.valeur ?? "—"}
              </span>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6, lineHeight: 1.5 }}>
          ✔ retenue · ✗ sans résultat · « · » trouvée mais devancée par une règle
          plus prioritaire.
        </div>
      </details>
    </div>
  );
}

const boutonApercu = {
  display: "flex", alignItems: "center", gap: 5, border: "1px solid var(--line-strong)",
  background: "transparent", color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "4px 10px", fontSize: 12, flexShrink: 0,
};
