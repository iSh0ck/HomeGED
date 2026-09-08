-- Deux colonnes que plus rien ne lit (§22.43).
--
-- `sys_categories.table_source` est un reliquat des « fiches de liaison »
-- (migration 049) : une fiche s'adossait alors à une table du foyer. Le §22.1 a
-- remplacé cette notion par la **fiche simple**, dont les entrées se saisissent
-- à la main ; la migration 064 a mis la colonne à NULL partout et le validateur
-- qui la remplissait a disparu du code. Elle ne portait donc plus rien.
--
-- `sys_verrous_document.date_prise` était posée à la création d'un verrou et
-- jamais relue : c'est `date_expiration` qui décide de tout, et un verrou vit
-- quelques minutes. La date de prise n'informait personne — le journal d'audit,
-- lui, garde trace de qui a pris quoi.
--
-- Un balayage des 42 tables et des 306 colonnes du schéma n'en a trouvé que
-- deux dans ce cas ; les retirer évite qu'on se demande, dans un an, ce qu'elles
-- voulaient dire.

ALTER TABLE sys_categories DROP COLUMN table_source;
ALTER TABLE sys_verrous_document DROP COLUMN date_prise;
