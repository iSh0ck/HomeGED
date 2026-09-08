-- Le contrôle d'intégrité des archives (§21.3).
--
-- Nous posions une empreinte SHA-256 à l'import, et **personne ne la
-- revérifiait jamais**. Une archive familiale est pourtant censée durer vingt
-- ans : un disque se dégrade, une synchronisation se trompe de sens, un
-- programme écrit là où il ne devait pas. Rien de tout cela ne prévient, et sans
-- contrôle on ne s'en aperçoit que le jour où l'on ouvre le document — c'est-à-dire
-- le jour où l'on en a besoin.
--
--   `empreinte_archive` : l'empreinte du **fichier archivé**, et non celle du
--     fichier reçu que porte déjà `hash_sha256`. Les deux diffèrent dès qu'un
--     document est océrisé ou compressé : comparer l'archive au fichier reçu
--     signalerait une altération à chaque document, ce qui revient à ne rien
--     signaler du tout.
--   `date_controle`    : quand elle a été vérifiée pour la dernière fois. C'est
--     par elle qu'on choisit qui contrôler ensuite — les plus anciennes d'abord,
--     ce qui fait tourner l'archive entière sans jamais la relire d'un coup.
--   `integrite`        : NULL (jamais contrôlée), 'ok', 'alteree', 'absent'.

ALTER TABLE sys_documents
    ADD COLUMN empreinte_archive VARCHAR(64) NULL,
    ADD COLUMN date_controle DATETIME NULL,
    ADD COLUMN integrite VARCHAR(20) NULL,
    ADD KEY idx_documents_controle (date_controle);
