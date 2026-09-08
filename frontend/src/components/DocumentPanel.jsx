import React, { useEffect, useRef, useState } from "react";
import { X, Download, AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, ChevronUp,
         FileText, History, Info,
         Hand, Image, Link2, ListTree, Maximize2, Star, Trash2 } from "lucide-react";
import { api } from "../api";
import HistoriqueDocument, { BoutonHistorique } from "./HistoriqueDocument.jsx";
import VersionsDocument from "./VersionsDocument.jsx";
import ZoneDepot from "./ZoneDepot.jsx";
import Liste from "./champs/Liste.jsx";
import { libelleDocument, sousTitreDocument } from "../lib/document";
import { estIso } from "../lib/cellules";
import { ilYA as quand } from "../lib/horodatage";
import { versFrancais } from "./champs/dates";
import { t } from "../lib/langue";
import { useEcran } from "../lib/ecran";
import { PoigneeMetadonnees, useLargeurMetadonnees } from "./champs/LargeurMetadonnees.jsx";

export default function DocumentPanel({ documentId, categories, onClose,
                                       onOuvrirDocument, onToutVoir, estAdmin = false,
                                       liensDeVue = [], onSuivreLien,
                                       modeParDefaut = "miniature" }) {
  const [doc, setDoc] = useState(null);
  // Lue à part de `doc` : c'est cette valeur-là dont dépend le chargement du
  // PDF, et l'objet entier changerait d'identité à chaque rechargement.
  const aUnFichier = doc?.a_un_fichier;
  const [chargement, setChargement] = useState(true);
  const [pdfUrl, setPdfUrl] = useState(null);
  // Le document lié qu'on lit dans la visionneuse, à la place de celui de la
  // fiche (§22.78). « Voir » ouvrait un onglet : on quittait l'écran pour
  // vérifier un montant, ce qui est exactement ce qu'on ne voulait plus.
  const [lecture, setLecture] = useState(null);   // { id, titre }
  // Son fichier, chargé **ici** (§22.81). La grille de vignettes en préparait un
  // pour son propre bouton, mais elle se démonte en passant en visionneuse et
  // révoque son URL au passage : on se retrouvait devant un cadre vide, alors
  // que l'ouverture en onglet — faite avant le démontage — fonctionnait.
  const [urlLecture, setUrlLecture] = useState(null);
  const [erreurLecture, setErreurLecture] = useState(null);
  const [pdfChargement, setPdfChargement] = useState(true);
  const [pdfErreur, setPdfErreur] = useState(null);
  const [erreur, setErreur] = useState(null);
  // La fiche est en lecture seule. On écrit depuis la barre de sélection, qui
  // ouvre la fenêtre de modification et prend un verrou (§17.21, §18.16).
  const [historique, setHistorique] = useState(false);
  // Le panneau s'ouvre en bas et montre le document (§19.19). Les champs se
  // déplient à la demande, la hauteur se double d'un clic : on vient lire une
  // page, pas une liste de valeurs qu'on a déjà en colonnes.
  const [details, setDetails] = useState(false);
  const [agrandi, setAgrandi] = useState(false);
  // La colonne des métadonnées se tire à la souris (§22.69) : 380 px fixes
  // conviennent à quatre champs courts et étouffent douze champs dont un
  // commentaire. La hauteur, elle, garde son chevron — deux états suffisent.
  const { largeur: largeurMeta, commencer: commencerLargeur,
          oublier: oublierLargeur } = useLargeurMetadonnees();
  // Ce que la vue courante dit d'aller voir ensuite (§22.5), et les documents
  // que ce lien désigne. C'est le **seul** rapprochement affiché depuis que le
  // rapprochement automatique par valeur partagée a été retiré de l'écran : ce
  // qui se montre ici a été déclaré par quelqu'un.
  const [voisinsDeVue, setVoisinsDeVue] = useState([]);
  // Ce que les **déclarations de type** rapprochent (§22.8) : un dossier et ses
  // pièces, reliés par un numéro que quelqu'un a désigné. Rien n'est deviné.
  const [rapproches, setRapproches] = useState([]);
  // Le contenu des champs qui attachent des documents (§22.11) : « Factures
  // liées » sous un entretien. Ce sont des documents choisis, pas devinés.
  const [attaches, setAttaches] = useState([]);
  // Document entier ou miniature de première page (§19.20). Le mode vient du
  // profil — il dépend de la machine de celui qui regarde — et se change ici
  // pour le document qu'on a sous les yeux, sans repasser par les options.
  const [mode, setMode] = useState(modeParDefaut);
  // L'identifiant du document dont on ouvre les dépôts — pas un booléen : la
  // pastille existe aussi sur les vignettes liées (§19.22).
  const [versionsDe, setVersionsDe] = useState(null);
  const [rechargement, setRechargement] = useState(0);
  // Les fichiers que porte ce document (§22.2). Un document en a toujours au
  // moins un — sa pièce principale, celle qu'on ouvre quand on ne dit rien.
  const [pieces, setPieces] = useState([]);
  // La pièce qu'on lit en entier, quand ce n'est pas la principale : sans cet
  // état, ouvrir la garantie afficherait la facture.
  const [pieceLue, setPieceLue] = useState(null);
  // Ce qu'on a rattaché à la main (§22.4) : ce qui ne partage aucune valeur
  // avec ce document mais lui répond quand même — un avenant, un litige.
  const [rattaches, setRattaches] = useState([]);

  // La lecture d'un document lié se referme au changement de **document** : la
  // sienne n'a plus de sens sur un autre. Effet à part, et c'est le point :
  // rangée avec le chargement du PDF, elle se serait refermée à chaque bascule
  // de mode — donc au moment même où l'on demandait à lire (§22.78).
  useEffect(() => { setLecture(null); }, [documentId, rechargement]);

  useEffect(() => {
    if (!lecture?.id) { setUrlLecture(null); setErreurLecture(null); return undefined; }
    let objet;
    let vivant = true;
    setUrlLecture(null);
    setErreurLecture(null);
    api.fichierBlobUrl(lecture.id)
      .then((url) => {
        objet = url;
        if (vivant) setUrlLecture(url);
        else URL.revokeObjectURL(url);
      })
      // Un document lié illisible ne doit pas laisser un « Chargement… » sans
      // fin : on dit ce qui s'est passé, et l'on peut revenir.
      .catch((e) => vivant && setErreurLecture(e.message || t("Aperçu indisponible.")));
    return () => {
      vivant = false;
      // Révoquée en quittant, et pas au clic : un onglet déjà ouvert dessus doit
      // continuer d'afficher le document.
      if (objet) URL.revokeObjectURL(objet);
    };
  }, [lecture?.id]);

  useEffect(() => {
    setChargement(true);
    setErreur(null);
    api
      .document(documentId)
      .then((d) => {
        setDoc(d);
      })
      // sans ce catch, un document refusé (403) ou supprimé (404) laissait le
      // panneau bloqué indéfiniment sur « Chargement… »
      .catch((e) => setErreur(e.message || t("Document indisponible.")))
      .finally(() => setChargement(false));

    setVoisinsDeVue([]);
    setRapproches([]);
    api.rapprochements(documentId)
      .then((r) => setRapproches(
        (r.rapprochements || []).flatMap((groupe) =>
          groupe.documents.map((autre) => ({ ...autre, rattachement: groupe.libelle })))))
      .catch(() => {});

    setAttaches([]);
    api.attaches(documentId)
      .then((r) => setAttaches(r.attaches || []))
      .catch(() => {});

    setRattaches([]);
    api.rattachements(documentId)
      .then((r) => setRattaches(r.rattachements || []))
      .catch(() => {});

    setPieces([]);
    setPieceLue(null);
    api.piecesDocument(documentId)
      .then(setPieces)
      // Une pièce en moins n'empêche pas de lire la fiche : le panneau se replie
      // sur le fichier du document, comme avant le §22.2.
      .catch(() => {});

    let url;
    setPdfErreur(null);
    setPdfUrl(null);
    // On ne charge que ce que le mode demande : en vignettes, le PDF n'est pas
    // rapatrié « au cas où » — c'est tout l'intérêt du mode, et chaque tuile va
    // chercher sa propre image.
    if (mode === "miniature") {
      setPdfChargement(false);
      return undefined;
    }
    // Une entrée de fiche simple peut n'avoir aucun fichier (§22.58) : demander
    // le PDF ne servirait qu'à recevoir un 404 et à l'afficher comme une panne.
    // On le dit posément, et l'on ne va rien chercher.
    if (aUnFichier === false && !pieceLue) {
      setPdfChargement(false);
      setPdfErreur(t("Cette entrée n'a pas de fichier : elle se remplit à la main. Glissez-en un dans sa fiche pour lui en joindre un."));
      return undefined;
    }
    setPdfChargement(true);
    // La pièce qu'on a demandé de lire, le document (donc sa pièce principale)
    // sinon : ouvrir la garantie ne doit pas afficher la facture.
    const charger = pieceLue
      ? api.fichierPieceBlobUrl(documentId, pieceLue)
      : api.fichierBlobUrl(documentId);
    charger
      .then((u) => {
        url = u;
        setPdfUrl(u);
      })
      .catch((e) => setPdfErreur(e.message || t("Impossible de charger l'aperçu.")))
      .finally(() => setPdfChargement(false));

    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [documentId, rechargement, mode, pieceLue, aUnFichier]);

  // Les documents que le lien de vue désigne (§22.5), affichés en tuiles à côté
  // des pièces. C'est le seul rapprochement montré depuis que le rapprochement
  // automatique a quitté l'écran : celui-ci a été **déclaré** par quelqu'un, et
  // l'on sait donc ce qu'il veut dire.
  useEffect(() => {
    const utilisable = (liensDeVue || [])
      .map((lien) => ({ lien, valeur: valeurDuChamp(doc, lien.champ_source) }))
      .find(({ valeur }) => valeur !== undefined && valeur !== null && valeur !== "");
    if (!doc || !utilisable) { setVoisinsDeVue([]); return undefined; }

    let vivant = true;
    api.documents({
      filtres: JSON.stringify([{ champ: utilisable.lien.champ_cible, operateur: "egal",
                                 valeur: String(utilisable.valeur) }]),
      limite: 12,
    })
      .then(({ documents }) => {
        if (!vivant) return;
        setVoisinsDeVue((documents || [])
          .filter((autre) => autre.id !== doc.id)
          .map((autre) => ({
            id: autre.id,
            libelle: libelleDocument(autre),
            categorie: autre.categorie,
            nom_fichier: autre.nom_fichier,
            nb_versions: autre.nb_versions,
            rattachement: utilisable.lien.libelle,
          })));
      })
      .catch(() => {});
    return () => { vivant = false; };
    // La **description** des liens, et non le tableau : `liensDeVue` est
    // reconstruit à chaque rendu du parent, et le comparer par identité relançait
    // l'effet sans fin — le panneau tournait en boucle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, JSON.stringify(liensDeVue || [])]);

  // Les champs de la fiche : ceux du type, valeurs comprises quand il y en a, et
  // vides sinon — quand on ouvre une fiche, on cherche souvent ce qui **manque**.
  // Les colonnes retirées du tableau n'arrivent ici que si le type le dit
  // (§19.21) : c'est un réglage d'administration, pas un choix de lecteur.
  const champsVisibles = doc?.champs_fiche || [];

  // Les documents qu'un champ « documents de la GED » attache à cette fiche
  // (§22.11) ont leur place parmi les vignettes, avec la pastille « lien » :
  // sur une fiche simple sans fichier, c'est tout ce qu'il y a à voir, et
  // l'écran n'affichait rien (§22.58). Le nom du champ porte le libellé de la
  // pastille : « Factures liées » dit ce qui rapproche, « lié » ne dit rien.
  const documentsAttaches = (attaches || []).flatMap((groupe) =>
    (groupe.documents || []).map((attache) => ({
      ...attache, rattachement: groupe.libelle,
    })));

  const { compact } = useEcran();

  return (
    <aside
      style={{
        // Sur un téléphone, la fiche prend l'écran : partagé en deux, ni le
        // tableau ni la fiche ne seraient lisibles (§22.52). `dvh` et non `vh` —
        // la barre d'adresse mange le bas de l'écran.
        height: compact ? "100dvh" : agrandi ? "72vh" : "46vh",
        ...(compact ? { position: "fixed", inset: 0, zIndex: 30, borderTop: "none" } : {}),
        flexShrink: 0,
        borderTop: "3px solid var(--accent)",
        background: "var(--bg-panel)",
        boxShadow: "var(--shadow-panel)",
        display: "flex",
        flexDirection: "column",
        animation: "monter 180ms ease-out",
      }}
    >
      <style>{`
        @keyframes monter {
          from { transform: translateY(24px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 16px",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <h2 style={{ fontSize: 14.5, overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap" }}>
            {doc ? libelleDocument(doc) : "…"}
          </h2>
          {doc && (
            <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 2,
                          overflow: "hidden", textOverflow: "ellipsis",
                          whiteSpace: "nowrap" }}>
              {sousTitreDocument(doc)}
              {/* le nom du fichier n'identifie plus le document, mais reste utile
                  pour retrouver le PDF dans storage/ ou dans une sauvegarde */}
              <span title={t("Nom du fichier archivé")} style={{ marginLeft: 8, opacity: 0.75 }}>
                · {doc.nom_fichier}
              </span>
              {doc.derniere_modification && (
                <span style={{ marginLeft: 8, opacity: 0.75 }}>
                  · modifié {quand(doc.derniere_modification.date)}
                  {doc.derniere_modification.auteur && ` par ${doc.derniere_modification.auteur}`}
                </span>
              )}
            </div>
          )}
        </div>

        {doc && (
          <>
            {/* Les champs se déplient : c'est le **document** qu'on vient voir en
                cliquant une ligne, pas la liste de ce qu'on en a extrait — celle-ci
                est déjà dans le tableau, colonne par colonne (§19.19). */}
            {/* Deux modes, deux icônes (§19.20) : la page entière, ou son image.
                La miniature ne charge pas le PDF — c'est tout son intérêt. */}
            <div style={{ display: "flex", border: "1px solid var(--line-strong)",
                          borderRadius: "var(--radius)", overflow: "hidden" }}>
              {[
                { cle: "document", icone: FileText, titre: t("Le document entier") },
                { cle: "miniature", icone: Image,
                  titre: t("Vignettes : ce document et ceux qui lui sont liés, côte à côte — le PDF n'est pas chargé") },
              ].map(({ cle, icone: Icone, titre }) => (
                <button
                  key={cle}
                  onClick={() => setMode(cle)}
                  aria-pressed={mode === cle}
                  aria-label={titre}
                  title={titre}
                  style={{
                    border: "none", padding: "5px 9px",
                    background: mode === cle ? "var(--accent-soft)" : "transparent",
                    color: mode === cle ? "var(--accent)" : "var(--ink-soft)",
                    display: "flex",
                  }}
                >
                  <Icone size={14} />
                </button>
              ))}
            </div>

            <button
              onClick={() => setDetails((ouvert) => !ouvert)}
              aria-pressed={details}
              style={{ ...boutonSecondaire,
                       borderColor: details ? "var(--accent)" : "var(--line-strong)",
                       color: details ? "var(--accent)" : "var(--ink-soft)" }}
            >
              <ListTree size={14} />
              Détails
            </button>
            <BoutonHistorique onClick={() => setHistorique(true)} />
            {/* Plusieurs dépôts pour ce document (§18.36) : la fiche montre le
                dernier, et donne accès aux précédents. */}
            {doc.nb_versions > 1 && (
              <button onClick={() => setVersionsDe(documentId)} style={boutonSecondaire}>
                <History size={14} />
                {doc.nb_versions} versions
              </button>
            )}
          </>
        )}

        <button
          onClick={() => setAgrandi((grand) => !grand)}
          aria-label={agrandi ? t("Réduire le panneau") : t("Agrandir le panneau")}
          title={agrandi ? t("Réduire") : t("Agrandir")}
          style={{ border: "none", background: "transparent", padding: 4,
                   color: "var(--ink-soft)" }}
        >
          {agrandi ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
        </button>
        <button
          onClick={onClose}
          aria-label={t("Fermer le détail")}
          style={{ border: "none", background: "transparent", padding: 4, color: "var(--ink-soft)" }}
        >
          <X size={18} />
        </button>
      </div>

      {erreur && (
        <div style={{ margin: "14px 20px", padding: "10px 12px", background: "var(--brick-soft)", color: "var(--brick)", borderRadius: "var(--radius)", fontSize: 12 }}>
          {erreur}
        </div>
      )}

      {chargement ? (
        <div style={{ padding: 20, color: "var(--ink-faint)", fontSize: 13 }}>{t("Chargement…")}</div>
      ) : !doc ? null : (
        <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
          {/* Le document occupe la place ; les champs prennent une colonne à
              droite seulement quand on les demande. */}
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column",
                        padding: "12px 16px" }}>
            {doc.champs_manquants?.length > 0 && (
              <div style={{
                marginBottom: 10, padding: "8px 11px", background: "var(--amber-soft)",
                border: "1px solid var(--amber)", borderRadius: "var(--radius)",
                fontSize: 12, color: "var(--ink)", display: "flex", gap: 8,
              }}>
                <AlertTriangle size={14} color="var(--amber)"
                               style={{ flexShrink: 0, marginTop: 1 }} />
                <div>
                  <strong>{t("Document incomplet")}</strong> — son type attend&nbsp;:{" "}
                  {doc.champs_manquants.map((c) => c.libelle).join(", ")}.
                </div>
              </div>
            )}

            {mode === "miniature" ? (
              <GrilleVignettes
                document={doc}
                pieces={pieces}
                voisins={[...documentsAttaches, ...rapproches, ...voisinsDeVue]}
                estAdmin={estAdmin}
                onOuvrir={onOuvrirDocument}
                onLirePiece={(piece) => {
                  setPieceLue(piece?.principale ? null : piece?.id || null);
                  setLecture(null);
                  setMode("document");
                }}
                // Lire un document lié **ici**, dans la visionneuse de la fiche
                // (§22.78) : on vérifie un montant, on ne déménage pas.
                onLireVoisin={(voisin) => {
                  setLecture({ id: voisin.id,
                               titre: voisin.libelle || voisin.nom_fichier });
                  setMode("document");
                }}
                onVersions={setVersionsDe}
                onLiaison={() => setDetails(true)}
                onRafraichirPieces={() =>
                  api.piecesDocument(documentId).then(setPieces).catch(() => {})}
                onPiecesChangees={(liste) => {
                  setPieces(liste);
                  // La principale a pu changer : le document ouvre un autre
                  // fichier, et ses colonnes le disent déjà côté serveur.
                  setRechargement((n) => n + 1);
                }}
                documentId={documentId}
              />
            ) : (lecture ? urlLecture : pdfUrl) ? (
              <embed src={lecture ? urlLecture : pdfUrl} type="application/pdf"
                     style={{ flex: 1, minHeight: 0, width: "100%",
                              border: "1px solid var(--line)",
                              borderRadius: "var(--radius)" }} />
            ) : (
              <div style={{
                flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
                border: "1px solid var(--line)", borderRadius: "var(--radius)",
                color: (lecture ? erreurLecture : pdfErreur)
                  ? "var(--brick)" : "var(--ink-faint)", fontSize: 12,
                background: "var(--bg-panel-alt)", textAlign: "center", padding: 16,
              }}>
                {lecture ? (erreurLecture || t("Chargement du document…"))
                  : pdfChargement ? t("Chargement du document…")
                  : pdfErreur ? `Aperçu indisponible : ${pdfErreur}`
                    : t("Aperçu indisponible.")}
              </div>
            )}
            {/* On lit un document lié : on dit lequel, et comment revenir —
                sans quoi on croirait s'être trompé de fiche (§22.78). */}
            {lecture && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8,
                            fontSize: 12, color: "var(--ink-soft)", flexWrap: "wrap" }}>
                <Link2 size={13} color="var(--accent)" />
                <span>{t("Vous lisez « {titre} »", { titre: lecture.titre })}</span>
                <button onClick={() => setLecture(null)} style={boutonBarre}>
                  {t("Revenir au document")}
                </button>
              </div>
            )}
            {(lecture ? urlLecture : pdfUrl) && (
              <a href={lecture ? urlLecture : pdfUrl} target="_blank" rel="noreferrer"
                 style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 8,
                          fontSize: 12, color: "var(--accent)", textDecoration: "none",
                          fontWeight: 500 }}>
                <Download size={13} />
                {t("Ouvrir le PDF en plein écran")}
              </a>
            )}
          </div>

          {details && (
          // `relative` pour que la poignée s'accroche au trait de séparation, et
          // sur téléphone la colonne prend toute la largeur : rien à ajuster.
          <div style={{ width: compact ? "100%" : largeurMeta, flexShrink: 0,
                        position: "relative", overflowY: "auto",
                        borderLeft: "1px solid var(--line)" }} className="scrollbar-thin">
            {!compact && (
              <PoigneeMetadonnees commencer={commencerLargeur} oublier={oublierLargeur} />
            )}
          {/* Le classement et l'émetteur sont déjà des colonnes du tableau, et le
              titre de la fiche les répète (§19.20). Les redire ici prenait la
              place de ce qu'on vient vraiment chercher : les valeurs extraites,
              **y compris celles qui manquent**. */}
          <Section titre={t("Métadonnées")}>
            {champsVisibles.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
                {t("Ce type de document ne déclare aucune métadonnée, et aucune règle n'en a trouvé.")}
              </div>
            ) : (
              champsVisibles.map((champ) => {
                // Une métadonnée pointant une table de données s'affiche par son
                // libellé : « Renault Clio » est parlant, « 3 » ne l'est pas.
                // Une date se lit comme partout ailleurs : 21/07/2026.
                const lisible = champ.reference
                  || (champ.valeur && estIso(champ.valeur)
                      ? versFrancais(String(champ.valeur))
                      : champ.valeur);
                return (
                  <ChampLigne
                    key={champ.cle}
                    label={t(champ.libelle)}
                    valeur={lisible}
                    mono={!champ.reference}
                    masquee={champ.masquee}
                  />
                );
              })
            )}

          </Section>

            <SectionAttaches attaches={attaches} onOuvrir={onOuvrirDocument} />
            <SectionLiensDeVue liens={liensDeVue} document={doc}
                               onSuivre={onSuivreLien} />
            <SectionRattachements
              rattaches={rattaches}
              onOuvrir={onOuvrirDocument}
              onDetacher={async (autreId) => {
                await api.detacher(documentId, autreId);
                setRattaches((liste) => liste.filter((r) => r.document_id !== autreId));
              }}
            />
          </div>
          )}
        </div>
      )}

      {versionsDe && (
        <VersionsDocument
          documentId={versionsDe}
          estAdmin={estAdmin}
          onFermer={() => setVersionsDe(null)}
          onChangement={() => setRechargement((n) => n + 1)}
        />
      )}

      {historique && (
        <HistoriqueDocument
          documentId={documentId}
          categories={categories}
          onFermer={() => setHistorique(false)}
        />
      )}
    </aside>
  );
}

function Section({ titre, children }) {
  return (
    <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)" }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--ink-faint)",
          marginBottom: 10,
          textTransform: "none",
        }}
      >
        {titre}
      </div>
      {children}
    </div>
  );
}

/**
 * Une ligne de la fiche. Un champ vide s'écrit « — » et **reste affiché** : une
 * case vide se voit et se réclame, une case absente laisse croire que le champ
 * n'existe pas (§19.20).
 */
function ChampLigne({ label, valeur, mono, masquee = false }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: 12,
        padding: "5px 0",
        borderBottom: "1px solid var(--line)",
        fontSize: 13,
        opacity: masquee ? 0.7 : 1,
      }}
    >
      <span style={{ color: "var(--ink-soft)", textTransform: "capitalize",
                     flexShrink: 0 }}>
        {label}
        {masquee && (
          <span title={t("Colonne retirée du tableau par l'administration")}
                style={{ color: "var(--ink-faint)", fontSize: 10.5, marginLeft: 5 }}>
            (hors tableau)
          </span>
        )}
      </span>
      {/* Sur la fiche, le texte est **entier** (§22.67) : c'est là qu'on vient
          lire un commentaire de dix lignes, alors que le tableau, lui, se
          parcourt et borne ses cellules. Il revient donc à la ligne, en
          respectant les retours saisis, et l'intitulé garde sa place à gauche. */}
      <span className={mono ? "tabular" : undefined}
            style={{ textAlign: "right", minWidth: 0, flex: "1 1 auto",
                     whiteSpace: "pre-wrap", wordBreak: "break-word",
                     color: valeur ? "var(--ink)" : "var(--ink-faint)" }}>
        {valeur || "—"}
      </span>
    </div>
  );
}

const labelStyle = {
  display: "block",
  fontSize: 12,
  color: "var(--ink-soft)",
  marginBottom: 4,
};

const selectStyle = {
  width: "100%",
  padding: "7px 9px",
  fontSize: 13,
  border: "1px solid var(--line-strong)",
  borderRadius: "var(--radius)",
  background: "var(--bg-panel)",
  color: "var(--ink)",
  fontFamily: "inherit",
};

/**
 * Style des deux actions de la fiche, aligné sur le bouton « Administration » de
 * la barre d'outils : ce sont des points d'entrée, pas des commandes discrètes.
 * Les enfouir revenait à laisser croire que la fiche ne se modifie pas.
 */

const boutonSecondaire = {
  display: "flex", alignItems: "center", gap: 6,
  background: "transparent", color: "var(--ink-soft)",
  border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
  padding: "7px 12px", fontSize: 13, cursor: "pointer",
};


/**
 * Les documents en vignettes, côte à côte (§19.21).
 *
 * Une pièce ne se comprend presque jamais seule : la facture d'entretien vaut
 * pour la carte grise qui l'accompagne, l'avis d'échéance pour le contrat. Les
 * montrer les uns à côté des autres — la première page de chacun, en grand — les
 * fait reconnaître d'un coup d'œil, là où une liste de noms de fichiers oblige à
 * les ouvrir un par un pour savoir lequel on cherche.
 *
 * Rien n'est chargé en entier : chaque tuile ne demande que son image de
 * première page. Un clic ouvre le document choisi, et le document courant passe
 * en lecture pleine page.
 */
function GrilleVignettes({ document: courant, documentId, pieces, voisins, estAdmin,
                          onOuvrir, onLirePiece, onLireVoisin, onVersions, onLiaison,
                          onPiecesChangees, onRafraichirPieces }) {
  const [erreur, setErreur] = useState(null);
  // Ce que devient le prochain fichier déposé : une pièce de plus (null), ou le
  // rescan de la pièce choisie (§22.3).
  const [remplace, setRemplace] = useState(null);
  // La pièce sur laquelle porte la barre d'outils. Un clic la choisit plutôt que
  // de l'ouvrir : on vient souvent la désigner — pour la lire, la promouvoir ou
  // la retirer — et non la lire tout de suite.
  const [choisie, setChoisie] = useState(null);
  // Le document lié qu'on désigne (§22.73). Cliquer une vignette voisine
  // quittait la fiche pour la sienne : on venait souvent la regarder, pas la
  // remplacer. On la choisit donc, comme une pièce, et l'on décide ensuite.
  const [voisinChoisi, setVoisinChoisi] = useState(null);
  const [urlVoisin, setUrlVoisin] = useState(null);
  const [details, setDetails] = useState(false);
  // L'adresse du fichier de la pièce choisie (§22.23). Préparée dès qu'on la
  // choisit, pour que « Voir » soit un **vrai lien** : c'est la seule façon
  // qu'un clic molette ou un Ctrl+clic ouvre un onglet, comme partout ailleurs
  // dans un navigateur. Un `window.open` après un aller-retour au serveur perd
  // le geste de l'utilisateur et se fait bloquer.
  const [urlPiece, setUrlPiece] = useState(null);

  // Un document d'avant le §22.2 dont les pièces ne seraient pas chargées garde
  // sa tuile : le panneau ne doit pas devenir vide parce qu'un appel a échoué.
  //
  // Sauf s'il n'a **aucun fichier** — une entrée de fiche simple se saisit à la
  // main (§19.1). La tuile de repli réclamait alors une vignette qui n'existe
  // pas, et l'écran répondait « Page non rendue » (§22.58). `pieces` vide ne
  // suffit pas à trancher : c'est aussi l'état d'un document d'avant le §22.2.
  const sansFichier = courant?.a_un_fichier === false;
  const tuiles = (pieces && pieces.length)
    ? pieces
    : (sansFichier
      ? []
      : [{ id: null, nom_fichier: libelleDocument(courant), principale: true, ordre: 1 }]);
  const piece = tuiles.find((p) => p.id === choisie) || null;
  const voisin = (voisins || []).find((v) => v.id === voisinChoisi) || null;

  useEffect(() => {
    if (!piece) { setUrlPiece(null); return undefined; }
    let objet;
    let vivant = true;
    const demande = piece.id
      ? api.fichierPieceBlobUrl(documentId, piece.id)
      : api.fichierBlobUrl(documentId);
    demande
      .then((url) => {
        objet = url;
        if (vivant) setUrlPiece(url);
        else URL.revokeObjectURL(url);
      })
      .catch(() => vivant && setUrlPiece(null));
    return () => {
      vivant = false;
      // Révoquée en quittant, et pas au clic : un onglet déjà ouvert dessus doit
      // continuer d'afficher la page.
      if (objet) URL.revokeObjectURL(objet);
    };
  }, [documentId, piece?.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!voisin) { setUrlVoisin(null); return undefined; }
    let objet;
    let vivant = true;
    api.fichierBlobUrl(voisin.id)
      .then((url) => {
        objet = url;
        if (vivant) setUrlVoisin(url);
        else URL.revokeObjectURL(url);
      })
      .catch(() => vivant && setUrlVoisin(null));
    return () => {
      vivant = false;
      if (objet) URL.revokeObjectURL(objet);
    };
  }, [voisin?.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function agir(action) {
    setErreur(null);
    try {
      onPiecesChangees?.(await action());
      setChoisie(null);
    } catch (e) {
      setErreur(e.message);
    }
  }

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: "auto",
                  border: "1px solid var(--line)", borderRadius: "var(--radius)",
                  background: "var(--bg-panel-alt)" }}
         className="scrollbar-thin">
      {/* Joindre une pièce (§22.2) : une facture, sa garantie et le bon de
          livraison sont un seul dossier — les réunir ici évite de remplir trois
          fois les mêmes champs. */}
      <ZoneDepot
        invitation={t("Glissez un fichier ici pour le joindre à ce document")}
        ariaLabel={t("Joindre une pièce à ce document")}
        envoyer={(fichier) => api.joindrePiece(documentId, fichier, remplace)}
        succes={(nombre) => (remplace
          ? t("Rescan reçu. Il remplacera cette pièce dans quelques secondes ; la version précédente reste dans son historique.")
          : nombre === 1
            ? t("Pièce reçue. Elle apparaîtra ici dans quelques secondes, le temps qu'elle soit lue.")
            : `${nombre} pièces reçues. Elles apparaîtront ici dans quelques secondes.`)}
        onDepose={() => setTimeout(() => onRafraichirPieces?.(), 4000)}
        // La seule question qu'on ne puisse pas deviner (§22.3) : le même PDF est
        // une pièce de plus ou le rescan d'une pièce existante selon ce qu'on
        // vient de faire. Elle se pose ici, avant le dépôt, et pas après.
        complement={pieces && pieces.length > 0 ? (
          <label style={{ display: "inline-flex", alignItems: "center", gap: 5,
                          color: "var(--ink-faint)" }}>
            en tant que
            <span style={{ width: 250, display: "inline-block" }}>
              <Liste
                valeur={remplace ? String(remplace) : ""}
                compact
                ariaLabel={t("Ce que devient le fichier déposé")}
                options={[{ valeur: "", libelle: t("nouvelle pièce") },
                  ...pieces.map((p) => ({
                    valeur: String(p.id),
                    libelle: `nouvelle version de « ${p.nom_fichier} »`,
                  }))]}
                onChange={(valeur) => setRemplace(valeur ? Number(valeur) : null)}
              />
            </span>
          </label>
        ) : null}
      />

      {/* La barre d'outils de la pièce choisie. Elle n'apparaît qu'une fois
          quelque chose de choisi : une rangée de boutons grisés en permanence
          apprend seulement qu'on ne peut rien faire. */}
      {piece && (
        <BarrePiece
          piece={piece}
          url={urlPiece}
          seule={tuiles.length <= 1}
          estAdmin={estAdmin}
          details={details}
          onDetails={() => setDetails((d) => !d)}
          onVoir={() => onLirePiece?.(piece)}
          onPrincipale={() => agir(() => api.piecePrincipale(documentId, piece.id))}
          rang={tuiles.findIndex((p) => p.id === piece.id)}
          nombre={tuiles.length}
          onDeplacer={(sens) => agir(() => {
            // L'ordre entier part au serveur : il range dans l'ordre reçu, et
            // les pièces omises suivent. Envoyer « celle-ci passe devant »
            // supposerait que les deux côtés comptent les rangs pareil.
            const rangs = tuiles.map((p) => p.id).filter(Boolean);
            const depuis = rangs.indexOf(piece.id);
            const vers = depuis + sens;
            if (depuis < 0 || vers < 0 || vers >= rangs.length) return null;
            [rangs[depuis], rangs[vers]] = [rangs[vers], rangs[depuis]];
            return api.ordonnerPieces(documentId, rangs);
          })}
          onRetirer={() => agir(async () =>
            (await api.retirerPiece(documentId, piece.id)).pieces)}
          onFermer={() => { setChoisie(null); setDetails(false); }}
        />
      )}

      {/* Le document lié qu'on a désigné : on le lit et on l'interroge d'ici,
          sans quitter la fiche qu'on est en train de regarder (§22.73). */}
      {voisin && (
        <BarreVoisin
          voisin={voisin}
          url={urlVoisin}
          onVoir={() => onLireVoisin?.(voisin)}
          onOuvrir={() => onOuvrir?.(voisin.id)}
          onFermer={() => setVoisinChoisi(null)}
        />
      )}

      <div style={{ padding: 14 }}>
      {erreur && (
        <div style={{ color: "var(--brick)", fontSize: 12, marginBottom: 10 }}>{erreur}</div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "flex-start" }}>
        {tuiles.map((p, rang) => (
          <Vignette
            key={p.id ?? "document"}
            documentId={courant.id}
            pieceId={p.id}
            titre={p.nom_fichier}
            sousTitre={p.principale ? t("Pièce principale") : `Pièce ${rang + 1} · jointe`}
            courante={p.id === choisie || (choisie === null && !!p.principale)}
            choisie={p.id === choisie}
            onClic={() => {
              setChoisie(p.id === choisie ? null : p.id);
              setVoisinChoisi(null);
            }}
            action={t("Choisir cette pièce")}
            // Les dépôts successifs portent sur le fichier : c'est lui qu'on
            // rescanne (§18.36, §22.3).
            nbVersions={p.principale ? courant.nb_versions : 1}
            onVersions={onVersions}
            // La pastille « lien » ne dit plus un rapprochement deviné : elle
            // marque ce qui a été **joint à la main** à ce document (§22.2).
            rattachement={p.id && !p.principale ? t("pièce jointe à la main") : null}
            // Le document lui-même est-il entré à la main ? (§22.68) C'est
            // l'histoire de sa **pièce principale**, pas des pièces jointes —
            // celles-là ont toujours été posées à la main.
            depotManuel={p.principale && courant?.depot_manuel === true}
            onLiaison={onLiaison}
          />
        ))}
        {(voisins || []).map((autre) => (
          <Vignette
            key={`voisin-${autre.id}`}
            documentId={autre.id}
            titre={autre.libelle || autre.nom_fichier}
            sousTitre={autre.categorie || t("Rejoint par le lien de la vue")}
            courante={autre.id === voisinChoisi}
            choisie={autre.id === voisinChoisi}
            onClic={() => {
              setVoisinChoisi((courant) => (courant === autre.id ? null : autre.id));
              setChoisie(null);
            }}
            action={t("Choisir ce document")}
            nbVersions={autre.nb_versions}
            onVersions={onVersions}
            rattachement={autre.rattachement || t("lien déclaré sur la vue")}
            onLiaison={onLiaison}
          />
        ))}
      </div>

      {tuiles.length === 0 && (voisins || []).length === 0 && (
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 12,
                      lineHeight: 1.45, maxWidth: 460 }}>
          {t("Cette entrée n'a pas de fichier, et rien ne lui est rattaché. Glissez-en un ci-dessus, ou désignez des documents depuis ses champs.")}
        </div>
      )}
      {tuiles.length === 1 && (voisins || []).length === 0 && (
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 12,
                      lineHeight: 1.45, maxWidth: 460 }}>
          {t("Ce document n'a qu'une pièce. Joignez-en une ci-dessus — une garantie, un bon de livraison — plutôt que d'en faire un document de plus : les champs seront remplis une seule fois.")}
        </div>
      )}
      </div>
    </div>
  );
}

/**
 * Ce qu'on peut faire de la pièce choisie (§22.2).
 *
 * Une barre plutôt que des icônes sur la tuile : les actions y tiennent avec
 * leur nom, et l'on sait ce qu'on va faire avant de cliquer. « Retirer » détache
 * la pièce du document — le fichier archivé part ensuite à la purge, comme pour
 * un document supprimé ; il n'est pas effacé sous les doigts.
 */
/**
 * « Voir », et une seconde façon de voir (§22.74).
 *
 * Le clic garde ce qu'il faisait : la pièce s'ouvre dans le panneau, sous les
 * yeux, sans quitter la fiche. Mais un PDF de douze pages ne se lit pas dans un
 * bandeau, et l'on veut alors l'écran entier. Cette seconde façon n'a pas à
 * encombrer la barre : elle se demande, par le chevron, et se referme dès qu'on
 * s'en va.
 *
 * Les deux moitiés sont des **liens** : un clic molette ou un Ctrl+clic ouvre un
 * onglet, ce qu'un navigateur fait d'un lien et que personne n'a envie de
 * réapprendre (§22.23).
 */
function BoutonVoir({ url, onVoir, titre }) {
  const [ouvert, setOuvert] = useState(false);
  const zone = useRef(null);

  // Un menu qui reste ouvert quand on regarde ailleurs est un menu qu'on ferme
  // à la main : il se referme donc au clic dehors et à l'échappement.
  useEffect(() => {
    if (!ouvert) return undefined;
    const dehors = (evenement) => {
      if (!zone.current?.contains(evenement.target)) setOuvert(false);
    };
    const echappe = (evenement) => { if (evenement.key === "Escape") setOuvert(false); };
    document.addEventListener("mousedown", dehors);
    document.addEventListener("keydown", echappe);
    return () => {
      document.removeEventListener("mousedown", dehors);
      document.removeEventListener("keydown", echappe);
    };
  }, [ouvert]);

  return (
    <span ref={zone} style={{ position: "relative", display: "inline-flex" }}>
      <a
        href={url || undefined}
        target="_blank"
        rel="noreferrer"
        onClick={(e) => { e.preventDefault(); onVoir?.(); }}
        style={{ ...boutonBarre, textDecoration: "none",
                 borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
        title={titre || t("Lire cette pièce — clic molette pour l'ouvrir dans un onglet")}
      >
        <FileText size={12} /> {t("Voir")}
      </a>
      <button
        onClick={() => setOuvert((o) => !o)}
        aria-label={t("Autres façons d'ouvrir")}
        aria-expanded={ouvert}
        title={t("Autres façons d'ouvrir")}
        style={{ ...boutonBarre, borderLeft: "none", padding: "3px 5px",
                 borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
      >
        <ChevronDown size={12} />
      </button>

      {ouvert && (
        <a
          href={url || undefined}
          target="_blank"
          rel="noreferrer"
          onClick={() => setOuvert(false)}
          style={{
            position: "absolute", top: "calc(100% + 4px)", right: 0, zIndex: 5,
            display: "inline-flex", alignItems: "center", gap: 6, whiteSpace: "nowrap",
            border: "1px solid var(--line-strong)", background: "var(--bg-panel)",
            color: "var(--ink)", borderRadius: "var(--radius)", padding: "5px 10px",
            fontSize: 11.5, textDecoration: "none", boxShadow: "var(--shadow-panel)",
          }}
        >
          <Maximize2 size={12} />
          {t("Ouvrir en plein écran, dans un onglet")}
        </a>
      )}
    </span>
  );
}


/**
 * La barre du document lié qu'on a désigné (§22.73).
 *
 * Cliquer une vignette voisine quittait la fiche pour la sienne. C'est rarement
 * ce qu'on veut : on la regarde **depuis** le document qu'on est en train de
 * lire, pour vérifier un montant ou une date. On la désigne donc, et l'on décide
 * ensuite — la lire, savoir ce qu'elle porte, ou aller pour de bon sur sa fiche.
 */
function BarreVoisin({ voisin, url, onVoir, onOuvrir, onFermer }) {
  const [details, setDetails] = useState(false);
  const champs = voisin.details || [];

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
      padding: "8px 14px", background: "var(--accent-soft)",
      borderBottom: "1px solid var(--line)", fontSize: 12.5,
    }}>
      <Link2 size={14} color="var(--accent)" style={{ flexShrink: 0 }} />
      <span style={{ fontWeight: 500, maxWidth: 260, overflow: "hidden",
                     textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {voisin.libelle || voisin.nom_fichier}
      </span>

      <button onClick={() => setDetails((ouvert) => !ouvert)} style={boutonBarre}
              title={t("Ce que ce document porte")}>
        <Info size={12} /> {t("Info")}
      </button>
      {/* Comme pour une pièce (§22.78) : le clic le lit **dans la fiche**, et le
          plein écran se demande à côté. Ouvrir un onglet d'office, c'était
          quitter l'écran pour vérifier un montant. */}
      <BoutonVoir url={url} onVoir={onVoir}
                  titre={t("Lire ce document ici — clic molette pour l'ouvrir dans un onglet")} />
      <button onClick={onOuvrir} style={boutonBarre}
              title={t("Quitter cette fiche pour la sienne")}>
        <ListTree size={12} /> {t("Ouvrir sa fiche")}
      </button>

      <div style={{ flex: 1 }} />
      <button onClick={onFermer} style={{ ...boutonBarre, border: "none" }}
              aria-label={t("Ne plus désigner ce document")}>
        <X size={12} />
      </button>

      {details && (
        <div style={{ width: "100%", fontSize: 11.5, color: "var(--ink-soft)",
                      marginTop: 4, lineHeight: 1.6 }}>
          {voisin.categorie && <div>{t("Classement")} : {t(voisin.categorie)}</div>}
          {voisin.date_document && <div>{t("Date du document")} : {voisin.date_document}</div>}
          {champs.map((champ) => (
            <div key={champ.libelle}>{t(champ.libelle)} : {champ.valeur}</div>
          ))}
          {!voisin.categorie && !voisin.date_document && champs.length === 0
            && t("Rien de plus à en dire d'ici : ouvrez sa fiche.")}
        </div>
      )}
    </div>
  );
}


function BarrePiece({ piece, url, seule, estAdmin, details, onDetails, onVoir,
                     onPrincipale, onRetirer, onFermer, rang = 0, nombre = 1,
                     onDeplacer }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
      padding: "8px 14px", background: "var(--accent-soft)",
      borderBottom: "1px solid var(--line)", fontSize: 12.5,
    }}>
      <FileText size={14} color="var(--accent)" style={{ flexShrink: 0 }} />
      <span style={{ fontWeight: 500, maxWidth: 260, overflow: "hidden",
                     textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {piece.nom_fichier}
      </span>

      <button onClick={onDetails} style={boutonBarre} title={t("Ce que l'on sait de cette pièce")}>
        <Info size={12} /> Info
      </button>
      <BoutonVoir url={url} onVoir={onVoir} />
      {!piece.principale && piece.id && (
        <button onClick={onPrincipale} style={boutonBarre}
                title={t("Faire de cette pièce la principale : c'est elle que le registre ouvrira")}>
          <Star size={12} /> Principale
        </button>
      )}
      {/* Ranger les pièces (§22.43). L'ordre décide de ce qu'on lit en premier :
          une facture, sa garantie et son bon de livraison ne se lisent pas dans
          l'ordre où on les a scannés. Deux boutons plutôt qu'un glisser-déposer :
          les vignettes se replient sur plusieurs rangs, et l'on désigne déjà une
          pièce pour agir dessus. */}
      {piece.id && !seule && onDeplacer && (
        <>
          <button onClick={() => onDeplacer(-1)} disabled={rang <= 0} style={boutonBarre}
                  title={t("Placer cette pièce avant la précédente")}
                  aria-label={t("Avancer cette pièce")}>
            <ChevronLeft size={12} />
          </button>
          <button onClick={() => onDeplacer(1)} disabled={rang >= nombre - 1}
                  style={boutonBarre} title={t("Placer cette pièce après la suivante")}
                  aria-label={t("Reculer cette pièce")}>
            <ChevronRight size={12} />
          </button>
        </>
      )}
      {estAdmin && piece.id && !seule && (
        <button onClick={onRetirer} style={{ ...boutonBarre, color: "var(--brick)",
                                             borderColor: "var(--brick)" }}
                title={t("Détacher cette pièce du document")}>
          <Trash2 size={12} /> Retirer
        </button>
      )}

      <button onClick={onFermer} style={{ ...boutonBarre, marginLeft: "auto" }}
              aria-label={t("Ne plus rien avoir de choisi")}>
        <X size={12} />
      </button>

      {details && (
        <div style={{ width: "100%", fontSize: 11.5, color: "var(--ink-soft)",
                      marginTop: 4, lineHeight: 1.5 }}>
          {piece.principale ? t("Pièce principale — c'est elle que le registre ouvre. ")
            : t("Pièce jointe à la main. ")}
          {piece.taille_octets != null
            && `${Math.max(1, Math.round(piece.taille_octets / 1024))} Ko. `}
          {piece.date_ajout && `Ajoutée le ${piece.date_ajout.replace("T", " à ")}. `}
          {!estAdmin && t("Seul un administrateur peut la retirer.")}
        </div>
      )}
    </div>
  );
}

const boutonBarre = {
  display: "inline-flex", alignItems: "center", gap: 4,
  border: "1px solid var(--line-strong)", background: "var(--bg-panel)",
  color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "3px 9px",
  fontSize: 11.5, cursor: "pointer",
};



/**
 * Une tuile : l'image de la première page, et de quoi nommer le document.
 *
 * L'image se demande tuile par tuile plutôt qu'en une fois : la première arrivée
 * s'affiche sans attendre les autres, et une page illisible — un format que le
 * moteur de rendu ne sait pas ouvrir — ne prive pas la grille des autres.
 */
function Vignette({ documentId, pieceId = null, titre, sousTitre, courante = false,
                    depotManuel = false,
                   choisie = false, onClic, action, nbVersions = 1, onVersions,
                   rattachement, onLiaison }) {
  const [url, setUrl] = useState(null);
  const [echec, setEchec] = useState(false);

  useEffect(() => {
    let objet;
    let vivant = true;
    setUrl(null);
    setEchec(false);
    // Chaque pièce a son image : le cache du serveur est indexé par empreinte,
    // deux pièces d'un même document ne se marchent donc pas dessus (§22.2).
    const demande = pieceId
      ? api.apercuPieceBlobUrl(documentId, pieceId)
      : api.apercuBlobUrl(documentId);
    demande
      .then((u) => {
        objet = u;
        if (vivant) setUrl(u);
        else URL.revokeObjectURL(u);
      })
      .catch(() => vivant && setEchec(true));
    return () => {
      vivant = false;
      if (objet) URL.revokeObjectURL(objet);
    };
  }, [documentId, pieceId]);

  return (
    // Les pastilles se posent **à côté** du bouton, pas dedans : un bouton dans
    // un bouton n'est pas du HTML valide, et le clavier n'y atteindrait jamais
    // le second.
    <div style={{ position: "relative", width: 158 }}>
      <div style={{ position: "absolute", top: 4, right: 4, zIndex: 1,
                    display: "flex", gap: 4 }}>
        {depotManuel && (
          <Pastille
            libelle={t("Déposé à la main dans l'application, et non par le dossier surveillé")}
            couleur="var(--accent)"
          >
            <Hand size={11} />
          </Pastille>
        )}
        {rattachement && (
          <Pastille
            libelle={`Document lié par « ${rattachement} » — voir ce qui les rapproche`}
            couleur="var(--accent)"
            onClic={() => onLiaison?.()}
          >
            <Link2 size={11} />
          </Pastille>
        )}
        {nbVersions > 1 && (
          <Pastille
            libelle={`${nbVersions} dépôts pour ce document — le plus récent est `
                   + `affiché ; voir les précédents`}
            couleur="var(--amber)"
            onClic={() => onVersions?.(documentId)}
          >
            <History size={11} />
            {nbVersions}
          </Pastille>
        )}
      </div>

    <button
      onClick={onClic}
      title={`${titre} — ${action}`}
      style={{
        width: "100%", padding: 8, textAlign: "left", background: "var(--bg-panel)",
        border: (choisie ? "2px solid var(--accent)"
          : "1px solid " + (courante ? "var(--accent)" : "var(--line)")),
        borderRadius: "var(--radius)", color: "var(--ink)", cursor: "pointer",
      }}
    >
      <div style={{
        height: 186, display: "flex", alignItems: "center", justifyContent: "center",
        overflow: "hidden", background: "var(--bg-panel-alt)",
        border: "1px solid var(--line)", borderRadius: 3,
      }}>
        {url ? (
          <img src={url} alt={`Première page de ${titre}`}
               style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
        ) : (
          <span style={{ fontSize: 11, color: "var(--ink-faint)", textAlign: "center",
                         padding: 8 }}>
            {echec ? t("Page non rendue") : "…"}
          </span>
        )}
      </div>
      <div style={{ fontSize: 12, marginTop: 7, lineHeight: 1.3,
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                    overflow: "hidden" }}>
        {titre}
      </div>
      {sousTitre && (
        <div style={{ fontSize: 11, color: courante ? "var(--accent)" : "var(--ink-faint)",
                      marginTop: 2, overflow: "hidden", textOverflow: "ellipsis",
                      whiteSpace: "nowrap" }}>
          {sousTitre}
        </div>
      )}
    </button>
    </div>
  );
}

/**
 * Une pastille de coin, à la manière d'une notification (§19.22).
 *
 * Elle ne dit pas ce que le document **est** — le titre s'en charge — mais ce
 * qu'il faut savoir avant de le lire : qu'il a été redéposé depuis, ou qu'il
 * n'est là que parce qu'un autre le rejoint. Deux choses qu'on ne devine pas en
 * regardant une première page, et qui changent la lecture qu'on en fait.
 */
function Pastille({ children, libelle, couleur, onClic }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClic?.(); }}
      title={libelle}
      aria-label={libelle}
      style={{
        display: "inline-flex", alignItems: "center", gap: 2,
        border: "1px solid var(--bg-panel)", background: couleur, color: "#fff",
        borderRadius: 9, padding: "1px 5px", fontSize: 10, lineHeight: 1.5,
        fontWeight: 600, boxShadow: "0 1px 3px rgba(0,0,0,.25)", cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}


// La section « Ce que ce document concerne » a disparu : elle affichait le
// rapprochement automatique par valeur partagée, qui remplissait le panneau de
// liens que personne n'avait déclarés. Ce qui se montre maintenant a été voulu —
// une pièce qu'on a jointe, un lien de vue qu'un administrateur a posé, un
// rattachement fait à la main. La déduction, elle, reste : elle remplit les
// champs, elle ne prétend plus dessiner un réseau.


/**
 * Par où l'on continue (§22.5).
 *
 * La correspondance de champs déclarée sur la vue : « depuis celle-ci, ouvrir
 * celle-là sur la ligne qu'on regarde ». Un lien dont le champ est vide sur ce
 * document-ci n'est pas affiché — proposer « ses factures » sur une fiche sans
 * titulaire ouvrirait une liste vide, et l'on chercherait pourquoi.
 */
function SectionLiensDeVue({ liens, document: doc, onSuivre }) {
  const utilisables = (liens || [])
    .map((lien) => ({ lien, valeur: valeurDuChamp(doc, lien.champ_source) }))
    .filter(({ valeur }) => valeur !== undefined && valeur !== null && valeur !== "");
  if (utilisables.length === 0) return null;

  return (
    <Section titre={t("Continuer vers")}>
      {utilisables.map(({ lien, valeur }) => (
        <button
          key={`${lien.vue_id}-${lien.champ_cible}`}
          onClick={() => onSuivre?.(lien, valeur)}
          title={`Ouvrir cette vue filtrée sur « ${valeur} »`}
          style={{ display: "block", width: "100%", textAlign: "left", border: "none",
                   background: "transparent", color: "var(--accent)", fontSize: 12,
                   padding: "3px 0", cursor: "pointer" }}
        >
          {t(lien.libelle)}
        </button>
      ))}
    </Section>
  );
}

/**
 * La valeur d'un champ sur ce document, dans le vocabulaire des filtres :
 * `meta:<clé>` pour une métadonnée, sinon une colonne du document.
 */
export function valeurDuChamp(doc, champ) {
  if (!doc || !champ) return null;
  if (champ.startsWith("meta:")) return (doc.metadonnees || {})[champ.slice(5)];
  if (champ === "categorie") return doc.categorie_id;
  return doc[champ];
}

/**
 * Ce que quelqu'un a rattaché à ce document (§22.4).
 *
 * C'est un lien **posé à la main**, entre deux papiers qui ne partagent aucune
 * valeur mais se répondent — un contrat et son avenant. Rien ici n'est deviné :
 * le rapprochement automatique par valeur partagée ne s'affiche plus.
 */
function SectionRattachements({ rattaches, onOuvrir, onDetacher }) {
  if (!rattaches || rattaches.length === 0) return null;
  return (
    <Section titre={t("Rattaché à la main")}>
      {rattaches.map((autre) => (
        <div key={autre.document_id}
             style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <button
            onClick={() => onOuvrir?.(autre.document_id)}
            title={autre.nom_fichier}
            style={{ flex: 1, textAlign: "left", border: "none", background: "transparent",
                     color: "var(--accent)", fontSize: 12, padding: "3px 0" }}
          >
            {t(autre.libelle)}
            {autre.categorie && (
              <span style={{ color: "var(--ink-faint)" }}> · {autre.categorie}</span>
            )}
            {autre.intitule && (
              <span style={{ color: "var(--ink-faint)" }}> — {t(autre.intitule)}</span>
            )}
          </button>
          <button
            onClick={() => onDetacher?.(autre.document_id)}
            title={t("Détacher : le lien disparaît des deux côtés")}
            aria-label={`Détacher ${t(autre.libelle)}`}
            style={{ border: "none", background: "transparent", color: "var(--ink-faint)",
                     padding: 2, cursor: "pointer" }}
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </Section>
  );
}


/**
 * Les documents attachés par un champ (§22.11).
 *
 * « Factures liées » sous un entretien : ce sont des documents **choisis** dans
 * la GED, avec l'intitulé que le type leur donne. Chaque champ garde son bloc —
 * les fondre en une seule liste perdrait ce qui les distingue, et c'est
 * précisément ce que le champ apporte sur un rattachement anonyme.
 *
 * Un champ vide reste affiché : quand on ouvre une fiche, on cherche souvent ce
 * qui **manque** (§19.20), et une case absente laisse croire qu'elle n'existe pas.
 */
function SectionAttaches({ attaches, onOuvrir }) {
  if (!attaches || attaches.length === 0) return null;
  return (
    <>
      {attaches.map((champ) => (
        <Section key={champ.champ} titre={t(champ.libelle)}>
          {champ.documents.length === 0 ? (
            <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
              {t("Aucun document attaché — cela se règle en modifiant la fiche.")}
            </div>
          ) : (
            champ.documents.map((autre) => (
              <button
                key={autre.id}
                onClick={() => onOuvrir?.(autre.id)}
                title={autre.nom_fichier}
                style={{ display: "block", width: "100%", textAlign: "left", border: "none",
                         background: "transparent", color: "var(--accent)", fontSize: 12,
                         padding: "3px 0", cursor: "pointer" }}
              >
                {t(autre.libelle)}
                {autre.categorie && (
                  <span style={{ color: "var(--ink-faint)" }}> · {autre.categorie}</span>
                )}
                {/* Ce que l'administration a coché : c'est ce qui distingue deux
                    factures du même mois (§22.19). */}
                {(autre.details || []).length > 0 && (
                  <span style={{ display: "block", color: "var(--ink-soft)",
                                 fontSize: 11.5 }}>
                    {autre.details.map((d) => `${t(d.libelle)} : ${d.valeur}`).join(" · ")}
                  </span>
                )}
              </button>
            ))
          )}
        </Section>
      ))}
    </>
  );
}
