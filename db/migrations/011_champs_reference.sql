-- 011 — Champs personnalisés adossés à une table de données (§17)
--
-- Une règle de champ peut désormais désigner une table de données comme source
-- de ses valeurs : « Véhicule » sur la catégorie Garage puise dans la table
-- `donnees_vehicules`, et l'utilisateur choisit une ligne au lieu de saisir du
-- texte libre.
--
-- La valeur reste stockée dans `metadonnees`, comme n'importe quel autre champ
-- extrait : c'est l'identifiant de la ligne référencée. Aucune table
-- supplémentaire, aucune colonne ajoutée à `documents` — l'architecture reste
-- la même quel que soit le nombre de champs personnalisés.

ALTER TABLE regles_champs_categorie
    ADD COLUMN IF NOT EXISTS source_table VARCHAR(64) NULL AFTER champ;
