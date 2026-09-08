-- 018 — Préfixes de tables : `sys_` et `usr_`
--
-- Le schéma mêlait sans distinction les tables du fonctionnement de
-- l'application et celles des données du foyer. Le préfixe rend la frontière
-- lisible d'un coup d'œil, dans l'écran d'exploration comme dans une console
-- SQL : `sys_` pour ce qui fait tourner l'application, `usr_` pour ce que
-- l'utilisateur gère lui-même.
--
-- `fournisseurs` devient `usr_emetteurs` : la liste des émetteurs est une
-- donnée du foyer, tenue par ses habitants, pas un rouage de l'application.
-- Elle conserve son rôle — regex d'identification, clé étrangère depuis les
-- documents — mais devient modifiable depuis « Base de données ».
--
-- `schema_migrations` n'est pas renommée ici : le mécanisme de migration s'en
-- sert au moment même où la migration s'exécute. Le renommage est fait par le
-- runner lui-même, avant toute lecture (cf. app/migrations.py).

RENAME TABLE categories TO sys_categories;
RENAME TABLE documents TO sys_documents;
RENAME TABLE metadonnees TO sys_metadonnees;
RENAME TABLE regles_extraction TO sys_regles_extraction;
RENAME TABLE regles_champs_categorie TO sys_regles_champs_categorie;
RENAME TABLE utilisateurs TO sys_utilisateurs;
RENAME TABLE roles TO sys_roles;
RENAME TABLE utilisateur_roles TO sys_utilisateur_roles;
RENAME TABLE droits_categorie TO sys_droits_categorie;
RENAME TABLE jobs TO sys_jobs;
RENAME TABLE journal_audit TO sys_journal_audit;
RENAME TABLE vues_enregistrees TO sys_vues_enregistrees;
RENAME TABLE tableaux_de_bord TO sys_tableaux_de_bord;
RENAME TABLE tables_donnees TO sys_tables_donnees;

RENAME TABLE fournisseurs TO usr_emetteurs;

-- Inscription des émetteurs au registre des tables de données : c'est cette
-- inscription qui les rend modifiables depuis l'écran « Base de données ».
INSERT INTO sys_tables_donnees (nom_table, libelle, description, colonne_libelle)
SELECT 'usr_emetteurs', 'Émetteurs',
       'Qui envoie les documents, et la regex qui permet de le reconnaître.', 'nom'
WHERE NOT EXISTS (SELECT 1 FROM sys_tables_donnees WHERE nom_table = 'usr_emetteurs');

-- Les tables de données déjà créées passent de `donnees_` à `usr_`.
RENAME TABLE donnees_vehicules TO usr_vehicules;
UPDATE sys_tables_donnees SET nom_table = CONCAT('usr_', SUBSTRING(nom_table, 9))
WHERE nom_table LIKE 'donnees\_%';
