# Revalidation indépendante du ruleset Loi 25 d’OSIRIS

**Date :** 5 août 2026  
**Périmètre audité :** les **5 règles réellement présentes** dans `rulesets/loi25.ruleset.yaml`, branche `backup/full-sync-2026-07-17`.  
**Commit audité :** `6d6102db463ce9b59b951786af74fb98bf715253`  
**Source normative exclusive :** *Loi sur la protection des renseignements personnels dans le secteur privé*, RLRQ c. P-39.1, texte officiel de LégisQuébec à jour au 1er avril 2026.  
**Sources secondaires :** pages et lignes directrices de la Commission d’accès à l’information (CAI), utilisées uniquement pour expliquer l’application du texte légal.

## 1. Verdict de validation

Le ruleset historique ne peut pas être utilisé comme moteur automatique de conformité juridique.

1. Ses cinq règles portent encore une source `TODO`, alors que le fichier exige lui-même une source officielle vérifiée avant toute assertion de conformité.
2. Le moteur contredit ce garde-fou : une règle non sourcée qui échoue produit actuellement `non_conforme`; seule une règle non sourcée qui passe produit `indetermine`.
3. Trois règles sur cinq — traceurs avant consentement, mécanisme de refus et traceurs après refus — ne correspondent pas à des obligations textuelles autonomes de P-39.1. Ce sont au mieux des **signaux techniques à qualifier juridiquement**.
4. Deux règles ont un fondement légal direct : publication du titre et des coordonnées du RPRP (art. 3.1) et publication d’une politique de confidentialité lorsqu’il y a collecte technologique de renseignements personnels (art. 8.2). Même pour celles-ci, une URL seule établit une publication observée ou un écart public apparent, pas la conformité globale de l’entreprise.

## 2. États de sortie requis

Les résultats doivent conserver deux dimensions séparées :

- `technical_observation` : fait capturé ou anomalie technique, borné au périmètre testé;
- `legal_status` : applicabilité ou qualification juridique, qui peut rester indéterminée.

Une anomalie technique et un statut juridique indéterminé peuvent donc coexister. Ils ne doivent pas être fusionnés dans un verdict unique.

Les combinaisons indiquées dans les tableaux sont des résultats attendus de validation, pas un enum exécutable. L’implémentation doit mapper explicitement chaque observation technique et chaque statut juridique dans leurs champs respectifs.

| État | Sens |
|---|---|
| `FAIT_OBSERVE` | Élément public ou technique effectivement capturé, sans conclusion juridique. |
| `CONTROLE_TECHNIQUE_OBSERVE` | Comportement favorable observé dans la session et le périmètre testés seulement. |
| `ANOMALIE_TECHNIQUE` | Comportement qui justifie une analyse, sans être automatiquement une violation. |
| `ECART_PUBLIC_APPARENT` | Élément expressément exigé sur le site et non trouvé après un crawl suffisamment complet. |
| `INDETERMINE_SOURCE` | Fondement normatif absent, provisoire ou non vérifié. Aucune sortie `pass` ou `fail` juridique. |
| `INDETERMINE_APPLICABILITE` | Le scanner ne peut pas établir que l’obligation s’applique au cas observé. |
| `INDETERMINE_SCAN` | Couverture, interaction, rendu ou accès insuffisant pour conclure. |
| `INDETERMINE_INTERNE` | Preuve organisationnelle, contractuelle ou opérationnelle interne requise. |
| `INDETERMINE_JURIDIQUE` | Qualification ou appréciation juridique requise. |

**Interdiction :** un scan URL-only ne doit jamais produire `CONFORME_LOI25`. Une règle non suffisamment sourcée doit sortir `INDETERMINE_SOURCE`, que le fait technique soit favorable ou défavorable.

Chaque règle doit conserver sa provenance normative : `source_url`, article(s) officiel(s) et `source_verified_at`.

---

## 3. Matrice corrigée des cinq règles réelles

### 3.1 `loi25-traceurs-pre-consentement`

| Champ | Validation indépendante |
|---|---|
| **Règle historique** | « Aucun traceur/cookie non essentiel ne doit se déclencher avant l’obtention d’un consentement libre et éclairé. » |
| **Article officiel pertinent** | **Art. 8.1** : lorsqu’une collecte de renseignements personnels recourt à une technologie permettant d’identifier, localiser ou profiler, l’entreprise doit informer la personne au préalable du recours à cette technologie et des moyens offerts pour activer ces fonctions. **Art. 14** : lorsqu’un consentement est prévu par la loi, il doit notamment être manifeste, libre, éclairé et spécifique. |
| **Obligation exacte** | P-39.1 ne formule pas une interdiction générale visant tout « cookie non essentiel » ou tout domaine inscrit dans une blocklist. L’applicabilité dépend de l’existence d’un renseignement personnel, de la fonction technologique, de la finalité et du régime juridique de l’utilisation ou de la communication. La CAI explique l’art. 8.1 comme exigeant que les fonctions d’identification, de localisation ou de profilage ne soient pas activées par défaut; cette explication demeure secondaire au texte légal. |
| **Fait observable par OSIRIS** | Requête réseau adressée, avant interaction, à un domaine présent dans la blocklist; URL, domaine, heure, type de ressource et état du navigateur. |
| **Information interne requise** | Finalité du service tiers, données réellement transmises, configuration serveur, rôle du fournisseur, traitement côté serveur, base juridique retenue. |
| **Jugement juridique requis** | La requête contient-elle ou révèle-t-elle un renseignement personnel? La technologie identifie-t-elle, localise-t-elle ou profile-t-elle? Un consentement est-il requis? Une exception ou une finalité primaire s’applique-t-elle? Le service est-il réellement « non essentiel »? |
| **Limite décisive du scan** | Une correspondance de blocklist ne démontre ni la nature des données ni l’obligation de consentement. L’absence de correspondance ne démontre pas l’absence de collecte, de profilage ou de traitement serveur. |
| **Verdict attendu** | Domaine détecté → `ANOMALIE_TECHNIQUE` + `INDETERMINE_JURIDIQUE`. Aucun domaine détecté → `FAIT_OBSERVE` (« aucun domaine de la liste observé dans cette session »), jamais `conforme`. Source non vérifiée → `INDETERMINE_SOURCE`. |
| **Décision sur la règle** | **Retirer du score juridique pass/fail.** Conserver comme signal technique dans l’axe « Signaux vie privée ». |

### 3.2 `loi25-mecanisme-de-refus`

| Champ | Validation indépendante |
|---|---|
| **Règle historique** | « Un mécanisme de refus du consentement doit être offert, aussi simple que le mécanisme d’acceptation. » |
| **Article officiel pertinent** | **Art. 14** : un consentement prévu par la loi doit être libre, manifeste, éclairé, spécifique, granulaire, simple et clair, et distinct lorsqu’il est écrit. |
| **Obligation exacte** | Les mots « aussi simple que l’acceptation » ne figurent pas comme obligation autonome dans P-39.1. La CAI interprète le caractère libre comme exigeant qu’il soit aussi facile de consentir que de ne pas consentir et que les choix soient présentés équitablement. C’est une ligne directrice d’application, pas le texte de l’article 14. |
| **Fait observable par OSIRIS** | Présence d’une interface de consentement; présence d’un contrôle de refus; nombre de clics; visibilité, libellé et ordre des contrôles; parcours avant et après choix. |
| **Information interne requise** | Finalités associées à l’interface, conséquences réelles du refus, persistance du choix, traitement backend et éventuelles autres interfaces. |
| **Jugement juridique requis** | Un consentement est-il requis pour les finalités visées? Le choix est-il réellement libre? La présentation influence-t-elle indûment la personne? Les options sont-elles équitables dans le contexte? |
| **Limite décisive du scan** | Le code historique ne mesure pas l’équité ni la simplicité comparative : il cherche seulement des mots dans des boutons, liens ou `span`, y compris le motif générique `non`. L’absence d’un bouton sur la page d’entrée peut aussi signifier qu’aucune demande de consentement n’est applicable ou que l’interface apparaît ailleurs. |
| **Verdict attendu** | Interface applicable + refus fiable observé → `FAIT_OBSERVE`. Interface applicable + refus absent ou nettement plus difficile → `ANOMALIE_TECHNIQUE` + `INDETERMINE_JURIDIQUE`. Aucune interface applicable établie → `INDETERMINE_APPLICABILITE`. Scan incomplet → `INDETERMINE_SCAN`. |
| **Décision sur la règle** | **Déclasser en contrôle d’interface.** Ne doit jamais être bloquante sur la seule détection DOM. |

### 3.3 `loi25-respect-du-refus`

| Champ | Validation indépendante |
|---|---|
| **Règle historique** | « Lorsque la personne refuse, les traceurs non essentiels ne doivent pas se déclencher. » |
| **Articles officiels pertinents** | **Art. 8, par. 4°** : informer la personne de son droit de retirer son consentement à la communication ou à l’utilisation. **Art. 14** : critères de validité du consentement. **Art. 22** : en prospection commerciale ou philanthropique, l’utilisation visée doit cesser lorsque la personne retire son consentement. Selon le contexte, les art. 12 et 13 encadrent aussi l’utilisation et la communication. |
| **Obligation exacte** | Le texte légal ne transforme pas automatiquement toute requête vers un domaine de blocklist après un clic de refus en violation. Il faut établir que le choix était valable, que le traitement observé est couvert par ce choix, qu’il implique des renseignements personnels et qu’aucune autre base ou exception ne s’applique. |
| **Fait observable par OSIRIS** | Requêtes réseau capturées après le clic sur un contrôle de refus fiable, dans une session fraîche, avec preuve du contrôle cliqué et du moment de la requête. |
| **Information interne requise** | Finalité de chaque requête, données transmises, traitements serveur, persistance du choix, classification essentiel/non essentiel, base juridique. |
| **Jugement juridique requis** | Le refus couvrait-il réellement ce traitement? Le traitement nécessitait-il un consentement? La requête constitue-t-elle une utilisation ou une communication visée par la loi? |
| **Limite décisive du scan** | Le code historique clique le premier élément correspondant à une liste de mots et considère toute requête de blocklist comme un traceur non essentiel. Il peut cliquer le mauvais élément et ne voit pas les traitements serveur ou différés. |
| **Verdict attendu** | Requête suspecte après refus fiable → `ANOMALIE_TECHNIQUE` + `INDETERMINE_JURIDIQUE`. Aucune requête suspecte → `CONTROLE_TECHNIQUE_OBSERVE` dans la session seulement. Refus non fiable ou absent → `INDETERMINE_SCAN` ou `INDETERMINE_APPLICABILITE`, jamais `non_applicable` automatiquement. |
| **Décision sur la règle** | **Conserver comme test comportemental**, mais supprimer la conclusion juridique automatique et la pénalité bloquante. |

### 3.4 `loi25-designation-rpp`

| Champ | Validation indépendante |
|---|---|
| **Règle historique** | « L’entreprise doit désigner un RPP et publier son titre et ses coordonnées. » |
| **Article officiel** | **Art. 3.1.** |
| **Obligation exacte** | L’entreprise est responsable des renseignements qu’elle détient. La personne ayant la plus haute autorité exerce la fonction de RPRP, sauf délégation écrite. **Le titre et les coordonnées du RPRP doivent être publiés sur le site Web**, ou rendus accessibles autrement si l’entreprise n’a pas de site. Le texte n’exige pas nécessairement la publication du nom personnel. |
| **Fait observable par OSIRIS** | Présence conjointe d’un titre ou rôle correspondant à la fonction de RPRP et d’au moins une coordonnée utilisable, avec URL, extrait et lien source. |
| **Information interne requise** | Identité de la plus haute autorité, existence et portée d’une délégation écrite, exercice effectif du rôle. |
| **Jugement juridique requis** | Le libellé publié désigne-t-il suffisamment la fonction? Les coordonnées permettent-elles réellement de joindre le responsable? |
| **Limite décisive du scan** | Un scan d’une seule page ne peut soutenir une absence. Le détecteur historique est techniquement défectueux : son expression régulière cherche `privacy|rpp|confidentialite|legal` au début du **domaine après `@`**, de sorte qu’une adresse normale comme `rpp@entreprise.ca` n’est pas reconnue. Une simple adresse générique ne prouve par ailleurs pas la publication du titre. |
| **Verdict attendu** | Titre + coordonnées trouvés → `FAIT_OBSERVE` (publication observée au regard de l’art. 3.1). Élément manquant après crawl complet → `ECART_PUBLIC_APPARENT`. Couverture insuffisante → `INDETERMINE_SCAN`. Désignation ou délégation réelle → `INDETERMINE_INTERNE`. |
| **Décision sur la règle** | **Conserver**, mais réécrire le détecteur et remplacer `pass/fail` par publication observée / écart public apparent / indéterminé. |

### 3.5 `loi25-politique-confidentialite-publiee`

| Champ | Validation indépendante |
|---|---|
| **Règle historique** | « Une politique de confidentialité claire doit être publiée et accessible. » |
| **Article officiel** | **Art. 8.2.** L’art. 3.2 porte plutôt sur les politiques et pratiques de gouvernance et constitue une obligation publique distincte. |
| **Obligation exacte** | Lorsqu’une entreprise recueille des renseignements personnels par un moyen technologique, elle doit publier sur son site et diffuser une politique de confidentialité rédigée en termes simples et clairs. Toute modification doit également faire l’objet d’un avis diffusé. L’obligation est donc **conditionnelle à une collecte technologique de renseignements personnels**. |
| **Fait observable par OSIRIS** | Existence d’un lien; accessibilité réelle de la cible; contenu identifiable comme politique de confidentialité; formulaires ou flux montrant une collecte technologique possible; version ou avis de modification lorsqu’il existe. |
| **Information interne requise** | Collectes non visibles, flux serveur, pratiques réelles, historique des modifications et moyens de diffusion utilisés. |
| **Jugement juridique requis** | Les données recueillies sont-elles des renseignements personnels? La politique est-elle simple, claire et adéquate? Correspond-elle aux pratiques réelles? Un avis de modification était-il requis? |
| **Limite décisive du scan** | Un lien textuel seul ne prouve ni l’applicabilité de l’art. 8.2, ni l’accessibilité de la page, ni la clarté du contenu, ni sa concordance avec les pratiques. Le détecteur historique accepte tout lien dont le texte contient le mot très large `protection`. |
| **Verdict attendu** | Collecte de renseignements personnels établie + politique accessible → `FAIT_OBSERVE` (publication observée au regard de l’art. 8.2); clarté et adéquation restent `INDETERMINE_JURIDIQUE`. Collecte établie + politique absente après crawl complet → `ECART_PUBLIC_APPARENT`. Collecte non établie → `INDETERMINE_APPLICABILITE`. Lien seul → `FAIT_OBSERVE`, jamais `conforme`. |
| **Décision sur la règle** | **Conserver sous condition d’applicabilité**, avec vérification de la cible et sans assimilation à l’art. 3.2. |

---

## 4. Obligation publique manquante du ruleset

### `loi25-gouvernance-publique` — art. 3.2

P-39.1 exige la publication d’informations détaillées, simples et claires au sujet des politiques et pratiques de gouvernance, notamment sur :

- la conservation et la destruction;
- les rôles et responsabilités du personnel pendant le cycle de vie des renseignements;
- le processus de traitement des plaintes.

OSIRIS peut rechercher la présence publique de ces trois thèmes. Il ne peut pas prouver la mise en œuvre, l’approbation par le RPRP, la proportionnalité des pratiques ni leur efficacité. Les sorties appropriées sont `FAIT_OBSERVE` (publication observée au regard de l’art. 3.2), `ECART_PUBLIC_APPARENT` après crawl complet, ou `INDETERMINE_SCAN`; jamais une certification globale.

---

## 5. Contrôles qui doivent rester hors verdict URL-only

| Contrôle | Article officiel | Ce qu’une URL peut montrer | Ce qu’elle ne peut pas prouver | Sortie obligatoire |
|---|---:|---|---|---|
| EFVP d’un projet de système ou de prestation électronique | 3.3 | Éventuelle déclaration publique | Existence, date, portée, analyse, consultation du RPRP, décisions de mitigation | `INDETERMINE_INTERNE` |
| Registre et gestion des incidents de confidentialité | 3.5 à 3.8 | Éventuel avis public d’incident | Registre complet, incidents non publics, évaluation du préjudice, notifications et mesures prises | `INDETERMINE_INTERNE`; qualification du préjudice → `INDETERMINE_JURIDIQUE` |
| Durée réelle de conservation, destruction et anonymisation | 3.2, 8 et 23 | Déclarations publiques et cadre de gouvernance | Durées appliquées, sauvegardes, délais légaux, journaux de suppression, irréversibilité | `INDETERMINE_INTERNE` |
| Communication ou traitement hors Québec | 8 et 17 | Domaine tiers, destination réseau, fournisseur déclaré, mention publique | Transmission réelle d’un renseignement personnel, destination juridique, EFVP, protection adéquate, entente écrite, sous-traitants | Signal réseau → `FAIT_OBSERVE`; conformité → `INDETERMINE_INTERNE` + `INDETERMINE_JURIDIQUE` |

---

## 6. Défauts d’implémentation à corriger avant toute réactivation du ruleset

### 6.1 Garde-fou normatif inversé

Le moteur actuel applique la séquence suivante :

- règle `TODO` + observation favorable → `indetermine`;
- règle `TODO` + observation défavorable → `non_conforme`.

C’est incohérent. Sans obligation juridiquement établie, le moteur peut consigner un fait défavorable, mais ne peut pas qualifier ce fait de violation. La source doit être vérifiée **avant** toute production d’un statut juridique ou toute pénalité de score.

### 6.2 Modèle de statut insuffisant

Le type actuel `pass | fail | non_applicable` doit être remplacé ou complété par au minimum :

- `observed`;
- `technical_anomaly`;
- `apparent_public_gap`;
- `indeterminate_source`;
- `indeterminate_applicability`;
- `indeterminate_scan`;
- `indeterminate_internal`;
- `indeterminate_legal`.

`non_applicable` ne doit être utilisé que lorsque l’inapplicabilité est réellement établie, et non lorsque le scanner manque une interface ou une preuve.

### 6.3 Agrégation globale

En mode URL-only :

- le champ global `conforme` doit rester `null`;
- le rapport peut fournir un résumé des faits, contrôles techniques, anomalies et écarts publics apparents;
- le score de l’axe L doit être présenté comme un score de **signaux de vie privée**, pas un score de conformité Loi 25;
- aucune règle partielle ne doit rendre vertes des obligations non vérifiées.

### 6.4 Couverture et preuves minimales

Avant `ECART_PUBLIC_APPARENT`, OSIRIS doit au minimum consigner :

- les URL visitées et la profondeur du crawl;
- le sitemap et les liens internes pertinents;
- les routes FR/EN usuelles de confidentialité et gouvernance;
- le rendu JavaScript et les interfaces déclenchées;
- les erreurs, blocages, redirections, authentifications, CAPTCHA ou refus d’automatisation;
- l’URL exacte, l’extrait, l’horodatage et la méthode de capture de chaque preuve.

Sans cette couverture : `INDETERMINE_SCAN`.

---

## 7. Tests de régression obligatoires

1. `source: TODO` + fait défavorable → `INDETERMINE_SOURCE`, score juridique non pénalisé.
2. `source: TODO` + fait favorable → `INDETERMINE_SOURCE`.
3. Art. 3.1 sourcé + titre et coordonnées trouvés → `FAIT_OBSERVE` avec l’article conservé dans la preuve.
4. Art. 3.1 sourcé + absence sur une seule page → `INDETERMINE_SCAN`.
5. Art. 3.1 sourcé + absence après crawl complet documenté → `ECART_PUBLIC_APPARENT`.
6. Aucun bandeau de consentement → `INDETERMINE_APPLICABILITE`, pas `fail`.
7. Domaine de blocklist avant interaction → `ANOMALIE_TECHNIQUE`, pas `non_conforme`.
8. Aucun domaine de blocklist observé → fait négatif borné au périmètre, pas `conforme`.
9. Adresse `rpp@entreprise.ca` avec titre RPRP → détectée correctement.
10. Mot isolé « non » dans un autre composant → ne doit pas être pris pour un mécanisme de refus.
11. Lien contenant seulement « protection » mais menant ailleurs → ne doit pas valider une politique.
12. Lien de politique retournant 404 ou redirection non pertinente → ne doit pas être considéré accessible.

---

## 8. Conclusion opérationnelle

La bonne orientation est celle du produit public actuel : **axe L = signaux de vie privée**, avec la mention explicite qu’il ne s’agit ni d’une certification ni d’une conclusion juridique. Le vieux ruleset peut servir de chantier de recherche, mais il ne doit pas être réactivé ni fusionné sans :

1. remplacement des cinq verdicts binaires;
2. correction du garde-fou `TODO`;
3. réécriture des détecteurs;
4. crawl et preuve de couverture;
5. validation humaine des qualifications juridiques.

## Sources

- LégisQuébec — P-39.1, texte officiel : https://www.legisquebec.gouv.qc.ca/fr/document/lc/P-39.1/
- CAI — Principaux changements de la Loi 25 : https://www.cai.gouv.qc.ca/protection-renseignements-personnels/sujets-et-domaines-dinteret/principaux-changements-loi-25
- CAI — Lignes directrices 2023-1, consentement : https://www.cai.gouv.qc.ca/uploads/pdfs/CAI_Criteres_Validite_Consentement.pdf
- Ruleset historique audité : https://github.com/AILabManager-tech/osiris-scanner/blob/backup/full-sync-2026-07-17/rulesets/loi25.ruleset.yaml
- Moteur de gouvernance historique : https://github.com/AILabManager-tech/osiris-scanner/blob/backup/full-sync-2026-07-17/governance.py
- Observateurs et évaluateurs historiques : https://github.com/AILabManager-tech/osiris-scanner/blob/backup/full-sync-2026-07-17/axes/legal.py
