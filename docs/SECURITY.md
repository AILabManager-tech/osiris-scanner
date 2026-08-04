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
4. validation de chaque IP DNS : seulement les adresses globales publiques;
5. refus d’une réponse DNS mixte public/privé;
6. résolution répétée par le connecteur au moment de la connexion;
7. redirections manuelles, revalidées une à une, maximum cinq;
8. navigateur Playwright intercepté pour chaque navigation et sous-ressource;
9. aucune décision DNS autorisée mise en cache;
10. services workers bloqués en mode navigateur;
11. 30 secondes par requête, 180 secondes globales et réponse maximale de 5 MiB;
12. aucun schéma `file:`, `ftp:`, `data:` ou `javascript:` comme cible principale.

Les fixtures de test peuvent activer `NetworkPolicy(allow_private=True, allowed_ports=None)` pour un
serveur local contrôlé. Cette politique n’est jamais la valeur par défaut du CLI ou de l’interface.

## Surface web

L’interface limite le corps des requêtes à 4 KiB, le nombre de jobs actifs à quatre et les workers à
deux. Elle sert une CSP restrictive, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, une
`Permissions-Policy` restrictive et `Cache-Control: no-store`. Les données dynamiques sont insérées
avec `textContent`, jamais avec `innerHTML`.

## Conteneur

Le conteneur s’exécute comme UID 10001, avec système de fichiers en lecture seule dans Compose,
`no-new-privileges`, `/tmp` borné et mémoire partagée dédiée au navigateur. Aucun secret n’est requis.

## Services externes

Les appels à Observatory, Green Web Foundation, Website Carbon et ipwho.is utilisent des endpoints
constants. Aucune réponse externe n’est exécutée. Les erreurs réduisent la couverture ou déclenchent
un repli documenté.

## Limites et divulgation

La protection DNS réduit le risque de rebinding mais dépend du résolveur et de la pile réseau du
système. OSIRIS ne doit pas être placé dans un réseau hautement privilégié sans isolation réseau
supplémentaire. Signaler confidentiellement une vulnérabilité à Auxo Systems avant publication.

Ce contrôle automatisé ne remplace pas un audit de sécurité professionnel.
