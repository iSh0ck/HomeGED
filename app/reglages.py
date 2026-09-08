"""
Réglages du foyer, modifiables depuis l'administration (§18.22).

Le projet vise plusieurs foyers, pas un seul. Or tout ce qui se règle vivait dans
`.env` : durée d'une session, seuil de verrouillage, langue de l'OCR, résolution
des scans… Autant de décisions qui ne concernent pas le fonctionnement du service
mais **les habitudes d'un foyer**, et qu'on ne pouvait prendre qu'avec un accès
SSH et un redémarrage. Un foyer qui reprend l'application héritait des arbitrages
du précédent.

Ce module tient la liste fermée de ces réglages, avec pour chacun son type, ses
bornes et son intitulé — de quoi construire l'écran de réglage sans écrire les
libellés deux fois, et refuser une valeur avant qu'elle ne casse quelque chose.

Ce qui reste dans `.env`, et doit y rester : les mots de passe de la base, la clé
de signature, les chemins de volumes. Ce sont des secrets ou des décisions
d'installation ; les exposer dans une interface n'aurait pas de sens.
"""
import re
from dataclasses import dataclass, field
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from . import config
from .db import Reglage


@dataclass
class Champ:
    defaut: str
    libelle: str
    description: str
    # texte | entier | booleen | choix | secret
    #
    # `secret` (§21.10) : la valeur se règle mais ne se relit pas. L'API rend une
    # marque à la place, l'export l'ignore, et n'écrire que sur une valeur
    # fournie permet d'enregistrer le reste de l'écran sans retaper le mot de
    # passe — ce qui, sinon, pousse à le noter quelque part.
    type: str = "texte"
    groupe: str = "foyer"        # foyer | exploitation | affichage | courriel
    options: list = field(default_factory=list)
    # Ce qu'un choix **se lit** quand sa valeur est technique (§22.70) : le tri
    # par défaut proposait « date_document » et « nom_fichier », des noms de
    # colonnes que personne n'écrit et que tout le monde doit deviner. Vide, la
    # valeur se suffit à elle-même — « auto », « papier », « compacte ».
    libelles_options: dict = field(default_factory=dict)
    mini: Optional[int] = None
    maxi: Optional[int] = None
    unite: str = ""


# Les intitulés des colonnes du document, tels que le registre les affiche.
# Importés depuis `colonnes` pour qu'il n'y ait qu'une source (§22.70).
from .colonnes import LIBELLES_SYSTEME as LIBELLES_COLONNES  # noqa: E402


# @traduit-a-la-lecture
CONNUS: dict[str, Champ] = {
    # ------------------------------------------------------------ le foyer
    "nom_foyer": Champ(
        "", "Nom du foyer", "Affiché en tête de la navigation et dans l'onglet du "
        "navigateur. Laissé vide, l'application garde son nom.", groupe="foyer"),
    "fuseau_horaire": Champ(
        "Europe/Paris", "Fuseau horaire",
        "Les dates et heures affichées sont converties dans ce fuseau. Tout reste "
        "enregistré en temps universel : changer ce réglage ne modifie aucune donnée, "
        "il ne change que la lecture.", groupe="foyer"),

    # ------------------------------- la sécurité, puis le traitement
    #
    # L'ordre du fichier ne décide de rien — c'est `groupe` qui range les
    # réglages à l'écran (§19.16). Les deux familles restent voisines ici
    # parce qu'elles sont arrivées ensemble, en sortant du fichier `.env`.
    "duree_session_heures": Champ(
        "8", "Durée d'une session", "Au-delà, il faut se reconnecter. Court sur un poste "
        "partagé, long sur un ordinateur familial : c'est un arbitrage de foyer.",
        type="entier", mini=1, maxi=720, unite="heures", groupe="securite"),
    "tentatives_avant_verrouillage": Champ(
        "5", "Tentatives avant verrouillage",
        "Nombre d'échecs de connexion tolérés avant que l'adresse ne soit écartée un "
        "moment. Trop bas, on se verrouille soi-même en se trompant de touche.",
        type="entier", mini=3, maxi=50, unite="tentatives", groupe="securite"),
    "duree_verrouillage_minutes": Champ(
        "15", "Durée du verrouillage", "Combien de temps l'adresse reste écartée après "
        "trop d'échecs.", type="entier", mini=1, maxi=1440, unite="minutes",
        groupe="securite"),
    "duree_verrou_edition_minutes": Champ(
        "5", "Durée d'un verrou de modification",
        "Pendant qu'une fiche est ouverte en modification, personne d'autre ne peut "
        "l'écrire. Le verrou se libère seul après ce délai, au cas où la fenêtre serait "
        "restée ouverte.", type="entier", mini=1, maxi=120, unite="minutes",
        groupe="exploitation"),
    "expiration_export_minutes": Champ(
        "30", "Expiration d'une archive d'export",
        "Une archive non téléchargée s'efface d'elle-même après ce délai. Un export "
        "oublié sur le disque est une copie complète du foyer qui attend son heure.",
        type="entier", mini=5, maxi=1440, unite="minutes", groupe="securite"),
    "retention_jobs_jours": Champ(
        "7", "Purge automatique du suivi des travaux",
        "Les tâches terminées et les doublons disparaissent du suivi passé ce délai, "
        "avec le fichier reçu qu'ils conservaient. Ce qui appelle une action — à "
        "classer, bloqué, en erreur — n'est jamais purgé : le faire disparaître ferait "
        "oublier le problème. 0 : rien n'est purgé automatiquement.",
        type="entier", mini=0, maxi=3650, unite="jours", groupe="exploitation"),
    "mode_developpeur": Champ(
        "0", "Mode développeur (scripts Python)",
        "Autorise l'écriture et l'exécution de scripts Python depuis l'administration. "
        "Ce que cela implique : un script est du code exécuté par le service — qui peut "
        "en écrire un peut faire ce que le service peut faire ; il voit ce qu'on lui "
        "donne, et c'est donc un moyen de faire sortir des données ; son accès réseau "
        "n'est pas bloqué. Les bornes : un seul point d'entrée, un contexte explicite, "
        "un processus séparé arrêté au bout d'une minute, aucun accès à la base, et "
        "chaque exécution journalisée. À n'armer que le temps qu'on s'en sert.",
        type="booleen", groupe="exploitation"),
    "travaux_tentatives_max": Champ(
        "5", "Abandon d'un travail après tant de tentatives",
        "Un dépôt qui échoue est retenté ; passé ce nombre, il est marqué en échec "
        "définitif et la reprise automatique ne le regarde plus — il reste visible dans "
        "le serveur de travaux, et un rejeu demandé à la main repart de zéro. Même palier "
        "pour les reprises d'un travail bloqué. 0 : on n'abandonne jamais.",
        type="entier", mini=0, maxi=100, unite="tentatives", groupe="exploitation"),
    "retention_consultations_jours": Champ(
        "365", "Purge automatique des consultations",
        "Qui a ouvert quel document est tracé (§21.16). Ces lignes sont nombreuses et "
        "vieillissent vite : passé ce délai, elles sont effacées. Le reste de l'histoire "
        "d'un document — dépôt, modification, suppression — n'est jamais purgé. "
        "0 : on garde tout.",
        type="entier", mini=0, maxi=3650, unite="jours", groupe="exploitation"),
    "retention_journal_jours": Champ(
        "0", "Purge automatique du journal d'audit",
        "Les entrées plus anciennes sont effacées chaque nuit. 0 : rien n'est purgé "
        "automatiquement — la purge reste alors une décision prise à la main. "
        "L'historique des documents n'est jamais touché.",
        type="entier", mini=0, maxi=3650, unite="jours", groupe="exploitation"),
    "retention_corbeille_jours": Champ(
        "0", "Vidage automatique de la corbeille des dépôts",
        "Les fichiers écartés au dépôt et gardés en corbeille depuis plus longtemps sont "
        "détruits. 0 : jamais — la corbeille est le dernier filet avant la perte "
        "définitive. Sans effet sur les documents supprimés du registre, réglés en dessous.",
        type="entier", mini=0, maxi=3650, unite="jours", groupe="exploitation"),
    "retention_documents_supprimes_jours": Champ(
        "0", "Vidage automatique des documents supprimés",
        "Un document supprimé du registre part en corbeille et y reste consultable. "
        "Au-delà de ce délai, il est détruit pour de bon, avec son fichier. 0 : jamais — "
        "c'est un foyer, la place manque rarement, et un papier qu'on a cru inutile "
        "ressert parfois des années plus tard.",
        type="entier", mini=0, maxi=3650, unite="jours", groupe="exploitation"),
    "integrite_lot_par_passage": Champ(
        "25", "Contrôle d'intégrité des archives",
        "Nombre de fichiers relus à chaque cycle de maintenance pour vérifier qu'ils "
        "n'ont pas changé depuis leur archivage. Les moins récemment contrôlés d'abord : "
        "l'archive tourne d'elle-même sans jamais être relue d'un bloc. 0 : aucun "
        "contrôle — un disque qui se dégrade ne prévient pas.",
        type="entier", mini=0, maxi=500, unite="fichiers", groupe="exploitation"),
    # ------------------------------------------------------------ le courriel
    "courriel_actif": Champ(
        "false", "Envoyer les rappels par courriel",
        "Les rappels d'échéance et les messages des automatisations partent aussi par "
        "courriel, en un résumé espacé. Sans cela, ils n'existent que dans l'application — "
        "ce qui suppose de l'ouvrir.",
        type="booleen", groupe="courriel"),
    "smtp_serveur": Champ(
        "", "Serveur d'envoi (SMTP)",
        "Le serveur qui expédie les messages : celui de votre fournisseur d'accès ou de "
        "votre boîte. Exemple : smtp.example.net.",
        groupe="courriel"),
    "smtp_port": Champ(
        "587", "Port",
        "587 avec STARTTLS dans la plupart des cas, 465 pour du SSL direct, 25 sans "
        "chiffrement — à éviter hors d'un réseau qu'on maîtrise.",
        type="entier", mini=1, maxi=65535, groupe="courriel"),
    "smtp_securite": Champ(
        "starttls", "Chiffrement",
        "STARTTLS commence en clair puis chiffre ; SSL chiffre d'emblée. « Aucun » "
        "envoie identifiants et messages en clair sur le réseau.",
        type="choix", options=["starttls", "ssl", "aucun"], groupe="courriel"),
    "smtp_compte": Champ(
        "", "Compte", "Identifiant de connexion au serveur d'envoi. Vide : pas "
        "d'authentification.", groupe="courriel"),
    "smtp_mot_de_passe": Champ(
        "", "Mot de passe",
        "Gardé pour l'envoi et jamais réaffiché : l'écran montre qu'il existe, pas sa "
        "valeur. Laissez le champ vide pour ne pas le changer. Il ne part pas non plus "
        "dans l'export de configuration.",
        type="secret", groupe="courriel"),
    "smtp_expediteur": Champ(
        "", "Adresse d'expédition",
        "Ce que verront les destinataires. Beaucoup de serveurs exigent qu'elle "
        "corresponde au compte utilisé.", groupe="courriel"),
    "adresse_publique": Champ(
        "", "Adresse de HomeGED",
        "L'adresse à laquelle vous ouvrez l'application, pour que les courriels puissent "
        "y renvoyer : https://ged.maison.lan par exemple. Les messages ne contiennent "
        "jamais le document lui-même, seulement un lien vers sa fiche.",
        groupe="courriel"),
    "langue_ocr": Champ(
        "fra", "Langue de la reconnaissance de texte",
        "Langues cherchées dans les documents scannés, à la manière de Tesseract : "
        "« fra », ou « fra+eng » pour un foyer qui reçoit aussi des documents anglais. "
        "Chaque langue ajoutée ralentit un peu le traitement.",
        type="choix", groupe="exploitation",
        options=["fra", "fra+eng", "fra+deu", "fra+spa", "fra+ita", "fra+nld", "eng"]),
    "resolution_ocr": Champ(
        str(config.RESOLUTION_CIBLE), "Résolution des scans océrisés",
        "300 points par pouce suffisent à lire une facture et à la relire dans dix ans ; "
        "au-delà, le fichier grossit sans gagner en lisibilité.",
        type="choix", options=["150", "200", "300", "400", "600"], unite="ppp",
        groupe="exploitation"),
    # ---- Sauvegarde (§22.49) ---------------------------------------------
    "sauvegarde_active": Champ(
        "0", "Sauvegarder automatiquement",
        "Quand c'est actif, le serveur de travaux copie la base et les archives au "
        "rythme choisi. Rien n'est sauvegardé tant que ce réglage est à non : "
        "l'application ne décide pas à votre place de remplir un disque.",
        type="booleen", groupe="sauvegarde"),
    "sauvegarde_heures": Champ(
        "24", "Toutes les",
        "Le délai entre deux sauvegardes. Vingt-quatre heures convient à un foyer : "
        "on perd au pire une journée de dépôts, et les documents perdus se "
        "redéposent. Descendre plus bas n'a de sens que sur une installation très "
        "active.",
        type="entier", mini=1, maxi=720, unite="heures", groupe="sauvegarde"),
    "sauvegarde_dossier": Champ(
        "/data/sauvegardes", "Où les écrire",
        "Le chemin **vu par le conteneur**. Le dossier livré est monté depuis "
        "`./sauvegardes` ; pour écrire ailleurs — un disque externe, un partage "
        "réseau — montez-le dans docker-compose.yml et indiquez ici son chemin "
        "interne. Une sauvegarde sur le même disque que les données protège d'une "
        "fausse manœuvre, pas d'une panne de disque.",
        groupe="sauvegarde"),
    "sauvegarde_garder": Champ(
        "7", "Combien en garder",
        "Les plus anciennes sont effacées au-delà de ce nombre. Sept sauvegardes "
        "quotidiennes couvrent une semaine — assez pour s'apercevoir d'une erreur "
        "et revenir avant elle.",
        type="entier", mini=1, maxi=365, unite="sauvegardes", groupe="sauvegarde"),
    "sauvegarde_archives": Champ(
        "1", "Y mettre aussi les archives",
        "La base seule pèse quelques mégaoctets et se sauvegarde en une seconde ; "
        "elle contient le classement, les champs extraits et les droits, mais **pas "
        "les PDF**. Sans les archives, une restauration rendrait un registre qui "
        "désigne des fichiers absents. Décochez seulement si vous copiez `storage/` "
        "autrement (instantané du système de fichiers, sauvegarde de la machine).",
        type="booleen", groupe="sauvegarde"),
    "sauvegarde_mot_de_passe": Champ(
        "", "Mot de passe de la sauvegarde",
        "Vide : la sauvegarde reste un dossier lisible tel quel — c'est ce qui la "
        "rend restaurable dans dix ans sans cette application.\n\n"
        "Renseigné, chaque sauvegarde devient **un seul fichier chiffré** en "
        "AES-256 (`.tar.gz.enc`). Une sauvegarde part souvent ailleurs — un disque "
        "externe rangé dans un tiroir, un partage réseau, un disque qu'on revendra "
        "un jour — et elle contient l'intégralité des papiers du foyer. Le "
        "chiffrement répond à ce moment-là, pas à un autre.\n\n"
        "Ce que cela implique : le déchiffrement passe par `openssl`, un outil "
        "standard, et la commande exacte est écrite en clair à côté de l'archive — "
        "rien de propre à ce code n'est nécessaire pour la relire. En revanche "
        "**ce mot de passe perdu, la sauvegarde est perdue** : aucune récupération "
        "n'existe, c'est le principe. Notez-le ailleurs que dans cette "
        "installation. Le chiffrement demande aussi de recopier l'ensemble à "
        "chaque fois : comptez le double de place pendant la durée de la "
        "sauvegarde, et un peu plus de temps.\n\n"
        "Gardé pour la sauvegarde et jamais réaffiché. Les sauvegardes déjà "
        "faites ne sont pas touchées : le changement vaut pour les suivantes.",
        type="secret", groupe="sauvegarde"),
    "sauvegarde_alerte_jours": Champ(
        "3", "Prévenir si rien n'est sauvegardé depuis",
        "Au-delà de ce délai sans sauvegarde réussie, l'administration affiche un "
        "avertissement. Une sauvegarde qui a cessé de fonctionner sans que personne "
        "ne le sache est pire que pas de sauvegarde du tout : on s'y fie.",
        type="entier", mini=1, maxi=365, unite="jours", groupe="sauvegarde"),
    "traitements_simultanes": Champ(
        "0", "Documents traités en même temps",
        "Combien de documents le serveur de travaux océrise en parallèle (§22.41). "
        "**0 : automatique** — la moitié des cœurs de la machine, quatre au plus, "
        "ce qui convient presque toujours.\n\n"
        "Un document demande environ sept secondes, passées presque entièrement dans "
        "l'océrisation : à un seul à la fois, c'est cinq cents documents à l'heure, et "
        "reprendre l'existant d'un foyer de vingt mille en demande quarante. Traiter à "
        "trois ou quatre divise d'autant.\n\n"
        "Monter plus haut que la moitié des cœurs ne sert à rien : les océrisations se "
        "disputent alors le processeur au lieu de se le partager, et la machine devient "
        "lente pour tout le reste — y compris pour l'interface. Le changement prend effet "
        "en quelques secondes, sans redémarrage : les documents en cours vont au bout, "
        "les suivants profitent du nouveau réglage.",
        type="choix", options=["0", "1", "2", "3", "4", "6", "8"], groupe="exploitation"),
    "compression_niveau": Champ(
        str(config.PDF_OPTIMISATION), "Compression des archives",
        "0 : aucune. 1 : sans perte. 2 : recommandée — 60 à 80 % de gain observé sans "
        "perte de texte. 3 : agressive, à réserver aux documents sans photo.",
        type="choix", options=["0", "1", "2", "3"], groupe="exploitation"),

    "otp_obligatoire": Champ(
        "false", "Double authentification exigée de tous",
        "Chaque compte devra la mettre en place à sa prochaine connexion. Sur un foyer "
        "où l'application est accessible depuis l'extérieur, c'est la mesure qui compte "
        "le plus.", type="booleen", groupe="securite"),
    "longueur_min_mot_de_passe": Champ(
        "10", "Longueur minimale d'un mot de passe",
        "S'applique aux mots de passe créés ou changés après ce réglage. Les mots de "
        "passe existants ne sont pas invalidés — ce serait enfermer tout le monde dehors.",
        type="entier", mini=8, maxi=128, unite="caractères", groupe="securite"),

    # -------------------------------------------------------- l'affichage
    "ecran_accueil": Champ(
        "accueil", "Écran d'ouverture",
        "Ce que l'on voit en arrivant : la vue d'ensemble, ou directement le registre.",
        type="choix", options=["accueil", "registre"], groupe="affichage"),
    "lignes_par_page": Champ(
        "50", "Lignes par page du registre",
        "Le réglage de départ ; chacun peut le changer depuis la pagination.",
        type="choix", options=["25", "50", "100", "200"], groupe="affichage"),
    "tri_defaut_champ": Champ(
        "date_import", "Tri par défaut du registre",
        "La colonne sur laquelle le registre s'ouvre. Chaque catégorie peut en décider "
        "autrement depuis « Colonnes des tableaux » ; ceci est le tri de celles qui ne "
        "disent rien.", type="choix",
        options=["date_import", "date_document", "categorie", "nom_fichier"],
        # Les intitulés viennent de `colonnes.LIBELLES_SYSTEME`, ceux-là mêmes
        # que le registre affiche en tête de colonne : les récrire ici les
        # ferait diverger le jour où l'un change.
        libelles_options=LIBELLES_COLONNES,
        groupe="affichage"),
    "tri_defaut_sens": Champ(
        "desc", "Sens du tri par défaut",
        "Décroissant convient à une date — le plus récent en premier ; croissant à un "
        "nom.", type="choix", options=["asc", "desc"], groupe="affichage"),
    "densite": Champ(
        "normale", "Densité du tableau",
        "« Compacte » resserre les lignes : plus de documents à l'écran, un peu moins "
        "d'air entre eux.", type="choix", options=["normale", "compacte"],
        groupe="affichage"),
    "langue": Champ(
        "auto", "Langue de l'interface",
        "La langue du foyer. « Automatique » suit celle du navigateur de chacun. "
        "Le français est la langue d'origine : ce qu'une traduction ne couvre pas "
        "s'affiche en français plutôt qu'en vide.\n\n"
        "Pour en ajouter une : déposez un fichier JSON dans le dossier `langues/` "
        "de l'installation — un dictionnaire du français vers votre langue — puis "
        "rechargez la page. Rien à recompiler.",
        type="choix", options=["auto", "fr", "en"], groupe="affichage"),
    "theme": Champ(
        "auto", "Thème",
        "La palette de l'interface. « Automatique » suit le réglage clair/sombre du "
        "système d'exploitation.\n\n"
        "Pour en ajouter un : déposez un fichier JSON dans le dossier `themes/` de "
        "l'installation — une clé, un nom, et les variables de couleur — puis "
        "rechargez la page. Un thème ajouté qui reprend la clé d'un thème livré le "
        "remplace, ce qui permet de retoucher une palette sans la recopier.",
        # Les valeurs livrées ; un thème déposé ajoute la sienne, acceptée telle
        # quelle (§22.50). « clair » et « sombre » restent compris — un foyer ne
        # perd pas son réglage parce que le catalogue s'est enrichi.
        type="choix", options=["auto", "papier", "nuit", "ardoise", "sepia", "contraste"],
        groupe="affichage"),
    "couleur_accent": Champ(
        "#3e5c46", "Couleur d'accent",
        "Sélection, boutons principaux, colonnes filtrées. Le vert d'origine est celui "
        "d'une chemise cartonnée.", type="texte", groupe="affichage"),
}

# Quatre groupes, et la séparation entre les deux du milieu n'est pas cosmétique :
# on ne règle pas une durée de session dans le même état d'esprit qu'une langue
# d'océrisation. L'un décide de qui entre et sous quelles conditions, l'autre de
# ce que la machine fait des documents — les mélanger obligeait à relire la liste
# entière pour trouver ce qu'on cherchait.
# @traduit-a-la-lecture
GROUPES = [
    ("foyer", "Le foyer", "Ce qui identifie cette installation."),
    ("securite", "Sécurité et accès",
     "Qui entre, combien de temps, et à quelles conditions. Ces réglages étaient "
     "jusqu'ici dans le fichier .env, hors de portée d'un administrateur."),
    ("exploitation", "Traitement et conservation",
     "Ce que la machine fait des documents, et ce qu'elle garde — océrisation, "
     "compression, durées de rétention."),
    ("courriel", "Courriel",
     "Comment le foyer est prévenu hors de l'application. Les messages ne "
     "contiennent jamais le document lui-même, seulement un lien vers sa fiche."),
    ("sauvegarde", "Sauvegarde",
     "L'application détient l'unique exemplaire des papiers du foyer. Ce qui suit "
     "décide de la copie de secours : quand elle se fait, où elle va, combien de "
     "temps on la garde. Rien n'est imposé — le rythme et la destination "
     "dépendent de la machine et de ce dont vous disposez."),
    ("affichage", "Affichage", "La présentation, pour tout le foyer."),
]


class ReglageInvalide(ValueError):
    pass


# Ce que l'écran affiche à la place d'un secret enregistré : de quoi savoir qu'il
# existe, sans le montrer.
MARQUE_SECRET = "••••••••"


class InchangeSecret(Exception):
    """Le champ secret n'a pas été retouché : il ne faut pas l'écraser."""


def defaut(cle: str) -> str:
    return CONNUS[cle].defaut if cle in CONNUS else ""


def tous(session: Session, masquer_secrets: bool = False) -> dict:
    """
    Tous les réglages, valeurs par défaut comprises.

    `masquer_secrets` remplace la valeur des champs secrets par une marque : ce
    qui part vers l'écran ou l'export ne doit pas contenir un mot de passe.
    """
    enregistres = {r.cle: r.valeur for r in session.query(Reglage).all()}
    valeurs = {cle: enregistres[cle] if enregistres.get(cle) not in (None, "") else champ.defaut
               for cle, champ in CONNUS.items()}
    if masquer_secrets:
        for cle, champ in CONNUS.items():
            if champ.type == "secret":
                valeurs[cle] = MARQUE_SECRET if valeurs.get(cle) else ""
    return valeurs


def decrire() -> list[dict]:
    """De quoi construire l'écran de réglage sans écrire les intitulés deux fois."""
    return [{
        "cle": cle, "libelle": c.libelle, "description": c.description, "defaut": c.defaut,
        "type": c.type, "groupe": c.groupe, "options": c.options,
        # Ce qu'un choix se lit, quand sa valeur est technique (§22.70).
        "libelles_options": c.libelles_options,
        "mini": c.mini, "maxi": c.maxi, "unite": c.unite,
    } for cle, c in CONNUS.items()]


def lire(session: Session, cle: str) -> str:
    ligne = session.get(Reglage, cle)
    valeur = ligne.valeur if ligne and ligne.valeur not in (None, "") else None
    return valeur if valeur is not None else defaut(cle)


def entier(session: Session, cle: str) -> int:
    """
    Valeur entière d'un réglage. Une valeur illisible retombe sur le défaut plutôt
    que de faire échouer l'appel : un réglage abîmé ne doit pas empêcher de se
    connecter — ce serait s'enfermer dehors sans moyen de se rattraper.
    """
    try:
        return int(str(lire(session, cle)).strip())
    except (TypeError, ValueError):
        return int(defaut(cle) or 0)


def booleen(session: Session, cle: str) -> bool:
    return str(lire(session, cle)).strip().lower() in ("1", "true", "vrai", "oui", "on")


def valider(cle: str, valeur: Optional[str]) -> str:
    if cle not in CONNUS:
        raise ReglageInvalide(f"Réglage inconnu : « {cle} ».")
    champ = CONNUS[cle]
    valeur = ("" if valeur is None else str(valeur)).strip()

    if champ.type == "booleen":
        return "true" if valeur.lower() in ("1", "true", "vrai", "oui", "on") else "false"

    if champ.type == "secret" and valeur == MARQUE_SECRET:
        # L'écran renvoie la marque quand personne n'a retouché le champ :
        # l'écrire telle quelle remplacerait le mot de passe par des points.
        raise InchangeSecret()

    if not valeur:
        return champ.defaut

    if champ.type == "entier":
        try:
            nombre = int(valeur)
        except ValueError:
            raise ReglageInvalide(f"« {champ.libelle} » attend un nombre entier.")
        if champ.mini is not None and nombre < champ.mini:
            raise ReglageInvalide(f"« {champ.libelle} » ne peut pas descendre sous {champ.mini}.")
        if champ.maxi is not None and nombre > champ.maxi:
            raise ReglageInvalide(f"« {champ.libelle} » ne peut pas dépasser {champ.maxi}.")
        return str(nombre)

    # Thème et langue acceptent une valeur hors liste (§22.50, §22.51) : le
    # catalogue s'enrichit d'un fichier déposé, que ce module ne connaît pas.
    # La forme est vérifiée, l'existence non — un thème retiré retombe sur celui
    # d'origine côté interface, ce qui vaut mieux qu'un réglage refusé.
    if cle in ("theme", "langue"):
        if not re.fullmatch(r"[a-z0-9_-]{2,32}", valeur):
            raise ReglageInvalide(
                f"« {champ.libelle} » : une clé en minuscules, chiffres, tiret ou souligné.")
        return valeur

    if champ.type == "choix" and cle != "langue_ocr" and valeur not in champ.options:
        raise ReglageInvalide(
            f"« {champ.libelle} » : valeur inattendue. Attendu : {', '.join(champ.options)}.")

    if cle == "fuseau_horaire":
        try:
            ZoneInfo(valeur)
        except (ZoneInfoNotFoundError, ValueError, ModuleNotFoundError):
            # Un fuseau inconnu rendrait toutes les heures illisibles d'un coup.
            raise ReglageInvalide(
                f"« {valeur} » n'est pas un fuseau horaire connu (exemple : Europe/Paris).")

    if cle == "langue_ocr":
        # Tesseract combine ses langues avec « + ». On vérifie la forme, pas la
        # présence du paquet : une langue absente se verrait au traitement, et
        # refuser ici obligerait à connaître l'installation depuis l'interface.
        morceaux = [m for m in valeur.split("+") if m]
        if not morceaux or any(not m.isalpha() or len(m) != 3 for m in morceaux):
            raise ReglageInvalide(
                "La langue de l'OCR s'écrit en codes de trois lettres, séparés par « + » "
                "(exemple : fra+eng).")
        return "+".join(morceaux)

    if cle == "couleur_accent":
        couleur = valeur if valeur.startswith("#") else f"#{valeur}"
        if len(couleur) != 7 or any(c not in "0123456789abcdefABCDEF" for c in couleur[1:]):
            raise ReglageInvalide("La couleur s'écrit en hexadécimal, par exemple #3e5c46.")
        return couleur.lower()

    if cle == "nom_foyer" and len(valeur) > 80:
        raise ReglageInvalide("Le nom du foyer ne peut pas dépasser 80 caractères.")

    return valeur


def enregistrer(session: Session, valeurs: dict) -> dict:
    """
    Enregistre un lot de réglages, **après les avoir tous validés** : un réglage
    juste ne doit pas être écrit à côté d'un réglage refusé, sinon l'écran affiche
    un état que la base ne porte qu'à moitié.
    """
    valides = {}
    for cle, valeur in valeurs.items():
        try:
            valides[cle] = valider(cle, valeur)
        except InchangeSecret:
            continue   # champ secret laissé tel quel : on n'y touche pas
    for cle, valeur in valides.items():
        ligne = session.get(Reglage, cle)
        if ligne:
            ligne.valeur = valeur
        else:
            session.add(Reglage(cle=cle, valeur=valeur))
    session.commit()
    return tous(session)


def fuseaux_proposables() -> list[str]:
    """
    Quelques fuseaux courants, pour ne pas obliger à connaître la nomenclature
    IANA par cœur. La saisie libre reste possible : un foyer peut vivre n'importe
    où, et la liste complète en compte plus de six cents.
    """
    return [
        "Europe/Paris", "Europe/Brussels", "Europe/Zurich", "Europe/London",
        "Europe/Lisbon", "Europe/Madrid", "Europe/Berlin", "Atlantic/Reykjavik",
        "America/Montreal", "America/New_York", "America/Cayenne",
        "Indian/Reunion", "Pacific/Noumea", "UTC",
    ]
