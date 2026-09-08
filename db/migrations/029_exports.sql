-- Exports de l'archive (§17.30).
--
-- Un export contient **tout** : chaque PDF du foyer, rangé selon son classement.
-- C'est le fichier le plus sensible que l'application puisse produire, et il
-- vit hors de tout contrôle une fois téléchargé. D'où trois précautions, dont
-- cette table porte deux :
--
--   `date_telechargement` — l'archive ne se télécharge **qu'une fois**. Un lien
--   qui resterait valable serait une copie de la GED entière à disposition de
--   qui remettrait la main dessus.
--
--   `date_expiration` — non téléchargée, elle s'efface d'elle-même. Un export
--   oublié sur le disque est une fuite qui attend son heure.
--
-- La troisième précaution — mot de passe et second facteur redemandés — est
-- appliquée au moment de la création, pas ici.

CREATE TABLE IF NOT EXISTS sys_exports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    jeton VARCHAR(64) NOT NULL UNIQUE,
    utilisateur_id INT NULL,
    chemin VARCHAR(500) NOT NULL,
    taille_octets BIGINT NULL,
    documents INT NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_expiration DATETIME NOT NULL,
    date_telechargement DATETIME NULL,
    CONSTRAINT fk_export_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;
