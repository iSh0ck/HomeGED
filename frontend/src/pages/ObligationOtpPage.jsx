import React from "react";
import { LogOut, ShieldAlert } from "lucide-react";
import AppairageOtp, { texteAide } from "../components/AppairageOtp.jsx";
import { t } from "../lib/langue";

/**
 * Écran d'appairage obligatoire.
 *
 * Il ne s'affiche que dans une situation : un administrateur exige la double
 * authentification, le compte vient de se connecter, elle n'est pas en place.
 * Rien d'autre ne lui est accessible.
 *
 * Cet écran ne montre donc **que** cela. Afficher la page « Mon compte »
 * complète — avec son formulaire de mot de passe — réclamait un mot de passe à
 * quelqu'un qui venait de le taper pour entrer, et noyait la seule action
 * possible au milieu d'options qui ne l'étaient pas.
 *
 * La seule autre issue est de partir : le bouton déconnecte et ramène à l'écran
 * de connexion. Un « Retour » n'aurait ici aucun sens — il n'y a rien derrière.
 */
export default function ObligationOtpPage({ nom, onLogout }) {
  return (
    <div style={{
      minHeight: "100dvh", background: "var(--bg-app)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "40px 20px",
    }}>
      <div className="apparition" style={{
        width: "100%", maxWidth: 560, background: "var(--bg-panel)",
        border: "1px solid var(--line)", borderTop: "3px solid var(--amber)",
        borderRadius: "var(--radius)",
        boxShadow: "0 18px 44px -22px rgba(34, 40, 31, 0.45)",
        padding: "26px 28px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ShieldAlert size={20} color="var(--amber)" />
          <h1 style={{ fontSize: 18 }}>{t("Sécurisation de votre compte")}</h1>
        </div>

        <p style={{ ...texteAide, marginTop: 10 }}>
          {nom ? `Bonjour ${nom}. ` : ""}
          Votre mot de passe a bien été accepté. Un administrateur demande en outre que
          ce compte soit protégé par un code à usage unique : c'est la dernière étape
          avant d'accéder à vos documents, et elle ne se fait qu'une fois.
        </p>

        <div style={{ height: 1, background: "var(--line)", margin: "18px 0" }} />

        <AppairageOtp demarrerImmediatement onTermine={() => window.location.reload()} />

        <div style={{ height: 1, background: "var(--line)", margin: "20px 0 14px" }} />

        <button
          onClick={onLogout}
          style={{
            display: "flex", alignItems: "center", gap: 6,
            border: "none", background: "transparent", color: "var(--ink-faint)",
            fontSize: 12, padding: 0, cursor: "pointer", textDecoration: "underline",
          }}
        >
          <LogOut size={12} />
          {t("Revenir à l'écran de connexion")}
        </button>
      </div>
    </div>
  );
}
