import React, { useCallback, useEffect, useRef, useState } from "react";

/**
 * Des colonnes qu'on élargit à la souris (§22.34).
 *
 * Une largeur de colonne dépend de ce qu'on y met et de l'écran qu'on a devant
 * soi : « N° de facture » tient en huit caractères chez l'un et en vingt chez
 * l'autre. Aucun réglage d'administration ne peut décider cela pour tout le
 * monde — c'est un confort propre à un poste, comme la largeur de la
 * navigation (§18.56), et il se range au même endroit : `localStorage`.
 *
 * Le geste est celui qu'on attend d'un tableau : on tire le bord droit d'un
 * en-tête, et un double-clic sur ce bord rend à la colonne sa largeur
 * naturelle. Rien n'est envoyé au serveur : ce que voit un poste ne regarde pas
 * les autres.
 */
const PREFIXE = "homeged.colonnes.";
const LARGEUR_MIN = 60;
const LARGEUR_MAX = 900;

export function useLargeursColonnes(cle) {
  const [largeurs, setLargeurs] = useState(() => lire(cle));
  const glisse = useRef(null);

  useEffect(() => { setLargeurs(lire(cle)); }, [cle]);

  useEffect(() => {
    if (!glisse.current) return undefined;
    const bouger = (e) => {
      const { champ, x, depart } = glisse.current;
      const large = borner(depart + (e.clientX - x));
      setLargeurs((courantes) => ({ ...courantes, [champ]: large }));
    };
    const lacher = () => {
      glisse.current = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setLargeurs((courantes) => { ecrire(cle, courantes); return courantes; });
      window.removeEventListener("mousemove", bouger);
      window.removeEventListener("mouseup", lacher);
    };
    window.addEventListener("mousemove", bouger);
    window.addEventListener("mouseup", lacher);
    return () => {
      window.removeEventListener("mousemove", bouger);
      window.removeEventListener("mouseup", lacher);
    };
  }, [cle, largeurs]);

  /** Le geste de départ, à poser sur la poignée du bord droit d'un en-tête. */
  const commencer = useCallback((champ, evenement, largeurActuelle) => {
    evenement.preventDefault();
    evenement.stopPropagation();   // sans quoi le clic trierait la colonne
    glisse.current = { champ, x: evenement.clientX, depart: largeurActuelle };
    // Pendant le glissé, la sélection de texte transformerait le geste en
    // surlignage de la moitié du tableau.
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    setLargeurs((courantes) => ({ ...courantes }));   // réveille l'effet d'écoute
  }, []);

  /** Rendre à une colonne sa largeur naturelle. */
  const oublier = useCallback((champ) => {
    setLargeurs((courantes) => {
      const suite = { ...courantes };
      delete suite[champ];
      ecrire(cle, suite);
      return suite;
    });
  }, [cle]);

  return { largeurs, commencer, oublier };
}

/**
 * La poignée du bord droit d'un en-tête.
 *
 * Elle déborde de quelques pixels de chaque côté du trait : viser une bordure
 * d'un pixel à la souris est un exercice, pas un geste.
 */
export function PoigneeColonne({ champ, largeur, commencer, oublier }) {
  return (
    <span
      role="separator"
      aria-label={`Ajuster la largeur de la colonne ${champ}`}
      onMouseDown={(e) => commencer(champ, e, largeur || e.currentTarget.parentElement?.offsetWidth || 120)}
      onDoubleClick={(e) => { e.stopPropagation(); oublier(champ); }}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: "absolute", top: 0, right: -3, width: 7, height: "100%",
        cursor: "col-resize", userSelect: "none",
      }}
    />
  );
}

function borner(valeur) {
  return Math.max(LARGEUR_MIN, Math.min(LARGEUR_MAX, Math.round(valeur)));
}

function lire(cle) {
  try {
    const brut = window.localStorage.getItem(PREFIXE + cle);
    const lues = brut ? JSON.parse(brut) : {};
    // On relit ce qu'on a écrit, mais on ne fait pas confiance à ce qu'on
    // relit : un stockage bricolé à la main ne doit pas casser un tableau.
    return Object.fromEntries(Object.entries(lues)
      .filter(([, v]) => Number.isFinite(v) && v >= LARGEUR_MIN && v <= LARGEUR_MAX));
  } catch {
    return {};   // navigation privée, stockage refusé, JSON abîmé
  }
}

function ecrire(cle, largeurs) {
  try {
    window.localStorage.setItem(PREFIXE + cle, JSON.stringify(largeurs));
  } catch {
    /* rien à faire : le réglage vaudra pour cette visite seulement */
  }
}
