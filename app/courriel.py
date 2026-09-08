"""
L'envoi de courriel (§21.10).

Les rappels du §21.9 n'existaient que dans l'application : encore fallait-il
l'ouvrir. Un rappel de contrôle technique doit venir vous chercher — c'est la
décision prise par l'utilisateur : « interface **et** courriel ».

Trois règles, et elles tiennent au fait qu'un courriel traverse des machines qui
ne sont pas les nôtres :

  * **jamais le contenu d'un document** dans le message : un titre, un lien vers
    la fiche, rien de plus. Ce qui part chez un hébergeur de messagerie n'est plus
    à nous ;
  * **un résumé espacé, pas un message par événement**. Les paliers d'EzGED
    (5 min, 15 min, 1 h, 24 h, 1 semaine, puis on cesse) évitent la seule chose
    qui tue un système de rappels : qu'on cesse de les lire ;
  * **le mot de passe ne se relit pas**. Il se règle, il s'oublie ; l'écran montre
    qu'il existe (cf. `app/reglages.py`, type « secret »).

Aucune dépendance ajoutée : `smtplib` est dans la bibliothèque standard.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from sqlalchemy.orm import Session

from . import reglages

log = logging.getLogger("homeged.courriel")

# Les paliers d'EzGED, en minutes. Après le dernier, on cesse : quelqu'un qui n'a
# pas réagi en une semaine ne réagira pas au huitième message, et l'insistance
# fait basculer les rappels dans le bruit — ou dans les indésirables.
PALIERS = (5, 15, 60, 24 * 60, 7 * 24 * 60)

DELAI_CONNEXION = 15


class EnvoiImpossible(Exception):
    """Refus destiné à l'écran : il dit ce qui manque, pas seulement que c'est non."""


def configure(session: Session) -> bool:
    """Un serveur et un expéditeur suffisent : le reste a des valeurs sensées."""
    return bool(reglages.lire(session, "smtp_serveur").strip()
                and reglages.lire(session, "smtp_expediteur").strip())


def actif(session: Session) -> bool:
    return reglages.booleen(session, "courriel_actif") and configure(session)


def _connexion(session: Session):
    serveur = reglages.lire(session, "smtp_serveur").strip()
    port = reglages.entier(session, "smtp_port")
    securite = reglages.lire(session, "smtp_securite").strip()

    if securite == "ssl":
        connexion = smtplib.SMTP_SSL(serveur, port, timeout=DELAI_CONNEXION,
                                     context=ssl.create_default_context())
    else:
        connexion = smtplib.SMTP(serveur, port, timeout=DELAI_CONNEXION)
        if securite == "starttls":
            connexion.starttls(context=ssl.create_default_context())

    compte = reglages.lire(session, "smtp_compte").strip()
    mot_de_passe = reglages.lire(session, "smtp_mot_de_passe")
    if compte:
        connexion.login(compte, mot_de_passe)
    return connexion


def envoyer(session: Session, destinataires: list[str], sujet: str, texte: str) -> int:
    """
    Envoie un message. Rend le nombre de destinataires servis.

    Les erreurs remontent en `EnvoiImpossible` avec le message du serveur : « ça
    n'a pas marché » n'aide personne à régler un SMTP, et c'est précisément le
    moment où l'on a besoin de savoir si c'est le port, le mot de passe ou le
    certificat.
    """
    adresses = [a.strip() for a in destinataires if a and a.strip()]
    if not adresses:
        return 0
    if not configure(session):
        raise EnvoiImpossible("Le serveur d'envoi n'est pas réglé : indiquez au moins "
                              "un serveur SMTP et une adresse d'expédition.")

    message = EmailMessage()
    message["From"] = reglages.lire(session, "smtp_expediteur").strip()
    message["To"] = ", ".join(adresses)
    message["Subject"] = sujet
    message.set_content(texte)

    try:
        with _connexion(session) as connexion:
            connexion.send_message(message)
    except smtplib.SMTPAuthenticationError as erreur:
        raise EnvoiImpossible(f"Le serveur a refusé le compte : {erreur.smtp_error.decode(errors='replace') if erreur.smtp_error else erreur}")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as erreur:
        raise EnvoiImpossible(f"Envoi impossible : {erreur}")
    return len(adresses)


def essayer(session: Session, adresse: str) -> int:
    """
    Un envoi d'essai depuis l'écran de réglage.

    Sans lui, on ne saurait jamais si le SMTP est correctement réglé avant la
    première échéance — c'est-à-dire au pire moment.
    """
    return envoyer(
        session, [adresse],
        "HomeGED — essai d'envoi",
        "Ce message confirme que HomeGED sait joindre votre boîte.\n\n"
        "Il a été demandé depuis l'écran de réglage du courriel. Si vous ne l'attendiez "
        "pas, quelqu'un règle l'application en ce moment.\n")


def lien_vers(session: Session, chemin: str = "") -> str:
    """
    L'adresse à laquelle renvoyer. Vide si le foyer ne l'a pas déclarée : mieux
    vaut un courriel sans lien qu'un lien vers `localhost`, qui ne mène nulle part
    depuis un téléphone.
    """
    base = reglages.lire(session, "adresse_publique").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/{chemin.lstrip('/')}" if chemin else base


def palier_suivant(palier: int) -> Optional[int]:
    """Le délai du palier suivant, en minutes. `None` quand on cesse d'insister."""
    return PALIERS[palier] if 0 <= palier < len(PALIERS) else None


def resumer(session: Session, forcer: bool = False) -> dict:
    """
    Envoie à chacun le résumé de ce qu'il n'a pas lu, en respectant son palier.

    C'est la boucle appelée par le serveur de travaux. Elle ne fait rien tant que
    le foyer n'a pas activé le courriel : un rappel qui part sans qu'on l'ait
    demandé est pire qu'un rappel qui manque.

    `forcer` sert à l'essai depuis l'écran : il ignore le délai du palier, pas le
    reste — on veut savoir si le message part, pas court-circuiter la règle.
    """
    from datetime import datetime, timedelta

    from . import notifications
    from .db import Utilisateur

    if not actif(session):
        return {"envoyes": 0, "raison": "courriel inactif ou serveur non réglé"}

    envoyes = 0
    for user in session.query(Utilisateur).filter(Utilisateur.actif.is_(True)):
        if not user.courriel_rappels or not (user.email or "").strip():
            continue

        attente = palier_suivant(user.palier_courriel or 0)
        if attente is None:
            continue      # on a cessé d'insister : il faut lire pour repartir

        lignes = notifications.resume_a_envoyer(session, user)
        if not lignes:
            continue

        if not forcer:
            depuis = user.date_dernier_courriel
            if depuis and datetime.now() - depuis < timedelta(minutes=attente):
                continue
            # La plus ancienne doit avoir atteint le délai du palier : sinon on
            # écrirait à quelqu'un pour un rappel posé il y a dix secondes.
            plus_ancienne = lignes[0].date_creation or datetime.now()
            if datetime.now() - plus_ancienne < timedelta(minutes=PALIERS[0]):
                continue

        lien = lien_vers(session)
        corps = ["Voici ce qui vous attend dans HomeGED :", ""]
        corps += [f"— {n.titre}" + (f"\\n  {n.message}" if n.message else "") for n in lignes]
        corps += ["", f"Ouvrir HomeGED : {lien}" if lien else
                  "Ouvrez HomeGED pour les consulter.",
                  "", "Ce résumé s'espace tant que personne ne les lit, puis cesse."]

        try:
            envoyer(session, [user.email],
                    f"HomeGED — {len(lignes)} rappel(s) en attente", "\\n".join(corps))
        except EnvoiImpossible as erreur:
            # On n'avance pas le palier : le problème vient de nous, pas du
            # destinataire, et le prochain passage réessaiera.
            log.warning("Résumé non envoyé à %s : %s", user.email, erreur)
            continue

        notifications.marquer_envoyees(session, lignes)
        user.palier_courriel = (user.palier_courriel or 0) + 1
        user.date_dernier_courriel = datetime.now()
        envoyes += 1

    return {"envoyes": envoyes}
