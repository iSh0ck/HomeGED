-- Un champ qui attache des documents existants (§22.11).
--
-- L'exemple de l'utilisateur : sous « Entretiens », noter ce qui a été fait sur
-- le véhicule **et** y attacher une ou plusieurs factures déjà présentes dans la
-- GED. Le besoin est général — une déclaration de sinistre et ses devis, un
-- dossier scolaire et ses bulletins, un chantier et ses pièces —, il ne doit
-- donc rien savoir des véhicules.
--
-- Ce n'est ni une pièce (§22.2 : un fichier de plus dans **ce** document), ni un
-- rattachement à la main (§22.4 : un lien entre deux documents, sans nom), ni un
-- rapprochement déclaré (§22.8 : deux documents qui portent la même valeur).
-- C'est un **champ** : il a un intitulé, il est propre à un type, et son contenu
-- est une liste de documents qu'on choisit — « Factures liées », « Devis reçus ».
--
-- Une table plutôt qu'une métadonnée à rallonge : une liste d'identifiants dans
-- une chaîne de 500 caractères s'y serait tenue trois documents, et rien
-- n'aurait effacé le lien à la suppression de la cible.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN attache_documents BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS sys_documents_attaches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    -- Le champ auquel cette attache appartient, dans le vocabulaire des filtres
    -- (`meta:factures_liees`) : un même document peut en porter plusieurs.
    champ VARCHAR(100) NOT NULL,
    document_attache_id INT NOT NULL,
    ordre INT NOT NULL DEFAULT 1,
    date_ajout DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    CONSTRAINT fk_attache_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_attache_cible FOREIGN KEY (document_attache_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_attache_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_attache (document_id, champ, document_attache_id),
    KEY idx_attache_cible (document_attache_id)
) ENGINE=InnoDB;
