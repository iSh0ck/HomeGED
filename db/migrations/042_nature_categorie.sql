-- Un dossier n'est pas un type de document (§19.1).
--
-- L'arborescence confondait deux choses qui n'ont pas le même usage :
--
--   * un **dossier** organise — « Maison », « Impôts ». Il ne contient aucun
--     document en propre, et n'a donc ni colonnes, ni champs attendus, ni règles
--     d'extraction. Régler les colonnes de « Maison » n'a jamais rien voulu dire ;
--   * un **type de document** est une feuille — « Factures », « Relevés
--     bancaires ». Il porte tout ce qui décrit un document de cette sorte, et,
--     à partir du §19.2, son dossier de dépôt.
--
-- En nommant la chose, chaque écran sait à quoi il s'adresse, et l'administration
-- cesse de proposer des réglages sans effet.
--
-- Conversion de l'existant, et c'est la seule règle qui vaille sans deviner :
-- une catégorie **qui a des enfants** devient un dossier, une **feuille** devient
-- un type. L'administration permet de rectifier ensuite, dans les limites que la
-- cohérence impose (un dossier qui a des enfants ne peut pas devenir un type, un
-- type qui porte des documents ne peut pas devenir un dossier).
--
-- Défaut `type` : une catégorie créée sans rien préciser porte des documents,
-- ce qui est le cas courant. Un dossier se demande.

ALTER TABLE sys_categories
    ADD COLUMN nature VARCHAR(10) NOT NULL DEFAULT 'type' AFTER nom;

UPDATE sys_categories SET nature = 'dossier'
WHERE id IN (SELECT parent_id FROM (
    SELECT DISTINCT parent_id FROM sys_categories WHERE parent_id IS NOT NULL
) AS parents);
