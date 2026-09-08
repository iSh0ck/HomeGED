-- 007 — Serveur de travaux (§13) et état « incomplet » (§16)
--
-- Chaque fichier déposé dans le dossier surveillé donne lieu à un travail,
-- dont l'état et le diagnostic sont conservés en base. Jusqu'ici, un échec ne
-- laissait qu'une ligne de log et un fichier déplacé dans `watch/erreurs/` :
-- rien n'était consultable ni rejouable depuis l'interface.
--
-- États d'un travail :
--   en_attente  déposé, pas encore pris en charge
--   en_cours    OCR / extraction en cours
--   termine     document indexé et conforme
--   erreur      échec technique (OCR illisible, fichier corrompu...)
--   bloque      document indexé mais non conforme aux champs attendus de sa
--               catégorie : il n'est pas « correctement traité » (§16)
--   ignore      doublon d'un document déjà présent (même empreinte)
--
-- `rejouer_demande` est le canal de commande de l'interface vers le worker :
-- l'API n'a pas accès au dossier surveillé, elle pose donc un drapeau que le
-- serveur de travaux relève à son passage suivant.

CREATE TABLE IF NOT EXISTS jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_fichier VARCHAR(255) NOT NULL,
    chemin_source VARCHAR(500) NULL,
    hash_sha256 CHAR(64) NULL,
    statut ENUM('en_attente','en_cours','termine','erreur','bloque','ignore') DEFAULT 'en_attente',
    document_id INT NULL,
    tentatives INT DEFAULT 0,
    message_erreur TEXT NULL,
    diagnostic TEXT NULL,
    rejouer_demande BOOLEAN DEFAULT FALSE,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_debut DATETIME NULL,
    date_fin DATETIME NULL,
    CONSTRAINT fk_jobs_document FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE INDEX IF NOT EXISTS idx_jobs_statut ON jobs (statut, date_creation);
CREATE INDEX IF NOT EXISTS idx_jobs_rejouer ON jobs (rejouer_demande);

-- Nouvel état pour un document indexé mais auquel il manque un champ exigé par
-- sa catégorie. Ajout purement additif : les valeurs existantes sont conservées.
ALTER TABLE documents
    MODIFY statut ENUM('en_attente','ocr_en_cours','traite','erreur','incomplet') DEFAULT 'en_attente';
