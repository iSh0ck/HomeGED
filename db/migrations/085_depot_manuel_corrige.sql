-- Le marqueur d'origine, remis à zéro (§22.72).
--
-- La migration 084 déduisait l'origine de `sys_jobs.chemin_source`. C'était
-- faux : le fichier reçu est **rangé à côté de son travail** à la fin du
-- traitement (§18.53), dans le dossier des travaux, quelle que soit sa
-- provenance. Le chemin y menait donc pour tout le monde, et tous les documents
-- se sont retrouvés marqués « déposé à la main » — y compris ceux qu'un dossier
-- surveillé avait pris tout seuls.
--
-- Rien ne permet de rattraper l'information : la trace de l'origine n'existe
-- nulle part une fois le fichier rangé. On efface donc ce qui a été déduit à
-- tort plutôt que de le laisser mentir. Le marqueur repart de zéro, et les
-- documents suivants le porteront correctement.

UPDATE sys_documents SET depot_manuel = NULL WHERE depot_manuel IS NOT NULL;
