import React from "react";
import { api } from "../api";
import ZoneDepot from "./ZoneDepot.jsx";
import { t } from "../lib/langue";

/**
 * Le dépôt à la main d'une fiche simple (§22.1).
 *
 * Une fiche n'a pas de dossier sous `ocr_wait` : **rien n'y entre tout seul**.
 * C'est le sens de cette nature — ce qu'on y range arrive rarement et
 * qu'aucune règle ne saurait lire : un acte notarié, une carte grise, un
 * contrat signé. Il faut donc une porte, et une seule : cette bande.
 */
export default function ZoneDepotFiche({ categorieId, nom, onDepose }) {
  return (
    <ZoneDepot
      invitation={`Glissez un fichier ici pour l'ajouter à « ${nom} »`}
      ariaLabel={`Ajouter un document à « ${nom} »`}
      envoyer={(fichier) => api.deposerDansFiche(categorieId, fichier)}
      succes={(nombre) => (nombre === 1
        ? t("Document reçu. Il apparaîtra ici dans quelques secondes, le temps qu'il soit lu.")
        : `${nombre} documents reçus. Ils apparaîtront ici dans quelques secondes.`)}
      onDepose={onDepose}
    />
  );
}
