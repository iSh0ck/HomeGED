-- 010 — Registre des tables de données (§17)
--
-- L'administration permet de créer ses propres tables de référence — véhicules,
-- personnes du foyer, contrats... — destinées à alimenter des champs
-- personnalisés. Ce registre décrit ces tables : leur intitulé lisible, la
-- colonne qui sert de libellé, et surtout **le fait qu'elles sont gérables
-- depuis l'interface**.
--
-- C'est ce registre qui fonde la séparation de sécurité : les tables du
-- fonctionnement de l'application (documents, utilisateurs, journal d'audit,
-- migrations...) ne s'y trouvent jamais et restent donc consultables sans être
-- modifiables. Écrire directement dans `documents` depuis une grille générique
-- court-circuiterait les droits, la conformité, l'audit et la gestion des
-- fichiers ; y modifier `utilisateurs` ou `journal_audit` ruinerait la sécurité
-- et la traçabilité.
--
-- Les tables créées portent physiquement le préfixe `donnees_`, ce qui évite
-- toute collision avec les tables du système et rend la frontière lisible.

CREATE TABLE IF NOT EXISTS tables_donnees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_table VARCHAR(64) NOT NULL UNIQUE,   -- nom physique, préfixé `donnees_`
    libelle VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,
    colonne_libelle VARCHAR(64) NULL,        -- colonne à afficher pour désigner une ligne
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
