-- Ce qui se lit d'une ligne de table, champ par champ (§22.59).
--
-- Une table de données déclare déjà ses colonnes identifiantes : c'est ce qui
-- désigne une ligne, et c'est ce qui composait l'affichage partout. Un réglage
-- unique par table, donc — alors que le même véhicule se lit « AA-123-BB » sous
-- « Véhicule concerné » et « Clio III · AA-123-BB » dans un sélecteur où l'on
-- cherche la bonne voiture.
--
-- Ce choix appartient au champ, pas à la table : c'est lui qui sait ce qu'on
-- vient y chercher. Vide — l'état de tout champ existant — veut dire « comme la
-- table le déclare », et rien ne change pour personne.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN colonnes_affichees VARCHAR(255) NULL AFTER colonnes_deduction;
