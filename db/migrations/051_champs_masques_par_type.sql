-- Où se décide l'affichage des colonnes retirées, et quel mode s'ouvre en
-- premier (§19.21).
--
-- Le §19.20 avait posé « montrer aussi les champs retirés du tableau » dans le
-- profil de chacun. C'était la mauvaise porte : retirer une colonne du tableau
-- est une décision d'administration, prise pour un type de document et pour
-- tout le foyer. Laisser chacun la contourner de son côté rendait le réglage
-- d'administration illisible — personne ne voyait la même fiche.
--
-- Le réglage remonte donc sur le **type**, à côté des colonnes qu'il commande
-- (écran « Colonnes des tableaux »). `champs_masques` quitte les comptes.
--
-- `mode_apercu` passe par défaut à la miniature : c'est le mode qui coûte le
-- moins cher à ouvrir, et il montre d'un coup d'œil les documents liés côte à
-- côte. Les comptes existants sont recalés dessus — la préférence datait de la
-- veille, personne n'avait choisi 'document' en connaissance de cause.

ALTER TABLE sys_categories
    ADD COLUMN fiche_champs_masques BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE sys_utilisateurs
    DROP COLUMN champs_masques,
    MODIFY COLUMN mode_apercu VARCHAR(20) NOT NULL DEFAULT 'miniature';

UPDATE sys_utilisateurs SET mode_apercu = 'miniature' WHERE mode_apercu = 'document';
