-- Colonnes et tri : réservés aux types de document (§19.7).
--
-- Un dossier organise, il ne contient aucun document en propre : il n'a donc ni
-- colonnes ni tri d'ouverture. L'administration le refuse depuis le §19.1, mais
-- les réglages posés **avant** la distinction sont restés en base — muets, sans
-- effet, et prêts à ressurgir si l'on rebasculait la catégorie en type.
--
-- Cette migration les retire. Elle emporte aussi l'héritage : une catégorie ne
-- reprend plus les colonnes de son parent. C'était utile quand une catégorie
-- pouvait à la fois porter des documents et en contenir d'autres ; ce n'est plus
-- le cas, et l'héritage n'avait donc plus rien à transmettre — sinon, justement,
-- ces réglages fantômes. À la place, une action explicite : « appliquer ces
-- colonnes à tous les types de ce dossier ». Un réglage que l'on déclenche vaut
-- mieux qu'un héritage que l'on subit ; le second se découvre toujours au
-- mauvais moment.

DELETE k FROM sys_colonnes_categorie k
JOIN sys_categories c ON c.id = k.categorie_id
WHERE c.nature = 'dossier';

UPDATE sys_categories SET tri_champ = NULL, tri_sens = NULL WHERE nature = 'dossier';
