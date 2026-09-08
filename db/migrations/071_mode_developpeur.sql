-- Le mode développeur (§21.14).
--
-- Les scripts Python sont la porte de sortie universelle d'EzGED. Ils étaient
-- écartés d'emblée de ce projet ; l'utilisateur les autorise **sous condition
-- d'un mode développeur activé en administration, qui énonce les problèmes que
-- cela pose**.
--
-- Ce qu'il pose, et qui est dit à l'écran avant d'armer l'interrupteur : un
-- script s'exécute avec les droits du service, lit ce qu'on lui donne, et peut
-- faire sortir des données. Il n'est donc pas exécuté n'importe comment :
--
--   * **un seul point d'entrée**, `executer(contexte)`, et un contexte explicite
--     — le script ne va pas se servir, on lui donne ;
--   * **dans un processus séparé**, avec une durée maximale : une boucle infinie
--     ne doit pas emporter le serveur de travaux avec elle ;
--   * **sans accès à la base** : ce qu'il rend est un texte, que quelqu'un lit.
--     La GED ne se modifie pas dans le dos de ses écrans ;
--   * **journalisé** : qui a écrit le script, qui l'a lancé, ce qu'il a rendu.

CREATE TABLE IF NOT EXISTS sys_scripts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    description TEXT NULL,
    code MEDIUMTEXT NOT NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME NULL,
    utilisateur_id INT NULL,
    CONSTRAINT fk_script_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_script_nom (nom)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sys_executions_script (
    id INT AUTO_INCREMENT PRIMARY KEY,
    script_id INT NULL,
    utilisateur_id INT NULL,
    date_execution DATETIME DEFAULT CURRENT_TIMESTAMP,
    duree_ms INT NULL,
    reussite BOOLEAN NOT NULL DEFAULT FALSE,
    sortie MEDIUMTEXT NULL,
    erreur TEXT NULL,
    CONSTRAINT fk_execution_script FOREIGN KEY (script_id)
        REFERENCES sys_scripts(id) ON DELETE SET NULL,
    CONSTRAINT fk_execution_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    KEY idx_execution_date (date_execution)
) ENGINE=InnoDB;
