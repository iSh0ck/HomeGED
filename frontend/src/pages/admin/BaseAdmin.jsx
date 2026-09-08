import React, { useEffect, useState } from "react";
import { Database, Eye, Lock, Plus, Trash2, Pencil, Search, Columns3, AlertTriangle } from "lucide-react";
import { adminApi, api } from "../../api";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import Pagination from "../../components/Pagination.jsx";
import Liste from "../../components/champs/Liste.jsx";
import { useReordonnable, PoigneeOrdre, deplacer } from "../../components/Reordonnable.jsx";
import { t } from "../../lib/langue";

const PAR_PAGE_DEFAUT = 25;

/**
 * Exploration et administration de la base (§17).
 *
 * Deux régimes, matérialisés dans l'écran : les tables du fonctionnement de
 * l'application se consultent seulement, les tables de données créées ici se
 * modifient entièrement. Écrire directement dans `documents` ou `utilisateurs`
 * depuis une grille court-circuiterait les droits, l'audit et la gestion des
 * fichiers — c'est refusé côté serveur, et l'écran l'annonce clairement.
 */
export default function BaseAdmin() {
  const [tables, setTables] = useState([]);
  const [table, setTable] = useState(null);
  const [colonnes, setColonnes] = useState([]);
  const [page, setPage] = useState({ total: 0, colonnes: [], lignes: [] });
  const [recherche, setRecherche] = useState("");
  const [decalage, setDecalage] = useState(0);
  const [parPage, setParPage] = useState(PAR_PAGE_DEFAUT);
  const [types, setTypes] = useState([]);
  const [erreur, setErreur] = useState(null);
  const [dialogue, setDialogue] = useState(null); // 'table' | 'colonne' | {ligne}
  const [suppression, setSuppression] = useState(null); // {portee: 'table'|'ligne', ...}

  function chargerTables() {
    adminApi.tablesBase().then(setTables).catch((e) => setErreur(e.message));
  }
  useEffect(() => {
    chargerTables();
    adminApi.typesColonnes().then(setTypes).catch(() => {});
  }, []);

  function chargerContenu() {
    if (!table) return;
    adminApi.colonnesBase(table.nom).then(setColonnes).catch((e) => setErreur(e.message));
    adminApi
      .lignesBase(table.nom, { limite: parPage, decalage, recherche })
      .then(setPage)
      .catch((e) => setErreur(e.message));
  }
  useEffect(chargerContenu, [table, decalage, parPage, recherche]);

  function selectionner(choisie) {
    setTable(choisie);
    setDecalage(0);
    setRecherche("");
    setErreur(null);
  }

  async function action(promesse) {
    setErreur(null);
    try {
      await promesse;
      setDialogue(null);
      chargerTables();
      chargerContenu();
    } catch (e) {
      setErreur(e.message);
      throw e;
    }
  }

  const tablesDonnees = tables.filter((candidate) => candidate.modifiable);
  const tablesSysteme = tables.filter((candidate) => !candidate.modifiable);

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        Vos <strong>tables de données</strong> se modifient librement : ce sont les
        références du foyer — les <strong>émetteurs</strong> de vos documents, et toutes
        celles que vous créez ici (véhicules, personnes…), qui peuvent ensuite alimenter
        un champ personnalisé. Leur nom commence par <code>usr_</code>.
        <br />
        <span style={{ color: "var(--ink-faint)" }}>
          Les tables du fonctionnement de l'application (préfixe <code>sys_</code>) restent
          consultables mais non modifiables : y écrire directement contournerait les droits,
          le contrôle de conformité, la journalisation et la gestion des fichiers.
        </span>
      </p>

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        <div style={{ width: 240, flexShrink: 0 }}>
          <EnTete
            libelle={t("Tables de données")}
            action={
              <button onClick={() => setDialogue("table")} style={boutonMinuscule} title={t("Créer une table")}>
                <Plus size={12} />
                Nouvelle
              </button>
            }
          />
          {tablesDonnees.length === 0 && (
            <div style={{ fontSize: 11, color: "var(--ink-faint)", padding: "4px 8px 10px" }}>
              {t("Aucune pour l'instant.")}
            </div>
          )}
          {tablesDonnees.map((candidate) => (
            <LigneTable key={candidate.nom} table={candidate} actif={table?.nom === candidate.nom}
                        onClick={() => selectionner(candidate)} />
          ))}

          <div style={{ marginTop: 18 }}>
            <EnTete libelle={t("Tables du système")} />
            {tablesSysteme.map((candidate) => (
              <LigneTable key={candidate.nom} table={candidate} actif={table?.nom === candidate.nom}
                          onClick={() => selectionner(candidate)} />
            ))}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {!table ? (
            <div
              style={{
                display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
                padding: "70px 16px", color: "var(--ink-faint)",
              }}
            >
              <Database size={28} />
              <div style={{ fontSize: 13 }}>{t("Choisis une table pour en voir le contenu.")}</div>
            </div>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 600 }}>{t(table.libelle)}</div>
                  <div className="tabular" style={{ fontSize: 11, color: "var(--ink-faint)" }}>
                    {table.nom} · {page.total} ligne{page.total > 1 ? "s" : ""}
                    {!table.modifiable && " · consultation seule"}
                  </div>
                </div>
                <div style={{ flex: 1 }} />
                {table.modifiable && (
                  <>
                    {/* Deux gestes de nature différente, et deux boutons qui le
                        disent : ajouter **une ligne** (une donnée) et régler **les
                        colonnes** (la structure). L'ajout d'une colonne a rejoint
                        l'écran des colonnes : deux boutons voisins nommés « Colonne »
                        et « Colonnes » ne se distinguaient que par un s. */}
                    <button onClick={() => setDialogue({ ligne: {} })} style={boutonMinuscule}>
                      <Plus size={12} />
                      Ajouter une ligne
                    </button>
                    <button onClick={() => setDialogue("structure")} style={boutonMinuscule}>
                      <Columns3 size={12} />
                      Colonnes
                    </button>
                    <button onClick={() => setDialogue("affichage")} style={boutonMinuscule}>
                      <Eye size={12} />
                      Affichage
                    </button>
                    <button
                      onClick={() => setSuppression({ portee: "table" })}
                      style={{ ...boutonMinuscule, borderColor: "var(--brick)", color: "var(--brick)" }}
                    >
                      <Trash2 size={12} />
                      Supprimer la table
                    </button>
                  </>
                )}
              </div>

              <div style={{ ...cadreRecherche }}>
                <Search size={13} color="var(--ink-faint)" />
                <input
                  value={recherche}
                  onChange={(e) => { setDecalage(0); setRecherche(e.target.value); }}
                  placeholder={t("Rechercher dans toutes les colonnes…")}
                  style={{ border: "none", outline: "none", background: "transparent", fontSize: 12, width: "100%", color: "var(--ink)" }}
                />
              </div>

              <div style={{ overflowX: "auto", border: "1px solid var(--line)", borderRadius: "var(--radius)" }} className="scrollbar-thin">
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr>
                      {page.colonnes.map((c) => (
                        <th key={c} style={thStyle}>{c}</th>
                      ))}
                      {table.modifiable && <th style={{ ...thStyle, width: 70 }} />}
                    </tr>
                  </thead>
                  <tbody>
                    {page.lignes.length === 0 && (
                      <tr>
                        <td colSpan={page.colonnes.length + 1} style={{ padding: 18, textAlign: "center", color: "var(--ink-faint)" }}>
                          {recherche ? t("Aucune ligne ne correspond.") : t("Table vide.")}
                        </td>
                      </tr>
                    )}
                    {page.lignes.map((ligne, i) => (
                      <tr key={ligne.id ?? i} style={{ borderTop: "1px solid var(--line)" }}>
                        {page.colonnes.map((c) => (
                          <td key={c} style={tdStyle}>
                            {ligne[c] === null || ligne[c] === undefined ? (
                              <span style={{ color: "var(--ink-faint)" }}>—</span>
                            ) : (
                              String(ligne[c])
                            )}
                          </td>
                        ))}
                        {table.modifiable && (
                          <td style={{ ...tdStyle, whiteSpace: "nowrap", textAlign: "right" }}>
                            <button
                              onClick={() => setDialogue({ ligne })}
                              aria-label="Modifier"
                              style={boutonIcone}
                            >
                              <Pencil size={12} />
                            </button>
                            <button
                              onClick={() => setSuppression({ portee: "ligne", ligne })}
                              aria-label="Supprimer"
                              style={{ ...boutonIcone, color: "var(--brick)" }}
                            >
                              <Trash2 size={12} />
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Pagination
                total={page.total}
                parPage={parPage}
                decalage={decalage}
                onDecalage={setDecalage}
                onParPage={(n) => { setParPage(n); setDecalage(0); }}
              />

              {colonnes.some((c) => c.masquee || c.tronquee) && (
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 10 }}>
                  Colonnes non restituées intégralement :{" "}
                  {colonnes.filter((c) => c.masquee || c.tronquee)
                    .map((c) => `${c.nom} (${c.masquee ? t("masquée") : t("tronquée")})`)
                    .join(", ")}.
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 12 }}>{erreur}</div>}

      {suppression?.portee === "table" && table && (
        <ConfirmerSuppression
          typeObjet="table_donnees"
          identifiant={table.nom}
          intitule={`la table « ${t(table.libelle)} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={async () => {
            await action(adminApi.supprimerTableBase(table.nom));
            setSuppression(null);
            setTable(null);
          }}
        />
      )}

      {suppression?.portee === "ligne" && table && (
        <ConfirmerSuppression
          intitule={`la ligne nº${suppression.ligne.id} de « ${t(table.libelle)} »`}
          consequences={[
            {
              nature: "suppression",
              libelle: Object.entries(suppression.ligne)
                .filter(([cle]) => cle !== "id")
                .map(([cle, valeur]) => `${cle} : ${valeur ?? "—"}`)
                .join(" · "),
              precision: t("définitivement — cette table n'a pas de corbeille"),
            },
            {
              nature: "avertissement",
              libelle: t("Un document qui pointait cette ligne gardera une référence vide"),
              precision: t("les champs personnalisés adossés à cette table ne la proposeront plus"),
            },
          ]}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={async () => {
            await action(adminApi.supprimerLigneBase(table.nom, suppression.ligne.id));
            setSuppression(null);
          }}
        />
      )}

      {dialogue === "table" && (
        <DialogueTable types={types} onClose={() => setDialogue(null)} onValider={(d) => action(adminApi.creerTableBase(d))} />
      )}
      {dialogue === "structure" && table && (
        <DialogueStructure
          table={table}
          colonnes={colonnes}
          tables={tablesDonnees}
          types={types}
          onFermer={() => { setDialogue(null); chargerTables(); chargerContenu(); }}
        />
      )}
      {dialogue === "affichage" && table && (
        <DialogueAffichage
          table={table}
          colonnes={colonnes}
          onClose={() => setDialogue(null)}
          onValider={(d) => action(adminApi.reglerAffichageTable(table.nom, d))}
        />
      )}
      {dialogue?.ligne && table && (
        <DialogueLigne
          colonnes={colonnes}
          ligne={dialogue.ligne}
          onClose={() => setDialogue(null)}
          onValider={(valeurs) =>
            action(
              dialogue.ligne.id
                ? adminApi.modifierLigneBase(table.nom, dialogue.ligne.id, valeurs)
                : adminApi.creerLigneBase(table.nom, valeurs)
            )
          }
        />
      )}
    </div>
  );
}

/**
 * Réglages d'affichage d'une table (§18.13).
 *
 * Deux questions, et une seule réponse à donner : **comment une ligne se lit**,
 * et **à quoi on la reconnaît** dans le texte d'un document. Les colonnes
 * identifiantes répondent aux deux — dans l'ordre choisi, elles composent le
 * libellé (« Camille DURAND ») et ce sont elles que l'on cherche pour rattacher
 * une facture à quelqu'un. Une seule déclaration, deux usages qui ne peuvent
 * donc pas diverger.
 *
 * C'était jusqu'ici posé par une migration, donc intouchable : un autre foyer
 * héritait de choix qu'il ne pouvait pas revoir.
 */
function DialogueAffichage({ table, colonnes, onClose, onValider }) {
  const noms = colonnes.map((c) => c.nom).filter((n) => n !== "id");
  const [libelle, setLibelle] = useState(table.libelle || "");
  const [colonneLibelle, setColonneLibelle] = useState(table.colonne_libelle || noms[0] || "");
  const [identifiantes, setIdentifiantes] = useState(
    (table.colonnes_identifiantes || "").split(",").map((c) => c.trim()).filter(Boolean)
  );

  function basculer(nom) {
    setIdentifiantes(identifiantes.includes(nom)
      ? identifiantes.filter((c) => c !== nom)
      // on ajoute à la fin : l'ordre des clics est l'ordre d'affichage
      : [...identifiantes, nom]);
  }

  const reordre = useReordonnable({
    nombre: identifiantes.length,
    onDeplacer: (de, vers) => setIdentifiantes(deplacer(identifiantes, de, vers)),
  });

  const apercu = (identifiantes.length ? identifiantes : [colonneLibelle])
    .map((c) => `‹${c}›`).join(" ");

  return (
    <Modal titre={t("Affichage de la table")} onClose={onClose} width={470}>
      <div style={champStyle}>
        <label style={labelStyle}>{t("Intitulé")}</label>
        <input value={libelle} onChange={(e) => setLibelle(e.target.value)} style={inputStyle} />
      </div>

      <div style={champStyle}>
        <label style={labelStyle}>{t("Colonne d'affichage")}</label>
        <Liste
          valeur={colonneLibelle}
          ariaLabel={t("Colonne d'affichage")}
          options={noms.map((n) => ({ valeur: n, libelle: n }))}
          onChange={setColonneLibelle}
        />
        <div style={aideStyle}>
          {t("Ce qui désigne une ligne quand aucune colonne identifiante n'est choisie.")}
        </div>
      </div>

      <div style={champStyle}>
        <label style={labelStyle}>{t("Colonnes identifiantes, dans l'ordre")}</label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
          {noms.map((nom) => {
            const rang = identifiantes.indexOf(nom);
            const choisie = rang >= 0;
            return (
              <button
                key={nom}
                onClick={() => basculer(nom)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 5,
                  border: `1px solid ${choisie ? "var(--accent)" : "var(--line-strong)"}`,
                  background: choisie ? "var(--accent-soft)" : "transparent",
                  color: choisie ? "var(--accent)" : "var(--ink-soft)",
                  borderRadius: 12, padding: "3px 10px", fontSize: 12,
                }}
              >
                {choisie && <span className="tabular" style={{ fontWeight: 700 }}>{rang + 1}</span>}
                {nom}
              </button>
            );
          })}
        </div>
        {identifiantes.length > 1 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 4 }}>
              {t("Ordre retenu — faites glisser pour le changer")}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {identifiantes.map((nom, index) => {
                const proprietes = reordre.proprietesLigne(index);
                return (
                  <span
                    key={nom}
                    {...proprietes}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 4,
                      border: "1px solid var(--accent)", background: "var(--accent-soft)",
                      color: "var(--accent)", borderRadius: 12, padding: "3px 10px 3px 4px",
                      fontSize: 12, ...proprietes.style,
                    }}
                  >
                    <PoigneeOrdre
                      {...reordre.proprietesPoignee(index, nom)}
                      style={{ color: "var(--accent)", padding: 0 }}
                    />
                    <span className="tabular" style={{ fontWeight: 700 }}>{index + 1}</span>
                    {nom}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        <div style={aideStyle}>
          Ces colonnes servent à <strong>deux choses</strong>, et à rien d'autre :
          <br />
          — elles <strong>composent le nom affiché</strong> d'une ligne dans les listes de
          choix, dans l'ordre retenu ({" "}<code>prenom</code> puis <code>nom</code> donne
          « Camille DURAND ») ;
          <br />
          — ce sont elles que l'application <strong>cherche dans le texte</strong> d'un
          document pour lui rattacher la bonne ligne. En choisir plusieurs demande qu'elles
          y figurent toutes : un nom de famille seul ne désigne personne dans un foyer où
          plusieurs personnes le portent.
          <br />
          <strong>{t("Elles n'interdisent rien.")}</strong> Deux lignes peuvent porter les mêmes
          valeurs. Pour qu'une valeur ne puisse pas se répéter, c'est l'
          <strong>identifiant naturel</strong> qui se déclare, dans l'écran « Colonnes ».
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-soft)" }}>
          Aperçu : <strong style={{ color: "var(--ink)" }}>{apercu || "—"}</strong>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
        <button onClick={onClose} style={boutonSecondaireModal}>Annuler</button>
        <button
          onClick={() => onValider({
            libelle: libelle.trim() || null,
            colonne_libelle: colonneLibelle || null,
            colonnes_identifiantes: identifiantes.join(","),
          })}
          style={boutonPrimaire}
        >
          Enregistrer
        </button>
      </div>
    </Modal>
  );
}

const labelStyle = { fontSize: 12, color: "var(--ink-faint)", display: "block", marginBottom: 4 };
const aideStyle = { fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5, marginTop: 5 };
const boutonSecondaireModal = {
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "8px 14px", fontSize: 13,
};

/**
 * Structure d'une table du foyer (§18.32) : colonnes, identifiant naturel,
 * liaisons vers d'autres tables.
 *
 * Ce qui manquait : on pouvait ajouter une colonne, jamais la renommer, changer
 * son type ni la retirer — et rien ne permettait de dire qu'une colonne
 * « propriétaire » désigne une personne du foyer plutôt qu'un texte libre.
 *
 * Les garde-fous vivent côté serveur, où ils protègent vraiment ; cet écran se
 * contente de dire ce qu'il sait avant d'agir — combien de valeurs une colonne
 * porte, à quoi elle sert — pour qu'on ne détruise rien en aveugle.
 */
function DialogueStructure({ table, colonnes, tables, types, onFermer }) {
  const [liste, setListe] = useState(colonnes);
  const [uniques, setUniques] = useState([]);
  const [edition, setEdition] = useState(null);
  const [suppression, setSuppression] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [message, setMessage] = useState(null);

  function recharger() {
    adminApi.colonnesTableBase(table.nom).then(setListe).catch((e) => setErreur(e.message));
    adminApi.uniciteBase(table.nom).then(setUniques).catch(() => setUniques([]));
  }
  useEffect(recharger, [table.nom]);

  async function agir(promesse, texte) {
    setErreur(null);
    setMessage(null);
    try {
      await promesse;
      setMessage(texte);
      recharger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  const modifiables = liste.filter((c) => c.nom !== "id");
  const cleNaturelle = uniques[0];
  const [ajout, setAjout] = useState(false);

  return (
    <Modal titre={`Colonnes de « ${t(table.libelle)} »`} onClose={onFermer} width={640}>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55, marginTop: 2 }}>
        La colonne <code>id</code> reste la clé de la table : c'est elle qui permet de
        modifier une ligne dont on vient justement de changer l'identifiant visible.
      </p>

      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
        <button onClick={() => setAjout(true)} style={boutonMinuscule}>
          <Plus size={12} />
          Ajouter une colonne
        </button>
      </div>

      <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", marginTop: 14 }}>
        {modifiables.map((colonne, index) => (
          <div key={colonne.nom} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "9px 12px",
            borderBottom: index < modifiables.length - 1 ? "1px solid var(--line)" : "none",
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, color: "var(--ink)" }}>
                {colonne.libelle || colonne.nom}
                {colonne.unique && (
                  <span title={t("Identifiant naturel : deux lignes ne peuvent pas partager cette valeur")}
                        style={etiquette("var(--accent)")}>unique</span>
                )}
                {!colonne.nullable && <span style={etiquette("var(--amber)")}>obligatoire</span>}
                {colonne.source_table && (
                  <span style={etiquette("var(--ink-faint)")}>→ {colonne.source_table}</span>
                )}
              </div>
              <code style={{ fontSize: 11, color: "var(--ink-faint)" }}>
                {colonne.nom} · {colonne.type_logique || colonne.type}
              </code>
            </div>
            <button onClick={() => setEdition(colonne)} style={boutonMinuscule}>
              <Pencil size={12} />
              Modifier
            </button>
            <button
              onClick={() => adminApi.impactColonneBase(table.nom, colonne.nom)
                .then((impact) => setSuppression({ colonne, impact }))
                .catch((e) => setErreur(e.message))}
              style={{ ...boutonMinuscule, borderColor: "var(--brick)", color: "var(--brick)" }}
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 18 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 4 }}>
          Identifiant naturel <span style={{ fontWeight: 400, color: "var(--ink-faint)" }}>
            — une règle, pas un affichage
          </span>
        </div>
        <p style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5, margin: "0 0 8px" }}>
          Ce qui, pour un humain, désigne la ligne sans ambiguïté : une immatriculation, un
          numéro de contrat. La base <strong>refusera</strong> alors deux lignes portant la
          même valeur — c'est une contrainte, elle empêche une saisie.
          <br />
          À ne pas confondre avec les <strong>colonnes identifiantes</strong> (écran
          « Affichage ») : celles-ci ne refusent rien, elles disent comment une ligne
          <em> se lit</em> dans les listes de choix et à quoi on la reconnaît dans le texte
          d'un document. Deux personnes peuvent porter le même nom ; on veut les afficher
          « Prénom NOM » sans pour autant interdire l'homonymie.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={{ minWidth: 200 }}>
            <Liste
              valeur={cleNaturelle ? cleNaturelle.colonnes.join(",") : ""}
              ariaLabel={t("Identifiant naturel")}
              placeholder={t("— Aucun —")}
              options={[{ valeur: "", libelle: t("— Aucun —") },
                        ...modifiables.map((c) => ({ valeur: c.nom, libelle: c.libelle || c.nom }))]}
              onChange={(v) => agir(
                adminApi.definirUniciteBase(table.nom, {
                  colonnes: v ? [v] : [],
                  contrainte: cleNaturelle?.nom,
                }),
                v ? `« ${v} » est désormais l'identifiant naturel.`
                  : t("Contrainte d'unicité retirée."))}
            />
          </div>
          {cleNaturelle && (
            <span style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
              actuellement : {cleNaturelle.colonnes.join(" + ")}
            </span>
          )}
        </div>
      </div>

      {message && <div style={{ fontSize: 12.5, color: "var(--accent)", marginTop: 14 }}>{message}</div>}
      {erreur && <div style={{ fontSize: 12.5, color: "var(--brick)", marginTop: 14 }}>{erreur}</div>}

      {edition && (
        <DialogueModifierColonne
          colonne={edition}
          table={table}
          tables={tables}
          types={types}
          onClose={() => setEdition(null)}
          onValider={async (structure, reglage) => {
            if (structure) await adminApi.modifierColonneBase(table.nom, edition.nom, structure);
            if (reglage) {
              await adminApi.reglerColonneBase(
                table.nom, structure?.nouveau_nom || edition.nom, reglage);
            }
            setEdition(null);
            recharger();
          }}
        />
      )}

      {ajout && (
        <DialogueColonne
          types={types}
          onClose={() => setAjout(false)}
          onValider={async (donnees) => {
            await adminApi.ajouterColonneBase(table.nom, donnees);
            setAjout(false);
            recharger();
          }}
        />
      )}

      {suppression && (
        <ConfirmerSuppression
          intitule={`la colonne « ${suppression.colonne.nom} »`}
          consequences={[
            {
              nature: "suppression",
              libelle: suppression.impact.valeurs_remplies > 0
                ? `${suppression.impact.valeurs_remplies} valeur(s) seront perdues`
                : t("Aucune valeur n'y est saisie"),
              precision: t("la colonne et son contenu disparaissent de la table"),
            },
            ...(suppression.impact.pointe_une_table ? [{
              nature: "detachement",
              libelle: `La liaison vers « ${suppression.impact.pointe_une_table} » sera défaite`,
            }] : []),
            ...(suppression.impact.est_unique ? [{
              nature: "avertissement",
              libelle: t("C'est l'identifiant naturel de la table"),
              precision: t("plus rien n'empêchera deux lignes identiques"),
            }] : []),
          ]}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={async () => {
            await adminApi.supprimerColonneBase(table.nom, suppression.colonne.nom);
            setSuppression(null);
            recharger();
          }}
        />
      )}
    </Modal>
  );
}

/** Renommer, changer le type, rendre obligatoire, ou pointer une autre table. */
function DialogueModifierColonne({ colonne, table, tables, types, onClose, onValider }) {
  const [nom, setNom] = useState(colonne.nom);
  const [type, setType] = useState(colonne.type_logique || "texte");
  const [obligatoire, setObligatoire] = useState(!colonne.nullable);
  const [libelle, setLibelle] = useState(colonne.libelle || "");
  const [source, setSource] = useState(colonne.source_table || "");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState(null);

  const autres = (tables || []).filter((autre) => autre.nom !== table.nom);

  async function valider(e) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      const structure = (nom !== colonne.nom || type !== (colonne.type_logique || "texte")
                         || obligatoire !== !colonne.nullable)
        ? { nouveau_nom: nom !== colonne.nom ? nom : null, type, obligatoire } : null;
      const reglage = (libelle !== (colonne.libelle || "") || source !== (colonne.source_table || ""))
        ? { libelle: libelle || null, source_table: source || null } : null;
      await onValider(structure, reglage);
    } catch (e2) {
      setErreur(e2.message);
      setEnvoi(false);
    }
  }

  return (
    <Modal titre={`Colonne « ${colonne.nom} »`} onClose={onClose} width={470}>
      <form onSubmit={valider}>
        <label style={champStyle}>{t("Nom technique")}</label>
        <input value={nom} onChange={(e) => setNom(e.target.value)} style={inputStyle} />

        <label style={{ ...champStyle, marginTop: 12 }}>{t("Intitulé lisible")}</label>
        <input value={libelle} onChange={(e) => setLibelle(e.target.value)}
               placeholder={colonne.nom} style={inputStyle} />

        <label style={{ ...champStyle, marginTop: 12 }}>Type</label>
        <Liste valeur={type} ariaLabel="Type"
               options={(types || []).map((nomType) => ({ valeur: nomType, libelle: nomType }))}
               onChange={setType} />

        <label style={{ ...champStyle, marginTop: 12 }}>{t("Pointe une autre table")}</label>
        <Liste
          valeur={source}
          ariaLabel={t("Table pointée")}
          placeholder={t("— Aucune (texte libre) —")}
          options={[{ valeur: "", libelle: t("— Aucune (texte libre) —") },
                    ...autres.map((autre) => ({ valeur: autre.nom, libelle: autre.libelle }))]}
          onChange={setSource}
        />
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5, marginTop: 6 }}>
          {t("La saisie devient alors une liste de choix, et la valeur enregistrée est la ligne pointée : l'affichage suit son nom, même quand celui-ci change. Les textes déjà saisis ne sont pas des identifiants — le serveur dira combien sont à reprendre.")}
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14, fontSize: 12.5 }}>
          <input type="checkbox" checked={obligatoire}
                 onChange={(e) => setObligatoire(e.target.checked)} />
          Valeur obligatoire
        </label>

        {erreur && (
          <div style={{
            marginTop: 12, padding: "8px 11px", borderRadius: "var(--radius)",
            background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5,
          }}>
            {erreur}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <button type="button" onClick={onClose} style={boutonSecondaireModal}>Annuler</button>
          <button type="submit" disabled={envoi} style={boutonPrimaire}>
            {envoi ? "Enregistrement…" : "Enregistrer"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function etiquette(couleur) {
  return {
    marginLeft: 6, fontSize: 10.5, color: couleur,
    border: `1px solid ${couleur}`, borderRadius: 8, padding: "0 6px",
  };
}

/** Liste des lignes d'une autre table, pour une colonne qui la pointe (§18.32). */
function ChoixLie({ source, valeur, onChange, obligatoire }) {
  const [options, setOptions] = useState(null);
  const [recherche, setRecherche] = useState("");

  useEffect(() => {
    let annule = false;
    const minuterie = setTimeout(() => {
      api.references(source, recherche)
        .then((lignes) => { if (!annule) setOptions(lignes); })
        .catch(() => { if (!annule) setOptions([]); });
    }, recherche ? 180 : 0);
    return () => { annule = true; clearTimeout(minuterie); };
  }, [source, recherche]);

  return (
    <Liste
      recherchable
      valeur={String(valeur ?? "")}
      ariaLabel={`Choisir dans ${source}`}
      placeholder={options ? "— Choisir —" : "Chargement…"}
      options={[
        ...(obligatoire ? [] : [{ valeur: "", libelle: t("— Aucun —") }]),
        ...(options || []).map((o) => ({
          valeur: String(o.valeur),
          libelle: o.complement ? `${t(o.libelle)} — ${o.complement}` : o.libelle,
        })),
      ]}
      onRecherche={setRecherche}
      onChange={(v) => onChange(v)}
    />
  );
}

function LigneTable({ table, actif, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 6, width: "100%", textAlign: "left",
        border: "none", borderLeft: actif ? "3px solid var(--accent)" : "3px solid transparent",
        background: actif ? "var(--accent-soft)" : "transparent", color: "var(--ink)",
        padding: "5px 8px", fontSize: 12, borderRadius: 2,
      }}
    >
      {!table.modifiable && <Lock size={10} color="var(--ink-faint)" style={{ flexShrink: 0 }} />}
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {t(table.libelle)}
      </span>
      <span className="tabular" style={{ fontSize: 10, color: "var(--ink-faint)" }}>{table.nb_lignes}</span>
    </button>
  );
}

function EnTete({ libelle, action }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-faint)" }}>{libelle}</span>
      <div style={{ flex: 1 }} />
      {action}
    </div>
  );
}

function DialogueTable({ types, onClose, onValider }) {
  const [nom, setNom] = useState("");
  const [libelle, setLibelle] = useState("");
  const [description, setDescription] = useState("");
  const [colonnes, setColonnes] = useState([{ nom: "", type: "texte", obligatoire: false }]);
  const [envoi, setEnvoi] = useState(false);

  async function soumettre(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      await onValider({ nom, libelle, description, colonnes: colonnes.filter((c) => c.nom.trim()) });
    } catch {
      setEnvoi(false);
    }
  }

  return (
    <Modal titre={t("Nouvelle table de données")} onClose={onClose} width={520}>
      <form onSubmit={soumettre}>
        <label style={champStyle}>{t("Intitulé")}</label>
        <input required autoFocus value={libelle} onChange={(e) => setLibelle(e.target.value)}
               placeholder={t("ex : Véhicules")} style={inputStyle} />

        <label style={champStyle}>{t("Nom technique")}</label>
        <input required value={nom} onChange={(e) => setNom(e.target.value)}
               placeholder="ex : vehicules" style={{ ...inputStyle, fontFamily: "var(--font-mono)" }} />
        <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 4 }}>
          Minuscules, chiffres et soulignés. La table sera créée sous le nom{" "}
          <code>usr_{nom || "…"}</code> — le préfixe <code>usr_</code> distingue les données
          du foyer des tables du fonctionnement, préfixées <code>sys_</code> — et recevra
          automatiquement une colonne <code>id</code>.
        </div>

        <label style={champStyle}>{t("Description (facultative)")}</label>
        <input value={description} onChange={(e) => setDescription(e.target.value)} style={inputStyle} />

        <label style={{ ...champStyle, marginBottom: 8 }}>Colonnes</label>
        {colonnes.map((c, i) => (
          <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6, alignItems: "center" }}>
            <input
              value={c.nom}
              onChange={(e) => setColonnes(colonnes.map((x, j) => (j === i ? { ...x, nom: e.target.value } : x)))}
              placeholder="nom_colonne"
              style={{ ...inputStyle, marginTop: 0, flex: 1, fontFamily: "var(--font-mono)" }}
            />
            <Liste
              compact
              valeur={c.type}
              ariaLabel={t("Type de la colonne")}
              style={{ width: 130 }}
              options={types.map((nomType) => ({ valeur: nomType, libelle: nomType }))}
              onChange={(v) => setColonnes(colonnes.map((x, j) => (j === i ? { ...x, type: v } : x)))}
            />
            <label style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4, color: "var(--ink-soft)" }}>
              <input
                type="checkbox"
                checked={c.obligatoire}
                onChange={(e) => setColonnes(colonnes.map((x, j) => (j === i ? { ...x, obligatoire: e.target.checked } : x)))}
              />
              requis
            </label>
            {colonnes.length > 1 && (
              <button type="button" onClick={() => setColonnes(colonnes.filter((_, j) => j !== i))} style={boutonIcone}>
                <Trash2 size={12} />
              </button>
            )}
          </div>
        ))}
        <button type="button" onClick={() => setColonnes([...colonnes, { nom: "", type: "texte", obligatoire: false }])}
                style={{ ...boutonMinuscule, marginTop: 4 }}>
          <Plus size={12} />
          Ajouter une colonne
        </button>

        <button type="submit" disabled={envoi} style={boutonPrimaire}>
          {envoi ? t("Création…") : t("Créer la table")}
        </button>
      </form>
    </Modal>
  );
}

function DialogueColonne({ types, onClose, onValider }) {
  const [nom, setNom] = useState("");
  const [type, setType] = useState("texte");
  const [envoi, setEnvoi] = useState(false);

  return (
    <Modal titre={t("Ajouter une colonne")} onClose={onClose} width={420}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setEnvoi(true);
          try { await onValider({ nom, type, obligatoire: false }); } catch { setEnvoi(false); }
        }}
      >
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12, color: "var(--ink-soft)" }}>
          <AlertTriangle size={14} color="var(--amber)" style={{ flexShrink: 0, marginTop: 2 }} />
          <span>
            {t("Seul l'ajout est possible : modifier ou retirer une colonne existante détruirait les valeurs déjà saisies.")}
          </span>
        </div>
        <label style={champStyle}>Nom</label>
        <input required autoFocus value={nom} onChange={(e) => setNom(e.target.value)}
               style={{ ...inputStyle, fontFamily: "var(--font-mono)" }} />
        <label style={champStyle}>Type</label>
        <Liste
          valeur={type}
          ariaLabel={t("Type de la colonne à ajouter")}
          options={types.map((nomType) => ({ valeur: nomType, libelle: nomType }))}
          onChange={setType}
        />
        <button type="submit" disabled={envoi} style={boutonPrimaire}>
          {envoi ? "Ajout…" : "Ajouter"}
        </button>
      </form>
    </Modal>
  );
}

function DialogueLigne({ colonnes, ligne, onClose, onValider }) {
  const modifiables = colonnes.filter((c) => c.nom !== "id" && !c.masquee);
  const [valeurs, setValeurs] = useState(() =>
    Object.fromEntries(modifiables.map((c) => [c.nom, ligne[c.nom] ?? ""]))
  );
  const [envoi, setEnvoi] = useState(false);

  return (
    <Modal titre={ligne.id ? `Modifier la ligne nº${ligne.id}` : t("Nouvelle ligne")} onClose={onClose} width={460}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setEnvoi(true);
          try { await onValider(valeurs); } catch { setEnvoi(false); }
        }}
      >
        {modifiables.map((c) => (
          <div key={c.nom}>
            <label style={champStyle}>
              {c.libelle || c.nom}
              <span style={{ color: "var(--ink-faint)", fontWeight: 400 }}>
                {" · "}{c.source_table ? `liée à ${c.source_table}` : c.type_logique || c.type}
              </span>
            </label>
            {c.source_table ? (
              // Colonne liée (§18.32) : on choisit une ligne de l'autre table,
              // on ne tape pas un identifiant. C'est tout l'intérêt de la
              // liaison — le texte libre ne désignait personne.
              <ChoixLie
                source={c.source_table}
                valeur={valeurs[c.nom] ?? ""}
                obligatoire={!c.nullable}
                onChange={(v) => setValeurs({ ...valeurs, [c.nom]: v })}
              />
            ) : (
              <input
                value={valeurs[c.nom] ?? ""}
                onChange={(e) => setValeurs({ ...valeurs, [c.nom]: e.target.value })}
                type={/date/i.test(c.type) ? "date" : /int|decimal/i.test(c.type) ? "number" : "text"}
                step={/decimal/i.test(c.type) ? "0.01" : undefined}
                required={!c.nullable}
                style={inputStyle}
              />
            )}
          </div>
        ))}
        <button type="submit" disabled={envoi} style={boutonPrimaire}>
          {envoi ? "Enregistrement…" : "Enregistrer"}
        </button>
      </form>
    </Modal>
  );
}

const thStyle = {
  textAlign: "left", padding: "7px 10px", fontSize: 11, fontWeight: 600,
  color: "var(--ink-soft)", background: "var(--bg-panel-alt)",
  borderBottom: "1px solid var(--line)", whiteSpace: "nowrap",
};

const tdStyle = { padding: "6px 10px", verticalAlign: "top", maxWidth: 280, wordBreak: "break-word" };

const boutonMinuscule = {
  display: "flex", alignItems: "center", gap: 4,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "3px 9px", fontSize: 11,
};

const boutonIcone = {
  border: "none", background: "transparent", color: "var(--ink-faint)", padding: "2px 4px",
};

const cadreRecherche = {
  display: "flex", alignItems: "center", gap: 6, marginBottom: 10,
  border: "1px solid var(--line)", background: "var(--bg-panel)",
  borderRadius: "var(--radius)", padding: "5px 9px", maxWidth: 340,
};
