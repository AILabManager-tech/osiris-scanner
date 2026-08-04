# Méthodologie OSIRIS-6A-2026.1

## Objet

OSIRIS produit un prédiagnostic technique reproductible, pas une certification. Les six scores
décrivent uniquement les observations réalisées par les sources indiquées dans le rapport.

> Prédiagnostic technique automatisé. Ne constitue pas une certification de conformité ni un avis
> juridique.

## Calcul

Les poids sont O 0,15; S 0,25; I 0,20; R 0,10; V 0,15; L 0,15. Leur somme est 1.

Pour les axes produits :

```text
score technique = Σ(score axe × poids) / Σ(poids disponibles)
couverture = Σ(couverture axe × poids canonique)
facteur de fiabilité = 0,75 + 0,25 × couverture
score publié = score technique × facteur de fiabilité
```

Les scores et facteurs sont bornés. Le facteur vaut 1 seulement avec une couverture totale; il ne
peut augmenter le score technique. Un axe absent n’est jamais remplacé par zéro : zéro signifie une
mesure réellement produite à 0, tandis qu’un axe absent demeure `non évalué` ou `erreur technique`.

## Couverture par mode

La couverture reflète la profondeur de la preuve, pas la qualité du site. Par exemple, une analyse
HTML statique des traceurs peut obtenir un score I élevé avec une couverture partielle, car les
scripts injectés après rendu ne sont pas observés. Les valeurs précises sont incluses dans chaque
`AxisResult` et le rapport.

## Interprétation des axes

- **O — Performance** : temps de réponse HTTP en mode rapide; chronométrage de navigation et rendu
  en mode approfondi. Aucune donnée utilisateur réelle n’est affirmée.
- **S — Sécurité** : qualité observable de six en-têtes et grade Observatory si disponible. L’échec
  d’Observatory conserve l’analyse locale avec couverture réduite.
- **I — Intrusion** : correspondance de domaines avec la blocklist embarquée. Le résultat décrit des
  indicateurs de traçage, pas l’intention du fournisseur.
- **R — Ressources** : octets mesurés, ressources référencées et estimation gCO2. Le modèle carbone
  est indicatif.
- **V — Souveraineté** : pays et ASN apparents des IP observées. Une IP ou un siège social ne prouve
  pas le lieu juridique de traitement.
- **L — Signaux vie privée** : traceurs avant interaction, contrôle de refus détectable, lien de
  confidentialité et signal de contact. Ces indices ne déterminent aucune conformité globale.

## Statuts

| Statut | Règle |
|---|---|
| bon | couverture suffisante et score ≥ 8,5 |
| à surveiller | couverture suffisante et score ≥ 6,5 |
| risque élevé | couverture suffisante et score < 6,5 |
| donnée insuffisante | résultat présent avec couverture < 70 % |
| non évalué | aucune donnée ni erreur spécifique |
| erreur technique | outil ou source en échec |

Le statut du scan est `complete` si les six axes produisent leur mesure demandée, `partial` si un
axe manque ou se replie après une erreur du mode approfondi, et `failed` si aucune donnée exploitable
n’est produite ou si la cible est refusée.

## Profil Diagnostic technique Loi 25

Le profil met en évidence S, I, V et L sans recalculer un score parallèle. Il sélectionne les preuves
liées aux traceurs, scripts tiers, consentement observable, politique de confidentialité, sécurité
technique, souveraineté apparente et services externes. Une interprétation juridique exige le
contexte organisationnel, les finalités, les contrats, les processus et une personne qualifiée.

## Versionnement

Toute modification des axes, poids, seuils, facteurs ou règles de couverture exige une nouvelle
version de méthodologie et des fixtures de comparaison. Les résultats antérieurs à
`OSIRIS-6A-2026.1` ne sont pas directement comparables.
