-- 003 — Référentiel par défaut (catégories, émetteurs, règles, rôle Foyer)
--
-- Même cause que la migration 002 : la base ayant été créée par create_all(),
-- les données d'exemple de `db/schema.sql` n'ont jamais été insérées. Sans
-- elles, le classement automatique et l'extraction de métadonnées ne font
-- rien du tout (aucune regex à appliquer).
--
-- Chaque insertion est gardée par un NOT EXISTS sur sa propre ligne : la
-- migration est donc rejouable et ne touche pas à un référentiel déjà
-- personnalisé par l'utilisateur.

INSERT INTO fournisseurs (nom, regex_identification)
SELECT 'EDF', '(?i)\\bEDF\\b' WHERE NOT EXISTS (SELECT 1 FROM fournisseurs WHERE nom = 'EDF');

INSERT INTO fournisseurs (nom, regex_identification)
SELECT 'Impots.gouv', '(?i)direction g[ée]n[ée]rale des finances publiques' WHERE NOT EXISTS (SELECT 1 FROM fournisseurs WHERE nom = 'Impots.gouv');

INSERT INTO fournisseurs (nom, regex_identification)
SELECT 'Free Mobile', '(?i)\\bfree\\s*mobile\\b' WHERE NOT EXISTS (SELECT 1 FROM fournisseurs WHERE nom = 'Free Mobile');

INSERT INTO categories (nom, regex_identification, priorite)
SELECT 'Factures', '(?i)\\bfacture\\b', 10 WHERE NOT EXISTS (SELECT 1 FROM categories WHERE nom = 'Factures');

INSERT INTO categories (nom, regex_identification, priorite)
SELECT 'Impôts', '(?i)direction g[ée]n[ée]rale des finances publiques|avis d.imposition', 10 WHERE NOT EXISTS (SELECT 1 FROM categories WHERE nom = 'Impôts');

INSERT INTO categories (nom, regex_identification, priorite)
SELECT 'Banque', '(?i)relev[ée] de compte|IBAN', 20 WHERE NOT EXISTS (SELECT 1 FROM categories WHERE nom = 'Banque');

INSERT INTO categories (nom, regex_identification, priorite)
SELECT 'Courriers', NULL, 200 WHERE NOT EXISTS (SELECT 1 FROM categories WHERE nom = 'Courriers');

INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite)
SELECT 'Numéro de facture', 'numero_facture', 'Facture\\s*n[°o]?\\s*[:\\-]?\\s*([A-Z0-9\\-\\/]{4,20})', 'texte', 10 WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE champ_cible = 'numero_facture');

INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite)
SELECT 'Montant TTC', 'montant_ttc', 'Total\\s*TTC\\s*[:\\-]?\\s*([0-9]+[,\\.][0-9]{2})\\s*€?', 'montant', 20 WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE champ_cible = 'montant_ttc');

INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite)
SELECT 'Date document (jj/mm/aaaa)', 'date_document', '\\b([0-3][0-9]/[0-1][0-9]/[0-9]{4})\\b', 'date', 30 WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE champ_cible = 'date_document');

INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite)
SELECT 'IBAN', 'iban', '\\b(FR[0-9]{2}[\\s]?[0-9A-Z]{4}[\\s]?[0-9A-Z]{4}[\\s]?[0-9A-Z]{4}[\\s]?[0-9A-Z]{4}[\\s]?[0-9A-Z]{3})\\b', 'texte', 40 WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE champ_cible = 'iban');

INSERT INTO roles (nom, description)
SELECT 'Foyer', 'Accès à toutes les catégories du foyer' WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nom = 'Foyer');

INSERT INTO droits_categorie (role_id, categorie_id, peut_voir, peut_modifier)
SELECT r.id, c.id, TRUE, TRUE FROM roles r CROSS JOIN categories c WHERE r.nom = 'Foyer' AND NOT EXISTS (SELECT 1 FROM droits_categorie d WHERE d.role_id = r.id AND d.categorie_id = c.id);
