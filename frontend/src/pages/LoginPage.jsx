import React, { useState } from "react";
import { Eye, EyeOff, FolderSearch, ScanLine, ShieldCheck, KeyRound, ArrowLeft } from "lucide-react";
import { useAuth } from "../auth/AuthContext.jsx";
import AlerteModale from "../components/AlerteModale.jsx";
import { t } from "../lib/langue";

/**
 * Écran de connexion.
 *
 * C'est la seule page que voit quelqu'un qui n'est pas encore entré : elle dit
 * donc ce qu'est l'application, plutôt que de se réduire à deux champs sur fond
 * vide. Le panneau de gauche présente, celui de droite fait entrer.
 *
 * Le message d'erreur distingue deux situations qui n'appellent pas la même
 * réaction : des identifiants refusés (on réessaie) et un verrouillage après
 * trop de tentatives (on attend). Les confondre laisserait l'utilisateur
 * s'acharner en vain.
 */
export default function LoginPage({ nomFoyer }) {
  const { login, validerOtp } = useAuth();
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [motDePasseVisible, setMotDePasseVisible] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  // jeton de l'étape intermédiaire : sa présence fait basculer l'écran sur la
  // demande du code à usage unique
  const [jetonOtp, setJetonOtp] = useState(null);

  const attente = erreur && /tentative/i.test(erreur);

  async function soumettre(e) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      const suite = await login(email, motDePasse);
      if (suite?.otpRequis) setJetonOtp(suite.jetonIntermediaire);
    } catch (err) {
      setErreur(err.message);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div style={{ minHeight: "100dvh", display: "flex", background: "var(--bg-app)" }}>
      <style>{`
        /* Le champ actif se signale par un halo discret plutôt que par un saut
           de couleur : l'œil suit le déplacement sans être arrêté. */
        .champ-connexion {
          transition: border-color 160ms, box-shadow 160ms, background 160ms;
        }
        .champ-connexion:focus {
          outline: none;
          border-color: var(--accent);
          box-shadow: 0 0 0 3px var(--accent-soft);
          background: var(--bg-panel);
        }
        .bouton-connexion {
          transition: transform 120ms, box-shadow 160ms, background 160ms;
        }
        .bouton-connexion:not(:disabled):hover {
          transform: translateY(-1px);
          box-shadow: 0 6px 16px -8px rgba(34, 40, 31, 0.55);
        }
        .bouton-connexion:not(:disabled):active { transform: translateY(0); }
      `}</style>

      {erreur && (
        <AlerteModale
          titre={attente ? t("Connexion suspendue") : t("Connexion refusée")}
          message={erreur}
          ton={attente ? "attente" : "erreur"}
          onFermer={() => { setErreur(null); setMotDePasse(""); }}
        />
      )}

      <Presentation nomFoyer={nomFoyer} />

      <div
        style={{
          position: "relative",
          overflow: "hidden",
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "40px 24px",
        }}
      >
        <FondAnime />

        {jetonOtp ? (
          <SecondFacteur
            jeton={jetonOtp}
            onValider={validerOtp}
            onRetour={() => { setJetonOtp(null); setMotDePasse(""); setErreur(null); }}
          />
        ) : (
        <form
          onSubmit={soumettre}
          className="apparition"
          style={{
            animationDelay: "160ms",
            position: "relative",
            zIndex: 1,
            width: "100%",
            maxWidth: 360,
            background: "var(--bg-panel)",
            border: "1px solid var(--line)",
            borderTop: "3px solid var(--accent)",
            borderRadius: "var(--radius)",
            /* Ombre plus creusée que celle des panneaux ordinaires : la carte doit
               se détacher franchement du fond qui bouge derrière elle. Elle reste
               opaque — la lisibilité d'un formulaire de connexion prime sur l'effet. */
            boxShadow: "0 18px 44px -22px rgba(34, 40, 31, 0.45), 0 2px 6px -3px rgba(34, 40, 31, 0.12)",
            padding: "30px 28px",
          }}
        >
          <h2 style={{ fontSize: 19 }}>{t("Content de vous revoir")}</h2>
          <p style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 5, marginBottom: 24 }}>
            {t("Connectez-vous pour accéder au registre du foyer.")}
          </p>

          <label htmlFor="email" style={labelStyle}>{t("Adresse e-mail")}</label>
          <input
            id="email"
            type="email"
            required
            autoFocus
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="vous@exemple.fr"
            className="champ-connexion"
            style={inputStyle}
          />

          <label htmlFor="motdepasse" style={{ ...labelStyle, marginTop: 16 }}>
            Mot de passe
          </label>
          <div style={{ position: "relative" }}>
            <input
              id="motdepasse"
              type={motDePasseVisible ? "text" : "password"}
              required
              autoComplete="current-password"
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
              className="champ-connexion"
              style={{ ...inputStyle, paddingRight: 38 }}
            />
            <button
              type="button"
              onClick={() => setMotDePasseVisible((v) => !v)}
              aria-label={motDePasseVisible ? t("Masquer le mot de passe") : t("Afficher le mot de passe")}
              title={motDePasseVisible ? "Masquer" : "Afficher"}
              style={{
                position: "absolute", right: 6, top: 0, bottom: 0,
                display: "flex", alignItems: "center",
                border: "none", background: "transparent", color: "var(--ink-faint)",
                padding: "0 6px",
              }}
            >
              {motDePasseVisible ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>

          <button
            type="submit"
            disabled={envoi}
            className="bouton-connexion"
            style={{
              marginTop: 22,
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              padding: "11px 0",
              fontSize: 13.5,
              fontWeight: 600,
              cursor: envoi ? "default" : "pointer",
              opacity: envoi ? 0.8 : 1,
            }}
          >
            {envoi && <Rouet />}
            {envoi ? t("Connexion…") : t("Se connecter")}
          </button>

          <p style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 18, marginBottom: 0, lineHeight: 1.5 }}>
            {t("Mot de passe oublié ? Un administrateur du foyer peut le réinitialiser depuis l'espace d'administration.")}
          </p>
        </form>
        )}
      </div>
    </div>
  );
}

/**
 * Fond animé de la colonne de connexion.
 *
 * Trois halos très flous dérivent lentement derrière le formulaire, comme une
 * lumière de lampe qui bouge dans une pièce. Le mouvement est volontairement au
 * bord du perceptible — cycles de 26 à 38 s, amplitudes de quelques dizaines de
 * pixels, opacités faibles : on doit sentir que la page respire sans jamais être
 * tenté de regarder ailleurs que les deux champs.
 *
 * Deux précautions :
 *   les trajets bouclent (100 % identique à 0 %), donc en mouvement réduit —
 *   où le navigateur fige l'animation à son terme — les halos se posent
 *   exactement là où ils ont été placés, et non dans un état de passage ;
 *   tout est en `transform` et `opacity`, seules propriétés que le compositeur
 *   traite sans réagencer la page.
 *
 * Aucune image : deux dégradés radiaux et un grain de papier en CSS.
 */
function FondAnime() {
  return (
    <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <style>{`
        @keyframes derive-a {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33%      { transform: translate(76px, -52px) scale(1.14); }
          66%      { transform: translate(-48px, 44px) scale(0.92); }
        }
        @keyframes derive-b {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50%      { transform: translate(-92px, 64px) scale(1.18); }
        }
        @keyframes derive-c {
          0%, 100% { transform: translate(0, 0) scale(1); }
          40%      { transform: translate(56px, 70px) scale(0.88); }
          75%      { transform: translate(-62px, -38px) scale(1.12); }
        }
        .halo {
          position: absolute;
          border-radius: 50%;
          filter: blur(58px);
          will-change: transform;
        }
      `}</style>

      {/* Chaleur générale : le coin haut-gauche, côté panneau, est le plus clair. */}
      <div style={{
        position: "absolute", inset: 0,
        background:
          "radial-gradient(120% 100% at 18% 12%, rgba(255,253,248,0.9) 0%, rgba(255,253,248,0) 62%)," +
          "radial-gradient(90% 80% at 88% 92%, rgba(198,138,52,0.20) 0%, rgba(198,138,52,0) 62%)",
      }} />

      <div className="halo" style={{
        width: 420, height: 420, top: "-12%", left: "4%",
        background: "radial-gradient(circle, rgba(62,92,70,0.38), rgba(62,92,70,0) 70%)",
        animation: "derive-a 26s ease-in-out infinite",
      }} />
      <div className="halo" style={{
        width: 400, height: 400, bottom: "-10%", left: "18%",
        background: "radial-gradient(circle, rgba(198,138,52,0.34), rgba(198,138,52,0) 70%)",
        animation: "derive-b 30s ease-in-out infinite",
      }} />
      <div className="halo" style={{
        width: 360, height: 360, top: "30%", right: "-8%",
        background: "radial-gradient(circle, rgba(120,140,110,0.34), rgba(120,140,110,0) 70%)",
        animation: "derive-c 20s ease-in-out infinite",
      }} />

      <div className="halo" style={{
        width: 300, height: 300, top: "-6%", right: "14%",
        background: "radial-gradient(circle, rgba(146,110,64,0.26), rgba(146,110,64,0) 70%)",
        animation: "derive-b 24s ease-in-out infinite reverse",
      }} />

      {/* Grain de papier, immobile : il donne la matière que les halos, seuls,
          rendraient un peu vaporeuse. */}
      <div style={{
        position: "absolute", inset: 0, opacity: 0.7,
        backgroundImage:
          "repeating-linear-gradient(0deg, rgba(90,95,82,0.045) 0 1px, transparent 1px 4px)," +
          "repeating-linear-gradient(90deg, rgba(90,95,82,0.035) 0 1px, transparent 1px 4px)",
      }} />
    </div>
  );
}

/**
 * Deuxième étape de la connexion.
 *
 * Le mot de passe est déjà accepté ; il ne manque que le code du téléphone —
 * ou un code de secours, pour qui a perdu l'appareil. L'écran le dit, parce
 * qu'un utilisateur bloqué sans savoir qu'une issue existe abandonne.
 *
 * Le champ est en `inputMode="numeric"` avec `autoComplete="one-time-code"` :
 * sur un téléphone, le clavier s'ouvre sur les chiffres et le code proposé se
 * remplit tout seul.
 */
function SecondFacteur({ jeton, onValider, onRetour }) {
  const [code, setCode] = useState("");
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [secours, setSecours] = useState(false);

  async function soumettre(e) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      await onValider(jeton, code.trim());
    } catch (err) {
      setErreur(err.message);
      setCode("");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form
      onSubmit={soumettre}
      className="apparition"
      style={{
        position: "relative",
        zIndex: 1,
        width: "100%",
        maxWidth: 360,
        background: "var(--bg-panel)",
        border: "1px solid var(--line)",
        borderTop: "3px solid var(--accent)",
        borderRadius: "var(--radius)",
        boxShadow: "0 18px 44px -22px rgba(34, 40, 31, 0.45), 0 2px 6px -3px rgba(34, 40, 31, 0.12)",
        padding: "30px 28px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <KeyRound size={18} color="var(--accent)" />
        <h2 style={{ fontSize: 18 }}>{t("Code de vérification")}</h2>
      </div>
      <p style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 6, marginBottom: 20, lineHeight: 1.5 }}>
        {secours
          ? t("Saisissez l'un des codes de secours notés lors de la mise en place. Chacun ne sert qu'une fois.")
          : t("Ouvrez votre application d'authentification et recopiez les six chiffres affichés pour HomeGED.")}
      </p>

      <label htmlFor="code" style={labelStyle}>
        {secours ? t("Code de secours") : t("Code à six chiffres")}
      </label>
      <input
        id="code"
        autoFocus
        autoComplete="one-time-code"
        inputMode={secours ? "text" : "numeric"}
        value={code}
        onChange={(e) => setCode(secours ? e.target.value.toUpperCase() : e.target.value.replace(/\D/g, "").slice(0, 6))}
        placeholder={secours ? "XXXXX-XXXXX" : "000000"}
        className="champ-connexion"
        style={{
          ...inputStyle,
          fontFamily: "var(--font-mono)",
          fontSize: secours ? 15 : 22,
          letterSpacing: secours ? "0.06em" : "0.28em",
          textAlign: "center",
        }}
      />

      {erreur && (
        <AlerteModale
          titre={t("Code refusé")}
          message={erreur}
          onFermer={() => setErreur(null)}
        />
      )}

      <button
        type="submit"
        disabled={envoi || code.length < (secours ? 6 : 6)}
        className="bouton-connexion"
        style={{
          marginTop: 20, width: "100%", display: "flex", alignItems: "center",
          justifyContent: "center", gap: 8, background: "var(--accent)", color: "#fff",
          border: "none", borderRadius: "var(--radius)", padding: "11px 0",
          fontSize: 13.5, fontWeight: 600,
          cursor: envoi ? "default" : "pointer",
          opacity: envoi || code.length < 6 ? 0.7 : 1,
        }}
      >
        {envoi && <Rouet />}
        {envoi ? t("Vérification…") : "Valider"}
      </button>

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
        <BoutonLien onClick={onRetour}>
          <ArrowLeft size={11} /> Changer de compte
        </BoutonLien>
        <BoutonLien onClick={() => { setSecours(!secours); setCode(""); setErreur(null); }}>
          {secours ? t("Utiliser l'application") : t("J'ai perdu mon téléphone")}
        </BoutonLien>
      </div>
    </form>
  );
}

function BoutonLien({ children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 4, border: "none",
        background: "transparent", color: "var(--ink-soft)", fontSize: 11.5,
        textDecoration: "underline", cursor: "pointer", padding: 0,
      }}
    >
      {children}
    </button>
  );
}

/**
 * Panneau de présentation. Masqué sous 860 px : sur un écran étroit, mieux vaut
 * le formulaire seul que deux colonnes serrées l'une contre l'autre.
 */
function Presentation({ nomFoyer }) {
  return (
    <>
      <style>{`
        @media (max-width: 860px) { .presentation-connexion { display: none !important; } }
      `}</style>
      <aside
        className="presentation-connexion"
        style={{
          width: "44%",
          maxWidth: 520,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 28,
          padding: "48px 56px",
          background: "var(--bg-panel-alt)",
          borderRight: "1px solid var(--line)",
          /* fines rayures : le grain d'une chemise cartonnée, sans image */
          backgroundImage:
            "repeating-linear-gradient(135deg, rgba(62,92,70,0.035) 0 2px, transparent 2px 9px)",
        }}
      >
        {/* Entrée échelonnée : les éléments arrivent dans l'ordre où on les lit,
            à 70 ms d'intervalle. Assez pour donner du mouvement, trop court pour
            qu'on ait à attendre quoi que ce soit. */}
        <div className="apparition">
          {/* Le nom du foyer, s'il est réglé (§18.24) : c'est la première chose
              qu'on voit, et ce qui dit qu'on est chez soi et pas ailleurs. */}
          <h1 style={{ fontSize: 34, letterSpacing: "-0.02em" }}>{nomFoyer || "HomeGED"}</h1>
          <p style={{ fontSize: 14.5, color: "var(--ink-soft)", marginTop: 8, lineHeight: 1.55 }}>
            {nomFoyer ? t("Le classeur du foyer, tenu par HomeGED. ") : t("Le classeur du foyer. ")}
            Vous déposez un scan, il en ressort lisible, rangé et retrouvable.
          </p>
        </div>

        <div className="apparition" style={{ animationDelay: "70ms" }}>
          <ClasseurDessine />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {[
            { icone: ScanLine, titre: t("Océrisé à l'arrivée"),
              texte: t("Chaque dépôt est reconnu, indexé, et son texte devient cherchable.") },
            { icone: FolderSearch, titre: t("Rangé tout seul"),
              texte: t("Les catégories se reconnaissent, les montants et les dates se remplissent.") },
            { icone: ShieldCheck, titre: t("Chacun ses documents"),
              texte: t("Les droits s'accordent catégorie par catégorie, pour tout le foyer.") },
          ].map((atout, i) => (
            <div key={t(atout.titre)} className="apparition"
                 style={{ animationDelay: `${140 + i * 70}ms` }}>
              <Atout icone={atout.icone} titre={t(atout.titre)}>{t(atout.texte)}</Atout>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}

function Atout({ icone: Icone, titre, children }) {
  return (
    <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
      <span
        style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          width: 28, height: 28, flexShrink: 0, borderRadius: "var(--radius)",
          background: "var(--accent-soft)", color: "var(--accent)",
        }}
      >
        <Icone size={15} />
      </span>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{titre}</div>
        <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 2, lineHeight: 1.45 }}>
          {children}
        </div>
      </div>
    </div>
  );
}

/**
 * Trois chemises empilées, dessinées en SVG : de quoi habiller la page sans
 * embarquer la moindre image ni dépendance.
 *
 * Une feuille descend s'y ranger en boucle. L'animation ne décore pas : elle
 * montre le geste que fait l'application — on dépose, elle range. Le cycle est
 * long (5 s) et l'essentiel du temps la feuille est absente, pour que le
 * mouvement reste à la lisière du regard plutôt qu'au centre.
 */
function ClasseurDessine() {
  return (
    <svg viewBox="0 0 240 132" role="img"
         aria-label={t("Trois chemises cartonnées empilées, dans lesquelles une feuille vient se ranger")}
         style={{ width: "100%", maxWidth: 260, height: "auto" }}>
      <style>{`
        @keyframes rangement {
          0%        { transform: translateY(-38px); opacity: 0; }
          14%       { opacity: 1; }
          40%, 100% { transform: translateY(0); opacity: 0; }
        }
        .feuille-rangee {
          animation: rangement 5s cubic-bezier(0.3, 0.7, 0.4, 1) infinite;
          transform-origin: center;
        }
        @keyframes tracage { to { stroke-dashoffset: 0; } }
        .chemise-tracee {
          stroke-dasharray: 420;
          stroke-dashoffset: 420;
          animation: tracage 900ms ease-out forwards;
        }
      `}</style>

      {/* la feuille qui descend se ranger */}
      <g className="feuille-rangee">
        <rect x="96" y="14" width="52" height="30" rx="2"
              fill="var(--bg-panel)" stroke="var(--accent)" strokeWidth="1.6" />
        <line x1="104" y1="24" x2="140" y2="24" stroke="var(--accent)"
              strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
        <line x1="104" y1="32" x2="128" y2="32" stroke="var(--accent)"
              strokeWidth="1.4" strokeLinecap="round" opacity="0.35" />
      </g>

      {[0, 1, 2].map((i) => {
        const y = 84 - i * 26;
        const opacite = 0.35 + i * 0.32;
        return (
          <g key={i} opacity={opacite}>
            {/* onglet de la chemise */}
            <path d={`M 22 ${y} h 46 l 9 11 h 121 v 33 h -176 z`}
                  fill="var(--accent)" opacity="0.16" />
            <path d={`M 22 ${y} h 46 l 9 11 h 121 v 33 h -176 z`}
                  className="chemise-tracee"
                  style={{ animationDelay: `${120 + i * 130}ms` }}
                  fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinejoin="round" />
            {/* deux lignes d'écriture suggérées */}
            <line x1="36" y1={y + 22} x2="120" y2={y + 22}
                  stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" opacity="0.55" />
            <line x1="36" y1={y + 31} x2="92" y2={y + 31}
                  stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" opacity="0.35" />
          </g>
        );
      })}
    </svg>
  );
}

/** Rouet d'attente, en SVG : le bouton dit qu'il travaille au lieu de se figer. */
function Rouet() {
  return (
    <svg className="rotation" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor"
              strokeWidth="3" opacity="0.3" />
      <path d="M12 3 a9 9 0 0 1 9 9" fill="none" stroke="currentColor"
            strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

const labelStyle = {
  display: "block",
  fontSize: 12,
  fontWeight: 500,
  color: "var(--ink-soft)",
  marginBottom: 5,
};

const inputStyle = {
  width: "100%",
  padding: "10px 11px",
  fontSize: 13.5,
  fontFamily: "inherit",
  border: "1px solid var(--line-strong)",
  borderRadius: "var(--radius)",
  background: "var(--bg-panel-alt)",
  color: "var(--ink)",
};
