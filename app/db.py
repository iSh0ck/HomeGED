from sqlalchemy import (
    create_engine, Column, BigInteger, Integer, String, Text, DateTime, Date, Boolean,
    Enum, ForeignKey, Index, Table, UniqueConstraint, func, text
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from . import config

engine = create_engine(config.SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def attendre_base(tentatives: int = 15, delai_secondes: float = 2.0) -> None:
    """
    Bloque jusqu'à ce que MariaDB accepte les connexions, ou lève l'erreur
    d'origine après épuisement des tentatives. Utile au démarrage (le temps
    que le conteneur `db` finisse son initialisation) et après un redémarrage
    de la base en cours de vie du conteneur.
    """
    import logging
    import time

    log = logging.getLogger(__name__)
    derniere_erreur = None
    for tentative in range(1, tentatives + 1):
        try:
            with engine.connect():
                return
        except OperationalError as e:
            derniere_erreur = e
            log.warning(
                f"Base de données indisponible (tentative {tentative}/{tentatives}), "
                f"nouvelle tentative dans {delai_secondes}s..."
            )
            time.sleep(delai_secondes)
    raise derniere_erreur


utilisateur_roles = Table(
    "sys_utilisateur_roles", Base.metadata,
    Column("utilisateur_id", Integer, ForeignKey("sys_utilisateurs.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("sys_roles.id", ondelete="CASCADE"), primary_key=True),
)


class Categorie(Base):
    __tablename__ = "sys_categories"
    id = Column(Integer, primary_key=True)
    nom = Column(String(150), nullable=False)
    # Dossier ou type de document (§19.1). Un dossier organise et ne porte aucun
    # document ; un type est une feuille qui porte les documents et tout ce qui
    # les décrit. La distinction évite de proposer des réglages sans effet.
    nature = Column(String(10), nullable=False, server_default=text("'type'"), default="type")
    # Dossier de dépôt sous `ocr_wait/`, propre à ce type (§19.2). Vide pour un
    # dossier de classement, qui ne reçoit aucun document, et pour une fiche
    # simple, où l'on dépose à la main et nulle part ailleurs (§22.1).
    dossier_depot = Column(String(64), unique=True)
    # Table à laquelle s'adossait une « fiche de liaison » (§19.17), abandonnée au
    # §22.1 : plus aucune catégorie ne s'adosse à une table. La colonne survit le
    # temps qu'on soit sûr de n'en plus rien vouloir ; plus rien ne l'écrit.
    parent_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="SET NULL"))
    # Place dans la navigation. Depuis le §19.3, c'est le seul ordre que porte une
    # catégorie : le classement ne se devine plus, il se dépose.
    ordre = Column(Integer, nullable=False, server_default=text("100"), default=100)
    # Tri par défaut du registre pour cette catégorie (§18.49). Vide : hérité du
    # parent, puis du réglage général du foyer. Même vocabulaire que les filtres.
    tri_champ = Column(String(100))
    tri_sens = Column(String(4))
    # Les colonnes retirées du tableau se voient-elles quand même sur la fiche ?
    # Décision d'administration, prise par type : masquer une colonne d'un tableau
    # qu'on parcourt n'est pas la même chose que la cacher sur la fiche (§19.21).
    fiche_champs_masques = Column(Boolean, nullable=False, server_default=text("FALSE"),
                                  default=False)
    documents = relationship("Document", back_populates="categorie")
    # Remonter l'arborescence depuis une catégorie : l'export en a besoin pour
    # reconstruire le chemin de dossiers d'un document (§17.30).
    parent = relationship("Categorie", remote_side=[id])


# `usr_emetteurs` n'a plus de modèle à elle (§21.12) : c'est une table du foyer
# comme les véhicules ou les membres, tenue par `app/base_donnees.py` et désignée
# par une métadonnée `usr_emetteurs:<id>`. Lui garder une classe, une colonne sur
# les documents et un champ de filtre en faisait une exception : deux mécanismes
# pour la même idée, dont un seul savait déduire, replier et restreindre.


class ProfilExtraction(Base):
    """
    Jeu de règles d'extraction, propre à un type de document (§19.6).

    Une seule liste de règles pour tous les documents grossissait à chaque
    émetteur — EDF n'écrit pas ses numéros comme Orange — et chaque règle ajoutée
    devenait un risque pour les autres. Un jeu appartient à un type et ne
    s'applique qu'à lui ; sa `reconnaissance`, cherchée dans le texte, dit « c'est
    bien de celui-là qu'il s'agit ».

    Ordre d'application : parmi les jeux du type, par priorité croissante, le
    premier reconnu l'emporte et est **seul** appliqué. Aucun : le jeu générique.
    On sait ainsi toujours quel jeu a produit une valeur.
    """
    __tablename__ = "sys_profils_extraction"
    id = Column(Integer, primary_key=True)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"),
                          nullable=False)
    nom = Column(String(150), nullable=False)
    reconnaissance = Column(String(500))
    # Plus d'émetteur posé par le jeu (§21.12) : c'est la **déduction** du champ
    # attendu qui s'en charge désormais, et elle lit le document au lieu de faire
    # confiance au jeu reconnu.
    generique = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    actif = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)
    priorite = Column(Integer, nullable=False, server_default=text("100"), default=100)

    categorie = relationship("Categorie")
    regles = relationship("RegleExtraction", back_populates="profil",
                          cascade="all, delete-orphan")


class RegleExtraction(Base):
    __tablename__ = "sys_regles_extraction"
    id = Column(Integer, primary_key=True)
    # Jeu auquel la règle appartient (§19.6). Une règle sans jeu ne s'applique à
    # rien : c'est le moyen de n'avoir jamais de règle qui vaut « pour tout ».
    profil_id = Column(Integer, ForeignKey("sys_profils_extraction.id", ondelete="CASCADE"))
    profil = relationship("ProfilExtraction", back_populates="regles")
    nom = Column(String(150), nullable=False)
    champ_cible = Column(String(100), nullable=False)
    # Facultatif depuis §18.35 : une règle peut s'appuyer sur une fonction prête
    # à l'emploi plutôt que sur une expression écrite à la main.
    pattern = Column(String(500))
    fonction = Column(String(40))
    # Valeur dont une fonction a besoin (§21.4) : les jours d'une échéance, le
    # séparateur d'une concaténation. Sans elle, il aurait fallu une fonction par
    # valeur possible — c'est-à-dire coder en dur ce qui doit se régler.
    parametre = Column(String(100))
    # `server_default` et pas seulement `default=` : sans clause DEFAULT en base,
    # une insertion en SQL brut laisse la colonne à NULL, et une règle dont `actif`
    # vaut NULL est écartée par le moteur — elle ne s'applique jamais (migration 012).
    type_champ = Column(Enum("texte", "date", "montant", "entier"), default="texte")
    actif = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)
    priorite = Column(Integer, default=100)
    # Pas de restriction par émetteur (§18.43) : il n'est pas connu au dépôt, une
    # telle règle ne se serait donc jamais appliquée au moment où elle sert.


class Document(Base):
    __tablename__ = "sys_documents"
    id = Column(Integer, primary_key=True)
    nom_fichier = Column(String(255), nullable=False)
    # Facultatifs depuis le §22.7 : un document est l'unité de **ce que l'on
    # sait**, et le fichier une pièce parmi d'autres (§22.2) — éventuellement
    # aucune. Une entrée saisie à la main dans une fiche simple n'a pas toujours
    # de papier : un contrat verbal, le code d'un cadenas.
    chemin_stockage = Column(String(500))
    # empreinte du fichier **reçu**, pas de l'archive : elle sert à refuser un
    # doublon à l'import et ne bouge pas si l'archive est recompressée (§17.8)
    hash_sha256 = Column(String(64), unique=True)
    # D'où vient ce document (§22.68) : `True` s'il a été glissé dans
    # l'application — quelqu'un l'a vu et lui a dit son type —, `False` s'il est
    # arrivé seul par le dossier surveillé. `None` quand on ne sait pas : la
    # tâche qui portait la trace a été purgée avant qu'on la note, et l'inventer
    # serait pire que se taire.
    depot_manuel = Column(Boolean)
    taille_octets = Column(BigInteger)
    date_compression = Column(DateTime)
    date_import = Column(DateTime, server_default=func.now())
    date_document = Column(Date)
    # LONGTEXT (et non TEXT) : le texte océrisé d'un document dépasse vite 64 Ko.
    texte_ocr = Column(LONGTEXT)
    statut = Column(Enum("en_attente", "ocr_en_cours", "traite", "erreur", "incomplet"), default="en_attente")
    # ondelete explicite : sans lui, la contrainte prend RESTRICT et supprimer une
    # catégorie encore utilisée échoue (cf. migration 013)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="SET NULL"))

    # L'état de conformité, **rangé** et non recalculé (§22.41) : « ce document
    # a-t-il ses champs obligatoires ? » se lisait en interrogeant tout le
    # registre à chaque page — 311 ms pour compter vingt mille documents, contre
    # 6 ms ici. Écrit à la fin du traitement, après une correction à la main, et
    # par un recalcul ciblé quand les champs attendus d'une catégorie changent.
    conforme = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)

    # Corbeille (§21.1). Un document supprimé est **daté**, pas effacé : il garde
    # sa place, ses métadonnées, ses versions et son fichier, et se restaure
    # exactement là où il était. `date_suppression` vide = document vivant, et
    # c'est le seul critère — toutes les listes le consultent.
    date_suppression = Column(DateTime)
    # Qui l'a jeté : c'est ce qui donne à chacun sa corbeille. Le compte peut
    # disparaître ensuite ; le document reste en corbeille et l'administration
    # le retrouve.
    supprime_par_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    # Supprimé une seconde fois, depuis sa propre corbeille : il sort de la vue
    # de son auteur et n'existe plus que pour l'administration.
    corbeille_masquee = Column(Boolean, nullable=False, server_default=text("FALSE"),
                               default=False)

    # Contrôle d'intégrité (§21.3). `empreinte_archive` est celle du fichier
    # **archivé** : `hash_sha256` porte celle du fichier reçu, et les deux
    # diffèrent dès qu'un document est océrisé ou compressé. Comparer l'archive au
    # fichier reçu signalerait une altération partout, donc nulle part.
    empreinte_archive = Column(String(64))
    date_controle = Column(DateTime)
    integrite = Column(String(20))

    # Le modèle doit décrire le schéma réel : `create_all()` peut créer ces
    # tables sur une base vierge, et un index manquant ici casse la recherche
    # plein texte (MATCH ... AGAINST dans app/api.py).
    __table_args__ = (
        Index("ft_texte_ocr", "texte_ocr", mysql_prefix="FULLTEXT"),
        Index("idx_documents_date_import", "date_import"),
        Index("idx_documents_suppression", "date_suppression"),
        Index("idx_documents_controle", "date_controle"),
        Index("idx_documents_conforme", "conforme"),
    )

    categorie = relationship("Categorie", back_populates="documents")
    metadonnees = relationship("Metadonnee", back_populates="document", cascade="all, delete-orphan")
    supprime_par = relationship("Utilisateur", foreign_keys=[supprime_par_id])
    versions = relationship("VersionDocument", back_populates="document",
                            cascade="all, delete-orphan",
                            order_by="VersionDocument.date_depot.desc()")
    pieces = relationship("PieceDocument", back_populates="document",
                          cascade="all, delete-orphan",
                          order_by="PieceDocument.ordre, PieceDocument.id")


class PieceDocument(Base):
    """
    Un des fichiers que porte un document (§22.2).

    Un document **était** un fichier : réunir une facture, sa garantie et le bon
    de livraison demandait trois documents et un lien entre eux — trois fiches à
    remplir pour un seul achat. Une fiche porte désormais N fichiers, comme le
    « docpak » d'EzGED, et les champs sont remplis une fois.

    La **principale** est celle qu'on voit partout ailleurs : son fichier est
    celui que le registre ouvre et que la miniature montre. Les colonnes du
    document en sont le reflet, tenu à jour par `app/pieces.py`.

    Une pièce n'est pas une version : la version est le **même papier redéposé**
    (§18.36), la pièce est un **autre papier du même dossier**. Chaque pièce a
    d'ailleurs ses propres versions, puisque c'est le fichier qu'on rescanne.
    """
    __tablename__ = "sys_pieces_document"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                         nullable=False)
    nom_fichier = Column(String(255), nullable=False)
    chemin_stockage = Column(String(500), nullable=False)
    # Empreinte du fichier **reçu** : c'est elle qui reconnaît un dépôt déjà
    # connu, quelle que soit la pièce ou le document où il a atterri.
    hash_sha256 = Column(String(64), nullable=False, unique=True)
    taille_octets = Column(BigInteger)
    # Le texte de cette pièce-là ; celui du document est leur concaténation, et
    # c'est lui que porte l'index plein texte.
    texte_ocr = Column(LONGTEXT)
    ordre = Column(Integer, nullable=False, server_default=text("1"), default=1)
    principale = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    date_ajout = Column(DateTime, server_default=func.now())
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    # Contrôle d'intégrité, pièce par pièce (§21.3, étendu au §22.2 bis) : une
    # garantie jointe s'abîme comme une facture, et personne ne l'ouvre pendant
    # des années. L'empreinte est celle de l'**archive**, pas du fichier reçu —
    # l'océrisation et la compression réécrivent ce dernier.
    empreinte_archive = Column(String(64))
    date_controle = Column(DateTime)
    integrite = Column(String(20))

    document = relationship("Document", back_populates="pieces")
    utilisateur = relationship("Utilisateur")

    __table_args__ = (Index("idx_piece_document", "document_id", "ordre"),
                      Index("idx_piece_controle", "date_controle"))


class Rattachement(Base):
    """
    Un lien posé **à la main** entre deux documents (§22.4).

    Le rapprochement par valeur partagée (§19.19) réunit ce qui désigne la même
    chose, sans qu'on ait rien à faire. Reste ce qui ne partage rien et se répond
    quand même : un contrat et son avenant, une facture et son litige. Seul
    quelqu'un qui les a lus le sait.

    Le couple est rangé à l'écriture — `document_a` porte toujours le plus petit
    identifiant : l'unicité est ainsi vraie dans les deux sens sans avoir à y
    penser à la lecture, et un lien ne peut pas être posé deux fois à l'envers.
    """
    __tablename__ = "sys_rattachements"
    id = Column(Integer, primary_key=True)
    document_a = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                        nullable=False)
    document_b = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                        nullable=False)
    # Ce que le lien veut dire, quand celui qui le pose sait le nommer.
    # Facultatif : un lien sans mot vaut mieux qu'un lien qu'on renonce à poser.
    libelle = Column(String(120))
    date_creation = Column(DateTime, server_default=func.now())
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))

    __table_args__ = (UniqueConstraint("document_a", "document_b", name="uq_rattachement"),)


class RattachementType(Base):
    """
    Ce que l'administration autorise à rattacher (§22.4).

    Tant que **rien** n'est déclaré, tout est permis : un réglage vide ne doit pas
    interdire une fonction, sans quoi personne ne comprendrait pourquoi le bouton
    refuse. Dès qu'une paire existe, elles seules le sont.
    """
    __tablename__ = "sys_rattachements_types"
    id = Column(Integer, primary_key=True)
    categorie_a = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"),
                         nullable=False)
    categorie_b = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"),
                         nullable=False)
    libelle = Column(String(120))

    __table_args__ = (UniqueConstraint("categorie_a", "categorie_b",
                                       name="uq_rattachement_type"),)


class VersionDocument(Base):
    """
    Un dépôt d'un document (§18.36).

    Une fiche ne change pas d'identité parce qu'on rescanne le papier : elle
    accumule des versions et pointe la courante. Chaque version garde son
    fichier, sa date et son empreinte — c'est cette dernière qui reconnaît un
    dépôt déjà connu, fût-il une ancienne version qu'on redépose par mégarde.
    """
    __tablename__ = "sys_versions_document"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                         nullable=False)
    hash_sha256 = Column(String(64), nullable=False, unique=True)
    chemin_stockage = Column(String(500), nullable=False)
    nom_fichier = Column(String(255), nullable=False)
    taille_octets = Column(BigInteger)
    date_depot = Column(DateTime, server_default=func.now())
    courante = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    # La pièce dont c'est un dépôt (§22.3). C'est le **fichier** qu'on rescanne,
    # donc la pièce : sans elle, redéposer la garantie remplacerait la facture.
    piece_id = Column(Integer, ForeignKey("sys_pieces_document.id", ondelete="CASCADE"))

    document = relationship("Document", back_populates="versions")
    utilisateur = relationship("Utilisateur")


class Metadonnee(Base):
    __tablename__ = "sys_metadonnees"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"), nullable=False)
    regle_id = Column(Integer, ForeignKey("sys_regles_extraction.id", ondelete="SET NULL"))
    cle = Column(String(100), nullable=False)
    valeur = Column(String(500))

    document = relationship("Document", back_populates="metadonnees")

    __table_args__ = (UniqueConstraint("document_id", "cle", name="uq_doc_cle"),)


# ------------------------------------------------------------
# Authentification / droits
# ------------------------------------------------------------

class Utilisateur(Base):
    __tablename__ = "sys_utilisateurs"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    # Nom et prénom : exigés des comptes ordinaires, facultatifs pour un
    # administrateur (§17.20). `nom_affiche` en donne la lecture.
    nom = Column(String(150))
    prenom = Column(String(100))
    mot_de_passe_hash = Column(String(255), nullable=False)
    est_admin = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    actif = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)
    date_creation = Column(DateTime, server_default=func.now())

    # Mode d'ouverture d'un document (§19.20). Personnel et non de foyer : il
    # dépend de la machine et de la liaison de celui qui regarde. Sur un portable
    # en 4G, la miniature change tout ; sur un poste fixe, non. Elle ouvre par
    # défaut : c'est le mode qui coûte le moins à afficher (§19.21).
    # Lignes par page du registre, pour ce compte (§22.44). NULL : on suit le
    # réglage du foyer — le nombre dépend de l'écran, pas du foyer.
    lignes_par_page = Column(Integer)
    # Palette et langue de ce compte (§22.50, §22.51). NULL : celles du foyer —
    # un thème dépend de l'écran et de la lumière, une langue dépend de qui lit.
    theme = Column(String(32))
    langue = Column(String(32))
    mode_apercu = Column(String(20), nullable=False, server_default=text("'miniature'"),
                         default="miniature")
    # Rappels par courriel (§21.10). Chacun peut ne pas vouloir être dérangé sans
    # perdre les rappels dans l'application. Les paliers espacent les relances de
    # qui ne réagit pas : 5 min, 15 min, 1 h, 24 h, 1 semaine, puis on cesse.
    courriel_rappels = Column(Boolean, nullable=False, server_default=text("TRUE"),
                              default=True)
    palier_courriel = Column(Integer, nullable=False, server_default=text("0"), default=0)
    date_dernier_courriel = Column(DateTime)

    # Double authentification (cf. db/migrations/020). Le secret n'est renvoyé
    # par l'API que le temps de l'appairage ; ensuite il ne sert qu'à vérifier.
    otp_secret = Column(String(64))
    otp_actif = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    otp_impose = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    otp_codes_secours = Column(Text)
    # Incrémentée à chaque changement de mot de passe : les jetons portant une
    # version antérieure sont refusés, ce qui referme les sessions déjà ouvertes.
    jeton_version = Column(Integer, nullable=False, server_default=text("0"), default=0)
    date_mot_de_passe = Column(DateTime)

    roles = relationship("Role", secondary=utilisateur_roles, back_populates="utilisateurs")

    @property
    def nom_affiche(self) -> str:
        """
        Ce qu'on montre à l'écran : « Prénom Nom », ou l'adresse quand ni l'un
        ni l'autre n'est renseigné. Un compte sans nom reste identifiable —
        c'est le cas d'un administrateur, qui n'a pas à décliner son identité.
        """
        complet = " ".join(part for part in (self.prenom, self.nom) if part and part.strip())
        return complet or self.email


class ExportArchive(Base):
    """
    Une archive d'export (§17.30).

    `date_telechargement` fait le « une seule fois » : une fois posée, le jeton
    ne vaut plus rien et le fichier est effacé. `date_expiration` fait le reste —
    un export oublié sur le disque est une fuite qui attend son heure.
    """
    __tablename__ = "sys_exports"
    id = Column(Integer, primary_key=True)
    jeton = Column(String(64), nullable=False, unique=True)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    chemin = Column(String(500), nullable=False)
    taille_octets = Column(BigInteger)
    documents = Column(Integer)
    date_creation = Column(DateTime, server_default=func.now())
    date_expiration = Column(DateTime, nullable=False)
    date_telechargement = Column(DateTime)

    utilisateur = relationship("Utilisateur")


class VerrouDocument(Base):
    """
    Verrou d'édition (§17.21).

    Une ligne par document au plus — la contrainte d'unicité le garantit, pas le
    code. `date_expiration` rend le verrou périssable : sans elle, un onglet
    fermé sans un mot bloquerait le document pour tout le foyer.
    """
    __tablename__ = "sys_verrous_document"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                         nullable=False, unique=True)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    date_expiration = Column(DateTime, nullable=False)

    utilisateur = relationship("Utilisateur")


class SessionOuverte(Base):
    """
    Une session ouverte (§17.2).

    Nommée `SessionOuverte` et non `Session` : ce dernier nom désigne déjà la
    session de base de données dans tout le projet, et deux objets de sens
    opposé sous le même nom rendraient chaque import ambigu.

    Le `jti` est l'identifiant unique porté par le jeton : c'est lui qui fait le
    lien entre un JWT en circulation et cette ligne. Révoquer une session, c'est
    dater `date_revocation` — la ligne survit, pour qu'on puisse relire après
    coup ce qui s'est passé.
    """
    __tablename__ = "sys_sessions"
    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="CASCADE"),
                            nullable=False)
    jti = Column(String(64), nullable=False, unique=True)
    date_creation = Column(DateTime, server_default=func.now())
    date_activite = Column(DateTime)
    date_expiration = Column(DateTime, nullable=False)
    date_revocation = Column(DateTime)
    adresse = Column(String(64))
    agent = Column(String(255))


class Role(Base):
    __tablename__ = "sys_roles"
    id = Column(Integer, primary_key=True)
    nom = Column(String(100), nullable=False, unique=True)
    description = Column(String(255))

    utilisateurs = relationship("Utilisateur", secondary=utilisateur_roles, back_populates="roles")
    droits_categorie = relationship("DroitCategorie", back_populates="role", cascade="all, delete-orphan")
    droits_generaux = relationship("DroitGeneral", back_populates="role", cascade="all, delete-orphan")
    droits_vue = relationship("DroitVue", back_populates="role", cascade="all, delete-orphan")
    # Restrictions par branche (§21.7) : « ce rôle ne voit que 2025 et 2026 ».
    droits_branche = relationship("DroitBranche", back_populates="role",
                                  cascade="all, delete-orphan")


class DroitCategorie(Base):
    __tablename__ = "sys_droits_categorie"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("sys_roles.id", ondelete="CASCADE"), nullable=False)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"), nullable=False)
    # Six actions (§19.12). `telecharger` se distingue de `voir` — laisser lire
    # une fiche n'oblige pas à donner le PDF ; `gerer_versions` de `modifier` —
    # supprimer une version détruit un fichier, corriger un champ non.
    peut_voir = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)
    peut_modifier = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    peut_deposer = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    peut_telecharger = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)
    peut_supprimer = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    peut_gerer_versions = Column(Boolean, nullable=False, server_default=text("FALSE"),
                                 default=False)

    role = relationship("Role", back_populates="droits_categorie")
    categorie = relationship("Categorie")


class DroitGeneral(Base):
    """
    Droit d'un rôle hors catégorie (§19.12) : Centre d'analyse, serveur de
    travaux, export de l'archive…

    La clé est le nom que le code déclare (`app/droits.py`) et non une ligne de
    référence en base : une table de correspondance se désynchroniserait au
    premier renommage d'un point d'entrée, et l'on découvrirait le décalage par
    un droit devenu sans effet.
    """
    __tablename__ = "sys_droits_generaux"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("sys_roles.id", ondelete="CASCADE"), nullable=False)
    droit = Column(String(40), nullable=False)

    role = relationship("Role", back_populates="droits_generaux")


class DroitVue(Base):
    """
    Visibilité d'une vue enregistrée pour un rôle (§19.12).

    Une vue est une lecture préfiltrée du registre, et toutes n'ont pas à être
    offertes à tout le monde. Sans aucune ligne, la vue suit `partagee` comme
    avant : pouvoir restreindre n'oblige pas chaque foyer à le faire.
    """
    __tablename__ = "sys_droits_vue"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("sys_roles.id", ondelete="CASCADE"), nullable=False)
    vue_id = Column(Integer, ForeignKey("sys_vues_enregistrees.id", ondelete="CASCADE"),
                    nullable=False)

    role = relationship("Role", back_populates="droits_vue")


class DroitBranche(Base):
    """
    Restriction d'un rôle à certaines **valeurs** d'un champ (§21.7).

    Nos droits se posent sur les emplacements — un dossier, un type ; rien ne
    permettait de dire « ce rôle ne voit que 2025 et 2026 ». Une ligne dit « ce
    rôle est autorisé sur cette branche ». L'absence de ligne sur un champ vaut
    absence de restriction : pouvoir restreindre n'oblige pas à le faire.

    Rien n'est dynamique : ce ne sont pas « mes documents », mais des branches
    que l'administration a nommées.
    """
    __tablename__ = "sys_droits_branche"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("sys_roles.id", ondelete="CASCADE"), nullable=False)
    champ = Column(String(100), nullable=False)
    valeur = Column(String(255), nullable=False)

    role = relationship("Role", back_populates="droits_branche")

    __table_args__ = (UniqueConstraint("role_id", "champ", "valeur",
                                       name="uq_droit_branche"),)


class Notification(Base):
    """
    Un rappel, ou ce qu'une automatisation a voulu dire (§21.9).

    Une table et non un compteur : un rappel doit pouvoir être lu, relu et
    retrouvé, et le §21.10 les enverra par courriel depuis ce même endroit.
    `utilisateur_id` vide = pour tout le foyer, ce qui est le cas ordinaire : une
    échéance de maison ne s'adresse à personne en particulier.

    `empreinte` est la mémoire du « déjà prévenu » : sans elle, la même échéance
    reviendrait chaque nuit.
    """
    __tablename__ = "sys_notifications"
    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="CASCADE"))
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"))
    titre = Column(String(200), nullable=False)
    message = Column(Text)
    source = Column(String(40), nullable=False, server_default=text("'rappel'"),
                    default="rappel")
    empreinte = Column(String(120), unique=True)
    date_creation = Column(DateTime, server_default=func.now())
    date_lecture = Column(DateTime)
    # Ce qui est déjà parti par courriel ne repart pas (§21.10).
    date_envoi = Column(DateTime)

    document = relationship("Document")


class Automatisation(Base):
    """
    « Quand… alors… » (§21.8).

    Le workflow d'EzGED enchaîne des étapes et des tâches ; pour une maison, la
    même idée tient en une phrase : quand un document arrive et que telle
    condition est vraie, faire ceci. Générique et réglée depuis l'administration
    — rien de spécifique aux factures n'est écrit dans le code.

    `conditions` est la même liste JSON `{champ, operateur, valeur}` que les
    filtres, les vues et les tableaux de bord : tout ce qui se filtre se teste,
    et il n'y a pas de second langage à apprendre.
    """
    __tablename__ = "sys_automatisations"
    id = Column(Integer, primary_key=True)
    nom = Column(String(150), nullable=False)
    declencheur = Column(String(40), nullable=False)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"))
    conditions = Column(Text)
    actions = Column(Text, nullable=False)
    actif = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)
    ordre = Column(Integer, nullable=False, server_default=text("100"), default=100)
    date_creation = Column(DateTime, server_default=func.now())

    categorie = relationship("Categorie")


class ExecutionAutomatisation(Base):
    """
    Ce qui s'est déclenché, et pourquoi (§21.8).

    Une automatisation silencieuse devient vite une source de mystères : on
    constate un champ rempli sans savoir par quoi. Le journal répond, et sert en
    plus à ne pas agir deux fois sur le même document quand le déclencheur est
    une date — qui, elle, revient tous les jours.
    """
    __tablename__ = "sys_journal_automatisation"
    id = Column(Integer, primary_key=True)
    automatisation_id = Column(Integer, ForeignKey("sys_automatisations.id",
                                                   ondelete="CASCADE"))
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"))
    date_execution = Column(DateTime, server_default=func.now())
    declencheur = Column(String(40), nullable=False)
    agi = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    detail = Column(Text)

    automatisation = relationship("Automatisation")


class Job(Base):
    """
    Travail de traitement d'un fichier déposé (§13). Conserve l'état, le nombre
    de tentatives et le diagnostic, pour que l'administration puisse suivre et
    rejouer les traitements sans intervenir sur le serveur.
    """
    __tablename__ = "sys_jobs"
    id = Column(Integer, primary_key=True)
    nom_fichier = Column(String(255), nullable=False)
    chemin_source = Column(String(500))
    hash_sha256 = Column(String(64))
    statut = Column(
        # « a_classer » (§19.3) : déposé à un endroit qu'aucun type de document
        # ne réclame. Le traitement s'arrête avant l'océrisation — le texte
        # reconnu ne servirait à rien tant qu'on ignore de quoi il s'agit.
        # `echec` : erreur **définitive** (§21.15). Un travail qui a épuisé le
        # palier de tentatives en sort — la reprise ne le regarde plus, et l'écran
        # le distingue de ce que la machine essaie encore.
        Enum("en_attente", "en_cours", "termine", "erreur", "bloque", "ignore",
             "a_classer", "echec"),
        default="en_attente",
    )
    # dernière étape atteinte, pour savoir où le travail s'est arrêté
    etape = Column(String(30))
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="SET NULL"))
    tentatives = Column(Integer, default=0)
    # Passes de la reprise automatique sur un travail bloqué (§21.15). Au-delà du
    # palier, la reprise cesse de le reprendre : il reste bloqué — il appelle une
    # action humaine — mais la machine ne fait plus semblant de chercher.
    reprises_auto = Column(Integer, nullable=False, server_default=text("0"), default=0)
    message_erreur = Column(Text)
    diagnostic = Column(Text)
    # drapeau posé par l'API : elle n'a pas accès au dossier surveillé, c'est le
    # worker qui relève la demande de rejeu à son passage suivant
    rejouer_demande = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    etape_demandee = Column(String(30))  # d'où reprendre lors du rejeu
    # Type de document demandé pour un fichier « à classer » (§19.4). L'API pose
    # la consigne ; c'est le serveur de travaux qui déplace le fichier, seul à
    # avoir les fichiers reçus en écriture. Effacée dès que c'est fait.
    categorie_demandee = Column(Integer, ForeignKey("sys_categories.id", ondelete="SET NULL"))
    # Dépôt écarté depuis le Centre d'analyse (§21.14) : même principe, l'API pose
    # la consigne et le serveur de travaux efface le fichier reçu — un double
    # scan ou une page de garde n'a pas à encombrer l'écran indéfiniment.
    rejet_demande = Column(Boolean, nullable=False, server_default=text("FALSE"),
                           default=False)
    # Type reconnu au dépôt (§21.15). Un **souvenir**, pas une consigne :
    # l'emplacement reste maître quand il parle. Il ne sert qu'au rejeu, où le
    # fichier vit dans `travaux/` et où l'emplacement ne dit plus rien.
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="SET NULL"))
    # Le fichier rejoint un document existant comme **pièce**, au lieu de créer un
    # document (§22.2). Le dossier de dépôt ne dit que le type et le fichier ne
    # dit rien : c'est le travail qui porte la consigne, comme pour le type
    # retenu au dépôt.
    #
    # `CASCADE`, et non `SET NULL` comme `document_id` : vidée, la consigne ne
    # dirait plus « pièce du document nº12 » mais « dépôt ordinaire », et le
    # serveur de travaux créerait un document là où l'on voulait une pièce. Le
    # travail s'en va donc avec le document qu'il visait — ce qui n'arrive qu'à
    # la suppression définitive, la corbeille ne touchant à rien.
    piece_pour_document_id = Column(Integer,
                                    ForeignKey("sys_documents.id", ondelete="CASCADE"))
    # Le dépôt est une **nouvelle version de cette pièce**, et non une pièce de
    # plus (§22.3) : la seule chose qu'on ne puisse pas deviner — le même PDF est
    # l'un ou l'autre selon ce qu'on vient de faire.
    version_pour_piece_id = Column(Integer,
                                   ForeignKey("sys_pieces_document.id", ondelete="CASCADE"))
    date_creation = Column(DateTime, server_default=func.now())
    date_debut = Column(DateTime)
    date_fin = Column(DateTime)

    document = relationship("Document", foreign_keys=[document_id])


class AffichageValeur(Base):
    """
    Ce que **cette entrée-ci** montre d'une ligne de table (§22.61).

    Trois niveaux, et chacun sait quelque chose que les autres ignorent : la
    table déclare ce qui désigne une ligne, le champ choisit ce qui la compose
    ici (§22.59, `colonnes_affichees`), et l'entrée retient, parmi ce que le
    champ propose, ce qui mérite la place d'une colonne. C'est celui qui saisit
    qui sait si le modèle apporte quelque chose à cette ligne-là.

    Aucune ligne ici veut dire « tout ce que le champ propose » : l'état de
    toutes les entrées existantes.
    """
    __tablename__ = "sys_affichages_valeur"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                         nullable=False)
    champ = Column(String(100), nullable=False)
    colonnes = Column(String(255), nullable=False)

    __table_args__ = (UniqueConstraint("document_id", "champ",
                                       name="uq_affichage_document_champ"),)


class RegleChampCategorie(Base):
    """
    Champ attendu sur les documents d'une catégorie, obligatoire ou facultatif
    (§15). `champ` reprend le vocabulaire du moteur de filtres : champ du
    document (`date_document`, `statut`…) ou `meta:<cle>` pour
    une métadonnée extraite — l'architecture reste ainsi générique vis-à-vis des
    futurs champs personnalisés.
    """
    __tablename__ = "sys_regles_champs_categorie"
    id = Column(Integer, primary_key=True)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"), nullable=False)
    champ = Column(String(100), nullable=False)
    # table de données servant de source de valeurs (champ personnalisé, §17) :
    # la valeur retenue est alors l'identifiant d'une ligne de cette table
    source_table = Column(String(64))
    # Sources multiples, séparées par des virgules (§17.28). `source_table`
    # garde la première : c'est elle qui donne son sens à une valeur enregistrée
    # sans préfixe.
    sources = Column(String(500))
    # Déduction automatique depuis le texte du document (§18.47) : 'aucune',
    # 'toutes' (toutes les colonnes cherchées doivent y figurer) ou 'une'. Rien
    # n'est déduit tant qu'un administrateur ne l'a pas déclaré — un
    # rattachement que personne n'a demandé se lit comme une erreur, même juste.
    deduction = Column(String(20), nullable=False, server_default=text("'aucune'"),
                       default="aucune")
    # Colonnes de la table source cherchées dans le document, séparées par des
    # virgules. Vide : les colonnes identifiantes de la table.
    colonnes_deduction = Column(String(255))
    # Colonnes de la table source qui composent la **valeur affichée** (§22.59),
    # séparées par des virgules. Vide : les colonnes identifiantes de la table.
    # Le choix appartient au champ et non à la table : le même véhicule se lit
    # « AA-123-BB » sous « Véhicule concerné » et « Clio III · AA-123-BB » dans
    # un sélecteur où l'on cherche la bonne voiture.
    colonnes_affichees = Column(String(255))
    # Le champ contient des **documents de la GED**, choisis dans une liste
    # (§22.11) : « Factures liées », « Devis reçus ». Ce n'est ni une pièce
    # (§22.2, un fichier de plus dans ce document), ni un rattachement à la main
    # (§22.4, un lien sans nom) — c'est un champ, avec son intitulé et sa place
    # dans la fiche.
    attache_documents = Column(Boolean, nullable=False, server_default=text("FALSE"),
                               default=False)
    # Comment ce champ se saisit et se relit (§22.12) : `texte`, `texte_long`,
    # `date`, `nombre`, `montant`, `booleen`. C'est le type qui décide du contrôle
    # affiché — un champ dont on ignore la nature se saisit toujours de la
    # mauvaise manière. `texte` par défaut : c'est ce que faisaient tous les
    # champs d'avant, et rien ne devait changer pour eux.
    type_champ = Column(String(20), nullable=False, server_default=text("'texte'"),
                        default="texte")
    # Ce qu'un champ « documents » accepte (§22.14) : le type qu'on peut y
    # attacher, et les champs sur lesquels la recherche porte. Un champ qui
    # propose toute la GED ne guide personne — « Factures liées » doit proposer
    # des factures, cherchées par leur numéro ou leur émetteur.
    documents_categorie_id = Column(Integer,
                                    ForeignKey("sys_categories.id", ondelete="SET NULL"))
    documents_champs = Column(String(255))
    # Ce champ attend-il d'être rempli par une règle d'extraction ? (§22.27)
    # Sans cette déclaration, « aucune règle ne le vise » ne distinguait pas un
    # commentaire qu'on saisit — et c'est très bien — d'un numéro de facture dont
    # la règle manque, ce qui est un réglage à faire.
    extraction_attendue = Column(Boolean, nullable=False, server_default=text("FALSE"),
                                 default=False)
    # Tolérer une petite différence entre le document et la table (§21.4). Se
    # déclare champ par champ et jamais par défaut : sur un nom de personne, la
    # tolérance rattrape un scan médiocre ; sur une immatriculation, elle
    # confondrait deux véhicules — un caractère les sépare.
    deduction_approchee = Column(Boolean, nullable=False, server_default=text("FALSE"),
                                 default=False)
    # Ce champ porte-t-il une date qui arrive à terme ? (§21.9) Le foyer décide
    # duquel il s'agit — `date_echeance` pour une facture, `fin_de_validite` pour
    # une carte d'identité — et de combien de jours à l'avance il veut être prévenu.
    echeance = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    rappel_jours = Column(Integer)
    libelle = Column(String(150))
    obligatoire = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)
    # Ce champ identifie-t-il un document de cette catégorie ? (§18.40) C'est lui
    # qui reconnaît la même pièce redéposée — un numéro de facture, une période
    # de paie. Plusieurs champs cochés comptent ensemble.
    identifiant = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    ordre = Column(Integer, default=100)

    # `foreign_keys` explicite depuis le §22.14 : la règle pointe deux fois les
    # catégories — celle qui la porte, et celle que le champ « documents »
    # accepte —, et SQLAlchemy ne peut plus deviner laquelle relie quoi.
    categorie = relationship("Categorie", foreign_keys=[categorie_id])
    categorie_documents = relationship("Categorie", foreign_keys=[documents_categorie_id])

    __table_args__ = (UniqueConstraint("categorie_id", "champ", name="uq_categorie_champ"),)


class ColonneDonnees(Base):
    """
    Réglages d'une colonne d'une table du foyer (§18.32) : son intitulé lisible,
    et la table qu'elle pointe le cas échéant.

    C'est ce qui permet à `usr_vehicules.proprietaire` de désigner une ligne de
    `usr_membres` — et à n'importe quelle autre colonne de pointer n'importe
    quelle autre table, puisque la liaison est déclarée et non écrite dans le
    code. L'unicité n'est pas ici : une contrainte UNIQUE vit dans le schéma de
    la table, qui reste la seule source de vérité.
    """
    __tablename__ = "sys_colonnes_donnees"
    id = Column(Integer, primary_key=True)
    nom_table = Column(String(64), nullable=False)
    colonne = Column(String(64), nullable=False)
    libelle = Column(String(150))
    source_table = Column(String(64))

    __table_args__ = (UniqueConstraint("nom_table", "colonne", name="uq_colonne_donnees"),)


class Reglage(Base):
    """
    Un réglage général, modifiable depuis l'administration (§18.19).

    Clé/valeur plutôt qu'une colonne par réglage : ce qui s'ajoutera ensuite
    n'imposera pas de migration, et un réglage retiré ne laisse pas une colonne
    orpheline. La liste des clés admises vit dans `app/reglages.py` — une clé
    inconnue est refusée, sans quoi une faute de frappe créerait un réglage que
    rien ne lit.
    """
    __tablename__ = "sys_reglages"
    cle = Column(String(64), primary_key=True)
    valeur = Column(Text)
    date_modification = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ColonneCategorie(Base):
    """
    Colonne du tableau pour une catégorie (§18.1).

    Ne contient que les **corrections** apportées aux colonnes déduites : le
    tableau d'une catégorie qui n'a aucune ligne ici reste parfaitement
    utilisable (cf. `app/colonnes.py`). D'où `visible` : masquer une colonne
    déduite se dit « pas celle-là », ce que l'absence de ligne ne saurait
    exprimer — l'absence, c'est ce qui déclenche la déduction.

    `champ` parle le vocabulaire du moteur de filtres (`date_document`,
    `meta:<cle>`, `lien:<table>`) : une colonne est donc filtrable et triable
    sans travail supplémentaire.
    """
    __tablename__ = "sys_colonnes_categorie"
    id = Column(Integer, primary_key=True)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"),
                          nullable=False)
    champ = Column(String(100), nullable=False)
    libelle = Column(String(150))
    ordre = Column(Integer, nullable=False, server_default=text("100"), default=100)
    largeur = Column(Integer)
    visible = Column(Boolean, nullable=False, server_default=text("TRUE"), default=True)

    categorie = relationship("Categorie")

    __table_args__ = (UniqueConstraint("categorie_id", "champ", name="uq_colonne_categorie"),)


class TableDonnees(Base):
    """
    Table de référence créée depuis l'administration (§17), destinée à alimenter
    des champs personnalisés. Son inscription ici est ce qui la rend modifiable
    depuis l'interface : les tables du fonctionnement de l'application n'y
    figurent pas et restent en consultation seule.
    """
    __tablename__ = "sys_tables_donnees"
    id = Column(Integer, primary_key=True)
    nom_table = Column(String(64), nullable=False, unique=True)
    libelle = Column(String(150), nullable=False)
    description = Column(String(500))
    colonne_libelle = Column(String(64))
    # Colonnes suffisant à désigner une ligne dans le texte d'un document
    # (§17.19) : « prenom,nom » pour les membres du foyer. Vide = la seule
    # colonne d'affichage.
    colonnes_identifiantes = Column(String(255))
    date_creation = Column(DateTime, server_default=func.now())


class TableauDeBord(Base):
    """
    Tableau de bord personnalisé : une liste d'indicateurs décrits en JSON
    (`widgets`), sur le modèle des vues enregistrées. Chaque indicateur
    réutilise le format de filtres du registre — décrire « les factures de
    l'année en cours » se fait de la même façon partout.
    """
    __tablename__ = "sys_tableaux_de_bord"
    id = Column(Integer, primary_key=True)
    nom = Column(String(150), nullable=False)
    description = Column(String(500))
    widgets = Column(Text, nullable=False)
    partage = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    ordre = Column(Integer, default=100)
    date_creation = Column(DateTime, server_default=func.now())

    utilisateur = relationship("Utilisateur")


class JournalAudit(Base):
    """
    Trace d'une action importante (§14). `action` et `objet_type` sont des
    chaînes libres pour rester extensible sans migration. `utilisateur_email`
    double la clé étrangère afin que la trace survive à la suppression du compte.
    """
    __tablename__ = "sys_journal_audit"
    id = Column(Integer, primary_key=True)
    date_evenement = Column(DateTime, server_default=func.now())
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    utilisateur_email = Column(String(255))
    action = Column(String(100), nullable=False)
    objet_type = Column(String(50), nullable=False)
    objet_id = Column(Integer)
    details = Column(Text)


class ExportModele(Base):
    """
    Une demande d'export par modèle (§21.13).

    L'export de secours (§17.30) sort tout le foyer, une fois, sous mot de passe :
    il répond à « je ne me sers plus de la GED ». Celui-ci répond au besoin
    quotidien — sortir une sélection rangée comme on la veut, pour la donner au
    comptable ou à l'assurance.

    C'est une **demande**, pas une réponse : cinq cents PDF à copier et
    compresser tiennent une connexion ouverte plusieurs minutes, et l'API n'a de
    toute façon pas les archives en écriture. Le serveur de travaux construit, on
    revient chercher.
    """
    __tablename__ = "sys_exports_modele"
    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    statut = Column(Enum("en_attente", "en_cours", "pret", "erreur"),
                    nullable=False, default="en_attente")
    criteres = Column(Text)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="SET NULL"))
    # Modèles à trous : « {annee}/{type} », « {champ:emetteur} - {date} ». Les
    # trous sont les champs du document — pas un vocabulaire de plus à apprendre.
    modele_dossier = Column(String(255))
    modele_nom = Column(String(255))
    chemin = Column(String(500))
    nb_documents = Column(Integer)
    message = Column(Text)
    date_demande = Column(DateTime, server_default=func.now())
    date_fin = Column(DateTime)

    utilisateur = relationship("Utilisateur")


class Script(Base):
    """
    Un script du mode développeur (§21.14).

    La porte de sortie universelle : ce qu'aucun écran ne prévoit et qu'on ne va
    pas coder pour un foyer. Autorisée sous condition d'un mode déclaré, qui
    énonce d'abord ce que cela pose — voir `app/scripts.py`.
    """
    __tablename__ = "sys_scripts"
    id = Column(Integer, primary_key=True)
    nom = Column(String(150), nullable=False, unique=True)
    description = Column(Text)
    code = Column(LONGTEXT, nullable=False)
    date_creation = Column(DateTime, server_default=func.now())
    date_modification = Column(DateTime)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))

    utilisateur = relationship("Utilisateur")


class ExecutionScript(Base):
    """
    Une exécution, avec ce qu'elle a rendu (§21.14).

    Journalisée systématiquement : c'est la contrepartie du mode. Qui l'a lancé,
    combien de temps, ce qui en est sorti — sans quoi « un script a tourné » ne
    serait qu'une rumeur.
    """
    __tablename__ = "sys_executions_script"
    id = Column(Integer, primary_key=True)
    script_id = Column(Integer, ForeignKey("sys_scripts.id", ondelete="SET NULL"))
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    date_execution = Column(DateTime, server_default=func.now())
    duree_ms = Column(Integer)
    reussite = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    sortie = Column(LONGTEXT)
    erreur = Column(Text)

    utilisateur = relationship("Utilisateur")


class DocumentAttache(Base):
    """
    Un document attaché à un autre **par un champ** (§22.11).

    Sous « Entretiens », on note ce qui a été fait sur le véhicule et l'on y
    attache une facture déjà présente dans la GED. Le besoin est général — une
    déclaration de sinistre et ses devis, un chantier et ses pièces —, d'où un
    champ générique plutôt qu'une notion de plus.

    Une table plutôt qu'une métadonnée à rallonge : une liste d'identifiants dans
    une chaîne de 500 caractères s'y serait tenue trois documents, et rien
    n'aurait effacé le lien à la suppression de la cible.
    """
    __tablename__ = "sys_documents_attaches"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                         nullable=False)
    # Le champ auquel cette attache appartient, dans le vocabulaire des filtres :
    # un même document peut en porter plusieurs.
    champ = Column(String(100), nullable=False)
    document_attache_id = Column(Integer, ForeignKey("sys_documents.id", ondelete="CASCADE"),
                                 nullable=False)
    ordre = Column(Integer, nullable=False, server_default=text("1"), default=1)
    date_ajout = Column(DateTime, server_default=func.now())
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))

    __table_args__ = (UniqueConstraint("document_id", "champ", "document_attache_id",
                                       name="uq_attache"),)


class LienType(Base):
    """
    Un rapprochement déclaré sur un type de document (§22.8).

    Un dossier porte un numéro, et ce numéro est repris sur le devis, le bon de
    commande, le bon de livraison : ouvrir l'un doit montrer les autres — non
    parce qu'une machine l'a deviné, mais parce que quelqu'un a **déclaré** que
    ce champ-là relie ces types-là.

    La déclaration vaut **dans les deux sens** : sans cela il faudrait déclarer
    six liens pour trois types, et l'on en oublierait toujours un. Elle se pose
    sur le type et non sur la vue (§22.5) : un devis appartient au dossier
    nº1234 quel que soit l'écran par lequel on l'ouvre.
    """
    __tablename__ = "sys_liens_types"
    id = Column(Integer, primary_key=True)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"),
                          nullable=False)
    # NULL : tous les types — c'est le cas du numéro de dossier, repris par des
    # pièces de sortes très différentes.
    categorie_cible_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"))
    champ_source = Column(String(100), nullable=False)
    champ_cible = Column(String(100), nullable=False)
    libelle = Column(String(120))

    categorie = relationship("Categorie", foreign_keys=[categorie_id])
    cible = relationship("Categorie", foreign_keys=[categorie_cible_id])

    __table_args__ = (
        UniqueConstraint("categorie_id", "categorie_cible_id", "champ_source", "champ_cible",
                         name="uq_lien_type"),
    )


class VueEnregistree(Base):
    """
    Jeu de critères de filtrage réutilisable (§9.B). `criteres` est la même
    liste JSON de `{champ, operateur, valeur}` que celle de la recherche par
    colonne : une vue n'est donc que la persistance d'un filtrage, rien n'est
    codé en dur par vue. `categorie_id` ne sert qu'au rattachement dans la
    navigation, le filtrage étant entièrement décrit par `criteres`.
    """
    __tablename__ = "sys_vues_enregistrees"
    id = Column(Integer, primary_key=True)
    nom = Column(String(150), nullable=False)
    categorie_id = Column(Integer, ForeignKey("sys_categories.id", ondelete="CASCADE"))
    criteres = Column(Text, nullable=False)
    utilisateur_id = Column(Integer, ForeignKey("sys_utilisateurs.id", ondelete="SET NULL"))
    partagee = Column(Boolean, nullable=False, server_default=text("FALSE"), default=False)
    ordre = Column(Integer, default=100)
    # Champs du repli en arborescence (§21.6), séparés par des virgules. Vide :
    # la vue s'ouvre à plat. C'est un classement calculé à partir des données,
    # distinct de l'arborescence des dossiers réglée par l'administration.
    groupement = Column(String(255))
    # Liens déclarés vers d'autres vues (§22.5) : la « correspondance de champs »
    # d'EzGED — « depuis cette vue, ouvrir celle-là sur la ligne qu'on regarde ».
    # JSON, porté par la vue : une déclaration n'a de sens qu'avec elle, et
    # disparaît avec elle.
    liens = Column(Text)
    date_creation = Column(DateTime, server_default=func.now())

    categorie = relationship("Categorie")
    utilisateur = relationship("Utilisateur")
    # Rôles auxquels cette vue est réservée (§19.12). Vide : elle suit `partagee`.
    droits = relationship("DroitVue", cascade="all, delete-orphan")


def ids_categorie_et_descendants(session, categorie_id: int) -> set[int]:
    """
    Renvoie l'id d'une catégorie et ceux de toutes ses sous-catégories, à
    n'importe quelle profondeur. Sélectionner une section de la navigation
    (ex: "Maison") doit en effet ramener les documents de ses enfants
    ("Factures", "Banque", ...) et pas seulement ceux classés sur la section
    elle-même. La table `categories` reste petite : on la charge en une fois
    plutôt que d'enchaîner une requête par niveau.
    """
    couples = session.query(Categorie.id, Categorie.parent_id).all()
    enfants: dict[int, list[int]] = {}
    for id_categorie, parent_id in couples:
        if parent_id is not None:
            enfants.setdefault(parent_id, []).append(id_categorie)

    ids = set()
    a_visiter = [categorie_id]
    while a_visiter:
        courant = a_visiter.pop()
        if courant in ids:      # garde-fou : une boucle éventuelle ne doit pas figer la requête
            continue
        ids.add(courant)
        a_visiter.extend(enfants.get(courant, []))
    return ids


def get_session():
    """Générateur de session à utiliser avec FastAPI Depends(), ou directement en `with`."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
