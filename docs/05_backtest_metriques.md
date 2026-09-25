# Backtest et métriques de performance

## 1. Paramètres du backtest

| Paramètre | Valeur |
|---|---|
| Capital initial | 1 000 000 € |
| Période de test | 30 % la plus récente de l'historique 2000-2026 (~2018-2026) (post-entraînement initial du HMM) |
| Fréquence de rééquilibrage | Hebdomadaire (avec anti-churn, cf. [04_beta_allocation.md](04_beta_allocation.md)) |
| Coûts de transaction | 0.10 % par transaction |
| Benchmark | CAC40 (`^FCHI`), avec dividendes réinvestis pour une comparaison cohérente |
| Fréquence de ré-entraînement HMM | Walk-forward, tous les ~63 jours de bourse (3 mois) — à ajuster empiriquement |

## 2. Méthodologie de simulation

1. À chaque semaine $t$ :
   - Récupérer le régime détecté par le dernier modèle HMM disponible (walk-forward).
   - Calculer les bêtas glissants à 252 jours de toutes les actions de l'univers, à la date $t$.
   - Déterminer le panier cible (top 10 selon le régime, avec règle anti-churn).
   - Comparer aux positions actuelles → générer les ordres d'achat/vente nécessaires.
   - Appliquer les coûts de transaction (0.10 %) sur le montant des ordres.
   - Mettre à jour la valeur du portefeuille jour par jour jusqu'au prochain rééquilibrage (équipondéré, valorisé en Adjusted Close).
2. Répéter jusqu'à la fin de la période de test.
3. Conserver l'historique complet : valeur du portefeuille, composition, régime détecté, bêtas, transactions, pour chaque date.

## 3. Métriques de performance

| Métrique | Définition | Usage |
|---|---|---|
| **Rendement annualisé** | $(V_{final}/V_{initial})^{252/n} - 1$ | Performance brute |
| **Volatilité annualisée** | Écart-type des rendements journaliers × $\sqrt{252}$ | Risque total |
| **Ratio de Sharpe** | (Rendement annualisé − taux sans risque) / Volatilité annualisée | Rendement ajusté du risque total |
| **Ratio de Sortino** | (Rendement annualisé − taux sans risque) / Volatilité des rendements négatifs uniquement | Rendement ajusté du risque baissier |
| **Ratio de Calmar** | Rendement annualisé / \|Max Drawdown\| | Rendement ajusté du risque de perte maximale |
| **Max Drawdown** | Perte maximale depuis un plus haut historique du portefeuille | Risque de perte extrême |
| **VaR (Value at Risk)** | VaR historique à 95 % (ou paramétrique gaussienne, à trancher en implémentation) sur les rendements journaliers | Risque de perte à horizon court |
| **Alpha vs CAC40** | Ordonnée à l'origine de la régression rendements portefeuille vs rendements CAC40 | Surperformance ajustée du risque de marché |
| **Bêta du portefeuille vs CAC40** | Pente de la même régression | Exposition résiduelle au marché |
| **Taux sans risque** | Proxy à définir (ex: taux OAT 3 mois ou Euribor 3M, ou simplification à 0 % si non disponible facilement) | Utilisé dans Sharpe/Sortino |

## 4. Comparaisons à produire

- Courbe de performance **portefeuille stratégie vs CAC40 buy & hold** sur la période de test (indexée base 100 ou en valeur absolue).
- Tableau comparatif des métriques ci-dessus, stratégie vs CAC40.
- Courbe des régimes détectés superposée à l'indice (validation qualitative, cf. [03_modele_hmm.md](03_modele_hmm.md)).
- Historique des paniers d'actions sélectionnés dans le temps (quelles actions, quel régime, quels bêtas).

## 6. Modèle de rééquilibrage retenu (Phase 4)

Afin d'éviter un turnover artificiel, le rééquilibrage hebdomadaire ne retouche que les **entrées et sorties de panier** : les positions conservées d'une semaine à l'autre ne sont pas revendues/rachetées pour les ramener à l'équipondération stricte (leur poids dérive naturellement avec le cours). Les nouvelles entrées sont financées par le cash libéré par les sorties (réparti également entre les entrants).

## 7. Résultats du backtest (période de test, après stabilisation du HMM cf. docs/03)

| Métrique | Stratégie HMM (v1, hebdo, panier dur) | Stratégie HMM (v2, mensuel, probabiliste + momentum) | CAC40 (buy & hold) |
|---|---|---|---|
| Capital final (1 000 000 € initial) | 806 476 € | **878 895 €** | 1 143 182 € |
| Rendement annualisé | -6.85 % | **-4.21 %** | 4.60 % |
| Volatilité annualisée | 17.31 % | 18.41 % | 14.24 % |
| Sharpe | -0.56 | -0.38 | 0.13 |
| Sortino | -0.75 | -0.52 | — |
| Calmar | -0.25 | -0.16 | — |
| Max Drawdown | -27.71 % | -26.67 % | -16.71 % |
| VaR 95 % (quotidien) | -1.80 % | -1.83 % | — |
| Coûts de transaction totaux | 31 365 € | 31 117 € | — |

La v2 (rééquilibrage mensuel, allocation probabiliste par blend des probabilités de régime, score composite bêta+momentum) réduit la perte de moitié par rapport à la v1, mais reste négative en absolu.

### Diagnostic de la sous-performance (Phase 4)

Analyse du rendement du CAC40 **après** chaque détection de régime :

| Régime détecté | Rendement CAC40 moyen la période suivante |
|---|---|
| Haussier | +0.79 % (mensuel) — signal correctement orienté |
| Neutre | +0.05 % (mensuel) |
| Baissier | +1.33 % (mensuel) — **signal inversé** |

Deux causes identifiées :
1. **Effet rebond post-krach** : le régime "baissier" est détecté après coup (le HMM est nécessairement rétrospectif), au moment où le marché a statistiquement tendance à rebondir à court terme. Positionnement défensif juste avant le rebond = performance ratée. Testé un correctif (atténuation du biais défensif vers le panier neutre, `ATTENUATION_BAISSIER`) : **n'améliore pas le résultat** (testé à 0.5 et 0.0, les deux dégradent légèrement vs pas d'atténuation) → paramètre supprimé (pas d'atténuation).
2. **Écart structurel de composition** : la sélection par bêta/momentum construit un portefeuille diversifié (~28 actions en moyenne) mais **non pondéré par capitalisation**, alors que le CAC40 est un indice pondéré par la capitalisation flottante. Un écart de performance vs un indice cap-weighted est attendu pour toute stratégie qui s'en écarte, indépendamment de la qualité de la détection de régime.

**Conclusion assumée** : la stratégie, telle que spécifiée (rotation bêta pilotée par un HMM sur rendement/volatilité/spread de taux), sous-performe le CAC40 sur cette période de test précise, pour des raisons documentées et diagnostiquées (pas un bug). Ceci est présenté comme un résultat scientifique honnête, avec un chemin d'amélioration clair pour des travaux futurs (features de régime moins rétrospectives, pondération par capitalisation, horizon plus long).

## 8. Limites à documenter dans le rapport

- Survivorship bias sur l'univers CAC40 (composition figée).
- Absence d'optimisation fine de portefeuille (équipondéré simple).
- Sensibilité des résultats à la fréquence de ré-entraînement du HMM et aux seuils de bêta (à mentionner comme axes d'amélioration).

## Base de valorisation (25/09/2026)

Le portefeuille est valorisé au Close Yahoo (sans dividendes), comme le benchmark ^FCHI (indice de prix) : `settings.BACKTEST_COLONNE_PRIX = 'close'`. La valorisation à l'Adjusted Close (dividendes réinvestis) surestimait la stratégie d'environ 3 %/an face au CAC40 et reprenait des sauts erronés de l'Adjusted Close Yahoo. Résultat sur le test (oct. 2018 - sept. 2026) : 5,2 %/an (Sharpe 0,18) contre 6,1 % (Sharpe 0,26) pour le CAC40. Détail et comparaisons : docs/04, sections 2 bis et 2 ter.

## Stratégie de rebond (25/09/2026)

Stratégie retenue : `ALLOCATION_MODE = 'rebond'` (cf. docs/04, section 5). Test oct. 2018 - sept. 2026 : 8,5 %/an, Sharpe 0,39, max drawdown -38,3 %, contre 6,1 %, 0,26 et -38,6 % pour le CAC40. `lancer_backtest` rejoue aussi les modes « suiveur » et « 1/3 par panier » sur les mêmes dates (table `valeur_comparaisons`), affichés sur la page Performance.
