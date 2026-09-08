-- Un document porte plusieurs pièces (§22.2).
--
-- Chez nous, un document **était** un fichier : une ligne, un PDF. Pour réunir
-- une facture, sa garantie et le bon de livraison, il fallait donc trois
-- documents et un lien entre eux — trois fiches à remplir pour un seul achat.
-- EzGED n'a pas ce détour : une fiche descriptive porte ses champs **et N
-- fichiers**. C'est la brique qui manquait, et c'est celle-ci.
--
-- La pièce **principale** est celle qu'on voit partout ailleurs : c'est son
-- fichier que le registre ouvre, que la miniature montre, que l'export emporte.
-- Les colonnes du document (`chemin_stockage`, `hash_sha256`, `nom_fichier`,
-- `taille_octets`) en restent le reflet, tenu à jour : tout ce qui les lit
-- aujourd'hui continue de fonctionner sans rien savoir des pièces.
--
-- Le texte océrisé est porté par chaque pièce ; celui du document est leur
-- concaténation, et c'est lui que l'index plein texte lit. Une recherche trouve
-- donc un document par le contenu de n'importe laquelle de ses pièces — ce qui
-- est exactement ce qu'on attend en cherchant « garantie ».

CREATE TABLE IF NOT EXISTS sys_pieces_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    nom_fichier VARCHAR(255) NOT NULL,
    chemin_stockage VARCHAR(500) NOT NULL,
    -- Empreinte du fichier **reçu**, comme sur le document : c'est elle qui
    -- reconnaît un dépôt déjà connu, quelle que soit la pièce où il a atterri.
    hash_sha256 VARCHAR(64) NOT NULL,
    taille_octets BIGINT NULL,
    texte_ocr LONGTEXT NULL,
    -- Place dans la fiche. La principale n'est pas forcément la première : on
    -- peut mettre le contrat en tête et garder la facture en pièce jointe.
    ordre INT NOT NULL DEFAULT 1,
    principale BOOLEAN NOT NULL DEFAULT FALSE,
    date_ajout DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    CONSTRAINT fk_piece_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_piece_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_piece_empreinte (hash_sha256),
    KEY idx_piece_document (document_id, ordre)
) ENGINE=InnoDB;

-- Le fichier actuel de chaque document devient sa première pièce, sans rien
-- perdre : même chemin, même empreinte, même texte. Aucun document ne change de
-- comportement le jour de la migration — il gagne seulement la possibilité d'en
-- porter d'autres.
INSERT INTO sys_pieces_document
    (document_id, nom_fichier, chemin_stockage, hash_sha256, taille_octets,
     texte_ocr, ordre, principale, date_ajout)
SELECT d.id, d.nom_fichier, d.chemin_stockage, d.hash_sha256, d.taille_octets,
       d.texte_ocr, 1, TRUE, d.date_import
FROM sys_documents d
WHERE NOT EXISTS (SELECT 1 FROM sys_pieces_document p WHERE p.document_id = d.id);

-- Un travail peut viser un document existant : le fichier déposé y entre comme
-- **pièce** au lieu de créer un document (§22.2). Sans cette colonne, le serveur
-- de travaux n'aurait aucun moyen de le savoir — le dossier de dépôt ne dit que
-- le type, et le fichier ne dit rien.
ALTER TABLE sys_jobs ADD COLUMN piece_pour_document_id INT NULL;
-- CASCADE, et non SET NULL comme `document_id` : vidée, la consigne ne dirait
-- plus « pièce du document nº12 » mais « dépôt ordinaire », et le serveur de
-- travaux créerait un document là où l'on voulait une pièce.
ALTER TABLE sys_jobs ADD CONSTRAINT fk_job_piece_document
    FOREIGN KEY (piece_pour_document_id) REFERENCES sys_documents(id) ON DELETE CASCADE;
