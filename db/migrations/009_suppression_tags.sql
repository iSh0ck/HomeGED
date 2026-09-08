-- 009 — Suppression du système de tags (§18)
--
-- Les tags ont été retirés de l'interface, de l'API et du modèle. Cette
-- migration retire ce qui reste en base.
--
-- Ordre imposé par les clés étrangères : la table de jointure d'abord, la table
-- des tags ensuite.
--
-- Vérifié avant écriture de cette migration : 0 tag et 0 association en base,
-- la suppression ne détruit donc aucune donnée saisie. Si vous rejouez ce projet
-- sur une base contenant des tags, exportez-les avant d'appliquer cette migration.

-- Une règle de champ pouvait exiger « tags » sur une catégorie : sans ce
-- nettoyage, elle porterait sur un champ qui n'existe plus et bloquerait
-- indéfiniment tous les documents de cette catégorie.
DELETE FROM regles_champs_categorie WHERE champ = 'tags';

DROP TABLE IF EXISTS document_tags;
DROP TABLE IF EXISTS tags;
