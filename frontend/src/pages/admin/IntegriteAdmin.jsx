import React, { useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, FileX, RefreshCw } from "lucide-react";
import { adminApi } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import { formaterHorodatage, ilYA } from "../../lib/horodatage";
import { t } from "../../lib/langue";

/**
 * L'intégrité des archives (§21.3).
 *
 * Une empreinte était posée à l'import, et personne ne la revérifiait jamais.
 * Une archive familiale est pourtant censée durer vingt ans : un disque se
 * dégrade, une synchronisation se trompe de sens, un programme écrit là où il ne
 * devait pas. Rien de cela ne prévient — on s'en aperçoit le jour où l'on ouvre
 * le document, c'est-à-dire le jour où l'on en a besoin.
 *
 * Le contrôle tourne tout seul, quelques fichiers par cycle. Cet écran dit ce
 * qu'il a trouvé, et permet de le relancer tout de suite — après un disque
 * remplacé ou une sauvegarde restaurée, on veut savoir maintenant.
 */
export default function IntegriteAdmin() {
  const [etat, setEtat] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [enCours, setEnCours] = useState(false);
  const [bilan, setBilan] = useState(null);

  function charger() {
    adminApi.integrite().then(setEtat).catch((e) => setErreur(e.message));
  }
  useEffect(charger, []);

  async function controler() {
    setEnCours(true);
    setErreur(null);
    setBilan(null);
    try {
      setBilan(await adminApi.controlerIntegrite());
      charger();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.55,
                  marginBottom: 16, maxWidth: 680 }}>
        {t("Chaque fichier archivé porte l'empreinte de son contenu. Le serveur de travaux en relit quelques-uns à chaque cycle — les moins récemment contrôlés d'abord — et signale ceux qui ne correspondent plus. Un disque qui se dégrade ne prévient pas, et une archive qu'on ne relit jamais n'est pas une archive.")}
      </p>

      {etat && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
          <Chiffre icone={ShieldCheck} valeur={etat.conformes} libelle="conformes"
                   couleur="var(--accent)" />
          <Chiffre icone={ShieldAlert} valeur={etat.alterees} libelle={t("altérées")}
                   couleur={etat.alterees ? "var(--brick)" : "var(--ink-faint)"} />
          <Chiffre icone={FileX} valeur={etat.absents} libelle="fichiers absents"
                   couleur={etat.absents ? "var(--brick)" : "var(--ink-faint)"} />
          <Chiffre icone={RefreshCw} valeur={etat.jamais_controles}
                   libelle={t("jamais contrôlées")} couleur="var(--ink-faint)" />
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
        <button onClick={controler} disabled={enCours} style={bouton}>
          <RefreshCw size={14} className={enCours ? "rotation" : undefined} />
          {enCours ? t("Contrôle en cours…") : t("Contrôler maintenant")}
        </button>
        {etat?.dernier_controle && (
          <span style={{ fontSize: 12, color: "var(--ink-faint)" }}
                title={formaterHorodatage(etat.dernier_controle)}>
            Dernier contrôle {ilYA(etat.dernier_controle)}
          </span>
        )}
      </div>

      {bilan && (
        <div style={{ fontSize: 12.5, color: "var(--ink-soft)", marginBottom: 14 }}>
          {bilan.controles} archive{bilan.controles > 1 ? "s" : ""} vérifiée
          {bilan.controles > 1 ? "s" : ""}
          {bilan.adoptees > 0 && (
            <>, {bilan.adoptees} empreinte{bilan.adoptees > 1 ? "s" : ""} de référence
            posée{bilan.adoptees > 1 ? "s" : ""} pour la première fois — celles-là n'ont
            pas été vérifiées, elles viennent d'être prises comme point de départ</>
          )}
          {bilan.anomalies.length > 0
            ? `, ${bilan.anomalies.length} anomalie(s).`
            : t(", aucune anomalie.")}
        </div>
      )}

      {erreur && (
        <div style={{ fontSize: 12.5, color: "var(--brick)", marginBottom: 12 }}>{erreur}</div>
      )}

      <h3 style={{ fontSize: 14, marginBottom: 8 }}>Anomalies</h3>
      {etat && etat.anomalies.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>
          Aucune archive altérée. {etat.jamais_controles > 0 && (
            <>Il reste {etat.jamais_controles} document(s) que le contrôle n'a pas encore
            atteint : il y viendra, quelques-uns par cycle.</>
          )}
        </div>
      ) : (
        <AdminTable
          lignes={etat?.anomalies || []}
          colonnes={[
            { key: "nom_fichier", label: "Document" },
            { key: "categorie", label: "Classement",
              render: (a) => a.categorie || <span style={{ color: "var(--ink-faint)" }}>—</span> },
            { key: "libelle_etat", label: t("État"),
              render: (a) => (
                <span style={{ color: "var(--brick)", fontWeight: 500 }}>{a.libelle_etat}</span>
              ) },
            { key: "chemin", label: "Fichier",
              render: (a) => (
                <code style={{ fontSize: 11, color: "var(--ink-faint)" }}>{a.chemin}</code>
              ) },
            { key: "date_controle", label: t("Constaté le"),
              render: (a) => (
                <span className="tabular">{formaterHorodatage(a.date_controle)}</span>
              ) },
          ]}
        />
      )}

      {etat?.anomalies.length > 0 && (
        <p style={{ fontSize: 12.5, color: "var(--ink-soft)", marginTop: 14,
                    lineHeight: 1.55, maxWidth: 680 }}>
          Une archive altérée n'est pas forcément perdue : reprenez le fichier depuis une
          sauvegarde, ou redéposez le document — il deviendra une nouvelle version, et
          l'ancienne empreinte cessera de faire foi. Un fichier absent vient souvent d'un
          déplacement à la main dans <code>storage/</code>.
        </p>
      )}
    </div>
  );
}

function Chiffre({ icone: Icone, valeur, libelle, couleur }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: "9px 14px",
      border: "1px solid var(--line)", borderRadius: "var(--radius)",
      background: "var(--bg-panel)", minWidth: 132,
    }}>
      <Icone size={16} color={couleur} />
      <div>
        <div className="tabular" style={{ fontSize: 16, fontWeight: 600, color: couleur }}>
          {valeur}
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-faint)" }}>{libelle}</div>
      </div>
    </div>
  );
}

const bouton = {
  display: "inline-flex", alignItems: "center", gap: 6,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "7px 13px", fontSize: 12.5, cursor: "pointer",
};
