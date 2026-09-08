-- Les règles d'extraction ne se limitent plus à un émetteur (§18.43).
--
-- Le champ « Limiter à un fournisseur » promettait des règles taillées pour un
-- émetteur — EDF n'écrit pas ses numéros comme Orange. Il ne pouvait pas tenir
-- cette promesse : depuis le §17, l'émetteur n'est plus deviné, c'est une donnée
-- que le foyer saisit à la main. Un document qui arrive n'en a donc aucun, et
-- ces règles étaient écartées d'office au dépôt. Elles ne s'appliquaient qu'au
-- **rejeu**, après qu'on avait renseigné l'émetteur — un détour que rien à
-- l'écran n'expliquait.
--
-- Une option qui ne fonctionne que par un chemin non documenté vaut moins que
-- pas d'option du tout : on la retire. Le jour où le foyer aura assez d'émetteurs
-- aux formats différents pour que la distinction compte, la bonne réponse sera de
-- reconnaître l'émetteur **avant** d'appliquer les règles, pas de rétablir ce
-- champ.
--
-- Ce que cette migration perd : la restriction portée par une règle, le cas
-- échéant. Les règles elles-mêmes restent, et s'appliquent désormais à tous les
-- documents — ce qu'elles faisaient déjà, en pratique, à chaque dépôt.

ALTER TABLE sys_regles_extraction DROP FOREIGN KEY fk_regles_fournisseur;
ALTER TABLE sys_regles_extraction DROP COLUMN fournisseur_id;
