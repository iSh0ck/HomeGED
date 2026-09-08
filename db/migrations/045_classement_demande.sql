-- Le type demandé pour un fichier à classer (§19.4).
--
-- Le Centre d'analyse dit de quel type de document il s'agit ; le fichier doit
-- alors rejoindre le dossier de dépôt de ce type, et le traitement reprendre
-- comme pour un dépôt ordinaire.
--
-- C'est le **serveur de travaux** qui déplace le fichier, et non l'API. Deux
-- raisons, dans cet ordre :
--
--   * les fichiers reçus (§18.53) sont montés en lecture seule côté API — elle
--     les affiche, elle ne les remue pas. Cette garantie vaut mieux qu'un
--     endpoint qui déplace : elle se vérifie d'un coup d'œil au fichier de
--     composition, là où une règle « l'API ne déplace que dans ce cas précis »
--     ne se vérifie qu'en relisant le code ;
--   * c'est déjà la convention du projet : l'API pose une demande de rejeu, le
--     serveur la relève à son passage suivant.
--
-- La colonne porte donc l'intention — « range-le dans ce type » — et le serveur
-- l'exécute. Elle est remise à zéro dès que c'est fait : ce qu'elle contient est
-- une consigne en attente, pas un historique.

ALTER TABLE sys_jobs
    ADD COLUMN categorie_demandee INT NULL AFTER etape_demandee,
    ADD CONSTRAINT fk_jobs_categorie_demandee
        FOREIGN KEY (categorie_demandee) REFERENCES sys_categories(id) ON DELETE SET NULL;
