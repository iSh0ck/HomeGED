# Sauvegarde et restauration

HomeGED détient **l'unique exemplaire** de vos papiers : la base dit comment ils
sont rangés, `storage/` contient les PDF. Perdre l'un ou l'autre ne se rattrape
pas. C'est le seul défaut de cette application qui puisse coûter des années.

## Régler la sauvegarde

*Administration → Réglages généraux → **Sauvegarde***

| Réglage | Ce qu'il décide |
|---|---|
| **Sauvegarder automatiquement** | Éteint par défaut. Rien ne se fait tant que vous ne l'avez pas demandé. |
| **Toutes les** | Le délai entre deux sauvegardes. 24 h convient à un foyer : on perd au pire une journée de dépôts, et un document perdu se redépose. |
| **Où les écrire** | Le chemin **vu par le conteneur**. `./sauvegardes` est monté par défaut. |
| **Combien en garder** | Les plus anciennes sont effacées au-delà. Sept quotidiennes couvrent une semaine. |
| **Y mettre aussi les archives** | Sans les PDF, une restauration rendrait un registre qui désigne des fichiers absents. Ne décochez que si vous copiez `storage/` autrement. |
| **Prévenir si rien n'est sauvegardé depuis** | Au-delà, l'administration affiche un avertissement. Une sauvegarde qui a cessé sans qu'on le sache est pire que pas de sauvegarde. |

> 📸 **Capture à placer ici — `images/sauvegarde.png`**
> L'écran Sauvegarde : le bandeau d'état (« Dernière sauvegarde le … »), le
> bouton « Sauvegarder maintenant », et la liste des sauvegardes avec leur
> taille et leur état.

### La mettre ailleurs que sur le même disque

Une copie sur le disque qu'elle protège ne protège que d'une fausse manœuvre.
Montez le disque ou le partage dans `docker-compose.yml` :

```yaml
  worker:
    volumes:
      - /mnt/disque-externe/homeged:/data/sauvegardes
  api:
    volumes:
      - /mnt/disque-externe/homeged:/data/sauvegardes
```

puis `docker compose up -d worker api`. Le chemin **dans le réglage** reste
`/data/sauvegardes` : c'est celui que voit le conteneur.

## Ce que contient une sauvegarde

```
sauvegardes/2026-09-06_15h44/
├── base.sql          le dump MariaDB, en clair
├── storage/          copie des PDF archivés (si demandé)
└── sauvegarde.txt    date, tailles, et la marche à suivre pour restaurer
```

`sauvegarde.txt` est **écrit en dernier** : un dossier qui n'en a pas est une
sauvegarde interrompue, et l'écran la montre comme telle.

## Restaurer

### Toute l'installation

```bash
# 1. Arrêter ce qui écrit
docker compose stop worker api

# 2. La base
docker compose exec -T db mariadb -u root -p<mot de passe> homeged \
    < sauvegardes/2026-09-06_15h44/base.sql

# 3. Les archives
cp -r sauvegardes/2026-09-06_15h44/storage/* storage/

# 4. Repartir
docker compose start api worker
```

Vérifiez ensuite dans *Administration → Intégrité des archives* que chaque
document retrouve son fichier.

### Sur une machine neuve

Installez HomeGED comme au premier jour (voir [Installation](Installation)),
**sans passer l'écran de première installation**, puis restaurez : le dump
contient les comptes, le classement et les documents.

### Un seul document

Il n'y a rien à restaurer : la corbeille garde les documents supprimés, et
*Administration → Corbeille* garde les fichiers que plus aucun document ne
réclame. Regardez là d'abord.

## Éprouver sa sauvegarde

Une sauvegarde qu'on n'a jamais restaurée n'est pas une sauvegarde. Une fois par
an, restaurez-la **dans une base d'essai** :

```bash
docker compose exec db mariadb -u root -p<mot de passe> \
    -e "CREATE DATABASE homeged_essai"
docker compose exec -T db mariadb -u root -p<mot de passe> homeged_essai \
    < sauvegardes/<la plus récente>/base.sql
docker compose exec db mariadb -u root -p<mot de passe> \
    -e "SELECT COUNT(*) FROM homeged_essai.sys_documents"
docker compose exec db mariadb -u root -p<mot de passe> \
    -e "DROP DATABASE homeged_essai"
```

Le compte doit correspondre à ce qu'affiche le registre.
