import React, { useState } from "react";
import { AlertTriangle, Check, Download, Lock, Package } from "lucide-react";
import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext.jsx";
import { t } from "../../lib/langue";

/**
 * Export complet de l'archive (§17.30).
 *
 * L'écran énonce ce que contient le fichier produit et ce qu'il implique avant
 * de le produire. Ce n'est pas de la prudence de façade : une fois téléchargé,
 * ce fichier contient tous les documents du foyer et échappe à l'application —
 * il n'y a plus ni droits, ni journal, ni verrou.
 *
 * D'où le mot de passe redemandé, le second facteur s'il est actif, et le
 * téléchargement unique. Ce dernier point est le plus visible à l'usage :
 * l'écran le dit avant, pendant et après.
 */
export default function ExportAdmin() {
  const { user } = useAuth();
  const [motDePasse, setMotDePasse] = useState("");
  const [code, setCode] = useState("");
  const [preparation, setPreparation] = useState(false);
  const [pret, setPret] = useState(null);       // { jeton, documents, taille_octets, ... }
  const [erreur, setErreur] = useState(null);
  const [fait, setFait] = useState(false);

  async function demander(evenement) {
    evenement.preventDefault();
    setPreparation(true);
    setErreur(null);
    try {
      setPret(await api.demanderExport(motDePasse, code));
      setMotDePasse("");
      setCode("");
    } catch (e) {
      setErreur(e.message);
    } finally {
      setPreparation(false);
    }
  }

  async function telecharger() {
    setErreur(null);
    try {
      await api.telechargerExport(pret.jeton, "homeged-export.zip");
      setFait(true);
      setPret(null);
    } catch (e) {
      setErreur(e.message);
    }
  }

  return (
    <div style={{ maxWidth: 640 }}>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.6, marginBottom: 16 }}>
        L'export produit une archive <code>.zip</code> contenant <strong>tous les documents
        du foyer</strong>, rangés selon leur classement — un dossier par catégorie et
        sous-catégorie. Elle se dépose telle quelle sur un serveur de fichiers et reste
        utilisable sans HomeGED. Un fichier <code>index.csv</code> l'accompagne, avec ce
        qu'un dossier ne sait pas dire : émetteur, dates, statut et champs extraits.
      </p>

      <div style={{
        display: "flex", gap: 10, padding: "12px 14px", marginBottom: 18,
        background: "var(--amber-soft)", border: "1px solid var(--amber)",
        borderRadius: "var(--radius)",
      }}>
        <AlertTriangle size={17} color="var(--amber)" style={{ flexShrink: 0, marginTop: 1 }} />
        <div style={{ fontSize: 12.5, lineHeight: 1.55 }}>
          Une fois téléchargée, cette archive n'est plus protégée par rien : ni droits
          d'accès, ni journal, ni verrou. Elle ne se télécharge donc
          <strong> qu'une seule fois</strong>, et s'efface d'elle-même si personne ne la
          récupère dans la demi-heure.
        </div>
      </div>

      {fait && !pret && (
        <div style={{
          display: "flex", gap: 8, alignItems: "center", marginBottom: 18,
          padding: "10px 13px", background: "var(--accent-soft)", color: "var(--accent)",
          borderRadius: "var(--radius)", fontSize: 12.5,
        }}>
          <Check size={15} />
          {t("Archive téléchargée. Le lien ne vaut plus rien : pour en obtenir une autre, refaites la demande ci-dessous.")}
        </div>
      )}

      {erreur && (
        <div style={{
          marginBottom: 16, padding: "10px 13px", borderRadius: "var(--radius)",
          background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5,
        }}>
          {erreur}
        </div>
      )}

      {pret ? (
        <div style={{
          border: "1px solid var(--accent)", borderRadius: "var(--radius)", padding: 18,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8 }}>
            <Package size={17} color="var(--accent)" />
            <strong style={{ fontSize: 14 }}>{t("Archive prête")}</strong>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55 }}>
            {pret.documents} document{pret.documents > 1 ? "s" : ""} · {formaterTaille(pret.taille_octets)}
            {pret.absents > 0 && (
              <span style={{ color: "var(--amber)" }}>
                {" "}· {pret.absents} PDF introuvable{pret.absents > 1 ? "s" : ""} sur le disque,
                signalé{pret.absents > 1 ? "s" : ""} dans l'archive
              </span>
            )}
          </div>
          <button onClick={telecharger} style={{
            display: "flex", alignItems: "center", gap: 7, marginTop: 14,
            border: "none", background: "var(--accent)", color: "#fff",
            borderRadius: "var(--radius)", padding: "9px 16px", fontSize: 13,
            fontWeight: 600, cursor: "pointer",
          }}>
            <Download size={15} />
            {t("Télécharger — une seule fois")}
          </button>
        </div>
      ) : (
        <form onSubmit={demander} style={{ maxWidth: 340 }}>
          <label style={etiquette}>{t("Votre mot de passe")}</label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={motDePasse}
            onChange={(e) => setMotDePasse(e.target.value)}
            style={champ}
          />

          {user?.otp_actif && (
            <>
              <label style={etiquette}>{t("Code de double authentification")}</label>
              <input
                required
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="000000"
                style={{ ...champ, fontFamily: "var(--font-mono)", letterSpacing: "0.2em" }}
              />
            </>
          )}

          <button type="submit" disabled={preparation || !motDePasse} style={{
            display: "flex", alignItems: "center", gap: 7, marginTop: 16,
            border: "none", background: "var(--accent)", color: "#fff",
            borderRadius: "var(--radius)", padding: "9px 16px", fontSize: 13,
            fontWeight: 600, cursor: "pointer",
            opacity: preparation || !motDePasse ? 0.6 : 1,
          }}>
            <Lock size={14} />
            {preparation ? t("Préparation de l'archive…") : t("Préparer l'export")}
          </button>
        </form>
      )}
    </div>
  );
}

const etiquette = {
  display: "block", fontSize: 12, color: "var(--ink-soft)", marginTop: 14, marginBottom: 4,
};

const champ = {
  width: "100%", padding: "8px 10px", fontSize: 13,
  border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)", color: "var(--ink)", fontFamily: "inherit",
};

function formaterTaille(octets) {
  if (!octets) return "0 o";
  if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} Ko`;
  if (octets < 1024 * 1024 * 1024) return `${(octets / (1024 * 1024)).toFixed(1)} Mo`;
  return `${(octets / (1024 * 1024 * 1024)).toFixed(2)} Go`;
}
