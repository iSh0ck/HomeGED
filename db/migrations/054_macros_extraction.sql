-- Macros d'extraction paramétrées et rapprochement approché (§21.4).
--
-- `parametre` : certaines fonctions ont besoin d'une valeur pour travailler —
--   le nombre de jours d'une échéance, le séparateur d'une concaténation. Sans
--   ce champ, il aurait fallu une fonction par valeur possible (« +30 jours »,
--   « +45 jours »…), c'est-à-dire coder en dur ce qui doit se régler.
--
-- `deduction_approchee` : accepter une petite différence entre le document et la
--   table du foyer. Un OCR lit « Hélene » pour « Hélène », « 0range » pour
--   « Orange ». La tolérance se déclare **champ par champ** et jamais par
--   défaut : sur un nom de personne elle rattrape des scans médiocres, sur une
--   immatriculation elle confondrait deux véhicules — un caractère les sépare.

ALTER TABLE sys_regles_extraction
    ADD COLUMN parametre VARCHAR(100) NULL;

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN deduction_approchee BOOLEAN NOT NULL DEFAULT FALSE;
