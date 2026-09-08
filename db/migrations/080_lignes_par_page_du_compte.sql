-- Les lignes par page, pour ce compte-ci (§22.44).
--
-- Le foyer règle un nombre de départ (« Lignes par page du registre »), et c'est
-- un bon défaut. Mais il ne dépend pas du foyer : il dépend de l'écran devant
-- lequel on est assis. Cinquante lignes tiennent sur un moniteur de bureau et
-- débordent sur un portable ; sur une tablette, vingt-cinq suffisent. Chacun
-- doit donc pouvoir décider pour lui, comme il décide déjà de son mode d'aperçu.
--
-- NULL veut dire « suivre le foyer » : c'est l'état de départ de tout compte, et
-- celui vers lequel on revient. Un zéro ou un défaut chiffré aurait figé le
-- choix du foyer au moment de la migration.

ALTER TABLE sys_utilisateurs
    ADD COLUMN lignes_par_page INT NULL;
