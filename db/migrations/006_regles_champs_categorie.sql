-- 006 — Règles de champs par catégorie (§15)
--
-- Chaque catégorie déclare les champs attendus sur ses documents, et pour
-- chacun s'il est obligatoire ou facultatif. Exemple : une facture exige un
-- émetteur, un montant et une date ; un contrat de travail exige un employeur
-- et une date de début.
--
-- `champ` réutilise **le vocabulaire du moteur de filtres** (app/filtres.py) :
-- soit un champ du document (`fournisseur`, `date_document`, `tags`...), soit
-- `meta:<cle>` pour n'importe quelle métadonnée extraite. Déclarer une règle
-- sur un nouveau champ personnalisé ne demandera donc ni migration ni code.

CREATE TABLE IF NOT EXISTS regles_champs_categorie (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,
    libelle VARCHAR(150) NULL,          -- intitulé affiché ; à défaut, déduit du champ
    obligatoire BOOLEAN DEFAULT TRUE,
    ordre INT DEFAULT 100,
    CONSTRAINT fk_regles_champs_categorie FOREIGN KEY (categorie_id) REFERENCES categories(id) ON DELETE CASCADE,
    UNIQUE KEY uq_categorie_champ (categorie_id, champ)
) ENGINE=InnoDB;
