import React, { useEffect, useMemo, useState } from "react";
import { Copy, Search, X } from "lucide-react";
import { api } from "../api";
import { t } from "../lib/langue";

/**
 * Le texte océrisé, en grille (§18.37).
 *
 * C'est la matière première des règles d'extraction. Tant qu'on ne l'a pas sous
 * les yeux, écrire une expression revient à deviner ce que la machine a lu : les
 * espaces qu'elle a semés dans un numéro de client, le « O » mis pour un zéro,
 * la ligne qu'elle a coupée en deux. Le Centre d'analyse est l'endroit où l'on
 * corrige un document mal lu ; c'est donc là qu'il faut pouvoir regarder.
 *
 * Trois repères, et ils servent tous à écrire une expression :
 *   le **numéro de ligne**, pour se retrouver dans un document long ;
 *   la **position du premier caractère** de la ligne dans le texte entier ;
 *   une **règle de colonnes** au-dessus, qui donne la colonne d'un caractère
 *   sans avoir à compter.
 *
 * Une recherche surligne au passage : on essaie un motif et l'on voit ce qu'il
 * attrape, avant de l'écrire dans une règle.
 */
export default function GrilleOcr({ documentId, onFermer, matrice = true }) {
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [recherche, setRecherche] = useState("");
  const [copie, setCopie] = useState(false);

  useEffect(() => {
    let annule = false;
    setDonnees(null);
    setErreur(null);
    api.texteOcr(documentId)
      .then((d) => { if (!annule) setDonnees(d); })
      .catch((e) => { if (!annule) setErreur(e.message); });
    return () => { annule = true; };
  }, [documentId]);

  const largeurMax = useMemo(
    () => Math.min(120, Math.max(40, ...(donnees?.lignes || []).map((l) => l.texte.length))),
    [donnees]);

  async function copier() {
    const texte = (donnees?.lignes || []).map((l) => l.texte).join("\n");
    try {
      await navigator.clipboard.writeText(texte);
      setCopie(true);
      setTimeout(() => setCopie(false), 2000);
    } catch {
      setErreur(t("Le navigateur refuse l'accès au presse-papiers."));
    }
  }

  return (
    <div style={cadre}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600 }}>{t("Texte reconnu")}</div>
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
          {donnees ? `${donnees.longueur} caractères · ${donnees.lignes.length} lignes` : ""}
        </div>
        <div style={{ flex: 1 }} />
        <div style={cadreRecherche}>
          <Search size={12} color="var(--ink-faint)" />
          <input
            value={recherche}
            onChange={(e) => setRecherche(e.target.value)}
            placeholder="surligner…"
            style={{
              border: "none", outline: "none", background: "transparent",
              fontSize: 11.5, width: 110, color: "var(--ink)",
            }}
          />
          {recherche && (
            <button onClick={() => setRecherche("")} aria-label={t("Effacer la recherche")}
                    style={boutonIcone}>
              <X size={11} />
            </button>
          )}
        </div>
        <button onClick={copier} style={boutonIcone} title={t("Copier tout le texte")}>
          <Copy size={12} />
        </button>
        {onFermer && (
          <button onClick={onFermer} style={boutonIcone} aria-label={t("Fermer la grille")}>
            <X size={13} />
          </button>
        )}
      </div>

      {copie && (
        <div style={{ fontSize: 11.5, color: "var(--accent)", marginBottom: 6 }}>
          Texte copié.
        </div>
      )}
      {erreur && <div style={{ fontSize: 12, color: "var(--brick)" }}>{erreur}</div>}
      {!donnees && !erreur && (
        <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{t("Lecture du texte…")}</div>
      )}

      {donnees?.vide && (
        <div style={{ fontSize: 12, color: "var(--amber)", lineHeight: 1.5 }}>
          {t("Ce document n'a produit aucun texte. Un scan trop pâle, une page à l'envers ou une image sans écriture donnent ce résultat : aucune règle ne pourra rien y lire.")}
        </div>
      )}

      {donnees && !donnees.vide && !matrice && (
        // Texte brut : ce que la machine a lu, tel quel. Le plus lisible pour
        // comprendre un document ; la matrice sert à compter les colonnes.
        <div style={{ ...grille, whiteSpace: "pre", lineHeight: 1.55 }} className="scrollbar-thin">
          {donnees.lignes.map((ligne) => (
            <div key={ligne.numero} style={{ display: "flex", gap: 10 }}>
              <span style={numeroBrut} title={`Position ${ligne.debut} dans le texte entier`}>
                {String(ligne.numero).padStart(3, " ")}
              </span>
              <span>{ligne.texte === ""
                ? <span style={{ color: "var(--line-strong)" }}>⏎</span>
                : ligne.texte}</span>
            </div>
          ))}
        </div>
      )}

      {donnees && !donnees.vide && matrice && (
        <div style={grille} className="scrollbar-thin">
          <table style={{ borderCollapse: "collapse", tableLayout: "fixed" }}>
            <thead>
              <tr>
                <th style={{ ...enteteCoin }} title={t("Numéro de ligne")}>{t("L\C")}</th>
                {Array.from({ length: largeurMax }, (_, colonne) => (
                  <th key={colonne} style={enteteColonne(colonne)}>
                    {colonne % 5 === 0 ? colonne : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {donnees.lignes.map((ligne) => (
                <LigneMatrice key={ligne.numero} ligne={ligne} largeur={largeurMax}
                              recherche={recherche} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/**
 * Une ligne de la matrice : un caractère par case.
 *
 * C'est ce que réclame l'écriture d'une expression — savoir que le numéro
 * commence colonne 17 et non « quelque part après le deux-points ». Les espaces
 * deviennent visibles par leur seule case vide, ce qu'un texte au fil de l'eau
 * ne montre pas : l'OCR en sème, et ce sont eux qui font échouer les motifs.
 */
function LigneMatrice({ ligne, largeur, recherche }) {
  const surlignes = useMemo(
    () => positionsSurlignees(ligne.texte, recherche), [ligne.texte, recherche]);

  return (
    <tr>
      <th style={enteteLigne} title={`Position ${ligne.debut} dans le texte entier`}>
        {ligne.numero}
      </th>
      {Array.from({ length: largeur }, (_, colonne) => {
        const caractere = ligne.texte[colonne];
        return (
          <td
            key={colonne}
            title={caractere !== undefined
              ? `L${ligne.numero} C${colonne} · position ${ligne.debut + colonne}`
              : undefined}
            style={{
              ...celluleMatrice,
              background: surlignes.has(colonne) ? "var(--amber-soft)" : undefined,
              color: caractere === " " ? "var(--line-strong)" : "var(--ink)",
            }}
          >
            {caractere === undefined ? "" : caractere === " " ? "·" : caractere}
          </td>
        );
      })}
    </tr>
  );
}

/** Colonnes couvertes par la recherche, pour les teinter case par case. */
function positionsSurlignees(texte, recherche) {
  const motif = (recherche || "").trim().toLowerCase();
  const positions = new Set();
  if (!motif) return positions;
  const bas = (texte || "").toLowerCase();
  let depart = 0;
  for (;;) {
    const trouve = bas.indexOf(motif, depart);
    if (trouve === -1) return positions;
    for (let i = trouve; i < trouve + motif.length; i += 1) positions.add(i);
    depart = trouve + motif.length;
  }
}

/**
 * Découpe une ligne autour des occurrences cherchées. La recherche est littérale
 * et insensible à la casse : on cherche ce qu'on lit, pas ce qu'on écrirait dans
 * une expression — celle-ci se teste sur le document, pas ici.
 */
function decouper(texte, recherche) {
  const motif = (recherche || "").trim();
  if (!motif) return [{ texte, surligne: false }];
  const morceaux = [];
  const bas = texte.toLowerCase();
  const cible = motif.toLowerCase();
  let position = 0;
  for (;;) {
    const trouve = bas.indexOf(cible, position);
    if (trouve === -1) {
      morceaux.push({ texte: texte.slice(position), surligne: false });
      return morceaux;
    }
    if (trouve > position) morceaux.push({ texte: texte.slice(position, trouve), surligne: false });
    morceaux.push({ texte: texte.slice(trouve, trouve + cible.length), surligne: true });
    position = trouve + cible.length;
  }
}

const cadre = {
  border: "1px solid var(--line)", borderRadius: "var(--radius)",
  background: "var(--bg-panel)", padding: "10px 12px",
};

const grille = {
  maxHeight: 460, overflow: "auto",
  fontFamily: "var(--font-mono)", fontSize: 11,
};

const LARGEUR_CASE = 13;

const numeroBrut = {
  color: "var(--ink-faint)", userSelect: "none", flexShrink: 0,
  fontVariantNumeric: "tabular-nums",
};

const celluleMatrice = {
  width: LARGEUR_CASE, minWidth: LARGEUR_CASE, height: 17,
  textAlign: "center", padding: 0,
  borderRight: "1px solid var(--line)", borderBottom: "1px solid var(--line)",
};

const enteteCoin = {
  position: "sticky", left: 0, top: 0, zIndex: 3,
  background: "var(--bg-panel-alt)", color: "var(--ink-faint)",
  fontWeight: 400, fontSize: 9.5, padding: "0 4px",
  borderRight: "1px solid var(--line-strong)", borderBottom: "1px solid var(--line-strong)",
};

function enteteColonne(colonne) {
  return {
    position: "sticky", top: 0, zIndex: 2,
    width: LARGEUR_CASE, minWidth: LARGEUR_CASE,
    background: "var(--bg-panel-alt)",
    color: colonne % 10 === 0 ? "var(--ink-soft)" : "var(--ink-faint)",
    fontWeight: colonne % 10 === 0 ? 600 : 400,
    fontSize: 9, padding: 0, textAlign: "center",
    borderRight: "1px solid var(--line)", borderBottom: "1px solid var(--line-strong)",
  };
}

const enteteLigne = {
  position: "sticky", left: 0, zIndex: 1,
  background: "var(--bg-panel-alt)", color: "var(--ink-faint)",
  fontWeight: 400, fontSize: 9.5, padding: "0 4px", textAlign: "right",
  borderRight: "1px solid var(--line-strong)", borderBottom: "1px solid var(--line)",
  fontVariantNumeric: "tabular-nums",
};

const cadreRecherche = {
  display: "flex", alignItems: "center", gap: 5,
  border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
  padding: "2px 6px",
};

const boutonIcone = {
  display: "flex", border: "1px solid transparent", background: "transparent",
  color: "var(--ink-faint)", borderRadius: "var(--radius)", padding: 3,
};
