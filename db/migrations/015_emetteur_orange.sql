-- 015 — Émetteur « Orange »
--
-- La liste d'émetteurs livrée à l'origine (EDF, Impots.gouv, Free Mobile) ne
-- couvrait pas le seul document réel présent : une facture Orange. La catégorie
-- « Factures » exigeant un émetteur, le document restait « incomplet » alors que
-- tout le reste était correctement extrait.

INSERT INTO fournisseurs (nom, regex_identification)
SELECT 'Orange', '(?i)\\bOrange\\b'
WHERE NOT EXISTS (SELECT 1 FROM fournisseurs WHERE nom = 'Orange');
