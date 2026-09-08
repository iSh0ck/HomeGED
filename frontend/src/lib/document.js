/**
 * Libellé lisible d'un document.
 *
 * Le nom technique du fichier n'est pas une information utile à l'utilisateur
 * (§12 du cahier des charges) : on identifie un document par ce qui en a été
 * extrait — son émetteur, sa catégorie, sa date. Le nom de fichier reste en
 * base et sert toujours au téléchargement du PDF, mais il n'est plus ce qui
 * désigne un document dans l'interface.
 */
export function libelleDocument(doc) {
  if (!doc) return "";
  // L'émetteur n'est plus un champ du document (§21.12) : c'est une métadonnée
  // comme une autre, et il se lit dans sa colonne. Le libellé dit ce que le
  // document **est** — sa sorte et sa date.
  const parties = [doc.categorie, formaterDate(doc.date_document)].filter(Boolean);
  if (parties.length) return parties.join(" · ");
  // document non classé et sans date extraite : rien de parlant à afficher
  return `Document nº${doc.id}`;
}

/** Complément d'identification, quand le libellé principal reste vague. */
export function sousTitreDocument(doc) {
  if (!doc) return "";
  return doc.date_import ? `Importé le ${formaterDate(doc.date_import.slice(0, 10))}` : "";
}

export function formaterDate(valeur) {
  if (!valeur) return "";
  const [a, m, j] = String(valeur).split("-");
  return j ? `${j}/${m}/${a}` : String(valeur);
}
