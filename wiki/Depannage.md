# Dépannage

## Un document déposé n'apparaît nulle part

Dans l'ordre :

1. **Centre d'analyse** — c'est le cas le plus fréquent : il lui manque un champ
   exigé, ou son type n'a pas été déterminé.
2. *Administration → Serveur de travaux* — le traitement a-t-il échoué ? Le
   diagnostic dit à quelle étape et pourquoi. « Rejouer » le relance.
3. *Administration → Dépôt* — le fichier est-il dans un dossier qu'aucun type ne
   réclame ? Il est alors resté en place, sans être lu.

## « Champ manquant » alors que la valeur est bien là

La règle d'extraction a écrit la valeur sous une **autre clé** que celle
qu'attend le champ. Ouvrez *Administration → Assembler un type* : chaque champ
attendu y affiche si sa règle est en place ou reste à écrire.

## Le traitement est lent, ou la file s'allonge

*Administration → Réglages généraux → Traitement et conservation → Documents
traités en même temps.* Zéro veut dire « décide pour moi » (la moitié des cœurs,
quatre au plus). Monter plus haut que la moitié des cœurs ralentit tout.

Voir [Performances](Performances).

## L'interface est lente

Regardez d'abord *Administration → Supervision* : disque, mémoire, processeur,
file de traitements. Une file longue explique tout le reste.

Au-delà de 10 000 documents, montez `innodb_buffer_pool_size` de MariaDB à
environ 1 Go dans `docker-compose.yml`.

## Je suis enfermé dehors (trop de tentatives)

Le verrouillage est **en mémoire du processus** : `docker compose restart api`
remet les compteurs à zéro. Sinon, *Administration → Tentatives de connexion*
permet de débloquer une adresse — depuis un autre compte administrateur.

## J'ai perdu mon second facteur

Utilisez un **code de secours** (« J'ai perdu mon téléphone » sur l'écran de
connexion). S'il n'en reste plus, un autre administrateur peut réinitialiser la
double authentification du compte depuis *Utilisateurs*.

## Un fichier a disparu de `storage/`

*Administration → Intégrité des archives* le dira. Les fichiers que plus aucun
document ne réclame ne sont pas effacés : ils partent dans
`storage/.corbeille/AAAA-MM-JJ/`, consultable depuis *Administration →
Corbeille*. Vider la corbeille reste une décision humaine.

## Où sont les journaux

```bash
docker compose logs -f worker    # océrisation, extraction, sauvegardes
docker compose logs -f api       # les requêtes et leurs erreurs
docker compose logs -f db
```

Et dans l'application : *Administration → Journal d'audit* garde la trace des
actions — documents, comptes, exports, scripts, et la configuration du
classement.

## Repartir de zéro sans rien perdre

*Administration → Configuration du foyer* exporte l'arborescence, les règles, les
champs, les colonnes, les vues, les rôles et les tables — **sans les documents**.
De quoi remonter le même classement ailleurs, ou revenir en arrière après une
expérience malheureuse.
