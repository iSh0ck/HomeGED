import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Folder, FileText, FilePlus2, LayoutDashboard, ChevronRight, ChevronDown, Bookmark,
         PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { construireArbre } from "../lib/arborescence";
import { t } from "../lib/langue";

export default function Sidebar({
  categories,
  vues = [],
  tableaux = [],
  tableauActif,
  onSelectTableau,
  filtreCategorie,
  vueActive,
  onFiltreCategorie,
  onSelectVue,
  nomFoyer,
}) {
  const arbre = useMemo(() => construireArbre(categories), [categories]);
  // vues regroupées par catégorie de rattachement ; `null` = vues générales
  const vuesParCategorie = useMemo(() => {
    const par = new Map();
    for (const vue of vues) {
      const cle = vue.categorie_id ?? null;
      if (!par.has(cle)) par.set(cle, []);
      par.get(cle).push(vue);
    }
    return par;
  }, [vues]);
  // Les branches sont **repliées par défaut** : une navigation qui s'ouvre tout
  // entière noie l'essentiel dès qu'il y a quelques catégories. On mémorise
  // donc celles que l'utilisateur a ouvertes, et non celles qu'il a fermées.
  const [deplies, setDeplies] = useState(() => new Set());

  function basculerRepli(id) {
    setDeplies((prev) => {
      const suivant = new Set(prev);
      if (suivant.has(id)) suivant.delete(id);
      else suivant.add(id);
      return suivant;
    });
  }

  function deplier(id) {
    setDeplies((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  }

  // Une catégorie choisie ailleurs — depuis un tableau de bord, une vue — doit
  // devenir visible : on ouvre la branche qui y mène.
  useEffect(() => {
    if (filtreCategorie == null) return;
    const parents = new Map(categories.map((c) => [c.id, c.parent_id]));
    const aOuvrir = [];
    let courant = parents.get(filtreCategorie);
    const vus = new Set();
    while (courant != null && !vus.has(courant)) {
      vus.add(courant);
      aOuvrir.push(courant);
      courant = parents.get(courant);
    }
    if (aOuvrir.length) setDeplies((prev) => new Set([...prev, ...aOuvrir]));
  }, [filtreCategorie, categories]);

  const proprietes = { vuesParCategorie, vueActive, onSelectVue,
                       deplies, onBasculerRepli: basculerRepli, onDeplier: deplier };

  const { largeur, repliee, setRepliee, poignee, enCoursDeGlisse } = useLargeurReglable();

  // Tout ce dont la navigation a besoin, rassemblé une fois. La barre dépliée
  // s'en sert ; le rail, lui, n'affiche que des icônes et ouvre un volet par
  // élément survolé.
  const navigation = {
    tableaux, tableauActif, onSelectTableau,
    vuesParCategorie, vueActive, onSelectVue,
    arbre, filtreCategorie, onFiltreCategorie, proprietes,
  };

  // Repliée, la barre devient un rail d'icônes : on gagne la place sans perdre
  // la navigation. Les tableaux de bord et les catégories racines restent
  // atteignables en un clic ; le détail (sous-catégories, vues rattachées)
  // demande de déplier, ce qui est le bon compromis pour 48 px de large.
  if (repliee) {
    return (
      <RailReplie
        tableaux={tableaux}
        tableauActif={tableauActif}
        onSelectTableau={onSelectTableau}
        racines={arbre}
        filtreCategorie={filtreCategorie}
        onFiltreCategorie={onFiltreCategorie}
        vuesGenerales={vuesParCategorie.get(null) || []}
        vueActive={vueActive}
        onSelectVue={onSelectVue}
        onDeplier={() => setRepliee(false)}
      />
    );
  }

  return (
    <aside
      style={{
        position: "relative",
        width: largeur,
        flexShrink: 0,
        borderRight: "1px solid var(--line)",
        background: "var(--bg-panel-alt)",
        display: "flex",
        flexDirection: "column",
        gap: 24,
        padding: "24px 16px",
        overflowY: "auto",
        // `overflow-y: auto` seul suffit à faire passer l'axe horizontal en
        // `auto` : une barre de défilement apparaissait dès qu'un nom de
        // catégorie dépassait d'un pixel. Les libellés se coupent déjà avec des
        // points de suspension — il n'y a rien à atteindre en défilant.
        overflowX: "hidden",
        // Pendant le glissé, la transition ferait traîner la bordure derrière
        // le curseur : on la coupe le temps du geste.
        transition: enCoursDeGlisse ? "none" : "width 120ms",
      }}
      className="scrollbar-thin"
    >
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: -14 }}>
        <BoutonRepli onClick={() => setRepliee(true)} />
      </div>

      <div
        onMouseDown={poignee}
        onDoubleClick={() => poignee(null, true)}
        title={t("Glisser pour redimensionner · double-clic pour la largeur d'origine")}
        style={{
          position: "absolute", top: 0, right: -3, width: 6, height: "100%",
          cursor: "col-resize", zIndex: 5,
        }}
      />

      <div>
        {/* Le nom du foyer prend la tête quand il est réglé (§18.24) : c'est ce
            qui fait qu'une installation appartient à ceux qui l'utilisent. */}
        <h1 style={{ fontSize: 19, overflow: "hidden", textOverflow: "ellipsis" }}>
          {nomFoyer || "HomeGED"}
        </h1>
        <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 2 }}>
          {nomFoyer ? t("HomeGED · registre documentaire") : t("Registre documentaire")}
        </div>
      </div>

      <CorpsNavigation {...navigation} />

    </aside>
  );
}

/**
 * Les trois groupes de la navigation : tableaux de bord, vues générales,
 * arborescence des catégories.
 *
 * Extraits de la barre pour être rendus à deux endroits : la barre dépliée, et
 * le panneau qui s'ouvre au survol quand elle est repliée. Les dupliquer aurait
 * garanti qu'ils divergent au premier changement.
 */
function CorpsNavigation({
  tableaux, tableauActif, onSelectTableau,
  vuesParCategorie, vueActive, onSelectVue,
  arbre, filtreCategorie, onFiltreCategorie, proprietes,
}) {
  const vuesGenerales = vuesParCategorie.get(null) || [];

  return (
    <>
      <div>
        <EnTeteGroupe icon={<LayoutDashboard size={14} />} label={t("Tableaux de bord")} />
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {tableaux.map((tableau) => {
            const actif = String(tableauActif) === String(tableau.id);
            return (
              <button
                key={tableau.id}
                onClick={() => onSelectTableau?.(tableau)}
                title={tableau.description || tableau.nom}
                style={{
                  display: "flex", alignItems: "center", gap: 8, width: "100%",
                  textAlign: "left", border: "none",
                  borderLeft: actif ? "3px solid var(--accent)" : "3px solid transparent",
                  background: actif ? "var(--accent-soft)" : "transparent",
                  color: "var(--ink)", fontWeight: actif ? 600 : 400,
                  padding: "6px 8px 6px 7px", fontSize: 13, borderRadius: 2,
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {tableau.nom}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {vuesGenerales.length > 0 && (
        <div>
          <EnTeteGroupe icon={<Bookmark size={14} />} label={t("Vues")} />
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {vuesGenerales.map((vue) => (
              <LigneVue
                key={vue.id}
                vue={vue}
                niveau={0}
                actif={vueActive === vue.id}
                onSelect={onSelectVue}
              />
            ))}
          </div>
        </div>
      )}

      <div>
        <EnTeteGroupe icon={<Folder size={14} />} label={t("Catégories")} />
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {arbre.length === 0 && <GroupeVide />}
          {arbre.map((noeud) => (
            <NoeudCategorie
              key={noeud.id}
              noeud={noeud}
              niveau={0}
              activeId={filtreCategorie}
              onSelect={onFiltreCategorie}
              {...proprietes}
            />
          ))}
        </div>
      </div>
    </>
  );
}

/**
 * Une catégorie de l'arbre. Une catégorie qui a des enfants se comporte comme
 * une section : elle est repliable, et la sélectionner filtre sur elle **et**
 * ses sous-catégories (le regroupement est fait côté API).
 */
/**
 * Trois natures, trois icônes (§19.1, §22.1) : un dossier organise, un type
 * porte les documents et reçoit les dépôts, une fiche simple porte des documents
 * mais n'en reçoit que glissés à la main. La distinction décide de tout ce qu'on
 * peut faire d'une entrée.
 */
/** @traduit-a-la-lecture */
const NATURE = {
  dossier: { icone: Folder, opacite: 0.55, titre: "dossier : regroupe des types de document" },
  type: { icone: FileText, opacite: 0.45, titre: "type de document" },
  fiche: { icone: FilePlus2, opacite: 0.55,
           titre: "fiche simple : on y glisse les documents à la main" },
};
const natureDe = (noeud) => NATURE[noeud?.nature || "type"] || NATURE.type;
const estDossier = (noeud) => (noeud?.nature || "type") === "dossier";


function NoeudCategorie({
  noeud, niveau, activeId, onSelect,
  vuesParCategorie, vueActive, onSelectVue,
  deplies, onBasculerRepli, onDeplier,
}) {
  const vuesDeLaCategorie = vuesParCategorie?.get(noeud.id) || [];
  const aDesEnfants = noeud.enfants.length > 0;
  // une catégorie qui n'a que des vues se replie aussi : c'est le même besoin
  const depliable = aDesEnfants || vuesDeLaCategorie.length > 0;
  const deplie = deplies.has(noeud.id);
  const isActive = activeId === noeud.id;

  // Un **dossier ne se liste pas, il se déroule** (§22.10).
  //
  // Il rassemble des types différents, dont les colonnes ne se ressemblent pas :
  // « Administratif » affichait donc un tableau où chaque ligne attendait des
  // colonnes que sa voisine n'avait pas. Cliquer dessus déplie, rien de plus —
  // c'est un chemin vers un type, pas une liste.
  //
  // Un dossier vide se déroule aussi, sur rien : il ne porte aucun document en
  // propre — le modèle l'interdit —, et le sélectionner n'aurait montré qu'un
  // tableau vide.
  const estSection = estDossier(noeud) || (niveau === 0 && aDesEnfants);

  return (
    <>
      <div style={{ display: "flex", alignItems: "stretch" }}>
        {depliable ? (
          <button
            onClick={() => onBasculerRepli(noeud.id)}
            aria-label={deplie ? `Replier ${noeud.nom}` : `Déplier ${noeud.nom}`}
            style={{
              border: "none",
              background: "transparent",
              color: "var(--ink-faint)",
              display: "flex",
              alignItems: "center",
              padding: 0,
              marginLeft: 8 + niveau * 12,
              width: 16,
              flexShrink: 0,
            }}
          >
            {deplie ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
        ) : (
          <span style={{ marginLeft: 8 + niveau * 12, width: 16, flexShrink: 0 }} />
        )}

        <button
          onClick={() => {
            if (estSection) return onBasculerRepli(noeud.id);
            // Choisir une catégorie ouvre aussi sa branche : on veut voir ce
            // qu'elle contient au moment où l'on s'y intéresse.
            if (depliable) onDeplier(noeud.id);
            // Recliquer sur la catégorie déjà affichée ne fait rien. Auparavant
            // cela désélectionnait, et l'on se retrouvait sans l'avoir demandé
            // devant tous les documents du foyer.
            if (!isActive) onSelect(noeud.id);
          }}
          aria-expanded={estSection ? deplie : undefined}
          title={`${noeud.nom} — ${t(natureDe(noeud).titre)}`}
          style={{
            flex: 1,
            minWidth: 0,
            display: "flex",
            alignItems: "center",
            border: "none",
            borderLeft: isActive ? "3px solid var(--accent)" : "3px solid transparent",
            background: isActive ? "var(--accent-soft)" : "transparent",
            color: estSection ? "var(--ink-soft)" : "var(--ink)",
            padding: "6px 8px 6px 5px",
            fontSize: 13,
            fontWeight: depliable ? 500 : 400,
            textAlign: "left",
            borderRadius: 2,
          }}
        >
          {/* Dossier ou type de document (§19.1) : la distinction décide de tout
              ce qu'on peut faire d'une entrée — y déposer, la configurer, y
              ranger un document. La lire ici évite d'aller la chercher dans
              l'administration. */}
          {React.createElement(natureDe(noeud).icone, {
            size: 12,
            style: { flexShrink: 0, marginRight: 6, opacity: natureDe(noeud).opacite },
          })}
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {noeud.nom}
          </span>
        </button>
      </div>

      {deplie &&
        vuesDeLaCategorie.map((vue) => (
          <LigneVue
            key={vue.id}
            vue={vue}
            niveau={niveau + 1}
            actif={vueActive === vue.id}
            onSelect={onSelectVue}
          />
        ))}

      {aDesEnfants &&
        deplie &&
        noeud.enfants.map((enfant) => (
          <NoeudCategorie
            key={enfant.id}
            noeud={enfant}
            niveau={niveau + 1}
            activeId={activeId}
            onSelect={onSelect}
            vuesParCategorie={vuesParCategorie}
            vueActive={vueActive}
            onSelectVue={onSelectVue}
            deplies={deplies}
            onBasculerRepli={onBasculerRepli}
            onDeplier={onDeplier}
          />
        ))}
    </>
  );
}

/** Une vue enregistrée : applique ses critères au tableau quand on la choisit. */
/**
 * Une vue enregistrée dans la navigation.
 *
 * Pas de bouton de suppression, même pour un administrateur : détruire une vue
 * est une opération d'administration, elle se fait dans l'écran dédié, où l'on
 * voit ce qu'on supprime et où la confirmation dit ce que cela emporte. Une
 * corbeille au bord d'un élément de navigation invite au geste malheureux —
 * juste à côté du clic qui sert cent fois par jour.
 */
function LigneVue({ vue, niveau, actif, onSelect }) {
  return (
    <div style={{ display: "flex", alignItems: "stretch" }} className="ligne-vue">
      <span style={{ marginLeft: 8 + niveau * 12, width: 16, flexShrink: 0 }} />
      <button
        onClick={() => onSelect?.(vue)}
        title={vue.partagee ? `${vue.nom} (partagée)` : vue.nom}
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          gap: 6,
          border: "none",
          borderLeft: actif ? "3px solid var(--accent)" : "3px solid transparent",
          background: actif ? "var(--accent-soft)" : "transparent",
          color: "var(--ink-soft)",
          padding: "5px 4px 5px 5px",
          fontSize: 12,
          textAlign: "left",
          borderRadius: 2,
        }}
      >
        <Bookmark size={11} style={{ flexShrink: 0 }} />
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {vue.nom}
        </span>
      </button>
    </div>
  );
}

function EnTeteGroupe({ icon, label }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        color: "var(--ink-faint)",
        fontWeight: 600,
        marginBottom: 8,
        paddingLeft: 2,
      }}
    >
      {icon}
      {label}
    </div>
  );
}

function GroupeVide() {
  return (
    <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "4px 10px" }}>
      {t("Aucun pour l'instant")}
    </div>
  );
}

const LARGEUR_DEFAUT = 232;
const LARGEUR_MIN = 170;
const LARGEUR_MAX = 460;
const CLE_LARGEUR = "homeged.sidebar.largeur";
const CLE_REPLI = "homeged.sidebar.repliee";

/**
 * Largeur réglable à la souris et repli complet, retenus d'une visite à l'autre.
 *
 * Les bornes ne sont pas décoratives : en dessous de 170 px les noms de
 * catégorie deviennent illisibles, au-delà de 460 px la barre mange le registre
 * qu'elle sert à filtrer.
 *
 * Le préréglage vit dans `localStorage` — c'est un confort propre à ce
 * navigateur, pas une donnée du foyer : le stocker côté serveur imposerait le
 * choix d'un poste aux autres. Les accès sont protégés, `localStorage` levant
 * une exception en navigation privée sur certains navigateurs.
 */
function useLargeurReglable() {
  const [largeur, setLargeur] = useState(() => lireNombre(CLE_LARGEUR, LARGEUR_DEFAUT));
  const [repliee, setRepliee] = useState(() => lire(CLE_REPLI) === "1");
  const [enCoursDeGlisse, setEnCoursDeGlisse] = useState(false);
  const depart = useRef(null);

  useEffect(() => { ecrire(CLE_LARGEUR, String(largeur)); }, [largeur]);
  useEffect(() => { ecrire(CLE_REPLI, repliee ? "1" : "0"); }, [repliee]);

  const deplacer = useCallback((evenement) => {
    if (!depart.current) return;
    const { x, largeurInitiale } = depart.current;
    const voulue = largeurInitiale + (evenement.clientX - x);
    setLargeur(Math.min(LARGEUR_MAX, Math.max(LARGEUR_MIN, voulue)));
  }, []);

  const relacher = useCallback(() => {
    depart.current = null;
    setEnCoursDeGlisse(false);
    // Rendus au document : sans ça, la sélection de texte resterait désactivée
    // si le bouton était relâché hors de la fenêtre.
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
  }, []);

  useEffect(() => {
    if (!enCoursDeGlisse) return undefined;
    window.addEventListener("mousemove", deplacer);
    window.addEventListener("mouseup", relacher);
    return () => {
      window.removeEventListener("mousemove", deplacer);
      window.removeEventListener("mouseup", relacher);
    };
  }, [enCoursDeGlisse, deplacer, relacher]);

  const poignee = useCallback((evenement, reinitialiser = false) => {
    if (reinitialiser) {
      setLargeur(LARGEUR_DEFAUT);
      return;
    }
    evenement.preventDefault();
    depart.current = { x: evenement.clientX, largeurInitiale: largeur };
    setEnCoursDeGlisse(true);
    // Pendant le glissé, la sélection de texte transformerait le geste en
    // surlignage de la moitié de la page.
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
  }, [largeur]);

  return { largeur, repliee, setRepliee, poignee, enCoursDeGlisse };
}

function lire(cle) {
  try {
    return window.localStorage.getItem(cle);
  } catch {
    return null;   // navigation privée, stockage refusé : on retombe sur les valeurs par défaut
  }
}

function lireNombre(cle, defaut) {
  const brut = Number(lire(cle));
  return Number.isFinite(brut) && brut >= LARGEUR_MIN && brut <= LARGEUR_MAX ? brut : defaut;
}

function ecrire(cle, valeur) {
  try {
    window.localStorage.setItem(cle, valeur);
  } catch {
    /* rien à faire : le réglage vaudra pour cette visite seulement */
  }
}

function BoutonRepli({ repliee, onClick }) {
  const Icone = repliee ? PanelLeftOpen : PanelLeftClose;
  const intitule = repliee ? t("Déplier la navigation") : t("Replier la navigation");
  return (
    <button
      onClick={onClick}
      aria-label={intitule}
      title={intitule}
      style={{
        display: "flex", border: "none", background: "transparent",
        color: "var(--ink-faint)", padding: 3, borderRadius: "var(--radius)",
        cursor: "pointer",
      }}
    >
      <Icone size={15} />
    </button>
  );
}

/**
 * Barre latérale repliée : un rail d'icônes.
 *
 * Le repli servait à gagner de la place, il faisait perdre toute la navigation —
 * un bandeau de 34 px qui ne savait que se rouvrir. Le rail garde les repères
 * qui comptent : les tableaux de bord, les vues générales, les catégories
 * racines. Un clic filtre directement, **sans déplier** : on a replié pour
 * gagner de la place, la lui reprendre à chaque clic serait absurde.
 *
 * Ce qui n'y tient pas — sous-catégories, vues rattachées — reste accessible en
 * dépliant, et l'icône d'en-tête de chaque groupe sert justement à ça.
 *
 * Chaque icône porte son intitulé en `title` (infobulle) **et** en `aria-label` :
 * une navigation réduite à des symboles doit rester lisible au lecteur d'écran.
 */
function RailReplie({
  tableaux, tableauActif, onSelectTableau,
  racines, filtreCategorie, onFiltreCategorie,
  vuesGenerales, vueActive, onSelectVue,
  onDeplier,
}) {
  // Un seul volet ouvert à la fois : celui de l'icône survolée. Il porte son
  // ancrage (le rectangle du bouton) pour se poser en face d'elle.
  const [volet, setVolet] = useState(null);
  const minuterie = useRef(null);

  const annuler = () => {
    if (minuterie.current) { clearTimeout(minuterie.current); minuterie.current = null; }
  };
  // Fermeture différée seulement : passer d'une icône à l'autre doit être
  // instantané, sinon la lecture du rail devient poussive.
  const survoler = (contenu, element) => {
    annuler();
    setVolet({ ...contenu, haut: element.getBoundingClientRect().top });
  };
  const quitter = () => {
    annuler();
    minuterie.current = setTimeout(() => setVolet(null), 180);
  };
  useEffect(() => annuler, []);

  return (
    <aside
      className="scrollbar-thin"
      onMouseLeave={quitter}
      style={{
        position: "relative",
        width: 48, flexShrink: 0, borderRight: "1px solid var(--line)",
        background: "var(--bg-panel-alt)", display: "flex", flexDirection: "column",
        alignItems: "center", gap: 4, padding: "16px 0", overflowY: "auto",
      }}
    >
      <BoutonRepli repliee onClick={onDeplier} />

      {tableaux.length > 0 && (
        <>
          <Separateur />
          {tableaux.map((tableau) => (
            <IconeRail
              key={tableau.id}
              intitule={tableau.nom}
              actif={String(tableauActif) === String(tableau.id)}
              onClick={() => onSelectTableau?.(tableau)}
              onSurvol={(element) => survoler({ titre: tableau.nom,
                                                detail: tableau.description }, element)}
              onSortie={quitter}
            >
              <LayoutDashboard size={16} />
            </IconeRail>
          ))}
        </>
      )}

      {vuesGenerales.length > 0 && (
        <>
          <Separateur />
          {vuesGenerales.map((vue) => (
            <IconeRail
              key={vue.id}
              intitule={`Vue : ${vue.nom}`}
              actif={vueActive === vue.id}
              onClick={() => onSelectVue?.(vue)}
              onSurvol={(element) => survoler({ titre: vue.nom, detail: t("Vue enregistrée") }, element)}
              onSortie={quitter}
            >
              <Bookmark size={16} />
            </IconeRail>
          ))}
        </>
      )}

      <Separateur />
      {racines.length === 0 ? (
        <IconeRail
          intitule={t("Aucune catégorie — déplier la navigation")}
          onClick={onDeplier}
          onSurvol={(element) => survoler({ titre: t("Aucune catégorie") }, element)}
          onSortie={quitter}
        >
          <Folder size={16} />
        </IconeRail>
      ) : (
        racines.map((noeud) => (
          <IconeRail
            key={noeud.id}
            intitule={noeud.nom}
            actif={filtreCategorie === noeud.id}
            // Même règle que dans la barre dépliée : une racine qui regroupe des
            // sous-catégories n'est pas un filtre. Cliquer dessus ouvre son
            // volet — utile au doigt, là où le survol n'existe pas.
            onClick={(element) => (noeud.enfants.length
              ? survoler({ titre: noeud.nom, enfants: noeud.enfants,
                           onChoisir: (id) => { onFiltreCategorie?.(id); setVolet(null); } }, element)
              : filtreCategorie !== noeud.id && onFiltreCategorie?.(noeud.id))}
            onSurvol={(element) => survoler({
              titre: noeud.nom,
              enfants: noeud.enfants,
              onChoisir: (id) => { onFiltreCategorie?.(id); setVolet(null); },
            }, element)}
            onSortie={quitter}
          >
            <InitialesCategorie nom={noeud.nom} />
          </IconeRail>
        ))
      )}

      {volet && (
        <VoletRail
          {...volet}
          actifId={filtreCategorie}
          onEntrer={annuler}
          onSortir={quitter}
        />
      )}
    </aside>
  );
}

/**
 * Volet ouvert en face de l'icône survolée.
 *
 * Il s'ancre sur le bouton, pas sur le haut de l'écran : on lit à hauteur de
 * regard, sans quitter des yeux ce qu'on vise. Il ne montre que ce que cette
 * icône contient — son nom, et les sous-catégories quand il y en a. Ouvrir la
 * navigation entière obligeait à s'y rendre pour trouver la ligne
 * correspondante ; c'est l'inverse de ce qu'on attend d'un survol.
 *
 * `position: fixed` parce que le rail défile : une position calculée dans le
 * flux glisserait avec lui pendant que le curseur, lui, ne bouge pas.
 */
function VoletRail({ titre, detail, enfants = [], haut, actifId, onChoisir, onEntrer, onSortir }) {
  const hauteurEstimee = 44 + enfants.length * 26;
  const debordement = Math.max(0, haut + hauteurEstimee + 12 - window.innerHeight);

  return (
    <div
      role="tooltip"
      className="apparition"
      onMouseEnter={onEntrer}
      onMouseLeave={onSortir}
      style={{
        position: "fixed", left: 50, top: Math.max(8, haut - 6 - debordement),
        zIndex: 70, minWidth: 168, maxWidth: 260,
        background: "var(--bg-panel)", border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        boxShadow: "0 12px 30px -16px rgba(34, 40, 31, 0.5)",
        padding: enfants.length ? "8px 6px" : "8px 11px",
        animationDuration: "110ms",
      }}
    >
      <div style={{
        fontSize: 12.5, fontWeight: 600, color: "var(--ink)",
        padding: enfants.length ? "2px 6px 6px" : 0,
      }}>
        {titre}
      </div>

      {detail && (
        <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 3 }}>{detail}</div>
      )}

      {enfants.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {enfants.map((enfant) => (
            <button
              key={enfant.id}
              onClick={() => onChoisir?.(enfant.id)}
              style={{
                display: "flex", alignItems: "center", gap: 6, width: "100%",
                border: "none", borderRadius: "var(--radius)", padding: "5px 7px",
                background: actifId === enfant.id ? "var(--accent-soft)" : "transparent",
                color: "var(--ink)", fontSize: 12, textAlign: "left", cursor: "pointer",
              }}
            >
              <ChevronRight size={11} color="var(--ink-faint)" style={{ flexShrink: 0 }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {enfant.nom}
              </span>
              {enfant.enfants?.length > 0 && (
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--ink-faint)" }}>
                  {enfant.enfants.length}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Les deux premières lettres de la catégorie, faute de mieux : une pile de
 * dossiers identiques ne se distingue pas, et le projet n'a pas d'icône par
 * catégorie. L'infobulle porte le nom complet.
 */
function InitialesCategorie({ nom }) {
  return (
    <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.02em" }}>
      {(nom || "?").trim().slice(0, 2).toUpperCase()}
    </span>
  );
}

function IconeRail({ children, intitule, actif, onClick, onSurvol, onSortie }) {
  return (
    <button
      onClick={(e) => onClick?.(e.currentTarget)}
      onMouseEnter={(e) => onSurvol?.(e.currentTarget)}
      onMouseLeave={onSortie}
      onFocus={(e) => onSurvol?.(e.currentTarget)}
      onBlur={onSortie}
      title={intitule}
      aria-label={intitule}
      aria-current={actif ? "true" : undefined}
      style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        width: 32, height: 32, flexShrink: 0,
        border: "none", borderRadius: "var(--radius)",
        background: actif ? "var(--accent-soft)" : "transparent",
        color: actif ? "var(--accent)" : "var(--ink-soft)",
        cursor: "pointer", transition: "background 140ms, color 140ms",
      }}
    >
      {children}
    </button>
  );
}

function Separateur() {
  return <div style={{ width: 20, height: 1, background: "var(--line)", margin: "6px 0" }} />;
}
