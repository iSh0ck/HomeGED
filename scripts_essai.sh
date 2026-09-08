#!/usr/bin/env sh
# Installation jetable : éprouver un premier démarrage sans toucher à la vraie.
#
# Elle vit dans son propre projet Docker (`homeged-essai`), avec ses propres
# volumes et ses propres ports. La détruire n'atteint donc ni vos documents, ni
# votre base, ni vos réglages.
set -e
cd "$(dirname "$0")"

PROJET="homeged-essai"
COMPOSE="docker compose -p $PROJET -f docker-compose.essai.yml"

case "${1:-aide}" in
  demarrer)
    # La base d'abord, et on attend qu'elle soit prête avant le reste : au tout
    # premier démarrage elle se crée et joue db/schema.sql, ce qui prend plus de
    # temps que la patience de `depends_on`. Démarrer les autres services dans la
    # foulée les fait échouer sur une base qui n'existe pas encore.
    echo "→ construction des images"
    $COMPOSE build
    echo "→ démarrage de la base (elle se crée au premier lancement)"
    $COMPOSE up -d db
    printf "  "
    for _ in $(seq 1 60); do
      etat=$(docker inspect --format '{{.State.Health.Status}}' "${PROJET}-db-1" 2>/dev/null || echo absent)
      [ "$etat" = "healthy" ] && break
      printf "."
      sleep 2
    done
    echo " base $etat"
    echo "→ démarrage de l'application"
    $COMPOSE up -d
    echo "→ attente de l'API"
    for _ in $(seq 1 40); do
      if curl -sf http://localhost:8002/installation >/dev/null 2>&1; then break; fi
      sleep 2
    done
    echo
    adresse=$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
    echo "  Interface : http://localhost:8082   (installation réelle : 8081)"
    [ -n "$adresse" ] && echo "              http://$adresse:8082   (depuis un autre poste du foyer)"
    echo "  API       : http://localhost:8002   (installation réelle : 8001)"
    echo "  Base      : 127.0.0.1:3308          (installation réelle : 3307)"
    curl -s http://localhost:8002/installation \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print('  Installation requise :', d.get('requise'), '| modèles proposés :', ', '.join(m['libelle'] for m in d.get('modeles', [])))" \
      2>/dev/null || echo "  (l'API ne répond pas encore : ./scripts_essai.sh journal)"
    ;;
  recommencer)
    echo "→ effacement des volumes d'essai, puis redémarrage"
    $COMPOSE down -v
    "$0" demarrer
    ;;
  detruire)
    echo "→ suppression de l'installation d'essai (conteneurs, réseau, volumes)"
    $COMPOSE down -v --remove-orphans
    # Les images aussi : « détruire » doit vouloir dire détruire. Leurs couches
    # sont partagées avec celles de l'installation réelle, la reconstruction
    # suivante est donc rapide.
    echo "→ suppression des images d'essai"
    docker image rm "${PROJET}-api" "${PROJET}-worker" "${PROJET}-frontend" >/dev/null 2>&1 || true
    echo "  Rien n'en reste."
    ;;
  journal)
    $COMPOSE logs --tail 60 "${2:-}"
    ;;
  etat)
    $COMPOSE ps
    ;;
  *)
    echo "Usage : $0 {demarrer|recommencer|detruire|journal [service]|etat}"
    ;;
esac
