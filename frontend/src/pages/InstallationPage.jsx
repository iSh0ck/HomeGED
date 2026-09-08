import React, { useEffect, useState } from "react";
import { ArrowRight, Check, FolderTree, Home, ShieldCheck } from "lucide-react";
import { api } from "../api";
import Liste from "../components/champs/Liste.jsx";
import { t } from "../lib/langue";

/**
 * Première installation (§18.23).
 *
 * L'écran qui accueille un foyer dont la base est vierge. Il remplace l'ancien
 * amorçage par `.env`, où il fallait un accès au serveur pour ouvrir le premier
 * compte — et où le mot de passe du foyer restait écrit en clair sur le disque.
 *
 * Trois étapes seulement, dans l'ordre où l'on y pense : qui administre, quel
 * foyer, quel classement de départ. Tout le reste se règle ensuite, depuis
 * l'application — c'est justement ce qui la rend transposable.
 */
export default function InstallationPage({ etat, onInstalle }) {
  const [etape, setEtape] = useState(0);
  const [valeurs, setValeurs] = useState({
    email: "", mot_de_passe: "", confirmation: "", prenom: "", nom: "",
    nom_foyer: "", fuseau_horaire: "Europe/Paris", classement: "essentiel",
  });
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    // Le fuseau du navigateur est une bien meilleure proposition qu'un défaut
    // écrit en dur : neuf fois sur dix, c'est le bon.
    try {
      const devine = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (devine && (etat.fuseaux || []).includes(devine)) {
        setValeurs((v) => ({ ...v, fuseau_horaire: devine }));
      }
    } catch { /* le navigateur ne sait pas : on garde le défaut */ }
  }, [etat.fuseaux]);

  const maj = (cle, valeur) => setValeurs((v) => ({ ...v, [cle]: valeur }));

  const problemeCompte =
    !valeurs.email.includes("@") ? t("Indiquez une adresse e-mail.")
    : valeurs.mot_de_passe.length < 10 ? t("Le mot de passe doit faire au moins 10 caractères.")
    : valeurs.mot_de_passe !== valeurs.confirmation ? t("Les deux mots de passe diffèrent.")
    : null;

  async function terminer() {
    setEnvoi(true);
    setErreur(null);
    try {
      const { confirmation, ...charge } = valeurs;
      await api.installer(charge);
      onInstalle();
    } catch (e) {
      setErreur(e.message);
      setEnvoi(false);
    }
  }

  return (
    <div style={cadre}>
      <div style={panneau}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <Home size={20} color="var(--accent)" />
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: 22, margin: 0 }}>
            {t("Bienvenue dans HomeGED")}
          </h1>
        </div>
        <p style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.6, marginTop: 6 }}>
          {t("Cette installation n'a encore aucun compte. Trois questions, et le classeur du foyer est à vous.")}
        </p>

        <Etapes courante={etape} />

        {etape === 0 && (
          <section>
            <Titre icone={ShieldCheck} texte={t("Le compte qui administrera")} />
            <p style={aide}>
              {t("C'est le compte qui pourra tout régler. Il n'est écrit nulle part ailleurs que dans cette base : personne ne peut le retrouver dans un fichier du serveur.")}
            </p>
            <div style={{ display: "flex", gap: 10 }}>
              <Champ label={t("Prénom")} valeur={valeurs.prenom} onChange={(v) => maj("prenom", v)} />
              <Champ label="Nom" valeur={valeurs.nom} onChange={(v) => maj("nom", v)} />
            </div>
            <Champ label={t("Adresse e-mail")} type="email" valeur={valeurs.email}
                   onChange={(v) => maj("email", v)} autoComplete="username" />
            <Champ label={t("Mot de passe")} type="password" valeur={valeurs.mot_de_passe}
                   onChange={(v) => maj("mot_de_passe", v)} autoComplete="new-password" />
            <Champ label="Confirmation" type="password" valeur={valeurs.confirmation}
                   onChange={(v) => maj("confirmation", v)} autoComplete="new-password" />
            {problemeCompte && valeurs.email && (
              <div style={{ fontSize: 12, color: "var(--amber)", marginTop: 6 }}>{problemeCompte}</div>
            )}
          </section>
        )}

        {etape === 1 && (
          <section>
            <Titre icone={Home} texte={t("Le foyer")} />
            <Champ label={t("Nom du foyer (facultatif)")} valeur={valeurs.nom_foyer}
                   onChange={(v) => maj("nom_foyer", v)} placeholder={t("Maison des Dupont")} />
            <div style={{ marginTop: 12 }}>
              <label style={etiquette}>{t("Fuseau horaire")}</label>
              <Liste
                recherchable
                valeur={valeurs.fuseau_horaire}
                ariaLabel={t("Fuseau horaire")}
                options={(etat.fuseaux || []).map((f) => ({ valeur: f, libelle: f }))}
                onChange={(v) => maj("fuseau_horaire", v)}
              />
              <p style={aide}>
                {t("Les dates sont enregistrées en temps universel et lues dans ce fuseau. Ce réglage se change à tout moment, sans rien modifier de ce qui est enregistré.")}
              </p>
            </div>
          </section>
        )}

        {etape === 2 && (
          <section>
            <Titre icone={FolderTree} texte={t("Le classement de départ")} />
            <p style={aide}>
              {t("Chaque foyer range à peu près les mêmes choses. Plutôt que de vous faire retaper ce que tous ont en commun, l'installation pose un classement tout fait — à élaguer ensuite, ce qui prend dix secondes par catégorie, quand inventer celle qui manque en prend dix minutes.")}
            </p>
            {(etat.modeles || []).map((modele) => (
              <Choix
                key={modele.cle}
                choisi={valeurs.classement === modele.cle}
                onClick={() => maj("classement", modele.cle)}
                titre={`${t(modele.libelle)} — ${modele.categories} catégories, ${modele.tables} table${modele.tables > 1 ? "s" : ""}`}
                detail={t(modele.description)}
              />
            ))}
            <Choix
              choisi={valeurs.classement === "vierge"}
              onClick={() => maj("classement", "vierge")}
              titre={t("Repartir d'une page blanche")}
              detail={t("Aucune catégorie, aucune règle. Vous construisez votre propre classement — c'est le choix d'un foyer qui range autrement.")}
            />
          </section>
        )}

        {erreur && (
          <div style={{
            marginTop: 14, padding: "9px 12px", borderRadius: "var(--radius)",
            background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5,
          }}>
            {erreur}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 22 }}>
          <button onClick={() => setEtape((e) => Math.max(0, e - 1))}
                  disabled={etape === 0} style={{ ...boutonSecondaire, opacity: etape === 0 ? 0.4 : 1 }}>
            Retour
          </button>
          {etape < 2 ? (
            <button onClick={() => setEtape((e) => e + 1)}
                    disabled={etape === 0 && Boolean(problemeCompte)}
                    style={{ ...boutonPrimaire, opacity: etape === 0 && problemeCompte ? 0.5 : 1 }}>
              Continuer
              <ArrowRight size={15} />
            </button>
          ) : (
            <button onClick={terminer} disabled={envoi || Boolean(problemeCompte)}
                    style={{ ...boutonPrimaire, opacity: envoi ? 0.6 : 1 }}>
              <Check size={15} />
              {envoi ? "Installation…" : t("Ouvrir le classeur")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Etapes({ courante }) {
  const noms = ["Administrateur", "Foyer", "Classement"];
  return (
    <div style={{ display: "flex", gap: 6, margin: "18px 0 20px" }}>
      {noms.map((nom, i) => (
        <div key={nom} style={{ flex: 1 }}>
          <div style={{
            height: 3, borderRadius: 2, marginBottom: 6,
            background: i <= courante ? "var(--accent)" : "var(--line)",
          }} />
          <div style={{
            fontSize: 11, color: i === courante ? "var(--ink)" : "var(--ink-faint)",
            fontWeight: i === courante ? 600 : 400,
          }}>
            {nom}
          </div>
        </div>
      ))}
    </div>
  );
}

function Titre({ icone: Icone, texte }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
      <Icone size={15} color="var(--ink-faint)" />
      <span style={{ fontSize: 14, fontWeight: 600 }}>{texte}</span>
    </div>
  );
}

function Champ({ label, valeur, onChange, type = "text", placeholder, autoComplete }) {
  return (
    <div style={{ marginTop: 12, flex: 1 }}>
      <label style={etiquette}>{label}</label>
      <input
        type={type}
        value={valeur}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        style={saisie}
      />
    </div>
  );
}

function Choix({ choisi, onClick, titre, detail }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "block", width: "100%", textAlign: "left", marginTop: 10,
        padding: "11px 13px", borderRadius: "var(--radius)",
        border: `1px solid ${choisi ? "var(--accent)" : "var(--line-strong)"}`,
        background: choisi ? "var(--accent-soft)" : "transparent",
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>{titre}</div>
      <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 3, lineHeight: 1.5 }}>
        {detail}
      </div>
    </button>
  );
}

const cadre = {
  minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center",
  background: "var(--bg-app)", padding: 24,
};

const panneau = {
  width: "100%", maxWidth: 520, background: "var(--bg-panel)",
  border: "1px solid var(--line)", borderRadius: "var(--radius)",
  boxShadow: "var(--shadow-panel)", padding: 28,
};

const etiquette = { fontSize: 12, color: "var(--ink-faint)", display: "block", marginBottom: 4 };
const aide = { fontSize: 12, color: "var(--ink-faint)", lineHeight: 1.55, marginTop: 6 };
const saisie = {
  width: "100%", border: "1px solid var(--line-strong)", background: "var(--bg-panel-alt)",
  borderRadius: "var(--radius)", padding: "8px 10px", fontSize: 13,
  color: "var(--ink)", fontFamily: "inherit",
};
const boutonPrimaire = {
  display: "inline-flex", alignItems: "center", gap: 7, border: "none",
  background: "var(--accent)", color: "#fff", fontWeight: 600,
  borderRadius: "var(--radius)", padding: "9px 18px", fontSize: 13,
};
const boutonSecondaire = {
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "9px 16px", fontSize: 13,
};
