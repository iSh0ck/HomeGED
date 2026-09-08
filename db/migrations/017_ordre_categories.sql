-- 017 — Ordre d'affichage des catégories
--
-- La navigation classait les catégories par ordre alphabétique. On veut pouvoir
-- décider de leur ordre : mettre « Factures » avant « Assurances » parce qu'on
-- y va tous les jours, indépendamment de l'alphabet.
--
-- Une colonne distincte de `priorite`, et non un réemploi : `priorite` fixe
-- l'ordre dans lequel les regex de classement sont **testées** (la première qui
-- correspond l'emporte). Les deux notions n'ont aucune raison de coïncider —
-- on peut vouloir tester « Factures » en premier tout en l'affichant en
-- dernier. Les confondre rendrait chaque réglage imprévisible pour l'autre.

ALTER TABLE categories ADD COLUMN IF NOT EXISTS ordre INT NOT NULL DEFAULT 100 AFTER priorite;
