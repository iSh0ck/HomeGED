-- L'état de conformité, rangé sur le document (§22.41).
--
-- « Ce document a-t-il tous ses champs obligatoires ? » était **recalculé à
-- chaque requête, pour chaque document** : le registre doit écarter les
-- documents incomplets, il posait donc la question à tout le monde, à chaque
-- page. Mesuré sur vingt mille documents : compter le registre coûtait 311 ms
-- avec ce calcul, 6 ms sans. Tout ce qui était lent l'était pour cette raison —
-- registre, tableau de bord, compteurs de la barre.
--
-- La réponse est écrite une fois, au moment où elle change : à la fin du
-- traitement d'un document, après une correction à la main, et par un recalcul
-- ciblé quand les champs attendus d'une catégorie changent. La lecture devient
-- une comparaison indexée.
--
-- `conforme` vaut TRUE par défaut, mais aucune ligne n'est laissée à ce défaut :
-- la mise à jour ci-dessous calcule la valeur réelle de chaque document, avec la
-- **même** définition que le code (cf. `app/conformite.py`). Un document sans
-- catégorie n'a aucune règle à respecter : il reste conforme.

ALTER TABLE sys_documents
    ADD COLUMN conforme BOOLEAN NOT NULL DEFAULT TRUE;

-- Peu de documents sont incomplets (quelques pour cent) : l'index sert surtout à
-- les compter et à les lister sans parcourir le registre entier.
CREATE INDEX idx_documents_conforme ON sys_documents (conforme);

-- La valeur de départ, calculée en SQL avec la définition du code : il manque au
-- document un champ obligatoire de sa catégorie.
UPDATE sys_documents d
SET conforme = NOT EXISTS (
    SELECT 1 FROM sys_regles_champs_categorie r
    WHERE r.categorie_id = d.categorie_id
      AND r.obligatoire = TRUE
      AND (
          (r.champ = 'date_document' AND d.date_document IS NULL)
          OR (r.champ = 'nom_fichier' AND (d.nom_fichier IS NULL OR d.nom_fichier = ''))
          OR (r.champ = 'statut' AND (d.statut IS NULL OR d.statut = ''))
          OR (r.champ LIKE 'meta:%' AND NOT EXISTS (
                  SELECT 1 FROM sys_metadonnees m
                  WHERE m.document_id = d.id
                    AND m.cle = SUBSTRING(r.champ, 6)
                    AND m.valeur IS NOT NULL
                    AND TRIM(m.valeur) <> ''))
      )
);
