-- 014 — Règles d'extraction réécrites sur des documents réels
--
-- Les quatre règles livrées à l'origine étaient des exemples théoriques : elles
-- attendaient « Facture n° X » et « Total TTC », formulations qu'aucune facture
-- réelle testée n'emploie. Une facture d'opérateur écrit « n° de facture : X »,
-- « date de facture : 21/08/26 » (année sur deux chiffres) et « total auprès
-- d'Orange 50,99 € ». Aucune des quatre ne trouvait donc quoi que ce soit.
--
-- Stratégie retenue : pour chaque champ, une règle **ciblée** sur l'intitulé
-- réel (priorité basse, donc testée en premier), puis des **variantes** pour
-- les autres formulations courantes, et enfin un **repli** générique. La
-- première qui trouve l'emporte (cf. app/regex_engine.py).
--
-- Les règles d'origine ne sont retirées que si elles n'ont pas été retouchées :
-- une expression personnalisée par l'utilisateur ne doit pas disparaître ici.

DELETE FROM regles_extraction WHERE champ_cible = 'numero_facture'
  AND pattern = 'Facture\\s*n[°o]?\\s*[:\\-]?\\s*([A-Z0-9\\-\\/]{4,20})';
DELETE FROM regles_extraction WHERE champ_cible = 'montant_ttc'
  AND pattern = 'Total\\s*TTC\\s*[:\\-]?\\s*([0-9]+[,\\.][0-9]{2})\\s*€?';
DELETE FROM regles_extraction WHERE champ_cible = 'date_document'
  AND pattern = '\\b([0-3][0-9]/[0-1][0-9]/[0-9]{4})\\b';

-- --- Numéro de facture ---
INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite, actif)
SELECT 'Numéro de facture (n° de facture : …)', 'numero_facture',
       '(?im)^\\s*n[°ºo]\\s*de\\s+facture\\s*:\\s*(\\S.*?)\\s*$', 'texte', 10, TRUE
WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE nom = 'Numéro de facture (n° de facture : …)');

INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite, actif)
SELECT 'Numéro de facture (facture n° …)', 'numero_facture',
       '(?i)facture\\s*n[°ºo]\\s*:?\\s*([A-Z0-9][A-Z0-9\\-/]{3,25})', 'texte', 11, TRUE
WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE nom = 'Numéro de facture (facture n° …)');

-- --- Date du document ---
INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite, actif)
SELECT 'Date de facture (intitulée)', 'date_document',
       '(?i)date\\s*(?:de\\s+)?facture\\s*:?\\s*([0-3]?\\d[/.\\-][01]?\\d[/.\\-]\\d{2,4})', 'date', 20, TRUE
WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE nom = 'Date de facture (intitulée)');

INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite, actif)
SELECT 'Date du document (repli : première date trouvée)', 'date_document',
       '\\b([0-3]\\d[/.\\-][01]\\d[/.\\-](?:\\d{4}|\\d{2}))\\b', 'date', 90, TRUE
WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE nom = 'Date du document (repli : première date trouvée)');

-- --- Montant TTC ---
INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite, actif)
SELECT 'Montant TTC (total TTC / à payer)', 'montant_ttc',
       '(?i)(?:total|montant)\\s*(?:à\\s*payer|ttc)\\s*:?\\s*([0-9]{1,3}(?:[  ][0-9]{3})*[,.][0-9]{2})', 'montant', 29, TRUE
WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE nom = 'Montant TTC (total TTC / à payer)');

INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite, actif)
SELECT 'Montant TTC (total … €)', 'montant_ttc',
       '(?i)total[^\\n]{0,40}?([0-9]{1,3}(?:[  ][0-9]{3})*,[0-9]{2})\\s*€', 'montant', 30, TRUE
WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE nom = 'Montant TTC (total … €)');

-- --- Références utiles au rapprochement ---
INSERT INTO regles_extraction (nom, champ_cible, pattern, type_champ, priorite, actif)
SELECT 'Numéro de client', 'numero_client',
       '(?im)^\\s*n[°ºo]\\s*(?:de\\s+)?client\\s*:\\s*(\\S.*?)\\s*$', 'texte', 50, TRUE
WHERE NOT EXISTS (SELECT 1 FROM regles_extraction WHERE nom = 'Numéro de client');
