-- 012 — Booléens à NULL : correction et prévention
--
-- Symptôme : l'onglet « Règles de champs » renvoyait une erreur 500, et surtout
-- **aucune règle d'extraction ne s'appliquait**. Le moteur sélectionne les
-- règles avec `actif IS TRUE` ; les quatre règles par défaut ayant `actif =
-- NULL`, elles étaient silencieusement écartées depuis leur création.
--
-- Cause : `Base.metadata.create_all()` s'exécutait avant les migrations et
-- créait les tables d'après le modèle Python. Or `Column(Boolean, default=True)`
-- est une valeur par défaut appliquée **côté Python**, pas une clause DEFAULT
-- SQL : les tables obtenues n'en avaient aucune, et le `CREATE TABLE IF NOT
-- EXISTS` de la migration suivante ne faisait plus rien. Une insertion en SQL
-- brut (migration 003) laissait donc la colonne à NULL.
--
-- Correction en trois temps : les valeurs existantes sont rétablies, les
-- colonnes deviennent NOT NULL avec une vraie valeur par défaut — de sorte
-- qu'aucune insertion ne puisse plus les laisser vides — et `create_all()` est
-- retiré du worker (cf. app/worker.py) pour que schéma et migrations restent
-- l'unique source de vérité.

UPDATE regles_extraction SET actif = TRUE WHERE actif IS NULL;
UPDATE utilisateurs SET actif = TRUE WHERE actif IS NULL;
UPDATE utilisateurs SET est_admin = FALSE WHERE est_admin IS NULL;
UPDATE droits_categorie SET peut_voir = TRUE WHERE peut_voir IS NULL;
UPDATE droits_categorie SET peut_modifier = FALSE WHERE peut_modifier IS NULL;
UPDATE vues_enregistrees SET partagee = FALSE WHERE partagee IS NULL;
UPDATE regles_champs_categorie SET obligatoire = TRUE WHERE obligatoire IS NULL;
UPDATE jobs SET rejouer_demande = FALSE WHERE rejouer_demande IS NULL;

ALTER TABLE regles_extraction MODIFY actif BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE utilisateurs MODIFY actif BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE utilisateurs MODIFY est_admin BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE droits_categorie MODIFY peut_voir BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE droits_categorie MODIFY peut_modifier BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE vues_enregistrees MODIFY partagee BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE regles_champs_categorie MODIFY obligatoire BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE jobs MODIFY rejouer_demande BOOLEAN NOT NULL DEFAULT FALSE;
