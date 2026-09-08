-- Tri par défaut du registre, réglable catégorie par catégorie (§18.49).
--
-- Le registre s'ouvrait sur un tri écrit en dur dans l'interface : date de dépôt,
-- la plus récente d'abord. Ce n'est pas le bon tri pour tout le monde ni pour
-- toute catégorie — des factures se lisent par date d'émission, des courriers par
-- émetteur — et rien ne permettait de le changer autrement qu'en cliquant sur une
-- colonne à chaque visite.
--
-- `tri_champ` parle le vocabulaire du moteur de filtres (`fournisseur`,
-- `date_document`, `meta:<cle>`) : toute colonne affichable est donc triable, sans
-- liste à tenir à part.
--
-- Vide, la catégorie hérite de son parent, puis du réglage général du foyer
-- (`tri_defaut_champ`). C'est la même règle que pour les colonnes : on ne règle
-- que ce qui doit différer.

ALTER TABLE sys_categories
    ADD COLUMN tri_champ VARCHAR(100) NULL AFTER ordre,
    ADD COLUMN tri_sens ENUM('asc','desc') NULL AFTER tri_champ;
