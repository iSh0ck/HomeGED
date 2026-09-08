-- Réglages généraux de l'application (§18.19).
--
-- Jusqu'ici, tout ce qui se règle vivait dans `.env` : il fallait un accès au
-- serveur et un redémarrage pour changer quoi que ce soit. Le fuseau horaire est
-- le premier réglage qui n'a rien à faire là — il ne concerne pas le
-- fonctionnement du service mais la façon dont les gens du foyer lisent les
-- heures affichées, et cela se décide depuis l'interface.
--
-- Une table clé/valeur plutôt qu'une colonne par réglage : ce qui s'ajoutera
-- ensuite n'imposera pas de migration, et un réglage retiré ne laisse pas une
-- colonne orpheline. Les valeurs sont du texte ; c'est le code qui sait les
-- relire, et qui retombe sur un défaut sain si la valeur ne veut rien dire.

CREATE TABLE IF NOT EXISTS sys_reglages (
    cle VARCHAR(64) NOT NULL PRIMARY KEY,
    valeur TEXT NULL,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Le fuseau du foyer. Les horodatages restent stockés en UTC — c'est ce qui
-- permet de changer ce réglage sans réécrire l'histoire ; seule leur lecture
-- change.
INSERT INTO sys_reglages (cle, valeur) VALUES ('fuseau_horaire', 'Europe/Paris')
    ON DUPLICATE KEY UPDATE cle = cle;
