import React, { useEffect, useState } from "react";
import { Check, Eye, FileText, Image, KeyRound, Laptop, Lock, LogOut, RefreshCw,
         ShieldCheck, ShieldAlert, UserRound, X } from "lucide-react";
import { api } from "../api";
import { ilYA } from "../lib/horodatage";
import { useAuth } from "../auth/AuthContext.jsx";
import AppairageOtp, {
  BoutonCopier, boutonPrimaire, boutonSecondaire, texteAide,
} from "../components/AppairageOtp.jsx";
import Modal from "../components/Modal.jsx";
import { themesDisponibles } from "../lib/apparence";
import { languesDisponibles, t } from "../lib/langue";

/**
 * Mon compte : ce que chacun règle pour lui-même.
 *
 * Deux sujets, deux encadrés : le mot de passe, et la double authentification.
 * L'écran dit à chaque fois ce que l'action entraîne — changer son mot de passe
 * referme les autres sessions, les codes de secours ne seront plus jamais
 * affichés — parce que ce sont précisément les conséquences qu'on découvre trop
 * tard quand personne ne les a écrites.
 */
export default function ComptePage({ onRetour }) {
  const { rafraichir } = useAuth();
  const [profil, setProfil] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [onglet, setOnglet] = useState("identite");

  function charger() {
    api.moi().then(setProfil).catch((e) => setErreur(e.message));
  }
  useEffect(charger, []);

  return (
    <Modal titre={t("Mon compte")} onClose={onRetour} width={560}>
      {erreur && <div style={{ color: "var(--brick)", fontSize: 12.5, marginTop: 10 }}>{erreur}</div>}

      {!profil && !erreur && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 14 }}>{t("Chargement…")}</div>
      )}

      {profil && (
        <div style={{ marginTop: 6 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13.5, fontWeight: 600 }}>{profil.nom}</span>
            <span style={{ fontSize: 12, color: "var(--ink-soft)" }}>{profil.email}</span>
          </div>

          {profil.otp_impose && !profil.otp_actif && (
            <div style={{
              display: "flex", gap: 10, alignItems: "flex-start", marginTop: 16,
              padding: "11px 13px", borderRadius: "var(--radius)",
              background: "var(--amber-soft)", border: "1px solid var(--amber)",
            }}>
              <ShieldAlert size={16} color="var(--amber)" style={{ flexShrink: 0, marginTop: 1 }} />
              <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.5 }}>
                <strong>{t("La double authentification est exigée sur ce compte.")}</strong> Tant
                qu'elle n'est pas en place, le reste de l'application vous est fermé.
              </div>
            </div>
          )}

          {/* Trois sujets sans rapport les uns avec les autres — qui je suis, comment
              je protège mon compte, d'où je suis connecté — étaient empilés sur une
              seule page qu'il fallait faire défiler. Des onglets les séparent : on
              vient ici pour une chose à la fois. */}
          <Onglets
            actif={onglet}
            onChange={setOnglet}
            entrees={[
              { id: "identite", libelle: t("Identité"), icone: UserRound },
              { id: "affichage", libelle: "Affichage", icone: Eye },
              { id: "securite", libelle: t("Sécurité"), icone: ShieldCheck,
                pastille: profil.otp_impose && !profil.otp_actif },
              { id: "appareils", libelle: "Appareils", icone: Laptop },
            ]}
          />

          <div style={{ marginTop: 16 }}>
            {onglet === "identite" && <Identite profil={profil} />}
            {onglet === "affichage" && (
              <Affichage profil={profil} onChange={() => { charger(); rafraichir(); }} />
            )}
            {onglet === "securite" && (
              <>
                <MotDePasse />
                <DoubleAuthentification profil={profil}
                                        onChange={() => { charger(); rafraichir(); }} />
              </>
            )}
            {onglet === "appareils" && <Sessions />}
          </div>
        </div>
      )}
    </Modal>
  );
}

/**
 * Onglets horizontaux de la fenêtre de compte.
 *
 * Une pastille signale l'onglet qui réclame quelque chose — la double
 * authentification exigée mais pas encore en place. Sans elle, l'avertissement
 * disparaîtrait derrière un onglet fermé, ce qui reviendrait à le supprimer.
 */
function Onglets({ entrees, actif, onChange }) {
  return (
    <div style={{
      display: "flex", gap: 2, marginTop: 18,
      borderBottom: "1px solid var(--line)",
    }}>
      {entrees.map(({ id, libelle, icone: Icone, pastille }) => {
        const choisi = id === actif;
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            aria-current={choisi ? "page" : undefined}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              border: "none", background: "transparent",
              borderBottom: `2px solid ${choisi ? "var(--accent)" : "transparent"}`,
              color: choisi ? "var(--ink)" : "var(--ink-soft)",
              fontWeight: choisi ? 600 : 400,
              fontSize: 12.5, padding: "7px 12px", marginBottom: -1,
            }}
          >
            <Icone size={13} />
            {libelle}
            {pastille && (
              <span title={t("Une action est attendue")} style={{
                width: 6, height: 6, borderRadius: "50%",
                background: "var(--amber)", flexShrink: 0,
              }} />
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Ce que l'application sait de vous, et qui le lui a dit. */
function Identite({ profil }) {
  return (
    <Encadre titre={t("Identité")} icone={UserRound}>
      <Ligne libelle={t("Nom")} valeur={profil.nom} />
      <Ligne libelle={t("Adresse e-mail")} valeur={profil.email} />
      <Ligne libelle={t("Rôle")} valeur={profil.est_admin ? "Administrateur" : "Utilisateur"} />
      {profil.roles.length > 0 && (
        <Ligne libelle={t("Groupes")} valeur={profil.roles.join(", ")} />
      )}
      {profil.date_mot_de_passe && (
        <Ligne libelle={t("Mot de passe changé")} valeur={ilYA(profil.date_mot_de_passe)} />
      )}
      <div style={{ fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.5, marginTop: 10 }}>
        {t("Ces informations sont tenues par un administrateur, depuis l'écran des comptes : un nom qu'on modifierait soi-même ne désignerait plus personne de sûr dans le journal ni sur les documents qui vous sont rattachés.")}
      </div>
    </Encadre>
  );
}

function Ligne({ libelle, valeur }) {
  if (!valeur) return null;
  return (
    <div style={{ display: "flex", gap: 10, fontSize: 12.5, padding: "3px 0" }}>
      <span style={{ width: 150, color: "var(--ink-faint)", flexShrink: 0 }}>{libelle}</span>
      <span style={{ color: "var(--ink)" }}>{valeur}</span>
    </div>
  );
}

// ------------------------------------------------------------

function MotDePasse() {
  const [ancien, setAncien] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const discordance = confirmation && nouveau !== confirmation;
  const tropCourt = nouveau && nouveau.length < 10;

  async function soumettre(e) {
    e.preventDefault();
    setErreur(null);
    setMessage(null);
    setEnvoi(true);
    try {
      await api.changerMotDePasse(ancien, nouveau);
      setMessage(t("Mot de passe changé. Les autres sessions ouvertes ont été refermées."));
      setAncien(""); setNouveau(""); setConfirmation("");
    } catch (e2) {
      setErreur(e2.message);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Encadre titre={t("Mot de passe")} icone={Lock}>
      <p style={texteAide}>
        {t("Le changer referme toutes les autres sessions ouvertes sur ce compte — c'est voulu : un mot de passe qu'on change est souvent un mot de passe qu'on croit connu de quelqu'un d'autre. Celle-ci reste ouverte.")}
      </p>
      <form onSubmit={soumettre} style={{ marginTop: 14, maxWidth: 340 }}>
        <Champ label={t("Mot de passe actuel")} type="password" value={ancien}
               autoComplete="current-password" onChange={setAncien} />
        <Champ label={t("Nouveau mot de passe")} type="password" value={nouveau}
               autoComplete="new-password" onChange={setNouveau}
               aide={tropCourt ? t("Au moins 10 caractères.") : null} />
        <Champ label="Confirmation" type="password" value={confirmation}
               autoComplete="new-password" onChange={setConfirmation}
               aide={discordance ? t("Les deux saisies diffèrent.") : null} />

        {erreur && <Alerte ton="erreur">{erreur}</Alerte>}
        {message && <Alerte ton="succes">{message}</Alerte>}

        <button type="submit" disabled={envoi || !ancien || !nouveau || discordance || tropCourt}
                style={{ ...boutonPrimaire, marginTop: 14,
                         opacity: envoi || !ancien || !nouveau || discordance || tropCourt ? 0.55 : 1 }}>
          {envoi ? "Changement…" : t("Changer le mot de passe")}
        </button>
      </form>
    </Encadre>
  );
}

// ------------------------------------------------------------

function DoubleAuthentification({ profil, onChange }) {
  const [appairage, setAppairage] = useState(false);
  const [codesSecours, setCodesSecours] = useState(null);
  const [motDePasse, setMotDePasse] = useState("");
  const [action, setAction] = useState(null);   // 'desactiver' | 'codes'
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  // Codes refaits : ils ne seront plus jamais affichés, l'écran ne fait donc
  // que cela tant qu'ils n'ont pas été notés.
  if (codesSecours) {
    return (
      <Encadre titre={t("Nouveaux codes de secours")} icone={KeyRound}>
        <p style={texteAide}>
          Les précédents ne valent plus rien. Notez ceux-ci hors de cet ordinateur :
          ils sont conservés hachés, <strong>personne ne pourra vous les réafficher</strong>.
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
          <button onClick={() => { setCodesSecours(null); onChange(); }} style={boutonPrimaire}>
            <Check size={13} /> Je les ai notés
          </button>
        </div>
      </Encadre>
    );
  }

  if (appairage) {
    return (
      <Encadre titre={t("Mettre en place la double authentification")} icone={ShieldCheck}>
        <AppairageOtp
          demarrerImmediatement
          onTermine={() => { setAppairage(false); onChange(); }}
          onAnnuler={() => setAppairage(false)}
        />
      </Encadre>
    );
  }

  async function executer(promesse, apres) {
    setErreur(null);
    setEnvoi(true);
    try {
      apres(await promesse);
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Encadre titre={t("Double authentification")} icone={profil.otp_actif ? ShieldCheck : ShieldAlert}>
      <p style={texteAide}>
        {t("Un code à usage unique, lu sur votre téléphone, s'ajoute au mot de passe. Un mot de passe volé ne suffit alors plus à entrer.")}
      </p>

      <div style={{
        display: "flex", alignItems: "center", gap: 8, margin: "14px 0",
        fontSize: 13, color: profil.otp_actif ? "var(--accent)" : "var(--ink-soft)",
      }}>
        {profil.otp_actif ? <Check size={15} /> : <X size={15} />}
        {profil.otp_actif
          ? `Active · ${profil.codes_secours_restants} code${profil.codes_secours_restants > 1 ? "s" : ""} de secours restant${profil.codes_secours_restants > 1 ? "s" : ""}`
          : "Inactive"}
      </div>

      {erreur && <Alerte ton="erreur">{erreur}</Alerte>}

      {!profil.otp_actif && (
        <button onClick={() => setAppairage(true)} style={boutonPrimaire}>
          Mettre en place
        </button>
      )}

      {profil.otp_actif && !action && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={() => setAction("codes")} style={boutonSecondaire}>
            <RefreshCw size={13} /> Refaire des codes de secours
          </button>
          {!profil.otp_impose && (
            <button onClick={() => setAction("desactiver")}
                    style={{ ...boutonSecondaire, color: "var(--brick)", borderColor: "var(--brick)" }}>
              Désactiver
            </button>
          )}
        </div>
      )}

      {profil.otp_actif && profil.otp_impose && (
        <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 10 }}>
          {t("Un administrateur exige la double authentification sur ce compte : elle ne peut pas être désactivée ici.")}
        </div>
      )}

      {action && (
        <div style={{ marginTop: 14, maxWidth: 340 }}>
          <p style={{ ...texteAide, marginBottom: 8 }}>
            {action === "codes"
              ? t("Les codes actuels cesseront d'être valables — on refait des codes justement parce qu'on ne sait plus ce que sont devenus les précédents.")
              : t("Le second facteur sera retiré : le mot de passe suffira de nouveau à entrer.")}
          </p>
          <Champ label={t("Votre mot de passe")} type="password" value={motDePasse}
                 autoComplete="current-password" onChange={setMotDePasse} />
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button
              disabled={envoi || !motDePasse}
              onClick={() => {
                const suite = action === "codes"
                  ? api.regenererCodesSecours(motDePasse)
                  : api.desactiverOtp(motDePasse);
                const etait = action;
                executer(suite, (r) => {
                  setMotDePasse(""); setAction(null);
                  if (etait === "codes") setCodesSecours(r.codes); else onChange();
                });
              }}
              style={{ ...boutonPrimaire, opacity: envoi || !motDePasse ? 0.55 : 1,
                       background: action === "codes" ? "var(--accent)" : "var(--brick)" }}
            >
              {envoi ? "…" : action === "codes" ? t("Refaire les codes") : t("Désactiver")}
            </button>
            <button onClick={() => { setAction(null); setMotDePasse(""); setErreur(null); }}
                    style={boutonSecondaire}>
              Annuler
            </button>
          </div>
        </div>
      )}
    </Encadre>
  );
}

/**
 * Appareils connectés à ce compte.
 *
 * Un jeton de session ne se voit pas : sans cette liste, personne ne peut
 * répondre à « suis-je encore connecté sur l'ordinateur du bureau ? », ni
 * refermer une session laissée ouverte ailleurs. C'est aussi le premier endroit
 * où se remarque une connexion qui n'est pas la sienne — d'où l'appareil et
 * l'adresse, affichés pour être reconnus.
 */
function Sessions() {
  const [sessions, setSessions] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [enCours, setEnCours] = useState(false);

  function charger() {
    api.mesSessions().then(setSessions).catch((e) => setErreur(e.message));
  }
  useEffect(charger, []);

  async function agir(promesse) {
    setEnCours(true);
    setErreur(null);
    try {
      await promesse;
      charger();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(false);
    }
  }

  const autres = (sessions || []).filter((s) => !s.courante).length;

  return (
    <Encadre titre={t("Appareils connectés")} icone={Laptop}>
      <p style={texteAide}>
        {t("Chaque connexion à ce compte laisse une session ouverte jusqu'à son expiration. Fermer une session la coupe immédiatement, où qu'elle soit.")}
      </p>

      {erreur && <Alerte ton="erreur">{erreur}</Alerte>}
      {!sessions && !erreur && (
        <div style={{ fontSize: 12, color: "var(--ink-faint)", marginTop: 12 }}>{t("Chargement…")}</div>
      )}

      {sessions && (
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 2 }}>
          {sessions.map((session) => (
            <div key={session.id} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "8px 10px", borderRadius: "var(--radius)",
              background: session.courante ? "var(--accent-soft)" : "transparent",
              border: `1px solid ${session.courante ? "var(--accent-soft)" : "var(--line)"}`,
            }}>
              <Laptop size={15} color={session.courante ? "var(--accent)" : "var(--ink-faint)"}
                      style={{ flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: "var(--ink)" }}>
                  {session.appareil}
                  {session.courante && (
                    <span style={{ color: "var(--accent)", fontSize: 11, marginLeft: 8 }}>
                      cet appareil
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}>
                  {session.adresse || "adresse inconnue"} · vue {ilYA(session.date_activite)} ·
                  ouverte {ilYA(session.date_creation)}
                </div>
              </div>
              <button
                onClick={() => agir(api.fermerSession(session.id))}
                disabled={enCours}
                title={session.courante ? t("Se déconnecter de cet appareil") : t("Fermer cette session")}
                style={{
                  display: "flex", alignItems: "center", gap: 5,
                  border: "1px solid var(--line-strong)", background: "transparent",
                  color: "var(--ink-soft)", borderRadius: "var(--radius)",
                  padding: "3px 9px", fontSize: 11.5, cursor: "pointer", flexShrink: 0,
                }}
              >
                <LogOut size={11} />
                Fermer
              </button>
            </div>
          ))}
        </div>
      )}

      {autres > 0 && (
        <button
          onClick={() => agir(api.fermerLesAutresSessions())}
          disabled={enCours}
          style={{ ...boutonSecondaire, marginTop: 12 }}
        >
          <LogOut size={13} />
          Fermer les {autres} autre{autres > 1 ? "s" : ""} session{autres > 1 ? "s" : ""}
        </button>
      )}
    </Encadre>
  );
}

/** « il y a 3 heures », à partir d'un horodatage ISO. */
// ------------------------------------------------------------
// Petits éléments d'interface
// ------------------------------------------------------------

/**
 * Une section de la fenêtre. Dans une modale, un cadre dans un cadre n'apporte
 * rien : un filet de séparation suffit à découper.
 */
function Encadre({ titre, icone: Icone, children }) {
  return (
    <section style={{
      borderTop: "1px solid var(--line)", paddingTop: 16, marginTop: 18,
    }}>
      {titre && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          {Icone && <Icone size={16} color="var(--accent)" />}
          <h2 style={{ fontSize: 15 }}>{titre}</h2>
        </div>
      )}
      {children}
    </section>
  );
}

function Champ({ label, value, onChange, type = "text", aide, mono, ...reste }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: "block", fontSize: 12, color: "var(--ink-soft)", marginBottom: 4 }}>
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%", padding: "8px 10px", fontSize: 13,
          border: "1px solid var(--line-strong)", borderRadius: "var(--radius)",
          background: "var(--bg-panel-alt)", color: "var(--ink)",
          fontFamily: mono ? "var(--font-mono)" : "inherit",
          letterSpacing: mono ? "0.18em" : undefined,
        }}
        {...reste}
      />
      {aide && <div style={{ fontSize: 11, color: "var(--amber)", marginTop: 4 }}>{aide}</div>}
    </div>
  );
}

function Alerte({ ton, children }) {
  const couleurs = ton === "succes"
    ? { fond: "var(--accent-soft)", texte: "var(--accent)" }
    : { fond: "var(--brick-soft)", texte: "var(--brick)" };
  return (
    <div style={{
      marginTop: 12, padding: "8px 11px", borderRadius: "var(--radius)",
      background: couleurs.fond, color: couleurs.texte, fontSize: 12.5, lineHeight: 1.45,
    }}>
      {children}
    </div>
  );
}


/**
 * Mode d'ouverture d'un document (§19.20).
 *
 * Personnel, et non de foyer : il dépend de la machine et de la liaison de celui
 * qui regarde. Sur un portable en 4G, ouvrir la miniature plutôt que le PDF
 * change tout ; sur un poste fixe, la question ne se pose pas. Le mettre dans
 * les réglages généraux aurait obligé un foyer à trancher pour tout le monde une
 * question qui n'a pas de réponse commune.
 *
 * Ce qu'une fiche **montre**, en revanche, se règle en administration : c'est
 * une décision prise par type de document, pour tout le monde (§19.21).
 */
function Affichage({ profil, onChange }) {
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState(null);

  async function enregistrer(preferences) {
    setEnCours(true);
    setErreur(null);
    try {
      await api.changerPreferences(preferences);
      onChange();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div>
      <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 8 }}>
        {t("À l'ouverture d'un document")}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {[
          { cle: "document", icone: FileText, libelle: t("Le document"),
            aide: t("Le PDF entier, feuilletable dans le panneau.") },
          { cle: "miniature", icone: Image, libelle: t("Une miniature"),
            aide: t("Une vignette de la première page, et celles des documents liés côte à côte. Le PDF n'est pas chargé : on reconnaît sans attendre.") },
        ].map(({ cle, icone: Icone, libelle, aide }) => {
          const choisi = (profil.mode_apercu || "miniature") === cle;
          return (
            <button
              key={cle}
              disabled={enCours}
              onClick={() => enregistrer({ mode_apercu: cle })}
              style={{
                flex: 1, textAlign: "left", padding: "10px 12px",
                borderRadius: "var(--radius)",
                border: "1px solid " + (choisi ? "var(--accent)" : "var(--line)"),
                background: choisi ? "var(--accent-soft)" : "var(--bg-panel)",
                color: "var(--ink)",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 6,
                             fontSize: 12.5, fontWeight: 600 }}>
                <Icone size={14} />
                {libelle}
                {choisi && <Check size={13} color="var(--accent)" />}
              </span>
              <span style={{ display: "block", fontSize: 11, color: "var(--ink-soft)",
                             marginTop: 4, lineHeight: 1.45 }}>
                {aide}
              </span>
            </button>
          );
        })}
      </div>

      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 12,
                    lineHeight: 1.45 }}>
        {t("Ce choix ne vaut que pour vous. Il se change aussi, document ouvert, par les deux icônes du bandeau.")}
      </div>

      {/* Palette et langue : le foyer donne le départ, chacun le remplace pour
          lui (§22.50, §22.51). Un thème dépend de l'écran et de la lumière de la
          pièce ; une langue dépend de qui lit. */}
      <div style={{ fontSize: 12.5, fontWeight: 600, margin: "22px 0 8px" }}>
        {t("Thème de l'interface")}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {[{ cle: "", nom: t("Comme le foyer"), description: t("Le thème choisi en administration.") },
          ...themesDisponibles()].map((theme) => {
          const choisi = (profil.theme || "") === theme.cle;
          return (
            <button
              key={theme.cle || "foyer"}
              disabled={enCours}
              onClick={() => enregistrer({ theme: theme.cle })}
              aria-pressed={choisi}
              title={theme.description ? t(theme.description) : ""}
              style={{
                padding: "7px 12px", borderRadius: "var(--radius)", fontSize: 12.5,
                textAlign: "left", maxWidth: 220,
                border: "1px solid " + (choisi ? "var(--accent)" : "var(--line)"),
                background: choisi ? "var(--accent-soft)" : "var(--bg-panel)",
                color: choisi ? "var(--accent)" : "var(--ink)", cursor: "pointer",
              }}
            >
              <span style={{ display: "block", fontWeight: choisi ? 600 : 400 }}>
                {t(theme.nom || theme.cle)}
              </span>
              {theme.description && (
                <span style={{ display: "block", fontSize: 11, color: "var(--ink-soft)",
                               marginTop: 2, lineHeight: 1.4 }}>
                  {t(theme.description)}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div style={{ fontSize: 12.5, fontWeight: 600, margin: "22px 0 8px" }}>
        {t("Langue de l'interface")}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {[{ cle: "", nom: t("Comme le foyer") }, ...languesDisponibles()].map((langue) => {
          const choisie = (profil.langue || "") === langue.cle;
          return (
            <button
              key={langue.cle || "foyer"}
              disabled={enCours}
              onClick={() => enregistrer({ langue: langue.cle })}
              aria-pressed={choisie}
              style={{
                padding: "6px 12px", borderRadius: "var(--radius)", fontSize: 12.5,
                border: "1px solid " + (choisie ? "var(--accent)" : "var(--line)"),
                background: choisie ? "var(--accent-soft)" : "var(--bg-panel)",
                color: choisie ? "var(--accent)" : "var(--ink)", cursor: "pointer",
              }}
            >
              {langue.nom || langue.cle}
            </button>
          );
        })}
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.45 }}>
        Le français est la langue d'origine : ce qu'une traduction ne couvre pas s'affiche
        en français plutôt qu'en vide. Une langue ou un thème se rajoutent en déposant un
        fichier JSON dans les dossiers <code>langues/</code> et <code>themes/</code> de
        l'installation — voir le wiki.
      </div>

      {/* Le nombre de lignes du registre dépend de l'écran devant lequel on est
          assis, pas du foyer (§22.44) : le réglage du foyer donne le départ, ce
          choix-ci le remplace pour ce compte. */}
      <div style={{ fontSize: 12.5, fontWeight: 600, margin: "22px 0 8px" }}>
        {t("Lignes par page du registre")}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {[{ valeur: 0, libelle: t("Comme le foyer") },
          { valeur: 25, libelle: "25" }, { valeur: 50, libelle: "50" },
          { valeur: 100, libelle: "100" }, { valeur: 200, libelle: "200" }]
          .map(({ valeur, libelle }) => {
            const choisi = (profil.lignes_par_page || 0) === valeur;
            return (
              <button
                key={valeur}
                disabled={enCours}
                onClick={() => enregistrer({ lignes_par_page: valeur })}
                aria-pressed={choisi}
                style={{
                  padding: "6px 12px", borderRadius: "var(--radius)", fontSize: 12.5,
                  border: "1px solid " + (choisi ? "var(--accent)" : "var(--line)"),
                  background: choisi ? "var(--accent-soft)" : "var(--bg-panel)",
                  color: choisi ? "var(--accent)" : "var(--ink)", cursor: "pointer",
                }}
              >
                {libelle}
              </button>
            );
          })}
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 8,
                    lineHeight: 1.45 }}>
        {t("Cinquante lignes tiennent sur un grand écran et débordent sur un portable. « Comme le foyer » rend la main au réglage de l'administration ; tout autre choix le remplace, pour vous seul. La pagination du registre le change aussi, le temps d'une visite.")}
      </div>

      {/* Se taire par courriel ne fait pas perdre les rappels : ils restent dans
          l'application (§21.10). */}
      <div style={{ fontSize: 12.5, fontWeight: 600, margin: "22px 0 8px" }}>
        {t("Rappels par courriel")}
      </div>
      <label style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12.5 }}>
        <input
          type="checkbox"
          disabled={enCours}
          checked={profil.courriel_rappels !== false}
          onChange={(e) => enregistrer({ courriel_rappels: e.target.checked })}
          style={{ marginTop: 2 }}
        />
        <span>
          Recevoir un résumé des rappels par courriel
          <span style={{ display: "block", fontSize: 11, color: "var(--ink-soft)",
                         marginTop: 2, lineHeight: 1.45 }}>
            {t("Un résumé espacé de ce que personne n'a lu, jamais un message par événement. Décocher ne fait rien perdre : les rappels restent dans l'application. L'envoi dépend aussi du réglage du foyer.")}
          </span>
        </span>
      </label>

      {erreur && (
        <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>
      )}
    </div>
  );
}
