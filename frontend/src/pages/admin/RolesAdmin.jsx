import React, { useEffect, useState } from "react";
import { Trash2, Plus, Save, ChevronDown, ChevronRight } from "lucide-react";
import { adminApi, api } from "../../api";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import { aplatirArborescence } from "../../lib/arborescence";
import Liste from "../../components/champs/Liste.jsx";
import { t } from "../../lib/langue";

export default function RolesAdmin() {
  const [roles, setRoles] = useState([]);
  const [categories, setCategories] = useState([]);
  // Le catalogue vient du code (§19.12) : une liste tenue ici finirait par
  // proposer un droit que rien ne vérifie, ou par en oublier un qu'il exige.
  const [catalogue, setCatalogue] = useState({ actions: [], generaux: [] });
  const [vues, setVues] = useState([]);
  const [detailsOuverts, setDetailsOuverts] = useState(false);
  // Six actions par emplacement, c'est six colonnes de cases à cocher. Neuf fois
  // sur dix on règle « consulter » et « modifier » ; les quatre autres se
  // déplient (§19.15) — un réglage fin ne se paie pas à l'écran par défaut.
  const [toutesLesActions, setToutesLesActions] = useState(false);

  const ACTIONS_COURANTES = ["voir", "modifier"];
  const [roleActifId, setRoleActifId] = useState(null);
  const [creation, setCreation] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [suppression, setSuppression] = useState(null);
  const [enregistrement, setEnregistrement] = useState(false);

  function charger() {
    adminApi.roles().then((r) => {
      setRoles(r);
      if (!roleActifId && r.length) setRoleActifId(r[0].id);
    }).catch((e) => setErreur(e.message));
    adminApi.categories().then(setCategories).catch(() => {});
    adminApi.catalogueDroits().then(setCatalogue).catch(() => {});
    api.vues().then(setVues).catch(() => {});
  }
  useEffect(charger, []); // eslint-disable-line react-hooks/exhaustive-deps

  const roleActif = roles.find((r) => r.id === roleActifId);
  // Même arborescence que l'écran des catégories : c'est la seule façon de lire
  // un héritage — voir le dossier au-dessus de ce qui en dépend.
  const arborescence = aplatirArborescence(categories);
  const actionsAffichees = toutesLesActions
    ? catalogue.actions
    : catalogue.actions.filter((a) => ACTIONS_COURANTES.includes(a.cle));
  // Ce qui est masqué doit se dire : une case cochée qu'on ne voit plus reste
  // une case cochée, et l'ignorer serait pire que de l'afficher.
  const actionsMasquees = catalogue.actions
    .filter((a) => !ACTIONS_COURANTES.includes(a.cle))
    .filter((a) => (roleActif?.droits || []).some((d) => d[`peut_${a.cle}`]))
    .map((a) => a.libelle.toLowerCase());

  async function creerRole(e) {
    e.preventDefault();
    setErreur(null);
    try {
      await adminApi.creerRole(creation);
      setCreation(null);
      charger();
    } catch (err) {
      setErreur(err.message);
    }
  }

  async function supprimerRole() {
    await adminApi.supprimerRole(suppression.id).catch((e) => setErreur(e.message));
    setRoleActifId(null);
    charger();
    setSuppression(null);
  }

  /** Ce que ce rôle déclare sur cette catégorie — rien, s'il n'a rien déclaré. */
  function droitPour(categorieId) {
    return roleActif?.droits.find((d) => d.categorie_id === categorieId) || null;
  }

  /**
   * Le droit qui s'applique réellement, une fois l'héritage résolu (§19.12).
   *
   * L'écran doit montrer le **résultat**, pas la seule règle qui l'a produit :
   * un droit hérité se lit comme un droit, avec sa provenance en petit. Sans
   * cela, il faudrait remonter l'arbre de tête pour savoir ce qu'un rôle peut.
   */
  function droitEffectif(categorie) {
    let courante = categorie;
    const parents = new Map(categories.map((c) => [c.id, c]));
    for (let saut = 0; courante && saut < 20; saut += 1) {
      const propre = droitPour(courante.id);
      if (propre) return { droit: propre, herite: courante.id !== categorie.id, de: courante.nom };
      courante = courante.parent_id ? parents.get(courante.parent_id) : null;
    }
    return { droit: null, herite: false, de: null };
  }

  function basculerDroit(categorieId, champ) {
    const droits = [...(roleActif.droits || [])];
    const i = droits.findIndex((d) => d.categorie_id === categorieId);
    if (i === -1) {
      // Première coche sur cette catégorie : on part d'une ligne vide plutôt
      // que de recopier l'héritage — poser une exception, c'est dire ce qu'on
      // veut ici, pas repartir de ce qui vient d'ailleurs.
      const vide = Object.fromEntries(catalogue.actions.map((a) => [`peut_${a.cle}`, false]));
      droits.push({ categorie_id: categorieId, ...vide, [champ]: true });
    } else {
      droits[i] = { ...droits[i], [champ]: !droits[i][champ] };
    }
    setRoles(roles.map((r) => (r.id === roleActifId ? { ...r, droits } : r)));
  }

  /** Retire toute déclaration sur cette catégorie : elle repasse en héritage. */
  function rendreALHeritage(categorieId) {
    const droits = (roleActif.droits || []).filter((d) => d.categorie_id !== categorieId);
    setRoles(roles.map((r) => (r.id === roleActifId ? { ...r, droits } : r)));
  }

  function basculerGeneral(cle) {
    const actuels = roleActif.generaux || [];
    const generaux = actuels.includes(cle)
      ? actuels.filter((g) => g !== cle)
      : [...actuels, cle];
    setRoles(roles.map((r) => (r.id === roleActifId ? { ...r, generaux } : r)));
  }

  function basculerVue(vueId) {
    const actuelles = roleActif.vues || [];
    const suivantes = actuelles.includes(vueId)
      ? actuelles.filter((v) => v !== vueId)
      : [...actuelles, vueId];
    setRoles(roles.map((r) => (r.id === roleActifId ? { ...r, vues: suivantes } : r)));
  }

  async function enregistrerDroits() {
    setEnregistrement(true);
    try {
      // Une catégorie sans aucune coche n'est pas « interdite » : elle est
      // rendue à l'héritage de son dossier. On ne l'envoie donc pas.
      const categoriesDeclarees = (roleActif.droits || []).filter(
        (d) => catalogue.actions.some((a) => d[`peut_${a.cle}`]));
      await adminApi.definirDroits(roleActifId, {
        categories: categoriesDeclarees,
        generaux: roleActif.generaux || [],
        vues: roleActif.vues || [],
        branches: roleActif.branches || [],
      });
      charger();
    } catch (err) {
      setErreur(err.message);
    } finally {
      setEnregistrement(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        {t("Un rôle dit ce qu'on peut faire, et où. Six actions par emplacement — consulter, modifier, déposer, télécharger, mettre à la corbeille, gérer les versions — plus les droits qui ne dépendent d'aucune catégorie. Un compte cumule ses rôles : ce que l'un accorde, aucun autre ne le retire. Un administrateur accède à tout sans passer par eux. Les documents non classés restent visibles de tous les comptes connectés, mais seul un administrateur peut les détruire.")}
      </p>

      <div style={{ display: "flex", gap: 24 }}>
      <div style={{ width: 200, flexShrink: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-faint)" }}>{t("RÔLES")}</span>
          <button onClick={() => setCreation({ nom: "", description: "" })} style={{ border: "none", background: "transparent", color: "var(--accent)" }}>
            <Plus size={16} />
          </button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {roles.map((r) => (
            <button
              key={r.id}
              onClick={() => setRoleActifId(r.id)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                textAlign: "left",
                border: "none",
                borderLeft: r.id === roleActifId ? "3px solid var(--accent)" : "3px solid transparent",
                background: r.id === roleActifId ? "var(--accent-soft)" : "transparent",
                padding: "7px 8px",
                fontSize: 13,
                borderRadius: 2,
              }}
            >
              {r.nom}
            </button>
          ))}
          {roles.length === 0 && <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{t("Aucun rôle.")}</div>}
        </div>
      </div>

      <div style={{ flex: 1 }}>
        {!roleActif ? (
          <div style={{ color: "var(--ink-faint)", fontSize: 13 }}>{t("Sélectionne ou crée un rôle.")}</div>
        ) : (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <div>
                <h3 style={{ fontSize: 16 }}>{roleActif.nom}</h3>
                {roleActif.description && (
                  <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{t(roleActif.description)}</div>
                )}
              </div>
              <button onClick={() => setSuppression(roleActif)} style={{ border: "none", background: "transparent" }}>
                <Trash2 size={15} color="var(--brick)" />
              </button>
            </div>

            <p style={{ fontSize: 12, color: "var(--ink-soft)", margin: "10px 0 14px",
                        lineHeight: 1.5 }}>
              Un droit posé sur un <strong>dossier</strong> vaut pour tous ses types ; une
              case cochée sur un type fait exception et l'emporte. Une ligne sans aucune
              coche n'interdit rien : elle <strong>hérite</strong> de son dossier — c'est
              ce qui évite d'y revenir à chaque type ajouté. « hériter » retire
              l'exception.
            </p>

            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <button
                onClick={() => setToutesLesActions((ouvert) => !ouvert)}
                style={{ display: "flex", alignItems: "center", gap: 5, border: "none",
                         background: "transparent", color: "var(--ink-soft)",
                         fontSize: 12, padding: 0 }}
              >
                {toutesLesActions ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                {toutesLesActions ? t("Ne montrer que consulter et modifier") : t("Toutes les actions")}
              </button>
              {!toutesLesActions && actionsMasquees.length > 0 && (
                <span style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
                  {actionsMasquees.join(", ")} — réglées, mais repliées
                </span>
              )}
            </div>

            <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                          overflow: "auto", marginBottom: 14 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Emplacement</th>
                    {actionsAffichees.map((a) => (
                      <th key={a.cle} style={{ ...thStyle, width: 78, textAlign: "center" }}
                          title={t(a.libelle)}>
                        {a.libelle.split(" ")[0]}
                      </th>
                    ))}
                    <th style={{ ...thStyle, width: 70 }} />
                  </tr>
                </thead>
                <tbody>
                  {/* L'arborescence, dans son ordre et à sa profondeur (§19.17).
                      La grille listait les catégories par ordre d'affichage, à
                      plat : un type pouvait apparaître **avant** le dossier qui
                      le contient, et l'indentation d'un seul cran mentait sur
                      les niveaux. Un écran de droits qui ne montre pas la
                      structure réelle rend l'héritage impossible à lire. */}
                  {arborescence.map((c) => {
                    const { droit, herite, de } = droitEffectif(c);
                    const dossier = (c.nature || "type") === "dossier";
                    return (
                      <tr key={c.id} style={{ borderTop: "1px solid var(--line)" }}>
                        <td style={{ padding: "8px 12px" }}>
                          <span style={{ paddingLeft: c.profondeur * 16,
                                         fontWeight: dossier ? 600 : 400 }}>
                            {c.nom}
                          </span>
                          {herite && (
                            <div style={{ fontSize: 10.5, color: "var(--ink-faint)" }}>
                              hérité de « {de} »
                            </div>
                          )}
                        </td>
                        {actionsAffichees.map((a) => {
                          const coche = !!droit?.[`peut_${a.cle}`];
                          return (
                            <td key={a.cle} style={{ padding: "8px 12px", textAlign: "center" }}>
                              <input
                                type="checkbox"
                                checked={coche}
                                aria-label={`${t(a.libelle)} — ${c.nom}`}
                                onChange={() => basculerDroit(c.id, `peut_${a.cle}`)}
                                // Une case héritée s'affiche en gris : c'est un
                                // droit réel, mais il vient d'ailleurs.
                                style={{ opacity: herite ? 0.5 : 1 }}
                              />
                            </td>
                          );
                        })}
                        <td style={{ padding: "8px 6px", textAlign: "right" }}>
                          {droitPour(c.id) && (
                            <button
                              onClick={() => rendreALHeritage(c.id)}
                              title={t("Retirer l'exception : cette catégorie suivra son dossier")}
                              style={{ border: "none", background: "transparent",
                                       color: "var(--ink-faint)", fontSize: 11 }}
                            >
                              hériter
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Le fin se déplie : neuf droits généraux et la liste des vues
                n'ont pas à occuper l'écran de qui règle une visibilité. */}
            <button
              onClick={() => setDetailsOuverts((ouvert) => !ouvert)}
              style={{ display: "flex", alignItems: "center", gap: 5, border: "none",
                       background: "transparent", color: "var(--ink-soft)", fontSize: 12.5,
                       padding: 0, marginBottom: 10 }}
            >
              {detailsOuverts ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              Droits généraux, vues réservées et branches
              <span style={{ color: "var(--ink-faint)" }}>
                ({(roleActif.generaux || []).length} · {(roleActif.vues || []).length}
                {" "}· {(roleActif.branches || []).length})
              </span>
            </button>

            {detailsOuverts && (
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 14 }}>
                <div style={{ flex: "1 1 280px" }}>
                  <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-soft)",
                                marginBottom: 6 }}>
                    Hors catégorie
                  </div>
                  {catalogue.generaux.map((g) => (
                    <label key={g.cle} style={{ display: "flex", alignItems: "center", gap: 7,
                                                fontSize: 12.5, padding: "3px 0" }}>
                      <input
                        type="checkbox"
                        checked={(roleActif.generaux || []).includes(g.cle)}
                        onChange={() => basculerGeneral(g.cle)}
                      />
                      {t(g.libelle)}
                    </label>
                  ))}
                </div>
                <div style={{ flex: "1 1 280px" }}>
                  <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-soft)",
                                marginBottom: 6 }}>
                    {t("Vues réservées à ce rôle")}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 6,
                                lineHeight: 1.45 }}>
                    {t("Une vue est une lecture préfiltrée du registre. Sans aucune coche ici, chaque vue reste offerte selon son propre partage — restreindre est possible, pas obligatoire.")}
                  </div>
                  {vues.length === 0 && (
                    <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
                      {t("Aucune vue enregistrée.")}
                    </div>
                  )}
                  {vues.map((v) => (
                    <label key={v.id} style={{ display: "flex", alignItems: "center", gap: 7,
                                               fontSize: 12.5, padding: "3px 0" }}>
                      <input
                        type="checkbox"
                        checked={(roleActif.vues || []).includes(v.id)}
                        onChange={() => basculerVue(v.id)}
                      />
                      {v.nom}
                    </label>
                  ))}
                </div>

                <div style={{ flex: "1 1 280px" }}>
                  <Branches
                    branches={roleActif.branches || []}
                    onChange={(branches) => setRoles(roles.map(
                      (r) => (r.id === roleActifId ? { ...r, branches } : r)))}
                  />
                </div>
              </div>
            )}

            <button
              onClick={enregistrerDroits}
              disabled={enregistrement}
              style={{ ...boutonPrimaire, width: "auto", padding: "9px 16px", display: "inline-flex", alignItems: "center", gap: 8 }}
            >
              <Save size={14} />
              {enregistrement ? "Enregistrement…" : t("Enregistrer les droits")}
            </button>
          </div>
        )}
      </div>

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12 }}>{erreur}</div>}

      {creation && (
        <Modal titre={t("Nouveau rôle")} onClose={() => setCreation(null)}>
          <form onSubmit={creerRole}>
            <label style={champStyle}>{t("Nom du rôle")}</label>
            <input
              required
              value={creation.nom}
              onChange={(e) => setCreation({ ...creation, nom: e.target.value })}
              placeholder={t("ex : Enfants, Comptabilité, Invité…")}
              style={inputStyle}
            />
            <label style={champStyle}>{t("Description (optionnelle)")}</label>
            <input
              value={creation.description}
              onChange={(e) => setCreation({ ...creation, description: e.target.value })}
              style={inputStyle}
            />
            <button type="submit" style={boutonPrimaire}>{t("Créer le rôle")}</button>
          </form>
        </Modal>
      )}
      </div>

      {suppression && (
        <ConfirmerSuppression
          typeObjet="role"
          identifiant={suppression.id}
          intitule={`le rôle « ${suppression.nom} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimerRole}
        />
      )}
    </div>
  );
}

const thStyle = {
  textAlign: "left",
  padding: "8px 12px",
  background: "var(--bg-panel-alt)",
  color: "var(--ink-soft)",
  fontSize: 11,
  fontWeight: 600,
};


/**
 * Les branches auxquelles un rôle est restreint (§21.7).
 *
 * Nos droits se posent sur les emplacements ; celui-ci se pose sur les
 * **valeurs** : « ce rôle ne voit que 2025 et 2026 », « seulement le véhicule
 * Clio ». Les valeurs proposées sont celles qui existent réellement, avec leur
 * décompte — on choisit une branche du registre, pas une chaîne de caractères
 * qu'il faudrait deviner.
 *
 * Sans aucune ligne, aucune restriction : pouvoir restreindre n'oblige pas
 * chaque foyer à le faire, et un rôle neuf ne doit rien perdre.
 */
function Branches({ branches, onChange }) {
  const [champs, setChamps] = useState([]);
  const [champ, setChamp] = useState("");
  const [disponibles, setDisponibles] = useState([]);

  useEffect(() => {
    // Les colonnes réglées pour les types, réunies : c'est le vocabulaire que
    // l'administrateur a lui-même nommé, et il n'y a pas de raison de restreindre
    // sur un champ qu'aucun tableau ne montre. On écarte ce qui n'a pas de valeur
    // commune — le texte du document, le nom de fichier.
    api.colonnesCategories()
      .then((reponse) => {
        const parChamp = new Map();
        for (const colonnes of Object.values(reponse.colonnes || {})) {
          for (const colonne of colonnes) {
            if (!colonne.champ || colonne.champ === "texte"
                || colonne.champ === "nom_fichier") continue;
            if (!parChamp.has(colonne.champ)) parChamp.set(colonne.champ, colonne);
          }
        }
        setChamps([...parChamp.values()]);
      })
      .catch(() => setChamps([]));
  }, []);

  useEffect(() => {
    if (!champ) { setDisponibles([]); return; }
    api.groupes(champ).then((r) => setDisponibles(r.branches || [])).catch(() => setDisponibles([]));
  }, [champ]);

  function basculer(valeur) {
    const existe = branches.some((b) => b.champ === champ && b.valeur === valeur);
    onChange(existe
      ? branches.filter((b) => !(b.champ === champ && b.valeur === valeur))
      : [...branches, { champ, valeur }]);
  }

  return (
    <>
      <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-soft)",
                    marginBottom: 6 }}>
        Branches autorisées
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 8,
                    lineHeight: 1.45 }}>
        {t("Restreint ce rôle à certaines valeurs : « seulement 2025 et 2026 », « seulement ce véhicule ». Sans aucune coche sur un champ, ce champ ne restreint rien.")}
      </div>

      <Liste
        valeur={champ}
        ariaLabel={t("Champ à restreindre")}
        options={[{ valeur: "", libelle: t("— choisir un champ —") },
                  ...champs.map((c) => ({ valeur: c.champ, libelle: c.libelle }))]}
        onChange={setChamp}
      />

      {champ && disponibles.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 8 }}>
          {t("Aucune valeur pour ce champ dans le registre.")}
        </div>
      )}
      <div style={{ marginTop: 8, maxHeight: 180, overflowY: "auto" }} className="scrollbar-thin">
        {disponibles.map((b) => (
          <label key={b.valeur} style={{ display: "flex", alignItems: "center", gap: 7,
                                         fontSize: 12.5, padding: "3px 0" }}>
            <input
              type="checkbox"
              checked={branches.some((x) => x.champ === champ && x.valeur === b.valeur)}
              onChange={() => basculer(b.valeur)}
            />
            {t(b.libelle)}
            <span style={{ color: "var(--ink-faint)" }}>({b.nombre})</span>
          </label>
        ))}
      </div>

      {branches.length > 0 && (
        <div style={{ fontSize: 11.5, color: "var(--ink-soft)", marginTop: 10,
                      lineHeight: 1.5 }}>
          <strong>{t("Restrictions posées :")}</strong>{" "}
          {branches.map((b) => `${b.champ} = ${b.valeur}`).join(" · ")}
        </div>
      )}
    </>
  );
}
