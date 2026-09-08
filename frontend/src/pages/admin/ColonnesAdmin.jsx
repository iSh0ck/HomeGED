import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Eye, EyeOff, Plus, RotateCcw, Trash2 } from "lucide-react";
import { adminApi } from "../../api";
import Liste from "../../components/champs/Liste.jsx";
import RoleEcran from "../../components/RoleEcran.jsx";
import { aplatirArborescence } from "../../lib/arborescence";
import { useReordonnable, PoigneeOrdre, deplacer } from "../../components/Reordonnable.jsx";
import { t } from "../../lib/langue";

/**
 * Colonnes du tableau, par catégorie (§18.1).
 *
 * Une facture se lit en une ligne — émetteur, numéro, date d'émission, montant,
 * titulaire — et pas une de ces colonnes n'a de sens pour un courrier. Cet écran
 * décide donc, catégorie par catégorie, de ce que le tableau montre.
 *
 * **On ne configure que ce qui ne va pas de soi.** Une catégorie sans réglage
 * affiche déjà des colonnes déduites de ses champs attendus et des métadonnées
 * réellement extraites : cet écran part de cette déduction, et sert à la
 * corriger — réordonner, renommer, masquer une colonne parasite. Le bouton
 * « Repartir des colonnes déduites » rend la catégorie à cet état.
 */
export default function ColonnesAdmin({ onMontage }) {
  const [categories, setCategories] = useState([]);
  const [categorieId, setCategorieId] = useState(null);
  const [colonnes, setColonnes] = useState([]);
  const [disponibles, setDisponibles] = useState([]);
  // Le dossier dans lequel vit ce type, s'il en a un : c'est à ses voisins que
  // l'on peut appliquer ces colonnes (§19.7).
  const [toutes, setToutes] = useState([]);
  const [dossier, setDossier] = useState(null);
  const [propagation, setPropagation] = useState(false);
  const [ajout, setAjout] = useState("");
  const [erreur, setErreur] = useState(null);
  const [message, setMessage] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  // Tri d'ouverture (§18.49) : `tri` est ce que la catégorie déclare (vide =
  // hérité), `triEffectif` ce qui s'applique réellement.
  const [tri, setTri] = useState({ champ: null, sens: null });
  const [triEffectif, setTriEffectif] = useState(null);
  const [triOuvert, setTriOuvert] = useState(false);
  // Les colonnes retirées se voient-elles quand même sur la fiche d'un document
  // de ce type ? (§19.21) Le réglage vit ici parce qu'il commande ces colonnes-là.
  const [ficheMasques, setFicheMasques] = useState(false);

  useEffect(() => {
    adminApi.categories().then((toutes) => {
      // Le choix ne propose que des types : un dossier organise mais ne porte
      // aucun document (§19.1), le régler ici ne mènerait qu'à un refus. La
      // liste complète sert malgré tout — c'est elle qui nomme les dossiers.
      setToutes(toutes);
      const types = toutes.filter((c) => (c.nature || "type") !== "dossier");
      setCategories(types);
      if (types.length && categorieId === null) setCategorieId(types[0].id);
    }).catch((e) => setErreur(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Le dossier du type choisi : c'est à ses voisins qu'on peut appliquer ces
  // colonnes.
  useEffect(() => {
    const choisi = toutes.find((c) => c.id === categorieId);
    setDossier(choisi?.parent_id ?? null);
  }, [categorieId, toutes]);

  function charger() {
    if (!categorieId) return;
    setMessage(null);
    adminApi.colonnesCategorie(categorieId).then((d) => {
      // Rien de configuré : on part des colonnes déduites plutôt que d'une page
      // blanche. C'est l'état de départ de toute catégorie, et la page blanche
      // laisserait croire que le tableau n'affiche rien.
      const source = d.configurees.length ? d.configurees : d.effectives;
      setColonnes(source.map((c) => ({
        champ: c.champ,
        libelle: c.libelle ?? "",
        visible: c.visible !== false,
        // l'intitulé affiché à défaut de libellé propre, pour ne pas montrer
        // « meta:montant_ttc » à quelqu'un qui range des factures
        defaut: d.effectives.find((e) => e.champ === c.champ)?.libelle ?? c.champ,
      })));
      setDisponibles(d.disponibles || []);

      setTri({ champ: d.tri?.champ ?? null, sens: d.tri?.sens ?? null });
      setTriEffectif(d.tri_effectif ?? null);
      setFicheMasques(!!d.fiche?.champs_masques);
    }).catch((e) => setErreur(e.message));
  }
  useEffect(charger, [categorieId]);

  const reordre = useReordonnable({ nombre: colonnes.length, onDeplacer: deplacerLigne });

  /** L'ordre des colonnes est l'ordre du tableau : on le règle en le montrant. */
  function deplacerLigne(de, vers) {
    setColonnes(deplacer(colonnes, de, vers));
  }

  function ajouter(champ) {
    if (!champ || colonnes.some((c) => c.champ === champ)) return;
    const libelle = disponibles.find((d) => d.champ === champ)?.libelle || champ;
    setColonnes([...colonnes, { champ, libelle: "", visible: true, defaut: libelle }]);
    setAjout("");
  }

  async function enregistrer() {
    setEnvoi(true);
    setErreur(null);
    setMessage(null);
    try {
      await adminApi.enregistrerColonnes(categorieId, colonnes.map((c) => ({
        champ: c.champ,
        libelle: c.libelle.trim() || null,
        visible: c.visible,
      })));
      await adminApi.enregistrerTriCategorie(categorieId, {
        champ: tri.champ || null,
        sens: tri.champ ? (tri.sens || "asc") : null,
      });
      await adminApi.enregistrerOptionsFiche(categorieId, { champs_masques: ficheMasques });
      setMessage(t("Colonnes et tri enregistrés. Le tableau les prend au prochain chargement du registre."));
      charger();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnvoi(false);
    }
  }

  /**
   * Applique les colonnes de ce type à tous les types de son dossier (§19.7).
   *
   * Remplace l'héritage retiré au même paragraphe : une copie faite une fois, à
   * la demande, plutôt qu'un lien permanent qu'on subit. Les types touchés
   * gardent ensuite leur vie propre.
   */
  async function propager() {
    setPropagation(true);
    setErreur(null);
    setMessage(null);
    try {
      const bilan = await adminApi.propagerColonnes(categorieId);
      setMessage(bilan.types.length
        ? `Colonnes appliquées à : ${bilan.types.join(", ")}.`
        : t("Aucun autre type dans ce dossier."));
    } catch (e) {
      setErreur(e.message);
    } finally {
      setPropagation(false);
    }
  }

  async function reinitialiser() {
    setEnvoi(true);
    setErreur(null);
    try {
      await adminApi.enregistrerColonnes(categorieId, []);
      setMessage(t("Configuration retirée : la catégorie retrouve ses colonnes déduites."));
      charger();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnvoi(false);
    }
  }

  const restants = disponibles.filter((d) => !colonnes.some((c) => c.champ === d.champ));
  const nomCategorie = (id) => toutes.find((c) => c.id === id)?.nom || `n°${id}`;
  /** L'intitulé de la colonne, tel que le tableau l'affiche — pas sa clé technique. */
  const libelleColonne = (champ) =>
    colonnes.find((c) => c.champ === champ)?.defaut
    || disponibles.find((d) => d.champ === champ)?.libelle
    || champ;

  return (
    <div>
      <RoleEcran courant="colonnes" onMontage={onMontage} />
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16, lineHeight: 1.55 }}>
        {t("Chaque catégorie a son tableau. Une facture se lit en une ligne — émetteur, numéro, date, montant, titulaire — là où un courrier n'a que faire de ces colonnes. Rien n'est obligatoire ici : sans réglage, les colonnes sont déduites des champs attendus de la catégorie et des données réellement extraites de ses documents.")}
      </p>

      <div style={{ maxWidth: 320, marginBottom: 18 }}>
        <label style={{ fontSize: 12, color: "var(--ink-faint)", display: "block", marginBottom: 4 }}>
          Catégorie
        </label>
        <Liste
          valeur={categorieId ?? ""}
          ariaLabel={t("Catégorie")}
          options={aplatirArborescence(categories).map((c) => ({
            valeur: c.id,
            libelle: `${" ".repeat(c.profondeur * 3)}${c.nom}`,
          }))}
          onChange={(v) => setCategorieId(Number(v))}
        />
      </div>

      {dossier && (
        <div style={bandeau}>
          Ce type est dans le dossier « {nomCategorie(dossier)} ». Une fois ses colonnes
          enregistrées, vous pouvez les appliquer d'un coup aux autres types de ce
          dossier — c'est une copie faite à la demande, chacun garde ensuite sa vie
          propre.
          <button
            onClick={propager}
            disabled={propagation || colonnes.length === 0}
            style={{
              marginLeft: 10, border: "1px solid var(--line-strong)",
              background: "var(--bg-panel)", color: "var(--ink-soft)",
              borderRadius: "var(--radius)", padding: "3px 10px", fontSize: 12,
            }}
          >
            {propagation ? "Application…" : t("Appliquer aux autres types du dossier")}
          </button>
        </div>
      )}

      <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
        {colonnes.length === 0 && (
          <div style={{ padding: "14px 16px", fontSize: 12.5, color: "var(--ink-faint)" }}>
            {t("Aucune colonne : le tableau retomberait sur son affichage par défaut.")}
          </div>
        )}
        {colonnes.map((colonne, index) => {
          const proprietes = reordre.proprietesLigne(index);
          return (
          <div
            key={colonne.champ}
            {...proprietes}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "9px 12px",
              borderBottom: index < colonnes.length - 1 ? "1px solid var(--line)" : "none",
              background: colonne.visible ? "transparent" : "var(--bg-panel-alt)",
              opacity: colonne.visible ? 1 : 0.65,
              ...proprietes.style,
            }}
          >
            <PoigneeOrdre {...reordre.proprietesPoignee(index, `la colonne ${colonne.defaut}`)} />

            <span className="tabular" style={{ fontSize: 11, color: "var(--ink-faint)", width: 18 }}>
              {index + 1}
            </span>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, color: "var(--ink)" }}>{colonne.defaut}</div>
              <code style={{ fontSize: 11, color: "var(--ink-faint)" }}>{colonne.champ}</code>
            </div>

            <input
              value={colonne.libelle}
              placeholder={colonne.defaut}
              aria-label={`Intitulé de la colonne ${colonne.defaut}`}
              onChange={(e) => setColonnes(colonnes.map((c, i) =>
                i === index ? { ...c, libelle: e.target.value } : c))}
              style={{
                width: 170, border: "1px solid var(--line-strong)", background: "transparent",
                borderRadius: "var(--radius)", padding: "5px 8px", fontSize: 12.5,
                color: "var(--ink)",
              }}
            />

            <IconeBouton
              label={colonne.visible ? t("Masquer cette colonne") : t("Afficher cette colonne")}
              onClick={() => setColonnes(colonnes.map((c, i) =>
                i === index ? { ...c, visible: !c.visible } : c))}
            >
              {colonne.visible ? <Eye size={13} /> : <EyeOff size={13} />}
            </IconeBouton>

            <IconeBouton
              label={t("Retirer cette colonne")}
              danger
              onClick={() => setColonnes(colonnes.filter((_, i) => i !== index))}
            >
              <Trash2 size={13} />
            </IconeBouton>
          </div>
          );
        })}
      </div>

      {/* Une colonne masquée disparaît du tableau ; reste à dire si elle
          disparaît aussi de la fiche du document (§19.21). Les deux gestes se
          ressemblent mais ne disent pas la même chose : on allège un tableau
          qu'on parcourt, on ne rend pas forcément la donnée introuvable. */}
      <label style={{
        display: "flex", alignItems: "flex-start", gap: 8, marginTop: 12,
        padding: "10px 14px", border: "1px solid var(--line)",
        borderRadius: "var(--radius)", fontSize: 12.5, color: "var(--ink)",
      }}>
        <input
          type="checkbox"
          checked={ficheMasques}
          onChange={(e) => setFicheMasques(e.target.checked)}
          style={{ marginTop: 2 }}
        />
        <span>
          Montrer aussi les colonnes retirées sur la fiche du document
          <span style={{ display: "block", color: "var(--ink-faint)", fontSize: 11.5,
                         marginTop: 2, lineHeight: 1.45 }}>
            {t("Les colonnes masquées ci-dessus n'apparaissent pas dans le tableau. Cochez pour qu'elles restent lisibles dans les métadonnées, à l'ouverture d'un document de ce type.")}
          </span>
        </span>
      </label>

      {/* Le tri se règle une fois par type, et se lit tout le temps : la ligne
          dit d'abord ce qui s'applique, le réglage se déplie (§19.15). */}
      <div style={{
        marginTop: 16, border: "1px solid var(--line)", borderRadius: "var(--radius)",
        padding: "10px 14px",
      }}>
        <button
          onClick={() => setTriOuvert((ouvert) => !ouvert)}
          style={{ display: "flex", alignItems: "center", gap: 6, border: "none",
                   background: "transparent", color: "var(--ink)", fontSize: 12.5,
                   padding: 0, width: "100%", textAlign: "left" }}
        >
          {triOuvert ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          <span>{t("Tri à l'ouverture")}</span>
          <span style={{ color: "var(--ink-soft)" }}>
            {triEffectif
              ? `${libelleColonne(triEffectif.champ)} · ${triEffectif.sens === "asc"
                  ? "croissant" : t("décroissant")}`
              : "—"}
          </span>
          {!tri.champ && (
            <span style={{ fontSize: 11, color: "var(--ink-faint)" }}>
              (réglage général du foyer)
            </span>
          )}
        </button>

        {triOuvert && (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, flexWrap: "wrap",
                      marginTop: 12 }}>
          <div style={{ width: 240 }}>
            <label style={{ fontSize: 12, color: "var(--ink-faint)", display: "block", marginBottom: 4 }}>
              {t("Tri à l'ouverture du registre")}
            </label>
            <Liste
              valeur={tri.champ || ""}
              ariaLabel={t("Colonne du tri par défaut")}
              options={[
                { valeur: "", libelle: t("— Hérité —") },
                ...colonnes.map((c) => ({ valeur: c.champ, libelle: c.libelle.trim() || c.defaut })),
              ]}
              onChange={(v) => setTri({ champ: v || null, sens: v ? (tri.sens || "desc") : null })}
            />
          </div>
          <div style={{ width: 170 }}>
            <label style={{ fontSize: 12, color: "var(--ink-faint)", display: "block", marginBottom: 4 }}>
              Sens
            </label>
            <Liste
              valeur={tri.sens || "desc"}
              ariaLabel={t("Sens du tri par défaut")}
              options={[
                { valeur: "desc", libelle: t("Décroissant (récent d'abord)") },
                { valeur: "asc", libelle: "Croissant" },
              ]}
              onChange={(v) => setTri({ ...tri, sens: v })}
            />
          </div>
        </div>
        )}
        {triOuvert && (
        <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.45 }}>
          {tri.champ ? (
            <>Le registre s'ouvre sur ce tri pour cette catégorie. Chacun peut ensuite
            cliquer une colonne ; un troisième clic sur la même ramène ici.</>
          ) : (
            <>
              Rien n'est déclaré : la catégorie suit son parent, puis le réglage général
              du foyer.
              {triEffectif && (
                <> Aujourd'hui, elle s'ouvre sur <code>{triEffectif.champ}</code>
                {" "}({triEffectif.sens === "asc" ? "croissant" : t("décroissant")}).</>
              )}
            </>
          )}
        </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "flex-end", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
        <div style={{ width: 280 }}>
          <label style={{ fontSize: 12, color: "var(--ink-faint)", display: "block", marginBottom: 4 }}>
            Ajouter une colonne
          </label>
          <Liste
            recherchable
            valeur={ajout}
            ariaLabel={t("Ajouter une colonne")}
            placeholder={t("— Choisir un champ —")}
            // Groupés par origine (§21.13) : ce que l'application tient
            // elle-même, ce que ce type déclare attendre, ce que les règles ont
            // écrit, et ce que le document concerne. Trois façons de les changer,
            // et la liste ne disait pas laquelle.
            options={restants.map((d) => ({ valeur: d.champ, libelle: d.libelle,
                                            groupe: d.libelle_origine }))}
            onChange={(v) => ajouter(v)}
          />
          <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.45 }}>
            {t("Seuls les champs qui concernent ce type sont proposés : les colonnes que porte tout document, ce que ce type déclare attendre, ce que ses règles écrivent, et ce que ses documents portent déjà.")}
          </div>
        </div>
        <button onClick={() => ajouter(ajout)} disabled={!ajout} style={boutonSecondaire}>
          <Plus size={13} />
          Ajouter
        </button>
        <div style={{ flex: 1 }} />
        <button onClick={reinitialiser} disabled={envoi} style={boutonSecondaire}>
          <RotateCcw size={13} />
          {t("Repartir des colonnes déduites")}
        </button>
        <button onClick={enregistrer} disabled={envoi || !categorieId} style={boutonPrimaire}>
          {envoi ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>

      {message && (
        <div style={{ marginTop: 12, fontSize: 12.5, color: "var(--accent)" }}>{message}</div>
      )}
      {erreur && (
        <div style={{ marginTop: 12, fontSize: 12.5, color: "var(--brick)" }}>{erreur}</div>
      )}
    </div>
  );
}

function IconeBouton({ children, onClick, label, disabled, danger }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      style={{
        display: "flex", border: "1px solid transparent", background: "transparent",
        color: danger ? "var(--brick)" : "var(--ink-faint)",
        borderRadius: "var(--radius)", padding: 3,
        opacity: disabled ? 0.3 : 1,
      }}
    >
      {children}
    </button>
  );
}

const bandeau = {
  padding: "9px 12px", marginBottom: 12, borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
  fontSize: 12.5, color: "var(--ink-soft)",
};

const commun = {
  display: "inline-flex", alignItems: "center", gap: 6,
  borderRadius: "var(--radius)", padding: "7px 13px", fontSize: 12.5,
};

const boutonSecondaire = {
  ...commun, border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)",
};

const boutonPrimaire = {
  ...commun, border: "none", background: "var(--accent)", color: "#fff", fontWeight: 600,
};
