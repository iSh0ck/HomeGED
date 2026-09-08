-- Fiches de liaison : une troisième nature de catégorie (§19.17).
--
-- Deux natures suffisaient tant qu'un document n'appartenait qu'à un endroit :
-- un **dossier** organise, un **type de document** porte les documents. Mais un
-- foyer ne range pas seulement par sorte de papier — il range aussi *par chose* :
-- tout ce qui concerne la voiture, tout ce qui concerne une personne. Une facture
-- d'entretien est une facture **et** elle concerne ce véhicule-là ; les deux sont
-- vrais en même temps, et le classement en arbre ne sait pas dire cela.
--
-- Une **fiche de liaison** est ce second axe. Elle s'adosse à une table du foyer
-- (`usr_vehicules`, `usr_membres`) : chaque ligne de cette table devient une
-- fiche, et les documents qui la désignent — par un champ à source, §17.18 — s'y
-- retrouvent, quel que soit leur type.
--
-- Ce qu'elle n'a pas, et pourquoi :
--
--   * **pas de dossier de dépôt** : on ne dépose pas « dans un véhicule ». Un
--     document arrive par son type, et la fiche le retrouve ensuite ;
--   * **ni colonnes, ni champs attendus, ni jeux de règles** : elle ne décrit
--     aucune sorte de document, elle en rassemble de plusieurs sortes ;
--   * **aucun document ne s'y range** directement, pour la même raison.
--
-- `table_source` dit à quelle table du foyer elle s'adosse. Sans elle, la fiche
-- n'aurait rien à lister — c'est pourquoi l'administration la refuse vide.

ALTER TABLE sys_categories
    ADD COLUMN table_source VARCHAR(64) NULL AFTER dossier_depot;
