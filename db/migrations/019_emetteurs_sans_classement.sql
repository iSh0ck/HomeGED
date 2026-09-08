-- 019 — Les émetteurs ne servent plus au classement automatique
--
-- `usr_emetteurs` est devenue une table de données du foyer (migration 018).
-- Sa colonne `regex_identification` n'existait que pour un usage technique : le
-- worker s'en servait pour deviner l'émetteur d'un document à partir du texte
-- océrisé. Cet automatisme est retiré — l'émetteur se renseigne désormais à la
-- main, depuis la fiche du document ou le Centre d'analyse.
--
-- Les expressions existantes sont d'abord recopiées dans le journal d'audit :
-- supprimer une colonne détruit ses valeurs, autant en garder trace pour qui
-- voudrait les retrouver.

INSERT INTO sys_journal_audit (utilisateur_email, action, objet_type, objet_id, details)
SELECT NULL, 'emetteur.regex_retiree', 'emetteur', id,
       CONCAT('{"nom": "', REPLACE(nom, '"', '\\"'), '", "regex_identification": "',
              REPLACE(COALESCE(regex_identification, ''), '"', '\\"'), '"}')
FROM usr_emetteurs
WHERE regex_identification IS NOT NULL AND regex_identification <> '';

ALTER TABLE usr_emetteurs DROP COLUMN IF EXISTS regex_identification;
