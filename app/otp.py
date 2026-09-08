"""
Double authentification par code à usage unique (TOTP, RFC 6238).

Écrit à la main plutôt qu'ajouté en dépendance : l'algorithme tient en trente
lignes de bibliothèque standard, et une dépendance de plus sur le chemin de
l'authentification est une surface de plus à surveiller. Les vecteurs de test
de la RFC sont rejoués dans `tests/test_otp.py` — c'est ce qui rend ce choix
défendable : sans eux, réimplémenter de la cryptographie serait de
l'imprudence.

Trois précautions qui ne se voient pas dans la formule :

* **Fenêtre de tolérance** — le téléphone et le serveur n'ont jamais tout à fait
  la même heure. On accepte le pas précédent et le suivant, soit ±30 s. Plus
  large, on allongerait la durée de vie d'un code intercepté.
* **Comparaison à temps constant** — `secrets.compare_digest`, pour ne pas
  laisser deviner un code chiffre par chiffre en mesurant le temps de réponse.
* **Codes de secours** — un téléphone perdu ne doit pas fermer la porte
  définitivement. Ils sont hachés comme des mots de passe et consommés à l'usage.
"""
import base64
import hashlib
import hmac
import io
import json
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote

from passlib.context import CryptContext

from . import config

# Un pas de 30 secondes et 6 chiffres : les réglages par défaut de toutes les
# applications d'authentification. En changer rendrait l'application
# incompatible avec elles sans rien gagner.
PAS_SECONDES = 30
NOMBRE_CHIFFRES = 6
TOLERANCE_PAS = 1

NOMBRE_CODES_SECOURS = 8
GROUPES_CODE_SECOURS = 2       # « AB3CD-EF7GH » : deux groupes de cinq
CARACTERES_PAR_GROUPE = 5

# Les codes de secours sont des secrets à part entière : ils ouvrent la session
# aussi bien qu'un code du téléphone. Ils sont donc hachés, jamais stockés en
# clair, et affichés une seule fois — à leur création.
#
# Même coût que les mots de passe (§18.34) : il vaut 12 en service, et la suite
# de tests l'abaisse. Ce contexte l'ignorait, si bien que huit codes hachés à
# douze tours coûtaient trois secondes par test de double authentification —
# l'essentiel de ce qui restait après la première optimisation.
contexte_secours = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto",
                                bcrypt_sha256__rounds=config.BCRYPT_ROUNDS)

# Alphabet base32 sans padding : ce que lisent les applications
# d'authentification, et ce qu'un humain peut recopier à la main.
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def nouveau_secret(longueur: int = 32) -> str:
    """Une graine base32 tirée au sort, à partager avec l'application."""
    return "".join(secrets.choice(ALPHABET) for _ in range(longueur))


def _cle(secret: str) -> bytes:
    """Décode la graine base32, en tolérant l'absence de remplissage."""
    normalise = secret.strip().replace(" ", "").upper()
    remplissage = "=" * (-len(normalise) % 8)
    return base64.b32decode(normalise + remplissage, casefold=True)


def code(secret: str, moment: Optional[float] = None, decalage_pas: int = 0) -> str:
    """Le code attendu pour ce secret à cet instant."""
    compteur = int((moment if moment is not None else time.time()) // PAS_SECONDES) + decalage_pas
    empreinte = hmac.new(_cle(secret), struct.pack(">Q", compteur), hashlib.sha1).digest()
    # Troncature dynamique (RFC 4226 §5.3) : les quatre bits de poids faible du
    # dernier octet désignent où lire les quatre octets qui portent le code.
    depart = empreinte[-1] & 0x0F
    valeur = struct.unpack(">I", empreinte[depart:depart + 4])[0] & 0x7FFFFFFF
    return str(valeur % (10 ** NOMBRE_CHIFFRES)).zfill(NOMBRE_CHIFFRES)


def verifier(secret: str, propose: str, moment: Optional[float] = None) -> bool:
    """
    Vrai si le code proposé correspond, au pas près.

    La comparaison passe par `compare_digest` : comparer deux chaînes avec `==`
    s'arrête au premier caractère différent, et ce temps de réponse se mesure.
    """
    if not secret or not propose:
        return False
    propose = propose.strip().replace(" ", "")
    if not propose.isdigit() or len(propose) != NOMBRE_CHIFFRES:
        return False
    for decalage in range(-TOLERANCE_PAS, TOLERANCE_PAS + 1):
        if secrets.compare_digest(code(secret, moment, decalage), propose):
            return True
    return False


def uri_provisionnement(secret: str, compte: str, emetteur: str = "HomeGED") -> str:
    """
    L'URI `otpauth://` que lisent les applications d'authentification. C'est ce
    que contient le QR code ; il reste recopiable à la main si l'appareil photo
    n'est pas une option.
    """
    etiquette = quote(f"{emetteur}:{compte}", safe="")
    parametres = (f"secret={secret}&issuer={quote(emetteur, safe='')}"
                  f"&algorithm=SHA1&digits={NOMBRE_CHIFFRES}&period={PAS_SECONDES}")
    return f"otpauth://totp/{etiquette}?{parametres}"


def qr_data_uri(uri: str) -> str:
    """
    Le QR code de l'URI d'appairage, en SVG encodé en data URI.

    Rendu ainsi parce que la politique de contenu du site interdit les images
    venant d'ailleurs mais autorise `data:` — la page n'a donc rien à aller
    chercher. En SVG plutôt qu'en PNG : pas de dépendance graphique, et l'image
    reste nette à toute taille.

    Si la bibliothèque manque, on rend une chaîne vide plutôt qu'une erreur :
    l'appairage reste possible en recopiant le secret à la main, il serait
    absurde de bloquer la mise en place d'une double authentification faute
    d'avoir pu dessiner un carré.
    """
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:  # pragma: no cover - dépend de l'environnement
        return ""
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    tampon = io.BytesIO()
    image.save(tampon)
    return "data:image/svg+xml;base64," + base64.b64encode(tampon.getvalue()).decode()


def secret_lisible(secret: str) -> str:
    """La graine par groupes de quatre : on la recopie sans se perdre."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


# ------------------------------------------------------------
# Codes de secours
# ------------------------------------------------------------

def nouveaux_codes_secours() -> tuple[list[str], str]:
    """
    Rend les codes en clair (à montrer une seule fois) et leur forme stockable.

    Les deux ne se ressemblent pas volontairement : ce qui part en base ne
    permet pas de retrouver ce qui a été affiché.
    """
    clairs = [
        "-".join(
            "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
                    for _ in range(CARACTERES_PAR_GROUPE))
            for _ in range(GROUPES_CODE_SECOURS)
        )
        for _ in range(NOMBRE_CODES_SECOURS)
    ]
    return clairs, json.dumps([contexte_secours.hash(c) for c in clairs])


def consommer_code_secours(stockes: Optional[str], propose: str) -> Optional[str]:
    """
    Si le code proposé est l'un des codes de secours, rend la liste stockée
    privée de celui-ci ; sinon `None`.

    Un code de secours ne sert qu'une fois : c'est ce qui le rend acceptable
    comme équivalent d'un second facteur.
    """
    if not stockes or not propose:
        return None
    propose = propose.strip().upper().replace(" ", "")
    try:
        empreintes = json.loads(stockes)
    except (ValueError, TypeError):
        return None
    for empreinte in empreintes:
        try:
            valide = contexte_secours.verify(propose, empreinte)
        except ValueError:
            valide = False
        if valide:
            return json.dumps([e for e in empreintes if e != empreinte])
    return None


def nombre_codes_secours(stockes: Optional[str]) -> int:
    """Combien de codes de secours restent utilisables."""
    if not stockes:
        return 0
    try:
        return len(json.loads(stockes))
    except (ValueError, TypeError):
        return 0
