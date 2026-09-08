-- Un dossier de dépôt par type de document (§19.2).
--
-- Le classement cesse d'être deviné pour devenir déclaré : celui qui dépose
-- choisit le dossier, et c'est cet emplacement qui fera foi (§19.3). Chaque
-- **type de document** a donc un dossier à lui sous `ocr_wait/`, à plat — un
-- seul niveau, quel que soit l'endroit du type dans l'arborescence (décision D2
-- de la phase : chemins courts pour un scanner à destinations préprogrammées).
--
-- Un **dossier** de classement n'en a pas : il ne reçoit aucun document.
--
-- Le nom est proposé d'après celui du type (« Relevés bancaires » →
-- `releves_bancaires`) et **modifiable** depuis l'administration : c'est un
-- chemin que des gens tapent et qu'un scanner mémorise, il ne doit pas dépendre
-- d'une majuscule ou d'un accent dans un intitulé.
--
-- La colonne est laissée vide ici : c'est l'application qui la remplit, au
-- premier passage, avec la même fonction que celle qui proposera les noms
-- suivants. Écrire deux fois la règle de nommage — une fois en SQL, une fois en
-- Python — reviendrait à en avoir deux, et elles divergeraient.
--
-- L'unicité est portée par la base : deux types visant le même dossier
-- rendraient le dépôt ambigu, et c'est exactement ce que la phase supprime.

ALTER TABLE sys_categories
    ADD COLUMN dossier_depot VARCHAR(64) NULL AFTER nature,
    ADD UNIQUE KEY uq_categorie_depot (dossier_depot);
