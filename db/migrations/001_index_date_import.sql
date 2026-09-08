-- 001 — Index sur documents.date_import
--
-- Toutes les listes de documents se terminent par `ORDER BY date_import DESC
-- LIMIT 200` (app/api.py) : sans index, MariaDB trie l'intégralité de la table
-- à chaque appel. Les colonnes categorie_id / fournisseur_id sont déjà
-- indexées par leurs clés étrangères, elles n'ont rien à ajouter ici.
--
-- Sert aussi de première migration de référence : elle valide le mécanisme
-- sur une base déjà en service.

CREATE INDEX IF NOT EXISTS idx_documents_date_import ON documents (date_import);
