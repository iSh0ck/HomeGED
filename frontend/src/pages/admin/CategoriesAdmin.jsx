import React, { useEffect, useState } from "react";
import { FolderTree, FileText, FilePlus2, Plus } from "lucide-react";
import { adminApi } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import { deplacer as deplacerDans } from "../../components/Reordonnable.jsx";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import { aplatirArborescence, idsInterdits } from "../../lib/arborescence";
import Liste from "../../components/champs/Liste.jsx";
import { t } from "../../lib/langue";

const VIDE = { nom: "", nature: "type", dossier_depot: "", ordre: 100, parent_id: null };

/**
 * Trois natures, et la distinction porte tout le reste (§19.1, §22.1) : un
 * **dossier** organise et ne contient aucun document ; un **type de document**
 * est une feuille qui porte ses colonnes, ses champs attendus et ses règles, et
 * reçoit les dépôts par son dossier sous `ocr_wait` ; une **fiche simple** porte
 * les mêmes réglages, mais rien n'y entre tout seul — on y glisse le fichier.
 */
const NATURES = () => [
  { valeur: "dossier", libelle: "Dossier", icone: FolderTree,
    aide: t("Organise le classement. Ne contient aucun document en propre, et n'a donc ni colonnes ni champs attendus.") },
  { valeur: "type", libelle: t("Type de document"), icone: FileText,
    aide: t("Porte les documents de cette sorte, et tout ce qui les décrit. C'est une feuille de l'arborescence : il n'accueille pas de sous-catégorie.") },
  { valeur: "fiche", libelle: t("Fiche simple"), icone: FilePlus2,
    aide: t("Comme un type de document, mais sans dossier de dépôt : rien n'y entre tout seul. On y glisse le fichier à la main et l'on remplit ses valeurs. Pour ce qui arrive rarement et qu'aucune règle ne saurait lire : un acte notarié, une carte grise, un contrat signé.") },
];

const estDossier = (categorie) => (categorie?.nature || "type") === "dossier";
const estType = (categorie) => (categorie?.nature || "type") === "type";

export default function CategoriesAdmin() {
  const [categories, setCategories] = useState([]);
  const [edition, setEdition] = useState(null); // null = fermé, {} = création, {...} = édition
  const [erreur, setErreur] = useState(null);
  const [suppression, setSuppression] = useState(null);
  // Ce que l'on autorise à rattacher à la main (§22.4). Tant que rien n'est
  // déclaré, tout est permis : un réglage vide ne doit pas interdire une
  // fonction, sans quoi personne ne comprendrait pourquoi le bouton refuse.
  const [rattachements, setRattachements] = useState({ libre: true, paires: [] });
  const [paire, setPaire] = useState({ a: "", b: "", libelle: "" });
  // Les rapprochements déclarés sur un type (§22.8) : « ce champ relie ce type
  // aux autres ». C'est le numéro de dossier qui rassemble devis, bon de
  // commande et bon de livraison.
  const [liensTypes, setLiensTypes] = useState([]);
  const [champs, setChamps] = useState([]);
  const [lien, setLien] = useState({ depuis: "", vers: "", champ_source: "",
                                     champ_cible: "", libelle: "" });
  function charger() {
    adminApi.categories().then(setCategories).catch((e) => setErreur(e.message));
    adminApi.pairesRattachement().then(setRattachements).catch(() => {});
    adminApi.liensTypes().then(setLiensTypes).catch(() => {});
    adminApi.champsDisponibles().then(setChamps).catch(() => {});
  }
  useEffect(charger, []);

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const payload = {
        nom: edition.nom,
        nature: edition.nature || "type",
        // Vide : l'API le déduit du nom. C'est ce qu'on veut à la création — un
        // nom de dossier n'a pas à être inventé avant d'exister.
        dossier_depot: (edition.dossier_depot || "").trim() || null,
        ordre: Number(edition.ordre) || 100,
        parent_id: edition.parent_id || null,
      };
      if (edition.id) await adminApi.modifierCategorie(edition.id, payload);
      else await adminApi.creerCategorie(payload);
      setEdition(null);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  /**
   * Déplace une catégorie parmi ses sœurs (même parent), à la place où elle a
   * été lâchée. Les rangs sont réécrits en 10, 20, 30... pour rester lisibles
   * et éviter les ex æquo ; seules les catégories dont le rang change sont
   * réenregistrées.
   *
   * On ne déplace pas une catégorie **hors** de son parent en la faisant
   * glisser : cela reviendrait à rebrancher une branche entière de l'arbre par
   * mégarde. Le rattachement se change dans la fiche, où il est écrit.
   */
  async function deplacerLigne(de, vers) {
    const depart = lignes[de];
    const arrivee = lignes[vers];
    const soeurs = lignes.filter(
      (c) => (c.parent_id ?? null) === (depart.parent_id ?? null));
    const reordonne = deplacerDans(
      soeurs,
      soeurs.findIndex((c) => c.id === depart.id),
      soeurs.findIndex((c) => c.id === arrivee.id)
    );

    setErreur(null);
    try {
      for (const [position, c] of reordonne.entries()) {
        const rang = (position + 1) * 10;
        if (c.ordre === rang) continue;
        await adminApi.modifierCategorie(c.id, {
          nom: c.nom, nature: c.nature, dossier_depot: c.dossier_depot,
          ordre: rang, parent_id: c.parent_id,
        });
      }
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function supprimer() {
    await adminApi.supprimerCategorie(suppression.id).catch((e) => setErreur(e.message));
    charger();
    setSuppression(null);
  }

  const lignes = aplatirArborescence(categories);

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        Un <strong>dossier</strong> organise le classement ; un <strong>type de
        document</strong> porte les documents, et son dossier de dépôt sous
        <code> ocr_wait/</code>. C'est l'emplacement du dépôt qui décide du classement :
        un document déposé dans <code>ocr_wait/factures/</code> est une facture, sans
        que rien n'ait à le deviner. L'ordre d'affichage se règle en faisant glisser la
        poignée de gauche, entre catégories de même parent.
      </p>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginBottom: 12 }}>
        {NATURES().map((n) => {
          const Icone = n.icone;
          return (
            <button
              key={n.valeur}
              onClick={() => setEdition({
                ...VIDE, nature: n.valeur, ordre: (categories.length + 1) * 10,
              })}
              title={t(n.aide)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: n.valeur === "type" ? "var(--accent)" : "var(--bg-panel)",
                color: n.valeur === "type" ? "#fff" : "var(--ink-soft)",
                border: n.valeur === "type" ? "none" : "1px solid var(--line-strong)",
                whiteSpace: "nowrap",
                borderRadius: "var(--radius)", padding: "7px 12px", fontSize: 13, fontWeight: 500,
              }}
            >
              <Plus size={14} />
              <Icone size={14} />
              {t(n.libelle)}
            </button>
          );
        })}
      </div>

      <AdminTable
        onModifier={(c) => setEdition(c)}
        onSupprimer={setSuppression}
        colonnes={[
          {
            key: "nom",
            label: "Nom",
            render: (c) => (
              <span style={{ paddingLeft: c.profondeur * 18 }}>
                {c.profondeur > 0 && (
                  <span style={{ color: "var(--ink-faint)", marginRight: 6 }}>└</span>
                )}
                {c.nom}
              </span>
            ),
          },
          {
            key: "nature",
            label: "Nature",
            render: (c) => {
              const nature = NATURES().find((n) => n.valeur === (c.nature || "type"));
              const Icone = nature.icone;
              return (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5,
                               fontSize: 12, color: "var(--ink-soft)" }}
                      title={t(nature.aide)}>
                  <Icone size={13} />
                  {t(nature.libelle)}
                </span>
              );
            },
          },
          {
            key: "dossier_depot",
            label: t("Dossier de dépôt"),
            // Une fiche simple n'en a pas, et c'est ce qui la définit : le tiret
            // n'est pas un réglage qui manque, c'est la réponse.
            render: (c) => (!estType(c) ? (
              <span style={{ color: "var(--ink-faint)", fontSize: 12 }}
                    title={c.nature === "fiche"
                      ? t("Rien n'entre tout seul dans une fiche : on y glisse le fichier")
                      : t("Un dossier ne reçoit aucun document")}>—</span>
            ) : (
              <code style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}
                    title={`Déposez les documents de ce type dans ocr_wait/${c.dossier_depot || ""}`}>
                {c.dossier_depot || "—"}
              </code>
            )),
          },
        ]}
        lignes={lignes}
        reordonnable={{
          onDeplacer: deplacerLigne,
          groupeDe: (index) => lignes[index]?.parent_id ?? null,
          libelleDe: (c) => `la catégorie « ${c.nom} »`,
        }}
      />

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      <SectionLiensTypes
        liens={liensTypes}
        categories={categories}
        champs={champs}
        lien={lien}
        onLien={setLien}
        onDeclarer={async () => {
          setErreur(null);
          try {
            await adminApi.declarerLienType({
              categorie_id: Number(lien.depuis),
              categorie_cible_id: lien.vers ? Number(lien.vers) : null,
              champ_source: lien.champ_source,
              champ_cible: lien.champ_cible || lien.champ_source,
              libelle: lien.libelle || null,
            });
            setLien({ depuis: "", vers: "", champ_source: "", champ_cible: "", libelle: "" });
            charger();
          } catch (e) { setErreur(e.message); }
        }}
        onRetirer={async (id) => {
          try { await adminApi.retirerLienType(id); charger(); }
          catch (e) { setErreur(e.message); }
        }}
      />

      <SectionRattachements
        etat={rattachements}
        categories={categories}
        paire={paire}
        onPaire={setPaire}
        onDeclarer={async () => {
          setErreur(null);
          try {
            await adminApi.declarerPaireRattachement({
              categorie_a: Number(paire.a), categorie_b: Number(paire.b),
              libelle: paire.libelle || null,
            });
            setPaire({ a: "", b: "", libelle: "" });
            charger();
          } catch (e) { setErreur(e.message); }
        }}
        onRetirer={async (id) => {
          try {
            await adminApi.retirerPaireRattachement(id);
            charger();
          } catch (e) { setErreur(e.message); }
        }}
      />

      {suppression && (
        <ConfirmerSuppression
          typeObjet={"categorie"}
          identifiant={suppression.id}
          intitule={`la catégorie « ${suppression.nom} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimer}
        />
      )}

      {edition && (
        <Modal
          titre={edition.id
            ? `Modifier « ${edition.nom} »`
            : `Nouveau ${NATURES().find((n) => n.valeur === (edition.nature || "type")).libelle.toLowerCase()}`}
          onClose={() => setEdition(null)}
        >
          <form onSubmit={enregistrer}>
            <label style={{ ...champStyle, marginTop: 0 }}>Nature</label>
            <div style={{ display: "flex", gap: 6 }}>
              {NATURES().map((n) => {
                const Icone = n.icone;
                const actif = (edition.nature || "type") === n.valeur;
                return (
                  <button
                    key={n.valeur}
                    type="button"
                    onClick={() => setEdition({ ...edition, nature: n.valeur })}
                    style={{
                      flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
                      gap: 6, padding: "6px 10px", fontSize: 12, borderRadius: "var(--radius)",
                      border: "1px solid " + (actif ? "var(--accent)" : "var(--line)"),
                      background: actif ? "var(--accent-soft)" : "var(--bg-panel)",
                      color: "var(--ink)",
                    }}
                  >
                    <Icone size={13} />
                    {t(n.libelle)}
                  </button>
                );
              })}
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.45 }}>
              {NATURES().find((n) => n.valeur === (edition.nature || "type")).aide}
            </div>

            <label style={champStyle}>Nom</label>
            <input
              required
              value={edition.nom}
              onChange={(e) => setEdition({ ...edition, nom: e.target.value })}
              style={inputStyle}
            />

            {(edition.nature || "type") === "type" && (
              <>
                <label style={champStyle}>{t("Dossier de dépôt")}</label>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 12,
                                 color: "var(--ink-faint)", whiteSpace: "nowrap" }}>
                    ocr_wait/
                  </span>
                  <input
                    value={edition.dossier_depot || ""}
                    onChange={(e) => setEdition({ ...edition, dossier_depot: e.target.value })}
                    placeholder={edition.id ? "" : t("déduit du nom")}
                    style={{ ...inputStyle, fontFamily: "var(--font-mono)", marginTop: 0 }}
                  />
                </div>
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.45 }}>
                  {t("C'est là qu'on dépose les documents de ce type. Le nom est mis en forme automatiquement (sans accent ni majuscule) et doit rester unique ; le renommer déplace ce qui attendait dans l'ancien dossier.")}
                </div>
              </>
            )}

            <label style={champStyle}>{t("Catégorie parente")}</label>
            <Liste
              valeur={edition.parent_id ?? ""}
              ariaLabel={t("Catégorie parente")}
              options={[
                { valeur: "", libelle: t("Aucune (racine)") },
                // Seul un dossier accueille des sous-catégories : un type est une
                // feuille, et le proposer ne mènerait qu'à un refus.
                ...aplatirArborescence(categories)
                  .filter((c) => !idsInterdits(categories, edition.id).has(c.id))
                  .filter((c) => estDossier(c))
                  .map((c) => ({
                    valeur: c.id,
                    libelle: `${"\u00a0".repeat(c.profondeur * 3)}${c.nom}`,
                  })),
              ]}
              onChange={(v) => setEdition({ ...edition, parent_id: v === "" ? null : Number(v) })}
            />



            <button type="submit" style={boutonPrimaire}>Enregistrer</button>
          </form>
        </Modal>
      )}
    </div>
  );
}


/**
 * Ce que l'on autorise à rattacher à la main (§22.4).
 *
 * Le rapprochement par valeur partagée réunit ce qui désigne la même chose, sans
 * réglage. Ceci borne l'autre mécanisme : le lien posé à la main entre deux
 * documents qui ne partagent rien — un contrat et son avenant.
 *
 * Tant que rien n'est déclaré, tout est permis. C'est le seul choix tenable :
 * une liste vide qui interdirait tout laisserait un bouton qui refuse sans que
 * personne comprenne pourquoi.
 */
function SectionRattachements({ etat, categories, paire, onPaire, onDeclarer, onRetirer }) {
  const porteuses = categories.filter((c) => (c.nature || "type") !== "dossier");
  const nom = (id) => categories.find((c) => c.id === id)?.nom || `nº${id}`;

  return (
    <div style={{ marginTop: 28, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
      <h3 style={{ fontSize: 13.5, margin: "0 0 4px" }}>{t("Rattachements autorisés")}</h3>
      <p style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5,
                  maxWidth: 620, marginTop: 0 }}>
        Deux documents qui ne partagent aucune valeur peuvent se répondre quand même —
        un contrat et son avenant. On les relie à la main depuis le registre, en cochant
        les fiches. {etat.libre
          ? t("Tant qu'aucune paire n'est déclarée ici, tout peut se rattacher à tout.")
          : t("Seules les paires déclarées ci-dessous peuvent l'être.")}
      </p>

      {etat.paires.map((p) => (
        <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 8,
                                 fontSize: 12.5, padding: "4px 0" }}>
          <span>{p.nom_a || nom(p.categorie_a)} ↔ {p.nom_b || nom(p.categorie_b)}</span>
          {p.libelle && <span style={{ color: "var(--ink-faint)" }}>· {t(p.libelle)}</span>}
          <button onClick={() => onRetirer(p.id)}
                  style={{ border: "none", background: "transparent",
                           color: "var(--ink-faint)", fontSize: 11.5, cursor: "pointer" }}>
            Retirer
          </button>
        </div>
      ))}

      <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8,
                    flexWrap: "wrap" }}>
        <div style={{ width: 200 }}>
          <Liste
            valeur={paire.a}
            ariaLabel={t("Premier type du rattachement")}
            options={[{ valeur: "", libelle: t("— un type —") },
              ...porteuses.map((c) => ({ valeur: String(c.id), libelle: c.nom }))]}
            onChange={(v) => onPaire({ ...paire, a: v })}
          />
        </div>
        <div style={{ width: 200 }}>
          <Liste
            valeur={paire.b}
            ariaLabel={t("Second type du rattachement")}
            options={[{ valeur: "", libelle: t("— et un autre —") },
              ...porteuses.map((c) => ({ valeur: String(c.id), libelle: c.nom }))]}
            onChange={(v) => onPaire({ ...paire, b: v })}
          />
        </div>
        <input
          value={paire.libelle}
          aria-label={t("Ce que le lien veut dire")}
          placeholder="avenant, litige…"
          onChange={(e) => onPaire({ ...paire, libelle: e.target.value })}
          style={{ ...inputStyle, marginTop: 0, width: 160 }}
        />
        <button
          onClick={onDeclarer}
          disabled={!paire.a || !paire.b}
          style={{ ...boutonPrimaire, opacity: paire.a && paire.b ? 1 : 0.5 }}
        >
          Autoriser
        </button>
      </div>
    </div>
  );
}


/**
 * Les rapprochements déclarés sur un type de document (§22.8).
 *
 * L'exemple qui l'a fait naître : un dossier porte un numéro, repris sur le
 * devis, le bon de commande, le bon de livraison. Ouvrir l'un montre les autres.
 *
 * **Déclaré, jamais deviné** — c'est ce qui distingue ce rapprochement de celui
 * qui a été retiré : on sait toujours pourquoi deux documents se retrouvent côte
 * à côte. Et la déclaration vaut **dans les deux sens** : une seule ligne suffit
 * pour que le dossier montre ses pièces et que chaque pièce montre son dossier.
 */
function SectionLiensTypes({ liens, categories, champs, lien, onLien, onDeclarer,
                            onRetirer }) {
  const porteuses = categories.filter((c) => (c.nature || "type") !== "dossier");
  const optionsChamps = champs
    .filter((c) => c.champ !== "texte")
    .map((c) => ({ valeur: c.champ, libelle: c.libelle }));

  return (
    <div style={{ marginTop: 28, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
      <h3 style={{ fontSize: 13.5, margin: "0 0 4px" }}>{t("Rapprochements par champ")}</h3>
      <p style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5,
                  maxWidth: 640, marginTop: 0 }}>
        {t("Un dossier porte un numéro, repris sur le devis, le bon de commande, le bon de livraison : déclarez ici que ce champ les relie, et ouvrir l'un montrera les autres. La déclaration vaut dans les deux sens, et les vues en héritent — elle appartient au type, pas à l'écran.")}
      </p>

      {liens.map((l) => (
        <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 8,
                                 fontSize: 12.5, padding: "4px 0", flexWrap: "wrap" }}>
          <span>
            {l.categorie} · <code style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
              {l.champ_source}</code>
            {" ↔ "}
            {l.categorie_cible || t("tous les types")} · <code style={{
              fontFamily: "var(--font-mono)", fontSize: 11.5 }}>{l.champ_cible}</code>
          </span>
          {l.libelle && <span style={{ color: "var(--ink-faint)" }}>· {t(l.libelle)}</span>}
          <button onClick={() => onRetirer(l.id)}
                  style={{ border: "none", background: "transparent",
                           color: "var(--ink-faint)", fontSize: 11.5, cursor: "pointer" }}>
            Retirer
          </button>
        </div>
      ))}

      <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8,
                    flexWrap: "wrap" }}>
        <div style={{ width: 180 }}>
          <Liste
            valeur={lien.depuis}
            ariaLabel={t("Type qui déclare le rapprochement")}
            options={[{ valeur: "", libelle: t("— depuis ce type —") },
              ...porteuses.map((c) => ({ valeur: String(c.id), libelle: c.nom }))]}
            onChange={(v) => onLien({ ...lien, depuis: v })}
          />
        </div>
        <div style={{ width: 180 }}>
          <Liste
            valeur={lien.champ_source}
            recherchable
            ariaLabel={t("Champ lu sur ce type")}
            options={[{ valeur: "", libelle: t("— par ce champ —") }, ...optionsChamps]}
            onChange={(v) => onLien({ ...lien, champ_source: v })}
          />
        </div>
        <div style={{ width: 180 }}>
          <Liste
            valeur={lien.vers}
            ariaLabel={t("Type rapproché")}
            options={[{ valeur: "", libelle: t("— vers tous les types —") },
              ...porteuses.map((c) => ({ valeur: String(c.id), libelle: c.nom }))]}
            onChange={(v) => onLien({ ...lien, vers: v })}
          />
        </div>
        <div style={{ width: 180 }}>
          <Liste
            valeur={lien.champ_cible}
            recherchable
            ariaLabel={t("Champ cherché en face")}
            options={[{ valeur: "", libelle: t("— même champ —") }, ...optionsChamps]}
            onChange={(v) => onLien({ ...lien, champ_cible: v })}
          />
        </div>
        <input
          value={lien.libelle}
          aria-label={t("Intitulé du rapprochement")}
          placeholder={t("Pièces du dossier")}
          onChange={(e) => onLien({ ...lien, libelle: e.target.value })}
          style={{ ...inputStyle, marginTop: 0, width: 170 }}
        />
        <button
          onClick={onDeclarer}
          disabled={!lien.depuis || !lien.champ_source}
          style={{ ...boutonPrimaire, opacity: lien.depuis && lien.champ_source ? 1 : 0.5 }}
        >
          Déclarer
        </button>
      </div>
    </div>
  );
}
