-- Le type d'un champ libre (§22.12).
--
-- « Ajouter un champ attendu » ne proposait que deux natures : reprendre un champ
-- déjà connu (issu d'une règle d'extraction ou du document), ou adosser le champ
-- à une table du foyer. Déclarer une **valeur nouvelle** — « ce qui a été fait »,
-- « kilométrage », « date d'intervention » — obligeait donc à inventer une clé
-- technique à la main et à espérer que l'écran devine comment la saisir.
--
-- Le type se déclare donc, comme le reste : texte, texte long, date, nombre,
-- montant, oui/non. C'est lui qui décide de la façon dont le champ se saisit et
-- se relit — un champ dont on ne sait pas s'il porte une date ou une phrase se
-- saisit toujours de la mauvaise manière.
--
-- 'texte' par défaut : c'est ce que faisaient tous les champs existants, et la
-- migration ne doit rien changer à ce qui marche.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN type_champ VARCHAR(20) NOT NULL DEFAULT 'texte';
