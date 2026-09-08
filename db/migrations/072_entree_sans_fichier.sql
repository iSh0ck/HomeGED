-- Une entrée sans fichier (§22.7).
--
-- Une fiche simple (§22.1) sert à noter ce qu'un foyer garde et qui n'a pas
-- toujours de papier : un contrat verbal, une garantie annoncée au téléphone, le
-- code d'un cadenas, la référence d'un compteur. Jusqu'ici il fallait un fichier
-- pour créer une ligne — on n'avait donc rien où l'écrire.
--
-- Le document devient l'unité de **ce que l'on sait**, et le fichier une pièce
-- parmi d'autres (§22.2) — éventuellement aucune. Les deux colonnes qui
-- l'imposaient deviennent facultatives ; tout le reste (métadonnées, champs
-- attendus, droits, corbeille, recherche) fonctionne à l'identique, parce que
-- rien de tout cela ne dépendait du fichier.
--
-- `hash_sha256` reste unique : MySQL admet plusieurs NULL dans un index unique,
-- et deux entrées sans fichier ne sont pas des doublons l'une de l'autre.

ALTER TABLE sys_documents MODIFY COLUMN chemin_stockage VARCHAR(500) NULL;
ALTER TABLE sys_documents MODIFY COLUMN hash_sha256 VARCHAR(64) NULL;
