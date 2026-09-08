import React, { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { api } from "../api";
import { t } from "../lib/langue";

/**
 * Appairage d'une application d'authentification, en deux temps : on scanne,
 * on confirme par un premier code, puis on note les codes de secours.
 *
 * Partagé par les deux endroits où l'on met en place une double
 * authentification — volontairement depuis « Mon compte », ou parce qu'un
 * administrateur l'exige. Le geste est le même ; seul le cadre change.
 *
 * `demarrerImmediatement` évite un clic quand l'écran n'existe que pour ça :
 * quand la mise en place est obligatoire, proposer un bouton « Mettre en
 * place » sur une page qui ne propose rien d'autre serait une politesse inutile.
 */
export default function AppairageOtp({ demarrerImmediatement = false, onTermine, onAnnuler }) {
  const [preparation, setPreparation] = useState(null);
  const [codesSecours, setCodesSecours] = useState(null);
  const [code, setCode] = useState("");
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  async function preparer() {
    setErreur(null);
    setEnvoi(true);
    try {
      setPreparation(await api.preparerOtp());
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnvoi(false);
    }
  }

  useEffect(() => {
    if (demarrerImmediatement) preparer();
  }, [demarrerImmediatement]);

  async function activer() {
    setErreur(null);
    setEnvoi(true);
    try {
      const reponse = await api.activerOtp(code);
      setPreparation(null);
      setCode("");
      setCodesSecours(reponse.codes);
    } catch (e) {
      setErreur(e.message);
      setCode("");
    } finally {
      setEnvoi(false);
    }
  }

  // --- dernier écran : les codes de secours, montrés une seule fois
  if (codesSecours) {
    return (
      <div>
        <p style={texteAide}>
          Notez-les maintenant, hors de cet ordinateur. Ils ne sont conservés que sous
          forme hachée : <strong>personne ne pourra vous les réafficher</strong>, pas même
          un administrateur. Chacun ouvre une session une fois, si votre téléphone n'est
          plus à portée.
        </p>
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
          gap: 8, margin: "14px 0",
        }}>
          {codesSecours.map((c) => (
            <code key={c} style={{
              fontFamily: "var(--font-mono)", fontSize: 13, letterSpacing: "0.04em",
              background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
              borderRadius: "var(--radius)", padding: "7px 9px", textAlign: "center",
            }}>{c}</code>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <BoutonCopier texte={codesSecours.join("\n")} />
          <button onClick={() => { setCodesSecours(null); onTermine?.(); }} style={boutonPrimaire}>
            <Check size={13} /> Je les ai notés
          </button>
        </div>
      </div>
    );
  }

  // --- appairage : le QR, la clé, et le premier code
  if (preparation) {
    return (
      <div>
        <p style={texteAide}>
          {t("Ouvrez votre application d'authentification (Google Authenticator, Aegis, Bitwarden, 1Password…) et scannez ce code. Elle affichera alors six chiffres, renouvelés toutes les trente secondes.")}
        </p>
        <div style={{ display: "flex", gap: 20, marginTop: 16, flexWrap: "wrap" }}>
          {preparation.qr_svg && (
            <img src={preparation.qr_svg} alt={t("QR code d'appairage")} width={168} height={168}
                 style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                          background: "#fff", padding: 6 }} />
          )}
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
              {t("Pas d'appareil photo ? Saisissez cette clé à la main :")}
            </div>
            <code style={{
              display: "block", fontFamily: "var(--font-mono)", fontSize: 13,
              background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
              borderRadius: "var(--radius)", padding: "8px 10px", marginTop: 6,
              wordBreak: "break-all",
            }}>{preparation.secret_lisible}</code>

            <label style={{ display: "block", fontSize: 12, color: "var(--ink-soft)",
                            margin: "16px 0 4px" }}>
              {t("Code affiché par l'application")}
            </label>
            <input
              autoFocus
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              onKeyDown={(e) => { if (e.key === "Enter" && code.length === 6) activer(); }}
              placeholder="000000"
              style={{
                width: "100%", padding: "9px 10px", fontSize: 19, textAlign: "center",
                fontFamily: "var(--font-mono)", letterSpacing: "0.26em",
                border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
                background: "var(--bg-panel-alt)", color: "var(--ink)",
              }}
            />

            {erreur && <Alerte>{erreur}</Alerte>}

            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button onClick={activer} disabled={envoi || code.length !== 6}
                      style={{ ...boutonPrimaire, opacity: envoi || code.length !== 6 ? 0.55 : 1 }}>
                {envoi ? t("Vérification…") : "Activer"}
              </button>
              {onAnnuler && (
                <button onClick={() => { setPreparation(null); setCode(""); onAnnuler(); }}
                        style={boutonSecondaire}>
                  Annuler
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // --- point de départ (seulement quand la mise en place est facultative)
  return (
    <div>
      {erreur && <Alerte>{erreur}</Alerte>}
      <button onClick={preparer} disabled={envoi} style={boutonPrimaire}>
        {envoi ? t("Préparation…") : t("Mettre en place")}
      </button>
    </div>
  );
}

/**
 * Copie dans le presse-papier. `navigator.clipboard` n'existe pas hors contexte
 * sécurisé — une installation en HTTP sur le réseau local, précisément le cas
 * d'usage ici — d'où le repli sur la sélection d'un champ temporaire.
 */
export function BoutonCopier({ texte }) {
  const [copie, setCopie] = useState(false);

  function copier() {
    const marquer = () => { setCopie(true); setTimeout(() => setCopie(false), 2000); };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(texte).then(marquer).catch(() => {});
      return;
    }
    const zone = document.createElement("textarea");
    zone.value = texte;
    zone.style.position = "fixed";
    zone.style.opacity = "0";
    document.body.appendChild(zone);
    zone.select();
    try { document.execCommand("copy"); marquer(); } finally { document.body.removeChild(zone); }
  }

  return (
    <button onClick={copier} style={boutonSecondaire}>
      {copie ? <Check size={13} /> : <Copy size={13} />}
      {copie ? t("Copié") : "Copier"}
    </button>
  );
}

function Alerte({ children }) {
  return (
    <div style={{
      marginTop: 12, padding: "8px 11px", borderRadius: "var(--radius)",
      background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5, lineHeight: 1.45,
    }}>
      {children}
    </div>
  );
}

export const texteAide = { fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55 };

export const boutonPrimaire = {
  display: "flex", alignItems: "center", gap: 6, border: "none",
  background: "var(--accent)", color: "#fff", borderRadius: "var(--radius)",
  padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
};

export const boutonSecondaire = {
  display: "flex", alignItems: "center", gap: 6,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "8px 14px", fontSize: 13, cursor: "pointer",
};
