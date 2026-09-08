-- 002 — Alignement de la base sur db/schema.sql
--
-- Constat du 2026-09-02 : les tables de la base en service ont été créées par
-- `Base.metadata.create_all()` (worker) et non par `db/schema.sql`, qui n'est
-- joué qu'à la première initialisation du volume. Le schéma obtenu diverge sur
-- trois points, dont deux provoquent des bugs visibles :
--
--   1. `texte_ocr` en TEXT (64 Ko) au lieu de LONGTEXT : le texte océrisé d'un
--      document volumineux est tronqué ou rejeté.
--   2. index FULLTEXT `ft_texte_ocr` absent : `GET /documents?q=...` utilise
--      MATCH ... AGAINST et renvoyait une erreur 500.
--   3. contrainte d'unicité `uq_doc_cle` absente sur `metadonnees` : rien
--      n'empêchait deux valeurs pour un même couple (document, clé).
--
-- Le point 3 échouerait si des doublons existaient déjà : le cas échéant, les
-- dédoublonner avant de rejouer la migration (le runner s'arrête sur erreur
-- sans marquer la version comme appliquée).

ALTER TABLE documents MODIFY texte_ocr LONGTEXT NULL;

ALTER TABLE documents ADD FULLTEXT INDEX IF NOT EXISTS ft_texte_ocr (texte_ocr);

ALTER TABLE metadonnees ADD UNIQUE KEY IF NOT EXISTS uq_doc_cle (document_id, cle);
