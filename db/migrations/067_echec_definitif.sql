-- Erreur récupérable ou définitive (§21.15).
--
-- Nous reprenions les travaux indéfiniment : toutes les cinq minutes, pour
-- toujours, y compris ceux que rien ne débloquera jamais. EzGED sépare l'erreur
-- — retentée — de l'erreur critique, irréversible ; l'idée est juste, et
-- l'absence de palier a un coût : un document irrécupérable tourne sans fin, et
-- l'écran ne distingue pas « la machine essaie encore » de « la machine a
-- renoncé, à vous de jouer ».
--
-- Deux compteurs, parce que ce sont deux situations :
--
--   * `tentatives` (déjà là) compte les traitements du fichier. Au-delà du
--     palier, un travail en **erreur technique** passe à `echec` : il sort de
--     toute reprise, et se voit dans l'écran sous son propre état. Le rejeu
--     manuel reste possible — c'est un geste délibéré, qui remet le compteur à
--     zéro ;
--   * `reprises_auto` compte les passes de la reprise automatique sur un travail
--     **bloqué** (champ attendu manquant). Au-delà du palier, la reprise cesse de
--     le reprendre : le travail reste bloqué, car il appelle une action humaine,
--     mais la machine ne fait plus semblant de chercher. Corriger une règle ou
--     rejouer le travail remet ce compteur à zéro — c'est-à-dire exactement
--     quand il y a une raison de réessayer.

ALTER TABLE sys_jobs MODIFY COLUMN statut
    ENUM('en_attente','en_cours','termine','erreur','bloque','ignore','a_classer','echec')
    DEFAULT 'en_attente';

ALTER TABLE sys_jobs ADD COLUMN reprises_auto INT NOT NULL DEFAULT 0;
