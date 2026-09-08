"""
Le mode développeur (§21.14).

Les scripts Python sont la porte de sortie universelle d'EzGED : ce qu'aucun
écran ne prévoit et qu'on ne va pas coder pour un foyer — recouper deux listes,
sortir un décompte, préparer un fichier pour un tiers. Ils étaient écartés
d'emblée de ce projet ; l'utilisateur les autorise **sous condition d'un mode
développeur activé en administration, qui énonce les problèmes que cela pose**.

Ce que cela pose, et qui est dit à l'écran avant d'armer l'interrupteur :

* un script est du **code exécuté par le service**. Qui peut en écrire un peut
  faire ce que le service peut faire ;
* il **voit ce qu'on lui donne**, et ce qu'on lui donne sort de la GED : un
  script est un moyen d'extraire des données ;
* une erreur dedans est une erreur **chez vous** — pas un défaut du logiciel.

D'où quatre bornes, qui sont tout ce module :

1. **un seul point d'entrée**, `executer(contexte)`, et un contexte explicite.
   Le script ne va pas se servir : on lui donne, et ce qu'on lui donne est
   visible à l'écran avant de lancer ;
2. **un processus séparé, borné en durée**. Une boucle infinie ne doit pas
   emporter le serveur avec elle ;
3. **aucun accès à la base**. Le script rend un texte, que quelqu'un lit ; la GED
   ne se modifie pas dans le dos de ses écrans. C'est la borne qui coûte le plus
   en confort, et c'est celle qui rend le reste acceptable ;
4. **tout est journalisé** : qui a écrit, qui a lancé, ce qui est sorti.

Ce qui n'est **pas** borné, et qu'il faut savoir : l'accès réseau. Le bloquer
demanderait un bac à sable qui n'a pas sa place dans une application de foyer.
C'est l'une des raisons pour lesquelles ce mode se déclare au lieu d'exister.
"""
import json
import logging
import subprocess
import sys
import textwrap
import time
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Une minute : de quoi recouper quelques milliers de lignes, pas de quoi tenir un
# processus indéfiniment. Un script qui demande plus n'a pas sa place ici.
DUREE_MAX = 60

# Ce qui remonte à l'écran : au-delà, on ne lit plus, on scrolle.
SORTIE_MAX = 200_000


class ScriptRefuse(Exception):
    """Le script ne peut pas être exécuté. Le message est destiné à l'écran."""


def mode_actif(session: Session) -> bool:
    """Le mode est-il armé ? Défaut : non, et c'est le seul défaut acceptable."""
    from . import reglages

    return reglages.booleen(session, "mode_developpeur")


def exiger_mode_actif(session: Session) -> None:
    if not mode_actif(session):
        raise ScriptRefuse(
            "Le mode développeur n'est pas activé. Il s'arme depuis les réglages, "
            "après lecture de ce qu'il implique.")


def valider(code: str) -> str:
    """
    Le script doit être lisible par Python et déclarer son point d'entrée.

    Vérifié à l'enregistrement plutôt qu'au lancement : une faute de frappe se
    corrige au moment où on l'écrit, pas trois semaines plus tard devant une
    trace d'exécution.
    """
    texte = (code or "").strip()
    if not texte:
        raise ScriptRefuse("Un script vide n'a rien à exécuter.")
    try:
        compile(texte, "<script>", "exec")
    except SyntaxError as erreur:
        raise ScriptRefuse(f"Python n'arrive pas à lire ce script : {erreur}")
    if "def executer" not in texte:
        raise ScriptRefuse(
            "Le script doit définir « def executer(contexte): » — c'est le seul point "
            "d'entrée, et ce qui garantit qu'on sait quoi lui donner.")
    return texte


# Le lanceur, écrit ici et non dans un fichier : il doit rester sous les yeux de
# qui lit ce module. Il lit le contexte sur l'entrée standard, appelle le point
# d'entrée, et rend le résultat en JSON sur la sortie standard.
LANCEUR = textwrap.dedent('''
    import json, sys, traceback

    contexte = json.load(sys.stdin)
    espace = {}
    try:
        exec(compile(contexte.pop("__code__"), "<script>", "exec"), espace)
        point = espace.get("executer")
        if point is None:
            raise RuntimeError("Le script ne definit pas executer(contexte).")
        resultat = point(contexte)
        sys.stdout.write(json.dumps({"ok": True, "resultat": resultat},
                                    ensure_ascii=False, default=str))
    except Exception:
        sys.stdout.write(json.dumps({"ok": False,
                                     "erreur": traceback.format_exc(limit=8)},
                                    ensure_ascii=False))
''')


def executer(code: str, contexte: Optional[dict] = None,
             duree_max: int = DUREE_MAX) -> dict:
    """
    Exécute le script dans un processus séparé et rend
    `{reussite, sortie, erreur, duree_ms}`.

    Le contexte part en JSON sur l'entrée standard : c'est ce qui garantit qu'il
    ne passe **que** ce qu'on a décidé de passer. Aucune session, aucun chemin,
    aucun jeton — un script ne peut pas se servir tout seul.
    """
    charge = dict(contexte or {})
    charge["__code__"] = valider(code)
    debut = time.monotonic()
    try:
        termine = subprocess.run(
            [sys.executable, "-I", "-c", LANCEUR],
            input=json.dumps(charge, ensure_ascii=False, default=str),
            capture_output=True, text=True, timeout=duree_max,
            # Un environnement nu : ni identifiants de base, ni clé, ni chemin de
            # stockage. Ce que le script ne reçoit pas, il ne peut pas le lire.
            env={"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return {"reussite": False, "sortie": "",
                "erreur": f"Le script a dépassé {duree_max} secondes et a été arrêté.",
                "duree_ms": int((time.monotonic() - debut) * 1000)}
    except Exception as erreur:      # noqa: BLE001 — on rend l'échec, on ne le masque pas
        return {"reussite": False, "sortie": "", "erreur": str(erreur),
                "duree_ms": int((time.monotonic() - debut) * 1000)}

    duree = int((time.monotonic() - debut) * 1000)
    try:
        reponse = json.loads(termine.stdout or "{}")
    except ValueError:
        return {"reussite": False, "sortie": (termine.stdout or "")[:SORTIE_MAX],
                "erreur": "Le script n'a rien rendu de lisible.", "duree_ms": duree}

    if not reponse.get("ok"):
        return {"reussite": False, "sortie": (termine.stderr or "")[:SORTIE_MAX],
                "erreur": (reponse.get("erreur") or "Échec sans message.")[:SORTIE_MAX],
                "duree_ms": duree}

    resultat = reponse.get("resultat")
    if not isinstance(resultat, str):
        resultat = json.dumps(resultat, ensure_ascii=False, indent=2, default=str)
    return {"reussite": True, "sortie": resultat[:SORTIE_MAX], "erreur": None,
            "duree_ms": duree}
