import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { adminApi, api } from "../../api";
import Liste from "../../components/champs/Liste.jsx";
import AdminTable from "../../components/AdminTable.jsx";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import { deplacer } from "../../components/Reordonnable.jsx";
import EditeurCriteres from "../../components/EditeurCriteres.jsx";
import { decrireCritereEnTexte } from "../../lib/criteres";
import { aplatirArborescence } from "../../lib/arborescence";
import { t } from "../../lib/langue";

/**
 * Gestion des vues enregistrées : renommage, rattachement, partage et ordre
 * d'affichage dans la navigation.
 *
 * Les critères eux-mêmes ne se modifient pas ici : ils se règlent au plus près
 * de l'usage, en filtrant le registre puis en ré-enregistrant la vue. Cet écran
 * n'agit que sur ce qui relève de l'organisation.
 */
export default function VuesAdmin() {
  const [vues, setVues] = useState([]);
  const [categories, setCategories] = useState([]);
  const [edition, setEdition] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [suppression, setSuppression] = useState(null);
  const [enCours, setEnCours] = useState(false);
  // Le vocabulaire des filtres vient du moteur qui les applique (§19.8) : une
  // liste tenue ici finirait par accepter ce que l'API refuse.
  const [champs, setChamps] = useState([]);
  // Les colonnes réglées pour chaque type (§19.18) : ce sont elles qu'on propose
  // en critères, plutôt que toutes les métadonnées connues du foyer.
  const [colonnesParType, setColonnesParType] = useState({});

  function charger() {
    api.vues().then(setVues).catch((e) => setErreur(e.message));
    api.categories().then(setCategories).catch(() => {});
    adminApi.champsDisponibles().then(setChamps).catch(() => {});
    api.colonnesCategories()
      .then((reponse) => setColonnesParType(reponse.colonnes || {}))
      .catch(() => {});
  }
  useEffect(charger, []);

  const nomCategorie = (id) => categories.find((c) => c.id === id)?.nom;

  const majLien = (rang, modifications) => setEdition((courant) => ({
    ...courant,
    liens: (courant.liens || []).map((l, i) => (i === rang ? { ...l, ...modifications } : l)),
  }));
  const ajouterLien = () => setEdition((courant) => ({
    ...courant,
    liens: [...(courant.liens || []),
            { vue_id: null, champ_source: "", champ_cible: "", libelle: "" }],
  }));
  const retirerLien = (rang) => setEdition((courant) => ({
    ...courant,
    liens: (courant.liens || []).filter((_, i) => i !== rang),
  }));

  /** Charge utile complète attendue par PUT /vues/{id} (les critères sont conservés). */
  const charge = (vue, modifications = {}) => ({
    nom: vue.nom,
    categorie_id: vue.categorie_id,
    criteres: vue.criteres,
    partagee: vue.partagee,
    groupement: vue.groupement || [],
    liens: vue.liens || [],
    ordre: vue.ordre,
    ...modifications,
  });

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      // Une vue se créait uniquement depuis le registre, en filtrant puis en
      // enregistrant. C'est le geste le plus naturel, mais il oblige à
      // reconstituer une recherche pour ajouter une vue qu'on a déjà en tête :
      // on peut désormais partir d'une vue vide et poser ses critères ici.
      if (edition.id) await api.modifierVue(edition.id, charge(edition));
      else await api.creerVue(charge(edition));
      setEdition(null);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function supprimer() {
    try {
      await api.supprimerVue(suppression.id);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
    setSuppression(null);
  }

  /**
   * Déplace une vue dans son groupe de rattachement, à la place où elle a été
   * lâchée. Les positions sont réécrites en 10, 20, 30... pour rester lisibles
   * et éviter les ex æquo, et seules les vues dont la position change sont
   * réenregistrées.
   */
  async function deplacerLigne(de, vers) {
    const depart = lignes[de];
    const arrivee = lignes[vers];
    const groupe = lignes.filter((v) => v.categorie_id === depart.categorie_id);
    const reordonne = deplacer(
      groupe,
      groupe.findIndex((v) => v.id === depart.id),
      groupe.findIndex((v) => v.id === arrivee.id)
    );

    setEnCours(true);
    setErreur(null);
    try {
      for (const [position, v] of reordonne.entries()) {
        const nouvelOrdre = (position + 1) * 10;
        if (v.ordre !== nouvelOrdre) await api.modifierVue(v.id, charge(v, { ordre: nouvelOrdre }));
      }
      charger();
    } catch (err) {
      setErreur(err.message);
    } finally {
      setEnCours(false);
    }
  }

  /**
   * Les champs proposés en critères, groupés (§19.18).
   *
   * Toutes les métadonnées du foyer y figuraient, y compris celles qui n'ont
   * aucun sens pour la vue qu'on écrit : chercher un numéro de facture dans une
   * vue de courriers ne ramènera jamais rien. On propose donc **les colonnes du
   * type auquel la vue est rattachée** — celles que l'administrateur a réglées,
   * c'est-à-dire ce qu'un document de cette sorte porte réellement.
   *
   * Trois champs restent toujours là : le texte du document, la catégorie et la
   * date d'import valent pour n'importe quel document, quelle que soit sa sorte.
   *
   * Sans rattachement, la vue est générale : on propose tout, puisqu'on ne sait
   * pas sur quoi elle portera.
   */
  const GENERAUX = ["texte", "categorie", "date_import"];

  /** `categorie` est-elle rangée sous `ancetreId` ? */
  function descendDe(categorie, ancetreId, toutes) {
    const parents = new Map(toutes.map((c) => [c.id, c]));
    let courante = categorie;
    for (let saut = 0; courante?.parent_id && saut < 20; saut += 1) {
      if (courante.parent_id === ancetreId) return true;
      courante = parents.get(courante.parent_id);
    }
    return false;
  }

  function champsProposes(categorieId, criteresEcrits = []) {
    const parNom = new Map(champs.map((c) => [c.champ, c]));
    const generaux = GENERAUX
      .map((nom) => parNom.get(nom))
      .filter(Boolean)
      .map((c) => ({ ...c, groupe: t("Toujours disponibles") }));

    if (!categorieId) {
      return [...generaux, ...champs
        .filter((c) => !GENERAUX.includes(c.champ))
        .map((c) => ({ ...c, groupe: t("Tous les champs") }))];
    }

    // Un dossier rassemble plusieurs types : ses colonnes sont leur réunion.
    const concernees = aplatirArborescence(categories)
      .filter((c) => c.id === categorieId || descendDe(c, categorieId, categories))
      .flatMap((c) => colonnesParType[String(c.id)] || []);

    const vus = new Set(GENERAUX);
    const propres = [];
    for (const colonne of concernees) {
      if (vus.has(colonne.champ)) continue;
      vus.add(colonne.champ);
      const connu = parNom.get(colonne.champ);
      if (!connu) continue;      // une colonne que le moteur ne sait pas filtrer
      propres.push({ ...connu, libelle: colonne.libelle || connu.libelle,
                     groupe: t("Colonnes de ce classement") });
    }
    // Un critère déjà écrit garde son champ dans la liste, même si le
    // rattachement de la vue ne le propose plus : le retirer le ferait
    // disparaître sous les doigts, avec les opérateurs qui vont avec.
    const dejaUtilises = criteresEcrits
      .map((critere) => critere.champ)
      .filter((nom) => !vus.has(nom))
      .map((nom) => parNom.get(nom))
      .filter(Boolean)
      .map((c) => ({ ...c, groupe: t("Déjà dans cette vue") }));

    return [...generaux, ...propres, ...dejaUtilises];
  }

  const lignes = [...vues].sort(
    (a, b) =>
      (nomCategorie(a.categorie_id) || "").localeCompare(nomCategorie(b.categorie_id) || "") ||
      a.ordre - b.ordre ||
      a.nom.localeCompare(b.nom)
  );

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        Une vue mémorise un jeu de critères de recherche réutilisable. Elle se crée depuis
        le registre, en filtrant les colonnes puis en cliquant « Enregistrer la vue » ;
        cet écran permet de tout y reprendre — <strong>ses critères compris</strong>.
        Corriger une vue partagée ne demande plus de reconstituer, dans le registre, une
        recherche qu'on n'a pas forcément faite soi-même. L'ordre d'affichage se règle en
        faisant glisser la poignée de gauche, à l'intérieur du groupe de rattachement.
      </p>

      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
        <button
          onClick={() => setEdition({
            nom: "", categorie_id: null, criteres: [], partagee: true,
            groupement: [], liens: [], ordre: 100,
          })}
          style={boutonPrimaire}
        >
          <Plus size={13} /> Nouvelle vue
        </button>
      </div>

      <AdminTable
        lignes={lignes}
        reordonnable={{
          onDeplacer: enCours ? () => {} : deplacerLigne,
          groupeDe: (index) => lignes[index]?.categorie_id ?? null,
          libelleDe: (v) => `la vue « ${v.nom} »`,
        }}
        onModifier={(v) => setEdition({ ...v })}
        onSupprimer={setSuppression}
        colonnes={[
          { key: "nom", label: "Vue" },
          {
            key: "categorie_id",
            label: t("Rattachée à"),
            render: (v) => nomCategorie(v.categorie_id) || <Discret>{t("Vue générale")}</Discret>,
          },
          {
            key: "criteres",
            label: t("Critères"),
            render: (v) => (
              v.criteres.length === 0
                ? <Discret>{t("Tous les documents")}</Discret>
                : (
                  <span
                    style={{ fontSize: 12 }}
                    title={v.criteres
                      .map((c) => decrireCritereEnTexte(c, { categories }))
                      .join(" · ")}
                  >
                    {decrireCritereEnTexte(v.criteres[0], { categories })}
                    {v.criteres.length > 1 && (
                      <Discret> +{v.criteres.length - 1}</Discret>
                    )}
                  </span>
                )
            ),
          },
          {
            key: "partagee",
            label: "Partage",
            render: (v) => (v.partagee ? t("Partagée") : <Discret>{t("Privée")}</Discret>),
          },
          {
            key: "proprietaire",
            label: "Auteur",
            render: (v) => v.proprietaire || <Discret>{t("Système")}</Discret>,
          },
        ]}
      />

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {suppression && (
        <ConfirmerSuppression
          typeObjet={"vue"}
          identifiant={suppression.id}
          intitule={`la vue « ${suppression.nom} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimer}
        />
      )}

      {/* Plus large que la modale ordinaire : l'éditeur de critères y tient trois
          contrôles côte à côte, et 460 px les serraient l'un contre l'autre. */}
      {edition && (
        <Modal titre={edition.id ? t("Modifier la vue") : t("Nouvelle vue")} width={506}
               onClose={() => setEdition(null)}>
          <form onSubmit={enregistrer}>
            <label style={champStyle}>Nom</label>
            <input
              required
              autoFocus
              value={edition.nom}
              onChange={(e) => setEdition({ ...edition, nom: e.target.value })}
              style={inputStyle}
            />

            <label style={champStyle}>{t("Rattacher à")}</label>
            <Liste
              valeur={edition.categorie_id ?? ""}
              ariaLabel={t("Catégorie de rattachement")}
              options={[
                { valeur: "", libelle: t("Aucune catégorie (vue générale)") },
                ...aplatirArborescence(categories).map((c) => ({
                  valeur: c.id,
                  libelle: `${"\u00a0".repeat(c.profondeur * 3)}${c.nom}`,
                })),
              ]}
              onChange={(v) => setEdition({ ...edition, categorie_id: v === "" ? null : Number(v) })}
            />

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={edition.partagee}
                onChange={(e) => setEdition({ ...edition, partagee: e.target.checked })}
              />
              {t("Partagée avec les autres comptes")}
            </label>

            <label style={champStyle}>{t("Critères")}</label>
            <EditeurCriteres
              criteres={edition.criteres || []}
              champs={champsProposes(edition.categorie_id, edition.criteres || [])}
              categories={categories}
              onChange={(criteres) => setEdition({ ...edition, criteres })}
            />

            {/* Le repli en arborescence (§21.6). Déclaré ici, il ouvre la vue
                déjà repliée ; celui qui lit peut en changer, c'est sa façon de
                parcourir, pas une propriété du classement. */}
            <label style={champStyle}>{t("Replier par")}</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[0, 1].map((niveau) => {
                const choisis = edition.groupement || [];
                const proposes = champsProposes(edition.categorie_id, []);
                return (
                  <div key={niveau} style={{ width: 210 }}>
                    <Liste
                      valeur={choisis[niveau] || ""}
                      ariaLabel={`Niveau ${niveau + 1} du repli`}
                      options={[{ valeur: "", libelle: niveau === 0
                        ? t("— aucun (tableau à plat) —") : t("— pas de second niveau —") },
                        ...proposes
                          .filter((c) => c.champ !== "texte" && c.champ !== "nom_fichier")
                          .map((c) => ({ valeur: c.champ, libelle: c.libelle }))]}
                      onChange={(v) => {
                        const suivant = [...choisis];
                        suivant[niveau] = v;
                        // Un second niveau sans premier n'aurait pas de sens :
                        // on compacte plutôt que de garder un trou.
                        setEdition({ ...edition,
                                     groupement: suivant.filter(Boolean) });
                      }}
                    />
                  </div>
                );
              })}
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 5,
                          lineHeight: 1.45 }}>
              {t("La vue s'ouvre alors sur des branches — « 2026 », puis « EDF » — plutôt que sur trois cents lignes. Les dates se replient par année.")}
            </div>

            {/* Le lien déclaré sur la vue (§22.5) : la correspondance de champs
                d'EzGED. Ce n'est ni un rapprochement par valeur partagée — celui-là
                se voit sans qu'on le déclare — ni un rattachement entre deux
                documents : c'est un **chemin**, valable pour toutes les lignes. */}
            <label style={champStyle}>{t("Depuis cette vue, on continue vers")}</label>
            {(edition.liens || []).map((lien, rang) => (
              <div key={rang} style={{ display: "flex", gap: 6, alignItems: "center",
                                       marginBottom: 6, flexWrap: "wrap" }}>
                <div style={{ width: 190 }}>
                  <Liste
                    valeur={String(lien.vue_id || "")}
                    ariaLabel={`Vue d'arrivée du lien ${rang + 1}`}
                    options={[{ valeur: "", libelle: t("— choisir une vue —") },
                      ...vues.filter((v) => v.id !== edition.id)
                        .map((v) => ({ valeur: String(v.id), libelle: v.nom }))]}
                    onChange={(v) => majLien(rang, { vue_id: Number(v) || null })}
                  />
                </div>
                <div style={{ width: 170 }}>
                  <Liste
                    valeur={lien.champ_source || ""}
                    ariaLabel={`Champ lu au départ, lien ${rang + 1}`}
                    options={[{ valeur: "", libelle: "— champ lu ici —" },
                      ...champsProposes(edition.categorie_id, [])
                        .map((c) => ({ valeur: c.champ, libelle: c.libelle }))]}
                    onChange={(v) => majLien(rang, { champ_source: v })}
                  />
                </div>
                <div style={{ width: 170 }}>
                  <Liste
                    valeur={lien.champ_cible || ""}
                    ariaLabel={`Champ filtré à l'arrivée, lien ${rang + 1}`}
                    options={[{ valeur: "", libelle: t("— champ filtré là-bas —") },
                      ...champsProposes(null, [])
                        .map((c) => ({ valeur: c.champ, libelle: c.libelle }))]}
                    onChange={(v) => majLien(rang, { champ_cible: v })}
                  />
                </div>
                <input
                  value={lien.libelle || ""}
                  aria-label={`Intitulé du lien ${rang + 1}`}
                  placeholder={t("Ses factures")}
                  onChange={(e) => majLien(rang, { libelle: e.target.value })}
                  style={{ ...inputStyle, marginTop: 0, width: 150 }}
                />
                <button type="button" onClick={() => retirerLien(rang)}
                        style={{ border: "none", background: "transparent",
                                 color: "var(--ink-faint)", cursor: "pointer" }}>
                  Retirer
                </button>
              </div>
            ))}
            <button type="button" onClick={ajouterLien}
                    style={{ border: "1px dashed var(--line-strong)", background: "transparent",
                             color: "var(--ink-soft)", fontSize: 12, padding: "4px 10px",
                             borderRadius: "var(--radius)", cursor: "pointer" }}>
              Ajouter un lien
            </button>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 5,
                          lineHeight: 1.45 }}>
              {t("En ouvrant une fiche de cette vue, un raccourci proposera l'autre vue filtrée sur la valeur lue ici. Le raccourci ne s'affiche pas quand le champ est vide sur la fiche : il n'ouvrirait qu'une liste vide.")}
            </div>

            <button type="submit" style={boutonPrimaire}>Enregistrer</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

function Discret({ children }) {
  return <span style={{ color: "var(--ink-faint)" }}>{children}</span>;
}
