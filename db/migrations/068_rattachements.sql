-- Rattacher deux documents à la main (§22.4).
--
-- Le rapprochement par valeur partagée (§19.19, §22) réunit ce qui **désigne la
-- même chose** : deux papiers qui nomment le même véhicule se retrouvent sans
-- qu'on ait rien à faire. C'est le cas le plus fréquent, et il ne demande aucun
-- geste.
--
-- Reste ce qui ne partage rien et se répond quand même : un contrat et son
-- avenant, une facture et son litige, une ordonnance et son remboursement.
-- Aucune valeur commune ne les relie — seul quelqu'un qui les a lus le sait.
-- D'où ce lien **posé à la main**, et symétrique : vu d'un côté comme de
-- l'autre, parce qu'un avenant sans son contrat n'a pas plus de sens que
-- l'inverse.

CREATE TABLE IF NOT EXISTS sys_rattachements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    -- Toujours (petit, grand) : le couple est rangé à l'écriture, ce qui rend
    -- l'unicité vraie dans les deux sens sans avoir à y penser à la lecture.
    document_a INT NOT NULL,
    document_b INT NOT NULL,
    -- Ce que le lien veut dire, quand celui qui le pose sait le nommer :
    -- « avenant », « remboursement ». Facultatif — un lien sans mot vaut mieux
    -- qu'un lien qu'on renonce à poser.
    libelle VARCHAR(120) NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    CONSTRAINT fk_rattachement_a FOREIGN KEY (document_a)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_rattachement_b FOREIGN KEY (document_b)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_rattachement_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_rattachement (document_a, document_b),
    KEY idx_rattachement_b (document_b)
) ENGINE=InnoDB;

-- Ce que l'administration autorise à rattacher (§22.4).
--
-- Tant que **rien** n'est déclaré, tout est permis : un réglage vide ne doit pas
-- interdire une fonction, sans quoi personne ne comprendrait pourquoi le bouton
-- refuse. Dès qu'une paire est déclarée, elles seules sont permises — c'est le
-- moment où l'on décide que ce foyer relie des contrats à des avenants, et rien
-- d'autre.
CREATE TABLE IF NOT EXISTS sys_rattachements_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_a INT NOT NULL,
    categorie_b INT NOT NULL,
    libelle VARCHAR(120) NULL,
    CONSTRAINT fk_rattachement_type_a FOREIGN KEY (categorie_a)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_rattachement_type_b FOREIGN KEY (categorie_b)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    UNIQUE KEY uq_rattachement_type (categorie_a, categorie_b)
) ENGINE=InnoDB;
