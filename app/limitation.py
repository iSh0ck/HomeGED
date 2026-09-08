"""
Limitation des tentatives de connexion.

Rien n'empêchait jusqu'ici d'essayer des mots de passe en boucle sur
`/auth/login`. Le compte est protégé par un hachage coûteux, mais cela ne
suffit pas : un attaquant patient finit par trouver un mot de passe faible.

Le décompte est tenu **en mémoire du processus**, sans dépendance ni écriture en
base : sur une installation domestique à un seul conteneur d'API, cela répond au
besoin. Conséquence assumée : un redémarrage de l'API remet les compteurs à
zéro — ce qui donne au passage un moyen simple de se débloquer soi-même. La
trace durable, elle, est dans le journal d'audit.

Deux clés sont suivies pour chaque tentative :
  - `(adresse, identifiant)` : freine l'acharnement sur un compte précis ;
  - `(adresse)` : freine le balayage de nombreux comptes depuis la même source.
Le verrouillage de l'une ou l'autre suffit à refuser la tentative.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class Etat:
    """Ce que l'on sait d'une source de tentatives, pour l'afficher et agir dessus."""
    cle: str
    adresse: str
    identifiant: Optional[str]      # None pour une clé qui ne suit que l'adresse
    tentatives: int = 0             # cumul depuis la dernière réussite ou expiration
    horodatages: list = field(default_factory=list)  # échecs dans la fenêtre courante
    premiere: float = 0.0
    derniere: float = 0.0
    verrou_jusqu_a: Optional[float] = None


class LimiteurTentatives:
    """
    Compteur à fenêtre glissante avec verrouillage temporaire.

    Au-delà de `max_tentatives` échecs dans `fenetre` secondes, la clé est
    verrouillée pendant `verrouillage` secondes. Une connexion réussie efface
    l'ardoise : un utilisateur légitime qui se trompe puis se rattrape n'est
    jamais gêné.
    """

    def __init__(self, max_tentatives: int, fenetre: float, verrouillage: float):
        self.max_tentatives = max_tentatives
        self.fenetre = fenetre
        self.verrouillage = verrouillage
        self._etats: dict[str, Etat] = {}
        self._mutex = threading.Lock()

    def _nettoyer(self, maintenant: float) -> None:
        """
        Écarte les entrées périmées : verrou expiré **et** plus aucun échec dans
        la fenêtre. Sans cela la mémoire croîtrait indéfiniment sous une attaque
        qui change d'adresse à chaque essai.
        """
        for cle, etat in list(self._etats.items()):
            if etat.verrou_jusqu_a and etat.verrou_jusqu_a > maintenant:
                continue
            etat.verrou_jusqu_a = None
            etat.horodatages = [t for t in etat.horodatages if maintenant - t < self.fenetre]
            if not etat.horodatages:
                self._etats.pop(cle, None)

    def attente_requise(self, cles: Iterable[str]) -> Optional[int]:
        """Secondes restantes avant de pouvoir réessayer, ou None si la voie est libre."""
        maintenant = time.time()
        with self._mutex:
            self._nettoyer(maintenant)
            restants = [
                self._etats[c].verrou_jusqu_a - maintenant
                for c in cles
                if c in self._etats and self._etats[c].verrou_jusqu_a
            ]
        return int(max(restants)) + 1 if restants else None

    def echec(self, cles: Iterable[str], adresse: str = "", identifiant: str = "") -> bool:
        """Enregistre un échec. Renvoie True si cette tentative déclenche un verrouillage."""
        maintenant = time.time()
        declenche = False
        with self._mutex:
            self._nettoyer(maintenant)
            for cle in cles:
                etat = self._etats.get(cle)
                if etat is None:
                    etat = Etat(
                        cle=cle, adresse=adresse or _adresse_depuis_cle(cle),
                        identifiant=(identifiant or None) if cle.startswith("compte:") else None,
                        premiere=maintenant,
                    )
                    self._etats[cle] = etat
                etat.horodatages.append(maintenant)
                etat.tentatives += 1
                etat.derniere = maintenant
                if identifiant and cle.startswith("compte:"):
                    etat.identifiant = identifiant
                if len(etat.horodatages) >= self.max_tentatives and not etat.verrou_jusqu_a:
                    etat.verrou_jusqu_a = maintenant + self.verrouillage
                    etat.horodatages.clear()
                    declenche = True
        return declenche

    def succes(self, cles: Iterable[str]) -> None:
        with self._mutex:
            for cle in cles:
                self._etats.pop(cle, None)

    def etats(self) -> list[dict]:
        """
        Sources actuellement suivies, verrouillées d'abord. Sert à l'écran
        d'administration : on y voit ce qui est bloqué, et ce qui approche du seuil.
        """
        maintenant = time.time()
        with self._mutex:
            self._nettoyer(maintenant)
            resultat = [{
                "cle": e.cle,
                "adresse": e.adresse,
                "identifiant": e.identifiant,
                "portee": "compte" if e.cle.startswith("compte:") else "adresse",
                "tentatives": e.tentatives,
                "tentatives_dans_la_fenetre": len(e.horodatages),
                "premiere": e.premiere,
                "derniere": e.derniere,
                "verrouille": bool(e.verrou_jusqu_a),
                "secondes_restantes": int(e.verrou_jusqu_a - maintenant) + 1 if e.verrou_jusqu_a else None,
            } for e in self._etats.values()]
        resultat.sort(key=lambda e: (not e["verrouille"], -e["derniere"]))
        return resultat

    def deverrouiller(self, cle: str) -> bool:
        """Lève le verrou d'une source et efface son décompte. True si elle existait."""
        with self._mutex:
            return self._etats.pop(cle, None) is not None

    def tout_deverrouiller(self) -> int:
        with self._mutex:
            nombre = len(self._etats)
            self._etats.clear()
            return nombre

    def reinitialiser(self) -> None:
        """Remise à zéro complète — utile aux tests."""
        self.tout_deverrouiller()


def _adresse_depuis_cle(cle: str) -> str:
    reste = cle.split(":", 1)[1] if ":" in cle else cle
    return reste.split("|", 1)[0]


def adresse_client(request) -> str:
    """
    Adresse de l'appelant. Derrière le proxy nginx, toutes les requêtes
    proviennent du réseau Docker : on retient donc `X-Real-IP`, que la
    configuration nginx renseigne, et l'adresse de connexion à défaut.
    """
    entete = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    if entete:
        return entete.split(",")[0].strip()
    return request.client.host if request.client else "inconnu"


def cles(adresse: str, identifiant: str) -> list[str]:
    return [f"compte:{adresse}|{(identifiant or '').strip().lower()}", f"adresse:{adresse}"]
