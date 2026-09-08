-- Préférences d'affichage, par personne (§19.20).
--
-- Ouvrir une fiche chargeait le PDF entier — plusieurs mégaoctets pour
-- reconnaître un document, à chaque clic de ligne. Une image de la première page
-- suffit la plupart du temps ; le PDF reste à un clic pour qui veut lire.
--
-- Le choix est **personnel** et non de foyer : il dépend de la machine et de la
-- liaison de celui qui regarde, pas d'une décision commune. Sur un portable en
-- 4G, la miniature change tout ; sur un poste fixe, le document entier ne coûte
-- rien.
--
--   `mode_apercu` : 'document' (le PDF, comme avant) ou 'miniature'.
--   `champs_masques` : montrer aussi, sur la fiche, les colonnes que
--     l'administrateur a retirées du tableau. Masquer une colonne d'un tableau
--     qu'on parcourt n'est pas la même décision que la cacher sur la fiche.

ALTER TABLE sys_utilisateurs
    ADD COLUMN mode_apercu VARCHAR(20) NOT NULL DEFAULT 'document',
    ADD COLUMN champs_masques BOOLEAN NOT NULL DEFAULT FALSE;
