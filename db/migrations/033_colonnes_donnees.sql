-- Réglages par colonne des tables du foyer (§18.32).
--
-- Une table de données décrivait jusqu'ici son affichage d'ensemble — colonne
-- servant de libellé, colonnes identifiantes. Rien ne se disait **colonne par
-- colonne**, et deux besoins réels s'en trouvaient bloqués :
--
--   * la colonne « propriétaire » de la table des véhicules devrait pointer une
--     ligne de « Membres du foyer », comme le champ « Titulaire » d'un document
--     pointe une personne. Faute de le déclarer, elle ne contient qu'un texte
--     libre, que rien ne relie à qui que ce soit et que personne ne corrige
--     quand un nom change ;
--
--   * un intitulé lisible (« Mise en circulation ») ne pouvait pas accompagner
--     un nom de colonne technique (`mise_en_circulation`).
--
-- La liaison est **déclarée, pas figée** : n'importe quelle colonne de
-- n'importe quelle table du foyer peut pointer n'importe quelle autre table.
-- C'est ce qui permet à un autre foyer de relier ses propres tables — des
-- animaux à leur vétérinaire, un bien à son locataire — sans toucher au code.
--
-- L'unicité, elle, n'est pas ici : une contrainte UNIQUE vit dans le schéma de
-- la table, qui reste la seule source de vérité. La dupliquer dans une table de
-- réglages garantirait qu'elles finissent par diverger.

CREATE TABLE IF NOT EXISTS sys_colonnes_donnees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_table VARCHAR(64) NOT NULL,
    colonne VARCHAR(64) NOT NULL,
    libelle VARCHAR(150) NULL,
    -- table du foyer pointée par cette colonne ; la valeur enregistrée est alors
    -- l'identifiant d'une de ses lignes
    source_table VARCHAR(64) NULL,
    CONSTRAINT uq_colonne_donnees UNIQUE (nom_table, colonne)
) ENGINE=InnoDB;
