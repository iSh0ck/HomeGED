-- ============================================================
-- Schéma HomeGED - MariaDB / MySQL
-- ============================================================

CREATE DATABASE IF NOT EXISTS homeged CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE homeged;

-- ------------------------------------------------------------
-- Classement des sys_documents
-- ------------------------------------------------------------

-- Arborescence de classement (ex: Factures > EDF, Courriers > Impots ...)
-- Le classement est automatique : chaque catégorie porte sa propre regex
-- d'identification, appliquée par le worker sur le texte OCR.
CREATE TABLE IF NOT EXISTS sys_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    -- 'dossier' (organise, ne porte aucun document) ou 'type' (feuille qui porte
    -- les documents, leurs colonnes et leurs champs attendus) — cf. migration 042
    nature VARCHAR(10) NOT NULL DEFAULT 'type',
    -- dossier de dépôt sous ocr_wait/, un par type de document (cf. migration 043).
    -- Rempli par l'application ; les dossiers de classement n'en ont pas.
    dossier_depot VARCHAR(64) NULL,
    -- table du foyer à laquelle s'adosse une fiche de liaison (cf. migration 049) :
    -- chacune de ses lignes devient une fiche, et les documents qui la désignent
    -- s'y retrouvent quel que soit leur type
    -- Ancienne table adossée à une « fiche de liaison » (§19.17), abandonnée au
    -- §22.1 : une fiche simple ne s'adosse à rien. La colonne survit le temps
    -- qu'on soit sûr de n'en plus rien vouloir.
    parent_id INT NULL,
    ordre INT NOT NULL DEFAULT 100,          -- ordre d'affichage dans la navigation
    -- tri par défaut du registre pour cette catégorie (cf. db/migrations/040) ;
    -- vide : hérité du parent, puis du réglage général `tri_defaut_champ`
    tri_champ VARCHAR(100) NULL,
    tri_sens ENUM('asc','desc') NULL,
    -- Les colonnes retirées du tableau se voient-elles quand même sur la fiche
    -- d'un document de ce type ? (cf. db/migrations/051)
    fiche_champs_masques BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE KEY uq_categorie_depot (dossier_depot),
    CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES sys_categories(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Les émetteurs (EDF, impots.gouv, banque…). Une **table du foyer** comme les
-- autres depuis le §21.12 : un type qui veut un émetteur déclare un champ attendu
-- qui y puise, et gagne la déduction, le rattachement et le repli avec.
CREATE TABLE IF NOT EXISTS usr_emetteurs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL UNIQUE,
    regex_identification VARCHAR(255) NULL
) ENGINE=InnoDB;

-- Jeux de règles d'extraction, un ou plusieurs par type de document
-- (cf. db/migrations/046). Le premier jeu dont la `reconnaissance` correspond au
-- texte l'emporte et est seul appliqué ; à défaut, le jeu générique du type.
CREATE TABLE IF NOT EXISTS sys_profils_extraction (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_id INT NOT NULL,
    nom VARCHAR(150) NOT NULL,
    reconnaissance VARCHAR(500) NULL,    -- cherchée dans le texte ; vide sur le générique
    generique BOOLEAN NOT NULL DEFAULT FALSE,
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    priorite INT NOT NULL DEFAULT 100,
    CONSTRAINT fk_profils_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    KEY idx_profils_categorie (categorie_id, priorite)
) ENGINE=InnoDB;

-- Règles d'extraction automatique : une regex -> une colonne cible dans sys_metadonnees
CREATE TABLE IF NOT EXISTS sys_regles_extraction (
    id INT AUTO_INCREMENT PRIMARY KEY,
    profil_id INT NULL,                  -- jeu auquel la règle appartient (migration 046)
    nom VARCHAR(150) NOT NULL,
    champ_cible VARCHAR(100) NOT NULL,   -- ex: 'numero_facture', 'montant_ttc', 'date_document'
    pattern VARCHAR(500) NULL,           -- regex Python, avec un groupe capturant () ;
                                         -- facultatif si la règle porte une fonction
    fonction VARCHAR(40) NULL,             -- traitement prêt à l'emploi (cf. db/migrations/034)
    -- Valeur dont une fonction a besoin pour travailler : jours d'une échéance,
    -- séparateur d'une concaténation (cf. db/migrations/054).
    parametre VARCHAR(100) NULL,
    type_champ ENUM('texte','date','montant','entier') DEFAULT 'texte',
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    priorite INT DEFAULT 100,            -- ordre d'application, plus petit = appliqué en premier
    CONSTRAINT fk_regles_profil FOREIGN KEY (profil_id)
        REFERENCES sys_profils_extraction(id) ON DELETE CASCADE,
    KEY idx_regles_profil (profil_id, priorite)
) ENGINE=InnoDB;

-- Table principale des sys_documents
CREATE TABLE IF NOT EXISTS sys_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_fichier VARCHAR(255) NOT NULL,
    -- Facultatifs depuis le §22.7 : une entrée peut n'avoir aucun fichier — un
    -- contrat verbal, le code d'un cadenas — et le fichier n'est qu'une pièce
    -- parmi d'autres (cf. db/migrations/072).
    chemin_stockage VARCHAR(500) NULL,
    hash_sha256 CHAR(64) NULL UNIQUE,           -- évite les doublons ; NULL pour une entrée sans fichier
    date_import DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_document DATE NULL,                    -- date extraite du document (par regex)
    texte_ocr LONGTEXT NULL,
    statut ENUM('en_attente','ocr_en_cours','traite','erreur','incomplet') DEFAULT 'en_attente',
    categorie_id INT NULL,
    CONSTRAINT fk_documents_categorie FOREIGN KEY (categorie_id) REFERENCES sys_categories(id) ON DELETE SET NULL,
    KEY idx_documents_date_import (date_import),
    -- tri d'ouverture d'une catégorie (cf. db/migrations/041)
    KEY idx_documents_date_document (date_document),
    -- Compression des archives (cf. db/migrations/021)
    -- d'où vient le document : la main (§22.68) ou le dossier surveillé ;
    -- NULL pour ceux dont la tâche a été purgée avant qu'on le note
    depot_manuel BOOLEAN NULL,
    taille_octets BIGINT NULL,          -- taille du fichier archivé
    date_compression DATETIME NULL,     -- NULL = jamais repris par l'optimiseur
    FULLTEXT KEY ft_texte_ocr (texte_ocr),
    -- Corbeille (cf. db/migrations/052) : un document supprimé est daté, pas
    -- effacé. Il garde sa place, ses métadonnées et son fichier jusqu'à la purge.
    date_suppression DATETIME NULL,
    supprime_par_id INT NULL,
    corbeille_masquee BOOLEAN NOT NULL DEFAULT FALSE,
    KEY idx_documents_suppression (date_suppression),
    -- Contrôle d'intégrité (cf. db/migrations/053) : l'empreinte de l'archive
    -- telle qu'elle est stockée, et non celle du fichier reçu — les deux
    -- diffèrent dès qu'un document est océrisé ou compressé.
    empreinte_archive VARCHAR(64) NULL,
    date_controle DATETIME NULL,
    integrite VARCHAR(20) NULL,
    KEY idx_documents_controle (date_controle),
    -- Conformité rangée (cf. db/migrations/078) : « ce document a-t-il ses
    -- champs obligatoires ? » était recalculé à chaque requête et pour chaque
    -- document — 311 ms pour compter vingt mille documents, contre 6 ms ici.
    -- Écrit au moment où la réponse change, jamais deviné à la lecture.
    conforme BOOLEAN NOT NULL DEFAULT TRUE,
    KEY idx_documents_conforme (conforme)
) ENGINE=InnoDB;

-- Métadonnées extraites automatiquement (clé/valeur) - une ligne par champ trouvé par regex
CREATE TABLE IF NOT EXISTS sys_metadonnees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    regle_id INT NULL,          -- quelle règle a produit cette valeur (traçabilité)
    cle VARCHAR(100) NOT NULL,  -- = champ_cible de la règle
    valeur VARCHAR(500) NULL,
    CONSTRAINT fk_metadonnees_document FOREIGN KEY (document_id) REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_metadonnees_regle FOREIGN KEY (regle_id) REFERENCES sys_regles_extraction(id) ON DELETE SET NULL,
    UNIQUE KEY uq_doc_cle (document_id, cle),
    -- lecture par clé, sans connaître le document (cf. db/migrations/041)
    KEY idx_metadonnees_cle (cle, valeur)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Authentification & droits (extensible : rôles réutilisables,
-- droits accordés catégorie par catégorie)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sys_utilisateurs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    -- Nom et prénom exigés des comptes ordinaires, facultatifs pour un
    -- administrateur (cf. db/migrations/025). Là où ils manquent, l'adresse
    -- e-mail sert d'affichage.
    nom VARCHAR(150) NULL,
    prenom VARCHAR(100) NULL,
    mot_de_passe_hash VARCHAR(255) NOT NULL,
    est_admin BOOLEAN NOT NULL DEFAULT FALSE,  -- un admin voit/modifie tout, indépendamment des rôles
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- Double authentification (cf. db/migrations/020)
    otp_secret VARCHAR(64) NULL,                 -- graine partagée avec l'application d'authentification
    otp_actif BOOLEAN NOT NULL DEFAULT FALSE,
    otp_impose BOOLEAN NOT NULL DEFAULT FALSE,   -- exigée par un administrateur
    otp_codes_secours TEXT NULL,                 -- codes de secours à usage unique, hachés
    jeton_version INT NOT NULL DEFAULT 0,        -- incrémentée pour périmer les sessions ouvertes
    date_mot_de_passe DATETIME NULL,
    -- Mode d'ouverture d'un document (cf. db/migrations/050, 051) : personnel,
    -- il dépend de la machine de celui qui regarde, pas d'une décision de foyer.
    mode_apercu VARCHAR(20) NOT NULL DEFAULT 'miniature',
    -- Lignes par page du registre, pour ce compte (cf. db/migrations/080).
    -- NULL = suivre le réglage du foyer.
    lignes_par_page INT NULL,
    -- Palette et langue de ce compte (cf. db/migrations/081). NULL = celles du
    -- foyer : un thème dépend de l'écran, une langue dépend de qui lit.
    theme VARCHAR(32) NULL,
    langue VARCHAR(32) NULL,
    -- Rappels par courriel (cf. db/migrations/059) : chacun peut ne pas vouloir
    -- être dérangé sans perdre les rappels dans l'application. Les paliers
    -- espacent les relances de qui ne réagit pas.
    courriel_rappels BOOLEAN NOT NULL DEFAULT TRUE,
    palier_courriel INT NOT NULL DEFAULT 0,
    date_dernier_courriel DATETIME NULL
) ENGINE=InnoDB;

-- Qui a mis un document à la corbeille (cf. db/migrations/052). Posée ici et non
-- dans la table : `sys_documents` est déclarée avant `sys_utilisateurs`, et une
-- clé étrangère ne peut pas pointer une table qui n'existe pas encore.
ALTER TABLE sys_documents
    ADD CONSTRAINT fk_documents_supprime_par
        FOREIGN KEY (supprime_par_id) REFERENCES sys_utilisateurs(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS sys_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(100) NOT NULL UNIQUE,      -- ex: "Foyer", "Invité", "Comptabilité"
    description VARCHAR(255) NULL
) ENGINE=InnoDB;

-- Un utilisateur peut avoir plusieurs rôles (many-to-many)
CREATE TABLE IF NOT EXISTS sys_utilisateur_roles (
    utilisateur_id INT NOT NULL,
    role_id INT NOT NULL,
    PRIMARY KEY (utilisateur_id, role_id),
    CONSTRAINT fk_ur_utilisateur FOREIGN KEY (utilisateur_id) REFERENCES sys_utilisateurs(id) ON DELETE CASCADE,
    CONSTRAINT fk_ur_role FOREIGN KEY (role_id) REFERENCES sys_roles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Droits d'un rôle sur une catégorie donnée. Une catégorie sans entrée pour
-- un rôle donné = invisible pour ce rôle (sauf pour les admins, et sauf les
-- sys_documents non catégorisés qui restent visibles par tous les sys_utilisateurs
-- connectés).
CREATE TABLE IF NOT EXISTS sys_droits_categorie (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    categorie_id INT NOT NULL,
    -- Six actions (cf. db/migrations/048). `telecharger` se distingue de `voir` :
    -- laisser lire une fiche n'oblige pas à donner le PDF. `gerer_versions` de
    -- `modifier` : supprimer une version détruit un fichier.
    peut_voir BOOLEAN NOT NULL DEFAULT TRUE,
    peut_modifier BOOLEAN NOT NULL DEFAULT FALSE,
    peut_deposer BOOLEAN NOT NULL DEFAULT FALSE,
    peut_telecharger BOOLEAN NOT NULL DEFAULT TRUE,
    peut_supprimer BOOLEAN NOT NULL DEFAULT FALSE,
    peut_gerer_versions BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_droits_role FOREIGN KEY (role_id) REFERENCES sys_roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_droits_categorie FOREIGN KEY (categorie_id) REFERENCES sys_categories(id) ON DELETE CASCADE,
    UNIQUE KEY uq_role_categorie (role_id, categorie_id)
) ENGINE=InnoDB;

-- Droits généraux d'un rôle, hors catégorie (cf. db/migrations/048). La clé est
-- le nom du droit tel que le code le déclare : une table de correspondance en
-- base se désynchroniserait au premier renommage d'un point d'entrée.
CREATE TABLE IF NOT EXISTS sys_droits_generaux (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    droit VARCHAR(40) NOT NULL,
    CONSTRAINT fk_droits_generaux_role FOREIGN KEY (role_id)
        REFERENCES sys_roles(id) ON DELETE CASCADE,
    UNIQUE KEY uq_role_droit (role_id, droit)
) ENGINE=InnoDB;

-- Les pièces d'un document (cf. db/migrations/065).
--
-- Un document **était** un fichier : pour réunir une facture, sa garantie et le
-- bon de livraison, il fallait trois documents et un lien entre eux. Une fiche
-- porte désormais N fichiers, comme le « docpak » d'EzGED.
--
-- La pièce **principale** est celle qu'on voit partout ailleurs : c'est son
-- fichier que le registre ouvre et que la miniature montre. Les colonnes du
-- document (`chemin_stockage`, `hash_sha256`, `nom_fichier`, `taille_octets`)
-- en sont le reflet, tenu à jour par `app/pieces.py` — tout ce qui les lit
-- continue de fonctionner sans rien savoir des pièces.
CREATE TABLE IF NOT EXISTS sys_pieces_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    nom_fichier VARCHAR(255) NOT NULL,
    -- Facultatifs depuis le §22.7 : une entrée peut n'avoir aucun fichier — un
    -- contrat verbal, le code d'un cadenas — et le fichier n'est qu'une pièce
    -- parmi d'autres (cf. db/migrations/072).
    chemin_stockage VARCHAR(500) NULL,
    -- Empreinte du fichier **reçu**, comme sur le document : c'est elle qui
    -- reconnaît un dépôt déjà connu, quelle que soit la pièce où il a atterri.
    hash_sha256 VARCHAR(64) NOT NULL,
    taille_octets BIGINT NULL,
    -- Le texte de cette pièce-là. Celui du document est leur concaténation, et
    -- c'est lui que l'index plein texte lit : une recherche trouve donc un
    -- document par le contenu de n'importe laquelle de ses pièces.
    texte_ocr LONGTEXT NULL,
    ordre INT NOT NULL DEFAULT 1,
    principale BOOLEAN NOT NULL DEFAULT FALSE,
    date_ajout DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    -- Contrôle d'intégrité, pièce par pièce (cf. db/migrations/066) : une
    -- garantie jointe s'abîme comme une facture, et personne ne l'ouvre pendant
    -- des années. L'empreinte est celle de l'**archive**, pas du fichier reçu.
    empreinte_archive VARCHAR(64) NULL,
    date_controle DATETIME NULL,
    integrite VARCHAR(20) NULL,
    CONSTRAINT fk_piece_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_piece_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_piece_empreinte (hash_sha256),
    KEY idx_piece_document (document_id, ordre),
    KEY idx_piece_controle (date_controle)
) ENGINE=InnoDB;

-- Serveur de travaux : un travail par fichier déposé, avec son état et son
-- diagnostic (cf. db/migrations/007). `rejouer_demande` est le canal de commande
-- de l'interface vers le worker, l'API n'ayant pas accès au dossier surveillé.
CREATE TABLE IF NOT EXISTS sys_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_fichier VARCHAR(255) NOT NULL,
    chemin_source VARCHAR(500) NULL,
    hash_sha256 CHAR(64) NULL,
    -- 'a_classer' : déposé à un endroit qu'aucun type de document ne réclame
    -- (cf. db/migrations/044). Le traitement s'arrête avant l'océrisation.
    -- `echec` : erreur définitive (cf. db/migrations/067). Un travail qui a
    -- épuisé le palier de tentatives en sort — la reprise ne le regarde plus, et
    -- l'écran le distingue de ce que la machine essaie encore.
    statut ENUM('en_attente','en_cours','termine','erreur','bloque','ignore','a_classer',
                'echec')
        DEFAULT 'en_attente',
    etape VARCHAR(30) NULL,             -- dernière étape atteinte (cf. app/worker.py)
    document_id INT NULL,
    tentatives INT DEFAULT 0,
    -- Passes de la reprise automatique sur un travail bloqué (cf. migrations/067).
    -- Au-delà du palier, la reprise cesse : le travail reste bloqué — il appelle
    -- une action humaine — mais la machine ne fait plus semblant de chercher.
    reprises_auto INT NOT NULL DEFAULT 0,
    message_erreur TEXT NULL,
    diagnostic TEXT NULL,
    rejouer_demande BOOLEAN NOT NULL DEFAULT FALSE,
    etape_demandee VARCHAR(30) NULL,
    -- type de document demandé pour un fichier « à classer » (cf. migration 045) :
    -- l'API pose la consigne, le serveur de travaux déplace le fichier et reprend
    categorie_demandee INT NULL,
    -- Type reconnu au dépôt (cf. db/migrations/063). Un **souvenir**, pas une
    -- consigne : l'emplacement reste maître quand il parle, et ce champ ne sert
    -- qu'au rejeu, où le fichier n'est plus dans le dossier où on l'avait mis.
    categorie_id INT NULL,
    -- Demande d'écartement d'un dépôt (cf. db/migrations/062) : l'API pose la
    -- consigne, le serveur de travaux efface le fichier reçu.
    rejet_demande BOOLEAN NOT NULL DEFAULT FALSE,
    -- Le fichier déposé rejoint un document existant comme **pièce** au lieu de
    -- créer un document (cf. db/migrations/065). Le dossier de dépôt ne dit que
    -- le type, et le fichier ne dit rien : c'est le travail qui porte la
    -- consigne.
    piece_pour_document_id INT NULL,
    -- Le dépôt est une **nouvelle version de cette pièce**, et non une pièce de
    -- plus (cf. db/migrations/066). La seule chose qu'on ne puisse pas deviner.
    version_pour_piece_id INT NULL,
    CONSTRAINT fk_job_piece_document FOREIGN KEY (piece_pour_document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_job_version_piece FOREIGN KEY (version_pour_piece_id)
        REFERENCES sys_pieces_document(id) ON DELETE CASCADE,
    CONSTRAINT fk_jobs_categorie_demandee FOREIGN KEY (categorie_demandee)
        REFERENCES sys_categories(id) ON DELETE SET NULL,    -- étape à partir de laquelle reprendre
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_debut DATETIME NULL,
    date_fin DATETIME NULL,
    KEY idx_jobs_statut (statut, date_creation),
    KEY idx_jobs_rejouer (rejouer_demande),
    CONSTRAINT fk_jobs_document FOREIGN KEY (document_id) REFERENCES sys_documents(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Champs attendus par catégorie, obligatoires ou facultatifs (cf. db/migrations/006).
-- `champ` reprend le vocabulaire du moteur de filtres : champ du document
-- (`date_document`, `statut`…) ou `meta:<cle>` pour une métadonnée extraite.
CREATE TABLE IF NOT EXISTS sys_regles_champs_categorie (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,
    source_table VARCHAR(64) NULL,  -- première source, celle qui interprète une valeur sans préfixe
    -- sources de valeurs du champ, séparées par des virgules (cf. migration 028)
    sources VARCHAR(500) NULL,
    -- déduction automatique depuis le texte du document (cf. db/migrations/039) :
    -- 'aucune' (défaut), 'toutes' (toutes les colonnes cherchées doivent figurer
    -- dans le document) ou 'une' (une seule suffit). Rien n'est déduit tant qu'un
    -- administrateur ne l'a pas déclaré.
    deduction VARCHAR(20) NOT NULL DEFAULT 'aucune',
    -- colonnes de la table source cherchées dans le document, séparées par des
    -- virgules. Vide : les colonnes identifiantes de la table.
    colonnes_deduction VARCHAR(255) NULL,
    -- colonnes de la table source qui composent la valeur affichée (§22.59) ;
    -- vide : les colonnes identifiantes déclarées par la table
    colonnes_affichees VARCHAR(255) NULL,
    -- Tolérer une petite différence entre le document et la table (cf. 054).
    deduction_approchee BOOLEAN NOT NULL DEFAULT FALSE,
    -- Ce champ porte-t-il une date qui arrive à terme ? (cf. 058)
    echeance BOOLEAN NOT NULL DEFAULT FALSE,
    rappel_jours INT NULL,
    libelle VARCHAR(150) NULL,
    obligatoire BOOLEAN NOT NULL DEFAULT TRUE,
    -- champ qui identifie un document dans sa catégorie (cf. db/migrations/036) :
    -- c'est lui qui reconnaît la même pièce redéposée
    identifiant BOOLEAN NOT NULL DEFAULT FALSE,
    -- Le champ contient des **documents de la GED**, choisis dans une liste
    -- (cf. db/migrations/074) : « Factures liées », « Devis reçus ».
    attache_documents BOOLEAN NOT NULL DEFAULT FALSE,
    -- Ce qu'un champ « documents » accepte (cf. db/migrations/076) : le type de
    -- document qu'on peut y attacher, et les champs sur lesquels la recherche
    -- porte. Vides : tout type, recherche sur le nom et le texte reconnu.
    documents_categorie_id INT NULL,
    documents_champs VARCHAR(255) NULL,
    -- Ce champ attend-il d'être rempli par une règle d'extraction ?
    -- (cf. db/migrations/077) Sans cela, « aucune règle ne le vise » ne
    -- distinguait pas un commentaire qu'on saisit d'un numéro de facture dont la
    -- règle manque.
    extraction_attendue BOOLEAN NOT NULL DEFAULT FALSE,
    -- Comment ce champ se saisit et se relit (cf. db/migrations/075) : texte,
    -- texte_long, date, nombre, montant, booleen. C'est le type qui décide du
    -- contrôle affiché ; un champ dont on ignore la nature se saisit toujours de
    -- la mauvaise manière.
    type_champ VARCHAR(20) NOT NULL DEFAULT 'texte',
    ordre INT DEFAULT 100,
    CONSTRAINT fk_regles_champs_categorie FOREIGN KEY (categorie_id) REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_regle_documents_categorie FOREIGN KEY (documents_categorie_id)
        REFERENCES sys_categories(id) ON DELETE SET NULL,
    UNIQUE KEY uq_categorie_champ (categorie_id, champ)
) ENGINE=InnoDB;

-- Sessions ouvertes (cf. db/migrations/022). Un JWT porte sa propre validité ;
-- cette table permet en plus de savoir qui est connecté et de fermer une
-- session à distance.
CREATE TABLE IF NOT EXISTS sys_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utilisateur_id INT NOT NULL,
    jti VARCHAR(64) NOT NULL UNIQUE,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_activite DATETIME NULL,
    date_expiration DATETIME NOT NULL,
    date_revocation DATETIME NULL,
    adresse VARCHAR(64) NULL,
    agent VARCHAR(255) NULL,
    CONSTRAINT fk_sessions_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE CASCADE,
    KEY idx_sessions_utilisateur (utilisateur_id, date_revocation)
) ENGINE=InnoDB;

-- Verrou d'édition d'un document (cf. db/migrations/026). Périssable : un
-- onglet fermé sans un mot ne doit pas bloquer un document pour tout le foyer.
CREATE TABLE IF NOT EXISTS sys_verrous_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL UNIQUE,
    utilisateur_id INT NULL,
    date_expiration DATETIME NOT NULL,
    CONSTRAINT fk_verrou_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_verrou_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Exports de l'archive (cf. db/migrations/029). Téléchargeables une seule fois,
-- et effacés d'eux-mêmes s'ils ne le sont pas.
CREATE TABLE IF NOT EXISTS sys_exports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    jeton VARCHAR(64) NOT NULL UNIQUE,
    utilisateur_id INT NULL,
    chemin VARCHAR(500) NOT NULL,
    taille_octets BIGINT NULL,
    documents INT NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_expiration DATETIME NOT NULL,
    date_telechargement DATETIME NULL,
    CONSTRAINT fk_export_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Versions d'un document (cf. db/migrations/035). Chaque dépôt d'un document
-- déjà connu ajoute une version au lieu de créer une fiche de plus ; la fiche
-- pointe la version courante et garde les précédentes avec leur date.
CREATE TABLE IF NOT EXISTS sys_versions_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    hash_sha256 VARCHAR(64) NULL,
    -- Facultatifs depuis le §22.7 : une entrée peut n'avoir aucun fichier — un
    -- contrat verbal, le code d'un cadenas — et le fichier n'est qu'une pièce
    -- parmi d'autres (cf. db/migrations/072).
    chemin_stockage VARCHAR(500) NULL,
    nom_fichier VARCHAR(255) NOT NULL,
    taille_octets BIGINT NULL,
    date_depot DATETIME DEFAULT CURRENT_TIMESTAMP,
    courante BOOLEAN NOT NULL DEFAULT FALSE,
    utilisateur_id INT NULL,
    -- La pièce dont c'est un dépôt (cf. db/migrations/066) : c'est le **fichier**
    -- qu'on rescanne, donc la pièce, et non le document — sans quoi rescanner la
    -- garantie remplacerait la facture.
    piece_id INT NULL,
    CONSTRAINT fk_version_piece FOREIGN KEY (piece_id)
        REFERENCES sys_pieces_document(id) ON DELETE CASCADE,
    CONSTRAINT fk_version_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_version_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    CONSTRAINT uq_version_empreinte UNIQUE (hash_sha256),
    INDEX idx_versions_document (document_id, date_depot)
) ENGINE=InnoDB;

-- Rattachements posés à la main entre deux documents (cf. db/migrations/068).
--
-- Le rapprochement par valeur partagée (§19.19) réunit ce qui désigne la même
-- chose. Reste ce qui ne partage rien et se répond quand même : un contrat et
-- son avenant. Seul quelqu'un qui les a lus le sait — d'où ce lien posé à la
-- main, et symétrique.
CREATE TABLE IF NOT EXISTS sys_rattachements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    -- Toujours (petit, grand) : le couple est rangé à l'écriture, ce qui rend
    -- l'unicité vraie dans les deux sens sans avoir à y penser à la lecture.
    document_a INT NOT NULL,
    document_b INT NOT NULL,
    -- Ce que le lien veut dire, quand celui qui le pose sait le nommer :
    -- « avenant », « remboursement ». Facultatif — un lien sans mot vaut mieux
    -- qu'un lien qu'on renonce à poser.
    libelle VARCHAR(120) NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    CONSTRAINT fk_rattachement_a FOREIGN KEY (document_a)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_rattachement_b FOREIGN KEY (document_b)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_rattachement_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_rattachement (document_a, document_b),
    KEY idx_rattachement_b (document_b)
) ENGINE=InnoDB;

-- Ce que l'administration autorise à rattacher (§22.4).
--
-- Tant que **rien** n'est déclaré, tout est permis : un réglage vide ne doit pas
-- interdire une fonction, sans quoi personne ne comprendrait pourquoi le bouton
-- refuse. Dès qu'une paire est déclarée, elles seules sont permises — c'est le
-- moment où l'on décide que ce foyer relie des contrats à des avenants, et rien
-- d'autre.
CREATE TABLE IF NOT EXISTS sys_rattachements_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_a INT NOT NULL,
    categorie_b INT NOT NULL,
    libelle VARCHAR(120) NULL,
    CONSTRAINT fk_rattachement_type_a FOREIGN KEY (categorie_a)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_rattachement_type_b FOREIGN KEY (categorie_b)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    UNIQUE KEY uq_rattachement_type (categorie_a, categorie_b)
) ENGINE=InnoDB;


-- Exports par modèle d'arborescence et de nommage (cf. db/migrations/070).
--
-- L'export de secours (§17.30) sort tout le foyer, une fois, sous mot de passe.
-- Celui-ci sort **une sélection** rangée comme on la veut, pour la donner au
-- comptable ou à l'assurance. Construit par le serveur de travaux : cinq cents
-- PDF ne se compressent pas dans une requête HTTP.
CREATE TABLE IF NOT EXISTS sys_exports_modele (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utilisateur_id INT NULL,
    statut ENUM('en_attente','en_cours','pret','erreur') NOT NULL DEFAULT 'en_attente',
    -- Ce qu'on exporte : les mêmes critères que le registre, au même format.
    criteres TEXT NULL,
    categorie_id INT NULL,
    -- Comment on le range : deux modèles à trous, `{annee}/{type}` et
    -- `{champ:emetteur} - {date}`. Les trous sont les champs du document, ce qui
    -- évite d'inventer un vocabulaire de plus.
    modele_dossier VARCHAR(255) NULL,
    modele_nom VARCHAR(255) NULL,
    chemin VARCHAR(500) NULL,
    nb_documents INT NULL,
    message TEXT NULL,
    date_demande DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_fin DATETIME NULL,
    CONSTRAINT fk_export_modele_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    CONSTRAINT fk_export_modele_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE SET NULL,
    KEY idx_export_modele_statut (statut, date_demande)
) ENGINE=InnoDB;


-- Scripts du mode développeur (cf. db/migrations/071).
--
-- La porte de sortie universelle, autorisée sous condition d'un mode déclaré :
-- un seul point d'entrée, un contexte explicite, un processus séparé borné en
-- durée, aucun accès à la base, et tout est journalisé.
CREATE TABLE IF NOT EXISTS sys_scripts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    description TEXT NULL,
    code MEDIUMTEXT NOT NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_modification DATETIME NULL,
    utilisateur_id INT NULL,
    CONSTRAINT fk_script_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_script_nom (nom)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sys_executions_script (
    id INT AUTO_INCREMENT PRIMARY KEY,
    script_id INT NULL,
    utilisateur_id INT NULL,
    date_execution DATETIME DEFAULT CURRENT_TIMESTAMP,
    duree_ms INT NULL,
    reussite BOOLEAN NOT NULL DEFAULT FALSE,
    sortie MEDIUMTEXT NULL,
    erreur TEXT NULL,
    CONSTRAINT fk_execution_script FOREIGN KEY (script_id)
        REFERENCES sys_scripts(id) ON DELETE SET NULL,
    CONSTRAINT fk_execution_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    KEY idx_execution_date (date_execution)
) ENGINE=InnoDB;


-- Rapprochements déclarés sur un type de document (cf. db/migrations/073).
--
-- Un dossier porte un numéro, repris sur le devis, le bon de commande, le bon de
-- livraison : ouvrir l'un montre les autres. Déclaré, jamais deviné — c'est ce
-- qui distingue ce rapprochement de celui retiré au §22.7.
CREATE TABLE IF NOT EXISTS sys_liens_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    -- Le type qui déclare. La déclaration vaut **dans les deux sens** : ouvrir un
    -- devis montre son dossier comme ouvrir le dossier montre ses devis. Sans
    -- cela il faudrait déclarer six liens pour trois types, et l'on en oublierait
    -- toujours un.
    categorie_id INT NOT NULL,
    -- Le type d'en face. NULL : tous les types — c'est le cas du numéro de
    -- dossier, repris par des pièces de sortes très différentes.
    categorie_cible_id INT NULL,
    -- Les deux champs qui doivent porter la même valeur, dans le vocabulaire des
    -- filtres : `meta:numero_dossier`, `date_document`…
    champ_source VARCHAR(100) NOT NULL,
    champ_cible VARCHAR(100) NOT NULL,
    libelle VARCHAR(120) NULL,
    CONSTRAINT fk_lien_type_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_lien_type_cible FOREIGN KEY (categorie_cible_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    UNIQUE KEY uq_lien_type (categorie_id, categorie_cible_id, champ_source, champ_cible),
    KEY idx_lien_type_cible (categorie_cible_id)
) ENGINE=InnoDB;


-- Documents attachés par un champ (cf. db/migrations/074).
--
-- Sous « Entretiens », noter ce qui a été fait sur le véhicule et y attacher une
-- facture déjà présente dans la GED. Ce n'est ni une pièce, ni un rattachement à
-- la main, ni un rapprochement déclaré : c'est un **champ** — il a un intitulé,
-- il est propre à un type, et son contenu est une liste de documents choisis.
CREATE TABLE IF NOT EXISTS sys_documents_attaches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    -- Le champ auquel cette attache appartient, dans le vocabulaire des filtres
    -- (`meta:factures_liees`) : un même document peut en porter plusieurs.
    champ VARCHAR(100) NOT NULL,
    document_attache_id INT NOT NULL,
    ordre INT NOT NULL DEFAULT 1,
    date_ajout DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    CONSTRAINT fk_attache_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_attache_cible FOREIGN KEY (document_attache_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_attache_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE SET NULL,
    UNIQUE KEY uq_attache (document_id, champ, document_attache_id),
    KEY idx_attache_cible (document_attache_id)
) ENGINE=InnoDB;


-- Réglages par colonne des tables du foyer (cf. db/migrations/033) : intitulé
-- lisible et liaison vers une autre table. L'unicité n'y figure pas — elle vit
-- dans le schéma de la table, seule source de vérité.
CREATE TABLE IF NOT EXISTS sys_colonnes_donnees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_table VARCHAR(64) NOT NULL,
    colonne VARCHAR(64) NOT NULL,
    libelle VARCHAR(150) NULL,
    source_table VARCHAR(64) NULL,
    CONSTRAINT uq_colonne_donnees UNIQUE (nom_table, colonne)
) ENGINE=InnoDB;

-- Réglages généraux modifiables depuis l'administration (cf. db/migrations/032).
CREATE TABLE IF NOT EXISTS sys_reglages (
    cle VARCHAR(64) NOT NULL PRIMARY KEY,
    valeur TEXT NULL,
    date_modification DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Colonnes du tableau propres à chaque catégorie (cf. db/migrations/030).
-- Ne contient que les corrections apportées aux colonnes déduites : une catégorie
-- sans ligne ici affiche un tableau parfaitement utilisable (cf. app/colonnes.py).
CREATE TABLE IF NOT EXISTS sys_colonnes_categorie (
    id INT AUTO_INCREMENT PRIMARY KEY,
    categorie_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,
    libelle VARCHAR(150) NULL,
    ordre INT NOT NULL DEFAULT 100,
    largeur INT NULL,
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_colonne_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT uq_colonne_categorie UNIQUE (categorie_id, champ)
) ENGINE=InnoDB;

-- Registre des tables de données créées depuis l'administration (cf. db/migrations/010).
-- Seules les tables inscrites ici sont modifiables depuis l'interface ; les tables
-- du fonctionnement de l'application restent en consultation seule.
CREATE TABLE IF NOT EXISTS sys_tables_donnees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom_table VARCHAR(64) NOT NULL UNIQUE,   -- nom physique, préfixé `usr_`
    libelle VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,
    colonne_libelle VARCHAR(64) NULL,
    -- colonnes qui suffisent à désigner une ligne dans un document (cf. migration 024)
    colonnes_identifiantes VARCHAR(255) NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Notifications (cf. db/migrations/058) : rappels d'échéance et messages des
-- automatisations. `utilisateur_id` vide = pour tout le foyer.
CREATE TABLE IF NOT EXISTS sys_notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    utilisateur_id INT NULL,            -- NULL : pour tout le foyer
    document_id INT NULL,
    titre VARCHAR(200) NOT NULL,
    message TEXT NULL,
    source VARCHAR(40) NOT NULL DEFAULT 'rappel',   -- rappel | automatisation
    -- Ce qui rend un rappel unique : sans elle, la même échéance reviendrait
    -- chaque nuit. C'est la mémoire du « déjà prévenu ».
    empreinte VARCHAR(120) NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_lecture DATETIME NULL,
    -- Ce qui est déjà parti par courriel ne repart pas (cf. 059)
    date_envoi DATETIME NULL,
    CONSTRAINT fk_notification_utilisateur FOREIGN KEY (utilisateur_id)
        REFERENCES sys_utilisateurs(id) ON DELETE CASCADE,
    CONSTRAINT fk_notification_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    UNIQUE KEY uq_notification_empreinte (empreinte),
    KEY idx_notifications_lecture (date_lecture, date_creation)
) ENGINE=InnoDB;

-- Automatisations « quand… alors… » (cf. db/migrations/057) : générique et réglé
-- depuis l'administration, avec le journal de ce qui s'est déclenché et pourquoi.
CREATE TABLE IF NOT EXISTS sys_automatisations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    declencheur VARCHAR(40) NOT NULL,
    categorie_id INT NULL,
    conditions TEXT NULL,
    actions TEXT NOT NULL,
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    ordre INT NOT NULL DEFAULT 100,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_automatisation_categorie FOREIGN KEY (categorie_id)
        REFERENCES sys_categories(id) ON DELETE CASCADE,
    KEY idx_automatisations_declencheur (declencheur, actif)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sys_journal_automatisation (
    id INT AUTO_INCREMENT PRIMARY KEY,
    automatisation_id INT NULL,
    document_id INT NULL,
    date_execution DATETIME DEFAULT CURRENT_TIMESTAMP,
    declencheur VARCHAR(40) NOT NULL,
    agi BOOLEAN NOT NULL DEFAULT FALSE,   -- les conditions étaient-elles réunies ?
    detail TEXT NULL,                     -- ce qui a été fait, ou pourquoi rien
    CONSTRAINT fk_journal_auto_automatisation FOREIGN KEY (automatisation_id)
        REFERENCES sys_automatisations(id) ON DELETE CASCADE,
    CONSTRAINT fk_journal_auto_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE,
    KEY idx_journal_auto_document (automatisation_id, document_id, agi)
) ENGINE=InnoDB;

-- Vues enregistrées : un jeu de critères de filtrage réutilisable, rattaché à
-- une catégorie pour son emplacement dans la navigation (cf. db/migrations/004).
CREATE TABLE IF NOT EXISTS sys_vues_enregistrees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    categorie_id INT NULL,
    criteres TEXT NOT NULL,             -- JSON : [{champ, operateur, valeur}]
    utilisateur_id INT NULL,            -- NULL = vue du système
    partagee BOOLEAN NOT NULL DEFAULT FALSE,
    ordre INT DEFAULT 100,
    -- Champs du repli en arborescence, séparés par des virgules (cf. 055).
    groupement VARCHAR(255) NULL,
    -- Liens déclarés vers d'autres vues (cf. db/migrations/069) : la
    -- « correspondance de champs » d'EzGED. JSON, porté par la vue — une
    -- déclaration n'a de sens qu'avec elle et disparaît avec elle.
    liens TEXT NULL,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_vues_categorie (categorie_id),
    CONSTRAINT fk_vues_categorie FOREIGN KEY (categorie_id) REFERENCES sys_categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_vues_utilisateur FOREIGN KEY (utilisateur_id) REFERENCES sys_utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Tableaux de bord personnalisés : une liste d'indicateurs décrits en JSON,
-- réutilisant le format de filtres du registre (cf. db/migrations/016).
CREATE TABLE IF NOT EXISTS sys_tableaux_de_bord (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,
    widgets TEXT NOT NULL,
    partage BOOLEAN NOT NULL DEFAULT FALSE,
    utilisateur_id INT NULL,
    ordre INT DEFAULT 100,
    date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tdb_utilisateur FOREIGN KEY (utilisateur_id) REFERENCES sys_utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Journal d'audit des actions importantes (cf. db/migrations/005).
-- `utilisateur_email` est recopié en clair pour que la trace reste lisible même
-- après suppression du compte concerné.
CREATE TABLE IF NOT EXISTS sys_journal_audit (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date_evenement DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilisateur_id INT NULL,
    utilisateur_email VARCHAR(255) NULL,
    action VARCHAR(100) NOT NULL,       -- ex: 'document.suppression'
    objet_type VARCHAR(50) NOT NULL,    -- ex: 'document'
    objet_id INT NULL,
    details TEXT NULL,                  -- JSON : état avant / après
    KEY idx_audit_date (date_evenement),
    KEY idx_audit_objet (objet_type, objet_id),
    CONSTRAINT fk_audit_utilisateur FOREIGN KEY (utilisateur_id) REFERENCES sys_utilisateurs(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ============================================================
-- Données d'exemple
-- ============================================================

-- Règles écrites sur des sys_documents réels (cf. db/migrations/014). Pour chaque
-- champ : une règle ciblée sur l'intitulé rencontré (priorité basse, testée en
-- premier), des variantes pour les autres formulations, puis un repli
-- générique. La première qui trouve l'emporte.

-- Membres du foyer (cf. db/migrations/023 et 024).
--
-- Volontairement distincts des comptes de connexion : un enfant, un conjoint
-- sans compte, un parent dont on garde les papiers peuvent être titulaires d'une
-- facture sans jamais ouvrir la GED.
--
-- Prénom **et** nom sont obligatoires : c'est la conjonction des deux qui permet
-- de rattacher un document à la bonne personne. Deux membres d'une même famille
-- portent le même nom de famille.
CREATE TABLE IF NOT EXISTS usr_membres (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(150) NOT NULL,
    prenom VARCHAR(100) NOT NULL,
    remarque VARCHAR(255) NULL
) ENGINE=InnoDB;

INSERT INTO usr_emetteurs (nom) VALUES
('EDF'),
('Impots.gouv'),
('Free Mobile'),
('Orange');

-- Quatre types de document, chacun avec son dossier de dépôt sous ocr_wait/
-- (cf. migration 043). L'emplacement du dépôt décide du classement : il n'y a
-- plus d'expression de reconnaissance à écrire (cf. migration 044).
INSERT INTO sys_categories (nom, nature, dossier_depot, ordre) VALUES
('Factures', 'type', 'factures', 10),
('Impôts', 'type', 'impots', 20),
('Banque', 'type', 'banque', 30),
('Courriers', 'type', 'courriers', 90);

-- Un jeu générique par type de document (cf. db/migrations/046) : une règle
-- s'applique au type dans lequel le document a été déposé, et à lui seul.
INSERT INTO sys_profils_extraction (categorie_id, nom, generique, priorite)
SELECT id, CONCAT(nom, ' (générique)'), TRUE, 1000
FROM sys_categories WHERE nature = 'type';

-- Les règles de lecture d'une facture française. Elles sont posées dans chaque
-- jeu générique : délibérément généreux, parce que retirer d'un type une règle
-- qui ne le concerne pas prend dix secondes, et en écrire une manquante dix
-- minutes. La table temporaire évite de recopier les motifs autant de fois qu'il
-- y a de types — une expression régulière recopiée est une expression qui
-- divergera.
CREATE TEMPORARY TABLE tmp_regles_communes (
    nom VARCHAR(150), champ_cible VARCHAR(100), pattern VARCHAR(500),
    type_champ VARCHAR(20), priorite INT
);
INSERT INTO tmp_regles_communes (nom, champ_cible, pattern, type_champ, priorite) VALUES
('Numéro de facture (n° de facture : …)', 'numero_facture', '(?im)^\\s*n[°ºo]\\s*de\\s+facture\\s*:\\s*(\\S.*?)\\s*$', 'texte', 10),
('Numéro de facture (facture n° …)', 'numero_facture', '(?i)facture\\s*n[°ºo]\\s*:?\\s*([A-Z0-9][A-Z0-9\\-/]{3,25})', 'texte', 11),
('Date de facture (intitulée)', 'date_document', '(?i)date\\s*(?:de\\s+)?facture\\s*:?\\s*([0-3]?\\d[/.\\-][01]?\\d[/.\\-]\\d{2,4})', 'date', 20),
('Montant TTC (total TTC / à payer)', 'montant_ttc', '(?i)(?:total|montant)\\s*(?:à\\s*payer|ttc)\\s*:?\\s*([0-9]{1,3}(?:[  ][0-9]{3})*[,.][0-9]{2})', 'montant', 29),
('Montant TTC (total … €)', 'montant_ttc', '(?i)total[^\\n]{0,40}?([0-9]{1,3}(?:[  ][0-9]{3})*,[0-9]{2})\\s*€', 'montant', 30),
('Numéro de client', 'numero_client', '(?im)^\\s*n[°ºo]\\s*(?:de\\s+)?client\\s*:\\s*(\\S.*?)\\s*$', 'texte', 50),
('Date du document (repli : première date trouvée)', 'date_document', '\\b([0-3]\\d[/.\\-][01]\\d[/.\\-](?:\\d{4}|\\d{2}))\\b', 'date', 90);

INSERT INTO sys_regles_extraction (profil_id, nom, champ_cible, pattern, type_champ, priorite)
SELECT p.id, r.nom, r.champ_cible, r.pattern, r.type_champ, r.priorite
FROM sys_profils_extraction p CROSS JOIN tmp_regles_communes r
WHERE p.generique = TRUE;

DROP TEMPORARY TABLE tmp_regles_communes;

INSERT INTO sys_tables_donnees (nom_table, libelle, description, colonne_libelle, colonnes_identifiantes)
VALUES ('usr_emetteurs', 'Émetteurs',
        'Qui envoie les documents : fournisseurs, administrations, banques. Une table du foyer comme une autre — un type qui veut un émetteur déclare un champ qui y puise.',
        'nom', 'nom'),
       ('usr_membres', 'Membres du foyer',
        'Personnes auxquelles un document peut être rattaché. Indépendantes des comptes de connexion.',
        'nom', 'prenom,nom');

-- Champ « Émetteur » sur les factures, adossé à la table des émetteurs (§21.12).
-- Déduction « une seule colonne suffit » : un nom d'émetteur ne se confond pas
-- avec autre chose dans un document, contrairement à un nom de personne.
INSERT INTO sys_regles_champs_categorie
    (categorie_id, champ, source_table, sources, libelle, obligatoire, deduction, ordre)
SELECT id, 'meta:emetteur', 'usr_emetteurs', 'usr_emetteurs', 'Émetteur', FALSE, 'une', 15
FROM sys_categories WHERE nom = 'Factures';

-- Champ « Titulaire » sur les factures, adossé aux membres du foyer.
-- Facultatif : le rendre obligatoire écarterait du registre (§17.7) toute
-- facture dont le titulaire n'a pas été reconnu. La vue ci-dessous les rassemble
-- à la place, pour qu'on les complète sans les perdre de vue.
-- Le titulaire désigne un compte de la GED (cf. db/migrations/027). Pour
-- rattacher un document à quelqu'un qui n'a pas de compte, basculer la source
-- sur « Membres du foyer » dans « Champs requis ».
INSERT INTO sys_regles_champs_categorie (categorie_id, champ, source_table, sources, libelle, obligatoire, ordre)
SELECT id, 'meta:titulaire', 'sys_utilisateurs', 'sys_utilisateurs,usr_membres',
       'Titulaire', FALSE, 50
FROM sys_categories WHERE nom = 'Factures';

-- Le numéro de facture **identifie** une facture (cf. db/migrations/036) : c'est
-- lui qui reconnaît la même pièce redéposée, et l'ajoute comme version au lieu
-- d'en faire une seconde fiche. Facultatif : une facture dont l'OCR n'a pas su
-- lire le numéro reste une facture, elle ne se rapproche simplement de rien.
INSERT INTO sys_regles_champs_categorie
    (categorie_id, champ, libelle, obligatoire, identifiant, ordre)
SELECT id, 'meta:numero_facture', 'N° facture', FALSE, TRUE, 5
FROM sys_categories WHERE nom = 'Factures';

-- Visibilité d'une vue, rôle par rôle (cf. db/migrations/048). Une vue sans
-- aucune ligne ici suit `partagee` : pouvoir restreindre n'oblige pas chaque
-- foyer à le faire.
CREATE TABLE IF NOT EXISTS sys_droits_vue (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    vue_id INT NOT NULL,
    CONSTRAINT fk_droits_vue_role FOREIGN KEY (role_id)
        REFERENCES sys_roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_droits_vue_vue FOREIGN KEY (vue_id)
        REFERENCES sys_vues_enregistrees(id) ON DELETE CASCADE,
    UNIQUE KEY uq_role_vue (role_id, vue_id)
) ENGINE=InnoDB;

-- Droits par branche (cf. db/migrations/056) : un rôle peut n'être autorisé que
-- sur certaines valeurs d'un champ. Aucune ligne sur un champ = aucune
-- restriction sur ce champ.
CREATE TABLE IF NOT EXISTS sys_droits_branche (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,
    valeur VARCHAR(255) NOT NULL,
    CONSTRAINT fk_droits_branche_role FOREIGN KEY (role_id)
        REFERENCES sys_roles(id) ON DELETE CASCADE,
    UNIQUE KEY uq_droit_branche (role_id, champ, valeur)
) ENGINE=InnoDB;

INSERT INTO sys_vues_enregistrees (nom, categorie_id, criteres, partagee, ordre, utilisateur_id)
SELECT 'Toutes les factures sans utilisateur associé', id,
       CONCAT('[{"champ": "categorie", "operateur": "egal", "valeur": "', id,
              '"}, {"champ": "meta:titulaire", "operateur": "vide", "valeur": null}]'),
       TRUE, 10, NULL
FROM sys_categories WHERE nom = 'Factures';

-- Rôle par défaut (les comptes est_admin=TRUE n'en ont pas besoin pour voir
-- toutes les catégories, mais ce rôle sert de modèle pour en créer d'autres
-- à droits plus limités, ex: un rôle "Enfant" qui ne voit que "Scolarité").
INSERT INTO sys_roles (nom, description) VALUES
('Foyer', 'Accès à toutes les catégories du foyer');

INSERT INTO sys_droits_categorie (role_id, categorie_id, peut_voir, peut_modifier,
                                  peut_deposer, peut_telecharger, peut_supprimer,
                                  peut_gerer_versions)
SELECT (SELECT id FROM sys_roles WHERE nom = 'Foyer'), id, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE
FROM sys_categories;

-- Le compte administrateur initial est créé automatiquement au démarrage de
-- l'API à partir des variables d'environnement ADMIN_EMAIL / ADMIN_PASSWORD
-- (voir app/auth.py), pas en dur ici, pour ne jamais committer de mot de
-- passe dans le dépôt.

-- ------------------------------------------------------------
-- Ce que cette entrée-ci montre d'une ligne de table (§22.61)
-- ------------------------------------------------------------
--
-- Trois niveaux, et chacun sait quelque chose que les autres ignorent : la
-- table déclare ce qui désigne une ligne, le champ choisit ce qui la compose
-- ici (§22.59), et l'entrée retient ce qui mérite la place d'une colonne.
--
-- Aucune ligne ici veut dire « tout ce que le champ propose ».

CREATE TABLE IF NOT EXISTS sys_affichages_valeur (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL,
    champ VARCHAR(100) NOT NULL,
    -- colonnes retenues, séparées par des virgules, dans l'ordre du champ
    colonnes VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_affichage_document_champ (document_id, champ),
    CONSTRAINT fk_affichage_document FOREIGN KEY (document_id)
        REFERENCES sys_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- Repère de migrations
-- ============================================================
--
-- Ce fichier crée une base **déjà à jour**. Les migrations de `db/migrations/`
-- ne servent qu'à faire évoluer une base existante : les rejouer ici serait au
-- mieux inutile, au pire destructeur — la migration 018 renomme des tables qui
-- portent déjà leur nom définitif. On les inscrit donc comme appliquées.
--
-- Toute nouvelle migration doit être ajoutée à cette liste en même temps qu'au
-- dossier, faute de quoi elle serait rejouée sur chaque installation neuve.

CREATE TABLE IF NOT EXISTS sys_schema_migrations (
    version VARCHAR(50) PRIMARY KEY,
    nom VARCHAR(255) NOT NULL,
    date_application DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT IGNORE INTO sys_schema_migrations (version, nom) VALUES
('001', '001_index_date_import.sql'),
('002', '002_alignement_schema.sql'),
('003', '003_referentiel_par_defaut.sql'),
('004', '004_vues_enregistrees.sql'),
('005', '005_journal_audit.sql'),
('006', '006_regles_champs_categorie.sql'),
('007', '007_serveur_de_travaux.sql'),
('008', '008_etapes_travaux.sql'),
('009', '009_suppression_tags.sql'),
('010', '010_tables_donnees.sql'),
('011', '011_champs_reference.sql'),
('012', '012_booleens_non_nuls.sql'),
('013', '013_cles_etrangeres.sql'),
('014', '014_regles_extraction_reelles.sql'),
('015', '015_emetteur_orange.sql'),
('016', '016_tableaux_de_bord.sql'),
('017', '017_ordre_categories.sql'),
('018', '018_prefixes_tables.sql'),
('019', '019_emetteurs_sans_classement.sql'),
('020', '020_authentification_forte.sql'),
('021', '021_compression_archives.sql'),
('022', '022_sessions.sql'),
('023', '023_membres_du_foyer.sql'),
('024', '024_membres_prenom_nom.sql'),
('025', '025_comptes_prenom_nom.sql'),
('026', '026_verrous_documents.sql'),
('027', '027_titulaire_comptes.sql'),
('028', '028_sources_multiples.sql'),
('029', '029_exports.sql'),
('030', '030_colonnes_categorie.sql'),
('031', '031_titulaire_membres.sql'),
('032', '032_reglages.sql'),
('033', '033_colonnes_donnees.sql'),
('034', '034_fonctions_extraction.sql'),
('035', '035_versions_document.sql'),
('036', '036_champ_identifiant.sql'),
('037', '037_identifiant_factures.sql'),
('038', '038_regles_sans_emetteur.sql'),
('039', '039_deduction_declaree.sql'),
('040', '040_tri_par_defaut.sql'),
('041', '041_index_metadonnees.sql'),
('042', '042_nature_categorie.sql'),
('043', '043_dossier_depot.sql'),
('044', '044_emplacement_fait_foi.sql'),
('045', '045_classement_demande.sql'),
('046', '046_profils_extraction.sql'),
('047', '047_colonnes_types_seuls.sql'),
('048', '048_droits_fins.sql'),
('049', '049_fiches_de_liaison.sql'),
('050', '050_preferences_affichage.sql'),
('051', '051_champs_masques_par_type.sql'),
('052', '052_corbeille_documents.sql'),
('053', '053_integrite_archives.sql'),
('054', '054_macros_extraction.sql'),
('055', '055_groupement_vues.sql'),
('056', '056_droits_branche.sql'),
('057', '057_automatisations.sql'),
('058', '058_echeances_rappels.sql'),
('059', '059_courriel_rappels.sql'),
('060', '060_emetteur_generique.sql'),
('061', '061_menage_emetteur.sql'),
('062', '062_rejet_depot.sql'),
('063', '063_job_se_souvient_du_type.sql'),
('064', '064_fiche_simple.sql'),
('065', '065_pieces_document.sql'),
('066', '066_integrite_et_versions_par_piece.sql'),
('067', '067_echec_definitif.sql'),
('068', '068_rattachements.sql'),
('069', '069_liens_de_vue.sql'),
('070', '070_export_par_modele.sql'),
('071', '071_mode_developpeur.sql'),
('072', '072_entree_sans_fichier.sql'),
('073', '073_liens_de_type.sql'),
('074', '074_champ_documents.sql'),
('075', '075_type_de_champ.sql'),
('076', '076_champ_documents_borne.sql'),
('077', '077_extraction_attendue.sql'),
('078', '078_conformite_rangee.sql'),
('079', '079_colonnes_mortes.sql'),
('080', '080_lignes_par_page_du_compte.sql'),
('081', '081_preferences_apparence.sql'),
('082', '082_colonnes_affichees.sql'),
('083', '083_affichage_par_entree.sql'),
('084', '084_depot_manuel.sql'),
('085', '085_depot_manuel_corrige.sql');
