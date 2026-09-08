-- Des jeux de règles d'extraction, par type de document (§19.6).
--
-- Les règles formaient une liste unique, appliquée à tout document quel qu'il
-- soit. Elle grossit à chaque émetteur — EDF n'écrit pas ses numéros comme
-- Orange —, et chaque règle ajoutée est un risque pour les autres : une
-- expression un peu large attrape ce qui ne la regarde pas, sur des documents
-- qu'on n'avait pas en tête en l'écrivant.
--
-- Un **jeu de règles** répond aux deux problèmes à la fois :
--
--   * il appartient à un **type de document**, et ne s'applique qu'à lui. Une
--     règle écrite pour les factures ne touche plus les bulletins de paie ;
--   * il porte une **expression de reconnaissance**, cherchée dans le texte, qui
--     dit « c'est bien de celui-là qu'il s'agit ». C'est le retour, en mieux, de
--     l'option « Limiter à un fournisseur » retirée au §18.43 : celle-là exigeait
--     un émetteur que le dépôt ne connaissait pas encore, celle-ci se lit dans le
--     document.
--
-- `fournisseur_id` en découle : un jeu reconnu peut poser l'émetteur sur le
-- document. L'émetteur redevient déductible, ce qu'il n'était plus depuis le §17.
--
-- Ordre d'application (décision D5 de la phase) : parmi les jeux du type, par
-- priorité croissante, **le premier dont la reconnaissance correspond l'emporte,
-- et il est seul appliqué**. Aucun ne correspond : le jeu générique du type. On
-- sait ainsi toujours quel jeu a produit une valeur — ce qui n'était pas vrai
-- d'une liste unique où deux règles pouvaient se disputer un champ.
--
-- Migration des règles existantes : un jeu générique est créé pour **chaque**
-- type de document, et les règles en place y sont recopiées. Rien ne se perd, et
-- chaque type part avec de quoi lire une facture française. C'est délibérément
-- généreux : retirer d'un type une règle qui ne le concerne pas prend dix
-- secondes, retrouver une règle qu'une migration a effacée prend une soirée.

CREATE TABLE IF NOT EXISTS sys_profils_extraction (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_id INT NOT NULL,
    nom VARCHAR(150) NOT NULL,
    -- Cherchée dans le texte du document : c'est elle qui reconnaît « une facture
    -- Orange ». Vide sur le jeu générique, qui s'applique à défaut d'autre.
    reconnaissance VARCHAR(500) NULL,
    -- Émetteur posé sur le document quand ce jeu est reconnu (facultatif).
    fournisseur_id INT NULL,
    generique BOOLEAN NOT NULL DEFAULT FALSE,
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    priorite INT NOT NULL DEFAULT 100,
    CONSTRAINT fk_profils_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_profils_fournisseur FOREIGN KEY (fournisseur_id)
        REFERENCES usr_emetteurs(id) ON DELETE SET NULL,
    KEY idx_profils_categorie (categorie_id, priorite)
) ENGINE=InnoDB;

ALTER TABLE sys_regles_extraction
    ADD COLUMN profil_id INT NULL AFTER id,
    ADD CONSTRAINT fk_regles_profil FOREIGN KEY (profil_id)
        REFERENCES sys_profils_extraction(id) ON DELETE CASCADE,
    ADD KEY idx_regles_profil (profil_id, priorite);

-- Un jeu générique par type de document.
INSERT INTO sys_profils_extraction (categorie_id, nom, generique, priorite)
SELECT id, CONCAT(nom, ' (générique)'), TRUE, 1000
FROM sys_categories WHERE nature = 'type';

-- Les règles en place recopiées dans chacun d'eux.
INSERT INTO sys_regles_extraction
    (profil_id, nom, champ_cible, pattern, fonction, type_champ, actif, priorite)
SELECT p.id, r.nom, r.champ_cible, r.pattern, r.fonction, r.type_champ, r.actif, r.priorite
FROM sys_regles_extraction r
CROSS JOIN sys_profils_extraction p
WHERE r.profil_id IS NULL AND p.generique = TRUE;

-- Les originales, désormais sans jeu, n'ont plus de raison d'être : elles
-- s'appliqueraient à tout, ce que cette phase supprime.
DELETE FROM sys_regles_extraction WHERE profil_id IS NULL;
