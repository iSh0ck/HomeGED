import React, { useEffect, useState } from "react";
import { Plus, Trash2, Pencil } from "lucide-react";
import { adminApi, api } from "../../api";
import ChampDate from "../../components/champs/ChampDate.jsx";
import AdminTable from "../../components/AdminTable.jsx";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import Liste from "../../components/champs/Liste.jsx";
import { useReordonnable, PoigneeOrdre, deplacer } from "../../components/Reordonnable.jsx";
import EditeurCriteres from "../../components/EditeurCriteres.jsx";
import { t } from "../../lib/langue";

const INDICATEUR_VIDE = {
  type: "nombre", titre: "", icone: "Hash", unite: "", largeur: 2,
  champ: "", mesure: "compte", mesure_champ: "", granularite: "mois", limite: 12,
  periode: { champ: "date_document", type: "tout" }, filtres: [],
};

/**
 * Composition des tableaux de bord personnalisés.
 *
 * Un indicateur se décrit ici en quelques choix — que compter, sur quel
 * périmètre, sur quelle période — plutôt que par une formule à écrire. Les
 * listes proposées viennent de l'API : elles suivent les catégories, émetteurs
 * et métadonnées réellement présents, sans rien de codé en dur.
 */
export default function TableauxAdmin() {
  const [tableaux, setTableaux] = useState([]);
  const [options, setOptions] = useState(null);
  const [referentiels, setReferentiels] = useState({ categories: [] });
  const [edition, setEdition] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [suppression, setSuppression] = useState(null);

  function charger() {
    adminApi.tableaux().then(setTableaux).catch((e) => setErreur(e.message));
  }
  useEffect(() => {
    charger();
    api.optionsIndicateurs().then(setOptions).catch(() => {});
    api.categories()
      .then((categories) => setReferentiels({ categories }))
      .catch(() => {});
  }, []);

  /**
   * Déplace un tableau de bord dans la liste, à la place où il a été lâché.
   * Les rangs sont réécrits en 10, 20, 30... ; seuls les tableaux dont le rang
   * change sont réenregistrés.
   */
  async function deplacerLigne(de, vers) {
    const reordonne = deplacer(tableaux, de, vers);
    setErreur(null);
    try {
      for (const [position, tableau] of reordonne.entries()) {
        const rang = (position + 1) * 10;
        if (tableau.ordre === rang) continue;
        await adminApi.modifierTableau(tableau.id, {
          nom: tableau.nom, description: tableau.description || null, widgets: tableau.widgets,
          partage: !!tableau.partage, ordre: rang,
        });
      }
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const charge = {
        nom: edition.nom, description: edition.description || null,
        widgets: edition.widgets, partage: !!edition.partage, ordre: Number(edition.ordre) || 100,
      };
      if (edition.id) await adminApi.modifierTableau(edition.id, charge);
      else await adminApi.creerTableau(charge);
      setEdition(null);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function supprimer() {
    await adminApi.supprimerTableau(suppression.id).catch((e) => setErreur(e.message));
    charger();
    setSuppression(null);
  }

  function majIndicateur(index, modifications) {
    const widgets = edition.widgets.map((w, i) => (i === index ? { ...w, ...modifications } : w));
    setEdition({ ...edition, widgets });
  }

  /** L'ordre des indicateurs est celui de leur affichage sur le tableau de bord. */
  function deplacerIndicateur(de, vers) {
    setEdition({ ...edition, widgets: deplacer(edition.widgets, de, vers) });
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        {t("Un tableau de bord réunit des indicateurs : un total, un décompte, une répartition ou une évolution. Chacun se décrit par ce qu'il mesure, sur quel périmètre et sur quelle période — le tableau d'accueil, lui, est livré avec l'application et ne se modifie pas.")}
      </p>

      <AdminTable
        libelleAjout={t("Nouveau tableau de bord")}
        onAjouter={() => setEdition({
          nom: "", description: "", partage: true, ordre: (tableaux.length + 1) * 10, widgets: [],
        })}
        onModifier={(tableau) => setEdition({ ...tableau })}
        onSupprimer={setSuppression}
        lignes={tableaux}
        reordonnable={{
          onDeplacer: deplacerLigne,
          libelleDe: (tableau) => `le tableau « ${tableau.nom} »`,
        }}
        colonnes={[
          { key: "nom", label: "Tableau" },
          { key: "description", label: "Description",
            render: (tableau) => tableau.description || <span style={{ color: "var(--ink-faint)" }}>—</span> },
          { key: "widgets", label: "Indicateurs",
            render: (tableau) => <span className="tabular">{tableau.widgets.length}</span> },
          { key: "partage", label: t("Visibilité"),
            render: (tableau) => (tableau.partage ? t("Partagé") : <span style={{ color: "var(--ink-faint)" }}>{t("Privé")}</span>) },
        ]}
      />

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {suppression && (
        <ConfirmerSuppression
          typeObjet={"tableau"}
          identifiant={suppression.id}
          intitule={`le tableau « ${suppression.nom} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimer}
        />
      )}

      {edition && options && (
        <Modal
          titre={edition.id ? t("Modifier le tableau de bord") : t("Nouveau tableau de bord")}
          onClose={() => setEdition(null)}
          width={720}
        >
          <form onSubmit={enregistrer}>
            <label style={champStyle}>Nom</label>
            <input required autoFocus value={edition.nom}
                   onChange={(e) => setEdition({ ...edition, nom: e.target.value })}
                   placeholder={t("ex : Comptabilité")} style={inputStyle} />

            <label style={champStyle}>Description</label>
            <input value={edition.description || ""}
                   onChange={(e) => setEdition({ ...edition, description: e.target.value })}
                   style={inputStyle} />

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={!!edition.partage}
                     onChange={(e) => setEdition({ ...edition, partage: e.target.checked })} />
              {t("Visible par tous les comptes")}
            </label>

            <div style={{ ...champStyle, display: "flex", alignItems: "center" }}>
              <span>Indicateurs ({edition.widgets.length})</span>
              <div style={{ flex: 1 }} />
              <button
                type="button"
                onClick={() => setEdition({
                  ...edition,
                  widgets: [...edition.widgets, { ...INDICATEUR_VIDE, id: `w${Date.now()}` }],
                })}
                style={boutonMinuscule}
              >
                <Plus size={12} />
                Ajouter
              </button>
            </div>

            {edition.widgets.length === 0 && (
              <div style={{ fontSize: 12, color: "var(--ink-faint)", padding: "8px 0" }}>
                {t("Aucun indicateur pour l'instant.")}
              </div>
            )}

            <IndicateursOrdonnes
              widgets={edition.widgets}
              options={options}
              referentiels={referentiels}
              onDeplacer={deplacerIndicateur}
              onChange={majIndicateur}
              onSupprimer={(index) => setEdition({
                ...edition, widgets: edition.widgets.filter((_, i) => i !== index),
              })}
            />

            <button type="submit" style={boutonPrimaire}>{t("Enregistrer le tableau")}</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

/**
 * La liste des indicateurs, réordonnable à la poignée. Le hook vit ici plutôt
 * que dans le composant parent : il n'a de sens que le temps d'une édition.
 */
function IndicateursOrdonnes({ widgets, options, referentiels, onDeplacer, onChange, onSupprimer }) {
  const reordre = useReordonnable({ nombre: widgets.length, onDeplacer });

  if (widgets.length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {widgets.map((widget, index) => (
        <Indicateur
          key={widget.id || index}
          widget={widget}
          options={options}
          referentiels={referentiels}
          onChange={(m) => onChange(index, m)}
          onSupprimer={() => onSupprimer(index)}
          proprietesLigne={reordre.proprietesLigne(index)}
          proprietesPoignee={reordre.proprietesPoignee(index, `l'indicateur ${widget.titre || index + 1}`)}
        />
      ))}
    </div>
  );
}

function Indicateur({ widget, options, referentiels, onChange, onSupprimer,
                      proprietesLigne, proprietesPoignee }) {
  const estSomme = widget.type === "somme";
  const estRepartition = widget.type === "repartition";
  const estEvolution = widget.type === "evolution";
  const champsMeta = options.champs.filter((c) => c.champ.startsWith("meta:"));

  return (
    <div
      {...proprietesLigne}
      style={{
        border: "1px solid var(--line)", borderRadius: "var(--radius)", padding: 12,
        ...proprietesLigne.style,
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
        <PoigneeOrdre {...proprietesPoignee} style={{ marginBottom: 6 }} />
        <div style={{ flex: 2 }}>
          <label style={etiquette}>Titre</label>
          <input required value={widget.titre} onChange={(e) => onChange({ titre: e.target.value })}
                 placeholder={t("ex : Factures de l'année")} style={champCompact} />
        </div>
        <div style={{ flex: 1 }}>
          <label style={etiquette}>Mesure</label>
          <Liste
            compact
            valeur={widget.type}
            ariaLabel={t("Type de mesure")}
            options={options.types.map((tableau) => ({ valeur: tableau.type, libelle: tableau.libelle }))}
            onChange={(v) => onChange({ type: v })}
          />
        </div>
        <button type="button" onClick={onSupprimer} style={{ ...boutonIcone, color: "var(--brick)" }}>
          <Trash2 size={12} />
        </button>
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 190 }}>
          <label style={etiquette}>{t("Documents comptés")}</label>
          <Liste
            compact
            valeur={widget.portee || "complets"}
            ariaLabel={t("Documents comptés")}
            options={[
              { valeur: "complets", libelle: t("Complets seulement (par défaut)") },
              { valeur: "incomplets", libelle: t("Incomplets seulement") },
              { valeur: "tous", libelle: "Tous" },
            ]}
            onChange={(v) => onChange({ portee: v })}
          />
          <div style={{ fontSize: 10.5, color: "var(--ink-faint)", marginTop: 3, lineHeight: 1.4 }}>
            {t("Un document auquel il manque un champ exigé par sa catégorie n'est pas encore classé : il ne compte pas, sauf à le demander ici.")}
          </div>
        </div>

        {estSomme && (
          <div style={{ flex: 1, minWidth: 170 }}>
            <label style={etiquette}>{t("Montant à totaliser")}</label>
            <Liste
              compact
              valeur={widget.champ || ""}
              ariaLabel={t("Montant à totaliser")}
              placeholder="— Choisir —"
              options={[{ valeur: "", libelle: "— Choisir —" },
                        ...champsMeta.map((c) => ({ valeur: c.champ, libelle: c.libelle }))]}
              onChange={(v) => onChange({ champ: v })}
            />
          </div>
        )}

        {estRepartition && (
          <div style={{ flex: 1, minWidth: 170 }}>
            <label style={etiquette}>{t("Regrouper par")}</label>
            <Liste
              compact
              valeur={widget.champ || "categorie"}
              ariaLabel="Regroupement"
              options={[
                ...options.groupements.map((g) => ({ valeur: g.champ, libelle: g.libelle,
                                                     groupe: t("Colonnes du document") })),
                ...champsMeta.map((c) => ({ valeur: c.champ, libelle: c.libelle,
                                            groupe: t("Champs extraits") })),
              ]}
              onChange={(v) => onChange({ champ: v })}
            />
          </div>
        )}

        {estEvolution && (
          <div style={{ width: 130 }}>
            <label style={etiquette}>Par</label>
            <Liste
              compact
              valeur={widget.granularite || "mois"}
              ariaLabel={t("Granularité de l'évolution")}
              options={[{ valeur: "mois", libelle: "Mois" }, { valeur: "annee", libelle: t("Année") }]}
              onChange={(v) => onChange({ granularite: v })}
            />
          </div>
        )}

        {(estRepartition || estEvolution) && (
          <div style={{ flex: 1, minWidth: 170 }}>
            <label style={etiquette}>{t("Ce qu'on additionne")}</label>
            <Liste
              compact
              valeur={widget.mesure === "somme" ? widget.mesure_champ || "" : "compte"}
              ariaLabel={t("Mesure de l'évolution")}
              options={[
                { valeur: "compte", libelle: t("Nombre de documents") },
                ...champsMeta.map((c) => ({ valeur: c.champ, libelle: `Total — ${t(c.libelle)}` })),
              ]}
              onChange={(v) => onChange(v === "compte"
                ? { mesure: "compte", mesure_champ: "" }
                : { mesure: "somme", mesure_champ: v })}
            />
          </div>
        )}

        <div style={{ flex: 1, minWidth: 150 }}>
          <label style={etiquette}>{t("Période")}</label>
          <Liste
            compact
            valeur={widget.periode?.type || "tout"}
            ariaLabel={t("Période")}
            options={options.periodes.map((periode) => ({ valeur: periode.type,
                                                          libelle: periode.libelle }))}
            onChange={(v) => onChange({ periode: { ...(widget.periode || {}), type: v } })}
          />
        </div>

        <div style={{ width: 150 }}>
          <label style={etiquette}>{t("Date de référence")}</label>
          <Liste
            compact
            valeur={widget.periode?.champ || "date_document"}
            ariaLabel={t("Date sur laquelle porte la période")}
            options={options.dates.map((date) => ({ valeur: date.champ, libelle: date.libelle }))}
            onChange={(v) => onChange({ periode: { ...(widget.periode || {}), champ: v } })}
          />
        </div>

        {widget.periode?.type === "personnalisee" && (
          <>
            <div style={{ width: 140 }}>
              <label style={etiquette}>Du</label>
              <ChampDate compact valeur={widget.periode?.debut || ""}
                         max={widget.periode?.fin || undefined}
                         ariaLabel={t("Début de la période de l'indicateur")}
                         onChange={(v) => onChange({ periode: { ...widget.periode, debut: v } })} />
            </div>
            <div style={{ width: 140 }}>
              <label style={etiquette}>Au</label>
              <ChampDate compact valeur={widget.periode?.fin || ""}
                         min={widget.periode?.debut || undefined}
                         ariaLabel={t("Fin de la période de l'indicateur")}
                         onChange={(v) => onChange({ periode: { ...widget.periode, fin: v } })} />
            </div>
          </>
        )}

        <div style={{ width: 110 }}>
          <label style={etiquette}>{t("Unité")}</label>
          <input value={widget.unite || ""} onChange={(e) => onChange({ unite: e.target.value })}
                 placeholder="€" style={champCompact} />
        </div>

        {(estRepartition || estEvolution) && (
          <div style={{ width: 110 }}>
            <label style={etiquette}>Largeur</label>
            <Liste
              compact
              valeur={widget.largeur || 2}
              ariaLabel={t("Largeur de l'indicateur")}
              options={[{ valeur: 1, libelle: "Quart" }, { valeur: 2, libelle: t("Moitié") },
                        { valeur: 4, libelle: "Pleine" }]}
              onChange={(v) => onChange({ largeur: Number(v) })}
            />
          </div>
        )}
      </div>

      <FiltresIndicateur widget={widget} referentiels={referentiels}
                         champs={options.champs || []} onChange={onChange} />
    </div>
  );
}

/**
 * Périmètre de l'indicateur (§19.9).
 *
 * Deux listes déroulantes — une catégorie, un émetteur — couvraient le cas
 * courant et rien d'autre : impossible de compter « les factures de plus de
 * 100 € », ni « celles sans titulaire ». C'est pourtant la même mécanique de
 * filtres que le registre et les vues enregistrées.
 *
 * On réemploie donc l'éditeur des vues (§19.8) : un vocabulaire, un composant,
 * et ce que le moteur accepte est ce que l'écran propose. Choisir un **dossier**
 * y compte tous ses types — c'est la façon de mesurer un ensemble, qu'aucun
 * réglage ne permettait jusqu'ici.
 */
function FiltresIndicateur({ widget, referentiels, champs, onChange }) {
  return (
    <div style={{ marginTop: 10 }}>
      <label style={etiquette}>{t("Périmètre")}</label>
      <EditeurCriteres
        criteres={widget.filtres || []}
        champs={champs}
        categories={referentiels.categories}
        onChange={(filtres) => onChange({ filtres })}
        libelleVide={t("Aucun critère : l'indicateur porte sur tous les documents.")}
        aide={t("Les critères se cumulent. Choisir un dossier compte tous ses types de document — c'est ainsi qu'on mesure un ensemble.")}
      />
    </div>
  );
}

const etiquette = {
  display: "block", fontSize: 10, color: "var(--ink-faint)", marginBottom: 3, fontWeight: 600,
};
const champCompact = {
  width: "100%", padding: "5px 7px", fontSize: 12,
  border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)", color: "var(--ink)", fontFamily: "inherit",
};
const boutonMinuscule = {
  display: "inline-flex", alignItems: "center", gap: 4,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "3px 9px", fontSize: 11,
};
const boutonIcone = {
  border: "1px solid var(--line)", background: "transparent", color: "var(--ink-soft)",
  borderRadius: "var(--radius)", padding: 4, display: "flex", alignItems: "center",
};
