-- Les échéances et les rappels (§21.9).
--
-- C'est le besoin le plus concret d'une maison : contrôle technique, assurance,
-- garantie, échéance de facture. Un document porte la date ; encore faut-il que
-- quelqu'un la regarde avant qu'elle ne passe.
--
-- Rien de spécifique aux factures ici non plus : un **champ** d'un type est
-- déclaré « échéance », et c'est tout. Le foyer décide de quel champ il s'agit —
-- `meta:date_echeance` pour les factures, `meta:fin_de_validite` pour les
-- papiers d'identité — et de combien de jours à l'avance il veut être prévenu.
--
--   `echeance`     : ce champ porte-t-il une date qui arrive à terme ?
--   `rappel_jours` : combien de jours avant. Vide : le réglage du foyer.
--
-- Les notifications sont une table à part, et non un simple compteur : un rappel
-- doit pouvoir être lu, relu et retrouvé, et le §21.10 les enverra par courriel
-- depuis ce même endroit. `utilisateur_id` vide = pour tout le foyer, ce qui est
-- le cas ordinaire — une échéance de maison ne s'adresse à personne en
-- particulier.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN echeance BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN rappel_jours INT NULL;

CREATE TABLE IF NOT EXISTS sys_notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utilisateur_id INT NULL,            -- NULL : pour tout le foyer
    document_id INT NULL,
    titre VARCHAR(200) NOT NULL,
    message TEXT NULL,
    source VARCHAR(40) NOT NULL DEFAULT 'rappel',   -- rappel | automatisation
    -- Ce qui rend un rappel unique : sans elle, la même échéance reviendrait
    -- chaque nuit. C'est la mémoire du « déjà prévenu ».
    empreinte VARCHAR(120) NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_lecture DATETIME NULL,
    CONSTRAINT fk_notification_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE CASCADE,
    CONSTRAINT fk_notification_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    UNIQUE KEY uq_notification_empreinte (empreinte),
    KEY idx_notifications_lecture (date_lecture, date_creation)
) ENGINE=InnoDB;
