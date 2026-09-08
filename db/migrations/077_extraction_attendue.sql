-- Dire qu'un champ **doit** se remplir tout seul (§22.27).
--
-- L'écran d'assemblage annonçait « saisi à la main » pour tout champ qu'aucune
-- règle ne visait. C'est vrai, mais cela mélange deux situations très
-- différentes : un commentaire d'entretien **se saisit** à la main, et c'est très
-- bien ; un numéro de facture qui n'a pas encore sa règle d'extraction est un
-- réglage **qui manque**, et rien ne le disait.
--
-- Le champ déclare donc s'il attend une règle. L'assemblage peut alors montrer
-- trois états au lieu de deux — en place, à paramétrer, saisi à la main — et
-- proposer d'écrire la règle là où elle manque.
--
-- FALSE par défaut : un champ qu'on n'a rien dit d'attendre se saisit, et la
-- migration ne réclame donc rien à personne.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN extraction_attendue BOOLEAN NOT NULL DEFAULT FALSE;
