-- Membres du foyer, et rattachement d'un document à l'un d'eux (§17.18).
--
-- Volontairement distincts des comptes : les personnes concernées par des
-- documents et celles qui se connectent ne sont pas le même ensemble. Un
-- enfant, un conjoint sans compte, un parent dont on garde les papiers peuvent
-- être titulaires d'une facture sans jamais ouvrir la GED. Leur créer un compte
-- fictif reviendrait à mentir dans la table des comptes.
--
-- `compte_email` note, à titre indicatif, le compte associé quand il en existe
-- un. Ce n'est pas une clé étrangère : supprimer un compte ne doit pas effacer
-- l'existence de la personne dans l'archive.
--
-- La table est inscrite dans `sys_tables_donnees` : elle devient donc modifiable
-- depuis l'administration comme n'importe quelle table de données du foyer, et
-- utilisable comme source de valeurs pour un champ attendu.

CREATE TABLE IF NOT EXISTS usr_membres (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    compte_email VARCHAR(255) NULL,
    remarque VARCHAR(255) NULL
) ENGINE=InnoDB;

INSERT INTO sys_tables_donnees (nom_table, libelle, description, colonne_libelle)
SELECT 'usr_membres', 'Membres du foyer',
       'Personnes auxquelles un document peut être rattaché. Indépendantes des comptes de connexion.',
       'nom'
WHERE NOT EXISTS (SELECT 1 FROM sys_tables_donnees WHERE nom_table = 'usr_membres');

-- Champ « Titulaire » sur les factures, adossé à cette table.
--
-- Déclaré **facultatif** : le rendre obligatoire ferait basculer d'un coup
-- toutes les factures déjà classées à l'état incomplet, donc hors du registre
-- (§17.7). C'est peut-être ce qu'on veut, mais c'est une décision qui appartient
-- à l'utilisateur — elle se prend en un clic dans « Champs requis ».
INSERT INTO sys_regles_champs_categorie (categorie_id, champ, source_table, libelle, obligatoire, ordre)
SELECT c.id, 'meta:titulaire', 'usr_membres', 'Titulaire', FALSE, 50
FROM sys_categories c
WHERE c.nom = 'Factures'
  AND NOT EXISTS (
      SELECT 1 FROM sys_regles_champs_categorie r
      WHERE r.categorie_id = c.id AND r.champ = 'meta:titulaire'
  );
