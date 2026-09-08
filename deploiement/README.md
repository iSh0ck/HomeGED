# Déploiement — surveillance des tentatives de connexion

Ce dossier contient ce qui vit **hors des conteneurs** : la configuration
fail2ban et la rotation du journal d'accès. Rien ici n'est appliqué
automatiquement — l'installation touche au système de l'hôte et demande les
droits root, c'est donc une décision explicite.

## Ce que le projet fournit déjà

nginx écrit son journal d'accès à deux endroits (`frontend/nginx.conf`) :

* sur la sortie standard, collectée par Docker et bornée à 10 Mo × 5 fichiers ;
* dans `logs/nginx/acces.log`, à chemin stable, monté depuis l'hôte.

Le second existe pour fail2ban. Le fichier de Docker ne convenait pas : son nom
contient l'identifiant du conteneur, qui change à chaque reconstruction, et son
contenu est enveloppé dans du JSON.

C'est **la seule source exploitable** : l'API, derrière le proxy, ne voit que
l'adresse du réseau Docker et journalise donc toujours la même. Le limiteur
applicatif, lui, ne s'y trompe pas — il lit l'en-tête `X-Real-IP`.

## Installation

```sh
sudo cp deploiement/fail2ban/filter.d/homeged-auth.conf /etc/fail2ban/filter.d/
sudo cp deploiement/fail2ban/jail.d/homeged.local       /etc/fail2ban/jail.d/
sudo cp deploiement/logrotate/homeged-nginx             /etc/logrotate.d/
sudo systemctl reload fail2ban
```

Adapter dans `homeged.local` : le chemin `logpath` si le projet n'est pas dans
`/home/shk/homeged`, et surtout `ignoreip` à votre plan d'adressage — s'exclure
soi-même de sa propre GED est l'issue la plus probable d'un réglage approximatif.

## Vérifications

```sh
# le filtre reconnaît-il les lignes réelles ?
fail2ban-regex logs/nginx/acces.log deploiement/fail2ban/filter.d/homeged-auth.conf

# la jail est-elle active, et qui est banni ?
sudo fail2ban-client status homeged-auth

# lever un bannissement
sudo fail2ban-client set homeged-auth unbanip 192.168.1.42

# la rotation ferait-elle ce qu'on croit ?
sudo logrotate -d /etc/logrotate.d/homeged-nginx
```

## Le piège à connaître

Un service publié par Docker **n'est pas protégé** par les règles que fail2ban
place d'ordinaire dans la chaîne `INPUT` : le trafic vers un conteneur est
routé, donc traité par `FORWARD`, et Docker y insère ses propres règles avant.
Sans précaution, les bannissements apparaissent bien dans
`fail2ban-client status` et ne bloquent rien du tout.

La jail fournie contourne cela avec `banaction = iptables-allports[chain="DOCKER-USER"]` :
`DOCKER-USER` est la chaîne prévue par Docker pour les règles de l'administrateur,
et elle est traversée avant celles de la publication de ports.

## Ce que fail2ban ajoute au limiteur déjà présent

L'application compte déjà les échecs (`app/limitation.py`) et écarte une source
au-delà de 5 tentatives par quart d'heure, avec un écran d'administration pour
lever les blocages. Trois différences :

| | Limiteur applicatif | fail2ban |
|---|---|---|
| Portée | l'authentification seule | toute la machine |
| Survie | en mémoire du processus : un redémarrage de l'API remet à zéro | sur disque, survit aux redémarrages |
| Niveau | la requête est traitée puis refusée | le paquet n'atteint jamais l'application |

Sur un réseau domestique fermé, le gain est modeste. Il devient réel le jour où
l'interface est exposée sur Internet.

---

## Migrer HomeGED vers un autre serveur

Question posée : faut-il un écran dédié dans l'administration ? **Non.** Une
migration se fait service arrêté ; une interface qui tourne dans le service ne
peut pas la conduire — elle devrait s'éteindre au milieu. Et il n'y a rien à
calculer : tout ce qui doit voyager est nommé ci-dessous.

Deux choses seulement contiennent l'état du foyer :

| Ce qui compte | Où | Comment ça voyage |
|---|---|---|
| Les PDF archivés, les dépôts en attente, les journaux nginx | `./storage`, `./watch`, `./logs` — dans le dossier du projet | copie du dossier |
| Le registre : documents, catégories, comptes, journal d'audit | volume Docker `homeged_db_data` | **sauvegarde SQL** (voir plus bas) |
| Les secrets et les chemins | `.env` | copie du fichier |

Le reste — images, conteneurs, dépendances — se reconstruit à l'arrivée avec
`docker compose build`.

### Sur l'ancien serveur

```bash
cd /chemin/vers/homeged
# 1. La base, en une sauvegarde cohérente (les conteneurs peuvent rester allumés :
#    --single-transaction fige une vue de la base sans bloquer les écritures)
. ./.env
docker compose exec -T db sh -c \
  'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --events "$MARIADB_DATABASE"' \
  > sauvegarde-homeged.sql

# 2. Tout le reste, y compris .env et les archives
docker compose down
tar czf homeged-complet.tar.gz --exclude=.git .
```

> Copier directement le volume `db_data` fonctionne aussi, **à condition d'avoir
> arrêté la base avant** : copier un fichier de données MariaDB en cours
> d'écriture donne une base qui ne remonte pas, et on ne s'en aperçoit qu'au
> moment de la restaurer. La sauvegarde SQL n'a pas ce défaut.

### Sur le nouveau serveur

```bash
tar xzf homeged-complet.tar.gz -C /chemin/vers/homeged
cd /chemin/vers/homeged
docker compose up -d db          # la base se crée vide, avec db/schema.sql
sleep 20
. ./.env
docker compose exec -T db sh -c \
  'mariadb -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' < sauvegarde-homeged.sql
docker compose up -d --build     # api, worker, frontend
```

Puis vérifier, dans cet ordre : la connexion, un document qui s'ouvre (le PDF
vient de `./storage`, pas de la base), et **Administration → Supervision**, qui
dit d'un coup d'œil si le disque, la base et la file de traitements sont dans
l'état attendu.

### Ce qui n'est *pas* une migration

L'export complet de l'archive (Administration → Export) sert à autre chose :
sortir les documents **classés en dossiers**, pour un serveur de fichiers ou
pour quitter HomeGED. Il ne contient ni les comptes, ni les règles, ni le
journal — ce n'est pas une sauvegarde du service, c'est une sortie des documents.

### Et le jour où le disque sature

C'est le cas qui rend une migration urgente. Il se voit venir dans
**Administration → Supervision**, qui affiche l'occupation du disque et alerte
au-delà de 80 %. Trois leviers, du moins au plus coûteux :

1. **Vider la corbeille** (Administration → Corbeille) : les PDF supprimés y
   restent tant que personne ne tranche.
2. **Vérifier la compression** : le même écran indique combien d'archives
   attendent encore d'être reprises par l'optimiseur (§17.8, gain observé de 60
   à 80 %).
3. **Déplacer `./storage` sur un disque plus grand** et ajuster le montage dans
   `docker-compose.yml`. C'est le seul moyen d'augmenter durablement la capacité,
   et cela ne demande pas de migrer le reste.
