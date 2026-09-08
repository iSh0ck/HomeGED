-- La déduction automatique d'un champ à source devient une déclaration (§18.47).
--
-- Ce qui ne allait pas : dès qu'un champ était rattaché à une table du foyer,
-- l'application cherchait d'elle-même, dans le texte de chaque document, les
-- colonnes identifiantes de cette table — pour le titulaire, le prénom **et**
-- le nom. Le mécanisme était bon ; c'est qu'il était invisible qui ne l'était
-- pas. Rien à l'écran ne disait qu'il existait, ni ce qu'il cherchait, ni
-- comment le régler. Un titulaire apparaissait sur des factures sans que
-- personne ne l'ait demandé, et sans qu'on puisse savoir d'où il sortait.
--
-- Un rattachement que l'on n'a pas demandé se lit comme une erreur, même quand
-- il est juste : on ne peut pas le vérifier sans relire le document.
--
-- Désormais chaque champ dit ce qu'il veut :
--
--   * `deduction = 'aucune'`  — rien n'est déduit, le champ reste vide et se
--     remplit au Centre d'analyse. C'est la valeur par défaut, y compris pour
--     les champs déjà en place : personne n'a déclaré cette déduction, elle ne
--     doit donc pas continuer à s'exercer en sous-main.
--   * `deduction = 'toutes'` — la ligne n'est retenue que si **toutes** les
--     colonnes cherchées figurent dans le document. C'est le réglage sûr : deux
--     personnes d'une même famille portent le même nom.
--   * `deduction = 'une'`    — une seule colonne trouvée suffit. Utile pour une
--     immatriculation ou un numéro de contrat, qui ne se répètent pas.
--
-- `colonnes_deduction` dit **où chercher** : les colonnes de la table source,
-- séparées par des virgules. Vide, ce sont les colonnes identifiantes de la
-- table qui servent — ce qui était le comportement en dur.
--
-- Ce que cette migration change à l'usage : plus aucun champ n'est déduit tant
-- qu'un administrateur ne l'a pas déclaré, dans « Champs attendus ». Les
-- valeurs déjà rattachées, elles, restent en place — elles ont été vérifiées ou
-- elles ne l'ont pas été, ce n'est pas à une migration d'en juger.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN deduction VARCHAR(20) NOT NULL DEFAULT 'aucune' AFTER sources,
    ADD COLUMN colonnes_deduction VARCHAR(255) NULL AFTER deduction;
