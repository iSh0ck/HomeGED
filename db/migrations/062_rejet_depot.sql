-- Écarter un dépôt depuis le Centre d'analyse (§21.14).
--
-- On pouvait dire de quel type était un fichier « à classer », jamais qu'il
-- n'avait rien à faire là — un double scan, une page de garde, un fichier déposé
-- par erreur. Il fallait aller le chercher sur le disque, ou le laisser encombrer
-- l'écran indéfiniment ; le compteur, lui, continuait d'appeler à l'action.
--
-- Comme pour le classement (§19.4) : l'API **pose la consigne**, le serveur de
-- travaux l'exécute. Elle seule a les fichiers reçus en lecture seule, et une
-- règle écrite deux fois divergerait.

ALTER TABLE sys_jobs
    ADD COLUMN rejet_demande BOOLEAN NOT NULL DEFAULT FALSE;
