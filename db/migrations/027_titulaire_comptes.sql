-- Le titulaire d'une facture désigne un compte de la GED (§17.27).
--
-- La version précédente pointait `usr_membres`, une table de personnes du foyer
-- distincte des comptes. L'usage a tranché autrement : ce qu'on veut rattacher à
-- une facture, c'est quelqu'un qui existe déjà dans l'application.
--
-- `usr_membres` n'est pas supprimée pour autant : elle reste disponible pour qui
-- doit rattacher un document à une personne sans compte — un enfant, un parent
-- dont on garde les papiers. Il suffit de rebasculer la source dans
-- « Champs requis ».

UPDATE sys_regles_champs_categorie
SET source_table = 'sys_utilisateurs'
WHERE champ = 'meta:titulaire' AND source_table = 'usr_membres';
