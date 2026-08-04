# Sécurité du scanner

## Modèle de menace

L’entrée principale est une URL contrôlée par l’utilisateur. La menace prioritaire est un SSRF vers
le poste local, le réseau privé, les métadonnées cloud ou un service atteint après redirection ou
rebinding DNS. Les réponses volumineuses, lentes ou cycliques sont aussi traitées comme hostiles.

## Contrôles appliqués

`url_security.py` applique une politique fail-closed :

1. schémas HTTP/HTTPS seulement et aucun identifiant dans l’URL;
2. ports 80/443 seulement en politique publique;
3. refus des noms localhost et métadonnées connus;
4. validation de chaque IP DNS : seulement les adresses globales publiques unicast;
5. refus d’une réponse DNS mixte public/privé;
6. résolution répétée par le connecteur au moment de la connexion;
7. redirections manuelles, revalidées une à une, maximum cinq;
8. navigateur Playwright intercepté pour chaque navigation et sous-ressource;
9. relais des requêtes Playwright par `safe_fetch`; Chromium ne résout ni ne contacte la cible;
10. aucune décision DNS autorisée mise en cache;
11. services workers bloqués en mode navigateur;
12. 30 secondes par requête, 180 secondes globales, 5 MiB par réponse et 20 MiB par axe
    navigateur;
13. aucun schéma `file:`, `ftp:`, `data:` ou `javascript:` comme cible principale.

Les fixtures de test peuvent activer `NetworkPolicy(allow_private=True, allowed_ports=None)` pour un
serveur local contrôlé. Cette politique n’est jamais la valeur par défaut du CLI ou de l’interface.

## Surface web

L’interface limite le corps des requêtes à 4 KiB, le nombre de jobs actifs à quatre, les workers à
deux et les connexions simultanées à 32. Chaque socket expire après dix secondes d’inactivité. Elle
sert une CSP restrictive, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, une
`Permissions-Policy` restrictive et `Cache-Control: no-store`. Les données dynamiques sont insérées
avec `textContent`, jamais avec `innerHTML`.

## Conteneur

Le conteneur s’exécute comme UID 10001, avec système de fichiers en lecture seule dans Compose,
`no-new-privileges`, `/tmp` borné, 1 GiB de mémoire, deux CPU, 256 processus au maximum et mémoire
partagée dédiée au navigateur. Le port Compose est publié sur `127.0.0.1` seulement. Aucun secret
n’est requis.

## Services externes

Les appels à Observatory, Green Web Foundation, Website Carbon et ipwho.is utilisent des endpoints
constants. Aucune réponse externe n’est exécutée. Les erreurs réduisent la couverture ou déclenchent
un repli documenté.

## Limites et divulgation

Le connecteur HTTP épingle l’adresse autorisée obtenue par son résolveur contrôlé. Le navigateur
reçoit les réponses par interception et n’effectue pas une seconde connexion réseau. OSIRIS ne doit
malgré tout pas être placé dans un réseau hautement privilégié sans isolation egress supplémentaire.
Le serveur HTTP intégré est une interface de démonstration locale; une exposition Internet permanente
exige toujours TLS et un reverse proxy maintenu. Signaler confidentiellement une vulnérabilité à
Auxo Systems avant publication.

Ce contrôle automatisé ne remplace pas un audit de sécurité professionnel.
