# Installation

## Prérequis

* **Docker** et **Docker Compose** (v2). Rien d'autre : Python, MariaDB,
  Tesseract et Ghostscript vivent dans les conteneurs.
* Une machine qui reste allumée — le serveur de travaux océrise en continu.

### Configuration matérielle

Chiffres **mesurés** sur un Xeon E5-2470 v2 (2013, 2,4 GHz) avec 15 Go de
mémoire. Une machine récente fait mieux.

| Taille du foyer | Processeur | Mémoire | Disque |
|---|---|---|---|
| jusqu'à 5 000 documents | 2 cœurs | 4 Go | 20 Go + vos PDF |
| jusqu'à 20 000 documents | 4 cœurs | 8 Go | 60 Go + vos PDF |

* Le **disque** : vos PDF, plus ~15 Mo de base par millier de documents, plus les
  sauvegardes si elles emportent les archives.
* Le **processeur** décide de la vitesse d'entrée, pas de lecture : ~7 secondes
  par document, à plusieurs de front (réglable).
* Un **Raspberry Pi 4** convient à un foyer qui dépose quelques documents par
  semaine ; la reprise d'un existant y sera longue.

## Première installation

```bash
git clone <votre dépôt> homeged && cd homeged
cp .env.example .env
```

Renseignez dans `.env` :

| Variable | Ce que c'est |
|---|---|
| `SECRET_KEY` | Signe les jetons de session. `openssl rand -hex 32`. **L'API refuse de démarrer avec la valeur d'exemple.** |
| `DB_PASSWORD`, `DB_ROOT_PASSWORD` | Mots de passe de la base |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Le premier compte administrateur |
| `COOKIE_SECURE` | `true` **si et seulement si** vous servez en HTTPS |

```bash
docker compose up -d --build
```

L'interface répond sur **http://localhost:8081**. Le premier écran propose un
classement de départ : « L'essentiel », « Foyer complet », ou une page blanche.

> 📸 **Capture à placer ici — `images/installation.png`**
> L'écran de première installation : le choix du modèle de classement, le nom du
> foyer et le fuseau horaire.

## Ce qui vit sur le disque

| Dossier | Contenu | À sauvegarder |
|---|---|---|
| `storage/` | Les PDF archivés | **oui** |
| `sauvegardes/` | Les copies de secours | non (c'est la copie) |
| `ocr_wait/` | Les dépôts en attente | non (transitoire) |
| `travaux/` | Les fichiers reçus, le temps du traitement | non |
| `apercus/` | Miniatures — un cache | non |
| `themes/`, `langues/` | Vos personnalisations | oui, si vous en avez |

La **base** se sauvegarde aussi : voir [Sauvegarde et restauration](Sauvegarde-et-restauration).

## Mise à jour

```bash
git pull
docker compose build && docker compose up -d
```

Les migrations de base s'appliquent seules au démarrage. **Faites une sauvegarde
avant** : c'est le geste qui rend une mise à jour réversible.
