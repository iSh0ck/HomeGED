-- Le rapprochement déclaré sur le type de document (§22.8).
--
-- L'exemple que l'utilisateur donne est celui d'EzGED, et il vaut pour une
-- maison comme pour un bureau : un dossier porte un numéro, et ce numéro est
-- repris sur le devis, le bon de commande, le bon de livraison. Ouvrir l'un doit
-- montrer les autres — non pas parce qu'une machine l'a deviné, mais parce que
-- quelqu'un a **déclaré** que ce champ-là relie ces types-là.
--
-- C'est la différence avec le rapprochement automatique retiré au §22.7 : celui-ci
-- ne montre que ce qui a été paramétré, et l'on sait donc toujours pourquoi deux
-- documents se retrouvent côte à côte.
--
-- La déclaration se pose sur le **type**, et non sur la vue (§22.5) : un devis
-- appartient au dossier nº1234 quel que soit l'écran par lequel on l'ouvre. Les
-- vues montrent donc ces liens sans avoir à les redéclarer.

CREATE TABLE IF NOT EXISTS sys_liens_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    -- Le type qui déclare. La déclaration vaut **dans les deux sens** : ouvrir un
    -- devis montre son dossier comme ouvrir le dossier montre ses devis. Sans
    -- cela il faudrait déclarer six liens pour trois types, et l'on en oublierait
    -- toujours un.
    categorie_id INT NOT NULL,
    -- Le type d'en face. NULL : tous les types — c'est le cas du numéro de
    -- dossier, repris par des pièces de sortes très différentes.
    categorie_cible_id INT NULL,
    -- Les deux champs qui doivent porter la même valeur, dans le vocabulaire des
    -- filtres : `meta:numero_dossier`, `date_document`…
    champ_source VARCHAR(100) NOT NULL,
    champ_cible VARCHAR(100) NOT NULL,
    libelle VARCHAR(120) NULL,
    CONSTRAINT fk_lien_type_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_lien_type_cible FOREIGN KEY (categorie_cible_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    UNIQUE KEY uq_lien_type (categorie_id, categorie_cible_id, champ_source, champ_cible),
    KEY idx_lien_type_cible (categorie_cible_id)
) ENGINE=InnoDB;
