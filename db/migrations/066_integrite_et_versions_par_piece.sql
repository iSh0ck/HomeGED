-- Chaque pièce a son empreinte d'archive, et ses versions (§22.2 bis).
--
-- Deux oublis du §22.2, et le même : les pièces jointes existaient dans le
-- modèle mais restaient invisibles aux deux mécanismes qui veillent sur les
-- fichiers.
--
-- **Le contrôle d'intégrité** (§21.3) ne relisait que le fichier principal :
-- une garantie jointe pouvait s'abîmer sur le disque sans que rien ne le dise.
-- Or c'est précisément ce que le contrôle existe pour éviter — une archive
-- familiale dure vingt ans, et personne n'ouvre une garantie tous les ans.
--
-- **Les versions** portaient sur le document : rescanner la garantie aurait
-- remplacé la facture. C'est le **fichier** qu'on rescanne, donc la pièce.

ALTER TABLE sys_pieces_document ADD COLUMN empreinte_archive VARCHAR(64) NULL;
ALTER TABLE sys_pieces_document ADD COLUMN date_controle DATETIME NULL;
ALTER TABLE sys_pieces_document ADD COLUMN integrite VARCHAR(20) NULL;
ALTER TABLE sys_pieces_document ADD INDEX idx_piece_controle (date_controle);

-- La pièce principale hérite de ce que le document savait déjà : sans cela, le
-- premier passage adopterait l'empreinte de tout le fonds et le contrôle
-- perdrait un cycle — pire, il validerait un fichier déjà altéré.
UPDATE sys_pieces_document p
  JOIN sys_documents d ON d.id = p.document_id
   SET p.empreinte_archive = d.empreinte_archive,
       p.date_controle = d.date_controle,
       p.integrite = d.integrite
 WHERE p.principale = TRUE;

-- Une version appartient à une pièce. Les versions existantes sont celles de la
-- pièce principale : c'est le fichier du document, et c'est lui qu'on redéposait.
ALTER TABLE sys_versions_document ADD COLUMN piece_id INT NULL;
ALTER TABLE sys_versions_document ADD CONSTRAINT fk_version_piece
    FOREIGN KEY (piece_id) REFERENCES sys_pieces_document(id) ON DELETE CASCADE;

UPDATE sys_versions_document v
  JOIN sys_pieces_document p ON p.document_id = v.document_id AND p.principale = TRUE
   SET v.piece_id = p.id
 WHERE v.piece_id IS NULL;

-- Le travail sait aussi qu'un dépôt est une **nouvelle version d'une pièce** et
-- non une pièce de plus (§22.3) : c'est la seule chose qu'on ne puisse pas
-- deviner — le même PDF est l'un ou l'autre selon ce qu'on vient de faire.
ALTER TABLE sys_jobs ADD COLUMN version_pour_piece_id INT NULL;
ALTER TABLE sys_jobs ADD CONSTRAINT fk_job_version_piece
    FOREIGN KEY (version_pour_piece_id) REFERENCES sys_pieces_document(id) ON DELETE CASCADE;
