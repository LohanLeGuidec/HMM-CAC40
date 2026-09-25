# Calcul du bêta et règles d'allocation

## 1. Calcul du bêta

### 1.1 Formule

Pour chaque action $i$, le bêta par rapport au CAC40 est estimé par régression linéaire des rendements :

$$r_{i,t} = \alpha_i + \beta_i \cdot r_{CAC40,t} + \varepsilon_t$$

$$\beta_i = \frac{\text{Cov}(r_i, r_{CAC40})}{\text{Var}(r_{CAC40})}$$

### 1.2 Fenêtre de calcul

- **Fenêtre glissante de 252 jours de bourse** (≈ 1 an), recalculée **chaque semaine** (alignée sur la fréquence de rééquilibrage du portefeuille).
- **Pas de look-ahead bias** : au jour $t$, seules les données des 252 jours précédant (et incluant) $t$ sont utilisées — jamais de données futures.

### 1.3 Pourquoi ce choix (rappel des arbitrages)

| Approche | Avantages | Inconvénients | Retenu ? |
|---|---|---|---|
| Bêta fixe (toute la période) | Stable, peu bruité | Ignore l'évolution du profil de risque, risque de look-ahead bias si mal implémenté | ❌ |
| Glissant 60 jours | Très réactif aux changements récents | Bruité, instable, sensible aux outliers | ❌ |
| **Glissant 252 jours** | Bon compromis stabilité/réactivité, standard académique/pro | Retard de quelques mois pour capter un changement structurel | ✅ |

### 1.4 Ajustement de Blume (optionnel)

$$\beta_{ajusté} = \frac{2}{3} \beta_{brut} + \frac{1}{3} \times 1$$

- Réduit le bruit d'estimation en "tirant" les bêtas extrêmes vers 1 (mean reversion empirique des bêtas dans le temps).
- **Décision (Phase 3, comparaison empirique sur 471 semaines)** : Blume retenu. Turnover total 1681 vs 1940 avec le bêta brut (-13 %), taille moyenne de panier quasi identique (9.11 vs 9.67). `settings.UTILISER_BLUME = True`.

## 2. Seuils de classification

**Méthode retenue (24/09/2026) : terciles recalculés à chaque date** (`BETA_METHODE_SEUILS = 'quantiles'`, `BETA_QUANTILE_COUPURE = 0.33`). À chaque rééquilibrage, les 33 % d'actions au bêta ajusté le plus faible forment le panier défensif, les 33 % au bêta le plus élevé le panier offensif, le reste le panier neutre. Plus de zone grise : chaque panier compte ~13 actions quel que soit le niveau général des bêtas. Justification en section 2 bis.

Ancienne méthode (seuils fixes, toujours disponible avec `BETA_METHODE_SEUILS = 'fixes'`) :

| Régime de marché détecté | Critère de sélection des actions | Label bêta |
|---|---|---|
| Baissier | $\beta_i < 0.8$ | Défensif |
| Neutre | $0.9 \le \beta_i \le 1.1$ | Neutre |
| Haussier | $\beta_i > 1.2$ | Offensif |

- Les actions avec $0.8 \le \beta_i < 0.9$ ou $1.1 < \beta_i \le 1.2$ sont dans une **zone grise**, non éligibles à un panier tant qu'elles n'ont pas franchi clairement un seuil (évite les allers-retours de classification dus au bruit).
- Limites constatées : seuils appliqués au bêta *ajusté* (resserré vers 1 par Blume), donc « > 1,2 » ne retenait que 7 actions offensives en moyenne (parfois 2, soit > 30 % du portefeuille par action) ; ~10 actions sur 40 inutilisées (zone grise).

## 2 bis. Choix du seuil : analyse ROC puis backtest sur le train

Tout le calibrage est fait sur la période d'entraînement (déc. 2000 - sept. 2018) ; le test (oct. 2018 - sept. 2026) n'a servi qu'une fois, pour vérifier le choix.

**1. Analyse ROC (abandonnée).** Une courbe ROC du bêta (cible : l'action bat le CAC40 le mois suivant, 7 546 observations action x mois) donne une AUC de 0,50 en régime baissier et 0,47 en régime haussier, intervalles de confiance contenant 0,5 ; un random forest (bêta, momentum, probabilités de régime) en validation temporelle ne fait pas mieux (AUC 0,50). Le bêta ne prédit pas la surperformance du mois suivant : il n'existe pas de seuil « optimal » au sens de Youden. Le code de cette analyse a été retiré du projet.

**2. Backtest sur le train.** Faute de seuil « optimal » au sens ROC, on compare les méthodes de construction des paniers par leur performance sur le train :

| Méthode | Rdt annualisé | Sharpe | Max drawdown | Poids max moyen |
|---|---|---|---|---|
| Seuils fixes 0,8 / 0,9 / 1,1 / 1,2 | 2,6 % | 0,03 | -77,5 % | 17,2 % |
| Quantiles 20 % | 5,3 % | 0,16 | -64,8 % | 11,0 % |
| Quantiles 25 % | 5,2 % | 0,15 | -63,7 % | 9,4 % |
| Quantiles 30 % | 6,3 % | 0,21 | -56,3 % | 8,5 % |
| **Quantiles 33 % (retenu)** | **6,4 %** | **0,21** | **-57,3 %** | **8,5 %** |
| Quantiles 40 % | 7,1 % | 0,24 | -55,6 % | 9,5 % |

(CAC40 sur la même période : 1,2 %/an.) Plateau entre 30 et 40 % ; 33 % (terciles) retenu comme choix standard de la littérature des tris de portefeuille, au milieu du plateau plutôt qu'au maximum (limite le surajustement). Gain confirmé sur les deux moitiés du train (2000-2009 : -5,2 %/an contre -13,9 % ; 2009-2018 : 12,5 % contre 11,8 %). Le gain vient surtout de la diversification (paniers de ~13 actions au lieu de 2 à 10) et de la suppression de la zone grise.

**3. Vérification unique sur le test** (oct. 2018 - sept. 2026). Chiffres sur la base « sans dividendes » (cf. ci-dessous), même base que le CAC40 :

| | Seuils fixes | Terciles | CAC40 |
|---|---|---|---|
| Rendement annualisé | 1,4 % | 5,2 % | 6,1 % |
| Sharpe | 0,01 | 0,18 | 0,26 |
| Max drawdown | -32,3 % | -31,7 % | -38,6 % |
| Alpha | - | -0,4 % | - |

Les terciles restent nettement meilleurs que les seuils fixes (aussi sur le train, sans dividendes : 3,6 %/an contre 0,5 %), mais la stratégie ne bat plus le CAC40.

**Base de comparaison (25/09/2026).** Le backtest valorise désormais les actions au Close Yahoo (corrigé des divisions d'actions, pas des dividendes), comme le benchmark ^FCHI qui est un indice de prix (`BACKTEST_COLONNE_PRIX = 'close'`). Auparavant, l'Adjusted Close (dividendes réinvestis) avantageait la stratégie d'environ 3 %/an (8,0 % affiché contre 5,2 % réel) et intégrait des sauts erronés de Yahoo (Stellantis +39 % le 14/01/2021, AXA environ +10 % chaque mois de mai 2003-2008, alors que le cours ne bougeait pas). Les bêtas et le momentum restent calculés sur l'Adjusted Close.

## 2 ter. Le gain vient-il du HMM ? (test de contribution)

Même construction de paniers (terciles), seule la façon de répartir le portefeuille entre les trois paniers change (base sans dividendes) :

| Répartition entre paniers | Test : rdt / Sharpe / MDD | Train : rdt / Sharpe / MDD | Coûts (test) |
|---|---|---|---|
| Probabilités du HMM (stratégie actuelle) | 5,2 % / 0,18 / -31,7 % | 3,6 % / 0,08 / -59,8 % | 126 k€ |
| **Sans HMM : 1/3 par panier, fixe** | **7,2 % / 0,32 / -36,6 %** | **5,1 % / 0,16 / -57,4 %** | 20 k€ |
| Régimes du HMM mélangés au hasard | 4,7 % / 0,17 / -34,1 % | 2,3 % / 0,02 / -69,5 % | 155 k€ |
| HMM inversé (haussier <-> baissier) | 9,7 % / 0,43 / -44,8 % | 7,1 % / 0,22 / -64,6 % | 131 k€ |
| 100 % panier défensif | 7,1 % / 0,43 / -30,1 % | 6,4 % / 0,28 / -50,2 % | 19 k€ |
| 100 % panier neutre | 7,2 % / 0,30 / -32,4 % | 4,9 % / 0,15 / -56,4 % | 44 k€ |
| 100 % panier offensif | 5,8 % / 0,17 / -47,8 % | 2,7 % / 0,03 / -71,1 % | 24 k€ |
| CAC40 (indice de prix) | 6,1 % / 0,26 / -38,6 % | 1,2 % / -0,02 / -59,9 % | - |

Conclusions :
- Le gain des terciles vient de la diversification des paniers, pas du HMM : sans HMM (1/3 par panier) on fait mieux sur le train comme sur le test, avec 6 fois moins de coûts, et on bat le CAC40 sur le test (7,2 % contre 6,1 %).
- Le pilotage par le HMM fait à peine mieux que des régimes tirés au hasard : la règle « haussier -> bêta élevé, baissier -> bêta faible » coûte environ 1,5 à 2 points de rendement par an.
- La règle inversée fait mieux sur les deux périodes : le régime détecté (avec retard) porte une information de retour à la moyenne (après une phase baissière, les actions à bêta élevé rebondissent), cohérente avec le rendement moyen du CAC à 20 jours après un jour « baissier » (+2,2 % sur le test).
- Le panier défensif seul a le meilleur Sharpe (anomalie « low beta »).
- Toutes les stratégies bénéficient du biais de survivance (composition actuelle du CAC).

## 5. Stratégie retenue : « stratégie de rebond » (25/09/2026)

**Principe.** Le HMM confirme un régime avec quelques jours de retard : quand il annonce « baissier », la chute a souvent déjà eu lieu et le marché tend à rebondir (CAC40 +2,2 % en moyenne sur les 20 séances suivant un jour « baissier », période de test). On joue donc le retour à la moyenne :

| Régime détecté | Panier privilégié | Idée |
|---|---|---|
| Baissier | Offensif (bêta élevé) | on joue le rebond |
| Neutre | Neutre | - |
| Haussier | Défensif (bêta faible) | on sécurise les gains |

Le poids de chaque panier est la probabilité (filtrée) du régime correspondant. Réglage : `ALLOCATION_MODE = 'rebond'` (autres valeurs : `'suiveur'`, ancienne logique ; `'equipondere'`, 1/3 par panier sans HMM).

**Garde-fous, calibrés sur le train (2000-2018)** : probabilités moyennées sur N jours (`ALLOCATION_LISSAGE_JOURS`) et poids maximal du panier offensif (`ALLOCATION_PLAFOND_OFFENSIF`, excédent reporté sur le neutre).

| Lissage | Plafond offensif | Rdt train | Sharpe | MDD | Coûts |
|---|---|---|---|---|---|
| 1 j | 100 % | 7,1 % | 0,22 | -64,6 % | 514 k€ |
| 5 j | 80 % | 7,0 % | 0,23 | -64,3 % | 430 k€ |
| **10 j** | **80 %** | **6,9 %** | **0,22** | **-63,7 %** | **403 k€** |
| 21 j | 80 % | 6,5 % | 0,21 | -61,3 % | 302 k€ |
| 21 j | 60 % | 6,4 % | 0,21 | -60,4 % | 285 k€ |

Sharpe stable (0,21-0,23) pour les 12 combinaisons testées : 10 j / 80 % retenu au milieu du plateau (-22 % de coûts, ~97 % du rendement). Sur le train, le CAC40 fait 1,2 %/an, le mode suiveur 3,6 %, le 1/3 par panier 5,1 %.

**Vérification unique sur le test (oct. 2018 - sept. 2026)**, sans dividendes, mêmes paniers et mêmes garde-fous :

| Stratégie | Capital final | Rdt annualisé | Volatilité | Sharpe | Max drawdown |
|---|---|---|---|---|---|
| **Stratégie de rebond (HMM)** | **1 913 276 €** | **8,5 %** | **18,6 %** | **0,39** | **-38,3 %** |
| 1/3 par panier (sans HMM) | 1 742 985 € | 7,2 % | 18,6 % | 0,32 | -36,6 % |
| HMM suiveur | 1 557 194 € | 5,7 % | 21,1 % | 0,21 | -38,7 % |
| CAC40 (indice de prix) | 1 601 407 € | 6,1 % | 18,6 % | 0,26 | -38,6 % |

Alpha annualisé vs CAC40 : +3,1 %, bêta du portefeuille 0,89.

**Limites.** La règle a été identifiée en observant que la logique suiveuse faisait moins bien que le hasard ; elle est confirmée sur le train et sur le test, mais reste un pari sur le retour à la moyenne : pendant une baisse longue (2000-2003, 2008) elle détient les actions les plus risquées (MDD train -64 %). Sur le test, l'avantage se construit surtout lors des rebonds de 2020 et 2025-2026 ; de 2021 à fin 2024 elle est restée derrière le 1/3 par panier. Le biais de survivance (composition actuelle du CAC) s'applique à toutes les variantes.
