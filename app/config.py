import os
import unicodedata

# Connexion MariaDB (surchargeable par variables d'environnement / .env)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "homeged")
DB_PASSWORD = os.getenv("DB_PASSWORD", "changeme")
DB_NAME = os.getenv("DB_NAME", "homeged")

SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)

# Dossiers
# Dépôt des fichiers à traiter (§19.2). Le dossier s'appelait `watch/` ; il
# s'appelle désormais `ocr_wait/`, ce qui dit ce qu'on y attend plutôt que ce que
# le serveur y fait. `WATCH_FOLDER` reste accepté : une installation en service ne
# doit pas s'arrêter parce qu'un nom a changé.
#
# Il n'appartient qu'à la GED : elle y tient un dossier par type de document, et
# personne n'y crée rien à la main (D3 de la phase 19).
OCR_WAIT_FOLDER = os.getenv("OCR_WAIT_FOLDER") or os.getenv("WATCH_FOLDER", "/data/ocr_wait")
STORAGE_FOLDER = os.getenv("STORAGE_FOLDER", "/data/storage")  # archivage final
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# Le type MIME de chacun de ces formats. Il ne sert pas qu'à la politesse : un
# fichier servi en `application/octet-stream` n'est pas *affiché* par le
# navigateur, il est **téléchargé** — et depuis une URL d'objet, sous un nom sans
# extension. C'est ce qui arrivait au bouton « Examiner » du serveur de travaux :
# on cliquait pour voir la page, on récupérait un fichier anonyme dans les
# téléchargements.
TYPES_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def nom_pour_entete(nom: str) -> str:
    """
    Un nom de fichier utilisable dans un en-tête HTTP.

    Les en-têtes sont en latin-1 : « reçu_2026.pdf » y casse la réponse entière.
    On retire donc les accents et tout ce qui n'est pas imprimable, plutôt que de
    risquer une erreur 500 sur un nom parfaitement légitime côté disque.
    """
    sans_accents = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode()
    propre = "".join(c for c in sans_accents if c.isprintable() and c not in '"\\')
    return propre.strip() or "document"


def type_mime(nom_fichier) -> str:
    """
    Le type MIME déduit de l'extension, `application/octet-stream` à défaut.

    À défaut seulement : un type inventé se lit plus mal qu'un téléchargement
    assumé, et le navigateur refuserait d'afficher ce qu'il ne sait pas rendre.
    """
    extension = os.path.splitext(str(nom_fichier))[1].lower()
    return TYPES_MIME.get(extension, "application/octet-stream")

# Corbeille : le worker y déplace les fichiers de storage/ que plus aucun document
# ne référence, au lieu de les effacer. Seul ce sous-dossier est monté en écriture
# pour l'API, afin qu'un administrateur puisse le consulter et le vider sans que
# l'API n'ait jamais le droit de toucher aux archives.
# Exports de l'archive (§17.30) : dossier de travail, et durée de vie d'une
# archive non téléchargée. Trente minutes suffisent à cliquer sur un lien ; au
# delà, une copie complète du foyer qui traîne devient un risque, pas un confort.
EXPORT_FOLDER = os.getenv("EXPORT_FOLDER", "/data/exports")

# Fichiers déposés, conservés le temps que vit leur travail (§18.53). Le PDF
# archivé n'est plus le fichier reçu — l'océrisation lui ajoute une couche de
# texte, la compression le réécrit. Tant qu'un travail est consultable, son
# fichier d'origine doit l'être aussi : c'est le seul moyen de comprendre un
# échec, et de rejouer un traitement quel qu'ait été son résultat.
TRAVAUX_FOLDER = os.getenv("TRAVAUX_FOLDER", "/data/travaux")

# Miniatures de première page (§19.20). Elles se **regénèrent** : ce dossier est
# un cache, pas une archive — le vider ne perd rien, il coûte une seconde par
# document au prochain affichage.
APERCUS_FOLDER = os.getenv("APERCUS_FOLDER", "/data/apercus")
# Ce que l'on glisse à la main sur une fiche simple (§22.1) : ces fichiers
# n'entrent pas par `ocr_wait` — leur type est dit au moment du dépôt, pas par le
# dossier où on les pose. L'API les écrit ici, le serveur de travaux les reprend.
DEPOTS_MANUELS_FOLDER = os.getenv("DEPOTS_MANUELS_FOLDER", "/data/depots_manuels")

# Personnalisation déposée par le foyer (§22.50, §22.51) : une palette ou une
# traduction est un fichier JSON qu'on copie dans ces dossiers. Rien à compiler,
# rien à redémarrer — c'est ce qui rend le projet reprenable par quelqu'un qui
# n'en lira jamais le code.
THEMES_FOLDER = os.getenv("THEMES_FOLDER", "/data/themes")
LANGUES_FOLDER = os.getenv("LANGUES_FOLDER", "/data/langues")
# Un dépôt manuel passe par la mémoire du serveur d'API : la borne évite qu'un
# fichier de plusieurs gigaoctets, déposé par erreur ou par malveillance, ne
# remplisse le disque avant que quiconque s'en aperçoive.
TAILLE_MAX_DEPOT = int(os.getenv("TAILLE_MAX_DEPOT", str(200 * 1024 * 1024)))
APERCU_LARGEUR = int(os.getenv("APERCU_LARGEUR", "600"))
EXPORT_DUREE_MINUTES = int(os.getenv("EXPORT_DUREE_MINUTES", "30"))

NOM_CORBEILLE = ".corbeille"
CORBEILLE_FOLDER = os.path.join(STORAGE_FOLDER, NOM_CORBEILLE)

# Surveillance du dossier watch : le polling (vérification périodique du
# contenu du dossier) est activé par défaut car plus fiable que les
# événements inotify natifs sur les partages réseau (SMB/NFS) ou sous Docker
# Desktop (Mac/Windows), où ces événements ne remontent pas toujours au
# conteneur. Mets à "false" si ton dossier watch est sur un disque local
# Linux natif et que tu préfères une détection instantanée.
WATCH_POLLING = os.getenv("WATCH_POLLING", "true").lower() == "true"
WATCH_POLLING_INTERVAL = float(os.getenv("WATCH_POLLING_INTERVAL", "3"))

# Compression des archives (§17.8)
#
# Un scan océrisé pèse lourd — l'image de la page y est stockée telle quelle.
# L'optimiseur d'ocrmypdf recompresse ces images ; mesuré sur les documents
# réels du projet : -60 % sur une facture légère, -82 % sur un scan de 2 Mo,
# avec 100 % du texte conservé et un écart visuel moyen de 0,07 % par pixel.
#
# Niveaux : 0 aucune, 1 sans perte (gain nul en pratique sans jbig2enc, absent
# de Debian), 2 quantification des images (le réglage retenu), 3 ajoute une
# recompression JPEG plus agressive pour deux points de gain supplémentaires —
# pas de quoi accepter une perte de plus sur des documents qu'on archive.
PDF_OPTIMISATION = int(os.getenv("PDF_OPTIMISATION", "2"))

# Résolution des pages océrisées (§17.10).
#
# `--force-ocr` rastérise **toutes** les pages à 400 ppp, quelle que soit la
# source. Mesuré sur une facture dont on connaissait le texte exact : à 300 ppp
# l'OCR est juste à 100 %, à 400 ppp à 99,5 % (une référence contractuelle
# perdue) pour un fichier 30 % plus lourd. Au-dessus de 300, on paie du poids
# sans rien gagner ; en dessous, on commence à perdre les petits caractères
# (150 ppp perd déjà une référence).
#
# 0 laisse la résolution d'origine intacte.
RESOLUTION_CIBLE = int(os.getenv("RESOLUTION_CIBLE", "300"))

# Stratégie d'océrisation :
#   `auto`  — préserve le texte déjà présent (`--redo-ocr`) et n'océrise que ce
#             qui est image. Un PDF né numérique garde son texte vectoriel : net
#             à tout zoom, exact au caractère près, et huit fois plus léger.
#   `force` — tout rastériser et tout ré-océriser (`--force-ocr`), utile face à
#             un scanner qui produit une couche de texte fausse.
OCR_STRATEGIE = os.getenv("OCR_STRATEGIE", "auto").lower()

# Reprise des archives déjà en place, par petits lots, pendant les temps morts
# du serveur de travaux. 0 désactive la reprise (les nouveaux documents restent
# compressés à l'arrivée).
COMPRESSION_LOT = int(os.getenv("COMPRESSION_LOT", "5"))

# Authentification
# Coût du hachage des mots de passe (bcrypt : 2^rounds tours).
#
# 12 est la valeur de service : environ un quart de seconde par mot de passe,
# assez lent pour rendre une attaque par force brute déraisonnable, assez rapide
# pour ne pas se voir à la connexion. La suite de tests l'abaisse — elle hache
# des centaines de mots de passe dont aucun ne protège rien, et payer le prix de
# la sécurité sur des données jetables ne protège personne, cela ralentit
# seulement ceux qui vérifient le code.
#
# Abaisser cette valeur en service serait une faute : `verifier_secret_key()`
# le signale au démarrage.
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

# Valeurs de SECRET_KEY qu'il ne faut jamais laisser en service : elles sont
# publiques (dépôt, documentation), donc n'importe qui peut forger un jeton
# d'administrateur valide. L'API refuse de démarrer avec l'une d'elles.
SECRET_KEYS_INTERDITES = {
    "change-me-in-production",
    "change_this_to_a_long_random_string",
}
LONGUEUR_MIN_SECRET_KEY = 32


def verifier_secret_key() -> list[str]:
    """
    Lève une erreur si la clé de signature est une valeur d'exemple connue.
    Renvoie la liste des avertissements non bloquants (clé trop courte).
    """
    if SECRET_KEY in SECRET_KEYS_INTERDITES:
        raise RuntimeError(
            "SECRET_KEY est encore la valeur d'exemple : n'importe qui pourrait "
            "forger un jeton d'administrateur. Génère-en une avec "
            "`openssl rand -hex 32` et renseigne-la dans .env."
        )
    avertissements = []
    if len(SECRET_KEY) < LONGUEUR_MIN_SECRET_KEY:
        avertissements.append(
            f"SECRET_KEY ne fait que {len(SECRET_KEY)} caractères "
            f"(recommandé : au moins {LONGUEUR_MIN_SECRET_KEY}, via `openssl rand -hex 32`)."
        )
    if BCRYPT_ROUNDS < 10:
        # Abaissé pour la suite de tests ; sur une installation qui sert, c'est
        # un mot de passe volé qui se craque en quelques heures au lieu de siècles.
        avertissements.append(
            f"BCRYPT_ROUNDS vaut {BCRYPT_ROUNDS} : les mots de passe sont hachés trop "
            f"vite pour résister à une attaque hors ligne. Retirez ce réglage de "
            f"l'environnement (valeur de service : 12)."
        )
    return avertissements


# Cookie de session : `Secure` impose une connexion chiffrée. Laissé à faux par
# défaut, l'application étant servie en HTTP en local — à passer à vrai dès
# qu'elle est publiée derrière HTTPS, sans quoi le cookie ne serait pas posé.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# Origines autorisées à appeler l'API depuis un navigateur. En production le
# frontend passe par le proxy nginx (même origine) : la liste ne sert qu'au
# serveur de développement Vite. `*` est refusé ici, une liste explicite évite
# qu'un site tiers pilote l'API avec le jeton d'un utilisateur connecté.
CORS_ORIGINS = [
    origine.strip()
    for origine in os.getenv(
        "CORS_ORIGINS", "http://localhost:8081,http://localhost:5173"
    ).split(",")
    if origine.strip()
]

# Limitation des tentatives de connexion (protection contre la force brute).
# Au-delà de LOGIN_MAX_TENTATIVES échecs dans la fenêtre, la source est écartée
# pendant la durée de verrouillage. Mettre LOGIN_MAX_TENTATIVES à 0 désactive.
# Registre des sessions (§17.2). Un jeton sans identifiant de session ne peut
# pas être révoqué : on le refuse. Mettre à "false" laisserait vivre les jetons
# délivrés avant la mise en place du registre — utile le temps d'une bascule,
# au prix de sessions invisibles dans « Mon compte ».
EXIGER_SESSION_ENREGISTREE = os.getenv("EXIGER_SESSION_ENREGISTREE", "true").lower() == "true"

LOGIN_MAX_TENTATIVES = int(os.getenv("LOGIN_MAX_TENTATIVES", "5"))
LOGIN_FENETRE_SECONDES = float(os.getenv("LOGIN_FENETRE_SECONDES", "900"))
LOGIN_VERROUILLAGE_SECONDES = float(os.getenv("LOGIN_VERROUILLAGE_SECONDES", "900"))

# Compte administrateur créé automatiquement au premier démarrage
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@homeged.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
