-- 008 — Étapes de traitement et purge des travaux (§13)
--
-- `etape` mémorise jusqu'où un travail est allé : on sait ainsi où il a échoué,
-- et on peut le reprendre à un point précis plutôt que de tout refaire. Reprendre
-- à « regles » réapplique les expressions régulières sur le texte déjà océrisé,
-- ce qui est immédiat, là où un OCR complet coûte plusieurs dizaines de secondes.
--
-- `etape_demandee` accompagne `rejouer_demande` : l'interface indique d'où
-- reprendre, le worker s'y conforme.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS etape VARCHAR(30) NULL AFTER statut;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS etape_demandee VARCHAR(30) NULL AFTER rejouer_demande;
