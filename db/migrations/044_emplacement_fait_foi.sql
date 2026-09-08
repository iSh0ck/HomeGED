-- L'emplacement du dépôt fait foi (§19.3).
--
-- Le classement était deviné : le serveur essayait les expressions régulières
-- portées par chaque catégorie sur le texte océrisé, dans l'ordre de leur
-- priorité, et rangeait le document là où la première correspondait. Depuis le
-- §19.2, celui qui dépose choisit le dossier — et deux mécanismes concurrents
-- pour ranger un document, c'est un de trop : celui qu'on ne voit pas gagne
-- toujours au mauvais moment.
--
-- Ce que cette migration retire :
--
--   * `regex_identification` — l'expression de classement. Les règles
--     d'**extraction** (`sys_regles_extraction`), elles, ne sont pas touchées :
--     elles lisent le contenu d'un document, elles ne décident pas de sa place ;
--   * `priorite` — l'ordre dans lequel ces expressions étaient essayées. Sans
--     expressions, il n'ordonne plus rien. À ne pas confondre avec `ordre`, qui
--     reste : c'est la place de la catégorie dans la navigation.
--
-- Ce que cette migration ajoute : l'état `a_classer` d'un travail. Un fichier
-- déposé à la racine, ou dans un dossier qu'aucun type ne réclame, s'arrête là
-- — **avant l'océrisation** (décision D6) : le texte reconnu ne servirait à rien
-- tant qu'on ne sait pas de quel type de document il s'agit, et l'étape coûteuse
-- n'a pas à être faite deux fois.
--
-- Perte assumée : les expressions de classement déjà écrites. Elles ne
-- décrivaient qu'une façon de deviner ce qui se déclare désormais.

ALTER TABLE sys_jobs
    MODIFY COLUMN statut ENUM('en_attente','en_cours','termine','erreur','bloque',
                              'ignore','a_classer') DEFAULT 'en_attente';

ALTER TABLE sys_categories
    DROP COLUMN regex_identification,
    DROP COLUMN priorite;
