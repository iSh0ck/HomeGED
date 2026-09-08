-- Fonctions d'extraction prêtes à l'emploi (§18.35).
--
-- Écrire une expression régulière pour attraper une date ou un montant est le
-- passage obligé du projet, et le plus ingrat : chaque foyer réécrit les mêmes
-- motifs, avec les mêmes oublis — l'année sur deux chiffres, l'espace insécable
-- des milliers, la virgule décimale.
--
-- Une règle peut désormais désigner une **fonction** qui fait ce travail :
--
--   premiere_date   la première date du texte, quelle que soit son écriture ;
--   montant_ttc     le montant TTC, en tolérant « 1 234,56 € » ;
--   chiffres_seuls  ne garde que les chiffres de ce que la regex a trouvé ;
--   sans_espaces    retire les espaces de ce que la regex a trouvé.
--
-- Les deux premières se passent d'expression : elles portent la leur. Les deux
-- dernières transforment ce qu'une expression a trouvé — d'où une colonne, et
-- non deux notions séparées : c'est la même règle, avec un traitement en plus.

ALTER TABLE sys_regles_extraction
    ADD COLUMN fonction VARCHAR(40) NULL AFTER pattern;

-- Le motif devient facultatif : une règle « première date » n'en a pas besoin.
ALTER TABLE sys_regles_extraction
    MODIFY COLUMN pattern VARCHAR(500) NULL;
