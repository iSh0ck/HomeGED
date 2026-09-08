-- Les droits par branche (§21.7).
--
-- Nos droits se posent sur les **emplacements** — un dossier, un type — et rien
-- ne permettait de dire « ce rôle ne voit que 2025 et 2026 », ou « seulement les
-- documents du véhicule Clio ». EzGED y arrive en filtrant les **lignes** à
-- travers une table de droits jointe au groupe de l'utilisateur ; voici
-- l'équivalent, déclaré et lisible.
--
-- Une ligne = « ce rôle est autorisé sur cette valeur de ce champ ». Le sens de
-- l'absence compte autant que celui de la présence :
--
--   * **aucune ligne sur un champ** = aucune restriction sur ce champ. Pouvoir
--     restreindre n'oblige pas chaque foyer à le faire, et un rôle neuf ne doit
--     rien perdre.
--   * **une ou plusieurs lignes** = le rôle ne voit que ces valeurs-là.
--
-- Rien n'est dynamique : ce ne sont pas « mes documents », ce sont des branches
-- que l'administration a nommées — l'utilisateur l'a explicitement demandé.

CREATE TABLE IF NOT EXISTS sys_droits_branche (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,        -- vocabulaire du moteur de filtres
    valeur VARCHAR(255) NOT NULL,       -- la branche : « 2026 », « 4 », « usr_vehicules:3 »
    CONSTRAINT fk_droits_branche_role FOREIGN KEY (role_id)
        REFERENCES sys_roles(id) ON DELETE CASCADE,
    UNIQUE KEY uq_droit_branche (role_id, champ, valeur)
) ENGINE=InnoDB;
