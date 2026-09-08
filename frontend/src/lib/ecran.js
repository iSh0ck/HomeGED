import { useEffect, useState } from "react";

/**
 * La taille de l'écran, pour les mises en page qui ne peuvent pas s'en passer
 * (§22.52).
 *
 * L'interface est écrite en styles **en ligne** : une requête média CSS ne peut
 * donc pas les corriger, elle perdrait toujours en priorité. On lit la largeur
 * ici, et les composants choisissent leur disposition — c'est plus verbeux
 * qu'une feuille de style, mais c'est la seule façon honnête dans ce projet.
 *
 * Deux seuils, et pas un de plus. Multiplier les paliers donne des mises en page
 * que personne ne voit jamais et que personne ne teste :
 *
 *   * **compact** (moins de 820 px) — téléphone, tablette en portrait : la
 *     navigation se referme en tiroir, les tableaux défilent, les fenêtres
 *     prennent tout l'écran ;
 *   * **étroit** (moins de 1180 px) — tablette en paysage, petit portable : la
 *     navigation reste, le panneau de document passe dessous plutôt qu'à côté.
 */
export const SEUIL_COMPACT = 820;
export const SEUIL_ETROIT = 1180;

function mesurer() {
  if (typeof window === "undefined") return { largeur: 1400, compact: false, etroit: false };
  const largeur = window.innerWidth;
  return { largeur, compact: largeur < SEUIL_COMPACT, etroit: largeur < SEUIL_ETROIT };
}

export function useEcran() {
  const [ecran, setEcran] = useState(mesurer);

  useEffect(() => {
    // `resize` plutôt que deux `matchMedia` : on veut aussi la largeur, et une
    // rotation de tablette change les deux seuils d'un coup.
    const relire = () => setEcran(mesurer());
    window.addEventListener("resize", relire);
    // `orientationchange` : sur iOS, `resize` arrive parfois avant que la
    // nouvelle largeur ne soit connue.
    window.addEventListener("orientationchange", relire);
    relire();
    return () => {
      window.removeEventListener("resize", relire);
      window.removeEventListener("orientationchange", relire);
    };
  }, []);

  // `data-ecran` sur la racine : les rares règles de la feuille de style qui
  // dépendent de la taille (hauteur des cellules, épaisseur des barres) peuvent
  // s'y accrocher sans que chaque composant ait à les porter.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.ecran = ecran.compact
      ? "compact" : ecran.etroit ? "etroit" : "large";
  }, [ecran.compact, ecran.etroit]);

  return ecran;
}
