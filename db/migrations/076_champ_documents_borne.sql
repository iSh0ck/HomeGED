-- Un champ « documents » se borne (§22.14).
--
-- « Le bouton "Documents de la GED" est trop général : il faut pouvoir choisir un
-- type de document, et par quels champs la recherche peut se faire. »
--
-- C'est juste. « Factures liées » sous un entretien ne devrait proposer que des
-- factures, et se chercher par leur numéro ou leur émetteur — pas par le texte
-- entier de toute la GED, où l'on retrouve le mot « facture » sur la moitié des
-- documents. Un champ qui propose tout ne guide personne.
--
-- Deux colonnes, et rien de plus : le type accepté, et les champs sur lesquels
-- la recherche porte. Vides, elles gardent le comportement d'avant — tout type,
-- recherche sur le nom et le texte reconnu.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN documents_categorie_id INT NULL,
    ADD COLUMN documents_champs VARCHAR(255) NULL;

ALTER TABLE sys_regles_champs_categorie
    ADD CONSTRAINT fk_regle_documents_categorie FOREIGN KEY (documents_categorie_id)
        REFERENCES sys_categories(id) ON DELETE SET NULL;
