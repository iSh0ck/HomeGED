-- La fiche de liaison devient une fiche simple (§22.1).
--
-- La fiche de liaison s'adossait à une table du foyer : pour qu'elle rassemble
-- quoi que ce soit, il fallait déclarer la table, un champ qui y puise, et
-- remplir ce champ sur chaque document. Trois réglages avant le premier
-- résultat — et un écran qui montrait des lignes vides tant qu'ils n'étaient pas
-- tous faits. L'utilisateur l'a dit sans détour : « pas du tout viable ».
--
-- La **fiche simple** la remplace, et ne s'adosse à rien. Elle porte des
-- documents comme un type de document, à une différence près : **rien n'y entre
-- tout seul**. Pas de dossier sous `ocr_wait`, donc pas de dépôt automatique —
-- on y glisse un fichier à la main, et l'on remplit ses valeurs. C'est ce qui
-- convient à ce qu'on reçoit rarement et qu'aucune règle ne saurait lire : un
-- acte notarié, une carte grise, un contrat signé.
--
-- Les fiches existantes sont conservées, telles quelles, sans leur table : elles
-- n'avaient de toute façon rien rassemblé, et ce qui y aurait été rattaché l'est
-- par les métadonnées des documents, qui ne bougent pas.

UPDATE sys_categories SET nature = 'fiche' WHERE nature = 'liaison';
UPDATE sys_categories SET table_source = NULL WHERE nature = 'fiche';

-- Une fiche n'a pas de dossier de dépôt : elle n'en avait déjà pas, la règle est
-- seulement rendue explicite ici pour les bases où un changement de nature en
-- aurait laissé un.
UPDATE sys_categories SET dossier_depot = NULL WHERE nature <> 'type';
