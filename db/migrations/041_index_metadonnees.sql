-- Deux index sur les chemins de lecture les plus fréquents (§18.56).
--
-- Ils ne changent rien aujourd'hui — le registre d'essai tient dans une poignée
-- de lignes, MariaDB lit tout séquentiellement plus vite qu'il ne consulterait
-- un index. Ils comptent à partir de quelques milliers de documents, c'est-à-dire
-- au moment précis où l'on n'a plus envie de s'en occuper.
--
-- `sys_metadonnees (cle, valeur)` : trois usages fréquents interrogent les
-- métadonnées **par clé**, sans connaître le document —
--   * la liste des valeurs proposées sous un en-tête de colonne,
--   * les champs filtrables (`SELECT DISTINCT cle`),
--   * le comptage par clé qui déduit les colonnes d'une catégorie.
-- Sans index, chacun parcourt toute la table. La valeur est incluse pour que le
-- filtrage d'une colonne se règle dans l'index, sans revenir aux lignes.
--
-- `sys_documents (date_document)` : c'est le tri d'ouverture naturel d'une
-- catégorie de factures (§18.49), et il portait sur une colonne sans index alors
-- que `date_import`, l'ancien tri en dur, en avait un.
--
-- Ce qui n'est **pas** ajouté, délibérément : un index sur `statut`. Cinq
-- valeurs pour tout le registre, l'optimiseur ne s'en servirait pas.

ALTER TABLE sys_metadonnees ADD INDEX idx_metadonnees_cle (cle, valeur);
ALTER TABLE sys_documents ADD INDEX idx_documents_date_document (date_document);
