-- Ce que **cette entrée-ci** montre d'une ligne de table (§22.61).
--
-- Trois niveaux, et chacun sait quelque chose que les autres ignorent :
--
--   * la **table** déclare ce qui désigne une ligne — « prenom, nom » ;
--   * le **champ** choisit ce qui la compose ici (§22.59) : sous « Véhicule
--     concerné », un administrateur retient l'immatriculation et le modèle ;
--   * l'**entrée** retient, parmi ce que le champ propose, ce qui mérite la
--     place d'une colonne. C'est celui qui saisit qui sait si le modèle apporte
--     quelque chose à cette ligne-là.
--
-- Aucune ligne ici veut dire « tout ce que le champ propose » : c'est l'état de
-- toutes les entrées existantes, et rien ne change pour elles.

CREATE TABLE IF NOT EXISTS sys_affichages_valeur (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,
    -- colonnes retenues, séparées par des virgules, dans l'ordre du champ
    colonnes VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_affichage_document_champ (document_id, champ),
    CONSTRAINT fk_affichage_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
