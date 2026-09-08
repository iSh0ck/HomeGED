-- D'où vient ce document : la main, ou le dossier surveillé (§22.68).
--
-- Un foyer dépose de deux façons : en posant un fichier dans `ocr_wait/`, où le
-- classement se déduit de l'endroit, et en le glissant dans l'application, où
-- l'on dit son type au moment du dépôt. Rien ne distinguait les deux ensuite,
-- alors que ce n'est pas la même histoire : le second a été vu et rangé par
-- quelqu'un, le premier est arrivé tout seul.
--
-- La trace existait — `sys_jobs.chemin_source` — mais les tâches se purgent :
-- l'information disparaissait avec elles. Elle est donc recopiée sur le
-- document, qui, lui, reste.
--
-- NULL veut dire « on ne sait pas » : c'est le cas des documents antérieurs
-- dont la tâche a déjà été purgée. On ne devine pas à leur place, aucune icône
-- ne s'affiche, et c'est plus honnête qu'un « automatique » inventé.

ALTER TABLE sys_documents
    ADD COLUMN depot_manuel BOOLEAN NULL;

-- Ce que les tâches encore présentes permettent de savoir, tant qu'elles sont là.
UPDATE sys_documents d
   JOIN sys_jobs j ON j.document_id = d.id
    SET d.depot_manuel = (j.chemin_source LIKE '/data/travaux/%')
  WHERE j.chemin_source IS NOT NULL;
