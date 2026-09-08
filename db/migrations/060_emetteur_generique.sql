-- L'émetteur cesse d'être une exception (§21.12).
--
-- Tout le reste de ce que désigne un document — un membre du foyer, un
-- véhicule — passe par le mécanisme générique : une **table du foyer**, un
-- **champ attendu** qui y puise, une valeur `usr_table:id` dans les métadonnées.
-- L'émetteur, lui, avait sa colonne à part sur `sys_documents`, son modèle, son
-- champ de filtre, sa branche dans la recherche, son point de groupement, et
-- même une case sur les jeux de règles. Deux mécanismes pour la même idée : le
-- générique, et celui d'avant.
--
-- Il n'y en a plus qu'un. `usr_emetteurs` reste ce qu'elle est — une table du
-- foyer, modifiable depuis l'administration comme les autres — et un type qui
-- veut un émetteur déclare un champ qui y puise. Il gagne au passage ce que
-- l'exception ne savait pas faire : la déduction depuis le texte, le rattachement
-- par fiche de liaison, le repli en arborescence, les droits par branche.
--
-- Cette migration **convertit ce qui existait**, sans rien perdre :
--   * chaque document qui portait un émetteur reçoit la métadonnée `emetteur`
--     avec la référence `usr_emetteurs:<id>` ;
--   * les types concernés reçoivent le champ attendu correspondant, avec sa
--     déduction — c'est elle qui remplace « l'émetteur posé par le jeu de
--     règles », en mieux : elle lit le document au lieu de faire confiance au jeu ;
--   * les colonnes, tris, critères de vue, indicateurs, conditions
--     d'automatisation et droits par branche qui visaient `fournisseur` visent
--     désormais `meta:emetteur`.
--
-- Les deux colonnes `fournisseur_id` disparaissent en dernier : tant qu'elles
-- existent, un code oublié pourrait continuer d'y écrire sans que rien ne le dise.

-- 1. La métadonnée, pour ce qui en portait un.
INSERT INTO sys_metadonnees (document_id, cle, valeur)
SELECT d.id, 'emetteur', CONCAT('usr_emetteurs:', d.fournisseur_id)
FROM sys_documents d
WHERE d.fournisseur_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_metadonnees m
                  WHERE m.document_id = d.id AND m.cle = 'emetteur');

-- 2. Le champ attendu sur les types concernés, s'il n'y est pas déjà. La
--    déduction « une seule colonne suffit » : un nom d'émetteur ne se confond
--    pas avec autre chose dans un document, contrairement à un nom de personne.
INSERT INTO sys_regles_champs_categorie
    (categorie_id, champ, libelle, obligatoire, source_table, sources, deduction, ordre)
SELECT DISTINCT d.categorie_id, 'meta:emetteur', 'Émetteur', FALSE,
       'usr_emetteurs', 'usr_emetteurs', 'une', 15
FROM sys_documents d
WHERE d.categorie_id IS NOT NULL
  AND d.fournisseur_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM sys_regles_champs_categorie r
                  WHERE r.categorie_id = d.categorie_id AND r.champ = 'meta:emetteur');

-- 3. Ce qui visait le champ codé en dur vise maintenant la métadonnée.
--
--    Le renommage peut **entrer en collision** : un type peut déjà porter une
--    colonne « meta:emetteur » posée à la main, et les colonnes sont uniques par
--    (type, champ). Dans ce cas la ligne d'avant est retirée plutôt que renommée
--    — celle que l'administrateur a placée lui-même a la priorité, avec sa
--    position et son intitulé.
DELETE c FROM sys_colonnes_categorie c
 WHERE c.champ = 'fournisseur'
   AND EXISTS (SELECT 1 FROM (SELECT categorie_id FROM sys_colonnes_categorie
                              WHERE champ = 'meta:emetteur') AS deja
               WHERE deja.categorie_id = c.categorie_id);
UPDATE sys_colonnes_categorie SET champ = 'meta:emetteur' WHERE champ = 'fournisseur';
UPDATE sys_categories SET tri_champ = 'meta:emetteur' WHERE tri_champ = 'fournisseur';
-- Même précaution pour les branches, uniques par (rôle, champ, valeur).
DELETE b FROM sys_droits_branche b
 WHERE b.champ = 'fournisseur'
   AND EXISTS (SELECT 1 FROM (SELECT role_id, valeur FROM sys_droits_branche
                              WHERE champ = 'meta:emetteur') AS deja
               WHERE deja.role_id = b.role_id AND deja.valeur = b.valeur);
UPDATE sys_droits_branche SET champ = 'meta:emetteur' WHERE champ = 'fournisseur';
-- Les critères et indicateurs sont du JSON : le remplacement porte sur la paire
-- `"champ": "fournisseur"`, qui ne peut désigner que cela.
UPDATE sys_vues_enregistrees
   SET criteres = REPLACE(criteres, '"champ": "fournisseur"', '"champ": "meta:emetteur"')
 WHERE criteres LIKE '%"champ": "fournisseur"%';
UPDATE sys_vues_enregistrees
   SET criteres = REPLACE(criteres, '"champ":"fournisseur"', '"champ":"meta:emetteur"')
 WHERE criteres LIKE '%"champ":"fournisseur"%';
UPDATE sys_tableaux_de_bord
   SET widgets = REPLACE(widgets, '"champ": "fournisseur"', '"champ": "meta:emetteur"')
 WHERE widgets LIKE '%"champ": "fournisseur"%';
UPDATE sys_tableaux_de_bord
   SET widgets = REPLACE(widgets, '"champ":"fournisseur"', '"champ":"meta:emetteur"')
 WHERE widgets LIKE '%"champ":"fournisseur"%';
UPDATE sys_automatisations
   SET conditions = REPLACE(conditions, '"champ": "fournisseur"', '"champ": "meta:emetteur"')
 WHERE conditions LIKE '%"champ": "fournisseur"%';
UPDATE sys_automatisations
   SET conditions = REPLACE(conditions, '"champ":"fournisseur"', '"champ":"meta:emetteur"')
 WHERE conditions LIKE '%"champ":"fournisseur"%';

-- 3 bis. La table est inscrite comme table du foyer si elle ne l'était pas :
--        c'est ce qui la rend modifiable depuis « Base de données » et utilisable
--        comme source d'un champ attendu.
INSERT INTO sys_tables_donnees (nom_table, libelle, description, colonne_libelle,
                                colonnes_identifiantes)
SELECT 'usr_emetteurs', 'Émetteurs',
       'Qui envoie les documents : fournisseurs, administrations, banques.',
       'nom', 'nom'
WHERE NOT EXISTS (SELECT 1 FROM sys_tables_donnees WHERE nom_table = 'usr_emetteurs');

-- 4. Les colonnes disparaissent. `usr_emetteurs` reste : c'est une table du
--    foyer, et elle le redevient pleinement.
ALTER TABLE sys_documents
    DROP FOREIGN KEY fk_documents_fournisseur,
    DROP COLUMN fournisseur_id;

ALTER TABLE sys_profils_extraction
    DROP FOREIGN KEY fk_profils_fournisseur,
    DROP COLUMN fournisseur_id;
