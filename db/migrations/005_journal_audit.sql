-- 005 — Journal d'audit (§14)
--
-- Trace les actions importantes sur les documents. Volontairement générique :
-- `action` et `objet_type` sont des chaînes libres, de nouveaux types
-- d'événements s'ajoutent donc sans migration.
--
-- `utilisateur_email` est recopié en clair à côté de la clé étrangère : si le
-- compte est supprimé plus tard, la trace doit rester exploitable — c'est tout
-- l'intérêt d'un journal d'audit.

CREATE TABLE IF NOT EXISTS journal_audit (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date_evenement DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    utilisateur_email VARCHAR(255) NULL,
    action VARCHAR(100) NOT NULL,
    objet_type VARCHAR(50) NOT NULL,
    objet_id INT NULL,
    details TEXT NULL,
    CONSTRAINT fk_audit_utilisateur FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE INDEX IF NOT EXISTS idx_audit_date ON journal_audit (date_evenement);
CREATE INDEX IF NOT EXISTS idx_audit_objet ON journal_audit (objet_type, objet_id);
