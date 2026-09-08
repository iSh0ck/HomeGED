-- Plusieurs sources pour un même champ (§17.28).
--
-- Le titulaire d'une facture peut être une personne qui possède un compte, ou
-- quelqu'un du foyer qui n'en a pas — un enfant, un parent dont on garde les
-- papiers. Obliger à choisir l'une des deux familles revenait à rendre l'autre
-- inatteignable.
--
-- `sources` liste donc les sources d'un champ, séparées par des virgules.
-- `source_table` reste renseignée avec la **première** : c'est elle qui donne
-- son sens à une valeur enregistrée sans préfixe, comme celles écrites avant
-- cette migration.
--
-- Les valeurs deviennent préfixées — `usr_membres:3` — parce que deux sources
-- ont chacune leur ligne nº3, et qu'un identifiant nu ne dirait plus laquelle.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN IF NOT EXISTS sources VARCHAR(500) NULL AFTER source_table;

UPDATE sys_regles_champs_categorie
SET sources = source_table
WHERE sources IS NULL AND source_table IS NOT NULL;

UPDATE sys_regles_champs_categorie
SET sources = 'sys_utilisateurs,usr_membres'
WHERE champ = 'meta:titulaire';
