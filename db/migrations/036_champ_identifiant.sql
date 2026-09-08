-- Le champ qui identifie un document dans sa catégorie (§18.40).
--
-- Le versionnage devait reconnaître « la même pièce, redéposée ». Il s'appuyait
-- sur une liste de clés écrite dans le code — numéro de facture, de contrat, de
-- client, montant — ce qui est doublement fautif : un foyer qui range autrement
-- n'y retrouve pas ses petits, et rien à l'écran ne dit sur quoi le
-- rapprochement se fonde.
--
-- C'est la catégorie qui sait ce qui identifie ses documents : une facture par
-- son numéro, un bulletin de paie par sa période, un relevé par son mois. La
-- déclaration rejoint donc les champs attendus, là où l'on décrit déjà ce qu'une
-- catégorie exige.
--
-- Plusieurs champs peuvent être cochés : ils comptent alors **ensemble** — deux
-- documents ne sont la même pièce que s'ils s'accordent sur tous.

ALTER TABLE sys_regles_champs_categorie
    ADD COLUMN identifiant BOOLEAN NOT NULL DEFAULT FALSE AFTER obligatoire;

-- Le numéro de facture identifie une facture : c'est le cas d'usage qui a motivé
-- la demande, et il vaut pour la quasi-totalité des foyers.
UPDATE sys_regles_champs_categorie
   SET identifiant = TRUE
 WHERE champ = 'meta:numero_facture';
