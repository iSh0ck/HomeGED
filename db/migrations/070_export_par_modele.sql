-- L'export par modèle d'arborescence et de nommage (§21.13).
--
-- Notre export existant (§17.30) est une **sortie de secours** : tout le foyer,
-- une archive, un mot de passe administrateur, un téléchargement unique. Il
-- répond à « je ne me sers plus de la GED », et rien d'autre.
--
-- Celui-ci répond à l'autre besoin, quotidien : sortir **une sélection** rangée
-- comme on la veut — « année/type », « Facture EDF - 2026-03.pdf » — pour la
-- donner au comptable, à l'assurance, au notaire.
--
-- Deux raisons pour une table plutôt qu'une réponse directe :
--
--   * l'archive se construit **hors de la requête**. Cinq cents PDF à copier et
--     compresser tiennent une connexion ouverte plusieurs minutes ; le serveur
--     de travaux le fait à son rythme, et l'on revient chercher le fichier ;
--   * l'API n'a pas les archives en écriture. Elle pose la demande, le serveur
--     de travaux écrit — c'est la règle depuis le §18.53, et elle vaut ici aussi.

CREATE TABLE IF NOT EXISTS sys_exports_modele (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utilisateur_id INT NULL,
    statut ENUM('en_attente','en_cours','pret','erreur') NOT NULL DEFAULT 'en_attente',
    -- Ce qu'on exporte : les mêmes critères que le registre, au même format.
    criteres TEXT NULL,
    categorie_id INT NULL,
    -- Comment on le range : deux modèles à trous, `{annee}/{type}` et
    -- `{champ:emetteur} - {date}`. Les trous sont les champs du document, ce qui
    -- évite d'inventer un vocabulaire de plus.
    modele_dossier VARCHAR(255) NULL,
    modele_nom VARCHAR(255) NULL,
    chemin VARCHAR(500) NULL,
    nb_documents INT NULL,
    message TEXT NULL,
    date_demande DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_fin DATETIME NULL,
    CONSTRAINT fk_export_modele_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    CONSTRAINT fk_export_modele_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE SET NULL,
    KEY idx_export_modele_statut (statut, date_demande)
) ENGINE=InnoDB;
