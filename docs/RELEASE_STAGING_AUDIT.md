# Audit local de release/staging

Audit effectué le 2026-08-06 à partir du dépôt et du handoff packaging. Aucun service externe
n'a été contacté et aucun déploiement n'a été effectué.

## Contrôles confirmés localement

- `Dockerfile` utilise une base Python épinglée par digest, un utilisateur non-root (UID 10001),
  un système de fichiers non privilégié et une image sans artefacts de tests grâce à `.dockerignore`.
- `docker-compose.yml` borne CPU, mémoire, PIDs, `/tmp`, mémoire partagée et connexions; le port est
  publié sur `127.0.0.1` seulement et `/health` est utilisé par le healthcheck.
- Le serveur intégré borne les jobs, workers, connexions et délais; l'interface ajoute CSP,
  `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` et `Cache-Control`.
- L'adaptateur serverless applique désormais le même socle d'en-têtes et rejette explicitement les
  corps JSON qui ne sont pas des objets.

## Bloqueurs d'infrastructure (à traiter avant exposition publique)

- Le dépôt ne fournit pas de reverse proxy ni de terminaison TLS. Une exposition Internet exige un
  proxy maintenu avec certificat TLS, redirection HTTP→HTTPS et limites de taille/délai adaptées.
- Compose n'impose pas de politique egress au niveau réseau. OSIRIS doit pouvoir joindre ses cibles
  et fournisseurs documentés, mais la production doit appliquer une allowlist egress au niveau de
  l'hôte, du réseau ou du fournisseur; ce réglage ne peut pas être inventé dans ce dépôt.
- Le serveur intégré limite la concurrence mais ne fournit pas de rate limiting persistant par
  client. Le proxy ou la plateforme serverless doit appliquer une limite distribuée et un quota
  d'abus avant publication.
- La vérification Gitleaks/équivalent reste à exécuter dans une CI ou un environnement approuvé;
  l'alternative locale du handoff ne remplace pas cette preuve externe.

Ces points sont des prérequis de staging/production, pas des corrections applicables sans choisir
une infrastructure et ses paramètres d'exploitation.

