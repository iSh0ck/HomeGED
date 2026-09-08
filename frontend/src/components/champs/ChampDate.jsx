import React, { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react";
import {
  JOURS, MOIS, grilleDuMois, isoDuJour, versFrancais, versIso,
} from "./dates";
import { t } from "../../lib/langue";

/**
 * Champ de date du projet, en remplacement de `<input type="date">`.
 *
 * Le champ natif a deux défauts qui se voient : son apparence change d'un
 * navigateur à l'autre — impossible à accorder au reste de l'interface — et son
 * calendrier n'est pas celui d'ici (semaine commençant le dimanche selon la
 * langue du système, mois en anglais chez qui a un système anglais).
 *
 * Ce champ garde ce que le natif faisait bien : **on peut taper la date** sans
 * ouvrir le calendrier. C'est le geste le plus rapide pour qui connaît la date,
 * et le supprimer au nom de la jolie fenêtre serait un mauvais échange.
 *
 * `valeur` et `onChange` parlent ISO (`2026-09-04`), comme l'API ; l'affichage
 * est en français. La conversion vit dans `dates.js`.
 */
export default function ChampDate({
  valeur = "",
  onChange,
  min,
  max,
  placeholder = "jj/mm/aaaa",
  compact = false,
  ariaLabel,
  style,
}) {
  const [saisie, setSaisie] = useState(versFrancais(valeur));
  const [ouvert, setOuvert] = useState(false);
  const zone = useRef(null);

  // La valeur peut changer de l'extérieur (réinitialisation d'un filtre, vue
  // enregistrée appliquée) : le champ doit suivre.
  useEffect(() => { setSaisie(versFrancais(valeur)); }, [valeur]);

  useEffect(() => {
    if (!ouvert) return undefined;
    const auClic = (e) => { if (!zone.current?.contains(e.target)) setOuvert(false); };
    const auClavier = (e) => { if (e.key === "Escape") setOuvert(false); };
    document.addEventListener("mousedown", auClic);
    document.addEventListener("keydown", auClavier);
    return () => {
      document.removeEventListener("mousedown", auClic);
      document.removeEventListener("keydown", auClavier);
    };
  }, [ouvert]);

  function taper(texte) {
    // On ne garde que ce qui peut composer une date, et on pose les barres
    // obliques au fil de la frappe : taper « 04092026 » écrit « 04/09/2026 ».
    const chiffres = texte.replace(/\D/g, "").slice(0, 8);
    const morceaux = [chiffres.slice(0, 2), chiffres.slice(2, 4), chiffres.slice(4, 8)];
    const formate = morceaux.filter(Boolean).join("/");
    setSaisie(formate);
    const iso = versIso(formate);
    if (iso) onChange?.(iso);
    else if (!chiffres) onChange?.("");
  }

  function quitter() {
    // Saisie incomplète abandonnée : on revient à la valeur connue plutôt que
    // de laisser « 04/09 » à l'écran, qui donnerait à croire qu'il s'est passé
    // quelque chose.
    if (!versIso(saisie)) setSaisie(versFrancais(valeur));
  }

  return (
    <div ref={zone} style={{ position: "relative", ...style }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <input
          value={saisie}
          onChange={(e) => taper(e.target.value)}
          onBlur={quitter}
          onKeyDown={(e) => { if (e.key === "Enter") setOuvert(false); }}
          placeholder={placeholder}
          inputMode="numeric"
          aria-label={ariaLabel || t("Date, au format jour/mois/année")}
          className="champ-projet"
          style={{
            width: "100%",
            // Même hauteur que les autres filtres de colonne : sans elle, la
            // rangée de recherche se déforme d'un champ à l'autre.
            height: compact ? 26 : undefined,
            boxSizing: "border-box",
            padding: compact ? "0 30px 0 8px" : "8px 34px 8px 10px",
            fontSize: compact ? 12 : 13,
            fontFamily: "inherit",
            border: "1px solid var(--line-strong)",
            borderRadius: "var(--radius)",
            background: "var(--bg-panel-alt)",
            color: "var(--ink)",
          }}
        />
        <button
          type="button"
          onClick={() => setOuvert(!ouvert)}
          aria-label={ouvert ? t("Fermer le calendrier") : t("Ouvrir le calendrier")}
          title="Calendrier"
          style={{
            position: "absolute", right: 3, display: "flex", border: "none",
            background: "transparent", color: ouvert ? "var(--accent)" : "var(--ink-faint)",
            padding: 4, cursor: "pointer",
          }}
        >
          <CalendarDays size={compact ? 13 : 15} />
        </button>
      </div>

      {ouvert && (
        <Calendrier
          valeur={valeur}
          min={min}
          max={max}
          onChoisir={(iso) => { onChange?.(iso); setSaisie(versFrancais(iso)); setOuvert(false); }}
          onEffacer={() => { onChange?.(""); setSaisie(""); setOuvert(false); }}
        />
      )}
    </div>
  );
}

function Calendrier({ valeur, min, max, onChoisir, onEffacer }) {
  const depart = valeur || isoDuJour();
  const [annee, setAnnee] = useState(Number(depart.slice(0, 4)));
  const [mois, setMois] = useState(Number(depart.slice(5, 7)) - 1);
  // Trois vues successives derrière le même en-tête : jours, mois, années.
  // Sans elles, atteindre une date de 2019 demandait quatre-vingts clics sur la
  // flèche « mois précédent » — le calendrier devenait plus lent que la saisie
  // au clavier qu'il est censé épauler.
  const [vue, setVue] = useState("jours");

  const cases = useMemo(() => grilleDuMois(annee, mois), [annee, mois]);
  const aujourdhui = isoDuJour();

  function deplacer(pas) {
    if (vue === "annees") { setAnnee(annee + pas * 12); return; }
    if (vue === "mois") { setAnnee(annee + pas); return; }
    const suivant = new Date(annee, mois + pas, 1);
    setAnnee(suivant.getFullYear());
    setMois(suivant.getMonth());
  }

  const isoDe = (jour) =>
    `${annee}-${String(mois + 1).padStart(2, "0")}-${String(jour).padStart(2, "0")}`;

  const horsBornes = (iso) => (min && iso < min) || (max && iso > max);

  return (
    <div
      role="dialog"
      aria-label="Calendrier"
      className="apparition"
      style={{
        position: "absolute", top: "calc(100% + 5px)", left: 0, zIndex: 60,
        width: 244, padding: 10, background: "var(--bg-panel)",
        border: "1px solid var(--line)", borderRadius: "var(--radius)",
        boxShadow: "0 14px 32px -16px rgba(34, 40, 31, 0.45)",
        animationDuration: "140ms",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <BoutonMois onClick={() => deplacer(-1)} label={t("Mois précédent")}>
          <ChevronLeft size={14} />
        </BoutonMois>
        <button
          type="button"
          onClick={() => setVue(vue === "jours" ? "mois" : vue === "mois" ? "annees" : "jours")}
          aria-label={vue === "jours" ? t("Choisir un mois") : vue === "mois" ? t("Choisir une année") : t("Revenir aux jours")}
          title={vue === "jours" ? t("Choisir un mois") : vue === "mois" ? t("Choisir une année") : t("Revenir aux jours")}
          style={{
            border: "none", background: "transparent", color: "var(--ink)",
            fontSize: 12.5, fontWeight: 600, textTransform: "capitalize",
            cursor: "pointer", padding: "2px 6px", borderRadius: "var(--radius)",
            fontFamily: "inherit",
          }}
        >
          {vue === "jours" && `${t(MOIS[mois])} ${annee}`}
          {vue === "mois" && annee}
          {vue === "annees" && `${debutDecennie(annee)} – ${debutDecennie(annee) + 11}`}
        </button>
        <BoutonMois onClick={() => deplacer(1)} label={t("Mois suivant")}>
          <ChevronRight size={14} />
        </BoutonMois>
      </div>

      {vue === "mois" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, marginTop: 8 }}>
          {MOIS.map((nom, index) => (
            <button
              key={nom}
              type="button"
              onClick={() => { setMois(index); setVue("jours"); }}
              style={{
                ...caseChoix,
                background: index === mois ? "var(--accent)" : "transparent",
                color: index === mois ? "#fff" : "var(--ink)",
              }}
            >
              {t(nom).slice(0, 4)}.
            </button>
          ))}
        </div>
      )}

      {vue === "annees" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, marginTop: 8 }}>
          {Array.from({ length: 12 }, (_, index) => debutDecennie(annee) + index).map((an) => (
            <button
              key={an}
              type="button"
              onClick={() => { setAnnee(an); setVue("mois"); }}
              style={{
                ...caseChoix,
                background: an === annee ? "var(--accent)" : "transparent",
                color: an === annee ? "#fff" : "var(--ink)",
              }}
            >
              {an}
            </button>
          ))}
        </div>
      )}

      {vue === "jours" && (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginTop: 8 }}>
        {JOURS.map((jour) => (
          <div key={jour} style={{
            fontSize: 10, color: "var(--ink-faint)", textAlign: "center", paddingBottom: 2,
          }}>
            {t(jour).slice(0, 2)}
          </div>
        ))}

        {cases.map((jour, index) => {
          if (!jour) return <span key={`vide${index}`} />;
          const iso = isoDe(jour);
          const choisi = iso === valeur;
          const bloque = horsBornes(iso);
          return (
            <button
              key={iso}
              type="button"
              disabled={bloque}
              onClick={() => onChoisir(iso)}
              aria-current={choisi ? "date" : undefined}
              style={{
                height: 26, border: iso === aujourdhui && !choisi
                  ? "1px solid var(--accent)" : "1px solid transparent",
                borderRadius: "var(--radius)",
                background: choisi ? "var(--accent)" : "transparent",
                color: bloque ? "var(--ink-faint)" : (choisi ? "#fff" : "var(--ink)"),
                fontSize: 12, cursor: bloque ? "default" : "pointer",
                opacity: bloque ? 0.35 : 1,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {jour}
            </button>
          );
        })}
      </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
        <BoutonLien onClick={() => { setVue("jours"); onChoisir(aujourdhui); }}>
          Aujourd'hui
        </BoutonLien>
        {valeur && (
          <BoutonLien onClick={onEffacer}>
            <X size={10} /> Effacer
          </BoutonLien>
        )}
      </div>
    </div>
  );
}

/** Première année du bloc de douze affiché dans la vue « années ». */
function debutDecennie(annee) {
  return annee - ((annee % 12) + 12) % 12;
}

const caseChoix = {
  height: 30, border: "1px solid transparent", borderRadius: "var(--radius)",
  fontSize: 12, cursor: "pointer", fontFamily: "inherit",
  textTransform: "capitalize", fontVariantNumeric: "tabular-nums",
};

function BoutonMois({ children, onClick, label }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label} style={{
      display: "flex", border: "1px solid var(--line)", background: "transparent",
      color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: 3, cursor: "pointer",
    }}>
      {children}
    </button>
  );
}

function BoutonLien({ children, onClick }) {
  return (
    <button type="button" onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 4, border: "none",
      background: "transparent", color: "var(--ink-soft)", fontSize: 11,
      textDecoration: "underline", cursor: "pointer", padding: 0,
    }}>
      {children}
    </button>
  );
}
