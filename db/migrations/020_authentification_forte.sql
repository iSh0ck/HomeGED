-- Authentification à deux facteurs (TOTP) et invalidation des sessions.
--
-- `otp_secret` est la graine partagée avec l'application d'authentification.
-- Elle n'est jamais renvoyée par l'API une fois l'activation confirmée : elle
-- ne sert plus qu'à vérifier les codes.
--
-- `otp_impose` est la décision d'un administrateur : le compte doit configurer
-- sa double authentification. Tant qu'il ne l'a pas fait, l'API ne lui répond
-- que sur les routes de configuration — imposer sans contraindre ne serait
-- qu'une suggestion.
--
-- `otp_codes_secours` conserve des codes d'usage unique, hachés comme des mots
-- de passe : un téléphone perdu ne doit pas fermer définitivement la porte.
--
-- `jeton_version` rend un changement de mot de passe efficace : les jetons déjà
-- délivrés portent la version qui avait cours: l'incrémenter les périme tous,
-- y compris ceux d'un intrus qui aurait ouvert une session avant.

ALTER TABLE sys_utilisateurs
    ADD COLUMN IF NOT EXISTS otp_secret VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS otp_actif BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS otp_impose BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS otp_codes_secours TEXT NULL,
    ADD COLUMN IF NOT EXISTS jeton_version INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS date_mot_de_passe DATETIME NULL;
