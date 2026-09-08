-- Thème et langue, pour ce compte-ci (§22.50, §22.51).
--
-- Le foyer choisit une palette et une langue de départ ; elles ne le regardent
-- pourtant pas tout à fait. Un thème dépend de l'écran devant lequel on est
-- assis et de la lumière de la pièce ; une langue dépend de qui lit. Chacun doit
-- pouvoir décider pour lui, comme il décide déjà de son mode d'aperçu et de son
-- nombre de lignes par page.
--
-- NULL veut dire « suivre le foyer » : c'est l'état de départ de tout compte, et
-- celui vers lequel on revient.

ALTER TABLE sys_utilisateurs
    ADD COLUMN theme VARCHAR(32) NULL,
    ADD COLUMN langue VARCHAR(32) NULL;
