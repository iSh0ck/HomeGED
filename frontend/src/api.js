import { t } from "./lib/langue";

const BASE = "/api";

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

/**
 * La session vit dans un cookie `httpOnly` posé par l'API : le jeton n'est plus
 * accessible au JavaScript de la page, et donc plus lisible par un script qui y
 * serait injecté. Le navigateur joint le cookie de lui-même à chaque requête de
 * même origine, il n'y a plus rien à transporter ici.
 *
 * En contrepartie, un cookie part aussi sur une requête déclenchée par un autre
 * site : c'est le risque CSRF. L'API pose donc un second cookie, lisible celui-là,
 * dont la valeur doit être répétée en en-tête sur toute écriture. Un site tiers
 * ne peut ni lire ce cookie ni forger l'en-tête.
 */
const NOM_COOKIE_CSRF = "homeged_csrf";

function jetonCsrf() {
  const trouve = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${NOM_COOKIE_CSRF}=`));
  return trouve ? decodeURIComponent(trouve.slice(NOM_COOKIE_CSRF.length + 1)) : null;
}

async function handle(res) {
  if (res.status === 401) {
    onUnauthorized?.();
  }
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(t(detail) || t("Erreur API {code}", { code: res.status }));
  }
  return res.status === 204 ? null : res.json();
}

/**
 * Consultation du registre sous l'identité d'un autre compte (§18.50).
 *
 * Le jeton vit dans `sessionStorage` : il ne survit pas à la fermeture de
 * l'onglet, et n'atteint pas les autres onglets — on peut ainsi garder
 * l'administration ouverte à côté, sous sa propre identité, ce qui est
 * exactement l'usage visé.
 */
const CLE_CONSULTATION = "homeged_consultation";

export function consultationEnCours() {
  try {
    const brut = sessionStorage.getItem(CLE_CONSULTATION);
    return brut ? JSON.parse(brut) : null;
  } catch {
    return null;   // stockage indisponible (navigation privée stricte)
  }
}

export function retenirConsultation(consultation) {
  try {
    sessionStorage.setItem(CLE_CONSULTATION, JSON.stringify(consultation));
  } catch {
    /* sans stockage, la consultation ne peut pas être retenue */
  }
}

export function quitterConsultation() {
  try {
    sessionStorage.removeItem(CLE_CONSULTATION);
  } catch {
    /* rien à retirer */
  }
}

/** Le cookie de session suffit ; seul le jeton anti-CSRF doit être ajouté. */
function authHeaders(extra = {}, avecConsultation = true) {
  const csrf = jetonCsrf();
  const entetes = csrf ? { ...extra, "X-CSRF-Token": csrf } : { ...extra };
  const consultation = consultationEnCours();
  if (avecConsultation && consultation?.jeton) {
    entetes["X-Consulter-Comme"] = consultation.jeton;
  }
  return entetes;
}

function get(path) {
  return fetch(`${BASE}${path}`, { headers: authHeaders() }).then(handle);
}
function send(method, path, body) {
  return fetch(`${BASE}${path}`, {
    method,
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(handle);
}
function del(path) {
  return fetch(`${BASE}${path}`, { method: "DELETE", headers: authHeaders() }).then(handle);
}

export const api = {
  // --- Authentification ---
  async login(email, motDePasse) {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", motDePasse);
    const res = await fetch(`${BASE}/auth/login`, { method: "POST", body: form });
    return handle(res);   // l'API pose les cookies de session dans sa réponse
  },
  async logout() {
    // Sans consultation : c'est **sa propre** session que l'on ferme, et une
    // consultation est en lecture seule — l'en-tête ferait refuser la
    // déconnexion, ce qui enfermerait dans le mode dont on veut sortir.
    quitterConsultation();
    await fetch(`${BASE}/auth/logout`, {
      method: "POST", headers: authHeaders({}, false),
    });
  },
  /**
   * Deuxième étape de la connexion, quand le compte porte une double
   * authentification. Le jeton intermédiaire ne transite qu'ici : il ne vaut
   * pas session et vit deux minutes.
   */
  async verifierOtp(jetonIntermediaire, code) {
    const res = await fetch(`${BASE}/auth/otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jeton_intermediaire: jetonIntermediaire, code }),
    });
    return handle(res);
  },
  me() {
    return get("/auth/me");
  },

  // --- Mon compte ---
  moi: () => get("/moi"),
  mesSessions: () => get("/moi/sessions"),
  fermerSession: (id) => del(`/moi/sessions/${id}`),
  fermerLesAutresSessions: () => send("POST", "/moi/sessions/fermer-les-autres"),
  changerMotDePasse: (ancien, nouveau) => send("POST", "/moi/mot-de-passe", { ancien, nouveau }),
  preparerOtp: () => send("POST", "/moi/otp/preparer"),
  activerOtp: (code) => send("POST", "/moi/otp/activer", { code }),
  desactiverOtp: (motDePasse) => send("POST", "/moi/otp/desactiver", { mot_de_passe: motDePasse }),
  regenererCodesSecours: (motDePasse) =>
    send("POST", "/moi/otp/codes-secours", { mot_de_passe: motDePasse }),

  // --- Documents ---
  /**
   * Renvoie `{ documents, total }`. Le total porte sur l'ensemble du filtre et
   * non sur la page reçue : il vient de l'en-tête `X-Total-Count`.
   */
  async documents(params = {}) {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
    ).toString();
    const res = await fetch(`${BASE}/documents${qs ? `?${qs}` : ""}`, { headers: authHeaders() });
    const documents = await handle(res);
    const total = Number(res.headers.get("X-Total-Count"));
    return { documents, total: Number.isFinite(total) ? total : documents.length };
  },
  document(id) {
    return get(`/documents/${id}`);
  },
  async fichierBlobUrl(id) {
    const res = await fetch(`${BASE}/documents/${id}/fichier`, { headers: authHeaders() });
    if (!res.ok) {
      if (res.status === 401) {
        onUnauthorized?.();
      }
      let detail = "";
      try {
        detail = (await res.json()).detail;
      } catch {
        detail = await res.text().catch(() => "");
      }
      throw new Error(t(detail) || t("erreur HTTP {code}", { code: res.status }));
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
  /**
   * Valeurs déjà présentes dans les documents pour une colonne (suggestions de
   * recherche). `filtres` transmet le contexte : les suggestions se limitent
   * alors à ce que les autres filtres actifs laissent visible.
   */
  valeursColonne(champ, { recherche, filtres, categorieId, q } = {}) {
    const qs = new URLSearchParams({ champ });
    if (recherche) qs.set("recherche", recherche);
    if (filtres?.length) qs.set("filtres", JSON.stringify(filtres));
    // Périmètre de la vue affichée : la catégorie choisie dans la navigation et
    // la recherche plein texte comptent autant que les filtres de colonne.
    if (categorieId !== undefined && categorieId !== null) qs.set("categorie_id", categorieId);
    if (q) qs.set("q", q);
    return get(`/documents/valeurs?${qs.toString()}`);
  },
  categories() {
    return get("/categories");
  },
  /**
   * Colonnes du tableau pour chaque catégorie (§18.1), toutes en une réponse :
   * changer de catégorie dans la navigation ne redemande rien au serveur.
   */
  colonnesCategories() {
    return get("/categories/colonnes");
  },
  /** Réglages généraux : fuseau horaire, nom du foyer (§18.19). */
  reglages: () => get("/reglages"),
  /** Nom du foyer, thème, accent — lisibles avant toute connexion (§18.24). */
  apparence: () => get("/apparence"),
  /** Première installation (§18.23) : ouverte tant qu'aucun compte n'existe. */
  etatInstallation: () => get("/installation"),
  installer: (donnees) => send("POST", "/installation", donnees),
  patchDocument(id, patch) {
    return send("PATCH", `/documents/${id}`, patch);
  },
  supprimerDocument(id) {
    return del(`/documents/${id}`);
  },

  // --- Valeurs proposées par une table de données (champs personnalisés) ---
  // Verrou d'édition (§17.21) : pris à l'ouverture de la fenêtre de
  // modification, prolongé tant qu'elle reste ouverte, rendu à la fermeture.
  prendreVerrou: (id) => send("POST", `/documents/${id}/verrou`),
  rendreVerrou: (id) => del(`/documents/${id}/verrou`),
  /** Essai d'extraction : ce que les règles trouvent, sans rien enregistrer (§18.41). */
  testerExtraction: (id) => send("POST", `/documents/${id}/tester-extraction`),

  /** Texte océrisé, ligne à ligne avec la position de chacune (§18.37). */
  texteOcr: (id) => get(`/documents/${id}/texte`),

  // Versions d'un document (§18.36)
  // Ce qu'un document rejoint par la chose qu'il concerne (§19.19).
  /** Les branches d'un niveau de repli (§21.6) : une branche n'est qu'un filtre. */
  groupes: (champ, { categorieId, filtres } = {}) => {
    const params = new URLSearchParams({ champ });
    if (categorieId != null) params.set("categorie_id", categorieId);
    if (filtres?.length) params.set("filtres", JSON.stringify(filtres));
    return get(`/groupes?${params}`);
  },
  /** Où sont les mots dans la page (§21.5) : de quoi désigner une valeur. */
  motsDocument: (id, page = 1) => get(`/documents/${id}/mots?page=${page}`),
  /** Export par modèle (§21.13) : ce qu'un modèle sait remplir, et les demandes. */
  trousExport: () => get("/exports-modele/trous"),
  demanderExportModele: (data) => send("POST", "/exports-modele", data),
  exportsModele: () => get("/exports-modele"),
  // Ce que l'archive contiendra, avant de la demander (§22.66) : on écrivait un
  // modèle à trous à l'aveugle et l'on découvrait le rangement après coup.
  apercuExportModele: (data) => send("POST", "/exports-modele/apercu", data),
  supprimerExportModele: (id) => send("DELETE", `/exports-modele/${id}`),
  /** Ce qu'on peut attacher à ce champ-là (§22.14) : borné par la déclaration. */
  attachables: (categorieId, champ, q = "", sauf = null) =>
    get(`/categories/${categorieId}/attachables?champ=${encodeURIComponent(champ)}`
        + `&q=${encodeURIComponent(q)}${sauf ? `&sauf=${sauf}` : ""}`),
  /** Les documents attachés par un champ (§22.11). */
  attaches: (id) => get(`/documents/${id}/attaches`),
  definirAttaches: (id, champ, documents) =>
    send("PUT", `/documents/${id}/attaches/${encodeURIComponent(champ)}`, { documents }),
  /** Ce que les déclarations de type rapprochent de ce document (§22.8). */
  rapprochements: (id) => get(`/documents/${id}/rapprochements`),
  /** Ce qui a été rattaché à la main à ce document (§22.4), des deux côtés. */
  rattachements: (id) => get(`/documents/${id}/rattachements`),
  rattacher: (id, autreId, libelle = null) =>
    send("POST", `/documents/${id}/rattachements`,
         { document_id: autreId, libelle: libelle || null }),
  detacher: (id, autreId) => del(`/documents/${id}/rattachements/${autreId}`),
  /** Ce qu'une catégorie attend, pour construire un formulaire (§22.7). */
  champsCategorie: (id) => get(`/categories/${id}/champs`),
  /** Créer une entrée à la main, sans fichier obligatoire (§22.7). */
  creerEntree: (data) => send("POST", "/documents", data),
  /** Les fichiers que porte un document (§22.2), dans leur ordre d'affichage. */
  piecesDocument: (id) => get(`/documents/${id}/pieces`),
  /** Image de première page d'une pièce : de quoi la reconnaître sans l'ouvrir. */
  async apercuPieceBlobUrl(documentId, pieceId) {
    const res = await fetch(`${BASE}/documents/${documentId}/pieces/${pieceId}/apercu`,
                            { headers: authHeaders() });
    if (!res.ok) return handle(res);
    return URL.createObjectURL(await res.blob());
  },
  /** Le fichier d'une pièce, pour le lire en entier. */
  async fichierPieceBlobUrl(documentId, pieceId) {
    const res = await fetch(`${BASE}/documents/${documentId}/pieces/${pieceId}/fichier`,
                            { headers: authHeaders() });
    if (!res.ok) return handle(res);
    return URL.createObjectURL(await res.blob());
  },
  /**
   * Joindre un fichier à un document existant (§22.2), ou rescanner l'une de ses
   * pièces (§22.3) — `remplacePieceId` dit laquelle. Vide : une pièce de plus.
   */
  joindrePiece: (documentId, fichier, remplacePieceId = null) => {
    const corps = new FormData();
    corps.append("fichier", fichier);
    if (remplacePieceId) corps.append("remplace_piece_id", String(remplacePieceId));
    return fetch(`${BASE}/documents/${documentId}/pieces`, {
      method: "POST", headers: authHeaders(), body: corps,
    }).then(handle);
  },
  /**
   * Ranger les pièces d'un document (§22.43). L'ordre décide de ce qu'on lit en
   * premier : une facture, sa garantie, son bon de livraison ne se lisent pas
   * dans l'ordre où on les a scannés.
   */
  ordonnerPieces: (documentId, ordre) =>
    send("PUT", `/documents/${documentId}/pieces/ordre`, ordre),
  /** La pièce que le registre ouvre et que la miniature montre. */
  piecePrincipale: (documentId, pieceId) =>
    send("PUT", `/documents/${documentId}/pieces/${pieceId}/principale`),
  retirerPiece: (documentId, pieceId) =>
    del(`/documents/${documentId}/pieces/${pieceId}`),
  /**
   * Glisser un fichier dans une fiche simple (§22.1).
   *
   * `Content-Type` n'est pas posé : le navigateur doit écrire lui-même la
   * frontière du multipart, et l'imposer à la main casse l'envoi.
   */
  deposerDansFiche: (categorieId, fichier) => {
    const corps = new FormData();
    corps.append("fichier", fichier);
    return fetch(`${BASE}/fiches/${categorieId}/documents`, {
      method: "POST", headers: authHeaders(), body: corps,
    }).then(handle);
  },
  /**
   * Image d'une page (§19.20) : de quoi reconnaître sans tout charger. La
   * première par défaut ; les suivantes servent à désigner une valeur qui n'est
   * pas en tête de document (§22.75).
   */
  async apercuBlobUrl(id, page = 1) {
    const res = await fetch(`${BASE}/documents/${id}/apercu?page=${page}`,
                            { headers: authHeaders() });
    if (!res.ok) return handle(res);
    return URL.createObjectURL(await res.blob());
  },
  /** Préférences d'affichage de ce compte-ci (§19.20). */
  changerPreferences: (preferences) => send("PUT", "/moi/preferences", preferences),
  /**
   * Recherche globale (§21.2) : un mot, et le périmètre où le chercher.
   * `filtres` n'accompagne que le périmètre « vue » — ailleurs il n'a pas de sens.
   */
  recherche: (q, perimetre = "tout", { categorieId, filtres, limite } = {}) => {
    const params = new URLSearchParams({ q, perimetre });
    if (categorieId != null) params.set("categorie_id", categorieId);
    if (filtres?.length) params.set("filtres", JSON.stringify(filtres));
    if (limite) params.set("limite", limite);
    return get(`/recherche?${params}`);
  },
  // Échéances et rappels (§21.9) : ce qui arrive à terme, et ce dont on a été prévenu.
  echeances: (horizon) => get(`/echeances${horizon ? `?horizon=${horizon}` : ""}`),
  notifications: (nonLues = false) =>
    get(`/notifications${nonLues ? "?non_lues=true" : ""}`),
  marquerNotificationLue: (id) => send("POST", `/notifications/${id}/lue`),
  toutMarquerLu: () => send("POST", "/notifications/tout-lu"),
  // La corbeille de chacun (§21.1) : supprimer met de côté, rien n'est perdu.
  // Paginée (§22.90) : un plafond dur rendait les plus anciens invisibles et
  // irrécupérables, sans que rien ne le dise.
  corbeille: ({ limite = 25, decalage = 0 } = {}) =>
    get(`/corbeille?limite=${limite}&decalage=${decalage}`),
  restaurerDocument: (id) => send("POST", `/corbeille/${id}/restaurer`),
  retirerDeLaCorbeille: (id) => del(`/corbeille/${id}`),
  viderMaCorbeille: () => send("POST", "/corbeille/vider"),
  versionsDocument: (id, pieceId = null) =>
    get(`/documents/${id}/versions${pieceId ? `?piece_id=${pieceId}` : ""}`),
  supprimerVersion: (id, versionId) => del(`/documents/${id}/versions/${versionId}`),
  async fichierVersionBlobUrl(id, versionId) {
    const res = await fetch(`${BASE}/documents/${id}/versions/${versionId}/fichier`,
                            { headers: authHeaders() });
    if (!res.ok) {
      if (res.status === 401) onUnauthorized?.();
      let detail = "";
      try { detail = (await res.json()).detail; } catch { detail = ""; }
      throw new Error(t(detail) || t("Version illisible ({code})", { code: res.status }));
    }
    return URL.createObjectURL(await res.blob());
  },
  journalDocument: (id, { limite = 25, decalage = 0 } = {}) =>
    get(`/documents/${id}/journal?limite=${limite}&decalage=${decalage}`),

  // `contexte` dit pour quel champ on demande ces valeurs (§22.59) : c'est lui
  // qui décide de ce qui se lit d'une ligne. Le serveur relit ce choix sur la
  // règle — un appelant ne désigne pas les colonnes qu'il veut voir.
  references: (table, recherche, contexte = null) => {
    const qs = new URLSearchParams();
    if (recherche) qs.set("recherche", recherche);
    if (contexte?.categorieId) qs.set("categorie_id", String(contexte.categorieId));
    if (contexte?.champ) qs.set("champ", contexte.champ);
    const suite = qs.toString();
    return get(`/references/${encodeURIComponent(table)}${suite ? `?${suite}` : ""}`);
  },

  /**
   * Conséquences réelles d'une suppression. Un administrateur passe par la
   * route d'administration, qui couvre tous les objets ; un compte ordinaire par
   * la route publique, restreinte à ce qu'il peut lui-même supprimer.
   */
  impactSuppression(typeObjet, identifiant, administrateur = true) {
    const base = administrateur ? "/admin/impact-suppression" : "/impact-suppression";
    return get(`${base}?type_objet=${encodeURIComponent(typeObjet)}`
      + `&identifiant=${encodeURIComponent(identifiant)}`);
  },

  // --- Centre d'analyse (documents non conformes aux champs attendus) ---
  /**
   * Le Centre d'analyse, **par page** (§22.43) : mille huit cents documents à
   * reprendre pesaient 825 ko à chaque ouverture. Le total vient de l'en-tête,
   * comme au registre.
   */
  async analyse({ limite = 50, decalage = 0 } = {}) {
    const res = await fetch(`${BASE}/analyse?limite=${limite}&decalage=${decalage}`,
                            { headers: authHeaders() });
    if (!res.ok) return handle(res);
    return { documents: await res.json(),
             total: Number(res.headers.get("X-Total-Count") || 0) };
  },
  // Ce qui attend qu'on dise de quel type il s'agit (§19.4).
  aClasser: () => get("/a-classer"),
  /**
   * Les chiffres de la barre d'outils, en une requête (§22.39). Assez léger pour
   * être relu souvent : c'est ce qui fait qu'un document qui arrive se voit sans
   * recharger la page.
   */
  compteurs: () => get("/compteurs"),
  /** Écarter un dépôt : ce fichier n'avait rien à faire là (§21.14). */
  ecarterTravail: (jobId) => del(`/a-classer/${jobId}`),
  classerTravail: (jobId, categorieId) =>
    send("POST", `/a-classer/${jobId}`, { categorie_id: categorieId }),
  /** Le fichier reçu d'un travail à classer, pour le regarder avant de trancher. */
  async fichierAClasserBlobUrl(jobId) {
    const res = await fetch(`${BASE}/a-classer/${jobId}/fichier`, { headers: authHeaders() });
    if (!res.ok) return handle(res);
    return URL.createObjectURL(await res.blob());
  },

  // --- Tableaux de bord ---
  tableauxDeBord: () => get("/tableaux-de-bord"),
  donneesTableau: (id) => get(`/tableaux-de-bord/${encodeURIComponent(id)}/donnees`),
  optionsIndicateurs: () => get("/tableaux-de-bord/options"),

  // --- Vues enregistrées (jeux de critères réutilisables) ---
  vues: () => get("/vues"),
  creerVue: (data) => send("POST", "/vues", data),
  modifierVue: (id, data) => send("PUT", `/vues/${id}`, data),
  supprimerVue: (id) => del(`/vues/${id}`),
};

export const adminApi = {
  // Catégories (classement automatique par regex)
  categories: () => get("/admin/categories"),
  creerCategorie: (data) => send("POST", "/admin/categories", data),
  modifierCategorie: (id, data) => send("PUT", `/admin/categories/${id}`, data),
  supprimerCategorie: (id) => del(`/admin/categories/${id}`),
  colonnesCategorie: (id) => get(`/admin/categories/${id}/colonnes`),
  reglages: () => get("/admin/reglages"),
  enregistrerReglages: (valeurs) => send("PUT", "/admin/reglages", valeurs),
  supervision: () => get("/admin/supervision"),
  // Configuration du foyer : la sortir, la reprendre, partir d'un modèle (§18.26).
  exporterConfiguration: (avecDonnees = false) =>
    get(`/admin/configuration${avecDonnees ? "?avec_donnees=true" : ""}`),
  modelesConfiguration: () => get("/admin/configuration/modeles"),
  importerConfiguration: (charge) => send("POST", "/admin/configuration/import", charge),
  // Réglages d'affichage d'une table de données : intitulé, colonne
  // d'affichage, colonnes identifiantes (§18.13).
  reglerAffichageTable: (nom, data) =>
    send("PUT", `/admin/base/tables/${encodeURIComponent(nom)}`, data),
  // Colonnes d'une table du foyer (§18.32) : modifier, régler, supprimer, et
  // déclarer l'identifiant naturel.
  modifierColonneBase: (nom, colonne, data) =>
    send("PUT", `/admin/base/tables/${encodeURIComponent(nom)}/colonnes/${encodeURIComponent(colonne)}`, data),
  reglerColonneBase: (nom, colonne, data) =>
    send("PUT", `/admin/base/tables/${encodeURIComponent(nom)}/colonnes/${encodeURIComponent(colonne)}/reglage`, data),
  impactColonneBase: (nom, colonne) =>
    get(`/admin/base/tables/${encodeURIComponent(nom)}/colonnes/${encodeURIComponent(colonne)}/impact`),
  supprimerColonneBase: (nom, colonne) =>
    del(`/admin/base/tables/${encodeURIComponent(nom)}/colonnes/${encodeURIComponent(colonne)}`),
  colonnesTableBase: (nom) => get(`/admin/base/tables/${encodeURIComponent(nom)}/colonnes`),
  uniciteBase: (nom) => get(`/admin/base/tables/${encodeURIComponent(nom)}/unicite`),
  definirUniciteBase: (nom, data) =>
    send("PUT", `/admin/base/tables/${encodeURIComponent(nom)}/unicite`, data),
  enregistrerColonnes: (id, colonnes) => send("PUT", `/admin/categories/${id}/colonnes`, colonnes),
  // Tri d'ouverture du registre pour cette catégorie (§18.49). Un champ vide
  // rend la catégorie à l'héritage : son parent, puis le réglage du foyer.
  enregistrerTriCategorie: (id, tri) => send("PUT", `/admin/categories/${id}/tri`, tri),
  // Le courriel (§21.10) : essai d'envoi et résumés à la demande.
  essaiCourriel: (adresse) => send("POST", "/admin/courriel/essai", { adresse }),
  resumerCourriel: () => send("POST", "/admin/courriel/resumer"),
  // Les automatisations « quand… alors… » (§21.8).
  automatisations: () => get("/admin/automatisations"),
  catalogueAutomatisations: () => get("/admin/automatisations/catalogue"),
  journalAutomatisations: (limite = 100) =>
    get(`/admin/automatisations/journal?limite=${limite}`),
  creerAutomatisation: (charge) => send("POST", "/admin/automatisations", charge),
  modifierAutomatisation: (id, charge) => send("PUT", `/admin/automatisations/${id}`, charge),
  supprimerAutomatisation: (id) => del(`/admin/automatisations/${id}`),
  essayerAutomatisation: (id, documentId) =>
    send("POST", `/admin/automatisations/${id}/essayer?document_id=${documentId}`),
  /** Ce qu'une règle peut remplir pour ce type (§21.11) : de quoi ne pas taper à l'aveugle. */
  champsCibles: (categorieId) =>
    get(`/admin/regles/champs-cibles${categorieId ? `?categorie_id=${categorieId}` : ""}`),
  /** Proposer une règle à partir d'une valeur désignée sur un document (§21.5). */
  apprendreRegle: (payload) => send("POST", "/admin/regles/apprendre", payload),
  /**
   * Les documents sur lesquels apprendre (§22.35) : le dernier mois sans rien
   * taper, la recherche globale à partir de trois caractères, et le type en
   * cours d'édition comme périmètre — sans lui, toute la GED (§22.37).
   */
  exemplesApprentissage: (q = "", categorieId = null) =>
    get(`/admin/regles/exemples?q=${encodeURIComponent(q || "")}`
        + (categorieId ? `&categorie_id=${categorieId}` : "")),
  /**
   * Océriser un fichier **sans l'archiver**, pour écrire une règle sur un
   * document qui n'est pas encore dans la GED (§22.35).
   *
   * `Content-Type` n'est pas posé : le navigateur écrit lui-même la frontière du
   * multipart, et l'imposer à la main casse l'envoi.
   */
  importerExemple: (fichier) => {
    const corps = new FormData();
    corps.append("fichier", fichier);
    return fetch(`${BASE}/admin/regles/exemple-importe`, {
      method: "POST", headers: authHeaders(), body: corps,
    }).then(handle);
  },
  /** L'image de la page d'un exemple importé (§22.35). */
  async apercuExempleBlobUrl(jeton) {
    const res = await fetch(`${BASE}/admin/regles/exemple-importe/${jeton}/apercu`,
                            { headers: authHeaders() });
    if (!res.ok) return handle(res);
    return URL.createObjectURL(await res.blob());
  },
  enregistrerOptionsFiche: (id, options) =>
    send("PUT", `/admin/categories/${id}/fiche`, options),
  // Applique les colonnes d'un type à tous les types de son dossier (§19.7).
  propagerColonnes: (id) => send("POST", `/admin/categories/${id}/colonnes/propager`),
  // Consultation du registre sous l'identité d'un autre compte (§18.50).
  ouvrirConsultation: (utilisateurId) => send("POST", `/admin/consultation/${utilisateurId}`),


  // Règles d'extraction (remplissage auto de colonnes)
  // Jeux de règles d'extraction, par type de document (§19.6).
  jeuxExtraction: (categorieId) =>
    get(`/admin/jeux-extraction${categorieId ? `?categorie_id=${categorieId}` : ""}`),
  creerJeuExtraction: (data) => send("POST", "/admin/jeux-extraction", data),
  modifierJeuExtraction: (id, data) => send("PUT", `/admin/jeux-extraction/${id}`, data),
  supprimerJeuExtraction: (id) => del(`/admin/jeux-extraction/${id}`),
  regles: (profilId) => get(`/admin/regles${profilId ? `?profil_id=${profilId}` : ""}`),
  /** Fonctions prêtes à l'emploi proposées dans une règle (§18.35). */
  fonctionsExtraction: () => get("/admin/regles/fonctions"),
  creerRegle: (data) => send("POST", "/admin/regles", data),
  modifierRegle: (id, data) => send("PUT", `/admin/regles/${id}`, data),
  supprimerRegle: (id) => del(`/admin/regles/${id}`),

  // Utilisateurs
  utilisateurs: () => get("/admin/utilisateurs"),
  creerUtilisateur: (data) => send("POST", "/admin/utilisateurs", data),
  modifierUtilisateur: (id, data) => send("PUT", `/admin/utilisateurs/${id}`, data),
  supprimerUtilisateur: (id) => del(`/admin/utilisateurs/${id}`),
  reinitialiserOtp: (id) => send("POST", `/admin/utilisateurs/${id}/otp/reinitialiser`),

  // Administration de la base (§17)
  typesColonnes: () => get("/admin/base/types-colonnes"),
  tablesBase: () => get("/admin/base/tables"),
  colonnesBase: (table) => get(`/admin/base/tables/${encodeURIComponent(table)}/colonnes`),
  lignesBase: (table, params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== null)
    ).toString();
    return get(`/admin/base/tables/${encodeURIComponent(table)}/lignes${qs ? `?${qs}` : ""}`);
  },
  creerTableBase: (data) => send("POST", "/admin/base/tables", data),
  supprimerTableBase: (table) => del(`/admin/base/tables/${encodeURIComponent(table)}`),
  ajouterColonneBase: (table, data) =>
    send("POST", `/admin/base/tables/${encodeURIComponent(table)}/colonnes`, data),
  creerLigneBase: (table, valeurs) =>
    send("POST", `/admin/base/tables/${encodeURIComponent(table)}/lignes`, { valeurs }),
  modifierLigneBase: (table, id, valeurs) =>
    send("PUT", `/admin/base/tables/${encodeURIComponent(table)}/lignes/${id}`, { valeurs }),
  supprimerLigneBase: (table, id) =>
    del(`/admin/base/tables/${encodeURIComponent(table)}/lignes/${id}`),

  // Surveillance des connexions (limitation de la force brute)
  connexions: () => get("/admin/connexions"),
  deverrouillerConnexion: (cle) => send("POST", "/admin/connexions/deverrouiller", { cle }),
  toutDeverrouiller: () => send("POST", "/admin/connexions/tout-deverrouiller"),

  // Tableaux de bord personnalisés
  tableaux: () => get("/admin/tableaux-de-bord"),
  creerTableau: (data) => send("POST", "/admin/tableaux-de-bord", data),
  modifierTableau: (id, data) => send("PUT", `/admin/tableaux-de-bord/${id}`, data),
  supprimerTableau: (id) => del(`/admin/tableaux-de-bord/${id}`),

  // Journal d'audit : consultation, plus une purge en bloc de l'ancien.
  // Aucune entrée ne se supprime individuellement — voir app/admin.py.
  auditActions: () => get("/admin/audit/actions"),
  audit: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== null)
    ).toString();
    return get(`/admin/audit${qs ? `?${qs}` : ""}`);
  },
  apercuPurgeAudit: (avant) => get(`/admin/audit/purge-apercu?avant=${encodeURIComponent(avant)}`),
  purgerAudit: (avant) => del(`/admin/audit?avant=${encodeURIComponent(avant)}`),

  // Serveur de travaux
  jobs: (statut, categorieId) => {
    const parametres = new URLSearchParams();
    if (statut) parametres.set("statut", statut);
    if (categorieId) parametres.set("categorie_id", categorieId);
    const suite = parametres.toString();
    return get(`/admin/jobs${suite ? `?${suite}` : ""}`);
  },
  // `categorieId` restreint le compte par état au type retenu : une pastille qui
  // annonce un nombre différent de la liste affichée est pire que pas de nombre.
  resumeJobs: (categorieId) =>
    get(`/admin/jobs/resume${categorieId ? `?categorie_id=${categorieId}` : ""}`),
  etapesRejeu: () => get("/admin/jobs/etapes"),
  rejouerJob: (id, etape) =>
    send("POST", `/admin/jobs/${id}/rejouer${etape ? `?etape=${encodeURIComponent(etape)}` : ""}`),
  actionsGroupeesJobs: (ids, action, etape) =>
    send("POST", "/admin/jobs/actions", { ids, action, etape: etape || null }),
  supprimerJob: (id) => del(`/admin/jobs/${id}`),
  /** Le mode développeur (§21.14) : scripts, exécution, historique. */
  scripts: () => get("/admin/scripts"),
  creerScript: (data) => send("POST", "/admin/scripts", data),
  modifierScript: (id, data) => send("PUT", `/admin/scripts/${id}`, data),
  supprimerScript: (id) => del(`/admin/scripts/${id}`),
  executerScript: (id, data) => send("POST", `/admin/scripts/${id}/executer`, data),
  executionsScript: () => get("/admin/scripts/executions"),
  /** Les rapprochements déclarés sur un type de document (§22.8). */
  liensTypes: (categorieId) =>
    get(`/admin/liens-types${categorieId ? `?categorie_id=${categorieId}` : ""}`),
  declarerLienType: (data) => send("POST", "/admin/liens-types", data),
  retirerLienType: (id) => del(`/admin/liens-types/${id}`),
  /** Ce que l'administration autorise à rattacher (§22.4). */
  pairesRattachement: () => get("/admin/rattachements-types"),
  declarerPaireRattachement: (data) => send("POST", "/admin/rattachements-types", data),
  retirerPaireRattachement: (id) => del(`/admin/rattachements-types/${id}`),
  /**
   * Le fichier reçu, tel qu'il a été déposé (§18.53) — et non le PDF archivé,
   * que l'océrisation et la compression ont réécrit. Rendu comme URL d'objet,
   * à révoquer après usage.
   */
  async originalBlobUrl(jobId) {
    const res = await fetch(`${BASE}/admin/jobs/${jobId}/fichier`, { headers: authHeaders() });
    if (!res.ok) return handle(res);
    return URL.createObjectURL(await res.blob());
  },

  /**
   * Copie de secours (§22.49) : où l'on en est, en déclencher une, en effacer une.
   * L'écran ne sauvegarde pas lui-même — c'est le serveur de travaux qui écrit.
   */
  sauvegardes: () => get("/admin/sauvegardes"),
  sauvegarderMaintenant: () => send("POST", "/admin/sauvegardes"),
  supprimerSauvegarde: (nom) => del(`/admin/sauvegardes/${encodeURIComponent(nom)}`),

  // Champs attendus par catégorie (obligatoires / facultatifs)
  champsDisponibles: () => get("/admin/champs-disponibles"),
  /** Ce qu'un champ libre peut être (§22.12) : texte, date, montant… */
  typesDeChamp: () => get("/admin/types-de-champ"),
  reglesChamps: (categorieId) =>
    get(`/admin/regles-champs${categorieId ? `?categorie_id=${categorieId}` : ""}`),
  creerRegleChamp: (data) => send("POST", "/admin/regles-champs", data),
  modifierRegleChamp: (id, data) => send("PUT", `/admin/regles-champs/${id}`, data),
  supprimerRegleChamp: (id) => del(`/admin/regles-champs/${id}`),

  // Corbeille des fichiers archivés (admin uniquement)
  corbeille: ({ limite = 25, decalage = 0 } = {}) =>
    get(`/admin/corbeille?limite=${limite}&decalage=${decalage}`),
  stockage: () => get("/admin/stockage"),
  // Dépôt : ce qui s'y trouve sans y avoir sa place (§19.5).
  anomaliesDepot: () => get("/admin/depots/anomalies"),
  rangerFichierEgare: (chemin, categorieId) =>
    send("POST", "/admin/depots/ranger", { chemin, categorie_id: categorieId }),
  retirerDuDepot: (chemin) => send("POST", "/admin/depots/retirer", { chemin }),

  // Sources proposables pour un champ personnalisé : tables du foyer et comptes.
  sourcesChamps: () => get("/admin/sources-champs"),

  // Export de l'archive (§17.30). Deux temps : on prouve son identité, on
  // obtient un jeton ; on télécharge, et le jeton ne vaut plus rien.
  demanderExport: (motDePasse, codeOtp) =>
    send("POST", "/admin/export", { mot_de_passe: motDePasse, code_otp: codeOtp || null }),
  async telechargerExport(jeton, nomPropose) {
    const res = await fetch(`${BASE}/admin/export/${jeton}`, { headers: authHeaders() });
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).detail; } catch { detail = ""; }
      throw new Error(t(detail) || t("Téléchargement impossible ({code})", { code: res.status }));
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const lien = document.createElement("a");
    lien.href = url;
    lien.download = nomPropose || "homeged-export.zip";
    lien.click();
    URL.revokeObjectURL(url);
  },
  supprimerFichierCorbeille: (chemin) =>
    del(`/admin/corbeille/fichier?chemin=${encodeURIComponent(chemin)}`),
  viderCorbeille: () => send("POST", "/admin/corbeille/vider"),
  // L'intégrité des archives (§21.3) : ce que valent les fichiers stockés.
  integrite: () => get("/admin/integrite"),
  controlerIntegrite: () => send("POST", "/admin/integrite/controler"),
  // Les documents supprimés du registre (§21.1) — l'administration les voit
  // tous, y compris ceux que leur auteur a retirés de sa propre corbeille.
  documentsSupprimes: () => get("/admin/documents-supprimes"),
  restaurerDocumentSupprime: (id) =>
    send("POST", `/admin/documents-supprimes/${id}/restaurer`),
  effacerDocumentDefinitivement: (id) => del(`/admin/documents-supprimes/${id}`),
  async fichierCorbeilleBlobUrl(chemin) {
    const res = await fetch(
      `${BASE}/admin/corbeille/fichier?chemin=${encodeURIComponent(chemin)}`,
      { headers: authHeaders() }
    );
    if (!res.ok) throw new Error(`Téléchargement impossible (HTTP ${res.status})`);
    return URL.createObjectURL(await res.blob());
  },

  // Rôles & droits par catégorie
  roles: () => get("/admin/roles"),
  creerRole: (data) => send("POST", "/admin/roles", data),
  supprimerRole: (id) => del(`/admin/roles/${id}`),
  // Les trois axes des droits partent ensemble (§19.12) : ils se règlent sur le
  // même écran, et un enregistrement partiel laisserait un rôle à moitié changé.
  definirDroits: (roleId, droits) => send("PUT", `/admin/roles/${roleId}/droits`, droits),
  catalogueDroits: () => get("/admin/droits/catalogue"),
};
