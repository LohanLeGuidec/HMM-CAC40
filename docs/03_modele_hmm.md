# Modèle HMM — Détection des régimes de marché

## 1. Principe général

Un **Hidden Markov Model (HMM) Gaussien** est utilisé pour détecter, de manière **non supervisée**, les régimes cachés du marché à partir de séries d'observations calculées sur le CAC40 (`^FCHI`). Le modèle logit initialement envisagé est **abandonné** : seul le HMM est utilisé.

## 2. Nombre d'états cachés

- **3 régimes** :
  1. **Haussier** (bull) — rendements moyens positifs, volatilité modérée à faible.
  2. **Neutre** (sideways) — rendements proches de zéro, volatilité faible à modérée.
  3. **Baissier** (bear) — rendements moyens négatifs, volatilité élevée.
- L'**identification** (quel état numérique correspond à quel label) se fait **a posteriori**, en triant les états par la moyenne de rendement associée (état à moyenne la plus haute = Haussier, etc.), car le HMM ne connaît pas ces labels a priori.

## 3. Variables d'observation (révisées — Phase 5)

| Variable | Description | Justification |
|---|---|---|
| **Tendance longue** | Rendement log cumulé du CAC40 sur 60 jours | Porte la *direction* du marché ; sert à étiqueter les états |
| **Tendance courte** | Rendement log cumulé sur 20 jours | Réagit plus vite aux retournements |
| **Volatilité (log)** | Log de l'écart-type des rendements sur 20 jours, annualisé | Niveau de stress ; le log rapproche la distribution d'une gaussienne |
| **Variation du spread** | Variation sur 63 jours du spread France - Allemagne, **décalé d'un mois** | Contexte macro, sans la dérive du niveau |

Variables abandonnées et pourquoi (diagnostic du 23/09/2026) :
- **Rendement quotidien** : les moyennes par état ne différaient que de ~0,02 écart-type ; le HMM ne pouvait pas s'en servir pour séparer hausse et baisse, il découpait uniquement selon la volatilité et le spread.
- **Niveau du spread** : non stationnaire (0,44 en moyenne sur le train, 0,55-0,83 sur le test, soit jusqu'à +3,6 écarts-types). Il faisait basculer 61 % du test dans un même état « spread élevé » étiqueté neutre.
- **Fuite d'information** : la série FRED est une moyenne mensuelle datée du 1er du mois. Sans décalage, le 1er novembre on utilisait déjà la moyenne de tout novembre. Le spread du mois M n'est désormais utilisé qu'à partir de M + 1 (`HMM_SPREAD_DECALAGE_MOIS`).

- **Type de covariance** : **diagonale** (`covariance_type="diag"`).
- **Standardisation** : z-score ajusté sur le train uniquement, réutilisé tel quel sur le test.
- **Initialisations** : l'EM est lancé avec `HMM_NB_INITIALISATIONS = 5` graines, la meilleure log-vraisemblance est retenue.

## 4. Entraînement et ré-entraînement (walk-forward)

- **Entraînement initial** : sur les 70 % de données les plus anciennes (période "train").
- **Walk-forward pendant le test** : le HMM est **ré-entraîné périodiquement** (fréquence à définir précisément en implémentation, proposition : tous les 3 mois / 63 jours de bourse) en utilisant uniquement les données disponibles jusqu'à la date courante (pas de fuite d'information vers le futur).
- À chaque date de rééquilibrage hebdomadaire du portefeuille, le régime utilisé est celui décodé par le **dernier modèle HMM disponible** à cette date (`predict` sur les nouvelles observations, pas de ré-estimation à chaque semaine — seulement au rythme du ré-entraînement walk-forward).

## 5. Étiquetage, alignement et décodage (révisés — Phase 5)

- **Étiquetage** : les états sont triés par **tendance longue moyenne** (la plus basse = baissier, la plus haute = haussier). L'ancien score composite `rendement − 0,5×vol − 0,5×spread` était en pratique dicté par la volatilité et le spread.
- **Alignement entre ré-entraînements** : chaque état du nouveau modèle hérite du label de l'état le plus proche du modèle précédent (affectation hongroise sur les moyennes standardisées). Si cela contredit l'ordre des tendances, on revient à l'étiquetage par tendance. Avant : jusqu'à 47 % de l'historique changeait de label à un ré-entraînement ; après : 5,6 % en moyenne (max 21 %).
- **Décodage causal** : régime du jour t = état de plus forte **probabilité filtrée** P(état_t | obs_1..t), calculée par l'algorithme forward. Viterbi et `predict_proba` (forward-backward) sont abandonnés car ils utilisent des observations postérieures à t (jusqu'à 63 jours dans le walk-forward). Les probabilités stockées sont désormais réellement filtrées.

## 6. Risque d'overfitting — points de vigilance

- Nombre de paramètres limité par le choix de covariance diagonale (~3 états × (3 moyennes + 3 variances) + matrice de transition 3×3 ≈ 27 paramètres pour ~1750 observations en train → ratio raisonnable).
- Le **spread de taux**, à variation lente, peut introduire de l'autocorrélation et favoriser des régimes très persistants corrélés à des tendances macro plutôt qu'à des régimes de marché actions à proprement parler. **Point à valider empiriquement** : comparer les régimes obtenus avec/sans cette variable, vérifier la cohérence avec les crises connues (2018 Q4, COVID 2020, 2022 inflation/taux).
- Prévoir une **analyse de sensibilité** : faire tourner le HMM avec 2 puis 3 variables, comparer la stabilité des régimes détectés (nombre de transitions, durée moyenne des régimes) avant de figer la configuration finale.

## 7. Bibliothèque

- `hmmlearn` (`GaussianHMM`) en Python — implémentation standard, compatible avec les besoins (Viterbi, probabilités filtrées, covariance diagonale).

## 8. Validation qualitative

- Superposer visuellement les régimes détectés à la courbe du CAC40 sur la période complète (graphique dans le dashboard) pour une validation qualitative : les régimes baissiers doivent correspondre aux krachs/corrections connus (2020, 2022...).
- Validé : le krach COVID (fév-mars 2020) est détecté en régime baissier avec ~100 % de probabilité.

## 9. Stabilisation des régimes (Phase 4 — correctif)

Le walk-forward initial produisait un **whipsaw** (oscillation haussier/baissier quasi hebdomadaire) sur certaines périodes peu directionnelles, générant un turnover de portefeuille excessif. Deux correctifs ont été appliqués :

1. **Prior de transition "collant"** (`transmat_prior`, diagonale renforcée à `HMM_TRANSMAT_PRIOR_DIAGONAL = 20`) : favorise la persistance d'état lors de l'estimation Baum-Welch.
2. **Filtre de persistance causal** (`HMM_PERSISTANCE_MIN_JOURS = 5`) : un changement de régime n'est confirmé que s'il persiste au moins 5 jours de bourse consécutifs ; sinon le régime précédent est maintenu. Purement causal (aucune fuite d'information future).

Résultat : turnover hebdomadaire total passé de 1697 à 787 sur 471 semaines, répartition des régimes de test plus équilibrée (neutre 313 / haussier 255 / baissier 194 contre 106/444/212 avant correctif).

## 10. Résultats de la refonte (Phase 5, 23/09/2026)

Épisodes connus (part des jours dans chaque régime) :

| Épisode | Avant | Après |
|---|---|---|
| 2018 Q4 (−14 %) | 77 % haussier, 0 % baissier | 30 % baissier, 58 % neutre |
| COVID 2020 (−25 %) | 88 % baissier | 80 % baissier |
| 2022 inflation (−19 %) | 19 % baissier, 72 % neutre | 42 % baissier |
| Rallye 2017 (+17 %) | 96 % neutre | 100 % haussier |
| Rallye 2023-24 (+12 %) | 70 % haussier | 78 % haussier |

Backtest (période de test) : le backtest se dégrade (rendement annualisé −7,0 % contre +1,8 % avant ; CAC40 +4,6 %). Cause identifiée : sur 2023-2026, le panier défensif (bêta faible) a rapporté +18,3 %/an contre +0,65 %/an pour le panier offensif (drawdown −39 %). Le régime « haussier », détecté avec retard (tendance 60 j), n'a pas de pouvoir prédictif sur les 20 jours suivants (−0,26 % en moyenne sur le test). La règle d'allocation « haussier → bêta élevé » est à revoir : c'est elle, et non plus la détection, qui limite la stratégie.

### 10.1 Correctif du retard aux retournements (23/09/2026, après revue du graphique)

Constat : sur le test, le régime affiché était « haussier » pendant les baisses et « baissier » pendant les rebonds. Mesure : le label était d'accord avec le sens des 20 jours **passés** dans 70 % des cas, mais avec le sens **centré** du marché (±10 jours) dans seulement 53 % des cas. Le CAC faisait −9,9 %/an pendant les jours « haussier » et +86 %/an pendant les jours « baissier ».

Causes : fenêtre de tendance de 60 jours (centre de gravité ~30 jours en arrière) et filtre de persistance de 5 jours (une semaine de retard supplémentaire à chaque retournement).

Correctif, choisi sur la période **train uniquement** (le test sert de vérification) :
- tendance longue 20 j, tendance courte 5 j, volatilité sur 10 j ;
- filtre de persistance désactivé (`HMM_PERSISTANCE_MIN_JOURS = 1`) : la persistance reste assurée par le prior de transition collant. Même 2 jours de filtre inversaient le signe du rendement des jours « haussier ».

| | Train avant | Train après | Test avant | Test après |
|---|---|---|---|---|
| Accord avec la direction centrée | 52 % | 62 % | 53 % | 63 % |
| Rendement CAC les jours « haussier » | +0,1 %/an | +22,9 %/an | −9,9 %/an | +17,3 %/an |
| Rendement CAC les jours « baissier » | +26,6 %/an | +7,2 %/an | +85,9 %/an | −1,1 %/an |
| Changements de régime | 53 | 102 | 25 | 59 |

Épisodes : COVID 94 % baissier, 2022 61 %, tarifs 2025 68 %, 2018 Q4 45 %.

Limite qui demeure : aucun réglage causal ne prédit les 20 jours suivants (accord 44-50 %) ; le régime décrit le marché avec quelques jours de retard, il ne l'anticipe pas. Backtest : −6,3 %/an (CAC +6,0 % sur les mêmes dates) ; la règle « haussier → panier bêta élevé » reste le facteur limitant.
