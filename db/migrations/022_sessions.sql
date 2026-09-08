-- Registre des sessions ouvertes (§17.2).
--
-- Les jetons sont des JWT : ils portent leur propre validité et le serveur n'a
-- jamais eu besoin de savoir qui était connecté. C'est économe, mais cela rend
-- deux choses impossibles — dire à quelqu'un « voici les appareils connectés à
-- ton compte », et fermer une session à distance. Cette table les rend
-- possibles : chaque jeton délivré y laisse une ligne, identifiée par le `jti`
-- qu'il transporte.
--
-- Une session révoquée n'est pas supprimée : on garde la trace de sa fermeture,
-- c'est précisément ce qu'on veut pouvoir relire après un incident.
--
-- L'adresse et le navigateur sont conservés pour que l'utilisateur reconnaisse
-- ses propres connexions. C'est une donnée personnelle : elle disparaît avec le
-- compte (ON DELETE CASCADE) et avec le ménage des sessions expirées.

CREATE TABLE IF NOT EXISTS sys_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utilisateur_id INT NOT NULL,
    jti VARCHAR(64) NOT NULL UNIQUE,          -- identifiant unique du jeton
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_activite DATETIME NULL,              -- dernière requête vue avec ce jeton
    date_expiration DATETIME NOT NULL,
    date_revocation DATETIME NULL,            -- NULL = session ouverte
    adresse VARCHAR(64) NULL,
    agent VARCHAR(255) NULL,                  -- en-tête User-Agent, tel quel
    CONSTRAINT fk_sessions_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE CASCADE,
    KEY idx_sessions_utilisateur (utilisateur_id, date_revocation)
) ENGINE=InnoDB;
