# Sécurité avancée

HomeGED est écrit pour un foyer, pas pour l'internet ouvert. Ce qu'il fait déjà,
et ce que vous devez faire vous-même, sont deux choses distinctes : cette page
sépare les deux.

## Ce que l'application fait déjà

| | |
|---|---|
| **Session en cookie `httpOnly`** | Le jeton n'est pas lisible par le JavaScript de la page : un script injecté ne peut pas le voler. |
| **Anti-CSRF** | `SameSite=Strict` et un second cookie répété en en-tête sur toute écriture. Un autre site ne peut ni le lire ni le forger. |
| **En-têtes de sécurité** | CSP, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, sur la page **et** sur l'API. |
| **Limitation des tentatives** | Sur le mot de passe **et** sur le second facteur, par compte et par adresse. Journalisée. |
| **Double authentification** | TOTP, avec codes de secours, imposable par compte ou pour tout le foyer. |
| **Droits par catégorie et par action** | Voir, modifier, déposer, télécharger, supprimer, gérer les versions — séparément. |
| **Journal d'audit** | Documents, comptes, exports, scripts, **et la configuration du classement**. |
| **Archives en lecture seule pour l'API** | Seul le serveur de travaux écrit dans `storage/`. |

## Ce que vous devez faire

### 1. Ne pas exposer l'API directement

Par défaut, `docker-compose.yml` publie l'API sur `127.0.0.1:8001` — **la machine
seulement**. Ne la publiez pas sur `0.0.0.0` : elle serait joignable sans passer
par nginx, donc sans les en-têtes de sécurité, et son `X-Real-IP` deviendrait
forgeable — ce qui rendrait la limitation des tentatives contournable.

Seul `frontend` (port 8081) a vocation à être joignable.

### 2. HTTPS, et `COOKIE_SECURE`

En clair sur un réseau local, le mot de passe circule en clair. Mettez un proxy
inverse devant (Caddy, Traefik, nginx) et passez `COOKIE_SECURE=true` dans
`.env` : le cookie de session ne partira plus que sur une liaison chiffrée.

```
# Caddyfile — le plus court chemin vers un certificat valide
ged.mondomaine.fr {
    reverse_proxy 127.0.0.1:8081
}
```

### 3. Restreindre `/admin` et `/api/admin/`

L'administration est déjà protégée par les droits ; la restreindre **au réseau**
ajoute une serrure devant la porte. Les deux chemins vont ensemble : protéger la
page sans l'API ne protège rien.

```nginx
# Dans le proxy inverse, devant HomeGED
location /admin        { include /etc/nginx/acces-admin.conf; proxy_pass http://homeged; }
location /api/admin/   { include /etc/nginx/acces-admin.conf; proxy_pass http://homeged; }

# acces-admin.conf
allow 192.168.1.0/24;   # le réseau de la maison
allow 10.8.0.0/24;      # le VPN, si vous en avez un
deny all;
```

Avec Caddy :

```
ged.mondomaine.fr {
    @admin path /admin* /api/admin/*
    handle @admin {
        @interdit not remote_ip 192.168.1.0/24 10.8.0.0/24
        respond @interdit "Interdit" 403
        reverse_proxy 127.0.0.1:8081
    }
    reverse_proxy 127.0.0.1:8081
}
```

> ⚠️ Vérifiez ensuite que vous pouvez **encore** entrer dans l'administration
> depuis le réseau autorisé. Une règle trop stricte s'enferme dehors, et il faut
> alors éditer la configuration du proxy en console.

### 4. fail2ban

Le frontend écrit un journal d'accès au format `combined` dans un fichier
**stable** — `/var/log/homeged/acces.log`, monté depuis l'hôte — précisément pour
que fail2ban puisse le lire. (Le journal Docker, lui, porte l'identifiant du
conteneur dans son nom, qui change à chaque reconstruction.)

`/etc/fail2ban/filter.d/homeged.conf` :

```ini
[Definition]
# Une authentification refusée par l'API : 401 sur /api/auth/login.
failregex = ^<HOST> .* "POST /api/auth/login[^"]*" 401
            ^<HOST> .* "POST /api/auth/otp[^"]*" 401
ignoreregex =
```

`/etc/fail2ban/jail.d/homeged.conf` :

```ini
[homeged]
enabled  = true
port     = http,https
filter   = homeged
logpath  = /var/log/homeged/acces.log
maxretry = 10
findtime = 10m
bantime  = 1h
```

```bash
sudo fail2ban-client reload
sudo fail2ban-client status homeged
```

> La limitation interne de HomeGED (5 tentatives, verrouillage 15 minutes) agit
> **par compte** ; fail2ban agit **par adresse**, et coupe avant que la requête
> n'atteigne l'application. Les deux se complètent, aucune ne remplace l'autre.

> 📸 **Capture à placer ici — `images/tentatives-connexion.png`**
> L'écran « Tentatives de connexion » de l'administration, montrant une adresse
> verrouillée et le bouton pour la débloquer.

### 5. Sauvegarder ailleurs

Une sauvegarde sur le même disque protège d'une fausse manœuvre, pas d'une
panne. Montez un disque externe ou un partage réseau et indiquez son chemin :
voir [Sauvegarde et restauration](Sauvegarde-et-restauration).

### 6. Le mode développeur

L'écran « Scripts » exécute du Python sur le serveur. Il est **éteint par
défaut**, s'arme en connaissance de cause, exige le droit *Réglages* et le statut
d'administrateur, et chaque exécution est journalisée. Laissez-le éteint tant que
vous n'en avez pas besoin.

## Ce qui reste assumé

* `/docs` et `/openapi.json` sont ouverts — mais l'API n'étant joignable que
  depuis la machine, ils ne le sont pas depuis le réseau.
* La liste des émetteurs est lisible par tout compte connecté : ce sont des noms,
  pas des documents.
* Une expression régulière pathologique écrite par un administrateur peut occuper
  le serveur de travaux : Python n'offre pas de délai sur les regex.
