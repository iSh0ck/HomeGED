import React, { useEffect, useState } from "react";
import { ArrowLeft, Bell, CalendarClock, Check, FileText } from "lucide-react";
import { api } from "../api";
import { formaterHorodatage, ilYA } from "../lib/horodatage";
import { versFrancais } from "../components/champs/dates";
import { t } from "../lib/langue";

/**
 * Les échéances et les rappels (§21.9).
 *
 * Le besoin le plus concret d'une maison : contrôle technique, assurance,
 * garantie, échéance de facture. Le document porte la date ; ce qui manquait,
 * c'est que quelqu'un la regarde avant qu'elle ne passe.
 *
 * Deux listes, et l'ordre compte : ce qui **arrive** d'abord, ce dont on a
 * **déjà été prévenu** ensuite. Un rappel lu par quelqu'un l'est pour tout le
 * monde — c'est un tableau d'affichage, pas une boîte aux lettres.
 */
export default function EcheancesPage({ onRetour, onOuvrirDocument, onChangement }) {
  const [echeances, setEcheances] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [erreur, setErreur] = useState(null);

  function charger() {
    api.echeances().then((r) => setEcheances(r.echeances || []))
      .catch((e) => setErreur(e.message));
    api.notifications().then((r) => setNotifications(r.notifications || []))
      .catch(() => {});
  }
  useEffect(charger, []);

  async function marquerLue(notification) {
    try {
      await api.marquerNotificationLue(notification.id);
      charger();
      onChangement?.();
    } catch (e) {
      setErreur(e.message);
    }
  }

  async function toutMarquer() {
    await api.toutMarquerLu();
    charger();
    onChangement?.();
  }

  return (
    <div style={{ padding: "20px 26px", overflowY: "auto", flex: 1 }} className="scrollbar-thin">
      <button
        onClick={onRetour}
        style={{ display: "flex", alignItems: "center", gap: 6, border: "none",
                 background: "transparent", color: "var(--accent)", fontSize: 12.5,
                 padding: 0, marginBottom: 14, cursor: "pointer" }}
      >
        <ArrowLeft size={14} />
        Retour au registre
      </button>

      <h2 style={{ fontSize: 16, marginBottom: 4 }}>{t("Échéances et rappels")}</h2>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55,
                  maxWidth: 660, marginBottom: 20 }}>
        {t("Ce qui arrive à terme, la plus urgente d'abord. Un champ devient une échéance quand l'administration le déclare comme tel sur son type de document — c'est le foyer qui décide de quel champ il s'agit, et combien de jours à l'avance il veut être prévenu.")}
      </p>

      {erreur && (
        <div style={{ fontSize: 12.5, color: "var(--brick)", marginBottom: 12 }}>{erreur}</div>
      )}

      <Titre icone={CalendarClock}>{t("Ce qui arrive")}</Titre>
      {echeances === null ? (
        <Vide>{t("Chargement…")}</Vide>
      ) : echeances.length === 0 ? (
        <Vide>
          {t("Aucune échéance en vue. Si vous en attendiez, vérifiez qu'un champ est bien déclaré « échéance » dans les champs attendus de son type.")}
        </Vide>
      ) : (
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                      overflow: "hidden", marginBottom: 24 }}>
          {echeances.map((e, index) => (
            <button
              key={`${e.document_id}-${e.champ}`}
              onClick={() => onOuvrirDocument?.(e.document_id)}
              style={{
                display: "flex", alignItems: "center", gap: 12, width: "100%",
                textAlign: "left", padding: "10px 14px", border: "none",
                borderBottom: index < echeances.length - 1 ? "1px solid var(--line)" : "none",
                background: "transparent", color: "var(--ink)", cursor: "pointer",
              }}
            >
              <FileText size={14} color="var(--ink-faint)" style={{ flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13 }}>
                  {e.categorie || "Document"}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
                  {e.libelle_champ} au {versFrancais(e.date)} · {e.nom_fichier}
                </div>
              </div>
              <span style={{
                fontSize: 12, fontWeight: 600, whiteSpace: "nowrap",
                color: e.passee ? "var(--brick)" : e.jours <= 7 ? "var(--amber)"
                  : "var(--ink-soft)",
              }}>
                {e.passee
                  ? `dépassée de ${Math.abs(e.jours)} j`
                  : e.jours === 0 ? "aujourd'hui" : `dans ${e.jours} j`}
              </span>
            </button>
          ))}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Titre icone={Bell}>{t("Rappels reçus")}</Titre>
        <div style={{ flex: 1 }} />
        {notifications.some((n) => !n.lue) && (
          <button onClick={toutMarquer}
                  style={{ border: "1px solid var(--line-strong)", background: "transparent",
                           color: "var(--ink-soft)", borderRadius: "var(--radius)",
                           padding: "4px 10px", fontSize: 12, cursor: "pointer" }}>
            {t("Tout marquer comme lu")}
          </button>
        )}
      </div>

      {notifications.length === 0 ? (
        <Vide>{t("Aucun rappel pour l'instant.")}</Vide>
      ) : (
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                      overflow: "hidden" }}>
          {notifications.map((n, index) => (
            <div
              key={n.id}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                borderBottom: index < notifications.length - 1
                  ? "1px solid var(--line)" : "none",
                background: n.lue ? "transparent" : "var(--bg-panel-alt)",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: n.lue ? 400 : 600 }}>{t(n.titre)}</div>
                {n.message && (
                  <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>{t(n.message)}</div>
                )}
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}
                     title={formaterHorodatage(n.date)}>
                  {ilYA(n.date)}
                  {n.pour_le_foyer && <>{" · "}{t("pour le foyer")}</>}
                </div>
              </div>
              {n.document_id && (
                <button onClick={() => onOuvrirDocument?.(n.document_id)}
                        style={lien}>{t("Voir le document")}</button>
              )}
              {!n.lue && (
                <button onClick={() => marquerLue(n)} style={lien} title={t("Marquer comme lu")}>
                  <Check size={13} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Titre({ icone: Icone, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8,
                  fontSize: 13, fontWeight: 600 }}>
      <Icone size={15} color="var(--ink-faint)" />
      {children}
    </div>
  );
}

function Vide({ children }) {
  return (
    <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginBottom: 20,
                  lineHeight: 1.5, maxWidth: 560 }}>
      {children}
    </div>
  );
}

const lien = {
  display: "inline-flex", alignItems: "center", gap: 4, border: "none",
  background: "transparent", color: "var(--accent)", fontSize: 12, padding: 0,
  cursor: "pointer", flexShrink: 0,
};

/** Le bouton d'accès, avec son compteur : un rappel qu'on ne voit pas ne sert à rien. */
export function BoutonRappels({ nombre = 0, onClick }) {
  return (
    <button
      onClick={onClick}
      title={nombre ? `${nombre} rappel(s) non lu(s)` : t("Échéances et rappels")}
      style={{
        display: "flex", alignItems: "center", gap: 6, background: "transparent",
        color: nombre ? "var(--amber)" : "var(--ink-soft)",
        border: `1px solid ${nombre ? "var(--amber)" : "var(--line-strong)"}`,
        borderRadius: "var(--radius)", padding: "7px 12px", fontSize: 13,
        fontWeight: nombre ? 600 : 400,
      }}
    >
      <Bell size={15} />
      {nombre || ""}
    </button>
  );
}
