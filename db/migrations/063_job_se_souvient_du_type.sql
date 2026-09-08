-- Un travail se souvient de son type de document (§21.15).
--
-- Le classement vient de l'**emplacement du dépôt** (§19.3), et lui seul. C'est
-- une bonne règle : rien n'est deviné sur le texte. Mais elle a un angle mort —
-- au **rejeu**, le fichier n'est plus dans le dossier où on l'avait mis : il vit
-- dans `travaux/`, où le serveur l'avait conservé. L'emplacement ne dit donc plus
-- rien, et un travail rejoué retombait « à classer » alors qu'il avait été classé
-- une première fois. On redemandait à quelqu'un une réponse déjà donnée.
--
-- Le travail garde désormais le type reconnu au dépôt. C'est un **souvenir**, pas
-- une consigne : l'emplacement reste maître quand il parle, et ce champ ne sert
-- que lorsqu'il s'est tu.

ALTER TABLE sys_jobs
    ADD COLUMN categorie_id INT NULL,
    ADD CONSTRAINT fk_jobs_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE SET NULL;

-- Les travaux déjà passés retrouvent leur type par le document qu'ils ont produit.
UPDATE sys_jobs j
  JOIN sys_documents d ON d.id = j.document_id
   SET j.categorie_id = d.categorie_id
 WHERE j.categorie_id IS NULL AND d.categorie_id IS NOT NULL;
