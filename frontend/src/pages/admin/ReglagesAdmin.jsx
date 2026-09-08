import React, { useEffect, useState } from "react";
import { Clock, Info, RotateCcw, Send } from "lucide-react";
import { adminApi } from "../../api";
import Liste from "../../components/champs/Liste.jsx";
import { definirFuseau, formaterHorodatage } from "../../lib/horodatage";
import { appliquerApparence } from "../../lib/apparence";
import { t, locale } from "../../lib/langue";

/**
 * Réglages du foyer (§18.22, §18.24).
 *
 * Ce qui vivait dans `.env` — durée d'une session, seuil de verrouillage, langue
 * de l'océrisation, résolution des scans — demandait un accès au serveur et un
 * redémarrage. Ce sont pourtant des arbitrages de foyer, pas des paramètres
 * d'installation : un foyer qui reprend l'application héritait de choix qu'il ne
 * pouvait pas revoir.
 *
 * L'écran se construit **à partir de la description rendue par l'API** : type,
 * bornes, intitulé, groupe. Ajouter un réglage ne demande donc pas une ligne de
 * code ici, et l'intitulé n'est écrit qu'une fois, du côté qui le valide.
 */
export default function ReglagesAdmin() {
  const [champs, setChamps] = useState([]);
  const [groupes, setGroupes] = useState([]);
  const [valeurs, setValeurs] = useState({});
  const [initiales, setInitiales] = useState({});
  const [fuseaux, setFuseaux] = useState([]);
  const [erreur, setErreur] = useState(null);
  const [message, setMessage] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [maintenant, setMaintenant] = useState(new Date().toISOString());
  const [ongletActif, setOngletActif] = useState(null);

  function charger() {
    adminApi.reglages().then((d) => {
      setChamps(d.champs);
      setGroupes(d.groupes || []);
      setOngletActif((actif) => actif || d.groupes?.[0]?.cle || null);
      setValeurs(d.valeurs);
      setInitiales(d.valeurs);
      setFuseaux(d.fuseaux);
    }).catch((e) => setErreur(e.message));
  }
  useEffect(charger, []);

  // L'heure courante sert d'aperçu au fuseau : c'est la seule façon de vérifier
  // d'un coup d'œil qu'on a choisi le bon.
  useEffect(() => {
    const minuterie = setInterval(() => setMaintenant(new Date().toISOString()), 30000);
    return () => clearInterval(minuterie);
  }, []);

  const modifies = Object.keys(valeurs).filter((c) => valeurs[c] !== initiales[c]);

  async function enregistrer() {
    setEnvoi(true);
    setErreur(null);
    setMessage(null);
    try {
      // On n'envoie que ce qui a changé : le reste n'a pas à être réécrit, et
      // une valeur laissée à son défaut doit le rester si le défaut évolue.
      const lot = Object.fromEntries(modifies.map((c) => [c, valeurs[c]]));
      const enregistres = await adminApi.enregistrerReglages(lot);
      setValeurs(enregistres);
      setInitiales(enregistres);
      // Ce qui change l'affichage prend effet tout de suite : demander de
      // recharger la page pour voir sa propre couleur d'accent serait bête.
      definirFuseau(enregistres.fuseau_horaire);
      appliquerApparence(enregistres);
      setMessage(t("Réglages enregistrés."));
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div style={{ maxWidth: 620 }}>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 18, lineHeight: 1.55 }}>
        Tout ce qui suit se règle par foyer. Ce qui reste dans le fichier <code>.env</code>,
        et doit y rester : les mots de passe de la base, la clé de signature, les chemins
        des volumes — des secrets et des décisions d'installation.
      </p>

      {/* Onglets horizontaux : vingt réglages d'affilée forment un mur qu'on
          parcourt sans le lire. Un compteur signale le groupe qui porte des
          changements en attente — sinon, passer d'un onglet à l'autre donnerait
          l'impression d'avoir perdu sa saisie. */}
      <div style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--line)", marginBottom: 20 }}>
        {groupes.map((groupe) => {
          const enAttente = modifies.filter(
            (c) => champs.find((champ) => champ.cle === c)?.groupe === groupe.cle).length;
          const choisi = groupe.cle === ongletActif;
          return (
            <button
              key={groupe.cle}
              onClick={() => setOngletActif(groupe.cle)}
              aria-current={choisi ? "page" : undefined}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                border: "none", background: "transparent",
                borderBottom: `2px solid ${choisi ? "var(--accent)" : "transparent"}`,
                color: choisi ? "var(--ink)" : "var(--ink-soft)",
                fontWeight: choisi ? 600 : 400,
                fontSize: 12.5, padding: "7px 13px", marginBottom: -1,
              }}
            >
              {t(groupe.libelle)}
              {enAttente > 0 && (
                <span className="tabular" style={{
                  fontSize: 10.5, fontWeight: 700, color: "#fff", background: "var(--accent)",
                  borderRadius: 8, padding: "1px 6px",
                }}>
                  {enAttente}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {groupes.map((groupe) => {
        const dedans = champs.filter((c) => c.groupe === groupe.cle);
        if (!dedans.length || groupe.cle !== ongletActif) return null;
        return (
          <section key={groupe.cle} style={{ marginBottom: 26 }}>
            <p style={{ fontSize: 12, color: "var(--ink-faint)", margin: "0 0 16px", lineHeight: 1.5 }}>
              {t(groupe.description)}
            </p>
            {dedans.map((champ) => (
              <ChampReglage
                key={champ.cle}
                champ={champ}
                valeur={valeurs[champ.cle] ?? champ.defaut}
                modifie={modifies.includes(champ.cle)}
                fuseaux={fuseaux}
                onChange={(v) => setValeurs({ ...valeurs, [champ.cle]: v })}
                onDefaut={() => setValeurs({ ...valeurs, [champ.cle]: champ.defaut })}
              />
            ))}
            {groupe.cle === "courriel" && <EssaiCourriel />}
            {groupe.cle === "foyer" && (
              <div style={apercu}>
                <Clock size={14} color="var(--ink-faint)" style={{ flexShrink: 0 }} />
                Il est actuellement{" "}
                <strong style={{ color: "var(--ink)" }}>
                  {heureDans(maintenant, valeurs.fuseau_horaire)}
                </strong>{" "}
                dans ce fuseau.
              </div>
            )}
          </section>
        );
      })}

      <div style={{
        display: "flex", gap: 9, padding: "10px 12px", borderRadius: "var(--radius)",
        background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
        fontSize: 12, color: "var(--ink-soft)", lineHeight: 1.55, marginBottom: 18,
      }}>
        <Info size={14} color="var(--ink-faint)" style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          Les dates et heures sont enregistrées en temps universel et converties à
          l'affichage : changer de fuseau ne modifie aucune donnée. Les traitements
          (langue, résolution, compression) valent pour les <strong>prochains</strong>
          {" "}dépôts — les documents déjà archivés ne sont pas repris.
          Relevé de l'interface : {formaterHorodatage(maintenant)}.
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button onClick={enregistrer} disabled={envoi || !modifies.length}
                style={{ ...boutonPrimaire, opacity: envoi || !modifies.length ? 0.5 : 1 }}>
          {envoi ? "Enregistrement…"
                 : modifies.length ? `Enregistrer (${modifies.length})` : "Enregistrer"}
        </button>
        {modifies.length > 0 && (
          <button onClick={() => setValeurs(initiales)} style={boutonSecondaire}>
            {t("Annuler les changements")}
          </button>
        )}
        {message && <span style={{ fontSize: 12.5, color: "var(--accent)" }}>{message}</span>}
        {erreur && <span style={{ fontSize: 12.5, color: "var(--brick)" }}>{erreur}</span>}
      </div>
    </div>
  );
}

/** Un réglage, dessiné d'après son type — l'API décrit, l'écran obéit. */
function ChampReglage({ champ, valeur, onChange, onDefaut, modifie, fuseaux }) {
  const options = champ.cle === "fuseau_horaire"
    ? [...new Set([...(fuseaux || []), valeur].filter(Boolean))]
    : champ.options;

  return (
    <div style={{
      marginBottom: 16, paddingLeft: 10,
      borderLeft: `2px solid ${modifie ? "var(--accent)" : "transparent"}`,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <label style={{ fontSize: 12.5, color: "var(--ink)", fontWeight: 500 }}>
          {t(champ.libelle)}
        </label>
        {modifie && (
          <button onClick={onDefaut} title={t("Revenir à la valeur d'origine")}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    border: "none", background: "transparent", color: "var(--ink-faint)",
                    fontSize: 11, padding: 0,
                  }}>
            <RotateCcw size={10} />
            défaut : {champ.defaut || "—"}
          </button>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 5, maxWidth: 340 }}>
        {champ.type === "booleen" ? (
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
            <input
              type="checkbox"
              checked={String(valeur) === "true"}
              onChange={(e) => onChange(e.target.checked ? "true" : "false")}
            />
            {String(valeur) === "true" ? t("Activé") : t("Désactivé")}
          </label>
        ) : champ.type === "choix" || champ.cle === "fuseau_horaire" ? (
          <div style={{ flex: 1 }}>
            <Liste
              recherchable={champ.cle === "fuseau_horaire" || champ.cle === "langue_ocr"}
              valeur={valeur}
              ariaLabel={t(champ.libelle)}
              // Un choix se lit par son intitulé quand il en a un (§22.70) :
              // « Date du document » plutôt que « date_document », un nom de
              // colonne que personne n'écrit et que tout le monde devinait.
              options={(options || []).map((o) => ({
                valeur: o, libelle: t(champ.libelles_options?.[o] || o),
              }))}
              onChange={onChange}
            />
          </div>
        ) : champ.type === "entier" ? (
          <>
            <input
              type="number"
              value={valeur}
              min={champ.mini ?? undefined}
              max={champ.maxi ?? undefined}
              onChange={(e) => onChange(e.target.value)}
              style={{ ...saisie, width: 110 }}
            />
            {champ.unite && (
              <span style={{ fontSize: 12, color: "var(--ink-faint)" }}>{champ.unite}</span>
            )}
          </>
        ) : champ.type === "secret" ? (
          // Un secret se règle et ne se relit pas (§21.10) : le champ montre
          // qu'il existe, et rester vide le laisse tel quel. Sans cela, on
          // retaperait le mot de passe à chaque enregistrement de l'écran — ce
          // qui pousse à le noter quelque part.
          <input
            type="password"
            value={valeur}
            autoComplete="new-password"
            placeholder={t("inchangé")}
            onChange={(e) => onChange(e.target.value)}
            style={saisie}
          />
        ) : champ.cle === "couleur_accent" ? (
          <>
            <input type="color" value={valeur} onChange={(e) => onChange(e.target.value)}
                   style={{ width: 42, height: 30, padding: 2, border: "1px solid var(--line-strong)",
                            borderRadius: "var(--radius)", background: "transparent" }} />
            <input value={valeur} onChange={(e) => onChange(e.target.value)}
                   style={{ ...saisie, width: 110 }} />
          </>
        ) : (
          <input value={valeur} onChange={(e) => onChange(e.target.value)}
                 placeholder={champ.defaut} style={saisie} />
        )}
      </div>

      <div style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5, marginTop: 5 }}>
        {t(champ.description)}
      </div>
    </div>
  );
}

function heureDans(iso, fuseau) {
  try {
    return new Intl.DateTimeFormat(locale(), {
      timeZone: fuseau || "UTC", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date(iso)).replace(":", "h");
  } catch {
    return "—";
  }
}

const apercu = {
  display: "flex", alignItems: "center", gap: 7, marginTop: 4,
  padding: "8px 11px", borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
  fontSize: 12.5, color: "var(--ink-soft)",
};

const saisie = {
  width: "100%", border: "1px solid var(--line-strong)", background: "var(--bg-panel-alt)",
  borderRadius: "var(--radius)", padding: "7px 9px", fontSize: 12.5, color: "var(--ink)",
  fontFamily: "inherit",
};

const boutonPrimaire = {
  border: "none", background: "var(--accent)", color: "#fff", fontWeight: 600,
  borderRadius: "var(--radius)", padding: "8px 16px", fontSize: 13,
};

const boutonSecondaire = {
  border: "1px solid var(--line-strong)", background: "transparent", color: "var(--ink-soft)",
  borderRadius: "var(--radius)", padding: "8px 14px", fontSize: 13,
};


/**
 * L'envoi d'essai (§21.10).
 *
 * Sans lui, on ne saurait jamais si le SMTP est correctement réglé avant la
 * première échéance — c'est-à-dire au pire moment. Le message d'erreur est celui
 * du serveur : « ça n'a pas marché » n'aide personne à régler un SMTP.
 */
function EssaiCourriel() {
  const [adresse, setAdresse] = useState("");
  const [etat, setEtat] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  async function essayer() {
    setEnvoi(true);
    setEtat(null);
    try {
      const reponse = await adminApi.essaiCourriel(adresse);
      setEtat({ ok: true, message: `Message envoyé à ${reponse.adresse}.` });
    } catch (e) {
      setEtat({ ok: false, message: e.message });
    } finally {
      setEnvoi(false);
    }
  }

  /**
   * Envoyer les résumés en attente sans attendre le cycle (§22.43).
   *
   * Le serveur savait le faire depuis le §21.10 ; il n'y avait pas de bouton.
   * C'est pourtant le geste qu'on veut après avoir réglé un SMTP : vérifier que
   * ce que le foyer recevra part bien, et à qui.
   */
  async function resumer() {
    setEnvoi(true);
    setEtat(null);
    try {
      const bilan = await adminApi.resumerCourriel();
      const envoyes = bilan?.envoyes ?? 0;
      setEtat({
        ok: true,
        message: envoyes
          ? `${envoyes} résumé(s) envoyé(s).`
          : `Aucun résumé envoyé${bilan?.raison ? ` : ${bilan.raison}` : ""}.`,
      });
    } catch (e) {
      setEtat({ ok: false, message: e.message });
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div style={{ margin: "0 0 18px", padding: "12px 14px", border: "1px solid var(--line)",
                  borderRadius: "var(--radius)", background: "var(--bg-panel-alt)" }}>
      <div style={{ fontSize: 12.5, color: "var(--ink-soft)", marginBottom: 8,
                    lineHeight: 1.5 }}>
        {t("Enregistrez d'abord les réglages, puis essayez : on veut savoir si le message part avant la première échéance, pas au moment où elle tombe.")}
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input
          value={adresse}
          placeholder={t("votre adresse (par défaut, celle du compte)")}
          aria-label={t("Adresse de destination de l'essai")}
          onChange={(e) => setAdresse(e.target.value)}
          style={{ ...saisie, width: 300 }}
        />
        <button type="button" onClick={essayer} disabled={envoi}
                style={{ display: "inline-flex", alignItems: "center", gap: 6,
                         border: "1px solid var(--line-strong)", background: "transparent",
                         color: "var(--ink-soft)", borderRadius: "var(--radius)",
                         padding: "6px 12px", fontSize: 12.5, cursor: "pointer" }}>
          <Send size={13} />
          {envoi ? "Envoi…" : t("Envoyer un essai")}
        </button>
        <button type="button" onClick={resumer} disabled={envoi}
                title={t("Envoyer maintenant les résumés d'échéances en attente, sans attendre le cycle")}
                style={{ display: "inline-flex", alignItems: "center", gap: 6,
                         border: "1px solid var(--line-strong)", background: "transparent",
                         color: "var(--ink-soft)", borderRadius: "var(--radius)",
                         padding: "6px 12px", fontSize: 12.5, cursor: "pointer" }}>
          <Send size={13} />
          {t("Envoyer les résumés en attente")}
        </button>
      </div>
      {etat && (
        <div style={{ fontSize: 12.5, marginTop: 8,
                      color: etat.ok ? "var(--accent)" : "var(--brick)" }}>
          {t(etat.message)}
        </div>
      )}
    </div>
  );
}
