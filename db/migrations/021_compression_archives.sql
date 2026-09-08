-- Compression des archives (§17.8).
--
-- `taille_octets` : taille du fichier archivé. Conservée en base pour que
-- l'administration sache ce que pèse le stockage sans parcourir le disque à
-- chaque affichage.
--
-- `date_compression` : quand le fichier a été repris par l'optimiseur. NULL
-- signifie « jamais tenté » ; c'est ce qui permet au serveur de travaux de
-- reprendre les archives par petits lots sans repasser indéfiniment sur les
-- mêmes. Un fichier que l'optimiseur n'a pas su réduire est daté lui aussi :
-- il a été examiné, la réponse était non.
--
-- L'empreinte `hash_sha256` n'est pas touchée : elle porte sur le **fichier
-- d'origine**, celui qui a été déposé, et sert à refuser un doublon à l'import.
-- Recompresser l'archive ne change pas ce qui a été reçu.

ALTER TABLE sys_documents
    ADD COLUMN IF NOT EXISTS taille_octets BIGINT NULL,
    ADD COLUMN IF NOT EXISTS date_compression DATETIME NULL;
