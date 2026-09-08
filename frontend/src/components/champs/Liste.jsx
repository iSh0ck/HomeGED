import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Search } from "lucide-react";
import { t } from "../../lib/langue";

/**
 * Liste déroulante du projet, en remplacement de `<select>`.
 *
 * Le `<select>` natif ne se met pas en forme : sa flèche, sa police, la fenêtre
 * qu'il ouvre appartiennent au système. Sur un écran soigné par ailleurs, il
 * détonne — et sous Windows il affiche une liste blanche à bordure bleue qui
 * n'a rien à voir avec le reste.
 *
 * Ce qu'il fallait garder du natif, et qui est reproduit ici : la navigation au
 * clavier (flèches, Entrée, Échap, Origine/Fin), la recherche par frappe, et le
 * fait qu'un clic ailleurs referme sans rien changer. Au-delà de douze entrées,
 * un champ de recherche s'ajoute — c'est le seuil à partir duquel on cherche
 * plutôt qu'on ne parcourt.
 *
 * `options` accepte `{valeur, libelle, groupe?, aide?}`. Les groupes rendent les
 * intitulés d'`<optgroup>` ; `aide` s'affiche au survol du choix — de quoi
 * expliquer une option sans allonger son intitulé, ni forcer à ouvrir une aide.
 *
 * La fenêtre est rendue **hors du flux**, à la racine du document : à l'intérieur
 * d'une fenêtre modale, une liste posée en `absolute` était coupée par le bord du
 * cadre — il fallait faire défiler pour voir les derniers choix, ce qu'un
 * `<select>` natif ne demande jamais. Posée à la racine et positionnée sur le
 * champ, elle s'ouvre par-dessus, et se retourne vers le haut quand le bas de
 * l'écran manque.
 */
export default function Liste({
  valeur,
  options = [],
  onChange,
  placeholder = "— Choisir —",
  compact = false,
  // Variante « rangée de filtres » (§18.14) : pas de cadre, un simple trait,
  // et la même hauteur que les autres champs de recherche — une rangée dont un
  // seul champ dépasse de quatre pixels ondule, et cela se voit.
  souligne = false,
  ariaLabel,
  style,
  disabled = false,
  // Force le champ de recherche, quel que soit le nombre d'entrées : une liste
  // adossée à une source peut être courte aujourd'hui et longue demain, et
  // l'utilisateur ne devrait pas avoir à s'apercevoir du changement.
  recherchable = false,
  // Prévient le parent de ce qui est tapé : à lui d'aller rechercher plus loin
  // que ce qu'il a déjà chargé, si sa source le permet.
  onRecherche,
}) {
  const [ouvert, setOuvert] = useState(false);
  const [recherche, setRecherche] = useState("");
  const [survol, setSurvol] = useState(0);
  const [cadre, setCadre] = useState(null);   // position de la fenêtre, à l'écran
  const zone = useRef(null);
  const listeRef = useRef(null);

  // La position se calcule à l'ouverture, puis suit défilement et redimension :
  // une fenêtre posée à la racine ne bouge pas toute seule avec son champ.
  useLayoutEffect(() => {
    if (!ouvert) return undefined;
    const placer = () => {
      const bord = zone.current?.getBoundingClientRect();
      if (!bord) return;
      const dessous = window.innerHeight - bord.bottom - 12;
      const dessus = bord.top - 12;
      // On ouvre vers le haut quand le bas manque **et** que le haut offre
      // mieux : mieux vaut une liste retournée qu'une liste écrasée.
      const versLeHaut = dessous < 200 && dessus > dessous;
      setCadre({
        left: bord.left,
        largeur: bord.width,
        haut: versLeHaut ? undefined : bord.bottom + 4,
        bas: versLeHaut ? window.innerHeight - bord.top + 4 : undefined,
        hauteurMax: Math.max(140, (versLeHaut ? dessus : dessous)),
      });
    };
    placer();
    window.addEventListener("scroll", placer, true);
    window.addEventListener("resize", placer);
    return () => {
      window.removeEventListener("scroll", placer, true);
      window.removeEventListener("resize", placer);
    };
  }, [ouvert]);

  const avecRecherche = recherchable || options.length > 12;

  const visibles = useMemo(() => {
    const terme = recherche.trim().toLowerCase();
    if (!terme) return options;
    return options.filter((o) => (o.libelle || "").toLowerCase().includes(terme));
  }, [options, recherche]);

  const choisie = options.find((o) => String(o.valeur) === String(valeur));

  useEffect(() => {
    if (!ouvert) return undefined;
    setRecherche("");
    setSurvol(Math.max(0, visibles.findIndex((o) => String(o.valeur) === String(valeur))));
    // La fenêtre vit désormais à la racine du document : un clic dedans n'est
    // plus « dans » le champ, et refermait la liste avant d'avoir choisi.
    const auClic = (e) => {
      if (zone.current?.contains(e.target)) return;
      if (e.target.closest?.("[data-liste-deroulante]")) return;
      setOuvert(false);
    };
    document.addEventListener("mousedown", auClic);
    return () => document.removeEventListener("mousedown", auClic);
    // Volontairement dépendant du seul `ouvert` : inclure `visibles` relancerait
    // l'effet à chaque frappe dans le filtre et remettrait la surbrillance sur
    // la première ligne, ce qui rendrait la navigation au clavier inutilisable.
  }, [ouvert]); // eslint-disable-line react-hooks/exhaustive-deps

  // L'entrée survolée doit rester visible quand on descend au clavier : sans
  // cela, la sélection sort de la fenêtre et l'on navigue à l'aveugle.
  useEffect(() => {
    const element = listeRef.current?.querySelector(`[data-index="${survol}"]`);
    element?.scrollIntoView({ block: "nearest" });
  }, [survol, ouvert]);

  function auClavier(evenement) {
    if (!ouvert) {
      if (["Enter", " ", "ArrowDown"].includes(evenement.key)) {
        evenement.preventDefault();
        setOuvert(true);
      }
      return;
    }
    if (evenement.key === "Escape") { setOuvert(false); return; }
    if (evenement.key === "ArrowDown") {
      evenement.preventDefault();
      setSurvol((n) => Math.min(visibles.length - 1, n + 1));
    } else if (evenement.key === "ArrowUp") {
      evenement.preventDefault();
      setSurvol((n) => Math.max(0, n - 1));
    } else if (evenement.key === "Home") {
      evenement.preventDefault(); setSurvol(0);
    } else if (evenement.key === "End") {
      evenement.preventDefault(); setSurvol(visibles.length - 1);
    } else if (evenement.key === "Enter") {
      evenement.preventDefault();
      const option = visibles[survol];
      if (option) { onChange?.(option.valeur); setOuvert(false); }
    }
  }

  return (
    <div ref={zone} style={{ position: "relative", ...style }}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOuvert(!ouvert)}
        onKeyDown={auClavier}
        aria-haspopup="listbox"
        aria-expanded={ouvert}
        aria-label={ariaLabel}
        className="champ-projet"
        style={{
          display: "flex", alignItems: "center", gap: 6, width: "100%",
          // En mode compact, la hauteur est fixée plutôt que déduite du
          // remplissage : ces listes voisinent avec d'autres champs dans une
          // rangée de filtres, et une hauteur qui dépend du contenu suffit à
          // rendre la rangée irrégulière.
          height: souligne ? 22 : compact ? 26 : undefined,
          padding: souligne ? "0 2px" : compact ? "0 8px" : "8px 10px",
          fontSize: compact || souligne ? 12 : 13, fontFamily: "inherit", textAlign: "left",
          border: souligne ? "none" : "1px solid var(--line-strong)",
          borderBottom: souligne
            ? `1px solid ${choisie ? "var(--accent)" : "var(--line-strong)"}`
            : "1px solid var(--line-strong)",
          borderRadius: souligne ? 0 : "var(--radius)",
          background: souligne ? "transparent" : "var(--bg-panel-alt)",
          color: choisie ? "var(--ink)" : "var(--ink-faint)",
          cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.6 : 1,
        }}
      >
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {choisie ? choisie.libelle : placeholder}
        </span>
        <ChevronDown size={compact ? 12 : 14} style={{
          flexShrink: 0, color: "var(--ink-faint)",
          transition: "transform 160ms", transform: ouvert ? "rotate(180deg)" : "none",
        }} />
      </button>

      {ouvert && cadre && createPortal(
        <div
          className="apparition"
          data-liste-deroulante=""
          style={{
            position: "fixed", left: cadre.left, top: cadre.haut, bottom: cadre.bas,
            minWidth: cadre.largeur, maxWidth: Math.max(cadre.largeur, 320),
            zIndex: 3000, background: "var(--bg-panel)",
            border: "1px solid var(--line)", borderRadius: "var(--radius)",
            boxShadow: "0 14px 32px -16px rgba(34, 40, 31, 0.45)",
            animationDuration: "120ms", overflow: "hidden",
            display: "flex", flexDirection: "column",
            maxHeight: cadre.hauteurMax,
          }}
        >
          {avecRecherche && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6, padding: "6px 8px",
              borderBottom: "1px solid var(--line)",
            }}>
              <Search size={12} color="var(--ink-faint)" />
              <input
                autoFocus
                value={recherche}
                onChange={(e) => {
                  setRecherche(e.target.value);
                  setSurvol(0);
                  onRecherche?.(e.target.value);
                }}
                onKeyDown={auClavier}
                placeholder={t("Filtrer…")}
                aria-label={t("Filtrer la liste")}
                style={{
                  flex: 1, border: "none", background: "transparent", outline: "none",
                  fontSize: 12, fontFamily: "inherit", color: "var(--ink)",
                }}
              />
            </div>
          )}

          <div ref={listeRef} role="listbox" className="scrollbar-thin"
               style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 3 }}>
            {visibles.length === 0 && (
              <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "8px 9px" }}>
                {t("Aucune correspondance.")}
              </div>
            )}
            {visibles.map((option, index) => {
              const nouveauGroupe = option.groupe
                && option.groupe !== visibles[index - 1]?.groupe;
              const active = String(option.valeur) === String(valeur);
              return (
                <React.Fragment key={`${option.groupe || ""}-${option.valeur}`}>
                  {nouveauGroupe && (
                    <div style={{
                      fontSize: 10, fontWeight: 600, color: "var(--ink-faint)",
                      padding: "8px 9px 3px", textTransform: "uppercase", letterSpacing: "0.04em",
                    }}>
                      {option.groupe}
                    </div>
                  )}
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    data-index={index}
                    onMouseEnter={() => setSurvol(index)}
                    title={t(option.aide)}
                    onClick={() => { onChange?.(option.valeur); setOuvert(false); }}
                    style={{
                      display: "flex", alignItems: "center", gap: 7, width: "100%",
                      border: "none", borderRadius: "var(--radius)", padding: "6px 9px",
                      background: index === survol ? "var(--bg-panel-alt)" : "transparent",
                      color: "var(--ink)", fontSize: 12.5, textAlign: "left", cursor: "pointer",
                    }}
                  >
                    <Check size={12} style={{ flexShrink: 0, opacity: active ? 1 : 0,
                                              color: "var(--accent)" }} />
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis",
                                   whiteSpace: "nowrap" }}>
                      {t(option.libelle)}
                    </span>
                  </button>
                </React.Fragment>
              );
            })}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
