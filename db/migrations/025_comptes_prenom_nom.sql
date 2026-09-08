-- Prénom et nom sur les comptes, et retrait de `usr_membres.compte_email` (§17.20).
--
-- 1. `usr_membres.compte_email` n'a jamais servi : aucun code ne la lisait ni ne
--    l'écrivait. Une colonne inerte n'est pas neutre — elle apparaît comme un
--    champ à remplir dans l'administration, on la renseigne, il ne se passe
--    rien. On la retire plutôt que de la documenter comme « à venir ».
--
-- 2. Les comptes n'avaient qu'un champ `nom` libre, où chacun écrivait ce qu'il
--    voulait. Le prénom est ajouté à côté. Les deux deviennent **nullables** :
--    un compte administrateur n'a pas à décliner son identité civile pour
--    exister, et là où le nom manque, l'adresse e-mail sert d'affichage.
--
--    Les comptes déjà en place gardent ce que porte leur champ `nom` : le
--    découper automatiquement ferait des « Jean » de « Jean-Pierre Martin » et
--    des « Administrateur » sans prénom. Chacun corrigera le sien.

ALTER TABLE usr_membres DROP COLUMN IF EXISTS compte_email;

ALTER TABLE sys_utilisateurs
    ADD COLUMN IF NOT EXISTS prenom VARCHAR(100) NULL AFTER nom;

ALTER TABLE sys_utilisateurs MODIFY COLUMN nom VARCHAR(150) NULL;
