FROM python:3.13-slim AS base

# poppler-utils fournit `pdftotext -bbox`, qui rend la **position** de chaque mot
# dans la page (§21.5) : c'est ce qui permet de désigner une valeur sur l'image du
# document plutôt que d'écrire une expression régulière à l'aveugle.
#
# pngquant sert à l'optimiseur d'ocrmypdf (§17.8) : il quantifie les images des
# scans. Sans lui, `--optimize 2` n'a presque aucun effet — mesuré sur les
# documents du projet : 0 % de gain sans, 60 à 82 % avec. jbig2enc, qui
# compresserait en plus les images en noir et blanc, n'existe pas dans Debian.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ocrmypdf \
    tesseract-ocr \
    tesseract-ocr-fra \
    ghostscript \
    unpaper \
    qpdf \
    pngquant \
    poppler-utils \
    # mariadb-client fournit `mariadb-dump`, sur lequel repose la copie de
    # secours (§22.49). Un dump SQL se relit avec n'importe quel client, sans
    # l'application et sans ce code — c'est ce qui fait qu'une sauvegarde vaut
    # encore quelque chose dans dix ans.
    mariadb-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# migrations SQL jouées au démarrage (app/migrations.py)
COPY db ./db

# la commande réelle (worker ou api) est fixée dans docker-compose.yml
CMD ["python", "-m", "app.worker"]


# ------------------------------------------------------------------
# Image de test (§18.34)
#
# Les dépendances de test sont installées **dans une couche à part**, réutilisée
# d'une exécution à l'autre. Auparavant, `scripts_tests.sh` les réinstallait à
# chaque lancement : quelques secondes à chaque fois, et une dépendance au
# réseau — une machine hors ligne voyait la suite échouer avant d'avoir commencé.
#
# Elles ne sont pas embarquées dans l'image de service : pytest n'a rien à faire
# sur une installation qui tourne.
# ------------------------------------------------------------------
FROM base AS tests
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
