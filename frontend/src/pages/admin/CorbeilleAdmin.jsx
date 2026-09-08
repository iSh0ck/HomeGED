import React, { useEffect, useState } from "react";
import { Download, Trash2, AlertTriangle, HardDrive, RotateCcw } from "lucide-react";
import { adminApi } from "../../api";
import { formaterHorodatage } from "../../lib/horodatage";
import AdminTable from "../../components/AdminTable.jsx";
import Modal from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import { t } from "../../lib/langue";
import Pagination from "../../components/Pagination.jsx";

/**
 * Les deux corbeilles de l'administration.
 *
 * **Les documents supprimés** (§21.1) d'abord : ceux que quelqu'un a jetés,
 * y compris ceux qu'il a ensuite retirés de sa propre corbeille. C'est le second
 * filet, celui qui rattrape le geste de trop, et le seul endroit d'où l'on efface
 * pour de bon.
 *
 * **Les fichiers orphelins** ensuite : quand un document disparaît pour de bon,
 * son PDF n'est pas détruit — le serveur de travaux le déplace ici au passage
 * suivant. On peut encore le récupérer ; sa destruction reste une décision
 * humaine. Deux filets, parce que ces gestes-là ne se défont pas.
 */
export default function CorbeilleAdmin() {
  const [fichiers, setFichiers] = useState([]);
  // Paginée (§22.90) : le dossier entier partait dans la réponse, et quelques
  // milliers de fichiers en attente de destruction faisaient un écran lent.
  // `total` et `octets` portent sur la corbeille entière — c'est ce qu'on vient
  // y chercher, pas ce que la page contient.
  const [total, setTotal] = useState(0);
  const [octetsTotal, setOctetsTotal] = useState(0);
  const [parPage, setParPage] = useState(25);
  const [decalage, setDecalage] = useState(0);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [vidage, setVidage] = useState(false);
  const [suppression, setSuppression] = useState(null);
  const [enCours, setEnCours] = useState(false);
  const [stockage, setStockage] = useState(null);

  function charger() {
    setChargement(true);
    adminApi
      .corbeille({ limite: parPage, decalage })
      .then((page) => {
        setFichiers(page.fichiers || []);
        setTotal(page.total || 0);
        setOctetsTotal(page.octets || 0);
      })
      .catch((e) => setErreur(e.message))
      .finally(() => setChargement(false));
  }
  useEffect(charger, [parPage, decalage]);
  useEffect(() => { adminApi.stockage().then(setStockage).catch(() => {}); }, []);

  async function telecharger(fichier) {
    setErreur(null);
    try {
      const url = await adminApi.fichierCorbeilleBlobUrl(fichier.chemin);
      const lien = document.createElement("a");
      lien.href = url;
      lien.download = fichier.nom;
      lien.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErreur(e.message);
    }
  }

  async function supprimer() {
    try {
      await adminApi.supprimerFichierCorbeille(suppression.chemin);
      charger();
    } catch (e) {
      setErreur(e.message);
    }
    setSuppression(null);
  }

  async function vider() {
    setEnCours(true);
    setErreur(null);
    try {
      await adminApi.viderCorbeille();
      setVidage(false);
      charger();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div>
      {stockage && <EtatStockage etat={stockage} />}

      <DocumentsSupprimes />

      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        Supprimer un document du registre ne détruit pas son PDF : le serveur de travaux
        le dépose ici au passage suivant, avec tout fichier de <code>storage/</code> que
        plus aucun document ne référence. Rien n'en part sans une action explicite de
        votre part — c'est le filet de sécurité de l'archive.
      </p>

      {total > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <button
            onClick={() => setVidage(true)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              border: "1px solid var(--brick)",
              background: "transparent",
              color: "var(--brick)",
              borderRadius: "var(--radius)",
              padding: "6px 12px",
              fontSize: 13,
              fontWeight: 500,
            }}
          >
            <Trash2 size={14} />
            {t("Vider la corbeille ({n})", { n: total })}
          </button>
        </div>
      )}

      {chargement ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>
      ) : (
        <AdminTable
          lignes={fichiers}
          colonnes={[
            {
              key: "nom",
              label: "Fichier",
              // Un nom et une taille ne disent pas ce qu'on détruit (§22.63).
              // Le journal garde la chaîne : d'où vient ce fichier, et de quel
              // document. Quand il ne sait rien — un fichier antérieur au
              // journal —, on le dit plutôt que de laisser une case vide.
              render: (f) => (
                <div style={{ minWidth: 0 }}>
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis",
                                whiteSpace: "nowrap" }}>{f.nom}</div>
                  <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 1 }}>
                    {f.origine === "document"
                      ? t("document « {nom} » nº{id}, détruit par {par}",
                        { nom: f.document || f.nom, id: f.document_id ?? "?",
                          par: f.par || t("par l'application") })
                      : f.origine === "orphelin"
                        ? t("fichier sans document rattaché, venu de {chemin}",
                          { chemin: f.chemin_origine })
                        : t("origine inconnue — antérieur au journal d'audit")}
                  </div>
                </div>
              ),
            },
            {
              key: "date_suppression",
              label: t("Mis en corbeille le"),
              render: (f) => (
                <span className="tabular">{formaterHorodatage(f.date_suppression)}</span>
              ),
            },
            {
              key: "taille",
              label: "Taille",
              render: (f) => <span className="tabular">{formaterTaille(f.taille)}</span>,
            },
            {
              key: "chemin",
              label: t("Récupérer"),
              render: (f) => (
                <button
                  onClick={() => telecharger(f)}
                  title={t("Télécharger avant destruction")}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    border: "1px solid var(--line-strong)",
                    background: "transparent",
                    color: "var(--ink-soft)",
                    borderRadius: "var(--radius)",
                    padding: "3px 9px",
                    fontSize: 12,
                  }}
                >
                  <Download size={12} />
                  Télécharger
                </button>
              ),
            },
          ]}
          onSupprimer={setSuppression}
        />
      )}

      {!chargement && total > 0 && (
        <Pagination
          total={total}
          parPage={parPage}
          decalage={decalage}
          onDecalage={setDecalage}
          // Changer le nombre par page renvoie au début : rester au même
          // décalage ferait atterrir ailleurs que là où on croit être.
          onParPage={(n) => { setParPage(n); setDecalage(0); }}
        />
      )}

      {!chargement && total === 0 && (
        <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 10 }}>
          {t("La corbeille est vide.")}
        </div>
      )}

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {suppression && (
        <ConfirmerSuppression
          intitule={`le fichier « ${suppression.nom} »`}
          consequences={[
            {
              nature: "suppression",
              libelle: `${formaterTaille(suppression.taille)} détruits définitivement`,
              precision: t("la corbeille est le dernier filet : au-delà, le fichier est perdu"),
            },
            {
              nature: "avertissement",
              libelle: t("Téléchargez-le d'abord si vous n'êtes pas certain"),
              precision: t("aucun document du registre ne le référence plus"),
            },
          ]}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimer}
        />
      )}

      {vidage && (
        <Modal titre={t("Vider la corbeille ?")} onClose={() => setVidage(false)} width={420}>
          <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
            <AlertTriangle size={18} color="var(--brick)" style={{ flexShrink: 0, marginTop: 2 }} />
            <div style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.5 }}>
              {t("Les {n} fichier(s) de la corbeille", { n: total })}
              seront détruits définitivement. Il n'y a pas de retour possible : téléchargez
              d'abord ce que vous souhaitez conserver.
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 22 }}>
            <button
              onClick={() => setVidage(false)}
              style={{
                border: "1px solid var(--line-strong)",
                background: "transparent",
                color: "var(--ink-soft)",
                borderRadius: "var(--radius)",
                padding: "8px 14px",
                fontSize: 13,
              }}
            >
              Annuler
            </button>
            <button
              onClick={vider}
              disabled={enCours}
              style={{
                border: "none",
                background: "var(--brick)",
                color: "#fff",
                borderRadius: "var(--radius)",
                padding: "8px 14px",
                fontSize: 13,
                fontWeight: 600,
                opacity: enCours ? 0.7 : 1,
              }}
            >
              {enCours ? "Suppression…" : t("Vider définitivement")}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/**
 * État du stockage et de la compression (§17.8).
 *
 * Le chiffre qui compte n'est pas le nombre de documents mais ce qu'ils pèsent :
 * c'est le disque qui sature, pas le registre. On indique donc le poids, et où
 * en est la reprise des archives — celle-ci se fait par petits lots pendant les
 * temps morts du serveur de travaux, il est normal qu'elle prenne du temps.
 */
function EtatStockage({ etat }) {
  const restant = etat.a_reprendre > 0;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 14, marginBottom: 16,
      padding: "12px 14px", borderRadius: "var(--radius)",
      background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
    }}>
      <HardDrive size={18} color="var(--ink-faint)" style={{ flexShrink: 0 }} />
      <div style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55 }}>
        <strong style={{ color: "var(--ink)" }}>
          {formaterTaille(etat.taille_totale)}
        </strong>{" "}
        d'archives pour {etat.documents} document{etat.documents > 1 ? "s" : ""}.{" "}
        {etat.niveau > 0 ? (
          <>
            Les scans sont recompressés à l'arrivée (niveau {etat.niveau}) — sur les
            documents d'essai, 60 à 80 % de gain sans perte de texte.{" "}
            {restant ? (
              <span style={{ color: "var(--amber)" }}>
                {etat.a_reprendre} archive{etat.a_reprendre > 1 ? "s" : ""} d'avant cette
                mise en place {etat.a_reprendre > 1 ? "restent" : "reste"} à reprendre ;
                le serveur de travaux s'en occupe par {etat.lot} à la fois.
              </span>
            ) : (
              <>{t("Toutes les archives sont passées par l'optimiseur.")}</>
            )}
          </>
        ) : (
          <span style={{ color: "var(--amber)" }}>
            {t("Compression désactivée (PDF_OPTIMISATION = 0).")}
          </span>
        )}
      </div>
    </div>
  );
}

function formaterTaille(octets) {
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} Ko`;
  if (octets < 1024 * 1024 * 1024) return `${(octets / (1024 * 1024)).toFixed(1)} Mo`;
  return `${(octets / (1024 * 1024 * 1024)).toFixed(2)} Go`;
}


/**
 * Les documents mis à la corbeille, vus de l'administration (§21.1).
 *
 * La corbeille de chacun ne montre que ses propres suppressions, et plus rien
 * dès qu'il les en a retirées. Celle-ci montre tout : c'est ce qui rend le
 * second geste sans danger.
 */
function DocumentsSupprimes() {
  const [documents, setDocuments] = useState([]);
  const [erreur, setErreur] = useState(null);
  const [effacement, setEffacement] = useState(null);

  function charger() {
    adminApi.documentsSupprimes().then(setDocuments).catch((e) => setErreur(e.message));
  }
  useEffect(charger, []);

  async function restaurer(doc) {
    setErreur(null);
    try {
      await adminApi.restaurerDocumentSupprime(doc.id);
      charger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  async function effacer() {
    try {
      await adminApi.effacerDocumentDefinitivement(effacement.id);
      charger();
    } catch (e) {
      setErreur(e.message);
    }
    setEffacement(null);
  }

  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ fontSize: 14, marginBottom: 6 }}>{t("Documents supprimés")}</h3>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 12, lineHeight: 1.5 }}>
        {t("Ce que le foyer a supprimé du registre attend ici, y compris ce que chacun a retiré de sa propre corbeille. Restaurer remet le document exactement à sa place, avec ses champs et ses versions. L'effacer est définitif — seul son fichier survit un temps, plus bas, en attendant votre décision.")}
      </p>

      {erreur && (
        <div style={{ fontSize: 12.5, color: "var(--brick)", marginBottom: 10 }}>{erreur}</div>
      )}

      {documents.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>
          {t("Aucun document supprimé.")}
        </div>
      ) : (
        <AdminTable
          lignes={documents}
          colonnes={[
            { key: "nom_fichier", label: "Document" },
            { key: "categorie", label: "Classement",
              render: (d) => d.categorie || <span style={{ color: "var(--ink-faint)" }}>—</span> },
            { key: "supprime_par", label: t("Supprimé par"),
              render: (d) => (
                <>
                  {d.supprime_par || t("compte supprimé")}
                  {d.masquee && (
                    <span title={t("Retiré de sa propre corbeille : lui ne le voit plus")}
                          style={{ color: "var(--ink-faint)", fontSize: 11, marginLeft: 6 }}>
                      (retiré de sa vue)
                    </span>
                  )}
                </>
              ) },
            { key: "date_suppression", label: "Le",
              render: (d) => (
                <span className="tabular">{formaterHorodatage(d.date_suppression)}</span>
              ) },
            { key: "actions", label: "",
              render: (d) => (
                <span style={{ display: "flex", gap: 6 }}>
                  <button onClick={() => restaurer(d)} style={boutonLigne}>
                    <RotateCcw size={12} />
                    Restaurer
                  </button>
                  <button onClick={() => setEffacement(d)}
                          style={{ ...boutonLigne, color: "var(--brick)",
                                   borderColor: "var(--brick)" }}>
                    <Trash2 size={12} />
                    Effacer
                  </button>
                </span>
              ) },
          ]}
        />
      )}

      {effacement && (
        <ConfirmerSuppression
          intitule={`le document « ${effacement.nom_fichier} »`}
          consequences={[
            { libelle: t("ses champs extraits et ses versions") },
            { libelle: t("son fichier, mis de côté plus bas avant destruction") },
          ]}
          onConfirmer={effacer}
          onAnnuler={() => setEffacement(null)}
        />
      )}
    </div>
  );
}

const boutonLigne = {
  display: "inline-flex", alignItems: "center", gap: 4,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "3px 8px", fontSize: 11.5, cursor: "pointer",
};
