-- La corbeille des documents (§21.1).
--
-- Jusqu'ici, supprimer un document effaçait la fiche sur-le-champ et le serveur
-- de travaux balayait le fichier au passage suivant : **rien n'était
-- récupérable**, dans une maison où chacun a le droit de supprimer. C'est le
-- manque le plus grave qu'ait révélé la comparaison avec EzGED.
--
-- Le document n'est donc plus effacé mais **daté** : il quitte le registre,
-- garde sa place, ses métadonnées, ses versions et son fichier, et se restaure
-- exactement là où il était.
--
--   `date_suppression` : vide = document vivant. C'est le seul critère, et il
--     porte un index parce que **toutes** les listes le consultent.
--   `supprime_par_id`  : qui l'a jeté — c'est ce qui donne à chacun sa corbeille.
--     Le compte peut disparaître ensuite ; le document, lui, reste en corbeille
--     (SET NULL) et l'administration le retrouve.
--   `corbeille_masquee`: supprimé une seconde fois, depuis sa propre corbeille.
--     Il sort alors de la vue de son auteur et n'existe plus que pour
--     l'administration — le second filet d'EzGED, celui qui rattrape le geste
--     de trop.

ALTER TABLE sys_documents
    ADD COLUMN date_suppression DATETIME NULL,
    ADD COLUMN supprime_par_id INT NULL,
    ADD COLUMN corbeille_masquee BOOLEAN NOT NULL DEFAULT FALSE,
    ADD KEY idx_documents_suppression (date_suppression),
    ADD CONSTRAINT fk_documents_supprime_par
        FOREIGN KEY (supprime_par_id) REFERENCES sys_utilisateurs(id) ON DELETE SET NULL;
