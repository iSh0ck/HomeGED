import React, { useEffect, useMemo, useState } from "react";
import { Wand2, Check, AlertTriangle, Search, FileText, ChevronLeft, ChevronRight } from "lucide-react";
import { api, adminApi } from "../api";
import Modal, { champStyle, boutonPrimaire } from "./Modal.jsx";
import ZoneDepot from "./ZoneDepot.jsx";
import { libelleDocument, sousTitreDocument } from "../lib/document";
import { t } from "../lib/langue";

/**
 * Apprendre une règle en la montrant (§21.5, bêta).
 *
 * L'écran des règles demande une expression régulière écrite à l'aveugle : on
 * décrit avec des symboles ce qu'on a sous les yeux, on enregistre, on relance un
 * traitement, et l'on découvre que le motif ne prend rien. C'est la boucle la
 * plus décourageante du projet.
 *
 * Ici, on ouvre un document du type, on **clique la valeur** sur la page, puis
 * l'intitulé qui l'annonce, et la règle se construit — avec, dans la foulée, ce
 * qu'elle extrait de ce document-ci. La vérification a lieu avant d'enregistrer,
 * et non après un retraitement complet.
 *
 * Le document d'exemple vient de deux endroits (§22.35) :
 *   - **la GED**, cadrée par défaut sur le type en cours d'édition — la règle
 *     qu'on écrit pour « Factures » se montre presque toujours sur une facture
 *     (§22.37). Le dernier mois sans rien taper, puis la recherche globale
 *     (§21.2) dès trois caractères — peu importe la colonne. Et un clic pour
 *     élargir à toute la GED, quand le document qu'on a sous la main n'est pas
 *     rangé là où la règle servira ;
 *   - **un fichier importé à la main**, qui n'entre pas au registre. C'est le
 *     cas du premier papier d'une sorte nouvelle : écrire la règle d'abord
 *     évite de déposer un document pour le voir mal lu, corriger, redéposer.
 *
 * Bêta assumée : elle ne remplace pas l'écriture à la main, elle l'évite quand
 * elle suffit. Ce qu'elle propose reste modifiable avant enregistrement.
 */
const boutonPage = {
  display: "inline-flex", alignItems: "center", gap: 4,
  border: "1px solid var(--line-strong)", background: "var(--bg-panel)",
  color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "3px 9px",
  fontSize: 12, cursor: "pointer",
};

export default function ApprentissageRegle({ categorieId, categorieNom, champCible,
                                            onUtiliser, onFermer }) {
  const [onglet, setOnglet] = useState("ged");
  // Le type en cours d'édition d'abord : c'est presque toujours là qu'est le
  // document qu'on veut montrer. Élargir reste à un clic (§22.37).
  const [partout, setPartout] = useState(false);
  const [terme, setTerme] = useState("");
  const [documents, setDocuments] = useState([]);
  // Ce que la liste montre : un extrait récent, ou un résultat de recherche. Les
  // confondre ferait croire qu'un document cherché n'existe pas (§22.26).
  const [extraitRecent, setExtraitRecent] = useState(true);
  const [minimum, setMinimum] = useState(3);
  // Ce que la même recherche aurait trouvé hors du type : sans ce nombre,
  // « aucun résultat » laisse croire que le document n'existe pas.
  const [ailleurs, setAilleurs] = useState(0);
  const [chargementListe, setChargementListe] = useState(false);
  // Le document montré : soit une entrée du registre, soit un exemple importé.
  // Un seul à la fois — c'est ce qu'on a sous les yeux quand on clique un mot.
  const [choix, setChoix] = useState(null);   // { type, id?, jeton?, libelle }
  const [image, setImage] = useState(null);
  const [page, setPage] = useState(null);       // { largeur, hauteur, mots, pages, avertissement }
  // La page regardée (§22.75). Une facture porte parfois sa référence en
  // deuxième page, et il n'y avait aucun moyen d'y arriver.
  const [numeroPage, setNumeroPage] = useState(1);
  const [cible, setCible] = useState("valeur"); // ce que le prochain clic désigne
  const [valeur, setValeur] = useState([]);
  const [ancre, setAncre] = useState([]);
  const [proposition, setProposition] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(false);

  useEffect(() => {
    const cherche = terme.trim();
    // Une ou deux lettres ne déclenchent rien : ni requête, ni attente. La liste
    // reste celle du dernier mois, et l'on dit ce qu'il manque pour chercher.
    if (cherche.length > 0 && cherche.length < minimum) return undefined;
    let vivant = true;
    setChargementListe(true);
    const minuterie = setTimeout(() => {
      adminApi.exemplesApprentissage(cherche, partout ? null : categorieId)
        .then((reponse) => {
          if (!vivant) return;
          const liste = reponse.documents || [];
          setDocuments(liste);
          // Le premier de la liste s'ouvre de lui-même, mais jamais à la place
          // d'un document déjà choisi : on n'arrache pas la page sous les clics
          // parce qu'une recherche a répondu.
          if (liste.length) {
            setChoix((actuel) => actuel
              || { type: "ged", id: liste[0].id, libelle: libelleDocument(liste[0]) });
          }
          setExtraitRecent(reponse.recents !== false);
          setAilleurs(reponse.ailleurs || 0);
          if (reponse.minimum_recherche) setMinimum(reponse.minimum_recherche);
        })
        .catch((e) => vivant && setErreur(e.message))
        .finally(() => vivant && setChargementListe(false));
    }, cherche ? 200 : 0);
    return () => { vivant = false; clearTimeout(minuterie); };
  }, [terme, minimum, partout, categorieId]);

  /** Remet à zéro ce qui était désigné : les mots d'une page n'ont pas de sens sur une autre. */
  function repartirDe(nouveau) {
    setChoix(nouveau);
    setValeur([]);
    setAncre([]);
    setProposition(null);
    setPage(null);
    setImage(null);
    setNumeroPage(1);
  }

  useEffect(() => {
    if (!choix) return undefined;
    let url;
    let vivant = true;
    setChargement(true);
    setErreur(null);

    // Un exemple importé n'a qu'une page rendue : il est lu au dépôt, et l'on ne
    // garde pas le PDF. Le registre, lui, se feuillette.
    const charge = choix.type === "import"
      ? Promise.all([adminApi.apercuExempleBlobUrl(choix.jeton),
                     Promise.resolve(choix.page)])
      : Promise.all([api.apercuBlobUrl(choix.id, numeroPage),
                     api.motsDocument(choix.id, numeroPage)]);

    charge
      .then(([blob, mots]) => {
        url = blob;
        if (!vivant) { URL.revokeObjectURL(blob); return; }
        setImage(blob);
        setPage(mots);
      })
      .catch((e) => vivant && setErreur(e.message))
      .finally(() => vivant && setChargement(false));

    return () => { vivant = false; if (url) URL.revokeObjectURL(url); };

  }, [choix, numeroPage]);

  const motsValeur = useMemo(() => new Set(valeur), [valeur]);
  const motsAncre = useMemo(() => new Set(ancre), [ancre]);

  function cliquer(index) {
    const liste = cible === "valeur" ? valeur : ancre;
    const poser = cible === "valeur" ? setValeur : setAncre;
    poser(liste.includes(index) ? liste.filter((i) => i !== index) : [...liste, index]);
    setProposition(null);
  }

  /** Les mots choisis, remis dans l'ordre de la page : on lit une ligne, pas des clics. */
  function texteDe(indices) {
    return [...indices].sort((a, b) => a - b)
      .map((i) => page.mots[i].texte).join(" ");
  }

  async function proposer() {
    setErreur(null);
    try {
      setProposition(await adminApi.apprendreRegle({
        // Un exemple importé n'a pas d'identifiant au registre : c'est son texte
        // qui part, puisqu'il n'y a rien à relire côté serveur (§22.35).
        document_id: choix?.type === "import" ? null : choix?.id,
        texte: choix?.type === "import" ? choix.texte : null,
        valeur: texteDe(valeur),
        ancre: ancre.length ? texteDe(ancre) : null,
        champ_cible: champCible || null,
      }));
    } catch (e) {
      setErreur(e.message);
      setProposition(null);
    }
  }

  // Dire où l'on cherche, partout où on le dit : un « aucun résultat » qui ne
  // nomme pas son périmètre se lit comme « ce document n'existe pas ».
  const perimetreDit = categorieId && !partout
    ? (categorieNom ? `« ${categorieNom} »` : t("ce type de document"))
    : t("toute la GED");

  const ongletStyle = (cle) => ({
    border: "none", borderBottom: onglet === cle
      ? "2px solid var(--accent)" : "2px solid transparent",
    background: "transparent", padding: "6px 10px", fontSize: 12.5, cursor: "pointer",
    color: onglet === cle ? "var(--accent)" : "var(--ink-soft)",
  });

  return (
    <Modal titre={t("Apprendre une règle en la montrant")} onClose={onFermer} width={860}>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55, marginTop: 2 }}>
        <strong style={{ color: "var(--amber)" }}>{t("Bêta.")}</strong> Cliquez la valeur sur le
        document, puis l'intitulé qui l'annonce — c'est lui qui permettra de la retrouver
        sur les autres documents. La règle proposée reste modifiable avant enregistrement.
      </p>

      <label style={{ ...champStyle, marginTop: 12 }}>{t("Document d'exemple")}</label>
      {/* Deux provenances, deux onglets : un document déjà classé, ou un papier
          qu'on vient de recevoir et dont la GED ne sait rien encore (§22.35). */}
      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--line)",
                    marginBottom: 10 }}>
        <button onClick={() => setOnglet("ged")} style={ongletStyle("ged")}
                aria-pressed={onglet === "ged"}>
          {t("Documents déjà présents dans la GED")}
        </button>
        <button onClick={() => setOnglet("import")} style={ongletStyle("import")}
                aria-pressed={onglet === "import"}>
          Document à importer
        </button>
      </div>

      {onglet === "ged" ? (
        <>
          {/* Le périmètre se choisit, comme dans la recherche globale (§21.2) :
              le type d'abord — c'est là qu'est le document neuf fois sur dix —
              et toute la GED d'un clic (§22.37). */}
          {categorieId && (
            <div style={{ display: "flex", gap: 0, marginBottom: 6,
                          border: "1px solid var(--line-strong)",
                          borderRadius: "var(--radius)", overflow: "hidden",
                          width: "fit-content" }}>
              {[[false, categorieNom ? `Dans « ${categorieNom} »` : t("Dans ce type")],
                [true, t("Toute la GED")]].map(([valeur, libelle]) => (
                <button
                  key={String(valeur)}
                  onClick={() => setPartout(valeur)}
                  aria-pressed={partout === valeur}
                  style={{ border: "none", padding: "5px 11px", fontSize: 12,
                           cursor: "pointer", fontFamily: "inherit",
                           background: partout === valeur ? "var(--accent-soft)" : "transparent",
                           color: partout === valeur ? "var(--accent)" : "var(--ink-soft)" }}
                >
                  {libelle}
                </button>
              ))}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 6,
                        border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
                        padding: "5px 8px", background: "var(--bg-panel-alt)" }}>
            <Search size={12} color="var(--ink-faint)" />
            <input
              value={terme}
              aria-label={t("Chercher un document d'exemple")}
              placeholder={`Chercher dans ${perimetreDit} : émetteur, montant, nom de fichier…`}
              onChange={(e) => setTerme(e.target.value)}
              style={{ flex: 1, border: "none", background: "transparent", outline: "none",
                       fontSize: 12.5, fontFamily: "inherit", color: "var(--ink)" }}
            />
          </div>
          <div className="scrollbar-thin"
               style={{ maxHeight: 150, overflowY: "auto", marginTop: 4,
                        border: "1px solid var(--line)", borderRadius: "var(--radius)" }}>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", padding: "5px 8px",
                          borderBottom: "1px solid var(--line)", lineHeight: 1.45 }}>
              {terme.trim().length > 0 && terme.trim().length < minimum
                ? `Encore ${minimum - terme.trim().length} caractère(s) pour chercher.`
                : extraitRecent
                  ? `Documents ajoutés dans ${perimetreDit} depuis un mois. `
                    + `Tapez au moins ${minimum} caractères pour chercher au-delà, `
                    + `sur n'importe quelle colonne.`
                  : `Résultats de la recherche dans ${perimetreDit}.`}
            </div>
            {chargementListe && documents.length === 0 && (
              <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "6px 8px" }}>
                Recherche…
              </div>
            )}
            {!chargementListe && documents.length === 0 && (
              <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "6px 8px" }}>
                {extraitRecent
                  ? t("Aucun document ajouté ce mois-ci — cherchez-en un, ou importez un fichier.")
                  : t("Aucun document ne correspond.")}
                {/* « Pas ici » n'est pas « nulle part » : sans ce rebond, on
                    conclurait que le document n'existe pas (§22.37). */}
                {!extraitRecent && !partout && ailleurs > 0 && (
                  <button
                    onClick={() => setPartout(true)}
                    style={{ display: "block", marginTop: 4, border: "none",
                             background: "transparent", color: "var(--accent)",
                             fontSize: 12, fontFamily: "inherit", padding: 0,
                             cursor: "pointer" }}
                  >
                    {ailleurs === 1
                      ? t("1 document ailleurs dans la GED — chercher partout")
                      : `${ailleurs} documents ailleurs dans la GED — chercher partout`}
                  </button>
                )}
              </div>
            )}
            {documents.map((doc) => (
              <button
                key={doc.id}
                onClick={() => repartirDe({ type: "ged", id: doc.id,
                                            libelle: libelleDocument(doc) })}
                aria-pressed={choix?.type === "ged" && choix.id === doc.id}
                style={{ display: "block", width: "100%", textAlign: "left", border: "none",
                         fontSize: 12, padding: "5px 8px", cursor: "pointer",
                         color: "var(--ink)", fontFamily: "inherit",
                         background: choix?.type === "ged" && choix.id === doc.id
                           ? "var(--accent-soft)" : "transparent" }}
              >
                {libelleDocument(doc)}
                <span style={{ display: "block", color: "var(--ink-soft)", fontSize: 11.5 }}>
                  {[doc.nom_fichier, sousTitreDocument(doc)].filter(Boolean).join(" · ")}
                </span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                      overflow: "hidden" }}>
          <ZoneDepot
            invitation={t("Glissez ici le document sur lequel écrire la règle")}
            ariaLabel={t("Importer un document d'exemple")}
            multiple={false}
            envoyer={async (fichier) => {
              const exemple = await adminApi.importerExemple(fichier);
              repartirDe({ type: "import", jeton: exemple.jeton, texte: exemple.texte,
                           page: exemple.page, libelle: exemple.nom_fichier });
            }}
            succes={() => t("Document lu. Cliquez la valeur sur la page.")}
          />
          <p style={{ fontSize: 11.5, color: "var(--ink-faint)", padding: "8px 12px",
                      margin: 0, lineHeight: 1.5 }}>
            {t("Ce fichier n'entre pas dans la GED : il est lu le temps d'écrire la règle, puis effacé. Déposez-le normalement ensuite — la règle s'y appliquera.")}
          </p>
        </div>
      )}

      {choix && (
        <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "12px 0" }}>
          <div style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: "var(--ink-soft)",
                        display: "flex", alignItems: "center", gap: 6 }}>
            <FileText size={13} style={{ flexShrink: 0 }} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis",
                           whiteSpace: "nowrap" }}>{t(choix.libelle)}</span>
          </div>
          <div style={{ display: "flex", border: "1px solid var(--line-strong)",
                        borderRadius: "var(--radius)", overflow: "hidden" }}>
            {[["valeur", t("La valeur")], ["ancre", t("Son intitulé")]].map(([cle, libelle]) => (
              <button
                key={cle}
                onClick={() => setCible(cle)}
                aria-pressed={cible === cle}
                style={{
                  border: "none", padding: "7px 12px", fontSize: 12.5,
                  background: cible === cle ? "var(--accent-soft)" : "transparent",
                  color: cible === cle ? "var(--accent)" : "var(--ink-soft)",
                }}
              >
                {libelle}
              </button>
            ))}
          </div>
        </div>
      )}

      {erreur && (
        <div style={{ fontSize: 12.5, color: "var(--brick)", marginBottom: 10 }}>{erreur}</div>
      )}
      {page?.avertissement && (
        <div style={{ fontSize: 12.5, color: "var(--amber)", marginBottom: 10,
                      display: "flex", gap: 6 }}>
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          {page.avertissement}
        </div>
      )}

      {/* Feuilleter le document (§22.75). Une facture porte parfois sa référence
          en deuxième page, et l'outil n'en montrait que la première : la valeur
          qu'on venait désigner était hors d'atteinte. La barre ne s'affiche que
          s'il y a quelque chose à feuilleter — un document d'une page n'a pas
          besoin qu'on le lui dise. */}
      {choix?.type !== "import" && (page?.pages || 1) > 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10,
                      fontSize: 12, color: "var(--ink-soft)" }}>
          <button
            type="button"
            onClick={() => setNumeroPage((n) => Math.max(1, n - 1))}
            disabled={numeroPage <= 1 || chargement}
            style={boutonPage}
            title={t("Page précédente")}
          >
            <ChevronLeft size={13} /> {t("Précédente")}
          </button>
          <span className="tabular">
            {t("Page {n} sur {total}", { n: numeroPage, total: page.pages })}
          </span>
          <button
            type="button"
            onClick={() => setNumeroPage((n) => Math.min(page.pages, n + 1))}
            disabled={numeroPage >= page.pages || chargement}
            style={boutonPage}
            title={t("Page suivante")}
          >
            {t("Suivante")} <ChevronRight size={13} />
          </button>
          <span style={{ fontSize: 11, color: "var(--ink-faint)" }}>
            {t("Ce qui est désigné vaut pour la page où on l'a désigné.")}
          </span>
        </div>
      )}

      <div style={{ position: "relative", maxHeight: "46vh", overflow: "auto",
                    border: "1px solid var(--line)", borderRadius: "var(--radius)",
                    background: "var(--bg-panel-alt)", marginTop: choix ? 0 : 12 }}
           className="scrollbar-thin">
        {!choix && !chargement && (
          <div style={{ padding: 20, fontSize: 12.5, color: "var(--ink-faint)" }}>
            {t("Choisissez un document d'exemple, ou importez-en un.")}
          </div>
        )}
        {chargement && (
          <div style={{ padding: 20, fontSize: 12.5, color: "var(--ink-faint)" }}>
            {t("Chargement du document…")}
          </div>
        )}
        {image && (
          <div style={{ position: "relative", display: "inline-block", width: "100%" }}>
            <img src={image} alt="Document" style={{ width: "100%", display: "block" }} />
            {/* Un rectangle par mot, posé en pourcentage : les positions sont
                rapportées à la page, l'image se redimensionne, et les deux
                restent alignés sans qu'on connaisse la résolution du rendu. */}
            {(page?.mots || []).map((mot, index) => {
              const dansValeur = motsValeur.has(index);
              const dansAncre = motsAncre.has(index);
              return (
                <button
                  key={index}
                  onClick={() => cliquer(index)}
                  title={t(mot.texte)}
                  aria-label={`Choisir « ${t(mot.texte)} »`}
                  style={{
                    position: "absolute",
                    left: `${mot.x * 100}%`, top: `${mot.y * 100}%`,
                    width: `${mot.l * 100}%`, height: `${mot.h * 100}%`,
                    border: dansValeur ? "2px solid var(--accent)"
                      : dansAncre ? "2px solid var(--amber)" : "1px solid transparent",
                    background: dansValeur ? "rgba(80,140,255,.18)"
                      : dansAncre ? "rgba(220,160,40,.18)" : "transparent",
                    borderRadius: 2, padding: 0, cursor: "pointer",
                  }}
                />
              );
            })}
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12,
                    flexWrap: "wrap" }}>
        <div style={{ fontSize: 12.5, color: "var(--ink-soft)", flex: 1, minWidth: 220 }}>
          {valeur.length ? (
            <>
              Valeur : <strong>{texteDe(valeur)}</strong>
              {ancre.length > 0 && <> · annoncée par <strong>{texteDe(ancre)}</strong></>}
            </>
          ) : t("Aucune valeur désignée pour l'instant.")}
        </div>
        <button onClick={proposer} disabled={!valeur.length} style={boutonPrimaire}>
          <Wand2 size={14} />
          Proposer une règle
        </button>
      </div>

      {proposition && (
        <div style={{ marginTop: 14, padding: "12px 14px", border: "1px solid var(--line)",
                      borderRadius: "var(--radius)", background: "var(--bg-panel-alt)" }}>
          <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginBottom: 4 }}>
            Expression proposée
          </div>
          <code style={{ fontSize: 12, wordBreak: "break-all" }}>{proposition.pattern}</code>

          <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 10,
                        fontSize: 12.5,
                        color: proposition.conforme ? "var(--accent)" : "var(--brick)" }}>
            {proposition.conforme ? <Check size={14} /> : <AlertTriangle size={14} />}
            {proposition.conforme
              ? <>Sur ce document, elle extrait bien « {proposition.valeur_extraite} ».</>
              : proposition.trouve
                ? <>Elle extrait « {proposition.valeur_extraite} », et non ce que vous avez
                    désigné. Ajoutez l'intitulé, ou corrigez l'expression après coup.</>
                : <>Elle ne trouve rien sur ce document. Désignez aussi l'intitulé qui
                    annonce la valeur.</>}
          </div>

          <button
            onClick={() => onUtiliser?.(proposition)}
            style={{ ...boutonPrimaire, marginTop: 12 }}
          >
            {t("Utiliser cette règle")}
          </button>
        </div>
      )}
    </Modal>
  );
}
