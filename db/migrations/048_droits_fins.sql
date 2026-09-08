-- Droits fins : par action, par emplacement, avec héritage (§19.12).
--
-- Un rôle disait deux choses par catégorie — voir, modifier — et tout le reste
-- tenait dans un unique interrupteur `est_admin` : soit on ne peut rien
-- administrer, soit on peut tout, y compris sortir l'archive entière du foyer.
-- Pour un foyer où quelqu'un doit pouvoir ranger les factures sans pouvoir
-- supprimer un contrat ni exporter l'archive, il n'y avait pas de réponse.
--
-- Trois axes, et c'est leur croisement qui fait la finesse.
--
-- 1. **Ce qu'on peut faire d'un document** : six droits là où il y en avait
--    deux. `telecharger` mérite d'être distingué de `voir` — laisser quelqu'un
--    lire une fiche n'oblige pas à lui donner le PDF ; `gerer_versions` de
--    `modifier` — supprimer une version détruit un fichier, corriger un champ
--    non.
--
-- 2. **Où** : sur un dossier, valable pour tous ses types ; ou sur un type, qui
--    l'emporte alors sur ce que dit son dossier. L'absence de ligne signifie
--    « hérité » — c'est la présence d'une ligne qui fait l'exception, jamais un
--    troisième état à renseigner. Sans cet héritage, ouvrir un dossier à
--    quelqu'un demanderait de cocher chacun de ses types, et d'y repenser à
--    chaque type ajouté : le genre d'oubli qui donne un accès qu'on croyait
--    fermé.
--
-- 3. **Ce qu'on peut faire du reste** : droits généraux, hors catégorie,
--    déclarés en dur dans le code (ce sont des points d'entrée, pas des données)
--    et attribués aux rôles ici.
--
-- Migration des droits en place, et c'est le point délicat : un `peut_modifier`
-- d'aujourd'hui **vaut modifier + déposer + supprimer + versions**, et un
-- `peut_voir` vaut aussi `telecharger`. Répartir autrement retirerait en silence
-- des droits dont personne ne se souvient les avoir donnés — une migration qui
-- restreint sans le dire est pire qu'une migration qui ne fait rien.
--
-- Les vues enregistrées reçoivent leur propre table de droits : une vue est une
-- lecture préfiltrée du registre, et toutes n'ont pas à être offertes à tout le
-- monde. `partagee` restait binaire — privée, ou visible de tous.

ALTER TABLE sys_droits_categorie
    ADD COLUMN peut_deposer BOOLEAN NOT NULL DEFAULT FALSE AFTER peut_modifier,
    ADD COLUMN peut_telecharger BOOLEAN NOT NULL DEFAULT TRUE AFTER peut_deposer,
    ADD COLUMN peut_supprimer BOOLEAN NOT NULL DEFAULT FALSE AFTER peut_telecharger,
    ADD COLUMN peut_gerer_versions BOOLEAN NOT NULL DEFAULT FALSE AFTER peut_supprimer;

UPDATE sys_droits_categorie
SET peut_deposer = peut_modifier,
    peut_supprimer = peut_modifier,
    peut_gerer_versions = peut_modifier,
    peut_telecharger = peut_voir;

-- Droits généraux d'un rôle. La clé est le nom du droit tel que le code le
-- déclare : une table de correspondance en base se désynchroniserait du jour où
-- l'on renommerait un point d'entrée.
CREATE TABLE IF NOT EXISTS sys_droits_generaux (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    droit VARCHAR(40) NOT NULL,
    CONSTRAINT fk_droits_generaux_role FOREIGN KEY (role_id)
        REFERENCES sys_roles(id) ON DELETE CASCADE,
    UNIQUE KEY uq_role_droit (role_id, droit)
) ENGINE=InnoDB;

-- Visibilité d'une vue enregistrée, rôle par rôle. Une vue sans aucune ligne ici
-- suit `partagee` comme avant : ce n'est pas parce qu'on peut restreindre qu'il
-- faut obliger chaque foyer à le faire.
CREATE TABLE IF NOT EXISTS sys_droits_vue (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    vue_id INT NOT NULL,
    CONSTRAINT fk_droits_vue_role FOREIGN KEY (role_id)
        REFERENCES sys_roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_droits_vue_vue FOREIGN KEY (vue_id)
        REFERENCES sys_vues_enregistrees(id) ON DELETE CASCADE,
    UNIQUE KEY uq_role_vue (role_id, vue_id)
) ENGINE=InnoDB;
