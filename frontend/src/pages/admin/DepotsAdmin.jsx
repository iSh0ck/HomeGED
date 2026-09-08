import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FolderX, FileWarning, RefreshCw, Trash2 } from "lucide-react";
import { adminApi } from "../../api";
import Liste from "../../components/champs/Liste.jsx";
import { aplatirArborescence } from "../../lib/arborescence";
import { formaterHorodatage } from "../../lib/horodatage";
import { t } from "../../lib/langue";

/**
 * Emplacements non valides du dépôt (§19.5).
 *
 * Le dépôt appartient à la GED : elle y tient un dossier par type de document,
 * et la racine est fermée en écriture pour que personne n'y crée quoi que ce
 * soit. Mais aucune permission ne tient contre un partage monté en écriture
 * totale ou un dépôt fait par root — **ce qui ne peut pas être interdit doit
 * être visible**. Cet écran est l'autre moitié du dispositif, pas un repli.
 *
 * Chaque ligne dit ce qu'il faut pour décider sans aller voir sur le serveur :
 * le chemin, la taille, la date, et la raison pour laquelle cette entrée pose
 * problème.
 */
const RAISONS = () => ({
  dossier_inconnu: {
    icone: FolderX,
    libelle: t("Dossier qu'aucun type ne réclame"),
    aide: t("Créé à la main, ou laissé par un type de document supprimé — la GED ne garde pas trace des seconds, et deviner serait pire que de le dire. Rien n'y est lu tant qu'il n'appartient à aucun type."),
  },
  hors_dossier_de_type: {
    icone: FileWarning,
    libelle: t("Fichier dans un dossier inconnu"),
    aide: t("Il attend dans un dossier que personne ne réclame. Rangez-le dans un type de document : il redevient un dépôt ordinaire."),
  },
  racine: {
    icone: FileWarning,
    libelle: t("Fichier à la racine du dépôt"),
    aide: t("En général transitoire : la surveillance l'attrape et en fait une tâche « à classer ». S'il est encore là, c'est qu'elle ne l'a pas vu."),
  },
  extension_non_traitee: {
    icone: FileWarning,
    libelle: t("Format non traité"),
    aide: t("Le serveur ne sait pas lire ce format : il resterait ici indéfiniment, sans tâche ni message. Le ranger ailleurs ne changerait rien — il n'y a qu'à le retirer."),
  },
});

export default function DepotsAdmin() {
  const [racine, setRacine] = useState("");
  const [entrees, setEntrees] = useState([]);
  const [categories, setCategories] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(null);
  const [choix, setChoix] = useState({});

  const charger = useCallback(() => {
    setChargement(true);
    adminApi.anomaliesDepot()
      .then((reponse) => {
        setRacine(reponse.racine);
        setEntrees(reponse.entrees || []);
      })
      .catch((e) => setErreur(e.message))
      .finally(() => setChargement(false));
  }, []);

  useEffect(() => {
    charger();
    adminApi.categories()
      .then((toutes) => setCategories(toutes.filter((c) => (c.nature || "type") !== "dossier")))
      .catch(() => {});
  }, [charger]);

  async function ranger(entree) {
    const categorieId = choix[entree.chemin];
    if (!categorieId) {
      setErreur(`Choisissez le type de document pour « ${entree.nom} ».`);
      return;
    }
    setErreur(null);
    try {
      await adminApi.rangerFichierEgare(entree.chemin, Number(categorieId));
      charger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  async function retirer(entree) {
    setErreur(null);
    try {
      await adminApi.retirerDuDepot(entree.chemin);
      charger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16, lineHeight: 1.5 }}>
        Le dépôt <code>{racine}</code> appartient à la GED : elle y tient un dossier par
        type de document, et sa racine est fermée en écriture pour que personne n'y crée
        rien. Aucune permission ne tient pourtant contre un partage ouvert en écriture
        totale ou un dépôt fait par l'administrateur du système —{" "}
        <strong>ce qui ne peut pas être interdit doit au moins se voir</strong>. Cette
        page montre ce qui traîne, et permet de le ranger ou de le retirer.
      </p>

      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <button
          onClick={charger}
          disabled={chargement}
          style={{
            display: "flex", alignItems: "center", gap: 6,
            border: "1px solid var(--line-strong)", background: "transparent",
            color: "var(--ink-soft)", borderRadius: "var(--radius)",
            padding: "5px 11px", fontSize: 12.5,
          }}
        >
          <RefreshCw size={13} />
          Actualiser
        </button>
      </div>

      {erreur && (
        <div style={{ color: "var(--brick)", fontSize: 12, marginBottom: 12 }}>{erreur}</div>
      )}

      {chargement ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Lecture du dépôt…")}</div>
      ) : entrees.length === 0 ? (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
          padding: "50px 16px", color: "var(--ink-faint)",
        }}>
          <CheckCircle2 size={28} color="var(--accent)" />
          <div style={{ fontSize: 14, color: "var(--ink)" }}>{t("Le dépôt est en ordre.")}</div>
          <div style={{ fontSize: 12 }}>
            {t("Rien à la racine, et aucun dossier qui n'appartienne à un type de document.")}
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {entrees.map((entree) => {
            const raison = RAISONS()[entree.raison] || RAISONS().racine;
            const Icone = raison.icone;
            return (
              <div
                key={entree.chemin}
                style={{
                  border: "1px solid var(--line)", borderLeft: "3px solid var(--amber)",
                  borderRadius: "var(--radius)", background: "var(--bg-panel)", padding: 12,
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
                  <Icone size={15} color="var(--amber)" style={{ flexShrink: 0, marginTop: 2 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <code style={{ fontFamily: "var(--font-mono)", fontSize: 12.5 }}>
                      {entree.chemin}
                    </code>
                    <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 3 }}>
                      {t(raison.libelle)}
                      {entree.dossier && entree.contient > 0 &&
                        ` · ${entree.contient} fichier(s)`}
                      {entree.taille_octets != null &&
                        ` · ${Math.max(1, Math.round(entree.taille_octets / 1024))} Ko`}
                      {entree.date && ` · ${formaterHorodatage(entree.date)}`}
                    </div>
                    <div style={{ fontSize: 11.5, color: "var(--ink-soft)", marginTop: 5,
                                  lineHeight: 1.45 }}>
                      {t(raison.aide)}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginTop: 10,
                              flexWrap: "wrap" }}>
                  {entree.traitable && (
                    <>
                      <div style={{ width: 240 }}>
                        <Liste
                          recherchable
                          valeur={choix[entree.chemin] || ""}
                          ariaLabel={`Type de document pour ${entree.nom}`}
                          placeholder={t("— Ranger dans —")}
                          options={aplatirArborescence(categories).map((c) => ({
                            valeur: c.id,
                            libelle: `${" ".repeat(c.profondeur * 3)}${c.nom}`,
                          }))}
                          onChange={(v) => setChoix({ ...choix, [entree.chemin]: v })}
                        />
                      </div>
                      <button
                        onClick={() => ranger(entree)}
                        style={{
                          background: "var(--accent)", color: "#fff", border: "none",
                          borderRadius: "var(--radius)", padding: "6px 13px", fontSize: 12.5,
                          fontWeight: 500,
                        }}
                      >
                        Ranger
                      </button>
                    </>
                  )}
                  <div style={{ flex: 1 }} />
                  <button
                    onClick={() => retirer(entree)}
                    title={entree.dossier
                      ? t("Supprimer ce dossier (seulement s'il est vide)")
                      : t("Mettre ce fichier à la corbeille")}
                    style={{
                      display: "flex", alignItems: "center", gap: 5,
                      border: "1px solid var(--brick)", background: "transparent",
                      color: "var(--brick)", borderRadius: "var(--radius)",
                      padding: "5px 11px", fontSize: 12.5,
                    }}
                  >
                    <Trash2 size={12} />
                    {entree.dossier ? t("Supprimer le dossier") : t("Mettre à la corbeille")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 18, fontSize: 11.5,
                    color: "var(--ink-faint)", lineHeight: 1.5 }}>
        <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
        <span>
          {t("Un fichier mis à la corbeille n'est pas détruit : il y reste récupérable le temps de la rétention. Ce qui traîne ici a pu y arriver par erreur, et la destruction se décide en connaissance de cause.")}
        </span>
      </div>
    </div>
  );
}
