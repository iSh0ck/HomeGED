-- Le titulaire d'un document désigne une personne du foyer, pas un compte (§18.13).
--
-- Les comptes de connexion étaient proposés comme source de valeurs. C'était une
-- exception codée en dur : `sys_utilisateurs` n'est pas une table de données, ses
-- colonnes ne se règlent pas depuis l'administration, et un autre foyer aurait
-- hérité de ce couplage sans pouvoir y toucher. Or les deux notions ne se
-- recouvrent pas : un enfant reçoit des factures sans avoir de compte, et un
-- compte peut n'être qu'un accès partagé.
--
-- Trois corrections, dans l'ordre où elles comptent :

-- 1. Le champ « titulaire » ne puise plus que dans les membres du foyer.
UPDATE sys_regles_champs_categorie
   SET sources = 'usr_membres', source_table = 'usr_membres'
 WHERE champ = 'meta:titulaire';

-- 2. Les valeurs déjà enregistrées suivent, quand la personne existe des deux
--    côtés : on rapproche sur le prénom **et** le nom, un nom seul ne désignant
--    personne dans une famille. Celles qui ne trouvent pas leur membre restent
--    telles quelles — mieux vaut une valeur à reprendre à la main qu'une valeur
--    rattachée à la mauvaise personne.
UPDATE sys_metadonnees AS m
  JOIN sys_utilisateurs AS u ON m.valeur = CONCAT('sys_utilisateurs:', u.id)
  JOIN usr_membres AS mb ON mb.prenom = u.prenom AND mb.nom = u.nom
   SET m.valeur = CONCAT('usr_membres:', mb.id);

-- 3. Réparation d'un renommage manqué : la migration 018 a préfixé les tables de
--    données en `usr_`, mais les règles qui les désignaient sont restées sur
--    l'ancien nom. Le champ « véhicule » pointait donc une table inexistante, et
--    sa liste de choix ne pouvait rien proposer.
UPDATE sys_regles_champs_categorie
   SET sources = REPLACE(sources, 'donnees_', 'usr_')
 WHERE sources LIKE '%donnees\_%';
UPDATE sys_regles_champs_categorie
   SET source_table = REPLACE(source_table, 'donnees_', 'usr_')
 WHERE source_table LIKE 'donnees\_%';
