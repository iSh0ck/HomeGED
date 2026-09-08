-- L'envoi des rappels par courriel (§21.10).
--
-- Les rappels du §21.9 n'existaient que dans l'application : encore fallait-il
-- l'ouvrir. Un rappel de contrôle technique doit venir vous chercher.
--
-- Ce que la base doit retenir, et rien de plus :
--
--   `sys_notifications.date_envoi` : ce qui est déjà parti ne repart pas. Sans
--     cette date, chaque passage aurait renvoyé toute la liste.
--   `sys_utilisateurs.courriel_rappels` : chacun peut ne pas vouloir être
--     dérangé par courriel sans pour autant perdre les rappels dans
--     l'application. C'est un réglage de personne, comme le mode d'affichage.
--   `palier_courriel` / `date_dernier_courriel` : les paliers d'EzGED (5 min,
--     15 min, 1 h, 24 h, 1 semaine, puis on cesse). Ils espacent les relances de
--     quelqu'un qui ne réagit pas, au lieu de répéter le même message chaque
--     heure — ce qui ferait cesser de les lire, ou basculer l'expéditeur dans les
--     indésirables.

ALTER TABLE sys_notifications
    ADD COLUMN date_envoi DATETIME NULL;

ALTER TABLE sys_utilisateurs
    ADD COLUMN courriel_rappels BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN palier_courriel INT NOT NULL DEFAULT 0,
    ADD COLUMN date_dernier_courriel DATETIME NULL;
