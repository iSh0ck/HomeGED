-- 004 — Vues enregistrées (§9.B)
--
-- Une vue mémorise un jeu de critères de filtrage réutilisable, au format déjà
-- utilisé par la recherche par colonne (app/filtres.py) : une liste JSON de
-- `{champ, operateur, valeur}`. Aucune vue n'est codée en dur ; en ajouter une
-- ne demande ni migration ni modification du code.
--
-- `categorie_id` sert uniquement au **rattachement dans la navigation** (une
-- section peut proposer plusieurs vues) ; le filtrage, lui, est entièrement
-- décrit par `criteres`.
--
-- `utilisateur_id` NULL = vue « du système », conservée si son auteur est
-- supprimé ; seuls les administrateurs peuvent alors la modifier.

CREATE TABLE IF NOT EXISTS vues_enregistrees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    categorie_id INT NULL,
    criteres TEXT NOT NULL,
    utilisateur_id INT NULL,
    partagee BOOLEAN DEFAULT FALSE,
    ordre INT DEFAULT 100,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_vues_categorie FOREIGN KEY (categorie_id) REFERENCES categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_vues_utilisateur FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE INDEX IF NOT EXISTS idx_vues_categorie ON vues_enregistrees (categorie_id);
