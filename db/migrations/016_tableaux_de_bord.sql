-- 016 — Tableaux de bord personnalisés
--
-- Un tableau de bord est une liste d'indicateurs (« widgets ») décrits en JSON,
-- exactement comme une vue enregistrée décrit une liste de critères. Rien n'est
-- codé en dur : ajouter un indicateur ne demande ni migration ni colonne.
--
-- Chaque indicateur réutilise le **format de filtres** du registre
-- (app/filtres.py) : « les factures EDF de l'année en cours » se décrit de la
-- même façon dans un tableau de bord et dans une recherche par colonne.
--
-- Le tableau d'accueil n'est pas stocké ici : il est défini dans le code
-- (app/statistiques.py) pour qu'une installation neuve en dispose d'emblée.

CREATE TABLE IF NOT EXISTS tableaux_de_bord (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,
    widgets TEXT NOT NULL,               -- JSON : [{type, titre, champ, filtres, ...}]
    partage BOOLEAN NOT NULL DEFAULT FALSE,
    utilisateur_id INT NULL,
    ordre INT DEFAULT 100,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tdb_utilisateur FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;
