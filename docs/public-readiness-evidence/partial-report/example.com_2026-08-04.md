# Rapport OSIRIS — example.com

**URL** : https://example.com/
**Date** : 2026-08-04T07:41:40.045116+00:00
**Version** : OSIRIS 0.3.0 · méthode OSIRIS-6A-2026.1

> Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un avis juridique.
> Automated technical pre-assessment. It does not constitute compliance certification or legal advice.

## 1. Résumé du scan

- État : **partial**
- Mode : **deep**
- Axes évalués : **6/6**
- Durée : **0.857 s**

## 2. Fiabilité et couverture

- Couverture pondérée : **68%**
- Facteur de fiabilité : **0.921**
- Score technique avant pénalité : **6.7/10**

## 3. Score global

**6.2/10 — Risque élevé**

## 4. Scores par axe

| Axe | Score | Poids | Couverture | Statut | Source |
|---|---:|---:|---:|---|---|
| O — Performance | 10.0/10 | 15% | 60% | donnée insuffisante | Protected HTTP Timing |
| S — Sécurité | 1.0/10 | 25% | 95% | risque élevé | Mozilla Observatory + Headers |
| I — Intrusion | 10.0/10 | 20% | 65% | donnée insuffisante | OSIRIS Blocklist Analysis |
| R — Ressources | 10.0/10 | 10% | 55% | donnée insuffisante | Page Weight + Website Carbon API |
| V — Souveraineté | 8.0/10 | 15% | 60% | donnée insuffisante | DNS + HTML Static Flow Mapping |
| L — Signaux vie privée | 5.0/10 | 15% | 55% | donnée insuffisante | OSIRIS Technical Privacy Signals (HTML) |

## 5. Problèmes prioritaires

- **S — Sécurité** : En-têtes absents ou non observés : strict-transport-security, content-security-policy, x-frame-options, x-content-type-options, referrer-policy, permissions-policy.
- **V — Souveraineté** : 2 destination(s) apparente(s) hors Canada.
- **L — Signaux vie privée** : Aucun lien de politique de confidentialité n'a été observé dans le HTML.

## 6. Observations techniques

### O — Performance

- Réponse principale reçue en 86 ms.

### S — Sécurité

- 0/6 en-têtes de sécurité observés.
- Mozilla Observatory a retourné le grade technique F.

### I — Intrusion

- 0 domaine(s) de traçage connu(s) dans le HTML statique.

### R — Ressources

- 1 ressource(s) référencée(s); 0.5 KiB mesurés.

### V — Souveraineté

- 2 destination(s) réseau observée(s).

### L — Signaux vie privée

- 0 domaine(s) de traçage connu(s) dans le HTML statique.
- 0 lien(s) de confidentialité visible(s).

## 7. Preuves

### O — Performance

- `{"elapsed_ms": 86.3, "redirects": [], "status": 200, "transfer_bytes": 559, "type": "http_timing"}`

### S — Sécurité

- `{"name": "strict-transport-security", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "content-security-policy", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "x-frame-options", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "x-content-type-options", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "referrer-policy", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "permissions-policy", "present": false, "quality": 0.0, "type": "security_header"}`

### R — Ressources

- `{"bytes": 559, "estimated_gco2": 0.0001, "referenced_resources": 1, "source": "HTML principal", "type": "resource_weight"}`

### V — Souveraineté

- `{"asn": 13335, "country": "US", "host": "example.com", "ip": "172.66.147.243", "organization": "Cloudflare, Inc.", "type": "network_destination"}`
- `{"asn": 16876, "country": "US", "host": "iana.org", "ip": "192.0.43.8", "organization": "ICANN", "type": "network_destination"}`

## 8. Recommandations

- **O — Performance** : Maintenir les contrôles observés et revalider après chaque changement majeur.
- **S — Sécurité** : Configurer et vérifier les en-têtes manquants selon le contexte de l'application.
- **I — Intrusion** : Maintenir les contrôles observés et revalider après chaque changement majeur.
- **R — Ressources** : Maintenir les contrôles observés et revalider après chaque changement majeur.
- **V — Souveraineté** : Vérifier les finalités, contrats et régions de traitement des services externes.
- **L — Signaux vie privée** : Rendre la politique de confidentialité clairement accessible.
- **L — Signaux vie privée** : Rendre le contrôle de consentement observable et accessible au clavier.

## 9. Limites

- Scan partiel : au moins un axe a rencontré une erreur technique.
- Les mesures dépendent du réseau, du rendu observé et de services externes.
- Une absence de preuve n'est ni une réussite ni la preuve d'une absence de risque.
- Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un avis juridique.
- Automated technical pre-assessment. It does not constitute compliance certification or legal advice.
- **O** : Mode rapide : le temps HTTP ne mesure ni le rendu JavaScript ni les Core Web Vitals.
- **O** : Lighthouse historique est désactivé sur les cibles non fiables pour éviter le SSRF par sous-ressource.
- **O** : Mesure approfondie indisponible; repli HTTP sécurisé : BrowserType.launch: Executable doesn't exist at /tmp/osiris-browser-intentionally-unavailable/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell
- **I** : Mode rapide : les traceurs injectés après exécution JavaScript ne sont pas observés.
- **I** : La blocklist n'est pas exhaustive et peut produire des omissions.
- **I** : Repli statique après échec Playwright : BrowserType.launch: Executable doesn't exist at /tmp/osiris-browser-intentionally-unavailable/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell
- **R** : Mode rapide : le poids du HTML ne couvre pas toutes les sous-ressources.
- **R** : Repli HTML après échec Playwright : BrowserType.launch: Executable doesn't exist at /tmp/osiris-browser-intentionally-unavailable/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell
- **V** : La géolocalisation IP est indicative et ne prouve pas le lieu juridique de traitement.
- **V** : Mode rapide : seuls les hôtes visibles dans le HTML statique sont cartographiés.
- **V** : Repli DNS/HTML après échec Playwright : BrowserType.launch: Executable doesn't exist at /tmp/osiris-browser-intentionally-unavailable/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell
- **L** : Mode rapide : aucun clic de refus ni chargement JavaScript n'est évalué.
- **L** : Les signaux observés ne permettent pas de conclure à une conformité juridique.
- **L** : Repli HTML après échec Playwright : BrowserType.launch: Executable doesn't exist at /tmp/osiris-browser-intentionally-unavailable/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell

## 10. Méthodologie

- Version : `OSIRIS-6A-2026.1`
- Formule : `Score technique = Σ(axe × poids); score publié = score technique × (0,75 + 0,25 × couverture)`
- Poids : `{"O": 0.15, "S": 0.25, "I": 0.2, "R": 0.1, "V": 0.15, "L": 0.15}`

---
*Un outil Auxo Systems · OSIRIS Scanner v0.3.0*
