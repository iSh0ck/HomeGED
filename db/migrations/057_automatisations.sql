-- Les automatisations « Quand… alors… » (§21.8).
--
-- Le workflow d'EzGED enchaîne des étapes, des conditions évaluées dans l'ordre
-- et des tâches. Pour une maison, la même idée tient en une phrase : **quand**
-- un document arrive et **que** telle condition est vraie, **alors** faire
-- ceci. Générique et réglé depuis l'administration — demande explicite de
-- l'utilisateur : « ça doit être générique et pas spécifique à des factures ».
--
--   `declencheur` : ce qui déclenche l'examen (dépôt, modification, date
--     atteinte). Le vocabulaire est déclaré dans le code, l'écran le lit.
--   `categorie_id`: limiter à un type. Vide = tous.
--   `conditions`  : la même liste JSON `{champ, operateur, valeur}` que les
--     filtres, les vues et les tableaux de bord. Rien de neuf à apprendre, et
--     tout ce qui se filtre se teste.
--   `actions`     : liste JSON `{type, …}`. Le catalogue est déclaré dans le
--     code, comme celui des fonctions d'extraction.
--
-- Le journal, lui, répond à la question qui rend une automatisation utilisable :
-- **qu'est-ce qui s'est déclenché, et pourquoi ?** Une automatisation
-- silencieuse devient vite une source de mystères. Il sert aussi à ne pas agir
-- deux fois sur le même document pour un déclencheur de date.

CREATE TABLE IF NOT EXISTS sys_automatisations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    declencheur VARCHAR(40) NOT NULL,
    categorie_id INT NULL,
    conditions TEXT NULL,
    actions TEXT NOT NULL,
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    ordre INT NOT NULL DEFAULT 100,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_automatisation_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    KEY idx_automatisations_declencheur (declencheur, actif)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sys_journal_automatisation (
    id INT AUTO_INCREMENT PRIMARY KEY,
    automatisation_id INT NULL,
    document_id INT NULL,
    date_execution DATETIME DEFAULT CURRENT_TIMESTAMP,
    declencheur VARCHAR(40) NOT NULL,
    agi BOOLEAN NOT NULL DEFAULT FALSE,   -- les conditions étaient-elles réunies ?
    detail TEXT NULL,                     -- ce qui a été fait, ou pourquoi rien
    CONSTRAINT fk_journal_auto_automatisation FOREIGN KEY (automatisation_id)
        REFERENCES sys_automatisations(id) ON DELETE CASCADE,
    CONSTRAINT fk_journal_auto_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    KEY idx_journal_auto_document (automatisation_id, document_id, agi)
) ENGINE=InnoDB;
