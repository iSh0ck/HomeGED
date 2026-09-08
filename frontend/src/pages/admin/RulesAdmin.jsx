import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Pencil, Plus, Trash2, Wand2 } from "lucide-react";
import { adminApi, api } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import Liste from "../../components/champs/Liste.jsx";
import SaisieSuggeree from "../../components/champs/SaisieSuggeree.jsx";
import { avecDrapeaux, drapeauxDe } from "../../lib/regex";
import { referenceRegle } from "../../lib/travaux";
import RoleEcran from "../../components/RoleEcran.jsx";
import ApprentissageRegle from "../../components/ApprentissageRegle.jsx";
import { t } from "../../lib/langue";

const VIDE = { nom: "", champ_cible: "", pattern: "", fonction: "", parametre: "",
               type_champ: "texte", priorite: 100, actif: true };
/**
 * Ce qu'un motif peut porter en tête (§22.30).
 *
 * Trois états utiles sur les six drapeaux de Python : les autres ne servent
 * jamais à lire un document. L'aide s'affiche au survol du choix, parce que
 * c'est là qu'on se demande lequel prendre.
 */
const DRAPEAUX = () => [
  { valeur: "", libelle: t("Tel quel"),
    aide: t("La casse compte, et ^ $ désignent le début et la fin du texte entier. Convient à un motif purement numérique.") },
  { valeur: "(?i)", libelle: t("(?i) — sans tenir compte de la casse"),
    aide: t("« facture », « Facture » et « FACTURE » sont reconnus de la même façon. C'est presque toujours ce qu'il faut sur un texte océrisé : la casse dépend de la mise en page du papier, pas de son contenu.") },
  { valeur: "(?im)", libelle: t("(?im) — casse ignorée, ligne par ligne"),
    aide: t("Comme (?i), et ^ $ désignent le début et la fin de **chaque ligne**. Indispensable pour un motif ancré sur une ligne entière — sans lui, ^…$ exigerait que la page tienne sur une seule ligne, donc ne trouverait jamais rien.") },
  { valeur: "(?m)", libelle: t("(?m) — ligne par ligne, casse respectée"),
    aide: t("^ $ désignent le début et la fin de chaque ligne, mais « Facture » et « facture » restent deux choses différentes. Rare : à réserver aux motifs où la casse porte un sens.") },
];

const JEU_VIDE = { nom: "", reconnaissance: "", generique: false,
                   actif: true, priorite: 100 };

export default function RulesAdmin({ onMontage, contexte }) {
  // Un type de document, puis un de ses jeux : on ne voit que les règles qui
  // s'appliquent là (§19.6). C'est ce qui répond à « ça permettrait d'en avoir
  // moins à l'écran » — une liste unique grossissait à chaque émetteur.
  const [categories, setCategories] = useState([]);
  const [categorieId, setCategorieId] = useState(null);
  const [jeux, setJeux] = useState([]);
  const [jeuId, setJeuId] = useState(null);
  const [editionJeu, setEditionJeu] = useState(null);
  const [suppressionJeu, setSuppressionJeu] = useState(null);
  const [regles, setRegles] = useState([]);
  const [edition, setEdition] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [suppression, setSuppression] = useState(null);
  // Catalogue des fonctions prêtes à l'emploi (§18.35), décrit par l'API : leur
  // intitulé et leur description ne sont écrits qu'une fois, du côté qui les
  // applique.
  const [fonctions, setFonctions] = useState([]);
  const fonctionChoisie = fonctions.find((f) => f.cle === edition?.fonction);

  useEffect(() => {
    adminApi.fonctionsExtraction().then(setFonctions).catch(() => {});
    adminApi.categories().then((toutes) => {
      // Un jeu appartient à un type de document : un dossier de classement ne
      // reçoit rien, le proposer ne mènerait qu'à un refus.
      const types = toutes.filter((c) => (c.nature || "type") !== "dossier");
      setCategories(types);
      // Le type sur lequel on travaillait, quand on arrive depuis l'assemblage
      // (§22.20) : y revenir à la main après avoir cliqué « ouvrir les règles »
      // était le genre de pas perdu qui fait renoncer.
      if (categorieId === null) {
        const voulu = contexte?.categorieId;
        if (voulu && types.some((c) => c.id === voulu)) setCategorieId(voulu);
        else if (types.length) setCategorieId(types[0].id);
      }
    }).catch((e) => setErreur(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const chargerJeux = useCallback(() => {
    if (!categorieId) return;
    adminApi.jeuxExtraction(categorieId)
      .then((liste) => {
        setJeux(liste);
        setJeuId((actuel) => (liste.some((j) => j.id === actuel) ? actuel : liste[0]?.id ?? null));
      })
      .catch((e) => setErreur(e.message));
  }, [categorieId]);
  useEffect(chargerJeux, [chargerJeux]);

  useEffect(() => {
    if (!categorieId) { setCibles([]); return; }
    adminApi.champsCibles(categorieId).then(setCibles).catch(() => setCibles([]));
  }, [categorieId]);

  // Le jeu voulu, quand on arrive depuis l'assemblage : une règle vit dans un
  // jeu, et l'ouvrir sans choisir le sien ne montrerait rien (§22.28).
  useEffect(() => {
    if (contexte?.jeuId && jeux.some((j) => j.id === contexte.jeuId)) {
      setJeuId(contexte.jeuId);
    }
  }, [contexte, jeux]);

  // Arriver depuis l'assemblage ouvre le formulaire : sur **la règle** quand on
  // vient d'un champ déjà rempli (§22.28), ou vide avec la colonne cible déjà
  // remplie quand la règle reste à écrire (§22.27) — le champ qu'on venait
  // remplir est le seul renseignement qu'on ait, et le retaper à la lettre près
  // est une occasion de se tromper.
  const [amorce, setAmorce] = useState(false);
  useEffect(() => {
    if (amorce || !jeuId) return;
    if (contexte?.regleId) {
      const trouvee = regles.find((r) => r.id === contexte.regleId);
      if (!trouvee) return;    // les règles du jeu ne sont pas encore là
      setEdition(trouvee);
      setAmorce(true);
      return;
    }
    if (contexte?.champCible) {
      setEdition({ ...VIDE, champ_cible: contexte.champCible });
      setAmorce(true);
    }
  }, [contexte, jeuId, regles, amorce]);

  const charger = useCallback(() => {
    if (!jeuId) {
      setRegles([]);
      return;
    }
    adminApi.regles(jeuId).then(setRegles).catch((e) => setErreur(e.message));
  }, [jeuId]);
  useEffect(charger, [charger]);

  const jeuCourant = jeux.find((j) => j.id === jeuId);
  // L'apprentissage visuel (§21.5, bêta) : on montre la valeur sur un document
  // plutôt que d'écrire l'expression à l'aveugle.
  const [apprentissage, setApprentissage] = useState(false);
  // Ce qu'une règle peut remplir pour ce type (§21.11) : la colonne cible se
  // tapait à l'aveugle, et une faute de frappe créait une métadonnée jumelle que
  // rien ne signalait.
  const [cibles, setCibles] = useState([]);

  // Les types, à plat et par ordre alphabétique : c'est ainsi qu'on cherche un
  // nom qu'on connaît déjà. Le dossier accompagne le nom sans le classer.
  const typesTries = useMemo(() => {
    const nomDossier = new Map(categories.map((c) => [c.id, c.nom]));
    return [...categories]
      .map((c) => ({ ...c, dossier: nomDossier.get(c.parent_id) || null }))
      .sort((a, b) => a.nom.localeCompare(b.nom, "fr", { sensitivity: "base" }));
  }, [categories]);

  // Les jeux dans l'ordre où ils sont **essayés** : c'est la priorité qui décide
  // lequel s'applique, la liste doit donc se lire dans cet ordre-là, priorité en
  // tête. Un ordre alphabétique aurait laissé croire à un examen au hasard.
  const jeuxTries = useMemo(
    () => [...jeux].sort((a, b) => (a.priorite - b.priorite)
                                   || a.nom.localeCompare(b.nom, "fr")),
    [jeux]);

  async function enregistrerJeu(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const payload = {
        categorie_id: categorieId,
        nom: editionJeu.nom,
        reconnaissance: (editionJeu.reconnaissance || "").trim() || null,
        generique: !!editionJeu.generique,
        actif: !!editionJeu.actif,
        priorite: Number(editionJeu.priorite) || 100,
      };
      if (editionJeu.id) await adminApi.modifierJeuExtraction(editionJeu.id, payload);
      else await adminApi.creerJeuExtraction(payload);
      setEditionJeu(null);
      chargerJeux();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function supprimerJeu() {
    try {
      await adminApi.supprimerJeuExtraction(suppressionJeu.id);
      setJeuId(null);
      chargerJeux();
    } catch (err) {
      setErreur(err.message);
    }
    setSuppressionJeu(null);
  }

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const payload = {
        profil_id: jeuId,
        nom: edition.nom,
        champ_cible: edition.champ_cible,
        pattern: edition.pattern,
        fonction: edition.fonction || null,
        // Le paramètre ne part qu'avec la fonction qui l'attend : gardé d'un
        // choix précédent, il n'aurait plus aucun sens (§21.4).
        parametre: fonctionChoisie?.parametre ? (edition.parametre || "").trim() || null : null,
        type_champ: edition.type_champ,
        priorite: Number(edition.priorite) || 100,
        actif: !!edition.actif,
      };
      if (edition.id) await adminApi.modifierRegle(edition.id, payload);
      else await adminApi.creerRegle(payload);
      setEdition(null);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function supprimer() {
    await adminApi.supprimerRegle(suppression.id).catch((e) => setErreur(e.message));
    charger();
    setSuppression(null);
  }

  return (
    <div>
      <RoleEcran courant="regles" onMontage={onMontage} />
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16, lineHeight: 1.5 }}>
        Les règles appartiennent à un <strong>jeu</strong>, et un jeu à un{" "}
        <strong>type de document</strong>. Un jeu porte une expression de reconnaissance
        — « cette facture vient d'Orange » — cherchée dans le texte : parmi les jeux du
        type, par priorité croissante, <strong>le premier reconnu l'emporte et est seul
        appliqué</strong>. Aucun ne l'est : le jeu générique du type.
        <br />
        <span style={{ color: "var(--ink-faint)" }}>
          Il s'agit ici de ce qu'on <strong>lit</strong> dans les documents. Ce qu'un type
          <strong> exige</strong> se règle dans « Champs attendus ».
        </span>
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", marginBottom: 14,
                    flexWrap: "wrap" }}>
        <div style={{ width: 260 }}>
          <label style={{ fontSize: 12, color: "var(--ink-faint)", display: "block",
                          marginBottom: 4 }}>
            Type de document
          </label>
          {/* Par ordre alphabétique, à plat (§19.21). L'arborescence sert à
              ranger les documents ; ici on cherche un type qu'on sait nommer, et
              on ne se rappelle pas toujours dans quel dossier il vit. Le dossier
              reste écrit à côté, pour les homonymes. */}
          <Liste
            valeur={categorieId ?? ""}
            ariaLabel={t("Type de document")}
            options={typesTries.map((c) => ({
              valeur: c.id,
              libelle: c.dossier ? `${c.nom} · ${c.dossier}` : c.nom,
            }))}
            onChange={(v) => { setCategorieId(Number(v)); setJeuId(null); }}
          />
        </div>
        <div style={{ width: 280 }}>
          <label style={{ fontSize: 12, color: "var(--ink-faint)", display: "block",
                          marginBottom: 4 }}>
            Jeu de règles
          </label>
          <Liste
            valeur={jeuId ?? ""}
            ariaLabel={t("Jeu de règles")}
            placeholder={t("— Aucun jeu —")}
            options={jeuxTries.map((j) => ({
              valeur: j.id,
              libelle: `${j.priorite} · ${j.nom}${j.generique ? t(" · générique") : ""}`
                     + ` (${j.nb_regles})`,
            }))}
            onChange={(v) => setJeuId(Number(v))}
          />
        </div>
        <button
          onClick={() => setEditionJeu({ ...JEU_VIDE, priorite: (jeux.length + 1) * 10 })}
          style={{
            display: "flex", alignItems: "center", gap: 6, background: "var(--bg-panel)",
            border: "1px solid var(--line-strong)", color: "var(--ink-soft)",
            borderRadius: "var(--radius)", padding: "7px 12px", fontSize: 12.5,
          }}
        >
          <Plus size={13} />
          Nouveau jeu
        </button>
        {jeuCourant && (
          <>
            <button
              onClick={() => setEditionJeu({ ...jeuCourant })}
              style={{
                display: "flex", alignItems: "center", gap: 6, background: "transparent",
                border: "1px solid var(--line-strong)", color: "var(--ink-soft)",
                borderRadius: "var(--radius)", padding: "7px 12px", fontSize: 12.5,
              }}
            >
              <Pencil size={13} />
              Modifier le jeu
            </button>
            <button
              onClick={() => setSuppressionJeu(jeuCourant)}
              style={{
                display: "flex", alignItems: "center", gap: 6, background: "transparent",
                border: "1px solid var(--brick)", color: "var(--brick)",
                borderRadius: "var(--radius)", padding: "7px 12px", fontSize: 12.5,
              }}
            >
              <Trash2 size={13} />
              Supprimer le jeu
            </button>
          </>
        )}
      </div>

      {jeuCourant && (
        <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 12,
                      padding: "8px 11px", background: "var(--bg-panel-alt)",
                      borderRadius: "var(--radius)", lineHeight: 1.5 }}>
          {jeuCourant.generique ? (
            <>Jeu <strong>générique</strong> : il s'applique quand aucun autre jeu de ce
            type n'a été reconnu.</>
          ) : (
            <>Reconnu quand le texte correspond à{" "}
            <code style={{ fontFamily: "var(--font-mono)" }}>
              {jeuCourant.reconnaissance}
            </code>{" "}
            (priorité {jeuCourant.priorite}).</>
          )}
          {!jeuCourant.actif && (
            <strong style={{ color: "var(--amber)" }}> {t("Ce jeu est désactivé.")}</strong>
          )}
        </div>
      )}

      {/* Les deux façons d'écrire une règle côte à côte (§22.36) : à la main,
          ou en la montrant sur un document. La bêta reste à gauche — c'est le
          chemin de traverse, pas la porte principale. */}
      <AdminTable
        libelleAjout={t("Nouvelle règle")}
        actions={jeuId ? (
          <button
            onClick={() => setApprentissage(true)}
            title={t("Ouvrir un document et y désigner la valeur à extraire")}
            style={{ display: "inline-flex", alignItems: "center", gap: 6,
                     border: "1px solid var(--line-strong)", background: "transparent",
                     color: "var(--ink-soft)", borderRadius: "var(--radius)",
                     padding: "6px 12px", fontSize: 12.5, cursor: "pointer" }}
          >
            <Wand2 size={13} />
            Apprendre depuis un document
            <span style={{ fontSize: 10.5, color: "var(--amber)", fontWeight: 600 }}>{t("BÊTA")}</span>
          </button>
        ) : null}
        onAjouter={jeuId ? () => setEdition({ ...VIDE }) : undefined}
        onModifier={(r) => setEdition(r)}
        onSupprimer={setSuppression}
        colonnes={[
          {
            key: "id",
            label: "Nº",
            // Une référence courte pour se citer une règle — « la R-0042 ne
            // trouve plus rien » — sans avoir à la décrire (§22.20).
            render: (r) => (
              <code style={{ fontFamily: "var(--font-mono)", fontSize: 11.5,
                             color: "var(--ink-faint)" }}>
                {referenceRegle(r.id)}
              </code>
            ),
          },
          { key: "nom", label: "Nom" },
          { key: "champ_cible", label: t("Colonne cible") },
          {
            key: "pattern",
            label: "Regex",
            render: (r) => (
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                  {r.pattern || <span style={{ color: "var(--ink-faint)" }}>—</span>}
                </code>
                {r.fonction && (
                  <span title={t("Fonction prête à l'emploi")} style={{
                    fontSize: 10.5, color: "var(--accent)", border: "1px solid var(--accent)",
                    borderRadius: 8, padding: "0 6px", whiteSpace: "nowrap",
                  }}>
                    {r.fonction.replace(/_/g, " ")}
                  </span>
                )}
              </span>
            ),
          },
          { key: "type_champ", label: "Type" },
          {
            key: "actif",
            label: "Statut",
            render: (r) => (r.actif ? "Active" : t("Désactivée")),
          },
        ]}
        lignes={regles}
      />

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {!jeuId && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 10 }}>
          {t("Ce type n'a aucun jeu de règles : rien n'est extrait de ses documents. Créez-en un — générique, pour commencer.")}
        </div>
      )}

      {suppressionJeu && (
        <ConfirmerSuppression
          typeObjet={"jeu_extraction"}
          identifiant={suppressionJeu.id}
          intitule={`le jeu « ${suppressionJeu.nom} »`}
          consequences={[{
            nature: "suppression",
            libelle: `${suppressionJeu.nb_regles} règle(s) de ce jeu`,
            precision: t("elles n'existent que par lui : rien ne les appliquerait plus"),
          }]}
          onAnnuler={() => setSuppressionJeu(null)}
          onConfirmer={supprimerJeu}
        />
      )}

      {apprentissage && (
        <ApprentissageRegle
          categorieId={categorieId}
          categorieNom={categories.find((c) => c.id === categorieId)?.nom}
          onFermer={() => setApprentissage(false)}
          onUtiliser={(proposition) => {
            // La proposition **remplit** le formulaire, elle ne l'enregistre pas :
            // on la relit, on nomme la règle, on choisit son champ. Enregistrer
            // à la place de quelqu'un serait reprendre d'une main ce que la bêta
            // donne de l'autre.
            setApprentissage(false);
            setEdition({
              ...VIDE,
              nom: `Depuis « ${proposition.ancre || proposition.forme} »`,
              champ_cible: proposition.champ_cible || "",
              pattern: proposition.pattern,
              fonction: proposition.fonction || "",
              type_champ: proposition.type_champ || "texte",
            });
          }}
        />
      )}

      {editionJeu && (
        <Modal
          titre={editionJeu.id ? t("Modifier le jeu de règles") : t("Nouveau jeu de règles")}
          onClose={() => setEditionJeu(null)}
        >
          <form onSubmit={enregistrerJeu}>
            <label style={{ ...champStyle, marginTop: 0 }}>{t("Nom du jeu")}</label>
            <input required autoFocus value={editionJeu.nom}
                   onChange={(e) => setEditionJeu({ ...editionJeu, nom: e.target.value })}
                   placeholder="ex : Facture Orange" style={inputStyle} />

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={!!editionJeu.generique}
                     onChange={(e) => setEditionJeu({ ...editionJeu, generique: e.target.checked })} />
              {t("Jeu générique de ce type")}
            </label>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.45 }}>
              {t("Celui qui s'applique quand aucun autre n'est reconnu. Il ne peut y en avoir qu'un par type — sinon on ne saurait pas lequel sert de repli.")}
            </div>

            {!editionJeu.generique && (
              <>
                <label style={champStyle}>{t("Expression de reconnaissance")}</label>
                <input
                  value={editionJeu.reconnaissance || ""}
                  onChange={(e) => setEditionJeu({ ...editionJeu, reconnaissance: e.target.value })}
                  placeholder="ex : (?i)\bORANGE\b"
                  style={{ ...inputStyle, fontFamily: "var(--font-mono)" }}
                />
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4,
                              lineHeight: 1.45 }}>
                  {t("Cherchée dans le texte du document. Sans elle, ce jeu ne serait jamais choisi.")}
                </div>
              </>
            )}

            {/* Plus d'« émetteur posé par ce jeu » (§21.12) : c'est la déduction
                du champ attendu qui s'en charge, et elle lit le document au lieu
                de faire confiance au jeu reconnu. */}

            <label style={champStyle}>{t("Priorité (plus petit = essayé en premier)")}</label>
            <input type="number" value={editionJeu.priorite}
                   onChange={(e) => setEditionJeu({ ...editionJeu, priorite: e.target.value })}
                   style={inputStyle} />

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={!!editionJeu.actif}
                     onChange={(e) => setEditionJeu({ ...editionJeu, actif: e.target.checked })} />
              Jeu actif
            </label>

            <button type="submit" style={boutonPrimaire}>Enregistrer</button>
          </form>
        </Modal>
      )}

      {suppression && (
        <ConfirmerSuppression
          typeObjet={"regle_extraction"}
          identifiant={suppression.id}
          intitule={`la règle « ${suppression.nom} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimer}
        />
      )}

      {edition && (
        <Modal titre={edition.id ? t("Modifier la règle") : t("Nouvelle règle d'extraction")} onClose={() => setEdition(null)}>
          <form onSubmit={enregistrer}>
            <label style={champStyle}>{t("Nom de la règle")}</label>
            <input required value={edition.nom} onChange={(e) => setEdition({ ...edition, nom: e.target.value })} style={inputStyle} />

            <label style={champStyle}>{t("Colonne cible")}</label>
            {/* Une liste de suggestions, pas une liste fermée : le champ reste
                libre — un nouveau nom s'écrit toujours — mais on ne le tape plus
                à l'aveugle (§21.11). Les propositions viennent de ce que le foyer
                a déjà nommé pour ce type. */}
            <SaisieSuggeree
              required
              ariaLabel={t("Colonne cible")}
              valeur={edition.champ_cible}
              placeholder="montant_ttc, date_document…"
              onChange={(v) => setEdition({ ...edition, champ_cible: v })}
              suggestions={cibles.map((c) => ({ valeur: c.champ, aide: c.origine }))}
              style={{ ...inputStyle, fontFamily: "var(--font-mono)", width: "100%" }}
            />
            {edition.champ_cible
              && !cibles.some((c) => c.champ === edition.champ_cible) && (
              <div style={{ fontSize: 11, color: "var(--amber)", marginTop: 4,
                            lineHeight: 1.45 }}>
                {t("Ce nom est nouveau pour ce type. C'est permis — mais vérifiez qu'il ne s'agit pas d'une variante d'un champ existant : deux noms voisins font deux colonnes, et l'une restera vide.")}
              </div>
            )}

            {/* La fonction avant l'expression : c'est le raccourci, et il rend
                souvent l'expression inutile. La proposer après reviendrait à
                laisser écrire une regex d'abord, pour découvrir ensuite qu'on
                aurait pu s'en passer. */}
            <label style={champStyle}>{t("Fonction prête à l'emploi")}</label>
            <Liste
              valeur={edition.fonction || ""}
              ariaLabel={t("Fonction d'extraction")}
              placeholder={t("— Aucune —")}
              options={[{ valeur: "", libelle: t("— Aucune (expression seule) —") },
                        ...fonctions.map((f) => ({ valeur: f.cle, libelle: f.libelle }))]}
              onChange={(v) => {
                const choisie = fonctions.find((f) => f.cle === v);
                setEdition({
                  ...edition,
                  fonction: v,
                  // le type conseillé évite une date rangée comme du texte, faute
                  // d'avoir pensé à changer la liste d'à côté
                  type_champ: choisie?.type_conseille || edition.type_champ,
                });
              }}
            />
            {fonctionChoisie && (
              <div style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5, marginTop: 5 }}>
                {t(fonctionChoisie.description)}
              </div>
            )}

            {/* Certaines fonctions demandent une valeur pour travailler — les
                jours d'une échéance, le séparateur d'une concaténation. Le champ
                n'apparaît que pour celles-là : ailleurs, personne ne saurait
                quoi y écrire (§21.4). */}
            {fonctionChoisie?.parametre && (
              <>
                <label style={champStyle}>{t(fonctionChoisie.parametre.libelle)}</label>
                <input
                  required
                  value={edition.parametre || ""}
                  placeholder={`exemple : ${fonctionChoisie.parametre.exemple}`}
                  onChange={(e) => setEdition({ ...edition, parametre: e.target.value })}
                  style={inputStyle}
                />
              </>
            )}

            <label style={champStyle}>
              Expression régulière (avec un groupe capturant)
              {fonctionChoisie?.extracteur && (
                <span style={{ color: "var(--ink-faint)", fontWeight: 400 }}>
                  {" "}· facultative : la fonction cherche d'elle-même
                </span>
              )}
            </label>
            <input
              required={!fonctionChoisie?.extracteur}
              value={edition.pattern || ""}
              placeholder={fonctionChoisie?.extracteur
                ? t("laissez vide pour chercher dans tout le document")
                : undefined}
              onChange={(e) => setEdition({ ...edition, pattern: e.target.value })}
              style={{ ...inputStyle, fontFamily: "var(--font-mono)" }}
            />
            {/* Les drapeaux, en clair (§22.30). Ils changent la façon dont
                **tout** le motif est lu, ne s'écrivent qu'en tête, et se
                retenaient mal : `(?im)` en début d'expression n'apprend rien à
                qui ne le connaît pas déjà. La description s'affiche au survol du
                choix, là où la question se pose. */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6,
                          flexWrap: "wrap" }}>
              <span style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
                {t("Comment lire le motif")}
              </span>
              <div style={{ width: 300 }}>
                <Liste
                  compact
                  valeur={drapeauxDe(edition.pattern || "")}
                  ariaLabel={t("Drapeaux de l'expression régulière")}
                  options={DRAPEAUX()}
                  onChange={(v) => setEdition({
                    ...edition, pattern: avecDrapeaux(edition.pattern || "", v),
                  })}
                />
              </div>
              <span style={{ fontSize: 11, color: "var(--ink-faint)" }}>
                {DRAPEAUX().find((d) => d.valeur === drapeauxDe(edition.pattern || ""))?.aide}
              </span>
            </div>

            {fonctionChoisie && !fonctionChoisie.extracteur && (
              <div style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5, marginTop: 5 }}>
                {t("L'expression délimite la zone, la fonction en tire la valeur.")}
              </div>
            )}

            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <label style={champStyle}>Type</label>
                <Liste
                  valeur={edition.type_champ}
                  ariaLabel={t("Type du champ extrait")}
                  options={[
                    { valeur: "texte", libelle: "Texte" },
                    { valeur: "date", libelle: "Date" },
                    { valeur: "montant", libelle: "Montant" },
                    { valeur: "entier", libelle: "Entier" },
                  ]}
                  onChange={(v) => setEdition({ ...edition, type_champ: v })}
                />
              </div>
              <div style={{ width: 100 }}>
                <label style={champStyle}>{t("Priorité")}</label>
                <input type="number" value={edition.priorite} onChange={(e) => setEdition({ ...edition, priorite: e.target.value })} style={inputStyle} />
              </div>
            </div>

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={!!edition.actif}
                onChange={(e) => setEdition({ ...edition, actif: e.target.checked })}
              />
              Règle active
            </label>

            <button type="submit" style={boutonPrimaire}>Enregistrer</button>
          </form>
        </Modal>
      )}
    </div>
  );
}
