#!/usr/bin/env sh
# Lance la suite de tests dans un conteneur jetable, sur une base dédiée.
#
# Les tests ne touchent jamais aux données réelles : ils travaillent sur la base
# `homeged_test`, recréée à chaque exécution à partir de db/schema.sql puis de
# toutes les migrations — ce qui vérifie au passage qu'une installation neuve
# reste cohérente.
set -e
cd "$(dirname "$0")"
. ./.env

echo "→ préparation des bases de test"
# `homeged_test%` : la suite s'exécute en parallèle, chaque processus travaillant
# sur sa propre base (homeged_test_gw0, _gw1…). Le droit est donné sur le motif,
# les bases elles-mêmes étant créées par les processus qui en ont besoin — leur
# nombre dépend de la machine.
docker compose exec -T db mariadb -uroot -p"$DB_ROOT_PASSWORD" -e "
CREATE DATABASE IF NOT EXISTS homeged_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON \`homeged\_test%\`.* TO '$DB_USER'@'%';
FLUSH PRIVILEGES;" 2>/dev/null

# Sans argument, toute la suite ; sinon les cibles données (chemins relatifs
# au dépôt, le conteneur travaillant dans /srv).
CIBLES="${*:-/srv/tests}"

# Exécution en parallèle : `loadfile` envoie chaque fichier à un seul processus,
# ce qui respecte les tests qui posent un état pour tout leur fichier. Se désactive
# avec PARALLELE="" pour lire une trace d'échec sans entrelacement.
PARALLELE="${PARALLELE-"-n auto --dist loadfile"}"

echo "→ exécution de la suite"
# Le code du dépôt est monté par docker-compose.tests.yml : les tests portent sur
# l'arbre de travail, sans reconstruction d'image à chaque itération — sans quoi
# ils s'exécuteraient sur le code figé au dernier build.
#
# L'image de test, elle, porte pytest et ses compagnons dans une couche réutilisée
# d'une fois sur l'autre. `--build` la reconstruit si `requirements-dev.txt` a
# changé, et ne fait rien sinon.
docker compose -f docker-compose.yml -f docker-compose.tests.yml run --rm --no-deps --build \
  -e DB_NAME=homeged_test \
  -e SECRET_KEY=cle-de-test-suffisamment-longue-pour-les-tests \
  -e ADMIN_EMAIL=admin@test.local \
  -e ADMIN_PASSWORD=motdepasse-de-test-1234 \
  `# Hachage au coût minimal : la suite hache des centaines de mots de passe` \
  `# dont aucun ne protège quoi que ce soit. À 12 tours, bcrypt coûtait un quart` \
  `# de seconde par mot de passe et représentait l'essentiel des trois minutes.` \
  -e BCRYPT_ROUNDS=4 \
  tests python -m pytest -q $PARALLELE $CIBLES
