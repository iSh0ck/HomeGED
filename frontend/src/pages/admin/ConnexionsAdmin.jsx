import React, { useEffect, useState } from "react";
import { ShieldAlert, Unlock, RefreshCw } from "lucide-react";
import { adminApi } from "../../api";
import { formaterHorodatage } from "../../lib/horodatage";
import { t, locale } from "../../lib/langue";

/**
 * Surveillance des tentatives de connexion.
 *
 * On y voit ce qui est verrouillé, ce qui approche du seuil, l'adresse d'où
 * viennent les tentatives et le compte visé — et on peut lever un verrou, par
 * exemple quand c'est un habitant du foyer qui s'est trompé cinq fois.
 *
 * Le décompte vit en mémoire de l'API : il disparaît à son redémarrage. La
 * trace durable est le journal d'audit, repris plus bas.
 */
export default function ConnexionsAdmin() {
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState(null);

  function charger() {
    adminApi.connexions().then(setDonnees).catch((e) => setErreur(e.message));
  }
  useEffect(charger, []);

  // tant qu'un verrou court, son décompte évolue : on rafraîchit doucement
  useEffect(() => {
    if (!donnees?.entrees?.some((e) => e.verrouille)) return;
    const timer = setInterval(charger, 15000);
    return () => clearInterval(timer);
  }, [donnees]);

  async function deverrouiller(cle) {
    setErreur(null);
    try {
      await adminApi.deverrouillerConnexion(cle);
      charger();
    } catch (e) {
      setErreur(e.message);
    }
  }

  async function toutDeverrouiller() {
    if (!confirm(t("Lever tous les verrous et remettre les compteurs à zéro ?"))) return;
    await adminApi.toutDeverrouiller().catch((e) => setErreur(e.message));
    charger();
  }

  if (!donnees) {
    return <div style={{ fontSize: 13, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>;
  }

  const { reglages, entrees, historique } = donnees;
  const verrouillees = entrees.filter((e) => e.verrouille);

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        Au-delà de <strong>{reglages.max_tentatives} échecs</strong> en{" "}
        {Math.round(reglages.fenetre_secondes / 60)} minutes, la source est écartée pendant{" "}
        {Math.round(reglages.verrouillage_secondes / 60)} minutes. Deux compteurs tournent en
        parallèle : l'un par couple adresse + compte, contre l'acharnement sur un compte
        précis ; l'autre par adresse seule, contre le balayage de plusieurs comptes.
      </p>

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <Compteur libelle={t("Sources verrouillées")} valeur={verrouillees.length} alerte={verrouillees.length > 0} />
        <Compteur libelle={t("Sous surveillance")} valeur={entrees.length - verrouillees.length} />
        <div style={{ flex: 1 }} />
        <button onClick={charger} style={boutonDiscret}>
          <RefreshCw size={12} />
          Rafraîchir
        </button>
        {entrees.length > 0 && (
          <button onClick={toutDeverrouiller} style={{ ...boutonDiscret, borderColor: "var(--accent)", color: "var(--accent)" }}>
            <Unlock size={12} />
            Tout déverrouiller
          </button>
        )}
      </div>

      {entrees.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-faint)", padding: "18px 0" }}>
          {t("Aucune tentative infructueuse en cours. Tout va bien.")}
        </div>
      ) : (
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={thStyle}>{t("État")}</th>
                <th style={thStyle}>Adresse</th>
                <th style={thStyle}>{t("Compte visé")}</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Tentatives</th>
                <th style={thStyle}>{t("Dernière")}</th>
                <th style={{ ...thStyle, width: 130 }} />
              </tr>
            </thead>
            <tbody>
              {entrees.map((e) => (
                <tr key={e.cle} style={{ borderTop: "1px solid var(--line)" }}>
                  <td style={tdStyle}>
                    {e.verrouille ? (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--brick)", fontWeight: 600 }}>
                        <ShieldAlert size={13} />
                        Verrouillée
                        <span className="tabular" style={{ color: "var(--ink-faint)", fontWeight: 400 }}>
                          {Math.ceil(e.secondes_restantes / 60)} min
                        </span>
                      </span>
                    ) : (
                      <span style={{ color: "var(--amber)" }}>
                        {e.tentatives_dans_la_fenetre}/{reglages.max_tentatives}
                      </span>
                    )}
                  </td>
                  <td style={{ ...tdStyle }} className="tabular">{e.adresse}</td>
                  <td style={tdStyle}>
                    {e.identifiant || (
                      <span style={{ color: "var(--ink-faint)" }}>
                        plusieurs comptes
                      </span>
                    )}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right" }} className="tabular">{e.tentatives}</td>
                  <td style={tdStyle} className="tabular">
                    {new Date(e.derniere * 1000).toLocaleTimeString(locale())}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>
                    <button onClick={() => deverrouiller(e.cle)} style={boutonDiscret}>
                      <Unlock size={12} />
                      Débloquer
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 style={{ fontSize: 14, marginTop: 28, marginBottom: 8 }}>
        {t("Verrouillages enregistrés")}
      </h3>
      <p style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 0, marginBottom: 10 }}>
        {t("Extrait du journal d'audit : contrairement au tableau ci-dessus, cet historique survit aux redémarrages de l'API.")}
      </p>
      {historique.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>{t("Aucun verrouillage à ce jour.")}</div>
      ) : (
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)", overflow: "hidden" }}>
          {historique.map((h, i) => (
            <div
              key={i}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "6px 12px",
                fontSize: 12, borderTop: i ? "1px solid var(--line)" : "none",
              }}
            >
              <span className="tabular" style={{ color: "var(--ink-faint)" }}>
                {formaterHorodatage(h.date)}
              </span>
              <span className="tabular">{h.adresse}</span>
              <span style={{ color: "var(--ink-soft)" }}>{h.identifiant}</span>
            </div>
          ))}
        </div>
      )}

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}
    </div>
  );
}

function Compteur({ libelle, valeur, alerte }) {
  return (
    <div
      style={{
        border: "1px solid " + (alerte ? "var(--brick)" : "var(--line)"),
        background: alerte ? "var(--brick-soft)" : "var(--bg-panel)",
        borderRadius: "var(--radius)", padding: "6px 14px",
      }}
    >
      <div className="tabular" style={{ fontSize: 18, fontWeight: 600, color: alerte ? "var(--brick)" : "var(--ink)" }}>
        {valeur}
      </div>
      <div style={{ fontSize: 10, color: "var(--ink-faint)" }}>{libelle}</div>
    </div>
  );
}

const thStyle = {
  textAlign: "left", padding: "7px 10px", fontSize: 11, fontWeight: 600,
  color: "var(--ink-soft)", background: "var(--bg-panel-alt)",
  borderBottom: "1px solid var(--line)", whiteSpace: "nowrap",
};
const tdStyle = { padding: "6px 10px", verticalAlign: "middle" };
const boutonDiscret = {
  display: "inline-flex", alignItems: "center", gap: 5,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "3px 9px", fontSize: 11,
};
