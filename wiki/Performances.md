# Performances

Tous les chiffres de cette page sont **mesurés**, sur un Xeon E5-2470 v2 (2013,
10 cœurs, 2,4 GHz) et 15 Go de mémoire, avec un jeu d'essai de documents réels.
Une machine récente fait sensiblement mieux : lisez-les comme un plancher.

## Lecture

Médianes de cinq appels, à travers le proxy :

| | 5 000 documents | 20 000 documents |
|---|---|---|
| Registre, une page | 64 ms | **66 ms** |
| Registre, page 40 | 57 ms | 68 ms |
| Recherche plein texte | 140 ms | 262 ms |
| Recherche globale | 133 ms | 201 ms |
| Centre d'analyse | 41 ms | 42 ms |
| Tableau de bord | 30 ms | 58 ms |
| Compteurs de la barre | 18 ms | 29 ms |

Le registre ne ralentit pratiquement pas entre 5 000 et 20 000 documents : ce qui
coûtait, c'était le calcul de conformité à chaque lecture ; il est désormais
**rangé sur le document** et mis à jour quand il change.

Ce qui croît encore avec le nombre de documents est ce qui le doit par nature :
la recherche plein texte et les valeurs proposées dans un filtre.

## Entrée

| | |
|---|---|
| Un document, de bout en bout | ~7 secondes (presque entièrement l'océrisation) |
| À un seul fil | ~500 documents/heure |
| À quatre fils | ~1 800 documents/heure |
| Reprendre 20 000 documents | ~40 h à un fil, ~11 h à quatre |

**Le réglage** : *Administration → Réglages généraux → Traitement et conservation
→ Documents traités en même temps*. Zéro veut dire « décide pour moi » : la
moitié des cœurs, quatre au plus. Le changement prend effet en quelques secondes,
sans redémarrage — les documents en cours vont au bout.

> Monter au-delà de la moitié des cœurs ne sert à rien : les océrisations se
> disputent le processeur au lieu de se le partager, et la machine devient lente
> pour tout le reste, y compris l'interface.

## Charge

Cinq clients simultanés sur le registre : **13,6 appels/seconde**, 337 ms par
appel. Un foyer n'y arrivera jamais.

## Disque

| | |
|---|---|
| Base, 20 000 documents | ~90 Mo (dont 38 Mo d'index plein texte) |
| Par millier de documents | ~15 Mo de base, plus vos PDF |
| Une facture océrisée | 100 à 300 ko selon le scan |

La compression des archives se règle (*Traitement et conservation*) : le niveau 2
gagne 60 à 80 % sur un scan sans perte de texte.

## Régler MariaDB

Le réglage qui compte est `innodb_buffer_pool_size` : 128 Mo par défaut, ce qui
suffit sous 10 000 documents. Au-delà :

```yaml
  db:
    command: --innodb-buffer-pool-size=1G
```

## Où est le plafond

Au-delà de 50 000 documents, deux choses demanderaient à être revues : les
valeurs proposées dans les filtres (aujourd'hui lues à la volée) et la recherche
plein texte, qui gagnerait à être bornée par défaut à une période. Rien de cela
n'est nécessaire pour un foyer.
