-- Colonnes du tableau, propres à chaque catégorie (§18.1).
--
-- Un registre unique force toutes les catégories dans le même moule : quatre
-- colonnes qui conviennent à peu près à tout et bien à rien. Une facture se lit
-- en une ligne — émetteur, numéro, date, montant, titulaire — et ces colonnes
-- n'ont aucun sens pour un courrier.
--
-- Une catégorie sans configuration n'est pas pour autant démunie : les colonnes
-- sont alors déduites de ce qu'elle déclare (ses champs attendus) et de ce que
-- ses documents portent réellement. Cette table ne sert qu'à *corriger* cette
-- déduction — retirer une colonne parasite, en réordonner deux, renommer un
-- intitulé. On ne configure que ce qui ne va pas de soi.
--
-- `visible` plutôt qu'une suppression de ligne : masquer une colonne déduite
-- demande de pouvoir dire « pas celle-là », ce qu'une absence de ligne ne sait
-- pas exprimer — l'absence, c'est précisément ce qui déclenche la déduction.

CREATE TABLE IF NOT EXISTS sys_colonnes_categorie (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,
    libelle VARCHAR(150) NULL,
    ordre INT NOT NULL DEFAULT 100,
    largeur INT NULL,
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_colonne_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT uq_colonne_categorie UNIQUE (categorie_id, champ)
) ENGINE=InnoDB;
