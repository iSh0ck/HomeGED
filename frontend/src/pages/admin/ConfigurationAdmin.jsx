import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, Download, PackageOpen, Upload } from "lucide-react";
import { adminApi } from "../../api";
import { t } from "../../lib/langue";

/**
 * Configuration du foyer : la sortir, la reprendre, partir d'un modèle (§18.26).
 *
 * Ce que HomeGED sait d'un foyer se range en deux tas : ses documents, et la
 * façon dont il les range. Le premier a son export ; voici la porte du second —
 * classement, règles de lecture, champs attendus, colonnes, vues, tableaux de
 * bord, tables du foyer, et les rôles qui disent qui voit quoi.
 *
 * Ni comptes, ni documents, ni journal : la configuration voyage, les identités
 * non. Importer les comptes d'un autre foyer donnerait des accès à des gens qui
 * n'y habitent pas.
 */
export default function ConfigurationAdmin() {
  const [modeles, setModeles] = useState([]);
  const [bilan, setBilan] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [remplacer, setRemplacer] = useState(false);
  const [avecDonnees, setAvecDonnees] = useState(false);
  const fichier = useRef(null);

  useEffect(() => {
    adminApi.modelesConfiguration().then(setModeles).catch((e) => setErreur(e.message));
  }, []);

  async function telecharger() {
    setErreur(null);
    try {
      const config = await adminApi.exporterConfiguration(avecDonnees);
      const contenu = JSON.stringify(config, null, 2);
      const lien = document.createElement("a");
      lien.href = URL.createObjectURL(new Blob([contenu], { type: "application/json" }));
      lien.download = `homeged-configuration-${new Date().toISOString().slice(0, 10)}.json`;
      lien.click();
      URL.revokeObjectURL(lien.href);
    } catch (e) {
      setErreur(e.message);
    }
  }

  async function importer(charge) {
    setEnvoi(true);
    setErreur(null);
    setBilan(null);
    try {
      setBilan(await adminApi.importerConfiguration({ ...charge, remplacer }));
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnvoi(false);
    }
  }

  function choisirFichier(evenement) {
    const choisi = evenement.target.files?.[0];
    if (!choisi) return;
    const lecteur = new FileReader();
    lecteur.onload = () => {
      try {
        importer({ configuration: JSON.parse(lecteur.result) });
      } catch {
        setErreur(t("Ce fichier n'est pas un JSON lisible."));
      }
    };
    lecteur.readAsText(choisi);
    evenement.target.value = "";   // le même fichier doit pouvoir être rechargé
  }

  return (
    <div style={{ maxWidth: 620 }}>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 20, lineHeight: 1.55 }}>
        La configuration, c'est votre façon de ranger : classement, règles de lecture,
        champs attendus, colonnes, vues, tableaux de bord, tables du foyer, et les
        <strong> rôles</strong> qui disent qui voit quoi. Elle se sort et se reprend d'une
        installation à l'autre. Vos <strong>documents</strong> ont leur propre export, et
        vos <strong>comptes</strong> ne voyagent jamais — un rôle est une étiquette, pas
        une personne.
      </p>

      <Section titre={t("Emporter la configuration")} icone={Download}>
        <label style={caseStyle}>
          <input type="checkbox" checked={avecDonnees}
                 onChange={(e) => setAvecDonnees(e.target.checked)} />
          {t("Emporter aussi le contenu des tables du foyer (membres, véhicules…)")}
        </label>
        <p style={aide}>
          {t("À cocher pour déménager votre installation, à laisser décoché pour publier un modèle : ces lignes sont des données personnelles, pas de la structure.")}
        </p>
        <button onClick={telecharger} style={boutonPrimaire}>
          <Download size={14} />
          {t("Télécharger le fichier")}
        </button>
      </Section>

      <Section titre={t("Partir d'un modèle")} icone={PackageOpen}>
        <p style={aide}>
          Chaque foyer range à peu près les mêmes choses. Ces modèles sont prévus pour être
          <strong> élagués</strong> : retirer une catégorie inutile prend dix secondes,
          inventer celle qui manque en prend dix.
        </p>
        {modeles.map((modele) => (
          <div key={modele.cle} style={carte}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{t(modele.libelle)}</div>
              <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 3, lineHeight: 1.5 }}>
                {t(modele.description)}
              </div>
              <div className="tabular" style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 5 }}>
                {modele.categories} catégories · {modele.regles} règles de lecture ·{" "}
                {modele.tables} table{modele.tables > 1 ? "s" : ""}
              </div>
            </div>
            <button onClick={() => importer({ modele: modele.cle })} disabled={envoi}
                    style={boutonSecondaire}>
              Appliquer
            </button>
          </div>
        ))}
      </Section>

      <Section titre={t("Reprendre une configuration")} icone={Upload}>
        <p style={aide}>
          {t("Le fichier exporté depuis une autre installation de HomeGED.")}
        </p>
        <input ref={fichier} type="file" accept="application/json,.json"
               onChange={choisirFichier} style={{ display: "none" }} />
        <button onClick={() => fichier.current?.click()} disabled={envoi} style={boutonPrimaire}>
          <Upload size={14} />
          Choisir un fichier
        </button>
      </Section>

      <div style={{
        display: "flex", gap: 9, padding: "10px 12px", borderRadius: "var(--radius)",
        background: remplacer ? "var(--brick-soft)" : "var(--bg-panel-alt)",
        border: `1px solid ${remplacer ? "var(--brick)" : "var(--line)"}`,
        marginTop: 6,
      }}>
        <AlertTriangle size={15} color={remplacer ? "var(--brick)" : "var(--ink-faint)"}
                       style={{ flexShrink: 0, marginTop: 1 }} />
        <div style={{ fontSize: 12, color: "var(--ink-soft)", lineHeight: 1.55 }}>
          <label style={{ ...caseStyle, marginBottom: 4 }}>
            <input type="checkbox" checked={remplacer}
                   onChange={(e) => setRemplacer(e.target.checked)} />
            <strong style={{ color: "var(--ink)" }}>{t("Remplacer la configuration existante")}</strong>
          </label>
          Décoché, l'import <strong>complète</strong> : ce qui porte déjà le même nom est
          laissé intact, seul ce qui manque est ajouté — on essaie sans rien perdre.
          Coché, le classement actuel est effacé d'abord ; refusé s'il reste des documents,
          dont le classement disparaîtrait sous eux.
        </div>
      </div>

      {envoi && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginTop: 14 }}>
          {t("Application en cours…")}
        </div>
      )}

      {bilan && <Bilan bilan={bilan} />}

      {erreur && (
        <div style={{
          marginTop: 14, padding: "9px 12px", borderRadius: "var(--radius)",
          background: "var(--brick-soft)", color: "var(--brick)", fontSize: 12.5,
        }}>
          {erreur}
        </div>
      )}
    </div>
  );
}

/**
 * Ce que l'import a réellement fait. Créer une table n'étant pas une opération
 * que la base sait défaire, un import ne peut pas être tout ou rien : le compte
 * rendu dit donc exactement ce qui est passé, échecs compris.
 */
function Bilan({ bilan }) {
  const lignes = [
    ["categories", t("catégories")], ["jeux_extraction", t("jeux de règles de lecture")],
    ["champs_attendus", "champs attendus"], ["colonnes", t("colonnes de tableau")],
    ["vues", "vues"], ["roles", t("rôles et droits")],
    ["tableaux_de_bord", t("tableaux de bord")],
    ["tables_donnees", t("tables du foyer")], ["lignes", t("lignes de table")],
    ["reglages", t("réglages")],
  ].filter(([cle]) => bilan[cle] > 0);

  return (
    <div style={{
      marginTop: 16, padding: "12px 14px", borderRadius: "var(--radius)",
      background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
    }}>
      <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>
        {lignes.length ? t("Configuration appliquée") : t("Rien à ajouter")}
      </div>
      {lignes.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>
          {t("Tout ce que porte ce fichier existait déjà, sous les mêmes noms.")}
        </div>
      )}
      {lignes.map(([cle, libelle]) => (
        <div key={cle} style={{ fontSize: 12, color: "var(--ink-soft)" }}>
          <span className="tabular" style={{ color: "var(--ink)", fontWeight: 600 }}>
            +{bilan[cle]}
          </span>{" "}
          {libelle}
        </div>
      ))}
      {(bilan.erreurs || []).length > 0 && (
        <div style={{ marginTop: 8, fontSize: 12, color: "var(--brick)" }}>
          {bilan.erreurs.map((texte, i) => <div key={i}>⚠ {texte}</div>)}
        </div>
      )}
      <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 8 }}>
        {t("Rechargez la page pour voir le nouveau classement dans la navigation.")}
      </div>
    </div>
  );
}

function Section({ titre, icone: Icone, children }) {
  return (
    <section style={{ marginBottom: 22 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
        <Icone size={15} color="var(--ink-faint)" />
        <h3 style={{ fontSize: 13.5, margin: 0 }}>{titre}</h3>
      </div>
      {children}
    </section>
  );
}

const aide = { fontSize: 12, color: "var(--ink-faint)", lineHeight: 1.55, margin: "0 0 10px" };
const caseStyle = {
  display: "flex", alignItems: "center", gap: 7, fontSize: 12.5,
  color: "var(--ink-soft)", marginBottom: 6,
};
const carte = {
  display: "flex", alignItems: "center", gap: 12, padding: "11px 13px", marginBottom: 8,
  border: "1px solid var(--line)", borderRadius: "var(--radius)",
};
const boutonPrimaire = {
  display: "inline-flex", alignItems: "center", gap: 7, border: "none",
  background: "var(--accent)", color: "#fff", fontWeight: 600,
  borderRadius: "var(--radius)", padding: "8px 15px", fontSize: 13,
};
const boutonSecondaire = {
  border: "1px solid var(--line-strong)", background: "transparent", color: "var(--ink-soft)",
  borderRadius: "var(--radius)", padding: "7px 13px", fontSize: 12.5, flexShrink: 0,
};
