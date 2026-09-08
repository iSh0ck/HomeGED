-- Rattrapage : déclarer le numéro comme identifiant des factures (§18.40).
--
-- La migration 036 marque `meta:numero_facture` comme identifiant **s'il figure
-- déjà** parmi les champs attendus d'une catégorie. Or une installation en
-- service peut ne l'avoir jamais déclaré — c'est le cas de celle du projet, dont
-- la catégorie « Factures » attend un montant, une date et un titulaire, mais pas
-- de numéro. Le versionnage y serait alors resté sans effet, silencieusement :
-- la fonction en place, et rien qui se rapproche jamais.
--
-- On crée donc ce champ pour la catégorie « Factures » lorsqu'elle n'a aucun
-- champ identifiant. **Facultatif** : une facture dont l'OCR n'a pas su lire le
-- numéro reste une facture conforme, elle ne se rapproche simplement de rien. Et
-- retirable d'un clic depuis « Champs attendus », comme n'importe quel autre.

INSERT INTO sys_regles_champs_categorie
    (categorie_id, champ, libelle, obligatoire, identifiant, ordre)
SELECT c.id, 'meta:numero_facture', 'N° facture', FALSE, TRUE, 5
  FROM sys_categories c
 WHERE c.nom = 'Factures'
   AND NOT EXISTS (SELECT 1 FROM sys_regles_champs_categorie r
                    WHERE r.categorie_id = c.id AND r.identifiant = TRUE)
   AND NOT EXISTS (SELECT 1 FROM sys_regles_champs_categorie r
                    WHERE r.categorie_id = c.id AND r.champ = 'meta:numero_facture');
