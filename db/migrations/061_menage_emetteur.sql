-- Ménage après le passage de l'émetteur au générique (§21.13).
--
-- 1. **L'IBAN livré d'office.** Le jeu de règles générique de *chaque* type
--    portait une règle « IBAN » — y compris pour des contrats de travail ou des
--    diplômes, qui n'en contiennent pas. Elle vient de la base livrée, personne
--    ne l'a demandée, et elle encombrait la liste des champs de tous les types.
--    On ne retire que celles **restées telles quelles** : une règle retouchée a
--    été voulue, et se garde.
--
-- 2. **Les valeurs de référence saisies sans leur source.** Un champ adossé à une
--    table et rempli à la main rangeait « 5 » au lieu de « usr_emetteurs:5 » : la
--    valeur ne se relisait plus, et l'émetteur « n'était pas trouvé » alors qu'il
--    venait d'être choisi. L'API préfixe désormais à l'écriture ; il reste à
--    réparer ce qui a été saisi avant.

DELETE r FROM sys_regles_extraction r
 WHERE r.nom = 'IBAN'
   AND r.champ_cible = 'iban'
   AND r.pattern LIKE '%FR[0-9]{2}%';

-- Les métadonnées d'un champ à source **unique** dont la valeur est un simple
-- nombre : on rétablit la référence. Les champs à sources multiples sont laissés
-- tels quels — on ne devine pas laquelle a été choisie.
UPDATE sys_metadonnees m
  JOIN sys_documents d ON d.id = m.document_id
  JOIN sys_regles_champs_categorie r
    ON r.categorie_id = d.categorie_id
   AND r.champ = CONCAT('meta:', m.cle)
   SET m.valeur = CONCAT(r.sources, ':', m.valeur)
 WHERE m.valeur REGEXP '^[0-9]+$'
   AND r.sources IS NOT NULL
   AND r.sources <> ''
   AND r.sources NOT LIKE '%,%';
