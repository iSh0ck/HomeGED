-- Le groupement en arborescence (§21.6).
--
-- Le registre est un tableau plat : on choisit un type, et l'on obtient trois
-- cents lignes qu'il faut filtrer colonne par colonne. EzGED propose de replier
-- les résultats sur un critère — « année, puis émetteur » — et de descendre
-- branche par branche. C'est un classement **calculé à partir des données**,
-- distinct de l'arborescence des dossiers que l'administration règle : la même
-- vue se groupe par titulaire aujourd'hui et par véhicule demain.
--
-- `groupement` : les champs du repli, séparés par des virgules, dans le
--   vocabulaire du moteur de filtres (`fournisseur`, `date_document`,
--   `meta:titulaire`, `lien:usr_vehicules`). Vide : la vue s'ouvre à plat, comme
--   avant.

ALTER TABLE sys_vues_enregistrees
    ADD COLUMN groupement VARCHAR(255) NULL;
