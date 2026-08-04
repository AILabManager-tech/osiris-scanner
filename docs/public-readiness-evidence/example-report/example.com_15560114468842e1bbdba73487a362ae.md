# Rapport OSIRIS — example.com

**URL** : https://example.com/
**Date** : 2026-08-04T17:28:48.171149+00:00
**Version** : OSIRIS 0.3.0 · méthode OSIRIS-6A-2026.1

> Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un avis juridique.
> Automated technical pre-assessment. It does not constitute compliance certification or legal advice.

## 1. Résumé du scan

- État : **complete**
- Mode : **deep**
- Axes évalués : **6/6**
- Durée : **15.737 s**

## 2. Fiabilité et couverture

- Couverture pondérée : **87%**
- Facteur de fiabilité : **0.967**
- Score technique avant pénalité : **6.6/10**

## 3. Score global

**6.4/10 — Risque élevé**

## 4. Scores par axe

| Axe | Score | Poids | Couverture | Statut | Source |
|---|---:|---:|---:|---|---|
| O — Performance | 10.0/10 | 15% | 85% | bon | Playwright Navigation Timing |
| S — Sécurité | 1.0/10 | 25% | 95% | risque élevé | Mozilla Observatory + Headers |
| I — Intrusion | 10.0/10 | 20% | 90% | bon | OSIRIS Deep Analysis (Playwright) |
| R — Ressources | 10.0/10 | 10% | 90% | bon | Deep Analysis (Playwright) + Website Carbon API |
| V — Souveraineté | 6.0/10 | 15% | 90% | risque élevé | Playwright Dynamic Flow Mapping |
| L — Signaux vie privée | 6.2/10 | 15% | 65% | donnée insuffisante | OSIRIS Technical Privacy Signals (Playwright) |

## 5. Problèmes prioritaires

- **S — Sécurité** : En-têtes absents ou non observés : strict-transport-security, content-security-policy, x-frame-options, x-content-type-options, referrer-policy, permissions-policy.
- **V — Souveraineté** : 4 destination(s) apparente(s) hors Canada.
- **L — Signaux vie privée** : Aucun lien de confidentialité visible n'a été observé.

## 6. Observations techniques

### O — Performance

- DOMContentLoaded observé à 136 ms.

### S — Sécurité

- 0/6 en-têtes de sécurité observés.
- Mozilla Observatory a retourné le grade technique F.

### I — Intrusion

- 0 domaine(s) de traçage connu(s) parmi 1 domaine(s).

### R — Ressources

- 1 réponse(s) réseau pour 0.5 KiB transférés.

### V — Souveraineté

- 4 destination(s) réseau observée(s).

### L — Signaux vie privée

- 0 traceur(s) connu(s) avant interaction.
- Le comportement après refus n'a pas pu être évalué.

## 7. Preuves

### O — Performance

- `{"domContentLoaded": 135.90000000596046, "firstContentfulPaint": 152, "loadEvent": 136.09999999403954, "responseStart": 131.90000000596046, "transferSize": 859, "type": "navigation_timing", "wallTime": 665.7}`

### S — Sécurité

- `{"name": "strict-transport-security", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "content-security-policy", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "x-frame-options", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "x-content-type-options", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "referrer-policy", "present": false, "quality": 0.0, "type": "security_header"}`
- `{"name": "permissions-policy", "present": false, "quality": 0.0, "type": "security_header"}`

### R — Ressources

- `{"bytes": 559, "estimated_gco2": 0.0001, "requests": 1, "type": "resource_weight"}`

### V — Souveraineté

- `{"asn": 13335, "country": "US", "host": "example.com", "ip": "104.20.23.154", "organization": "Cloudflare, Inc.", "type": "network_destination"}`
- `{"asn": 13335, "country": "US", "host": "example.com", "ip": "172.66.147.243", "organization": "Cloudflare, Inc.", "type": "network_destination"}`
- `{"asn": 13335, "country": "US", "host": "example.com", "ip": "2606:4700:10::6814:179a", "organization": "Cloudflare, Inc.", "type": "network_destination"}`
- `{"asn": 13335, "country": "US", "host": "example.com", "ip": "2606:4700:10::ac42:93f3", "organization": "Cloudflare, Inc.", "type": "network_destination"}`

## 8. Recommandations

- **O — Performance** : Maintenir les contrôles observés et revalider après chaque changement majeur.
- **S — Sécurité** : Configurer et vérifier les en-têtes manquants selon le contexte de l'application.
- **I — Intrusion** : Maintenir les contrôles observés et revalider après chaque changement majeur.
- **R — Ressources** : Maintenir les contrôles observés et revalider après chaque changement majeur.
- **V — Souveraineté** : Vérifier les finalités, contrats et régions de traitement des services externes.
- **L — Signaux vie privée** : Faire valider les finalités, le consentement et les mentions par une personne qualifiée.

## 9. Limites

- Les mesures dépendent du réseau, du rendu observé et de services externes.
- Une absence de preuve n'est ni une réussite ni la preuve d'une absence de risque.
- Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un avis juridique.
- Automated technical pre-assessment. It does not constitute compliance certification or legal advice.
- **O** : Mesure locale Playwright; elle ne remplace pas un jeu de données utilisateur réel.
- **I** : La blocklist n'est pas exhaustive et peut produire des omissions.
- **R** : L'estimation carbone est indicative et dépend d'un modèle externe.
- **V** : La géolocalisation IP est indicative et ne prouve pas le lieu juridique de traitement.
- **L** : Le clic automatisé ne couvre pas toutes les bannières ni tous les parcours.
- **L** : Les observations techniques ne constituent ni une certification ni un avis juridique.

## 10. Méthodologie

- Version : `OSIRIS-6A-2026.1`
- Formule : `Score technique = Σ(axe × poids); score publié = score technique × (0,75 + 0,25 × couverture)`
- Poids : `{"O": 0.15, "S": 0.25, "I": 0.2, "R": 0.1, "V": 0.15, "L": 0.15}`

---
*Un outil Auxo Systems · OSIRIS Scanner v0.3.0*
