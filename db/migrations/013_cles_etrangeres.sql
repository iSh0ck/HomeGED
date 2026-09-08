-- 013 — Rétablissement des comportements ON DELETE
--
-- Même cause que la migration 012 : les tables ayant été créées par
-- `create_all()` d'après le modèle Python, les clés étrangères déclarées sans
-- `ondelete=` ont pris le comportement par défaut RESTRICT, là où
-- `db/schema.sql` prévoit ON DELETE SET NULL.
--
-- Conséquences constatées, toutes visibles depuis l'administration :
--   - supprimer une catégorie utilisée par un document échouait ;
--   - supprimer une catégorie ayant des sous-catégories échouait ;
--   - supprimer un émetteur utilisé par un document ou une règle échouait ;
--   - supprimer une règle d'extraction ayant déjà produit une métadonnée
--     échouait — chaque fois avec une erreur 500 incompréhensible.
--
-- Le comportement voulu est SET NULL : supprimer une catégorie déclasse ses
-- documents, elle ne les emporte pas. `DROP FOREIGN KEY IF EXISTS` couvre les
-- deux nommages possibles, selon que la table vient de create_all (nom
-- automatique `*_ibfk_n`) ou de schema.sql (nom explicite).

ALTER TABLE documents DROP FOREIGN KEY IF EXISTS documents_ibfk_1;
ALTER TABLE documents DROP FOREIGN KEY IF EXISTS fk_documents_categorie;
ALTER TABLE documents ADD CONSTRAINT fk_documents_categorie FOREIGN KEY (categorie_id) REFERENCES categories(id) ON DELETE SET NULL;

ALTER TABLE documents DROP FOREIGN KEY IF EXISTS documents_ibfk_2;
ALTER TABLE documents DROP FOREIGN KEY IF EXISTS fk_documents_fournisseur;
ALTER TABLE documents ADD CONSTRAINT fk_documents_fournisseur FOREIGN KEY (fournisseur_id) REFERENCES fournisseurs(id) ON DELETE SET NULL;

ALTER TABLE categories DROP FOREIGN KEY IF EXISTS categories_ibfk_1;
ALTER TABLE categories DROP FOREIGN KEY IF EXISTS fk_categories_parent;
ALTER TABLE categories ADD CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL;

ALTER TABLE metadonnees DROP FOREIGN KEY IF EXISTS metadonnees_ibfk_2;
ALTER TABLE metadonnees DROP FOREIGN KEY IF EXISTS fk_metadonnees_regle;
ALTER TABLE metadonnees ADD CONSTRAINT fk_metadonnees_regle FOREIGN KEY (regle_id) REFERENCES regles_extraction(id) ON DELETE SET NULL;

ALTER TABLE regles_extraction DROP FOREIGN KEY IF EXISTS regles_extraction_ibfk_1;
ALTER TABLE regles_extraction DROP FOREIGN KEY IF EXISTS fk_regles_fournisseur;
ALTER TABLE regles_extraction ADD CONSTRAINT fk_regles_fournisseur FOREIGN KEY (fournisseur_id) REFERENCES fournisseurs(id) ON DELETE SET NULL;
