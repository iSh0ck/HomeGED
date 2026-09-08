/**
 * Traduction du journal d'audit en français lisible.
 *
 * Le journal est écrit pour la preuve : deux chaînes libres (`action`,
 * `objet_type`) et un objet JSON de détails. C'est exact, mais illisible pour
 * qui n'a pas écrit le code — « base.ligne_modifiee / table nº7 » ne dit rien à
 * la personne qui cherche simplement qui a touché à quoi hier soir.
 *
 * Ce module est une couche de **lecture**, jamais d'écriture : il ne modifie ni
 * le journal ni ce que l'API renvoie. Il traduit, et rien n'est perdu au
 * passage — le code d'action exact et le JSON brut restent affichables à côté
 * de la phrase. Une action inconnue n'est pas ignorée : elle est reconstruite à
 * partir de ses deux morceaux (`famille.verbe`), ce qui permet d'ajouter des
 * événements côté serveur sans que cet écran ne devienne muet.
 */
import { t } from "./langue";

// ------------------------------------------------------------
// Familles d'événements : ce qui donne la couleur et le regroupement
// ------------------------------------------------------------

/** @traduit-a-la-lecture */
export const FAMILLES = {
  document: { libelle: "Documents", ton: "neutre" },
  utilisateur: { libelle: "Comptes", ton: "attention" },
  role: { libelle: "Droits", ton: "attention" },
  auth: { libelle: "Sécurité des connexions", ton: "securite" },
  job: { libelle: "Traitements", ton: "neutre" },
  jobs: { libelle: "Traitements", ton: "neutre" },
  corbeille: { libelle: "Corbeille", ton: "danger" },
  stockage: { libelle: "Fichiers", ton: "neutre" },
  base: { libelle: "Base de données", ton: "attention" },
  tableau: { libelle: "Tableaux de bord", ton: "neutre" },
  emetteur: { libelle: "Émetteurs", ton: "neutre" },
  categorie: { libelle: "Classement", ton: "attention" },
  reglages: { libelle: "Réglages", ton: "attention" },
  configuration: { libelle: "Configuration", ton: "attention" },
  audit: { libelle: "Journal", ton: "danger" },
  export: { libelle: "Export", ton: "securite" },
  compte: { libelle: "Mon compte", ton: "attention" },
};

/**
 * Phrases par action. Chacune reçoit l'événement complet et rend une phrase au
 * passé : c'est ainsi qu'on raconte ce qui s'est produit.
 *
 * `ton` colore la ligne — `danger` pour ce qui détruit, `attention` pour ce qui
 * change des droits ou la structure, `securite` pour les tentatives d'intrusion,
 * `neutre` pour le reste. Il ne juge pas l'action : il indique seulement ce qui
 * mérite un deuxième regard quand on parcourt une longue liste.
 */
const PHRASES = {
  "document.depot": (e) => (fichier(e)
    ? t("Document déposé ({fichier})", { fichier: fichier(e) })
    : t("Document déposé")),
  "document.consultation": (e) => (fichier(e)
    ? t("Document {n} consulté ({fichier})", { n: numero(e), fichier: fichier(e) })
    : t("Document {n} consulté", { n: numero(e) })),
  "document.modification": (e, refs) => (nomDuDocument(e, refs)
    ? t("Document {n} modifié ({nom})", { n: numero(e), nom: nomDuDocument(e, refs) })
    : t("Document {n} modifié", { n: numero(e) })),

  // Ces deux-là n'avaient pas de phrase : le repli composait « Un document
  // attaches » et « Un document creation manuelle » à partir du code (§22.64).
  "document.attaches": (e, refs) => {
    const ids = d(e, "documents");
    const noms = (Array.isArray(ids) ? ids : [])
      .map((id) => refs?.documents?.[id] || t("nº{id}", { id }));
    if (!noms.length) return t("Aucun document attaché sous « {champ} »", { champ: intituleDuChamp(e) });
    return noms.length > 1
      ? t("Documents attachés sous « {champ} » : {noms}",
        { champ: intituleDuChamp(e), noms: noms.join(" · ") })
      : t("Document attaché sous « {champ} » : {noms}",
        { champ: intituleDuChamp(e), noms: noms[0] });
  },
  "document.creation_manuelle": (e) => (fichier(e)
    ? t("Création de la fiche « {nom} »", { nom: fichier(e) })
    : t("Création de la fiche")),
  "document.suppression": (e) => (fichier(e)
    ? t("Document {n} supprimé ({fichier})", { n: numero(e), fichier: fichier(e) })
    : t("Document {n} supprimé", { n: numero(e) })),

  "utilisateur.creation": (e) =>
    t("Compte créé pour {qui}", { qui: d(e, "email") || t("un nouvel arrivant") }),
  "utilisateur.modification": (e) => t("Compte {qui} modifié", {
    qui: d(e, "email") || e?.details?.apres?.email || e?.details?.avant?.email || numero(e),
  }),
  "utilisateur.suppression": (e) =>
    t("Compte {qui} supprimé", { qui: d(e, "email") || numero(e) }),

  "base.affichage_regle": (e) => t("Affichage de la table « {table} » revu", {
    table: d(e, "libelle") || d(e, "table") || "?",
  }),

  "reglages.modification": (e) => {
    // Un seul réglage : on dit lequel et ce qu'il vaut désormais — c'est la
    // ligne qu'on relit six mois plus tard en se demandant qui a changé la
    // durée des sessions. Plusieurs : le compte suffit, le détail est à un clic.
    const apres = e?.details?.apres || {};
    const avant = e?.details?.avant || {};
    const libelles = e?.details?.libelles || {};
    const cles = Object.keys(apres);
    if (cles.length === 1) {
      const cle = cles[0];
      return t("Réglage « {nom} » : {avant} → {apres}", {
        nom: t(libelles[cle] || etiquette(cle)),
        avant: formaterValeur(cle, avant[cle]),
        apres: formaterValeur(cle, apres[cle]),
      });
    }
    return t("{n} réglages modifiés", { n: cles.length });
  },

  "configuration.import": (e) => {
    const modele = d(e, "modele");
    const mode = d(e, "mode") === "remplacer" ? t("en remplacement") : t("en complément");
    return modele
      ? t("Configuration importée {mode} (modèle « {modele} »)", { mode, modele })
      : t("Configuration importée {mode}", { mode });
  },

  "categorie.colonnes": (e) => {
    const liste = d(e, "colonnes");
    const n = Array.isArray(liste) ? liste.length : null;
    if (n == null) return t("Colonnes du tableau revues");
    return n > 1
      ? t("Colonnes du tableau revues ({n} affichées)", { n })
      : t("Colonnes du tableau revues ({n} affichée)", { n });
  },

  "role.creation": (e) => t("Rôle « {nom} » créé", { nom: d(e, "nom") || "?" }),
  "role.suppression": (e) => t("Rôle « {nom} » supprimé", { nom: d(e, "nom") || "?" }),
  "role.droits_modifies": (e) =>
    t("Droits du rôle « {nom} » revus", { nom: d(e, "role") || "?" }),

  "auth.code_secours_utilise": (e) =>
    t("Connexion par code de secours ({n} restant(s))", { n: d(e, "codes_restants") ?? "?" }),

  "compte.mot_de_passe_change": () => t("Mot de passe changé, sessions ouvertes refermées"),
  "compte.session_fermee": (e) =>
    (d(e, "elle_meme")
      ? t("Déconnexion depuis cet appareil")
      : t("Session fermée à distance ({appareil})", {
        appareil: d(e, "appareil") || t("appareil inconnu"),
      })),
  "compte.sessions_fermees": (e) =>
    t("{n} autre(s) session(s) fermée(s) d'un coup", { n: d(e, "nombre") ?? "?" }),

  "compte.otp_active": () => t("Double authentification mise en place"),
  "compte.otp_desactive": () => t("Double authentification retirée"),
  "compte.codes_secours_regeneres": () => t("Nouveaux codes de secours établis"),
  "utilisateur.otp_reinitialise": (e) => (d(e, "reste_imposee")
    ? t("Double authentification débloquée pour {qui} (elle reste exigée)",
      { qui: d(e, "email") || numero(e) })
    : t("Double authentification débloquée pour {qui}",
      { qui: d(e, "email") || numero(e) })),

  "auth.verrouillage": (e) =>
    t("Connexions bloquées après trop d'essais sur « {identifiant} »", {
      identifiant: d(e, "identifiant_tente") || "?",
    }),
  "auth.deverrouillage": (e) =>
    (d(e, "sources_liberees") != null
      ? t("{n} blocage(s) levé(s) d'un coup", { n: d(e, "sources_liberees") })
      : t("Blocage de connexion levé")),

  "job.rejeu_demande": (e) =>
    t("Traitement relancé pour « {fichier} »", { fichier: d(e, "nom_fichier") || "?" }),
  "job.reprise_automatique": (e) =>
    t("Document complété par une reprise automatique (« {fichier} »)", {
      fichier: d(e, "nom_fichier") || "?",
    }),
  "job.suppression": (e) =>
    t("Ligne de suivi supprimée (« {fichier} »)", { fichier: d(e, "nom_fichier") || "?" }),
  "jobs.purge_automatique": (e) =>
    t("Ménage automatique : {n} ligne(s) de suivi ancienne(s) effacée(s)",
      { n: d(e, "nombre") ?? "?" }),

  "corbeille.suppression_definitive": () =>
    t("Fichier détruit définitivement depuis la corbeille"),
  "corbeille.vidage": (e) =>
    t("Corbeille vidée : {n} fichier(s) détruit(s)", { n: d(e, "fichiers_supprimes") ?? "?" }),
  "stockage.orphelin_en_corbeille": () =>
    t("Fichier sans document rattaché déplacé en corbeille"),
  // Action d'une version antérieure du serveur de travaux : le code ne l'écrit
  // plus, mais elle existe dans le journal et doit rester lisible.
  "stockage.purge_orphelin": () => t("Fichier sans document rattaché purgé"),
  "export.demande": (e) => t("Archive complète préparée ({n} documents, {taille})", {
    n: d(e, "documents") ?? "?",
    taille: formaterValeur("taille_octets", d(e, "taille_octets")),
  }),
  "export.telecharge": (e) =>
    t("Archive complète téléchargée ({n} documents)", { n: d(e, "documents") ?? "?" }),

  "stockage.compression": (e) =>
    t("{n} archive(s) recompressée(s), {gagnes} récupérés", {
      n: d(e, "documents") ?? "?",
      gagnes: formaterValeur("octets_gagnes", d(e, "octets_gagnes")),
    }),

  "base.table_creee": (e) =>
    t("Table « {table} » créée", { table: d(e, "libelle") || d(e, "table") || "?" }),
  "base.table_supprimee": (e) =>
    t("Table « {table} » supprimée avec ses {n} ligne(s)", {
      table: d(e, "table") || "?", n: d(e, "lignes_perdues") ?? "?",
    }),
  "base.colonne_ajoutee": (e) =>
    t("Colonne ajoutée à la table « {table} »", { table: d(e, "table") || "?" }),
  "base.ligne_creee": (e) =>
    t("Ligne ajoutée dans « {table} »", { table: d(e, "table") || "?" }),
  "base.ligne_modifiee": (e) =>
    t("Ligne modifiée dans « {table} »", { table: d(e, "table") || "?" }),
  "base.ligne_supprimee": (e) =>
    t("Ligne supprimée dans « {table} »", { table: d(e, "table") || "?" }),

  "tableau.creation": (e) =>
    t("Tableau de bord « {nom} » créé", { nom: d(e, "nom") || "?" }),
  "tableau.modification": (e) =>
    t("Tableau de bord « {nom} » modifié", { nom: d(e, "nom") || "?" }),
  "tableau.suppression": (e) =>
    t("Tableau de bord « {nom} » supprimé", { nom: d(e, "nom") || "?" }),

  "audit.purge": (e) =>
    t("Journal purgé : {n} entrée(s) antérieure(s) au {date} supprimée(s)", {
      n: d(e, "entrees_supprimees") ?? "?",
      date: formaterValeur("avant", d(e, "avant")),
    }),

  "emetteur.regex_retiree": (e) =>
    t("Règle de reconnaissance de l'émetteur « {nom} » retirée", {
      nom: d(e, "nom") || numero(e),
    }),
};

/** Tons particuliers, quand la famille seule serait trompeuse. */
const TONS = {
  "document.suppression": "danger",
  "utilisateur.suppression": "danger",
  "role.suppression": "danger",
  "base.table_supprimee": "danger",
  "base.ligne_supprimee": "danger",
  "tableau.suppression": "danger",
  "job.suppression": "attention",
  "compte.otp_desactive": "danger",
  "compte.mot_de_passe_change": "attention",
  "auth.code_secours_utilise": "securite",
  "utilisateur.otp_reinitialise": "danger",
  "auth.deverrouillage": "attention",
  "jobs.purge_automatique": "neutre",
  "stockage.orphelin_en_corbeille": "neutre",
};

/** Verbes de repli, pour une action que ce module ne connaît pas encore. */
/** @traduit-a-la-lecture */
const VERBES = {
  creation: "créé",
  creee: "créée",
  modification: "modifié",
  modifiee: "modifiée",
  suppression: "supprimé",
  supprimee: "supprimée",
  ajoutee: "ajoutée",
  purge_automatique: "purgé automatiquement",
};

/** @traduit-a-la-lecture */
const OBJETS = {
  document: "un document",
  utilisateur: "un compte",
  role: "un rôle",
  connexion: "une connexion",
  job: "un traitement",
  fichier: "un fichier",
  corbeille: "la corbeille",
  table: "une table",
  tableau_de_bord: "un tableau de bord",
  emetteur: "un émetteur",
};

// ------------------------------------------------------------
// Description d'un événement
// ------------------------------------------------------------

/** Traduit un événement en { phrase, ton, famille }. */
export function decrire(evenement, references) {
  const famille = (evenement.action || "").split(".")[0];
  const modele = PHRASES[evenement.action];
  return {
    // Les doubles espaces viennent d'un numéro absent — c'est le cas dans
    // l'historique d'un document, où rappeler son numéro à chaque ligne
    // n'apprend rien à qui l'a sous les yeux.
    phrase: (modele ? modele(evenement, references) : phraseDeRepli(evenement))
      .replace(/\s{2,}/g, " ").trim(),
    ton: TONS[evenement.action] || FAMILLES[famille]?.ton || "neutre",
    famille: t(FAMILLES[famille]?.libelle || "Autres"),
  };
}

/**
 * Phrase reconstruite pour une action absente du dictionnaire. Mieux vaut
 * « Un document supprimé » approximatif que le code brut : le lecteur comprend
 * l'essentiel, et le code exact reste affiché juste à côté.
 */
function phraseDeRepli(evenement) {
  const [, verbe] = (evenement.action || "").split(".");
  const objet = t(OBJETS[evenement.objet_type] || evenement.objet_type || "un objet");
  const action = t(VERBES[verbe] || (verbe || "").replace(/_/g, " "));
  const majuscule = objet.charAt(0).toUpperCase() + objet.slice(1);
  return `${majuscule} ${action}`.trim();
}

/**
 * Intitulés courts, pour les listes de filtres. Séparés des phrases : celles-ci
 * racontent un événement précis (« Compte créé pour marie@… »), un filtre doit
 * nommer une catégorie d'événements (« Création de compte »).
 */
/** @traduit-a-la-lecture */
const INTITULES = {
  "document.depot": "Dépôt d'un document",
  "document.consultation": "Consultation d'un document",
  "document.modification": "Modification d'un document",
  "document.attaches": "Document(s) attaché(s)",
  "document.creation_manuelle": "Création d'une fiche",
  "document.suppression": "Suppression d'un document",
  "utilisateur.creation": "Création de compte",
  "utilisateur.modification": "Modification de compte",
  "utilisateur.suppression": "Suppression de compte",
  "reglages.modification": "Modification des réglages",
  "configuration.import": "Import d'une configuration",
  "role.creation": "Création d'un rôle",
  "role.suppression": "Suppression d'un rôle",
  "role.droits_modifies": "Modification des droits d'un rôle",
  "auth.verrouillage": "Blocage après trop d'essais",
  "auth.code_secours_utilise": "Connexion par code de secours",
  "compte.mot_de_passe_change": "Changement de mot de passe",
  "compte.session_fermee": "Fermeture d'une session",
  "compte.sessions_fermees": "Fermeture des autres sessions",
  "compte.otp_active": "Mise en place d'une double authentification",
  "compte.otp_desactive": "Retrait d'une double authentification",
  "compte.codes_secours_regeneres": "Renouvellement des codes de secours",
  "utilisateur.otp_reinitialise": "Déblocage d'une double authentification",
  "auth.deverrouillage": "Levée d'un blocage",
  "job.rejeu_demande": "Relance d'un traitement",
  "job.suppression": "Suppression d'une ligne de suivi",
  "jobs.purge_automatique": "Ménage automatique du suivi",
  "corbeille.suppression_definitive": "Destruction d'un fichier",
  "corbeille.vidage": "Vidage de la corbeille",
  "stockage.orphelin_en_corbeille": "Fichier orphelin mis en corbeille",
  "stockage.purge_orphelin": "Purge d'un fichier orphelin",
  "stockage.compression": "Compression d'archives",
  "export.demande": "Préparation d'un export",
  "export.telecharge": "Téléchargement d'un export",
  "base.table_creee": "Création d'une table",
  "base.table_supprimee": "Suppression d'une table",
  "base.colonne_ajoutee": "Ajout d'une colonne",
  "base.ligne_creee": "Ajout d'une ligne",
  "base.ligne_modifiee": "Modification d'une ligne",
  "base.ligne_supprimee": "Suppression d'une ligne",
  "tableau.creation": "Création d'un tableau de bord",
  "tableau.modification": "Modification d'un tableau de bord",
  "tableau.suppression": "Suppression d'un tableau de bord",
  "emetteur.regex_retiree": "Retrait d'une règle d'émetteur",
  "audit.purge": "Purge du journal",
};

/** Libellé lisible d'un code d'action, pour les listes de filtres. */
// Les dictionnaires restent en français : ce sont des constantes de module,
// évaluées avant que la langue soit connue (§22.55). La traduction se fait donc
// **à la lecture**, ici, où la langue est établie.
export function libelleAction(code) {
  return t(INTITULES[code] || phraseDeRepli({ action: code, objet_type: null }));
}

export function familleDe(code) {
  return t(FAMILLES[(code || "").split(".")[0]]?.libelle || "Autres");
}

export function libelleObjet(code) {
  const objet = OBJETS[code];
  if (!objet) return code;
  return t(objet.replace(/^(un |une |la |le )/, "").replace(/^./, (c) => c.toUpperCase()));
}

// ------------------------------------------------------------
// Détails : tout montrer, mais en français
// ------------------------------------------------------------

/** @traduit-a-la-lecture */
const ETIQUETTES = {
  nom_fichier: "Nom du fichier",
  chemin: "Emplacement",
  chemin_stockage: "Emplacement du fichier",
  chemin_origine: "Emplacement d'origine",
  chemin_corbeille: "Emplacement en corbeille",
  hash_sha256: "Empreinte du fichier",
  categorie_id: "Catégorie",
  categorie: "Catégorie",
  montant_ttc: "Montant TTC",
  numero_facture: "Numéro de facture",
  numero_client: "Numéro de client",
  titulaire: "Titulaire",
  date_document: "Date du document",
  date_import: "Date d'entrée",
  fichier_a_purger: "Le PDF part en corbeille",
  email: "Adresse e-mail",
  nom: "Nom",
  roles: "Rôles",
  actif: "Compte actif",
  identifiant_tente: "Identifiant essayé",
  adresse: "Adresse d'origine",
  verrouillage_secondes: "Durée du blocage",
  sources_liberees: "Blocages levés",
  cle: "Blocage visé",
  fichiers_supprimes: "Fichiers détruits",
  echecs: "Échecs",
  table: "Table",
  libelle: "Intitulé",
  colonne: "Colonne",
  colonnes: "Colonnes",
  lignes_perdues: "Lignes perdues",
  valeurs: "Valeurs",
  nombre: "Nombre",
  indicateurs: "Indicateurs",
  statut: "État",
  etape: "Étape",
  role: "Rôle",
  droits: "Droits",
  regex_identification: "Ancienne expression de reconnaissance",
  metadonnees: "Champs extraits",
  avant: "Avant",
  apres: "Après",
  entrees_supprimees: "Entrées supprimées",
  octets_gagnes: "Espace récupéré",
  taille_octets: "Taille de l'archive",
  absents: "PDF introuvables",
  documents: "Documents",
  niveau: "Niveau de compression",
  codes_restants: "Codes de secours restants",
  reste_imposee: "Reste exigée",
  sessions_fermees: "Autres sessions refermées",
  appareil: "Appareil",
  elle_meme: "Session de l'auteur",
  otp_impose: "Double authentification exigée",
  etape: "Étape",
  plus_ancienne_supprimee: "Plus ancienne supprimée",
  id: "Identifiant interne",
  est_admin: "Administrateur",
  comptes_concernes: "Comptes concernés",
  mot_de_passe_change: "Mot de passe changé",
  statut_precedent: "État précédent",
  retention_jours: "Ancienneté retenue (jours)",
  peut_voir: "Peut voir",
  peut_modifier: "Peut modifier",
  obligatoire: "Obligatoire",
  type: "Type",
};

/** « lignes_perdues » → « Lignes perdues », pour toute clé non répertoriée. */
export function etiquette(cle) {
  if (ETIQUETTES[cle]) return t(ETIQUETTES[cle]);
  const mots = String(cle).replace(/_/g, " ");
  return mots.charAt(0).toUpperCase() + mots.slice(1);
}

/**
 * Clés qui portent un identifiant d'objet nommable ailleurs dans l'application.
 * Sans résolution, le journal dit « Catégorie (nº) : 2 » — exact, et illisible
 * pour qui ne connaît pas la numérotation interne.
 */
const REFERENCES = {
  categorie_id: "categories",
};

/**
 * Met une valeur brute en français : booléens, durées, dates, listes.
 *
 * `references` — facultatif — donne les noms correspondant aux identifiants
 * ({ categories: Map, emetteurs: Map }). Le numéro reste affiché à côté du nom :
 * c'est lui qui figure dans le journal, et c'est lui qu'on retrouvera si le nom
 * change plus tard.
 */
export function formaterValeur(cle, valeur, references) {
  if (valeur === null || valeur === undefined || valeur === "") return "—";
  if (REFERENCES[cle]) {
    const nom = references?.[REFERENCES[cle]]?.get(Number(valeur));
    // Le nom seul quand on le connaît : « Factures » se lit, « Factures (nº2) »
    // impose au lecteur un numéro qui ne lui apprend rien. Le numéro ne s'affiche
    // qu'à défaut de nom — c'est alors la seule chose qu'on puisse dire.
    return nom || `nº${valeur}`;
  }
  if (typeof valeur === "boolean") return valeur ? "oui" : "non";
  if (cle === "verrouillage_secondes" && typeof valeur === "number") return duree(valeur);
  if ((cle === "octets_gagnes" || cle === "taille_octets") && typeof valeur === "number") {
    return taille(valeur);
  }
  if (Array.isArray(valeur)) {
    if (!valeur.length) return "aucun";
    return valeur.map(decrireElement).join(" · ");
  }
  if (typeof valeur === "object") return null; // traité en sous-lignes
  const texte = String(valeur);
  const horodatage = texte.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (horodatage) {
    const [, a, m, j, h, min] = horodatage;
    return `${j}/${m}/${a} à ${h}h${min}`;
  }
  const jour = texte.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (jour) return `${jour[3]}/${jour[2]}/${jour[1]}`;
  return texte;
}

/**
 * Un élément de liste en une ligne. Les listes du journal contiennent soit des
 * chaînes (des rôles), soit de petits objets (une colonne de table, un droit sur
 * une catégorie) : on les nomme par ce qu'ils ont de parlant plutôt que de les
 * réduire à « [object Object] », qui ne dit rien à personne.
 */
function decrireElement(element) {
  if (element === null || element === undefined) return "—";
  if (typeof element !== "object") return String(element);

  if ("categorie_id" in element) {
    const droits = [element.peut_voir && t("voir"), element.peut_modifier && t("modifier")]
      .filter(Boolean).join(t(" et "));
    return t("catégorie nº{n} : {droits}", {
      n: element.categorie_id, droits: droits || t("aucun droit"),
    });
  }
  const nom = element.nom ?? element.libelle ?? element.titre;
  if (nom != null) {
    const precisions = Object.entries(element)
      .filter(([cle, v]) => !["nom", "libelle", "titre"].includes(cle) && v !== false && v !== null)
      .map(([cle, v]) => (v === true ? etiquette(cle).toLowerCase() : `${etiquette(cle).toLowerCase()} ${v}`));
    return precisions.length ? `${nom} (${precisions.join(", ")})` : String(nom);
  }
  return Object.entries(element).map(([cle, v]) => `${etiquette(cle).toLowerCase()} ${v}`).join(", ");
}

/** Des octets en unité lisible : « 1,6 Mo » plutôt que « 1659959 ». */
function taille(octets) {
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} Ko`;
  if (octets < 1024 * 1024 * 1024) return `${(octets / (1024 * 1024)).toFixed(1)} Mo`;
  return `${(octets / (1024 * 1024 * 1024)).toFixed(2)} Go`;
}

function duree(secondes) {
  if (secondes < 60) return `${secondes} secondes`;
  const minutes = Math.round(secondes / 60);
  if (minutes < 60) return `${minutes} minute${minutes > 1 ? "s" : ""}`;
  const heures = Math.round(minutes / 6) / 10;
  return `${heures} heure${heures > 1 ? "s" : ""}`;
}

/**
 * Transforme les détails en lignes affichables.
 *
 * Deux formes seulement, parce que le journal n'en écrit pas d'autres :
 *   une paire `avant` / `apres` — on montre alors le passage d'une valeur à
 *   l'autre, en signalant ce qui a réellement changé ;
 *   un objet plat — une ligne par clé.
 *
 * Aucune clé n'est écartée, même inconnue : perdre une information serait
 * exactement ce que ce journal existe pour empêcher.
 */
export function detailler(details, references) {
  if (!details || typeof details !== "object") return [];

  // Un vrai avant/après compare deux **états** : deux objets, ou deux listes.
  // Certaines actions emploient « avant » pour tout autre chose — la purge du
  // journal y range sa date de coupure. Sans cette vérification, la chaîne
  // « 2026-06-01 » était parcourue caractère par caractère et le détail devenait
  // une bouillie de lignes numérotées.
  const compare = (valeur) => valeur !== null && typeof valeur === "object";
  if (compare(details.avant) || compare(details.apres)) {
    const avant = details.avant ?? {};
    const apres = details.apres ?? {};
    // Intitulés joints à l'événement (§18.33) : « duree_session_heures » ne se
    // relit pas, et le réglage peut avoir été renommé — voire retiré — depuis.
    // Les recopier ici les ferait diverger de ceux qui les valident.
    const libelles = details.libelles ?? {};
    const autres = Object.entries(details).filter(
      ([cle]) => cle !== "avant" && cle !== "apres" && cle !== "libelles");

    // Remplacement en bloc (les droits d'un rôle, par exemple) : les deux états
    // sont des listes, il n'y a pas de champ à champ à comparer.
    if (Array.isArray(avant) || Array.isArray(apres)) {
      return [
        { type: "valeur", cle: "avant", libelle: t("Avant"), valeur: formaterValeur("avant", avant, references) },
        { type: "valeur", cle: "apres", libelle: t("Après"), valeur: formaterValeur("apres", apres, references) },
        ...autres.flatMap(([cle, valeur]) => ligneSimple(cle, valeur, references)),
      ];
    }

    const cles = [...new Set([...Object.keys(avant), ...Object.keys(apres)])];
    const lignes = cles.map((cle) => {
      // Une modification partielle n'envoie que les champs touchés : un champ
      // absent de « après » n'a pas été vidé, il n'a pas été soumis. Les
      // confondre ferait lire une perte de données là où il n'y en a pas.
      const soumis = cle in apres;
      return {
        type: "changement",
        cle,
        libelle: libelles[cle] || etiquette(cle),
        avant: formaterValeur(cle, avant[cle], references),
        apres: soumis
          ? formaterValeur(cle, apres[cle], references)
          : formaterValeur(cle, avant[cle], references),
        change: soumis && JSON.stringify(avant[cle]) !== JSON.stringify(apres[cle]),
      };
    });
    // Le reste des détails (le nom du rôle, la table concernée…) suit.
    return [...lignes, ...autres.flatMap(([cle, valeur]) => ligneSimple(cle, valeur, references))];
  }

  return Object.entries(details).flatMap(([cle, valeur]) => ligneSimple(cle, valeur, references));
}

function ligneSimple(cle, valeur, references) {
  // Une liste d'identifiants de documents n'est pas une valeur à lire mais des
  // fiches à ouvrir (§22.64) : « Documents 108 » ne dit rien, et l'on veut aller
  // voir. On rend la ligne avec de quoi les nommer **et** les atteindre.
  if (cle === "documents" && Array.isArray(valeur)) {
    return [{
      type: "documents",
      cle,
      libelle: etiquette(cle),
      documents: valeur.map((id) => ({
        id, nom: references?.documents?.[id] || t("nº{id}", { id }),
      })),
    }];
  }
  const formatee = formaterValeur(cle, valeur, references);
  if (formatee !== null) {
    return [{ type: "valeur", cle, libelle: etiquette(cle), valeur: formatee }];
  }
  // Objet imbriqué : on l'aplatit d'un niveau plutôt que d'afficher du JSON.
  return Object.entries(valeur).map(([sousCle, sousValeur]) => ({
    type: "valeur",
    cle: `${cle}.${sousCle}`,
    libelle: `${etiquette(cle)} · ${etiquette(sousCle)}`,
    valeur: formaterValeur(sousCle, sousValeur, references) ?? JSON.stringify(sousValeur),
  }));
}

// ------------------------------------------------------------
// Dates
// ------------------------------------------------------------

/** Clé de regroupement par jour, à partir d'un horodatage ISO. */
// Les dates du journal passent par le module d'horodatage : elles arrivent en
// temps universel, et se lisent dans le fuseau du foyer (§18.19). Découper la
// chaîne à la main, comme ici auparavant, revenait à afficher l'heure de
// Greenwich en croyant afficher celle de Paris — et à ranger sous la mauvaise
// journée tout ce qui se passe après 22 h.
export { cleDuJour as jourDe, formaterHeure as heureDe, libelleJour } from "./horodatage";

// ------------------------------------------------------------
// Petits accès aux détails
// ------------------------------------------------------------

function d(evenement, cle) {
  const valeur = evenement?.details?.[cle];
  return valeur === undefined ? null : valeur;
}

function numero(evenement) {
  return evenement?.objet_id != null ? `nº${evenement.objet_id}` : "";
}

/**
 * Le nom du document que l'événement désigne (§22.64).
 *
 * Le journal ne retient que des identifiants — c'est ce qui le rend fiable, un
 * nom change et l'histoire, non. Mais « Document nº108 modifié » n'apprend rien
 * à qui n'a pas la numérotation en tête. La page apporte les noms ; un document
 * détruit depuis n'en a plus, et l'on retombe alors sur le numéro seul.
 */
function nomDuDocument(evenement, references) {
  const identifiant = evenement?.objet_id;
  if (identifiant == null) return null;
  return references?.documents?.[identifiant] || null;
}

function fichier(evenement) {
  return d(evenement, "nom_fichier");
}

/** « meta:factures_liees » → « factures liees » : le champ, tel qu'on le lit. */
function intituleDuChamp(evenement) {
  const champ = d(evenement, "champ") || "";
  return champ.replace(/^meta:/, "").replace(/_/g, " ");
}
