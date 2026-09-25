# Données de marché

## 1. Source

- **Yahoo Finance** via la librairie `yfinance`.
- Champ utilisé : **Adjusted Close** (dividendes réinvestis) pour tous les calculs de rendement, de volatilité et de bêta. Le Close brut n'est pas utilisé (il fausserait le bêta des valeurs à fort dividende, ex: foncières, télécoms).

## 2. Univers d'actions

- Les **40 valeurs composant actuellement le CAC40** (liste figée au démarrage du projet, validée le 2026-09-10, stockée dans `config/univers_cac40.csv` : ticker Yahoo, nom, secteur).
- **Limite assumée** : pas de gestion de la composition historique réelle de l'indice → biais de survivance (survivorship bias) documenté mais non corrigé. À mentionner explicitement dans le rapport/soutenance comme limite méthodologique.
- Le CAC40 lui-même est utilisé comme **benchmark** (ticker Yahoo `^FCHI`).
- Liste validée (source Wikipedia, composition de référence 2025) : AI.PA, AIR.PA, ALO.PA, MT.AS, CS.PA, BNP.PA, EN.PA, CAP.PA, CA.PA, ACA.PA, BN.PA, DSY.PA, EDEN.PA, ENGI.PA, EL.PA, ERF.PA, RMS.PA, KER.PA, OR.PA, LR.PA, MC.PA, ML.PA, ORA.PA, RI.PA, PUB.PA, RNO.PA, SAF.PA, SGO.PA, SAN.PA, SU.PA, GLE.PA, STLAP.PA, STMPA.PA, TEP.PA, HO.PA, TTE.PA, URW.PA, VIE.PA, DG.PA, WLN.PA.

## 3. Période et fréquence

- **Historique** : ~26 ans, **fenêtre figée** du 2000-01-03 au 2026-09-10 (reproductibilité des résultats, indépendante de la date d'exécution future des scripts). Étendu depuis 10 ans (2016-2026) le 23/09/2026 : avec 10 ans, le train ne contenait qu'un vrai krach (COVID) et le test 3 ans quasi haussiers. Depuis 2000, le train (~2000-2018) couvre la bulle internet, 2008 et la crise de la dette euro ; le test (~2018-2026) couvre fin 2018, le COVID, 2022, la dissolution de 2024 et les tarifs de 2025. 2000 correspond aussi au début de la zone euro, ce qui rend le spread France - Allemagne comparable sur toute la période.
- **Fréquence** : journalière (OHLCV).
- **Split** :
  - **Train (70 %)** : entraînement initial du HMM (détection des régimes, estimation des paramètres).
  - **Test (30 %)** : évaluation walk-forward de la stratégie (le HMM est ré-entraîné périodiquement pendant cette phase, cf. [03_modele_hmm.md](03_modele_hmm.md)).
  - Split **chronologique strict** (pas de shuffle) pour éviter toute fuite d'information (look-ahead bias).

## 4. Variable macro complémentaire

- **Spread de taux** : différentiel de taux souverain long terme France - Allemagne, récupéré via **FRED** (`pandas-datareader`) :
  - `IRLTLT01FRM156N` (taux long terme France, mensuel)
  - `IRLTLT01DEM156N` (taux long terme Allemagne, mensuel)
  - Spread = série France − série Allemagne, interpolée/propagée (forward-fill) en fréquence journalière pour être alignée avec les autres observations du HMM.
- Yahoo Finance ne fournit pas de série fiable pour ce spread, d'où le choix de FRED comme source dédiée.

## 5. Stockage

- **DuckDB** comme moteur de stockage/analyse pour les données de marché brutes et transformées (fichiers `.duckdb` locaux) :
  - Table `prix_ohlcv` (ticker, date, open, high, low, close, adj_close, volume).
  - Table `rendements` (ticker, date, rendement_log ou rendement_simple).
  - Table `beta_glissant` (ticker, date, beta_252j).
  - Table `regimes_marche` (date, regime_detecte, probabilites_etats).
- Les résultats agrégés destinés à l'affichage (backtests, allocations, métriques de performance) sont **synchronisés vers SQLite** pour être exposés via les modèles Django/ORM.

## 6. Nettoyage des données

- Gestion des jours fériés / valeurs manquantes : alignement sur le calendrier de bourse Euronext Paris, forward-fill limité (max 2 jours) pour les données manquantes ponctuelles, exclusion des tickers avec trop de trous (> 5 % de valeurs manquantes **à partir de leur première cotation** : les jours antérieurs à l'introduction en bourse ne comptent pas comme des trous).
- Détection et traitement des splits/opérations sur titre (normalement déjà gérés par l'Adjusted Close de Yahoo Finance).
- Gestion des IPO/retraits récents : une action cotée après 2000 (ex. Legrand 2006, Edenred 2010, Worldline 2014) est incluse avec un historique partiel : elle n'entre dans le calcul des bêtas et dans l'allocation qu'une fois 252 jours de données disponibles. Les dates de rééquilibrage sont tirées du calendrier du CAC40, pas de celui d'une action.
- **Biais de survivance accru** : sur 26 ans, l'univers (composition actuelle du CAC40) ignore les sociétés sorties de l'indice (Alcatel, Lafarge, Vivendi...). La détection des régimes n'est pas concernée (elle n'utilise que l'indice), mais la performance des paniers d'actions est surestimée. Limite à mentionner explicitement dans le rapport.
