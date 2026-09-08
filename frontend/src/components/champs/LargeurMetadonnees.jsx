import React, { useCallback, useEffect, useRef, useState } from "react";
import { t } from "../../lib/langue";

/**
 * La colonne des métadonnées, qu'on élargit à la souris (§22.69).
 *
 * La fiche est partagée en deux : le document et ses pièces à gauche, les
 * métadonnées à droite, sur 380 px fixes. C'est une largeur choisie pour tout le
 * monde alors qu'elle dépend de ce qu'un type déclare — quatre champs courts s'y
 * perdent, douze champs dont un commentaire y étouffent. Le trait qui les sépare
 * se tire donc, comme le bord d'une colonne de tableau.
 *
 * Rien n'est envoyé au serveur : ce confort dépend de l'écran qu'on a devant
 * soi, il se range dans `localStorage` comme les largeurs de colonnes (§22.34).
 */
const CLE = "homeged.largeurMetadonnees";
const MIN = 240;
const MAX = 900;
const DEFAUT = 380;

export function useLargeurMetadonnees() {
  const [largeur, setLargeur] = useState(lire);
  const glisse = useRef(null);

  // Les écouteurs sont posés **une fois**, et se taisent tant qu'aucun geste
  // n'est en cours. Les poser au début du glissé demanderait de réveiller
  // l'effet par un changement d'état ; or reposer la même largeur ne provoque
  // aucun rendu — React s'en abstient quand la valeur est identique — et le
  // glissé restait sans effet. Le défaut existait, un test l'a montré.
  useEffect(() => {
    const bouger = (evenement) => {
      if (!glisse.current) return;
      const { x, depart } = glisse.current;
      // La colonne est ancrée à droite : tirer le trait vers la gauche
      // l'élargit, et c'est le geste qu'on attend d'une séparation.
      setLargeur(borner(depart + (x - evenement.clientX)));
    };
    const lacher = () => {
      if (!glisse.current) return;
      glisse.current = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setLargeur((courante) => { ecrire(courante); return courante; });
    };
    window.addEventListener("mousemove", bouger);
    window.addEventListener("mouseup", lacher);
    return () => {
      window.removeEventListener("mousemove", bouger);
      window.removeEventListener("mouseup", lacher);
    };
  }, []);

  const commencer = useCallback((evenement) => {
    evenement.preventDefault();
    glisse.current = { x: evenement.clientX, depart: lire() };
    // Pendant le glissé, la sélection de texte transformerait le geste en
    // surlignage de la moitié de la fiche.
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
  }, []);

  /** Rendre à la colonne sa largeur d'origine. */
  const oublier = useCallback(() => {
    setLargeur(DEFAUT);
    ecrire(DEFAUT);
  }, []);

  return { largeur, commencer, oublier };
}

/**
 * Le trait qui sépare le document de ses métadonnées, tirable.
 *
 * Il déborde de quelques pixels de part et d'autre : viser une bordure d'un
 * pixel à la souris est un exercice, pas un geste. Un double-clic rend la
 * largeur d'origine.
 */
export function PoigneeMetadonnees({ commencer, oublier }) {
  return (
    <div
      role="separator"
      aria-label={t("Ajuster la largeur des métadonnées")}
      title={t("Tirer pour élargir les métadonnées — double-clic pour la largeur d'origine")}
      onMouseDown={commencer}
      onDoubleClick={oublier}
      style={{
        position: "absolute", top: 0, bottom: 0, left: -4, width: 9,
        cursor: "col-resize", userSelect: "none", zIndex: 2,
      }}
    />
  );
}

function borner(valeur) {
  return Math.max(MIN, Math.min(MAX, Math.round(valeur)));
}

function lire() {
  try {
    const brut = Number(window.localStorage.getItem(CLE));
    return Number.isFinite(brut) && brut >= MIN && brut <= MAX ? brut : DEFAUT;
  } catch {
    return DEFAUT;   // navigation privée, stockage refusé
  }
}

function ecrire(valeur) {
  try {
    window.localStorage.setItem(CLE, String(valeur));
  } catch {
    /* le confort ne se garde pas : il se règlera de nouveau, et c'est tout */
  }
}
