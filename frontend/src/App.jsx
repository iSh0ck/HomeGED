import React, { useEffect, useRef, useState, useCallback } from "react";
import { Layers, Plus } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import Toolbar from "./components/Toolbar.jsx";
import DocumentsTable from "./components/DocumentsTable.jsx";
import ZoneDepotFiche from "./components/ZoneDepotFiche.jsx";
import CorbeillePage, { BoutonCorbeille } from "./pages/CorbeillePage.jsx";
import EcheancesPage, { BoutonRappels } from "./pages/EcheancesPage.jsx";
import ResultatsRecherche from "./components/ResultatsRecherche.jsx";
import Arborescence, { FilRepli } from "./components/Arborescence.jsx";
import DocumentPanel from "./components/DocumentPanel.jsx";
import BarreSelection from "./components/BarreSelection.jsx";
import ExporterSelection from "./components/ExporterSelection.jsx";
import AjouterEntree from "./components/AjouterEntree.jsx";
import Liste from "./components/champs/Liste.jsx";
import VersionsDocument from "./components/VersionsDocument.jsx";
import BarriereErreur from "./components/BarriereErreur.jsx";
import ModifierSelection from "./components/ModifierSelection.jsx";
import { estActif, versCriteres } from "./components/ColumnFilter.jsx";
import { libelleDuChamp } from "./lib/criteres";
import EnregistrerVue from "./components/EnregistrerVue.jsx";
import ConfirmerSuppression from "./components/ConfirmerSuppression.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import InstallationPage from "./pages/InstallationPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import { vueDuChemin, ecrireChemin } from "./lib/navigation";
import BandeauConsultation from "./components/BandeauConsultation.jsx";
import { consultationEnCours, quitterConsultation } from "./api";
import AnalysePage from "./pages/AnalysePage.jsx";
import ComptePage from "./pages/ComptePage.jsx";
import AlerteModale from "./components/AlerteModale.jsx";
import ObligationOtpPage from "./pages/ObligationOtpPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import { useAuth } from "./auth/AuthContext.jsx";
import { api } from "./api";
import { definirFuseau } from "./lib/horodatage";
import { appliquerApparence, poserThemesAjoutes } from "./lib/apparence";
import { definirLangue, poserLanguesAjoutees, t } from "./lib/langue";
import { useEcran } from "./lib/ecran";

const PAR_PAGE_DEFAUT = 50;

// Le nombre de caractères à partir duquel on cherche un document (§22.26).
// Le même partout : registre, sélecteurs de champs « documents ». Un seuil qui
// change d'un écran à l'autre s'apprend deux fois.
const MIN_RECHERCHE = 3;


export default function App() {
  const { user, chargement, logout, rafraichir } = useAuth();
  // Base vierge : on propose l'installation au lieu d'un écran de connexion
  // devant lequel personne ne pourrait entrer (§18.23).
  const [installation, setInstallation] = useState(undefined);
  // Apparence lisible sans être connecté : sans elle, un foyer en thème sombre
  // recevrait un écran de connexion éclatant de blanc, et sans son nom.
  const [apparence, setApparence] = useState({});
  // Consultation sous une autre identité (§18.50) : lue une fois, elle ne change
  // qu'au prix d'un rechargement de la page.
  const consultation = consultationEnCours();

  useEffect(() => {
    api.apparence().then((a) => {
      // Les palettes et les traductions déposées par le foyer arrivent avec
      // l'apparence publique (§22.50, §22.51) : l'écran de connexion doit déjà
      // être dans la bonne langue et la bonne couleur, pas les prendre après.
      poserThemesAjoutes(a.themes);
      poserLanguesAjoutees(a.langues);
      // Ce que le foyer a réglé — « auto » par défaut, qui suit le navigateur.
      // Rien du tout laisse la langue en place plutôt que de la deviner.
      definirLangue(a.langue);
      setApparence(a);
      appliquerApparence(a);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (user) { setInstallation(null); return; }
    api.etatInstallation()
      .then((e) => setInstallation(e.requise ? e : null))
      .catch(() => setInstallation(null));
  }, [user]);

  if (chargement || installation === undefined) return null;
  if (!user && installation) {
    return <InstallationPage etat={installation} onInstalle={() => {
      setInstallation(null);
      rafraichir();
    }} />;
  }
  if (!user) return <LoginPage nomFoyer={apparence.nom_foyer} />;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100dvh" }}>
      {/* Le bandeau est posé au-dessus de tous les écrans, et non dans chacun :
          pendant une consultation, l'interface se replie sur les droits du
          compte consulté et peut ne plus proposer de retour vers
          l'administration. Le moyen d'en sortir doit survivre à cela. */}
      <BandeauConsultation
        consultation={consultation}
        onQuitter={() => {
          quitterConsultation();
          // Rechargement franc : l'identité change, tout ce qui est en mémoire
          // porte sur quelqu'un d'autre.
          window.location.assign("/admin");
        }}
      />
      <div style={{ flex: 1, minHeight: 0 }}>
        <RegistreDocuments user={user} onLogout={logout} />
      </div>
    </div>
  );
}

function RegistreDocuments({ user, onLogout }) {
  // Un compte à qui la double authentification est imposée n'a accès qu'à sa
  // configuration : inutile de réclamer des référentiels que l'API refusera.
  const aConfigurerOtp = Boolean(user?.otp_impose && !user?.otp_actif);

  const [documents, setDocuments] = useState([]);
  const [categories, setCategories] = useState([]);
  const [vues, setVues] = useState([]);
  const [vueActive, setVueActive] = useState(null);
  const [enregistrementVue, setEnregistrementVue] = useState(false);
  // Sortir une sélection rangée selon un modèle (§21.13) : ce que l'on donne au
  // comptable, par opposition à l'export de secours qui sort tout le foyer.
  const [exportOuvert, setExportOuvert] = useState(false);
  // Téléphone et tablette (§22.52) : la navigation se replie en tiroir.
  const ecran = useEcran();
  const [tiroirOuvert, setTiroirOuvert] = useState(false);
  // Ajouter une entrée à la main dans une fiche simple (§22.7) : ce qu'un foyer
  // garde et qui n'a pas toujours de papier.
  const [ajoutEntree, setAjoutEntree] = useState(false);
  // D'où l'on venait en ouvrant un écran de passage — Centre d'analyse, corbeille,
  // échéances (§22.17). En revenir « au registre » par défaut ramenait sur
  // « tous les documents », c'est-à-dire nulle part : trois colonnes qui ne
  // correspondent à aucune vue, alors qu'on regardait ses factures.
  const [ecranPrecedent, setEcranPrecedent] = useState("accueil");
  const [suppression, setSuppression] = useState(null); // document en attente de confirmation

  const [query, setQuery] = useState("");
  const [filtreCategorie, setFiltreCategorie] = useState(undefined);

  // Filtres de colonne : { [champ]: { operateur, valeur } }. Même format que
  // celui attendu par l'API et que celui des vues enregistrées.
  const [filtresColonnes, setFiltresColonnes] = useState({});
  // Tri et pagination sont désormais faits par la base : ils portent sur tout
  // le registre, et non sur la seule page déjà chargée.
  const [tri, setTri] = useState({ colonne: "date_import", sens: "desc" });
  const [decalage, setDecalage] = useState(0);
  const [parPage, setParPage] = useState(PAR_PAGE_DEFAUT);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  // Colonnes propres à chaque catégorie (§18.1), chargées une fois pour toutes :
  // changer de catégorie ne doit pas faire clignoter le tableau.
  const [colonnesParCategorie, setColonnesParCategorie] = useState({});
  // Tri d'ouverture de chaque catégorie (§18.49), réglé depuis l'administration.
  const [trisParCategorie, setTrisParCategorie] = useState({});
  // Réglages du foyer : écran d'ouverture, lignes par page, nom affiché (§18.24).
  const [reglages, setReglages] = useState(null);
  // Sélection multiple (§18.3). Elle vit ici, et non dans le tableau : elle
  // traverse les pages et sert à la barre d'outils comme à la modification en
  // série.
  const [selection, setSelection] = useState([]);
  const [modificationSerie, setModificationSerie] = useState(null);
  // Document dont on consulte l'historique des dépôts (§18.36).
  const [versionsDe, setVersionsDe] = useState(null);
  const [suppressionMultiple, setSuppressionMultiple] = useState(null);
  const [actualisation, setActualisation] = useState(false);
  // L'écran affiché vient de l'adresse (§18.48) : /admin s'ouvre dans son propre
  // onglet, se met en marque-page, et se filtre depuis un proxy en amont.
  const [vue, setVue] = useState(() => vueDuChemin(window.location.pathname));
  const [tableaux, setTableaux] = useState([]);
  const [tableauActif, setTableauActif] = useState("accueil");
  const [nbAAnalyser, setNbAAnalyser] = useState(0);
  // Ce que j'ai supprimé et qui n'est pas encore perdu (§21.1). Le compteur est
  // ce qui fait exister la corbeille : sans lui, personne n'y va jamais.
  const [nbCorbeille, setNbCorbeille] = useState(0);
  // Rappels non lus (§21.9) : le compteur est ce qui fait exister les échéances.
  const [nbRappels, setNbRappels] = useState(0);
  // Recherche globale (§21.2) : `perimetre` dit où chercher, `resultats` est ce
  // qu'on a trouvé — nul tant qu'aucune recherche n'a abouti, ce qui laisse le
  // tableau à sa place.
  const [perimetre, setPerimetre] = useState("tout");
  const [resultats, setResultats] = useState(null);
  const [rechercheEnCours, setRechercheEnCours] = useState(false);
  // Le repli en arborescence (§21.6). `replis` sont les champs sur lesquels on
  // descend, `chemin` les branches déjà choisies. Tant que le chemin n'a pas
  // atteint le dernier champ, on montre des branches ; ensuite, le tableau.
  const [replis, setReplis] = useState([]);
  const [chemin, setChemin] = useState([]);
  const [branches, setBranches] = useState(null);
  const [branchesEnCours, setBranchesEnCours] = useState(false);

  // Déclarés ici, et non plus bas avec le reste de l'affichage : le tableau de
  // dépendances de la recherche les lit **pendant le rendu**.
  const categorieOuverte = categories.find((c) => c.id === filtreCategorie);

  /**
   * Où l'on retombe en quittant un écran de passage (§22.80).
   *
   * Jamais « tous les documents » : c'est une vue qui ne correspond à rien —
   * trois colonnes communes à des types qui n'ont rien à voir —, et l'on y
   * atterrissait en revenant de l'administration. Le registre n'est une
   * destination que **s'il montre quelque chose** : une catégorie ouverte, ou
   * une vue enregistrée. Sinon, l'accueil, qui est la page du foyer.
   */
  const retourNaturel = () => {
    const precedent = ecranPrecedent || "accueil";
    if (precedent !== "registre") return precedent;
    return (filtreCategorie != null || vueActive != null) ? "registre" : "accueil";
  };
  // On ne propose que des périmètres qui veulent dire quelque chose ici : sans
  // classement ouvert, « ce classement » n'a pas de sens, et sans filtre actif,
  // « cette vue » est le même ensemble que le classement (§21.2).
  const perimetresPossibles = [
    { cle: "tout", libelle: t("Toute la GED") },
    ...(categorieOuverte
      ? [{ cle: "classement", libelle: `Dans ${categorieOuverte.nom}` }] : []),
    ...(Object.values(filtresColonnes).filter(estActif).length
      ? [{ cle: "vue", libelle: t("Dans la vue en cours") }] : []),
  ];
  // Le périmètre choisi peut cesser d'exister — on ferme le classement, on
  // efface les filtres. Il retombe alors sur « toute la GED » plutôt que de
  // chercher dans un ensemble qui n'est plus affiché.
  const perimetreEffectif = perimetresPossibles.some((p) => p.cle === perimetre)
    ? perimetre : "tout";
  const [erreur, setErreur] = useState(null);
  // La gestion du compte se superpose à l'écran courant : on y règle deux ou
  // trois choses et on revient à ce qu'on faisait, sans perdre sa recherche.
  const [compteOuvert, setCompteOuvert] = useState(false);

  const charger = useCallback(() => {
    if (aConfigurerOtp) return;
    // Les filtres de colonne sont appliqués par l'API (et non sur les seuls
    // documents déjà chargés) : la recherche porte donc sur tout le registre.
    // Les branches parcourues sont des critères comme les autres : le tableau
    // n'a rien de particulier à savoir du repli (§21.6).
    // `chemin` ne sert plus qu'au fil d'ariane et au niveau de repli suivant :
    // ses critères ont rejoint les filtres de colonne en descendant, et les
    // compter deux fois les afficherait deux fois.
    const criteres = versCriteres(filtresColonnes);

    // categorie_id (et non le nom) : l'API remonte alors aussi les documents
    // des sous-catégories, ce qui fait fonctionner les sections de la navigation.
    api
      .documents({
        categorie_id: filtreCategorie,
        filtres: criteres.length ? JSON.stringify(criteres) : undefined,
        tri: tri.colonne,
        sens: tri.sens,
        limite: parPage,
        decalage,
      })
      .then(({ documents, total }) => {
        setDocuments(documents);
        setTotal(total);
        setErreur(null);
      })
      .catch((e) => setErreur(e.message))
      .finally(() => setActualisation(false));
  }, [filtreCategorie, filtresColonnes, tri, decalage, parPage, aConfigurerOtp]);

  // Le champ du niveau où l'on se trouve : rien à charger une fois qu'on est
  // descendu au bout, c'est le tableau qui prend la suite.
  const champReplié = replis[chemin.length] || null;

  useEffect(() => {
    if (!champReplié) { setBranches(null); return undefined; }
    let vivant = true;
    setBranchesEnCours(true);
    api.groupes(champReplié, {
      categorieId: filtreCategorie,
      filtres: versCriteres(filtresColonnes),
    })
      .then((reponse) => vivant && setBranches(reponse.branches || []))
      .catch((e) => { if (vivant) { setErreur(e.message); setBranches([]); } })
      .finally(() => vivant && setBranchesEnCours(false));
    return () => { vivant = false; };
  }, [champReplié, filtreCategorie, filtresColonnes, chemin]);

  /**
   * La recherche globale, temporisée (§21.2).
   *
   * Elle ne part qu'après une pause de frappe : une requête par caractère ferait
   * travailler le serveur pour des mots que personne n'a fini d'écrire. Et elle
   * ne remplace le tableau qu'une fois **aboutie** — sans quoi la liste
   * disparaîtrait sous les doigts au premier caractère.
   *
   * Trois caractères depuis le §22.26, comme les sélecteurs de documents : deux
   * lettres ramènent une part énorme de la GED, que personne ne lit et que la
   * base a calculée pour rien. Le seuil est le même partout où l'on cherche un
   * document — un seuil qui change d'un écran à l'autre s'apprend deux fois.
   */
  useEffect(() => {
    const terme = query.trim();
    if (terme.length < MIN_RECHERCHE) {
      setResultats(null);
      setRechercheEnCours(false);
      return undefined;
    }
    setRechercheEnCours(true);
    const attente = setTimeout(() => {
      api.recherche(terme, perimetreEffectif, {
        categorieId: perimetreEffectif === "tout" ? undefined : filtreCategorie,
        filtres: perimetreEffectif === "vue" ? versCriteres(filtresColonnes) : undefined,
      })
        .then((reponse) => setResultats(reponse.resultats || []))
        .catch((e) => { setErreur(e.message); setResultats([]); })
        .finally(() => setRechercheEnCours(false));
    }, 280);
    return () => clearTimeout(attente);
  }, [query, perimetreEffectif, filtreCategorie, filtresColonnes]);

  // un changement de critère ou de tri invalide la page courante
  useEffect(() => { setDecalage(0); }, [query, filtreCategorie, filtresColonnes, tri]);

  /**
   * Les seuls compteurs, sans les référentiels (§22.32).
   *
   * « 3 à analyser » vieillit tout seul : un dépôt traité pendant qu'on lit le
   * registre ne changeait rien à l'écran, et l'on n'allait au Centre d'analyse
   * que par hasard. Les catégories et les vues, elles, ne bougent qu'au moment
   * où quelqu'un les change — les relire en boucle serait du bruit.
   */
  const rafraichirCompteurs = useCallback(() => {
    if (aConfigurerOtp) return;
    api.compteurs()
      .then((c) => {
        setNbAAnalyser((c.a_analyser || 0) + (c.a_classer || 0));
        setNbCorbeille(c.corbeille || 0);
        setNbRappels(c.rappels || 0);
      })
      .catch(() => {});
  }, [aConfigurerOtp]);

  useEffect(() => {
    // Dix secondes, comme le Centre d'analyse (§22.32) : un document déposé met
    // ce temps-là à devenir un document, et le voir apparaître en haut du
    // registre sans recharger la page est tout l'intérêt du compteur (§22.39).
    // Une requête de quatre `COUNT` le permet ; les quatre listes d'avant, non.
    // L'onglet en arrière-plan ne demande rien, et le retour au premier plan
    // relit tout de suite plutôt que d'attendre le battement suivant.
    const battement = setInterval(() => {
      if (!document.hidden) rafraichirCompteurs();
    }, 10000);
    const auRetour = () => { if (!document.hidden) rafraichirCompteurs(); };
    document.addEventListener("visibilitychange", auRetour);
    return () => {
      clearInterval(battement);
      document.removeEventListener("visibilitychange", auRetour);
    };
  }, [rafraichirCompteurs]);

  const chargerReferentiels = useCallback(() => {
    if (aConfigurerOtp) return;
    api.categories().then(setCategories).catch((e) => setErreur(e.message));
    api.vues().then(setVues).catch((e) => setErreur(e.message));
    // Le compteur réunit les deux natures que le Centre d'analyse traite : les
    // documents incomplets et les fichiers sans type (§19.4). En annoncer une
    // seule laisserait l'autre invisible tant que personne n'ouvre l'écran.
    rafraichirCompteurs();
    api.tableauxDeBord().then(setTableaux).catch(() => {});
    api.colonnesCategories().then((reponse) => {
      setColonnesParCategorie(reponse.colonnes || {});
      setTrisParCategorie(reponse.tris || {});
    }).catch(() => {});
    // Les réglages du foyer décident de la lecture des heures (§18.19) et de
    // l'apparence (§18.24). Réclamés avec les référentiels : ils sont aussi
    // structurants qu'eux.
    api.reglages().then((r) => {
      definirFuseau(r.fuseau_horaire);
      setReglages(r);
    }).catch(() => {});
  }, [aConfigurerOtp, rafraichirCompteurs]);

  /**
   * Applique les critères d'une vue enregistrée aux filtres de colonne. Les
   * critères « egal » sur une catégorie ou un émetteur portent un identifiant :
   * on y rattache le libellé connu pour que le tableau affiche un nom lisible
   * plutôt qu'un numéro.
   */
  const appliquerVue = useCallback((vue) => {
    const libelle = (champ, valeur) => {
      const source = champ === "categorie" ? categories : null;
      return source?.find((e) => String(e.id) === String(valeur))?.nom;
    };
    const filtres = {};
    for (const critere of vue.criteres || []) {
      filtres[critere.champ] = {
        operateur: critere.operateur,
        valeur: critere.valeur,
        ...(critere.operateur === "egal" && libelle(critere.champ, critere.valeur)
          ? { libelle: libelle(critere.champ, critere.valeur) }
          : {}),
      };
    }
    setFiltresColonnes(filtres);
    setFiltreCategorie(undefined); // le filtrage vient entièrement de la vue
    setQuery("");
    setVueActive(vue.id);
    setSelectedId(null);          // voir `choisirCategorie` : on change de liste
    setSelection([]);   // on ne garde pas une sélection faite ailleurs
    // La vue apporte son repli (§21.6) ; on repart de sa racine, sinon on
    // afficherait la branche d'une autre vue sous un autre nom.
    setReplis(vue.groupement || []);
    setChemin([]);
  }, [categories]);

  /** Descendre d'une branche : son critère s'ajoute au chemin. */
  function descendre(branche) {
    setChemin([...chemin, { champ: champReplié, valeur: branche.valeur,
                            libelle: branche.libelle, critere: branche.critere }]);
    // Le critère de la branche rejoint les filtres de colonne : descendre dans
    // « Émetteur : Orange » **est** un filtre, et le tableau doit le montrer là
    // où on le lit et le corrige — sans quoi on cherche pourquoi la liste est
    // courte alors que les champs de recherche sont vides.
    setFiltresColonnes((courants) => ({
      ...courants,
      [branche.critere.champ]: {
        operateur: branche.critere.operateur,
        valeur: branche.critere.valeur,
        libelle: branche.libelle,
      },
    }));
    setSelectedId(null);
    setDecalage(0);
  }

  /** Remonter au niveau `index` (-1 : tout en haut). */
  function remonter(index) {
    const abandonnees = chemin.slice(index + 1);
    setChemin(chemin.slice(0, index + 1));
    // Les critères des branches qu'on quitte s'en vont avec elles : ils avaient
    // été posés dans les filtres de colonne en descendant.
    setFiltresColonnes((courants) => {
      const suite = { ...courants };
      for (const etape of abandonnees) delete suite[etape.critere.champ];
      return suite;
    });
    setSelectedId(null);
    setDecalage(0);
  }

  /**
   * Change la sélection.
   *
   * Une sélection vide referme la fiche : sans cela, décocher la dernière ligne
   * laissait le panneau ouvert sur un document que plus rien ne désignait, et la
   * barre d'outils disparaissait en même temps — on se retrouvait devant une
   * fiche sans aucun moyen d'agir dessus. Toutes les façons de vider la
   * sélection passent par ici : les cases à cocher, le reclic sur une ligne,
   * « tout décocher ».
   */
  function majSelection(suivante) {
    const liste = typeof suivante === "function" ? suivante(selection) : suivante;
    setSelection(liste);
    if (!liste.length) setSelectedId(null);
    return liste;
  }

  /**
   * Sélectionne une catégorie dans la navigation.
   *
   * Les filtres de colonne sont **effacés**. Sans cela, revenir de la vue
   * « Toutes les factures du foyer » à la catégorie « Factures » gardait les
   * critères de la vue : on croyait voir toute la catégorie, on n'en voyait
   * qu'une part, et rien à l'écran ne disait pourquoi. Choisir une catégorie,
   * c'est demander à la voir entière.
   */
  function choisirCategorie(id) {
    setFiltresColonnes({});
    setQuery("");
    // La fiche ouverte se referme : elle appartenait à ce qu'on regardait, et la
    // laisser ouverte sur un document absent de la nouvelle liste donne à croire
    // qu'il en fait partie.
    setSelectedId(null);
    setFiltreCategorie(id);
    setVueActive(null);
    setSelection([]);
    setReplis([]);
    setChemin([]);
  }

  /**
   * Tout ce qui concerne la même chose (§22).
   *
   * Le critère de lien réunit **tous** les champs qui la désignent : « véhicule
   * concerné » ici, « propriétaire » là. C'est ce que l'arbre des dossiers ne
   * sait pas dire, et c'est pour cela que le filtre ne porte pas sur un champ.
   *
   * Le classement est relâché au passage : on demande tout ce qui parle de cette
   * chose-là, or le reste est presque toujours d'un autre type — c'est justement
   * ce qu'on venait chercher.
   */
  function ouvrirLien(lien) {
    setFiltreCategorie(undefined);
    setVueActive(null);
    setReplis([]);
    setChemin([]);
    setQuery("");
    setFiltresColonnes({
      [lien.champ]: { operateur: "egal", valeur: lien.valeur, libelle: lien.libelle },
    });
    setSelectedId(null);
    setSelection([]);
    setVue("registre");
  }

  /**
   * Relie entre elles les fiches cochées (§22.4).
   *
   * Le rapprochement par valeur partagée réunit ce qui désigne la même chose ;
   * ceci relie ce qui ne partage rien et se répond quand même — un contrat et
   * son avenant. Le geste naturel est de cocher les papiers qui vont ensemble
   * puis de le dire : chercher l'autre dans une fenêtre demanderait de le
   * retrouver alors qu'on vient de le voir.
   *
   * Toutes les paires, et non une étoile autour de la première : trois documents
   * cochés se répondent tous les trois, et n'en relier que deux ferait dépendre
   * le résultat de l'ordre des clics.
   */
  async function rattacherLaSelection() {
    const ids = [...selection];
    try {
      for (let i = 0; i < ids.length; i += 1) {
        for (let j = i + 1; j < ids.length; j += 1) {
          await api.rattacher(ids[i], ids[j]);
        }
      }
      setErreur(null);
      // La fiche ouverte doit montrer ce qu'on vient de lui attacher.
      setSelectedId((courant) => courant);
      charger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  /**
   * Suivre un lien déclaré sur la vue (§22.5).
   *
   * La correspondance de champs d'EzGED : on lit une valeur sur la ligne qu'on
   * regarde, on ouvre l'autre vue filtrée dessus. Le lien ne produit qu'un
   * **critère ordinaire** — rien ne change côté droits, pagination ou recherche,
   * et c'est pourquoi il tient en si peu de lignes.
   */
  function suivreLienDeVue(lien, valeur) {
    const cible = vues.find((v) => v.id === lien.vue_id);
    if (!cible || valeur === undefined || valeur === null || valeur === "") return;
    appliquerVue(cible);
    setFiltresColonnes((courants) => ({
      ...courants,
      [lien.champ_cible]: { operateur: "egal", valeur: String(valeur) },
    }));
    setSelectedId(null);
    setVue("registre");
  }

  /** Ouvre le registre en appliquant les critères d'un indicateur cliqué. */
  function ouvrirRegistre(criteres = []) {
    const filtres = {};
    for (const critere of criteres) {
      filtres[critere.champ] = { operateur: critere.operateur || "contient", valeur: critere.valeur };
    }
    setFiltresColonnes(filtres);
    setFiltreCategorie(undefined);
    setQuery("");
    setVueActive(null);
    setVue("registre");
  }

  async function confirmerSuppression(doc) {
    await api.supprimerDocument(doc.id);
    if (selectedId === doc.id) setSelectedId(null); // le panneau porterait sur un document disparu
    setSuppression(null);
    charger();
  }

  /**
   * Relit la vue en cours. Le registre se recharge de lui-même quand un critère
   * change, mais pas quand c'est le monde extérieur qui bouge : un dépôt traité
   * par le serveur de travaux, une fiche corrigée depuis un autre poste.
   */
  function actualiser() {
    setActualisation(true);
    charger();
    chargerReferentiels();
  }

  async function confirmerSuppressionMultiple() {
    // Une par une : l'API n'a pas de suppression en lot, et l'enchaînement
    // laisse au moins les premières aboutir si l'une d'elles échoue.
    for (const id of suppressionMultiple) {
      await api.supprimerDocument(id);
      if (selectedId === id) setSelectedId(null);
    }
    majSelection(selection.filter((id) => !suppressionMultiple.includes(id)));
    setSuppressionMultiple(null);
    charger();
  }

  async function enregistrerVue(donnees) {
    await api.creerVue(donnees);
    setVues(await api.vues());
  }

  useEffect(chargerReferentiels, [chargerReferentiels]);

  // Réglages d'ouverture, appliqués une seule fois : les rejouer à chaque
  // changement ramènerait l'utilisateur à l'accueil pendant qu'il travaille.
  const reglagesAppliques = useRef(false);
  const premierRendu = useRef(true);
  useEffect(() => {
    if (!reglages || reglagesAppliques.current) return;
    reglagesAppliques.current = true;
    // ... mais pas si l'adresse demandait autre chose : ouvrir /admin dans un
    // onglet ne doit pas retomber sur le registre une seconde plus tard.
    if (reglages.ecran_accueil === "registre" && window.location.pathname === "/") {
      setVue("registre");
    }
  }, [reglages]);

  /**
   * Le nombre de lignes du registre : **le compte prime sur le foyer** (§22.44).
   *
   * Le réglage du foyer donne le départ ; la préférence de compte le remplace
   * pour celui qui l'a posée — le nombre dépend de l'écran devant lequel on est
   * assis, pas du foyer. Rejoué quand la préférence change, et non une fois pour
   * toutes : la modifier depuis son profil doit valoir tout de suite.
   */
  useEffect(() => {
    const lignes = Number(user?.lignes_par_page) || Number(reglages?.lignes_par_page);
    if (Number.isFinite(lignes) && lignes > 0) setParPage(lignes);
  }, [user?.lignes_par_page, reglages?.lignes_par_page]);

  /**
   * Palette et langue : **le compte prime sur le foyer** (§22.50, §22.51).
   *
   * Le foyer donne le départ ; chacun peut le remplacer depuis son profil. Un
   * thème dépend de l'écran devant lequel on est assis et de la lumière de la
   * pièce ; une langue dépend de qui lit. Rejoué à chaque changement : choisir
   * depuis son profil doit se voir tout de suite.
   */
  useEffect(() => {
    if (!reglages && !user) return;
    appliquerApparence({
      ...(reglages || {}),
      theme: user?.theme || reglages?.theme,
      // La couleur d'accent reste au foyer : elle fait partie de son identité,
      // là où la palette relève du confort de chacun.
      couleur_accent: reglages?.couleur_accent,
    });
    definirLangue(user?.langue || reglages?.langue);
    // `user` entier plutôt que ses deux champs : le linter ne sait pas qu'on ne
    // lit que ceux-là, et une dépendance mal déclarée finit toujours par mentir.
  }, [user, reglages]);

  // L'adresse suit l'écran, et le bouton « précédent » du navigateur suit
  // l'adresse. Sans le second effet, revenir en arrière quitterait l'application.
  useEffect(() => {
    ecrireChemin(vue, premierRendu.current);
    premierRendu.current = false;
  }, [vue]);

  useEffect(() => {
    const revenir = () => setVue(vueDuChemin(window.location.pathname));
    window.addEventListener("popstate", revenir);
    return () => window.removeEventListener("popstate", revenir);
  }, []);

  useEffect(() => {
    const timer = setTimeout(charger, 200); // léger debounce sur la recherche
    return () => clearTimeout(timer);
  }, [charger]);


  // Colonnes du tableau : celles de la catégorie affichée (§18.1). Une vue
  // enregistrée rattachée à une catégorie hérite des mêmes — « Toutes les
  // factures du foyer » se lit comme la catégorie « Factures ».
  const categorieAffichee = filtreCategorie
    ?? (vueActive ? vues.find((v) => v.id === vueActive)?.categorie_id : undefined);
  const colonnesActives =
    colonnesParCategorie[String(categorieAffichee)] || colonnesParCategorie.defaut || [];
  // Ce sur quoi on peut replier : les colonnes du classement affiché, moins
  // celles qui n'ont pas de valeur commune — replier sur le texte du document ou
  // sur son nom de fichier ferait une branche par document (§21.6).
  const champsGroupables = colonnesActives
    .map((c) => c.champ)
    .filter((champ) => champ && champ !== "texte" && champ !== "nom_fichier");

  // Tri d'ouverture de la catégorie affichée (§18.49). Des factures se lisent par
  // date d'émission, des courriers par émetteur : le tri est une propriété de ce
  // qu'on regarde, il se règle donc là où se règlent les colonnes.
  const triDefautCategorie = trisParCategorie[String(categorieAffichee)]
    || trisParCategorie.defaut || { champ: "date_import", sens: "desc" };
  const triDefaut = { colonne: triDefautCategorie.champ, sens: triDefautCategorie.sens };
  // Changer de catégorie applique le tri de cette catégorie. La dépendance est
  // le tri lui-même, pas l'objet qui le porte : recharger les référentiels ne
  // doit pas défaire le tri que quelqu'un vient de choisir en cliquant.
  const cleTriDefaut = `${triDefaut.colonne}:${triDefaut.sens}`;
  useEffect(() => {
    const [colonne, sens] = cleTriDefaut.split(":");
    setTri({ colonne, sens });
    setDecalage(0);   // la première page d'un autre tri n'est pas la même page
  }, [cleTriDefaut]);

  // Une fiche simple porte ses documents comme un type, et le registre les
  // affiche de la même façon. Ce qu'elle a de particulier tient en une chose :
  // rien n'y entre tout seul, il faut y glisser le fichier (§22.1).
  const surUneFiche = (categorieOuverte?.nature || "type") === "fiche";


  // Sidebar et barre d'outils sont communes au tableau de bord et au registre :
  // on passe de l'un à l'autre sans que le cadre de l'écran ne bouge.
  /**
   * Sur un écran étroit, la navigation devient un **tiroir** (§22.52).
   *
   * Deux cent trente-deux pixels de barre latérale sur un téléphone de trois
   * cent soixante-quinze, c'est les deux tiers de l'écran pour ne rien lire. Le
   * tiroir se déplie par le bouton de la barre d'outils, recouvre la page, et se
   * referme dès qu'on a choisi — comme partout ailleurs sur un téléphone.
   */
  const barreLaterale = ecran.compact ? (
    tiroirOuvert && (
      <>
        <div
          onClick={() => setTiroirOuvert(false)}
          aria-hidden="true"
          style={{ position: "fixed", inset: 0, zIndex: 40,
                   background: "rgba(0, 0, 0, 0.45)" }}
        />
        <div style={{ position: "fixed", inset: "0 auto 0 0", zIndex: 41,
                      maxWidth: "86vw", display: "flex",
                      boxShadow: "var(--shadow-panel)" }}>
          <Sidebar
            categories={categories}
            vues={vues}
            tableaux={tableaux}
            tableauActif={vue === "accueil" ? tableauActif : null}
            onSelectTableau={(tableau) => {
              setTableauActif(tableau.id); setVue("accueil"); setTiroirOuvert(false);
            }}
            filtreCategorie={vue === "registre" ? filtreCategorie : undefined}
            vueActive={vue === "registre" ? vueActive : null}
            onFiltreCategorie={(id) => {
              choisirCategorie(id); setVue("registre"); setTiroirOuvert(false);
            }}
            onSelectVue={(v) => { appliquerVue(v); setVue("registre"); setTiroirOuvert(false); }}
            nomFoyer={reglages?.nom_foyer}
          />
        </div>
      </>
    )
  ) : (
    <Sidebar
      categories={categories}
      vues={vues}
      tableaux={tableaux}
      tableauActif={vue === "accueil" ? tableauActif : null}
      onSelectTableau={(tableau) => { setTableauActif(tableau.id); setVue("accueil"); }}
      filtreCategorie={vue === "registre" ? filtreCategorie : undefined}
      vueActive={vue === "registre" ? vueActive : null}
      onFiltreCategorie={(id) => { choisirCategorie(id); setVue("registre"); }}
      onSelectVue={(v) => { appliquerVue(v); setVue("registre"); }}
      nomFoyer={reglages?.nom_foyer}
    />
  );

  // Une panne de liaison empêche tout : elle mérite mieux qu'un bandeau au bord
  // de l'écran, qu'on peut ne pas voir. La fenêtre s'efface dès qu'on l'acquitte
  // et ne revient que si l'erreur se reproduit après coup — sans quoi chaque
  // rafraîchissement automatique la ferait resurgir sous les doigts.
  const [erreurAcquittee, setErreurAcquittee] = useState(null);
  const alerteReseau = erreur && erreur !== erreurAcquittee && (
    <AlerteModale
      titre={t("Le serveur ne répond pas")}
      ton="reseau"
      message={`L'application n'arrive pas à joindre HomeGED. Vérifiez que le service tourne, puis réessayez. (${erreur})`}
      onFermer={() => setErreurAcquittee(erreur)}
    />
  );

  const modaleCompte = compteOuvert && (
    <ComptePage onRetour={() => setCompteOuvert(false)} />
  );

  // `onExporter` n'est passé que **dans le registre** : ailleurs — tableau de
  // bord, échéances, corbeille, Centre d'analyse — il n'y a pas de sélection à
  // exporter, et la fenêtre d'export n'est même pas montée. Le bouton ouvrait
  // alors une porte qui ne s'ouvrait qu'en changeant d'écran (§22.39) ; un
  // bouton qui ne peut rien faire ne doit pas être là.
  const barreOutils = (
    <Toolbar
      query={query}
      onQueryChange={(q) => { setQuery(q); if (q) setVue("registre"); }}
      perimetre={perimetre}
      onPerimetreChange={setPerimetre}
      perimetresPossibles={perimetresPossibles}
      total={documents.length}
      afficherTotal={vue === "registre" && query.trim().length < MIN_RECHERCHE}
      nbFiltres={Object.values(filtresColonnes).filter(estActif).length}
      onEffacerFiltres={() => {
        // « Tout effacer » remonte l'arborescence **jusqu'au type de document**,
        // et pas jusqu'à la racine.
        //
        // Une vue enregistrée ne pose pas de catégorie : son filtrage vient
        // entièrement de ses critères (cf. `appliquerVue`). Effacer les critères
        // en oubliant d'où l'on venait ramenait donc à « tous les documents » —
        // et les colonnes propres au type disparaissaient au passage, ce qui se
        // lit comme une perte de réglage alors qu'on voulait juste tout effacer.
        // On repose donc le type que l'on regardait, quel que soit le chemin par
        // lequel on y était arrivé : la navigation, ou une vue rattachée à lui.
        const typeRegarde = categorieAffichee;
        setFiltresColonnes({});
        setVueActive(null);
        // Les branches parcourues (§21.6) sont des filtres, même si elles ne se
        // posent pas dans une colonne.
        setChemin([]);
        setDecalage(0);
        setFiltreCategorie(typeRegarde);
      }}
      onEnregistrerVue={() => setEnregistrementVue(true)}
      onExporter={vue === "registre" ? () => setExportOuvert(true) : undefined}
      compact={ecran.compact}
      onOuvrirNavigation={ecran.compact ? () => setTiroirOuvert(true) : undefined}
      user={user}
      onLogout={onLogout}
      onOuvrirAdmin={() => { setEcranPrecedent(vue); setVue("admin"); }}
      onOuvrirCompte={() => setCompteOuvert(true)}
      nbAAnalyser={nbAAnalyser}
      onOuvrirAnalyse={() => { setEcranPrecedent(vue); setVue("analyse"); }}
      corbeille={<>
        <BoutonRappels nombre={nbRappels}
                       onClick={() => { setEcranPrecedent(vue); setVue("echeances"); }} />
        <BoutonCorbeille nombre={nbCorbeille}
                         onClick={() => { setEcranPrecedent(vue); setVue("corbeille"); }} />
      </>}
      onActualiser={actualiser}
      actualisation={actualisation}
    />
  );

  // Un compte à qui la double authentification est imposée n'a accès qu'à sa
  // configuration : le reste de l'API lui répond 403. On lui montre alors le
  // seul écran qui le concerne — pas la page de compte entière, dont rien
  // d'autre ne lui serait ouvert.
  if (aConfigurerOtp) {
    return <ObligationOtpPage nom={user?.nom} onLogout={onLogout} />;
  }

  if (vue === "admin") {
    return (
      <>
        <BarriereErreur
          titre={t("L'administration s'est interrompue")}
          onReprendre={() => setVue("accueil")}
        >
          <AdminPage
            // On revient d'où l'on vient (§22.64), et non au registre d'office :
            // ouvrir l'administration depuis le tableau de bord et se retrouver
            // dans le registre est un déplacement que personne n'a demandé.
            destination={retourNaturel()}
            onOuvrirDocument={(id) => { setVue("registre"); setSelectedId(id); }}
            onRetour={() => {
              setVue(retourNaturel());
              chargerReferentiels(); // les catégories/règles ont pu changer
            }}
          />
        </BarriereErreur>
        {modaleCompte}
        {alerteReseau}
      </>
    );
  }

  if (vue === "accueil") {
    return (
      <div style={{ display: "flex", height: "100dvh", background: "var(--bg-app)" }}>
        {barreLaterale}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {barreOutils}
          {/* La barrière n'entoure que le tableau de bord : navigation et barre
              d'outils survivent, et l'on s'en va ailleurs sans recharger. */}
          <BarriereErreur
            key={`tableau-${tableauActif}`}
            titre={t("Ce tableau de bord s'est interrompu")}
            onReprendre={() => setTableauActif("accueil")}
          >
            <DashboardPage
              tableauId={tableauActif}
              onOuvrirRegistre={ouvrirRegistre}
              onOuvrirAnalyse={() => { setEcranPrecedent(vue); setVue("analyse"); }}
            />
          </BarriereErreur>
        </div>
        {modaleCompte}
        {alerteReseau}
      </div>
    );
  }

  if (vue === "echeances") {
    return (
      <>
      <BarriereErreur titre={t("Les échéances ne s'affichent pas")}
                      onReprendre={() => setVue("registre")}>
        <EcheancesPage
          onRetour={() => setVue(retourNaturel())}
          onOuvrirDocument={(id) => { setVue("registre"); setSelectedId(id); }}
          onChangement={chargerReferentiels}
        />
      </BarriereErreur>
      {alerteReseau}
      {modaleCompte}
      </>
    );
  }

  if (vue === "corbeille") {
    return (
      <>
      <BarriereErreur titre={t("La corbeille ne s'affiche pas")}
                      onReprendre={() => setVue("registre")}>
        <CorbeillePage
          onRetour={() => setVue(retourNaturel())}
          onChangement={() => {
            // un document restauré revient dans le registre, et le compteur suit
            chargerReferentiels();
            charger();
          }}
        />
      </BarriereErreur>
      {alerteReseau}
      {modaleCompte}
      </>
    );
  }

  if (vue === "analyse") {
    return (
      <>
      <BarriereErreur
        titre={t("Le centre d'analyse s'est interrompu")}
        onReprendre={() => setVue("accueil")}
      >
      <AnalysePage
        categories={categories}
        onCorrige={() => {
          chargerReferentiels(); // met à jour le compteur « à reprendre »
          charger();             // un document corrigé change d'état dans le registre
        }}
        onRetour={() => {
          // On revient d'où l'on venait : le tableau de bord si l'on y était,
          // le registre avec sa vue sinon.
          setVue(retourNaturel());
          chargerReferentiels();
          charger();
        }}
      />
      </BarriereErreur>
      {modaleCompte}
      {alerteReseau}
      </>
    );
  }

  return (
    // `100dvh` et non `100vh` : sur un téléphone, la barre d'adresse du
    // navigateur mange une partie de `vh`, et le bas de l'écran passait sous
    // elle (§22.52).
    <div style={{ display: "flex", height: "100dvh", background: "var(--bg-app)" }}>
      {barreLaterale}

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {barreOutils}

        <BarreSelection
          nombre={selection.length}
          onModifier={() => setModificationSerie(selection)}
          onSupprimer={() => setSuppressionMultiple(selection)}
          onRattacher={rattacherLaSelection}
          onEffacer={() => majSelection([])}
        />

        {/* Le tableau au-dessus, la fiche en bas (§19.19). Le document y est plus
            large — c'est une page qu'on lit —, et le tableau garde toute la
            largeur pour ses colonnes, qui peuvent être nombreuses. */}
        {/* Le repli se change en lisant (§21.6) : la vue en propose un, mais
            c'est celui qui regarde qui décide comment il veut parcourir. */}
        {vue === "registre" && query.trim().length < MIN_RECHERCHE && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 24px",
                        borderBottom: "1px solid var(--line)", fontSize: 12,
                        color: "var(--ink-faint)" }}>
            <Layers size={13} />
            Grouper par
            {/* La liste du projet, et non un `<select>` natif : celui-ci ne se
                met pas en forme, et détonnait dans une rangée soignée par
                ailleurs (voir `components/champs/Liste.jsx`). */}
            <div style={{ width: 230 }}>
              <Liste
                valeur={replis[0] || ""}
                compact
                ariaLabel={t("Grouper par")}
                options={[{ valeur: "", libelle: t("— rien (tableau à plat) —") },
                  ...champsGroupables.map((champ) => ({
                    valeur: champ,
                    libelle: libelleDuChamp(champ, colonnesActives)
                      + (champ === "date_document" || champ === "date_import"
                        ? t(" (par année)") : ""),
                  }))]}
                onChange={(valeur) => {
                  setReplis(valeur ? [valeur] : []);
                  setChemin([]);
                  setDecalage(0);
                }}
              />
            </div>
          </div>
        )}

        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* L'en-tête d'une fiche simple vit **au-dessus** du mode d'affichage :
              replié en branches ou à plat, on doit pouvoir y ajouter une entrée
              et y glisser un fichier. Placé dans le tableau, il disparaissait dès
              qu'un repli était actif — c'est-à-dire au moment où l'on parcourt. */}
          {surUneFiche && query.trim().length < MIN_RECHERCHE && (
            <div>
                  <div style={{ display: "flex", justifyContent: "flex-end",
                                padding: "8px 14px 10px" }}>
                    <button
                      onClick={() => setAjoutEntree(true)}
                      title={t("Créer une entrée à la main : le fichier est facultatif")}
                      style={{ display: "inline-flex", alignItems: "center", gap: 5,
                               border: "none", background: "var(--accent)", color: "#fff",
                               borderRadius: "var(--radius)", padding: "5px 11px",
                               fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}
                    >
                      <Plus size={13} />
                      Ajouter une fiche
                    </button>
                  </div>
                  <ZoneDepotFiche
                    categorieId={filtreCategorie}
                    nom={categorieOuverte.nom}
                    onDepose={() => setTimeout(charger, 4000)}
                  />
            </div>
          )}

          <div style={{ flex: 1, minHeight: 0, display: "flex", overflow: "hidden" }}>
          <BarriereErreur titre={t("Le registre s'est interrompu")}
                          onReprendre={() => setVue("accueil")}>
          {query.trim().length >= MIN_RECHERCHE ? (
            // La recherche remplace le tableau, elle ne le filtre pas : ses
            // résultats traversent les types, et les colonnes d'un type ne
            // sauraient les décrire (§21.2).
            <ResultatsRecherche
              resultats={resultats}
              terme={query.trim()}
              chargement={rechercheEnCours && resultats === null}
              perimetre={perimetreEffectif}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          ) : champReplié ? (
            // Tant qu'il reste un niveau de repli à parcourir, on montre des
            // branches ; le tableau reprend la main au dernier (§21.6).
            <Arborescence
              champ={champReplié}
              libelle={libelleDuChamp(champReplié, colonnesActives)}
              branches={branches}
              chargement={branchesEnCours && branches === null}
              chemin={chemin}
              onDescendre={descendre}
              onRemonter={remonter}
            />
          ) : (
          <DocumentsTable
            documents={documents}
            colonnes={colonnesActives}
            selectedId={selectedId}
            onSelect={setSelectedId}
            filtres={filtresColonnes}
            categorieId={filtreCategorie}
            // Le tableau ne filtre plus sur le mot cherché (§21.2) : ses listes
            // de suggestions ne doivent donc pas s'y restreindre non plus, sous
            // peine de proposer des valeurs que la liste affichée ne contient pas.
            recherche={undefined}
            onFiltresChange={(f) => {
              setFiltresColonnes(f);
              setVueActive(null); // les filtres ne correspondent plus à la vue enregistrée
            }}
            tri={tri}
            triDefaut={triDefaut}
            onTriChange={setTri}
            total={total}
            decalage={decalage}
            parPage={parPage}
            onPage={setDecalage}
            onParPage={(n) => { setParPage(n); setDecalage(0); }}
            selection={selection}
            onSelectionChange={majSelection}
            onVersions={setVersionsDe}
            enTete={chemin.length > 0 && (
              // D'où l'on vient et ce qu'on regarde — et, sur une fiche simple,
              // la seule porte par laquelle un document y entre (§22.1).
              <>
                {chemin.length > 0 && (
                  <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--line)",
                                background: "var(--bg-panel-alt)" }}>
                    <FilRepli chemin={chemin} onRemonter={remonter} />
                  </div>
                )}
              </>
            )}
          />
          )}
          </BarriereErreur>
          </div>

          {selectedId && (
            // Barrière propre à la fiche, refaite à chaque document : une fiche
            // illisible n'emporte pas la liste qui a permis d'y arriver, et
            // ouvrir la suivante repart d'un écran sain.
            <BarriereErreur key={`fiche-${selectedId}`}
                            titre={t("Cette fiche ne s'affiche pas")}
                            onReprendre={() => setSelectedId(null)}>
              <DocumentPanel
                documentId={selectedId}
                categories={categories}
                liensDeVue={vues.find((v) => v.id === vueActive)?.liens || []}
                onSuivreLien={suivreLienDeVue}
                        estAdmin={!!user?.est_admin}
                onToutVoir={(lien) => {
                  // Depuis une facture, voir tout ce qui concerne cette
                  // personne ou ce véhicule, quel que soit le type du papier.
                  ouvrirLien(lien);
                }}
                modeParDefaut={user?.mode_apercu || "miniature"}
                onOuvrirDocument={setSelectedId}
                onClose={() => {
                  // Fermer la fiche relâche la ligne : la garder sélectionnée
                  // laisserait la barre d'outils proposer d'agir sur un document
                  // qu'on ne voit plus (§18.16).
                  majSelection(selection.filter((id) => id !== selectedId));
                  setSelectedId(null);
                }}
              />
            </BarriereErreur>
          )}
        </div>
      </div>

      {suppression && (
        <ConfirmerSuppression
          typeObjet="document"
          identifiant={suppression.id}
          intitule={suppression.nom_fichier}
          administrateur={!!user?.est_admin}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={() => confirmerSuppression(suppression)}
        />
      )}

      {suppressionMultiple && (
        <ConfirmerSuppression
          intitule={`${suppressionMultiple.length} document${suppressionMultiple.length > 1 ? "s" : ""}`}
          consequences={[
            {
              nature: "suppression",
              libelle: `${suppressionMultiple.length} fiche${suppressionMultiple.length > 1 ? "s" : ""} retirée${suppressionMultiple.length > 1 ? "s" : ""} du registre`,
              precision: t("avec leurs métadonnées, leur classement et leur historique"),
            },
            {
              nature: "avertissement",
              libelle: t("Les PDF partent en corbeille, pas à la poubelle"),
              precision: t("le serveur de travaux les y dépose ; un administrateur peut encore les récupérer"),
            },
          ]}
          onAnnuler={() => setSuppressionMultiple(null)}
          onConfirmer={confirmerSuppressionMultiple}
        />
      )}

      {versionsDe && (
        <VersionsDocument
          documentId={versionsDe}
          estAdmin={!!user?.est_admin}
          onFermer={() => setVersionsDe(null)}
          onChangement={charger}
        />
      )}

      {modificationSerie && (
        <ModifierSelection
          ids={modificationSerie}
          categories={categories}
            onEnregistre={charger}
          onFerme={(faites) => {
            setModificationSerie(null);
            // Les fiches enregistrées sortent de la sélection : ce qui reste
            // coché est exactement ce qu'il reste à faire — y compris celles
            // que l'on a délibérément passées.
            if (faites?.length) {
              majSelection(selection.filter((id) => !faites.includes(id)));
            }
            charger();
          }}
        />
      )}

      {ajoutEntree && categorieOuverte && (
        <AjouterEntree
          categorieId={categorieOuverte.id}
          nomCategorie={categorieOuverte.nom}
          onFerme={() => setAjoutEntree(false)}
          onCreee={(entree) => {
            setAjoutEntree(false);
            charger();
            // On ouvre la fiche créée : c'est là qu'on complètera, et qu'on
            // glissera le papier s'il arrive un jour.
            setSelectedId(entree.id);
          }}
        />
      )}

      {exportOuvert && (
        <ExporterSelection
          criteres={[...versCriteres(filtresColonnes), ...chemin.map((e) => e.critere)]}
          categorieId={filtreCategorie}
          onFermer={() => setExportOuvert(false)}
        />
      )}

      {enregistrementVue && (
        <EnregistrerVue
          criteres={versCriteres(filtresColonnes)}
          categories={categories}
            colonnes={colonnesActives}
          categorieParDefaut={filtreCategorie ?? ""}
          onClose={() => setEnregistrementVue(false)}
          onEnregistrer={enregistrerVue}
        />
      )}
    {modaleCompte}
    {alerteReseau}
    </div>
  );
}

