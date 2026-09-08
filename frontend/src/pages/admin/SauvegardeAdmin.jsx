import React, { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, HardDrive, Lock, Play, Trash2 } from "lucide-react";
import { adminApi } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import { t } from "../../lib/langue";

/**
 * Copie de secours (§22.49).
 *
 * HomeGED détient **l'unique exemplaire** des papiers du foyer : la base dit
 * comment ils sont rangés, `storage/` contient les PDF. Rien ne le sauvegardait,
 * et rien ne le rappelait.
 *
 * Cet écran ne fait pas la sauvegarde — c'est le serveur de travaux qui l'exécute,
 * lui seul ayant les archives sous la main. Il dit **où l'on en est**, ce qui est
 * la seule chose qui compte : une sauvegarde qu'on croit faite et qui a cessé est
 * pire que pas de sauvegarde du tout.
 *
 * Le réglage vit dans « Réglages généraux », groupe *Sauvegarde* : rythme,
 * destination, nombre gardé, avec ou sans les archives. Rien n'est imposé.
 */
export default function SauvegardeAdmin() {
  const [etat, setEtat] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [enCours, setEnCours] = useState(false);
  const [suppression, setSuppression] = useState(null);

  function charger() {
    adminApi.sauvegardes().then(setEtat).catch((e) => setErreur(e.message));
  }
  useEffect(charger, []);

  async function sauvegarder() {
    setEnCours(true);
    setErreur(null);
    try {
      await adminApi.sauvegarderMaintenant();
      charger();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(false);
    }
  }

  if (!etat) {
    return <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>;
  }

  const alerte = etat.jamais_faite || etat.en_retard;

  return (
    <div>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55, marginTop: 0 }}>
        La sauvegarde copie <strong>la base</strong> — le classement, les champs extraits,
        les droits — et, si vous le demandez, <strong>les archives</strong> elles-mêmes.
        Elle s'écrit dans un dossier daté contenant un fichier SQL en clair : cela se
        restaure avec un client MariaDB et une copie de fichiers, sans cette application.
        Le rythme, la destination et le nombre gardé se règlent dans
        « Réglages généraux », groupe <em>Sauvegarde</em>.
      </p>

      {/* L'état d'abord, en gros : c'est la seule chose qu'on vient voir. */}
      <div style={{
        display: "flex", alignItems: "flex-start", gap: 12, padding: "14px 16px",
        borderRadius: "var(--radius)", marginBottom: 16,
        border: `1px solid ${alerte ? "var(--amber)" : "var(--line)"}`,
        background: alerte ? "var(--amber-soft)" : "var(--bg-panel-alt)",
      }}>
        {alerte ? <AlertTriangle size={18} color="var(--amber)" style={{ flexShrink: 0 }} />
          : <CheckCircle2 size={18} color="var(--accent)" style={{ flexShrink: 0 }} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600,
                        color: alerte ? "var(--amber)" : "var(--ink)" }}>
            {etat.jamais_faite
              ? t("Aucune sauvegarde n'a jamais été faite")
              : etat.en_retard
                ? `Dernière sauvegarde le ${lisible(etat.derniere.date)} — au-delà du délai réglé`
                : `Dernière sauvegarde le ${lisible(etat.derniere.date)}`}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 4, lineHeight: 1.5 }}>
            {etat.active
              ? `Sauvegarde automatique toutes les ${etat.heures} h, ${etat.garder} gardées, `
                + `${etat.avec_archives ? "archives comprises" : "base seule"}.`
              : t("La sauvegarde automatique est éteinte. Vous pouvez en déclencher une ici, mais rien ne se fera tout seul.")}
            {" "}Dossier : <code style={{ fontFamily: "var(--font-mono)" }}>{etat.dossier}</code>.
            {etat.espace_libre != null
              && ` ${octets(etat.espace_libre)} libres sur ce disque.`}
          </div>
          {etat.jamais_faite && (
            <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 6, lineHeight: 1.5 }}>
              {t("Cette application détient l'unique exemplaire de vos documents. Une copie sur le même disque protège d'une fausse manœuvre, pas d'une panne : montez un disque externe ou un partage réseau, et indiquez son chemin dans les réglages.")}
            </div>
          )}
        </div>
        <button onClick={sauvegarder} disabled={enCours} style={boutonPrincipal}>
          <Play size={13} />
          {enCours ? t("Sauvegarde en cours…") : t("Sauvegarder maintenant")}
        </button>
      </div>

      {erreur && (
        <div style={{ color: "var(--brick)", fontSize: 12.5, marginBottom: 12 }}>{erreur}</div>
      )}

      <div style={{ display: "flex", gap: 18, fontSize: 12, color: "var(--ink-soft)",
                    marginBottom: 12 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <Database size={13} /> {etat.nombre} sauvegarde(s) complète(s)
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <HardDrive size={13} /> {octets(etat.octets_total)} occupés
        </span>
      </div>

      <AdminTable
        cle="sauvegardes"
        colonnes={[
          { key: "nom", label: "Sauvegarde" },
          { key: "date", label: t("Faite le"), render: (s) => lisible(s.date) },
          { key: "octets", label: "Taille", render: (s) => octets(s.octets) },
          { key: "complete", label: t("État"), render: (s) => (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ color: s.complete ? "var(--accent)" : "var(--amber)" }}>
                {s.complete ? t("complète") : t("interrompue")}
              </span>
              {/* Une archive chiffrée ne se restaure pas de la même façon
                  (§22.65) : il faut le mot de passe, et le dire ici évite de
                  l'apprendre le jour où l'on en a besoin. */}
              {s.chiffree && (
                <span title={t("Chiffrée : sa restauration demande le mot de passe réglé plus haut")}
                      style={{ display: "inline-flex", alignItems: "center", gap: 3,
                               color: "var(--ink-faint)", fontSize: 11 }}>
                  <Lock size={10} />
                  {t("chiffrée")}
                </span>
              )}
            </span>
          ) },
          { key: "actions", label: "", render: (s) => (
            <button onClick={() => setSuppression(s)} title={t("Effacer cette sauvegarde")}
                    style={{ border: "none", background: "transparent",
                             color: "var(--ink-faint)", cursor: "pointer" }}>
              <Trash2 size={13} />
            </button>
          ) },
        ]}
        lignes={etat.sauvegardes}
      />

      {suppression && (
        <ConfirmerSuppression
          typeObjet="sauvegarde"
          identifiant={suppression.nom}
          intitule={t("la sauvegarde du {date}", { date: lisible(suppression.date) })}
          consequences={[{
            nature: "suppression",
            libelle: t("{taille} effacés définitivement", { taille: octets(suppression.octets) }),
            precision: t("une sauvegarde effacée ne se retrouve pas : c'est une copie, pas un document de la GED"),
          }]}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={async () => {
            await adminApi.supprimerSauvegarde(suppression.nom);
            setSuppression(null);
            charger();
          }}
        />
      )}
    </div>
  );
}

function lisible(iso) {
  if (!iso) return "—";
  const [jour, heure] = String(iso).split("T");
  const [a, m, j] = jour.split("-");
  return `${j}/${m}/${a} à ${(heure || "").slice(0, 5)}`;
}

function octets(nombre) {
  if (nombre == null) return "—";
  const unites = ["o", "Ko", "Mo", "Go", "To"];
  let valeur = nombre;
  let rang = 0;
  while (valeur >= 1024 && rang < unites.length - 1) {
    valeur /= 1024;
    rang += 1;
  }
  return `${valeur < 10 && rang > 0 ? valeur.toFixed(1) : Math.round(valeur)} ${unites[rang]}`;
}

const boutonPrincipal = {
  display: "inline-flex", alignItems: "center", gap: 6, flexShrink: 0,
  border: "1px solid var(--line-strong)", background: "var(--bg-panel)",
  color: "var(--ink)", borderRadius: "var(--radius)", padding: "7px 13px",
  fontSize: 12.5, cursor: "pointer", fontFamily: "inherit",
};
