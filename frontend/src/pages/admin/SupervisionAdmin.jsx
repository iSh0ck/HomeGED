import React, { useEffect, useState } from "react";
import {
  Activity, AlertTriangle, Cpu, Database, HardDrive, MemoryStick, RefreshCw, Server, Users,
} from "lucide-react";
import { adminApi } from "../../api";
import { formaterHorodatage, ilYA } from "../../lib/horodatage";
import { t, locale } from "../../lib/langue";

const RAFRAICHISSEMENT_MS = 15000;

/**
 * Supervision : ce que la machine a dans le ventre (§18.18).
 *
 * Trois questions qu'on se pose toujours trop tard — **reste-t-il de la place**,
 * **la machine tient-elle**, **le traitement suit-il** — et un écran qui y répond
 * d'un coup d'œil. Rien n'y est modifiable : c'est un cadran, pas un tableau de
 * commande.
 *
 * Les mesures viennent du noyau (`/proc`, cgroup) et de la base, sans passer par
 * le démon Docker : lui donner accès depuis l'API reviendrait à lui confier
 * l'équivalent de root sur l'hôte, prix déraisonnable pour afficher des
 * pourcentages. Conséquence assumée : la mémoire et le processeur sont ceux de
 * **la machine entière**, pas d'un conteneur en particulier ; ce qui concerne le
 * serveur de travaux se lit dans sa file, ce qui concerne la base dans sa taille.
 */
export default function SupervisionAdmin() {
  const [etat, setEtat] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);

  useEffect(() => {
    let vivant = true;
    function relever() {
      adminApi.supervision()
        .then((d) => { if (vivant) { setEtat(d); setErreur(null); } })
        .catch((e) => { if (vivant) setErreur(e.message); })
        .finally(() => { if (vivant) setChargement(false); });
    }
    relever();
    // Un cadran qui ne bouge pas ne sert à rien : on relève régulièrement, sans
    // que personne ait à cliquer.
    const minuterie = setInterval(relever, RAFRAICHISSEMENT_MS);
    return () => { vivant = false; clearInterval(minuterie); };
  }, []);

  if (chargement) return <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Relevé en cours…")}</div>;
  if (erreur) return <div style={{ fontSize: 13, color: "var(--brick)" }}>{erreur}</div>;
  if (!etat) return null;

  const disque = etat.disques?.archives || {};
  const alertes = [];
  if (disque.pourcentage >= 90) {
    alertes.push(`Le disque des archives est occupé à ${disque.pourcentage} % — il reste ${octets(disque.libre)}.`);
  } else if (disque.pourcentage >= 80) {
    alertes.push(`Le disque des archives approche de la saturation (${disque.pourcentage} %).`);
  }
  if (etat.travaux?.en_erreur > 0) {
    alertes.push(`${etat.travaux.en_erreur} traitement(s) en erreur : voir le serveur de travaux.`);
  }
  if (etat.machine?.memoire?.pourcentage >= 90) {
    alertes.push(`La mémoire de la machine est occupée à ${etat.machine.memoire.pourcentage} %.`);
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16, lineHeight: 1.55 }}>
        Relevé de la machine et du service, en lecture seule, actualisé toutes les
        {" "}{RAFRAICHISSEMENT_MS / 1000} secondes. La mémoire et le processeur sont ceux de
        la machine entière : l'API ne dispose pas d'un accès au démon Docker — le lui donner
        équivaudrait à lui confier les droits d'administration de l'hôte, pour afficher des
        pourcentages.
      </p>

      {alertes.length > 0 && (
        <div style={{
          display: "flex", flexDirection: "column", gap: 6, marginBottom: 16,
          padding: "10px 12px", borderRadius: "var(--radius)",
          background: "var(--amber-soft)", border: "1px solid var(--amber)",
        }}>
          {alertes.map((texte, i) => (
            <div key={i} style={{ display: "flex", gap: 8, fontSize: 12.5, color: "var(--ink)" }}>
              <AlertTriangle size={14} color="var(--amber)" style={{ flexShrink: 0, marginTop: 1 }} />
              {texte}
            </div>
          ))}
        </div>
      )}

      <div style={grille}>
        <Cadran
          icone={HardDrive}
          titre="Disque"
          valeur={`${disque.pourcentage ?? "?"} %`}
          jauge={disque.pourcentage}
          detail={`${octets(disque.libre)} libres sur ${octets(disque.total)}`}
          bas={`Archives : ${octets(etat.disques?.archives?.poids)} · Exports : ${octets(etat.disques?.exports?.poids)}`}
        />
        <Cadran
          icone={MemoryStick}
          titre={t("Mémoire")}
          valeur={`${etat.machine?.memoire?.pourcentage ?? "?"} %`}
          jauge={etat.machine?.memoire?.pourcentage}
          detail={`${octets(etat.machine?.memoire?.utilisee)} sur ${octets(etat.machine?.memoire?.total)}`}
          bas={`API : ${octets(etat.api?.memoire?.utilisee)}`}
        />
        <Cadran
          icone={Cpu}
          titre="Processeur"
          valeur={`${etat.machine?.cpu?.pourcentage ?? "?"} %`}
          jauge={etat.machine?.cpu?.pourcentage}
          detail={`${etat.machine?.cpu?.coeurs ?? "?"} cœurs`}
          bas={etat.machine?.cpu?.charge
            ? `Charge : ${etat.machine.cpu.charge.map((c) => c.toFixed(2)).join(" · ")}`
            : null}
        />
        <Cadran
          icone={Database}
          titre={t("Base de données")}
          valeur={octets(etat.base?.octets)}
          detail={etat.base?.version || ""}
          bas={etat.base?.tables?.length
            ? `Plus grosse table : ${etat.base.tables[0].nom} (${octets(etat.base.tables[0].octets)})`
            : null}
        />
        <Cadran
          icone={Server}
          titre="Traitements"
          valeur={`${etat.travaux?.en_attente ?? 0} en attente`}
          detail={etat.travaux?.en_erreur ? `${etat.travaux.en_erreur} en erreur` : t("Aucune erreur")}
          alerte={etat.travaux?.en_erreur > 0}
          bas={etat.travaux?.dernier_traitement
            ? `Dernier : ${ilYA(etat.travaux.dernier_traitement)}`
            : t("Aucun traitement encore")}
        />
        <Cadran
          icone={Activity}
          titre="Documents"
          valeur={String(etat.documents?.total ?? 0)}
          detail={`${octets(etat.documents?.octets)} archivés`}
          bas={`${etat.documents?.recents ?? 0} déposés ce mois-ci · ${etat.documents?.a_comprimer ?? 0} à comprimer`}
        />
        <Cadran
          icone={Users}
          titre={t("Activité")}
          valeur={`${etat.activite?.sessions_ouvertes ?? 0} session(s)`}
          detail={`${etat.activite?.comptes_actifs ?? 0} compte(s) actif(s)`}
          bas={`${etat.activite?.evenements_journal ?? 0} événements au journal`}
        />
      </div>

      {etat.base?.tables?.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-soft)", marginBottom: 8 }}>
            {t("Ce qui pèse dans la base")}
          </div>
          <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
            {etat.base.tables.map((table, i) => (
              <div key={table.nom} style={{
                display: "flex", alignItems: "center", gap: 10, padding: "7px 12px", fontSize: 12.5,
                borderBottom: i < etat.base.tables.length - 1 ? "1px solid var(--line)" : "none",
              }}>
                <code style={{ flex: 1, color: "var(--ink-soft)" }}>{table.nom}</code>
                <span className="tabular" style={{ color: "var(--ink-faint)" }}>
                  ~{table.lignes.toLocaleString(locale())} lignes
                </span>
                <span className="tabular" style={{ width: 80, textAlign: "right", color: "var(--ink)" }}>
                  {octets(table.octets)}
                </span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 6 }}>
            {t("Le nombre de lignes est celui qu'estime le moteur : il approche, il ne compte pas.")}
          </div>
        </div>
      )}

      <div style={{
        display: "flex", alignItems: "center", gap: 6, marginTop: 16,
        fontSize: 11.5, color: "var(--ink-faint)",
      }}>
        <RefreshCw size={12} />
        Relevé du {formaterHorodatage(etat.instant)}
        {etat.machine?.uptime_secondes != null && ` · API démarrée ${duree(etat.machine.uptime_secondes)}`}
      </div>
    </div>
  );
}

function Cadran({ icone: Icone, titre, valeur, detail, bas, jauge, alerte }) {
  const couleur = alerte || jauge >= 90 ? "var(--brick)"
                : jauge >= 80 ? "var(--amber)" : "var(--accent)";
  return (
    <div style={{
      padding: "12px 14px", borderRadius: "var(--radius)",
      background: "var(--bg-panel)", border: "1px solid var(--line)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
        <Icone size={14} color="var(--ink-faint)" />
        <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-soft)" }}>{titre}</span>
      </div>
      <div style={{ fontSize: 20, fontWeight: 600, color: couleur }} className="tabular">{valeur}</div>
      {detail && <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 2 }}>{detail}</div>}
      {jauge != null && (
        <div style={{ height: 3, borderRadius: 2, background: "var(--line)", marginTop: 8 }}>
          <div style={{
            height: "100%", borderRadius: 2, background: couleur,
            width: `${Math.min(100, Math.max(0, jauge))}%`, transition: "width 400ms",
          }} />
        </div>
      )}
      {bas && <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 8 }}>{bas}</div>}
    </div>
  );
}

const grille = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
  gap: 12,
};

function octets(valeur) {
  if (valeur == null) return "—";
  if (valeur < 1024) return `${valeur} o`;
  if (valeur < 1024 * 1024) return `${Math.round(valeur / 1024)} Ko`;
  if (valeur < 1024 * 1024 * 1024) return `${(valeur / (1024 * 1024)).toFixed(1)} Mo`;
  return `${(valeur / (1024 * 1024 * 1024)).toFixed(2)} Go`;
}

function duree(secondes) {
  if (secondes < 60) return t("il y a moins d'une minute");
  const minutes = Math.round(secondes / 60);
  if (minutes < 60) return `il y a ${minutes} min`;
  const heures = Math.round(minutes / 60);
  if (heures < 48) return `il y a ${heures} h`;
  return `il y a ${Math.round(heures / 24)} jours`;
}
