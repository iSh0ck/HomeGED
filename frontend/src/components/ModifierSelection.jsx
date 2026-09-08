import React, { useEffect, useState } from "react";
import { api } from "../api";
import Modal from "./Modal.jsx";
import ModifierDocument from "./ModifierDocument.jsx";
import { t } from "../lib/langue";

/**
 * Modification en série d'une sélection de documents (§18.4).
 *
 * On coche plusieurs fiches, on ouvre la modification, et l'on avance de l'une à
 * l'autre : enregistrer passe à la suivante, sans revenir au tableau ni
 * rechercher la fiche d'après. C'est le geste que réclame une reprise de
 * classement — dix factures dont il faut corriger le titulaire.
 *
 * Les fiches sont chargées **une par une**, au moment d'y arriver : leur état
 * (verrou compris) ne doit pas dater du moment où l'on a coché la case, mais de
 * celui où l'on s'apprête à écrire.
 */
export default function ModifierSelection({
  ids, categories, onFerme, onEnregistre,
}) {
  const [rang, setRang] = useState(0);
  const [doc, setDoc] = useState(null);
  const [erreur, setErreur] = useState(null);
  // Les fiches réellement enregistrées, et non leur simple nombre : une fiche
  // passée fait avancer le rang sans rien changer, et un décompte ne saurait
  // plus lesquelles ont été traitées.
  const [faites, setFaites] = useState([]);

  const identifiant = ids[rang];

  useEffect(() => {
    if (identifiant === undefined) return undefined;
    let annule = false;
    setDoc(null);
    setErreur(null);
    api
      .document(identifiant)
      .then((d) => { if (!annule) setDoc(d); })
      .catch((e) => { if (!annule) setErreur(e.message); });
    return () => { annule = true; };
  }, [identifiant]);

  function suivante(deja = faites) {
    if (rang + 1 >= ids.length) onFerme(deja);
    else setRang(rang + 1);
  }

  if (identifiant === undefined) return null;

  if (erreur) {
    return (
      <Modal titre={t("Fiche illisible")} onClose={() => onFerme(faites)} width={420}>
        <div style={{ fontSize: 13, color: "var(--ink-soft)", marginTop: 6, lineHeight: 1.55 }}>
          {erreur}
          <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-faint)" }}>
            {t("Cette fiche a peut-être été supprimée depuis que vous l'avez sélectionnée.")}
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <button onClick={() => onFerme(faites)} style={bouton}>{t("Arrêter")}</button>
          {rang + 1 < ids.length && (
            <button onClick={() => suivante()} style={bouton}>{t("Passer à la suivante")}</button>
          )}
        </div>
      </Modal>
    );
  }

  if (!doc) {
    return (
      <Modal titre={`Modifier — fiche ${rang + 1} sur ${ids.length}`}
             onClose={() => onFerme(faites)} width={520}>
        <div style={{ fontSize: 13, color: "var(--ink-faint)", padding: "10px 0" }}>
          {t("Chargement de la fiche…")}
        </div>
      </Modal>
    );
  }

  return (
    <ModifierDocument
      key={doc.id}
      doc={doc}
      categories={categories}
      progression={{ rang: rang + 1, total: ids.length }}
      onPasser={() => suivante()}
      onFerme={() => onFerme(faites)}
      onEnregistre={() => {
        const augmentee = [...faites, doc.id];
        setFaites(augmentee);
        onEnregistre?.();
        suivante(augmentee);
      }}
    />
  );
}

const bouton = {
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "8px 14px", fontSize: 13,
};
