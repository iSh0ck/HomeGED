-- Verrou d'édition sur un document (§17.21).
--
-- Deux personnes du foyer peuvent ouvrir la même facture au même moment. Sans
-- verrou, la dernière à enregistrer écrase l'autre sans que personne ne le
-- sache — et l'on ne s'en aperçoit que plus tard, en constatant qu'une
-- correction a disparu.
--
-- Le verrou est **volontairement périssable** : un onglet fermé sans un mot, un
-- ordinateur éteint, et le document resterait bloqué pour tout le monde. Il
-- porte donc une date d'expiration, prolongée tant que la fenêtre d'édition
-- reste ouverte, et périmée d'elle-même sinon.
--
-- Une ligne par document au plus : c'est la clé unique qui le garantit, pas le
-- code applicatif.

CREATE TABLE IF NOT EXISTS sys_verrous_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL UNIQUE,
    utilisateur_id INT NULL,
    date_prise DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_expiration DATETIME NOT NULL,
    CONSTRAINT fk_verrou_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_verrou_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;
