-- Versions d'un document (§18.36).
--
-- Un document du foyer n'est pas figé : on rescanne une facture mal cadrée, on
-- reçoit la version corrigée d'un avis, on redépose la même pièce après l'avoir
-- signée. Jusqu'ici, chaque dépôt créait une fiche de plus — deux entrées pour
-- un seul papier, sans rien qui les relie — ou, si le fichier était identique au
-- bit près, était purement et simplement jeté.
--
-- Chaque dépôt devient donc une **version**. La fiche, elle, reste unique : elle
-- pointe la version courante, et garde l'historique des précédentes avec leur
-- date. C'est ce qui permet de revenir sur un scan raté sans avoir à retrouver
-- quelle fiche portait quoi.
--
-- Le fichier de chaque version est conservé sur le disque : une version dont on
-- ne peut plus rien ouvrir ne serait qu'une ligne de journal. Un administrateur
-- peut en supprimer une — la place n'est pas infinie —, mais jamais la seule qui
-- reste.

CREATE TABLE IF NOT EXISTS sys_versions_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    -- Empreinte du fichier reçu : c'est elle qui reconnaît un dépôt déjà connu,
    -- y compris s'il s'agit d'une ancienne version qu'on redépose.
    hash_sha256 VARCHAR(64) NOT NULL,
    chemin_stockage VARCHAR(500) NOT NULL,
    nom_fichier VARCHAR(255) NOT NULL,
    taille_octets BIGINT NULL,
    date_depot DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- La version que la fiche affiche. Une seule à la fois, et il y en a toujours une.
    courante BOOLEAN NOT NULL DEFAULT FALSE,
    utilisateur_id INT NULL,
    CONSTRAINT fk_version_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_version_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    CONSTRAINT uq_version_empreinte UNIQUE (hash_sha256),
    INDEX idx_versions_document (document_id, date_depot)
) ENGINE=InnoDB;

-- Les documents déjà présents deviennent leur propre première version : sans
-- cela, leur historique commencerait au deuxième dépôt et l'original ne serait
-- nulle part.
INSERT INTO sys_versions_document
    (document_id, hash_sha256, chemin_stockage, nom_fichier, taille_octets, date_depot, courante)
SELECT d.id, d.hash_sha256, d.chemin_stockage, d.nom_fichier, d.taille_octets,
       COALESCE(d.date_import, NOW()), TRUE
  FROM sys_documents d
 WHERE NOT EXISTS (SELECT 1 FROM sys_versions_document v WHERE v.document_id = d.id);
