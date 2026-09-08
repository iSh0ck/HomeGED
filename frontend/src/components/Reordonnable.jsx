import React, { useState } from "react";
import { GripVertical } from "lucide-react";
import { t } from "../lib/langue";

/**
 * Réordonner une liste à la main, par glisser-déposer (§18.46).
 *
 * Quatre écrans d'administration réglaient leur ordre d'affichage avec deux
 * flèches par ligne : un clic déplaçait d'un rang. Descendre une catégorie de
 * huit places demandait huit clics, et autant d'allers-retours à l'écran pour
 * vérifier où l'on en était. L'ordre est une chose qu'on voit ; il doit se
 * régler en le montrant.
 *
 * Ce module ne dessine pas la liste — les écrans concernés n'ont pas la même
 * forme (un tableau, une suite de blocs, une rangée d'étiquettes). Il fournit
 * les comportements à répandre sur ce qu'ils dessinent déjà :
 *
 *   const reordre = useReordonnable({ nombre, onDeplacer });
 *   <tr {...reordre.proprietesLigne(i)}>
 *     <td><PoigneeOrdre {...reordre.proprietesPoignee(i, ligne.nom)} /></td>
 *
 * Deux choix méritent d'être dits :
 *
 * * **La poignée seule est saisissable**, pas la ligne entière. On garde ainsi
 *   la sélection du texte et les boutons de la ligne, et l'on voit du premier
 *   coup d'œil ce qui se déplace.
 * * **Les flèches du clavier font le même travail** que le glissement, depuis
 *   cette même poignée. Un glisser-déposer sans équivalent au clavier retire
 *   une fonction à qui ne se sert pas d'une souris ; la poignée remplace les
 *   deux boutons d'avant sans rien retirer.
 *
 * `groupeDe` sert aux listes qui n'en sont pas vraiment une : les vues sont
 * rangées par catégorie de rattachement, les catégories par parent. On ne
 * déplace qu'à l'intérieur de son groupe — sortir une vue de sa catégorie en la
 * faisant glisser serait une tout autre décision, prise par mégarde.
 */
export function useReordonnable({ nombre, onDeplacer, groupeDe = () => null, actif = true }) {
  const [tire, setTire] = useState(null);
  const [survol, setSurvol] = useState(null);

  const accepte = (index) =>
    actif && tire !== null && tire !== index && groupeDe(tire) === groupeDe(index);

  function terminer() {
    setTire(null);
    setSurvol(null);
  }

  function styleLigne(index) {
    if (tire === index) return { opacity: 0.4 };
    if (survol !== index || !accepte(index)) return {};
    // Trait d'insertion posé en ombre intérieure : sur un tableau à bordures
    // fusionnées, une vraie bordure décalerait les lignes au survol.
    return tire > index
      ? { boxShadow: "inset 0 2px 0 0 var(--accent)" }
      : { boxShadow: "inset 0 -2px 0 0 var(--accent)" };
  }

  function proprietesLigne(index) {
    return {
      onDragOver: (evenement) => {
        if (!accepte(index)) return;
        evenement.preventDefault();          // sans cela, le dépôt est refusé
        evenement.dataTransfer.dropEffect = "move";
        if (survol !== index) setSurvol(index);
      },
      onDragLeave: () => setSurvol((actuel) => (actuel === index ? null : actuel)),
      onDrop: (evenement) => {
        evenement.preventDefault();
        if (accepte(index)) onDeplacer(tire, index);
        terminer();
      },
      style: styleLigne(index),
    };
  }

  function proprietesPoignee(index, libelle = "") {
    return {
      libelle,
      draggable: actif,
      onDragStart: (evenement) => {
        if (!actif) return;
        evenement.dataTransfer.effectAllowed = "move";
        // Firefox ignore un glissement dont rien n'a été transféré.
        evenement.dataTransfer.setData("text/plain", String(index));
        setTire(index);
      },
      onDragEnd: terminer,
      onKeyDown: (evenement) => {
        const sens = evenement.key === "ArrowUp" ? -1 : evenement.key === "ArrowDown" ? 1 : 0;
        if (!sens || !actif) return;
        evenement.preventDefault();
        const cible = index + sens;
        if (cible < 0 || cible >= nombre) return;
        if (groupeDe(cible) !== groupeDe(index)) return;
        onDeplacer(index, cible);
      },
    };
  }

  return { proprietesLigne, proprietesPoignee, tire, survol };
}

/**
 * La poignée. Un bouton, et non une simple icône : c'est ce qui la rend
 * atteignable au clavier, où elle répond aux flèches.
 */
export function PoigneeOrdre({ libelle, style, ...props }) {
  return (
    <button
      type="button"
      aria-label={libelle ? `Déplacer ${libelle}` : t("Déplacer")}
      title={t("Glisser pour déplacer — ou flèches haut et bas")}
      {...props}
      style={{
        display: "flex",
        alignItems: "center",
        border: "none",
        background: "transparent",
        color: "var(--ink-faint)",
        padding: 2,
        cursor: "grab",
        ...style,
      }}
    >
      <GripVertical size={14} />
    </button>
  );
}

/**
 * Réordonne un tableau en déplaçant l'élément `de` à la place `vers`.
 * Extrait ici parce que les six écrans en ont besoin, et qu'une permutation
 * (échanger deux éléments) ne donne pas le même résultat qu'un déplacement dès
 * que l'on saute plus d'un rang.
 */
export function deplacer(elements, de, vers) {
  const copie = [...elements];
  const [element] = copie.splice(de, 1);
  copie.splice(vers, 0, element);
  return copie;
}
