-- Prénom et nom séparés, et vue des factures non attribuées (§17.19).
--
-- Le rattachement automatique se faisait sur un seul libellé. Deux personnes
-- d'une même famille portent le même nom : « Dupont » ne désigne personne en
-- particulier. On sépare donc le prénom du nom, tous deux exigés, et le
-- rattachement ne se déclenche que si **les deux** figurent dans le document.
--
-- `colonnes_identifiantes` déclare, table par table, ce qui suffit à désigner
-- une ligne dans un document. C'est explicite plutôt que deviné : pour les
-- membres, prénom et nom ; pour une autre table, ce sera autre chose, et la
-- valeur par défaut (la colonne d'affichage) reste valable si l'on ne dit rien.

ALTER TABLE usr_membres
    ADD COLUMN IF NOT EXISTS prenom VARCHAR(100) NOT NULL DEFAULT '' AFTER nom;

-- Retrait de la valeur par défaut : une ligne sans prénom ni nom ne doit plus
-- pouvoir être créée, la colonne devient franchement obligatoire.
ALTER TABLE usr_membres MODIFY COLUMN prenom VARCHAR(100) NOT NULL;
ALTER TABLE usr_membres MODIFY COLUMN nom VARCHAR(150) NOT NULL;

ALTER TABLE sys_tables_donnees
    ADD COLUMN IF NOT EXISTS colonnes_identifiantes VARCHAR(255) NULL;

UPDATE sys_tables_donnees
SET colonnes_identifiantes = 'prenom,nom'
WHERE nom_table = 'usr_membres';

-- Vue partagée : les factures dont le titulaire n'a pas été trouvé.
--
-- C'est la réponse au champ laissé facultatif. Plutôt que de rendre la GED
-- inutilisable en écartant du registre toute facture non attribuée, on donne un
-- endroit où les voir toutes et les compléter à la main.
INSERT INTO sys_vues_enregistrees (nom, categorie_id, criteres, partagee, ordre, utilisateur_id)
SELECT 'Toutes les factures sans utilisateur associé', c.id,
       CONCAT('[{"champ": "categorie", "operateur": "egal", "valeur": "', c.id,
              '"}, {"champ": "meta:titulaire", "operateur": "vide", "valeur": null}]'),
       TRUE, 10, NULL
FROM sys_categories c
WHERE c.nom = 'Factures'
  AND NOT EXISTS (
      SELECT 1 FROM sys_vues_enregistrees v
      WHERE v.nom = 'Toutes les factures sans utilisateur associé'
  );
