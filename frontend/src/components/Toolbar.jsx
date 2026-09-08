import React, { useEffect, useRef, useState } from "react";
import Liste from "./champs/Liste.jsx";
import { AlertTriangle, BookmarkPlus, ChevronDown, FilterX, LogOut, Menu, PackageOpen, RefreshCw, Search, ShieldCheck, UserCog } from "lucide-react";
import { t } from "../lib/langue";

export default function Toolbar({
  query,
  onQueryChange,
  // Où chercher (§21.2), à la manière d'un client de messagerie : le mot ne dit
  // pas dans quel classement il tombe, c'est à celui qui cherche de le borner —
  // ou de ne pas le borner du tout, ce qui est le défaut.
  perimetre = "tout",
  onPerimetreChange,
  perimetresPossibles = [],
  total,
  afficherTotal = true,
  nbFiltres = 0,
  onEffacerFiltres,
  onEnregistrerVue,
  onExporter,
  user,
  onOuvrirCompte,
  onLogout,
  onOuvrirAdmin,
  nbAAnalyser = 0,
  onOuvrirAnalyse,
  // Le bouton de corbeille, rendu par le parent : il ne s'affiche que s'il y a
  // quelque chose dedans (§21.1).
  corbeille = null,
  onActualiser,
  actualisation = false,
  // Téléphone et tablette (§22.52) : la barre s'enroule et la navigation
  // s'ouvre par un bouton, la barre latérale étant devenue un tiroir.
  compact = false,
  onOuvrirNavigation,
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        // Sur un écran étroit, la barre passe à la ligne plutôt que de comprimer
        // la recherche jusqu'à l'illisible.
        flexWrap: compact ? "wrap" : "nowrap",
        gap: compact ? 8 : 16,
        padding: compact ? "10px 12px" : "16px 24px",
        borderBottom: "1px solid var(--line)",
        background: "var(--bg-panel)",
      }}
    >
      {onOuvrirNavigation && (
        <button
          onClick={onOuvrirNavigation}
          aria-label={t("Ouvrir la navigation")}
          title={t("Ouvrir la navigation")}
          style={{ border: "1px solid var(--line)", background: "var(--bg-panel-alt)",
                   color: "var(--ink)", borderRadius: "var(--radius)",
                   padding: "7px 9px", cursor: "pointer", flexShrink: 0 }}
        >
          <Menu size={16} />
        </button>
      )}
      <div
        style={{
          flex: 1,
          minWidth: compact ? 160 : 0,
          maxWidth: compact ? "none" : 420,
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: "var(--bg-panel-alt)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius)",
          padding: "7px 10px",
        }}
      >
        <Search size={15} color="var(--ink-faint)" />
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={t("Rechercher un document, un émetteur, un véhicule…")}
          aria-label={t("Rechercher")}
          style={{
            border: "none",
            outline: "none",
            background: "transparent",
            fontSize: 13,
            width: "100%",
            color: "var(--ink)",
          }}
        />
        {/* La liste du projet, comme partout ailleurs : un `<select>` natif ne
            se met pas en forme, et celui-ci trônait au milieu de la barre de
            recherche (voir `components/champs/Liste.jsx`). */}
        {perimetresPossibles.length > 1 && (
          <div style={{ width: 170, borderLeft: "1px solid var(--line)", paddingLeft: 6 }}>
            <Liste
              valeur={perimetre}
              compact
              souligne
              ariaLabel={t("Où chercher")}
              options={perimetresPossibles.map((p) => ({ valeur: p.cle, libelle: p.libelle }))}
              onChange={(v) => onPerimetreChange?.(v)}
            />
          </div>
        )}
      </div>

      {/* Relire la vue en cours. Le registre se recharge tout seul quand on
          change un critère, mais pas quand c'est le monde extérieur qui bouge :
          un dépôt traité par le serveur de travaux, une fiche corrigée depuis un
          autre poste. */}
      {onActualiser && (
        <button
          onClick={onActualiser}
          disabled={actualisation}
          title={t("Actualiser la vue en cours")}
          aria-label={t("Actualiser la vue en cours")}
          style={{
            display: "flex", alignItems: "center", gap: 6,
            background: "transparent", color: "var(--ink-soft)",
            border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
            padding: "6px 10px", fontSize: 12.5,
          }}
        >
          <RefreshCw
            size={14}
            className={actualisation ? "rotation" : undefined}
          />
          Actualiser
        </button>
      )}

      {afficherTotal && (
        <div style={{ fontSize: 12, color: "var(--ink-faint)" }} className="tabular">
          {total} document{total > 1 ? "s" : ""}
        </div>
      )}

      {nbFiltres > 0 && (
        <button
          onClick={onEffacerFiltres}
          title={t("Retirer tous les filtres de colonne")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            border: "1px solid var(--accent)",
            borderRadius: 12,
            padding: "3px 10px",
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          <FilterX size={12} />
          {nbFiltres} filtre{nbFiltres > 1 ? "s" : ""} — tout effacer
        </button>
      )}

      {/* Enregistrer une vue est réservé aux administrateurs : une vue est un
          élément de navigation partagé par le foyer, pas un marque-page
          personnel. Le contrôle est aussi côté API — masquer un bouton ne
          protège de rien. */}
      {nbFiltres > 0 && user?.est_admin && (
        <button
          onClick={onEnregistrerVue}
          title={t("Mémoriser ces filtres comme une vue réutilisable")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            background: "transparent",
            color: "var(--ink-soft)",
            border: "1px solid var(--line-strong)",
            borderRadius: 12,
            padding: "3px 10px",
            fontSize: 11,
            fontWeight: 500,
          }}
        >
          <BookmarkPlus size={12} />
          Enregistrer la vue
        </button>
      )}

      {/* Sortir une sélection rangée comme on la veut (§21.13), pour la donner
          au comptable ou à l'assurance. Droit à part de l'export de secours :
          les confondre obligerait à donner la porte de sortie définitive pour
          permettre un geste courant. */}
      {/* Le bouton suit le **droit**, et non la qualité d'administrateur
          (§22.82). Sortir une sélection, c'est faire quitter des documents du
          foyer : `exporter_selection` sert justement à le confier à un compte
          précis. Il ne le faisait qu'à moitié — l'API le vérifiait, l'écran
          regardait `est_admin`, et l'on pouvait accorder le droit à quelqu'un
          qui ne voyait jamais le bouton. Un administrateur porte tous les droits
          généraux d'office : rien ne change pour lui. */}
      {onExporter && porte(user, "exporter_selection") && (
        <button
          onClick={onExporter}
          title={t("Sortir ces documents dans une archive rangée selon un modèle")}
          style={{
            display: "flex", alignItems: "center", gap: 5, background: "transparent",
            color: "var(--ink-soft)", border: "1px solid var(--line-strong)",
            borderRadius: 12, padding: "3px 10px", fontSize: 11, fontWeight: 500,
          }}
        >
          <PackageOpen size={12} />
          Exporter
        </button>
      )}

      <div style={{ flex: 1 }} />

      {nbAAnalyser > 0 && (
        <button
          onClick={onOuvrirAnalyse}
          title={t("Documents auxquels il manque un champ, et fichiers dont le type reste à dire")}
          style={{
            display: "flex", alignItems: "center", gap: 6,
            background: "var(--amber-soft)", color: "var(--amber)",
            border: "1px solid var(--amber)", borderRadius: "var(--radius)",
            padding: "7px 12px", fontSize: 13, fontWeight: 600,
          }}
        >
          <AlertTriangle size={15} />
          {nbAAnalyser} à reprendre
        </button>
      )}

      {corbeille}

      {user?.est_admin && (
        <button
          onClick={onOuvrirAdmin}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            background: "transparent",
            color: "var(--accent)",
            border: "1px solid var(--accent)",
            borderRadius: "var(--radius)",
            padding: "7px 12px",
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <ShieldCheck size={15} />
          Administration
        </button>
      )}

      <MenuCompte user={user} onOuvrirCompte={onOuvrirCompte} onLogout={onLogout} />
    </div>
  );
}

/**
 * Menu du compte connecté.
 *
 * Le nom et la déconnexion étaient deux éléments juxtaposés, sans lien visible
 * entre eux : on ne devinait pas que le nom cliquable menait au profil, et
 * l'icône de sortie voisinait avec des actions qui n'ont rien à voir. Un seul
 * point d'entrée, qui se déplie, dit mieux ce qu'il contient.
 *
 * Trois façons de le refermer, parce qu'un menu qui reste ouvert derrière ce
 * qu'on fait ensuite est plus gênant que pas de menu du tout : un clic
 * ailleurs, la touche Échap, ou le choix d'une entrée.
 */
/**
 * Ce compte porte-t-il ce droit général ? (§22.82)
 *
 * `/moi` rend la liste, administrateur compris — la fonction n'a donc pas à
 * traiter ce cas à part, et un bouton qui suit le droit suit du même coup ce
 * que l'API autorisera.
 */
function porte(user, droit) {
  return (user?.droits || []).includes(droit);
}

function MenuCompte({ user, onOuvrirCompte, onLogout }) {
  const [ouvert, setOuvert] = useState(false);
  const zone = useRef(null);

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

  const choisir = (action) => { setOuvert(false); action(); };

  return (
    <div ref={zone} style={{ position: "relative", marginLeft: 4 }}>
      <button
        onClick={() => setOuvert(!ouvert)}
        aria-haspopup="menu"
        aria-expanded={ouvert}
        style={{
          display: "flex", alignItems: "center", gap: 7,
          border: "1px solid " + (ouvert ? "var(--line-strong)" : "transparent"),
          background: ouvert ? "var(--bg-panel-alt)" : "transparent",
          color: "var(--ink-soft)", borderRadius: "var(--radius)",
          padding: "6px 9px", fontSize: 12.5, cursor: "pointer",
          transition: "background 140ms, border-color 140ms",
        }}
      >
        <Pastille nom={user?.nom} />
        {user?.nom}
        <ChevronDown size={13} style={{
          transition: "transform 160ms",
          transform: ouvert ? "rotate(180deg)" : "none",
        }} />
      </button>

      {ouvert && (
        <div
          role="menu"
          className="apparition"
          style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 40,
            minWidth: 210, background: "var(--bg-panel)",
            border: "1px solid var(--line)", borderRadius: "var(--radius)",
            boxShadow: "0 12px 30px -14px rgba(34, 40, 31, 0.4)",
            padding: 5, animationDuration: "140ms",
          }}
        >
          <div style={{ padding: "7px 9px 9px" }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>{user?.nom}</div>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}>{user?.email}</div>
            {user?.est_admin && (
              <div style={{ fontSize: 10.5, color: "var(--accent)", marginTop: 3 }}>{t("Administrateur")}</div>
            )}
          </div>
          <div style={{ height: 1, background: "var(--line)", margin: "0 -5px 5px" }} />

          <EntreeMenu icone={UserCog} onClick={() => choisir(onOuvrirCompte)}>
            Mon compte
          </EntreeMenu>
          <EntreeMenu icone={LogOut} ton="brick" onClick={() => choisir(onLogout)}>
            Se déconnecter
          </EntreeMenu>
        </div>
      )}
    </div>
  );
}

function EntreeMenu({ icone: Icone, children, onClick, ton }) {
  const [survol, setSurvol] = useState(false);
  const couleur = ton === "brick" ? "var(--brick)" : "var(--ink)";
  return (
    <button
      role="menuitem"
      onClick={onClick}
      onMouseEnter={() => setSurvol(true)}
      onMouseLeave={() => setSurvol(false)}
      style={{
        display: "flex", alignItems: "center", gap: 8, width: "100%",
        border: "none", background: survol ? "var(--bg-panel-alt)" : "transparent",
        color: couleur, borderRadius: "var(--radius)", padding: "7px 9px",
        fontSize: 12.5, textAlign: "left", cursor: "pointer",
      }}
    >
      <Icone size={14} />
      {children}
    </button>
  );
}

/** Initiales du compte : un repère plus rapide à trouver qu'un nom en petit. */
function Pastille({ nom }) {
  const initiales = (nom || "?")
    .split(/\s+/).slice(0, 2).map((mot) => mot[0]).join("").toUpperCase();
  return (
    <span style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      width: 22, height: 22, borderRadius: "50%",
      background: "var(--accent-soft)", color: "var(--accent)",
      fontSize: 10.5, fontWeight: 700,
    }}>
      {initiales}
    </span>
  );
}
