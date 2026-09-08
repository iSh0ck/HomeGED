import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Search, X, Calendar, ChevronDown } from "lucide-react";
import { api } from "../api";
import ChampDate from "./champs/ChampDate.jsx";
import { versIso } from "./champs/dates";
import Liste from "./champs/Liste.jsx";
import { t } from "../lib/langue";

/**
 * Champs de recherche affichés sous l'en-tête de chaque colonne du registre.
 *
 * Chaque contrôle produit un filtre `{ operateur, valeur }` au format du moteur
 * de l'API (app/filtres.py) ; `null` signifie « aucun filtre sur cette colonne ».
 *
 * Principe retenu : **on peut toujours taper librement**. Les listes de valeurs
 * connues (catégories, émetteurs) et le calendrier ne sont que des aides à la
 * saisie, jamais une contrainte :
 *   - taper du texte      -> filtre « contient » sur le libellé ;
 *   - choisir dans la liste -> filtre « egal » sur l'identifiant, ce qui permet
 *     en prime de remonter les sous-catégories d'une section ;
 *   - le calendrier       -> opérateurs de date précis (avant, entre, ...).
 */
export default function ColumnFilter({ col, filtre, onChange, contexte, categorieId, recherche }) {
  const perimetre = { filtres: versCriteres(contexte), categorieId, q: recherche };
  if (col.filtre === "date") {
    return <FiltreDate filtre={filtre} onChange={onChange} />;
  }
  if (col.filtre === "liste") {
    return <FiltreListe col={col} filtre={filtre} onChange={onChange} perimetre={perimetre} />;
  }
  return <FiltreCombobox col={col} filtre={filtre} onChange={onChange} perimetre={perimetre} />;
}

/**
 * Traduit les filtres de colonne en critères pour l'API, en écartant ceux qui
 * sont incomplets (« entre » à moitié saisi, champ vidé...).
 */
export function versCriteres(filtres) {
  return Object.entries(filtres || {})
    .filter(([, f]) => estActif(f))
    // Seules ces trois clés partent à l'API : le reste (le libellé affiché, la
    // saisie en cours d'un champ de date) sert à l'écran et ferait rejeter le
    // critère par le moteur de filtres.
    .map(([champ, f]) => ({ champ, operateur: f.operateur || "contient", valeur: f.valeur }));
}

export function estActif(filtre) {
  if (!filtre) return false;
  if (filtre.operateur === "vide" || filtre.operateur === "non_vide") return true;
  if (Array.isArray(filtre.valeur)) return filtre.valeur.every(Boolean);
  return String(filtre.valeur ?? "").trim() !== "";
}

/* ------------------------------------------------------------------ */
/* Saisie libre + suggestions issues des documents                     */
/* ------------------------------------------------------------------ */

/**
 * Champ de recherche universel : on tape librement, et la liste ne propose que
 * les valeurs **réellement présentes dans les documents** pour cette colonne,
 * restreintes aux autres filtres actifs.
 * Rien n'est prédéfini : une catégorie ou un émetteur sans aucun document ne
 * sera jamais suggéré.
 */
function FiltreCombobox({ col, filtre, onChange, perimetre }) {
  const cellule = useRef(null);
  const [ouvert, setOuvert] = useState(false);
  const [focus, setFocus] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [chargement, setChargement] = useState(false);
  const [surligne, setSurligne] = useState(0);
  const actif = estActif(filtre);

  const saisie = filtre?.operateur === "contient" ? String(filtre.valeur ?? "") : "";
  const choisi = filtre?.operateur === "egal" ? filtre.libelle ?? String(filtre.valeur) : null;

  // Les suggestions sont recalculées à l'ouverture et à chaque frappe (avec un
  // court délai pour ne pas interroger l'API à chaque caractère).
  useEffect(() => {
    if (!ouvert) return;
    let annule = false;
    setChargement(true);
    const timer = setTimeout(() => {
      api
        .valeursColonne(col.champ, { ...perimetre, recherche: saisie })
        .then((v) => { if (!annule) { setSuggestions(v); setSurligne(0); } })
        .catch(() => { if (!annule) setSuggestions([]); })
        .finally(() => { if (!annule) setChargement(false); });
    }, 180);
    return () => { annule = true; clearTimeout(timer); };
    // `perimetre` est reconstruit à chaque rendu : le sérialiser évite de
    // relancer la requête sans que rien n'ait changé.
  }, [ouvert, saisie, col.champ, JSON.stringify(perimetre)]); // eslint-disable-line react-hooks/exhaustive-deps

  function choisir(suggestion) {
    onChange({ operateur: "egal", valeur: suggestion.valeur, libelle: suggestion.libelle });
    setOuvert(false);
  }

  function surTouche(e) {
    const total = suggestions.length + 1; // + l'entrée « Non renseigné »
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOuvert(true);
      setSurligne((i) => (i + (e.key === "ArrowDown" ? 1 : -1) + total) % total);
    } else if (e.key === "Enter" && ouvert) {
      e.preventDefault();
      if (surligne < suggestions.length) choisir(suggestions[surligne]);
      else { onChange({ operateur: "vide", valeur: null }); setOuvert(false); }
    } else if (e.key === "Escape") {
      setOuvert(false);
    }
  }

  const libelleFige = filtre?.operateur === "vide" ? t("Non renseigné") : choisi;

  return (
    <div ref={cellule} className="filtre-colonne"
         style={{ ...cadreStyle(actif, ouvert || focus), paddingLeft: 2, paddingRight: 2 }}>
      {/* La loupe ne s'affiche qu'au survol ou quand un filtre est posé : cinq
          loupes en rang attirent l'œil sans rien lui apprendre. */}
      <Search size={12} className={actif ? "filtre-loupe active" : "filtre-loupe"}
              color={actif ? "var(--accent)" : "var(--ink-faint)"} style={{ flexShrink: 0 }} />

      {libelleFige ? (
        <ValeurFigee libelle={libelleFige} onOuvrir={() => setOuvert(true)} />
      ) : (
        <input
          value={saisie}
          onChange={(e) => {
            setOuvert(true);
            onChange(e.target.value ? { operateur: "contient", valeur: e.target.value } : null);
          }}
          onFocus={() => { setFocus(true); setOuvert(true); }}
          onBlur={() => setFocus(false)}
          onKeyDown={surTouche}
          onClick={(e) => { e.stopPropagation(); setOuvert(true); }}
          placeholder="Rechercher"
          style={saisieStyle}
        />
      )}

      {actif && <BoutonEffacer onClick={() => { onChange(null); setOuvert(false); }} />}
      <button
        onClick={(e) => { e.stopPropagation(); setOuvert((o) => !o); }}
        aria-label={t("Voir les valeurs présentes dans les documents")}
        title={t("Voir les valeurs présentes dans les documents")}
        style={boutonIconeStyle}
      >
        <ChevronDown size={12} />
      </button>

      {ouvert && (
        <Popover ancre={cellule} onClose={() => setOuvert(false)} largeur={250}>
          <div style={{ maxHeight: 260, overflowY: "auto" }} className="scrollbar-thin">
            {chargement && suggestions.length === 0 && (
              <div style={messageStyle}>{t("Recherche…")}</div>
            )}
            {!chargement && suggestions.length === 0 && (
              <div style={messageStyle}>
                Aucune valeur de ce type dans les documents{saisie ? t(" pour cette saisie") : ""}.
              </div>
            )}
            {suggestions.map((v, i) => (
              <OptionListe
                key={`${v.valeur}-${i}`}
                actif={i === surligne}
                selectionne={filtre?.operateur === "egal" && String(filtre.valeur) === String(v.valeur)}
                onClick={() => choisir(v)}
                onSurvol={() => setSurligne(i)}
                indentation={(v.profondeur || 0) * 12}
              >
                {t(v.libelle)}
              </OptionListe>
            ))}
            <div style={{ borderTop: "1px solid var(--line)", marginTop: 4, paddingTop: 4 }}>
              <OptionListe
                actif={surligne === suggestions.length}
                selectionne={filtre?.operateur === "vide"}
                onClick={() => { onChange({ operateur: "vide", valeur: null }); setOuvert(false); }}
                onSurvol={() => setSurligne(suggestions.length)}
              >
                <span style={{ color: "var(--ink-soft)", fontStyle: "italic" }}>{t("Non renseigné")}</span>
              </OptionListe>
            </div>
          </div>
        </Popover>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Énumération (statut)                                                */
/* ------------------------------------------------------------------ */

function FiltreListe({ col, filtre, onChange, perimetre }) {
  const [valeurs, setValeurs] = useState(null);

  // Les entrées proposées sont celles réellement présentes dans la vue : si
  // tous les documents affichés sont « traités », la liste ne propose que
  // « Traité ». Une valeur qui ne ramènerait aucune ligne est une fausse piste.
  useEffect(() => {
    let annule = false;
    api
      .valeursColonne(col.champ, perimetre)
      .then((v) => { if (!annule) setValeurs(v); })
      .catch(() => { if (!annule) setValeurs([]); });
    return () => { annule = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [col.champ, JSON.stringify(perimetre)]);

  // Les intitulés lisibles viennent de la colonne ; une valeur inconnue
  // s'affiche telle quelle plutôt que de disparaître.
  const intitules = new Map((col.options || []).map((o) => [o.value, o.label]));
  const options = [
    { valeur: "", libelle: "Tous" },
    ...(valeurs || []).map((v) => ({
      valeur: v.valeur,
      libelle: intitules.get(v.valeur) || v.libelle || v.valeur,
    })),
  ];

  return (
    <Liste
      compact
      souligne
      valeur={filtre?.valeur ?? ""}
      ariaLabel={`Filtrer sur ${col.label}`}
      options={options}
      onChange={(v) => onChange(v ? { operateur: "egal", valeur: v } : null)}
      style={{ width: "100%" }}
    />
  );
}

/* ------------------------------------------------------------------ */
/* Date : saisie libre + calendrier et opérateurs                      */
/* ------------------------------------------------------------------ */

// Une fonction, pas une constante : un t() évalué au chargement du module
// figerait les intitulés dans la langue de départ.
const OPERATEURS_DATE = () => [
  { valeur: "egal", label: t("Le"), champs: 1 },
  { valeur: "apres", label: t("Après le"), champs: 1 },
  { valeur: "avant", label: t("Avant le"), champs: 1 },
  { valeur: "entre", label: t("Entre"), champs: 2 },
  { valeur: "non_vide", label: t("Renseignée"), champs: 0 },
  { valeur: "vide", label: t("Absente"), champs: 0 },
];

function formaterDate(valeur) {
  if (!valeur) return "";
  const [a, m, j] = String(valeur).split("-");
  return j ? `${j}/${m}/${a}` : String(valeur);
}

function resumeDate(filtre) {
  const op = OPERATEURS_DATE().find((o) => o.valeur === filtre?.operateur);
  if (!op) return null;
  if (op.champs === 0) return op.label;
  if (op.champs === 2) return `${formaterDate(filtre.valeur[0])} – ${formaterDate(filtre.valeur[1])}`;
  return `${op.label} ${formaterDate(filtre.valeur)}`;
}

function FiltreDate({ filtre, onChange }) {
  const cellule = useRef(null);
  const [ouvert, setOuvert] = useState(false);
  const [focus, setFocus] = useState(false);
  const actif = estActif(filtre);

  // « contient » = ce que l'utilisateur a tapé à la main (ex. « 2026-08 ») ;
  // les autres opérateurs viennent du panneau et sont résumés en toutes lettres.
  // Une saisie au clavier reste « en mode texte » tant qu'on la modifie, même
  // quand elle a produit un opérateur précis : sinon le champ se figerait en
  // résumé au milieu de la frappe.
  const modeTexte = !filtre || filtre.operateur === "contient" || Boolean(filtre.saisie);
  const resume = modeTexte ? null : resumeDate(filtre);

  const operateur = modeTexte ? "egal" : filtre.operateur;
  const definition = OPERATEURS_DATE().find((o) => o.valeur === operateur) ?? OPERATEURS_DATE()[0];
  const valeurs = Array.isArray(filtre?.valeur) ? filtre.valeur : [modeTexte ? "" : filtre?.valeur ?? "", ""];

  function majOperateur(nouvel) {
    const def = OPERATEURS_DATE().find((o) => o.valeur === nouvel);
    if (def.champs === 0) return onChange({ operateur: nouvel, valeur: null });
    if (def.champs === 2) return onChange({ operateur: nouvel, valeur: [valeurs[0] || "", valeurs[1] || ""] });
    onChange({ operateur: nouvel, valeur: valeurs[0] || "" });
  }

  // Ce que l'utilisateur voit dans le champ, en français. La valeur envoyée à
  // l'API reste au format ISO — le stockage n'a pas à suivre les habitudes
  // d'écriture, et l'utilisateur n'a pas à connaître celles du stockage.
  const saisieLibre = modeTexte ? (filtre?.saisie ?? "") : "";

  /**
   * Saisie au clavier, sans ouvrir le calendrier.
   *
   * Trois formes acceptées, de la plus précise à la plus large :
   *   `04/09/2026` un jour ;
   *   `09/2026`    un mois entier ;
   *   `2026`       une année entière.
   * Les deux dernières deviennent un intervalle : c'est ce que l'utilisateur
   * veut dire, et c'est ce que le moteur de filtres sait faire.
   */
  function taperDate(texte) {
    const chiffres = texte.replace(/\D/g, "").slice(0, 8);
    if (!chiffres) return onChange(null);

    const morceaux = [chiffres.slice(0, 2), chiffres.slice(2, 4), chiffres.slice(4, 8)]
      .filter(Boolean);
    const formate = morceaux.join("/");

    const jour = versIso(formate);
    if (jour) return onChange({ operateur: "egal", valeur: jour, saisie: formate });

    const mois = /^(\d{2})\/(\d{4})$/.exec(formate);
    if (mois) {
      const dernier = new Date(Number(mois[2]), Number(mois[1]), 0).getDate();
      return onChange({
        operateur: "entre", saisie: formate,
        valeur: [`${mois[2]}-${mois[1]}-01`, `${mois[2]}-${mois[1]}-${dernier}`],
      });
    }
    const annee = /^(\d{4})$/.exec(chiffres.length === 4 ? chiffres : "");
    if (annee) {
      return onChange({ operateur: "entre", saisie: formate,
                        valeur: [`${annee[1]}-01-01`, `${annee[1]}-12-31`] });
    }
    // saisie encore incomplète : on la garde à l'écran sans filtrer
    onChange({ operateur: "contient", valeur: "", saisie: formate });
  }

  function majDate(index, valeur) {
    if (definition.champs === 2) {
      const paire = [...valeurs];
      paire[index] = valeur;
      return onChange({ operateur: "entre", valeur: paire });
    }
    onChange(valeur ? { operateur, valeur } : null);
  }

  return (
    <div ref={cellule} className="filtre-colonne"
         style={{ ...cadreStyle(actif, ouvert || focus), paddingLeft: 2, paddingRight: 2 }}>
      {resume ? (
        <ValeurFigee libelle={resume} onOuvrir={() => setOuvert(true)} />
      ) : (
        <input
          value={saisieLibre}
          onChange={(e) => taperDate(e.target.value)}
          onFocus={() => { setFocus(true); setOuvert(true); }}
          onBlur={() => setFocus(false)}
          onClick={(e) => { e.stopPropagation(); setOuvert(true); }}
          placeholder="jj/mm/aaaa"
          inputMode="numeric"
          aria-label={t("Filtrer par date, au format jour/mois/année")}
          style={saisieStyle}
        />
      )}

      {actif && <BoutonEffacer onClick={() => { onChange(null); setOuvert(false); }} />}
      <button
        onClick={(e) => { e.stopPropagation(); setOuvert((o) => !o); }}
        aria-label={t("Choisir une date ou un opérateur")}
        title={t("Choisir une date ou un opérateur")}
        style={boutonIconeStyle}
      >
        <Calendar size={12} />
      </button>

      {ouvert && (
        <Popover ancre={cellule} onClose={() => setOuvert(false)} largeur={244}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 214 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {OPERATEURS_DATE().map((o) => (
                <button
                  key={o.valeur}
                  onClick={() => majOperateur(o.valeur)}
                  style={{
                    border: "1px solid " + (!modeTexte && o.valeur === operateur ? "var(--accent)" : "var(--line)"),
                    background: !modeTexte && o.valeur === operateur ? "var(--accent-soft)" : "var(--bg-panel)",
                    color: "var(--ink)",
                    borderRadius: "var(--radius)",
                    padding: "3px 8px",
                    fontSize: 11,
                  }}
                >
                  {o.label}
                </button>
              ))}
            </div>

            {definition.champs > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <ChampDate
                  compact
                  valeur={valeurs[0] || ""}
                  max={definition.champs === 2 ? (valeurs[1] || undefined) : undefined}
                  ariaLabel={definition.champs === 2 ? t("Date de début") : "Date"}
                  onChange={(v) => majDate(0, v)}
                  style={{ width: 122 }}
                />
                {definition.champs === 2 && (
                  <>
                    <span style={{ fontSize: 11, color: "var(--ink-faint)" }}>et</span>
                    <ChampDate
                      compact
                      valeur={valeurs[1] || ""}
                      min={valeurs[0] || undefined}
                      ariaLabel={t("Date de fin")}
                      onChange={(v) => majDate(1, v)}
                      style={{ width: 122 }}
                    />
                  </>
                )}
              </div>
            )}

            <div style={{ fontSize: 10, color: "var(--ink-faint)", lineHeight: 1.4 }}>
              {t("Vous pouvez aussi taper directement dans la colonne : « 04/09/2026 » pour un jour, « 09/2026 » pour tout un mois, « 2026 » pour l'année entière.")}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <button onClick={() => { onChange(null); setOuvert(false); }} style={lienStyle}>Effacer</button>
              <button onClick={() => setOuvert(false)} style={lienStyle}>Fermer</button>
            </div>
          </div>
        </Popover>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Éléments communs                                                    */
/* ------------------------------------------------------------------ */

/** Affichage d'un filtre choisi au panneau (non éditable au clavier ici). */
function ValeurFigee({ libelle, onOuvrir }) {
  return (
    <span
      onClick={(e) => { e.stopPropagation(); onOuvrir(); }}
      title={libelle}
      style={{
        flex: 1,
        minWidth: 0,
        fontSize: 12,
        color: "var(--ink)",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        cursor: "pointer",
      }}
    >
      {libelle}
    </span>
  );
}

function OptionListe({ children, actif, selectionne, onClick, onSurvol, indentation = 0 }) {
  return (
    <button
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      onMouseEnter={onSurvol}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        width: "100%",
        textAlign: "left",
        border: "none",
        background: actif ? "var(--accent-soft)" : "transparent",
        color: "var(--ink)",
        fontWeight: selectionne ? 600 : 400,
        fontSize: 12,
        padding: "4px 8px",
        paddingLeft: 8 + indentation,
        borderRadius: 2,
      }}
    >
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {children}
      </span>
    </button>
  );
}

/**
 * Panneau flottant positionné en `fixed` d'après la position de la cellule :
 * la ligne de filtres est dans un conteneur défilant, un positionnement absolu
 * y serait rogné.
 */
function Popover({ ancre, onClose, largeur = 240, children }) {
  const panneau = useRef(null);
  const [position, setPosition] = useState(null);

  useLayoutEffect(() => {
    const rect = ancre.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      top: rect.bottom + 4,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - largeur - 8)),
      minWidth: Math.max(rect.width, 160),
    });
  }, [ancre, largeur]);

  useEffect(() => {
    function surClicExterieur(e) {
      if (!panneau.current?.contains(e.target) && !ancre.current?.contains(e.target)) onClose();
    }
    function surTouche(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", surClicExterieur);
    document.addEventListener("keydown", surTouche);
    return () => {
      document.removeEventListener("mousedown", surClicExterieur);
      document.removeEventListener("keydown", surTouche);
    };
  }, [ancre, onClose]);

  if (!position) return null;

  return (
    <div
      ref={panneau}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "fixed",
        top: position.top,
        left: position.left,
        minWidth: position.minWidth,
        maxWidth: largeur,
        zIndex: 50,
        background: "var(--bg-panel)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-panel)",
        padding: 8,
      }}
    >
      {children}
    </div>
  );
}

function BoutonEffacer({ onClick }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      aria-label={t("Effacer ce filtre")}
      title={t("Effacer ce filtre")}
      style={{ ...boutonIconeStyle, color: "var(--ink-faint)" }}
    >
      <X size={11} />
    </button>
  );
}

/**
 * Le champ de recherche d'une colonne : un simple trait sous l'intitulé.
 *
 * Encadré, il pesait autant que l'en-tête lui-même — cinq boîtes en rang qui
 * réclamaient l'attention avant les documents. Un soulignement suffit à dire
 * « on peut écrire ici », et laisse la ligne se lire comme la suite du tableau.
 *
 * Le trait dit aussi l'état : discret au repos, marqué au survol et à la saisie,
 * en couleur d'accent quand un filtre est posé — la couleur ne sert qu'à ce qui
 * modifie ce qu'on voit.
 */
function cadreStyle(actif, focus) {
  const couleur = actif || focus ? "var(--accent)" : "var(--line-strong)";
  return {
    position: "relative",
    display: "flex",
    alignItems: "center",
    gap: 2,
    height: 22,
    border: "none",
    borderBottom: `1px solid ${couleur}`,
    background: "transparent",
    borderRadius: 0,
    // Le trait s'épaissit au lieu qu'un cadre apparaisse : une ombre interne
    // sur le seul bord bas, jamais un rectangle autour du champ.
    boxShadow: focus || actif ? `inset 0 -1px 0 ${couleur}` : "none",
    transition: "border-color 120ms, box-shadow 120ms",
  };
}

const saisieStyle = {
  flex: 1,
  minWidth: 0,
  border: "none",
  outline: "none",
  background: "transparent",
  fontFamily: "inherit",
  fontSize: 12,
  color: "var(--ink)",
  height: "100%",
  padding: 0,
};

const boutonIconeStyle = {
  display: "flex",
  alignItems: "center",
  border: "none",
  background: "transparent",
  color: "var(--ink-faint)",
  padding: "2px 3px",
  flexShrink: 0,
};


const messageStyle = {
  fontSize: 11,
  color: "var(--ink-faint)",
  padding: "6px 8px",
  lineHeight: 1.4,
};

const lienStyle = {
  border: "none",
  background: "transparent",
  color: "var(--ink-soft)",
  fontSize: 11,
  padding: 2,
  textDecoration: "underline",
};
