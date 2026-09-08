import React, { useEffect, useState } from "react";
import { ArrowLeft, Bookmark, Zap, Columns3, Database, DatabaseBackup, Gauge, SlidersHorizontal, FolderTree, Inbox, LayoutDashboard, ListChecks, PackageOpen, ScanText, ScrollText, Server, ShieldAlert, ShieldCheck, Terminal, Trash2, Users } from "lucide-react";
import { adminApi } from "../api";
import CategoriesAdmin from "./admin/CategoriesAdmin.jsx";
import RulesAdmin from "./admin/RulesAdmin.jsx";
import AutomatisationsAdmin from "./admin/AutomatisationsAdmin.jsx";
import UsersAdmin from "./admin/UsersAdmin.jsx";
import RolesAdmin from "./admin/RolesAdmin.jsx";
import ConnexionsAdmin from "./admin/ConnexionsAdmin.jsx";
import VuesAdmin from "./admin/VuesAdmin.jsx";
import TableauxAdmin from "./admin/TableauxAdmin.jsx";
import ChampsRequisAdmin from "./admin/ChampsRequisAdmin.jsx";
import ColonnesAdmin from "./admin/ColonnesAdmin.jsx";
import SupervisionAdmin from "./admin/SupervisionAdmin.jsx";
import ReglagesAdmin from "./admin/ReglagesAdmin.jsx";
import ConfigurationAdmin from "./admin/ConfigurationAdmin.jsx";
import JobsAdmin from "./admin/JobsAdmin.jsx";
import JournalAdmin from "./admin/JournalAdmin.jsx";
import BaseAdmin from "./admin/BaseAdmin.jsx";
import CorbeilleAdmin from "./admin/CorbeilleAdmin.jsx";
import IntegriteAdmin from "./admin/IntegriteAdmin.jsx";
import MontageAdmin from "./admin/MontageAdmin.jsx";
import ScriptsAdmin from "./admin/ScriptsAdmin.jsx";
import ExportAdmin from "./admin/ExportAdmin.jsx";
import DepotsAdmin from "./admin/DepotsAdmin.jsx";
import SauvegardeAdmin from "./admin/SauvegardeAdmin.jsx";
import { t } from "../lib/langue";
import { useEcran } from "../lib/ecran";

/**
 * Écrans d'administration, regroupés par question traitée plutôt qu'alignés
 * les uns après les autres : à onze entrées, une simple rangée d'onglets ne
 * dit plus rien de ce qu'on cherche.
 *
 * Chaque groupe répond à une question :
 *   Classement    — comment les documents sont rangés et retrouvés
 *   Extraction    — ce qu'on lit dans les documents, et ce qu'on en exige
 *   Accès         — qui voit et modifie quoi
 *   Exploitation  — ce qui se passe côté serveur, et ce qui a été fait
 *   Données       — les tables de référence du foyer
 *
 * `large` signale les écrans qui ont besoin de **toute** la largeur — une grille
 * de table, une liste de travaux, un journal. Les autres ne sont pas des
 * formulaires pour autant : ce sont presque tous des tableaux de cinq ou six
 * colonnes, et 780 px les serrait jusqu'à couper les intitulés (§22.31). Ils
 * tiennent désormais dans une colonne large, mais bornée : une ligne de texte
 * qui traverse un écran de 27 pouces ne se lit plus, elle se balaie.
 */

// Deux largeurs, et une seule raison de les distinguer : ce qui doit montrer
// beaucoup de colonnes prend l'écran, le reste s'arrête là où une ligne cesse
// d'être lisible.
const LARGEUR_PLEINE = 1400;
const LARGEUR_COURANTE = 1080;
const GROUPES = () => [
  {
    titre: "Classement",
    description: t("Comment les documents sont rangés, et comment on les retrouve."),
    entrees: [
      // Les catégories d'abord : on crée un type avant de l'assembler, et
      // l'ordre de la liste doit suivre celui des gestes.
      { id: "categories", label: t("Catégories"), icone: FolderTree,
        resume: t("Arborescence de classement et regex de rangement automatique.") },
      { id: "montage", label: t("Assembler un type"), icone: ListChecks, large: true,
        resume: t("Tout ce qui décrit un type, dans l'ordre : champs, colonnes, règles.") },
      { id: "colonnes", label: t("Colonnes des tableaux"), icone: Columns3, large: true,
        resume: t("Ce que le tableau montre, catégorie par catégorie.") },
      { id: "vues", label: t("Vues enregistrées"), icone: Bookmark,
        resume: t("Recherches mémorisées, proposées dans la navigation.") },
      { id: "tableaux", label: t("Tableaux de bord"), icone: LayoutDashboard, large: true,
        resume: t("Composer des tableaux d'indicateurs : totaux, répartitions, évolutions.") },
    ],
  },
  {
    titre: "Extraction",
    description: t("Ce que l'on lit dans les documents, et ce que l'on exige d'eux."),
    entrees: [
      { id: "regles", label: t("Règles d'extraction"), icone: ScanText,
        resume: t("Expressions régulières qui remplissent automatiquement les champs.") },
      { id: "automatisations", label: "Automatisations", icone: Zap, large: true,
        resume: t("Quand un document arrive et que…, alors… — réglé ici, pas dans le code.") },
      { id: "champs-requis", label: t("Champs attendus"), icone: ListChecks,
        resume: t("Ce qu'une catégorie exige d'un document pour le considérer complet.") },
    ],
  },
  {
    titre: t("Accès"),
    description: t("Qui peut voir et modifier quoi."),
    entrees: [
      { id: "utilisateurs", label: "Utilisateurs", icone: Users,
        resume: t("Comptes du foyer, mots de passe et rôles.") },
      { id: "roles", label: t("Rôles & droits"), icone: ShieldCheck,
        resume: t("Droits de consultation et de modification, catégorie par catégorie.") },
      { id: "connexions", label: t("Tentatives de connexion"), icone: ShieldAlert, large: true,
        resume: t("Sources verrouillées après trop d'échecs, et déblocage.") },
    ],
  },
  {
    titre: "Exploitation",
    description: t("Ce qui se passe côté serveur, et ce qui a été fait."),
    entrees: [
      { id: "supervision", label: "Supervision", icone: Gauge, large: true,
        resume: t("Disque, mémoire, processeur, file de traitements — l'état de la machine.") },
      { id: "jobs", label: t("Serveur de travaux"), icone: Server, large: true,
        resume: t("Suivi des traitements, diagnostic des échecs et relances.") },
      { id: "depots", label: t("Dépôt"), icone: Inbox, large: true,
        resume: t("Ce qui traîne dans ocr_wait sans y avoir sa place.") },
      { id: "corbeille", label: "Corbeille", icone: Trash2,
        resume: t("Documents supprimés et fichiers écartés, récupérables tant qu'on ne les détruit pas.") },
      { id: "integrite", label: t("Intégrité des archives"), icone: ShieldCheck,
        resume: t("Les fichiers stockés correspondent-ils encore à ce qu'on y a mis ?") },
      { id: "journal", label: t("Journal d'audit"), icone: ScrollText, large: true,
        resume: t("Trace des actions importantes. Consultation seule.") },
      { id: "sauvegarde", label: "Sauvegarde", icone: DatabaseBackup, large: true,
        resume: t("La copie de secours : quand elle a eu lieu, ce qu'elle contient, et en déclencher une.") },
      { id: "export", etroit: true, label: t("Export de l'archive"), icone: PackageOpen,
        resume: t("Sortir tous les documents en .zip, rangés selon leur classement.") },
    ],
  },
  {
    titre: t("Données"),
    description: t("Les tables de référence du foyer : émetteurs, véhicules, personnes…"),
    entrees: [
      { id: "configuration", etroit: true, label: t("Configuration du foyer"), icone: PackageOpen,
        resume: t("Emporter son classement, en reprendre un, partir d'un modèle.") },
      { id: "reglages", etroit: true, label: t("Réglages généraux"), icone: SlidersHorizontal,
        resume: t("Fuseau horaire et présentation, réglables sans toucher au serveur.") },
      { id: "base", label: t("Base de données"), icone: Database, large: true,
        resume: t("Explorer les tables, et gérer vos données de référence — dont les émetteurs.") },
      { id: "scripts", label: t("Scripts (mode développeur)"), icone: Terminal,
        resume: t("La porte de sortie, sous condition : ce que l'écran ne prévoit pas.") },
    ],
  },
];

const COMPOSANTS = {
  categories: CategoriesAdmin,
  vues: VuesAdmin,
  tableaux: TableauxAdmin,
  regles: RulesAdmin,
  automatisations: AutomatisationsAdmin,
  "champs-requis": ChampsRequisAdmin,
  colonnes: ColonnesAdmin,
  supervision: SupervisionAdmin,
  reglages: ReglagesAdmin,
  configuration: ConfigurationAdmin,
  utilisateurs: UsersAdmin,
  roles: RolesAdmin,
  connexions: ConnexionsAdmin,
  jobs: JobsAdmin,
  corbeille: CorbeilleAdmin,
  integrite: IntegriteAdmin,
  montage: MontageAdmin,
  scripts: ScriptsAdmin,
  journal: JournalAdmin,
  export: ExportAdmin,
  depots: DepotsAdmin,
  base: BaseAdmin,
  sauvegarde: SauvegardeAdmin,
};

const TOUTES_LES_ENTREES = GROUPES().flatMap((g) => g.entrees.map((e) => ({ ...e, groupe: g.titre })));

export default function AdminPage({ onRetour, destination = "registre", onOuvrirDocument }) {
  const [entreeId, setEntreeId] = useState("categories");
  // Téléphone et tablette (§22.52) : le menu et l'écran ne tiennent pas côte à
  // côte. On montre l'un **ou** l'autre — le menu d'abord, puis l'écran choisi,
  // avec un retour vers le menu. C'est la navigation d'un téléphone, et elle
  // évite de comprimer une liste de vingt-cinq entrées dans une colonne de
  // cent pixels.
  const ecran = useEcran();
  const [menuVisible, setMenuVisible] = useState(true);
  // Ce qu'un écran passe au suivant : le type sur lequel on travaillait, quand
  // l'assemblage renvoie aux règles d'extraction (§22.20).
  const [contexte, setContexte] = useState(null);
  // Le compte des emplacements non valides (§19.5), affiché dans la navigation :
  // sans lui, cet écran ne serait consulté qu'après coup — c'est-à-dire une fois
  // qu'on cherche déjà un document qui manque.
  const [anomalies, setAnomalies] = useState(0);

  useEffect(() => {
    adminApi.anomaliesDepot()
      .then((reponse) => setAnomalies((reponse.entrees || []).length))
      .catch(() => {});
  }, [entreeId]);
  const entree = TOUTES_LES_ENTREES.find((e) => e.id === entreeId) ?? TOUTES_LES_ENTREES[0];
  const Composant = COMPOSANTS[entree.id];

  return (
    <div style={{ display: ecran.compact ? "block" : "flex", height: "100dvh",
                  overflow: ecran.compact ? "auto" : undefined,
                  background: "var(--bg-app)" }}>
      <nav
        style={{
          width: ecran.compact ? "100%" : 250,
          flexShrink: 0,
          display: ecran.compact && !menuVisible ? "none" : "flex",
          borderRight: ecran.compact ? "none" : "1px solid var(--line)",
          borderBottom: ecran.compact ? "1px solid var(--line)" : "none",
          background: "var(--bg-panel-alt)",
          flexDirection: "column",
          overflowY: "auto",
        }}
        className="scrollbar-thin"
      >
        <div style={{ padding: "20px 16px 14px" }}>
          <button
            onClick={onRetour}
            style={{
              display: "flex", alignItems: "center", gap: 6, border: "none",
              background: "transparent", color: "var(--ink-soft)", fontSize: 12, padding: 0,
            }}
          >
            <ArrowLeft size={14} />
            {destination === "registre" ? t("Retour au registre") : t("Retour au tableau de bord")}
          </button>
          <h1 style={{ fontSize: 18, marginTop: 12 }}>{t("Administration")}</h1>
        </div>

        <div style={{ padding: "0 10px 24px", display: "flex", flexDirection: "column", gap: 18 }}>
          {GROUPES().map((groupe) => (
            <div key={t(groupe.titre)}>
              <div
                style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
                  textTransform: "uppercase", color: "var(--ink-faint)",
                  padding: "0 8px 6px",
                }}
              >
                {t(groupe.titre)}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {groupe.entrees.map((e) => {
                  const Icone = e.icone;
                  const actif = e.id === entreeId;
                  return (
                    <button
                      key={e.id}
                      onClick={() => { setEntreeId(e.id); setMenuVisible(false); }}
                      title={t(e.resume)}
                      style={{
                        display: "flex", alignItems: "center", gap: 8, width: "100%",
                        textAlign: "left", border: "none",
                        borderLeft: actif ? "3px solid var(--accent)" : "3px solid transparent",
                        background: actif ? "var(--accent-soft)" : "transparent",
                        color: actif ? "var(--ink)" : "var(--ink-soft)",
                        fontWeight: actif ? 600 : 400,
                        padding: "7px 8px 7px 6px", fontSize: 13, borderRadius: 2,
                      }}
                    >
                      <Icone size={14} style={{ flexShrink: 0, opacity: actif ? 1 : 0.75 }} />
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {e.label}
                      </span>
                      {e.id === "depots" && anomalies > 0 && (
                        <span
                          title={`${anomalies} emplacement(s) non valide(s)`}
                          style={{
                            marginLeft: "auto", background: "var(--amber-soft)",
                            color: "var(--amber)", fontSize: 10.5, fontWeight: 700,
                            borderRadius: 9, padding: "1px 6px",
                          }}
                        >
                          {anomalies}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </nav>

      <div style={{ flex: 1, display: ecran.compact && menuVisible ? "none" : "flex",
                    flexDirection: "column", minWidth: 0 }}>
        <header
          style={{
            padding: ecran.compact ? "12px 14px" : "18px 28px",
            borderBottom: "1px solid var(--line)",
            background: "var(--bg-panel)",
          }}
        >
          {/* Sur téléphone, le retour au menu prend la place du menu lui-même :
              on ne peut pas montrer les deux (§22.52). */}
          {ecran.compact && (
            <button
              onClick={() => setMenuVisible(true)}
              style={{ display: "flex", alignItems: "center", gap: 6, border: "none",
                       background: "transparent", color: "var(--ink-soft)",
                       fontSize: 12, padding: 0, marginBottom: 6 }}
            >
              <ArrowLeft size={14} />
              {t("Toutes les rubriques")}
            </button>
          )}
          <div style={{ fontSize: 11, color: "var(--ink-faint)", fontWeight: 600 }}>
            {entree.groupe}
          </div>
          <h2 style={{ fontSize: ecran.compact ? 16 : 18, marginTop: 2 }}>{entree.label}</h2>
        </header>

        <div style={{ flex: 1, overflowY: "auto",
                      padding: ecran.compact ? "16px 14px" : "24px 28px" }}
             className="scrollbar-thin">
          {/* Un formulaire garde sa colonne étroite : on y lit des phrases, et
              une phrase large se balaie au lieu de se lire. */}
          <div style={{ maxWidth: entree.large ? LARGEUR_PLEINE
            : entree.etroit ? 780 : LARGEUR_COURANTE }}>
            {/* Les écrans de montage se renvoient les uns aux autres : le
                bandeau de rôle propose l'assemblage, et l'assemblage renvoie aux
                règles d'extraction quand il faut y écrire une expression. */}
            <Composant
              key={`${entree.id}-${contexte?.categorieId ?? ""}`}
              contexte={contexte}
              onMontage={() => { setContexte(null); setEntreeId("montage"); }}
              onOuvrirEcran={(id, suite) => { setContexte(suite || null); setEntreeId(id); }}
              // Le journal cite des documents : on doit pouvoir aller les voir
              // (§22.64). Les autres écrans l'ignorent, et c'est sans effet.
              onOuvrirDocument={onOuvrirDocument}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
