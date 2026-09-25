# Feuille de route

## Phase 0 — Paramétrage (terminée)

- [x] Cahier des charges validé ([01_cahier_des_charges.md](01_cahier_des_charges.md))
- [x] Spécification des données ([02_donnees_marche.md](02_donnees_marche.md))
- [x] Spécification du modèle HMM ([03_modele_hmm.md](03_modele_hmm.md))
- [x] Règles de bêta et d'allocation ([04_beta_allocation.md](04_beta_allocation.md))
- [x] Méthodologie de backtest ([05_backtest_metriques.md](05_backtest_metriques.md))
- [x] Architecture technique ([06_architecture_technique.md](06_architecture_technique.md))

## Phase 1 — Données

- [x] Constituer la liste des 40 tickers Yahoo Finance du CAC40 actuel (validée, [config/univers_cac40.csv](../config/univers_cac40.csv)).
- [x] Écrire le script/commande d'import Yahoo Finance → DuckDB (depuis 2000, daily, Adjusted Close) : `python manage.py import_donnees_marche`.
- [x] Spread de taux France - Allemagne via FRED (`IRLTLT01FRM156N` / `IRLTLT01DEM156N`), stocké dans DuckDB.
- [x] Nettoyage des données (forward-fill limité à 2 jours, exclusion si > 5 % de valeurs manquantes).
- [x] Import exécuté avec succès : 39 actions + benchmark `^FCHI` importés (2558 jours), **URW.PA exclu automatiquement** (66 % de valeurs manquantes — restructuration de la cotation Unibail-Rodamco-Westfield en 2023, à documenter comme limite connue).

## Phase 2 — Modèle HMM

- [x] Construction des variables d'observation (rendement, volatilité réalisée, spread de taux) : [apps/regimes/services/features.py](../apps/regimes/services/features.py).
- [x] Entraînement du HMM sur la période train (70 %), covariance diagonale, 3 états : [apps/regimes/services/hmm_model.py](../apps/regimes/services/hmm_model.py).
- [x] Étiquetage des régimes (tri par moyenne de rendement).
- [x] Mise en place du ré-entraînement walk-forward pour la période test (fenêtre expansive, tous les 63 jours de bourse) : `python manage.py entrainer_hmm`.
- [x] Validation qualitative : krach COVID (fév-mars 2020) détecté en régime **baissier** avec probabilité ~100 %.
- [ ] Analyse de sensibilité (2 vs 3 variables) — à faire si le temps le permet, non bloquant pour la suite.

## Phase 3 — Bêta et allocation

- [x] Calcul du bêta glissant 252 jours (recalcul hebdomadaire, dernier jour de bourse de la semaine) : [apps/portfolio/services/beta_calculator.py](../apps/portfolio/services/beta_calculator.py), commande `python manage.py calculer_betas`.
- [x] Test de l'ajustement de Blume : comparaison bêta brut / ajusté → Blume réduit le turnover de ~13 % (1681 vs 1940 sur 471 semaines) pour une taille de panier quasi identique. **Blume retenu** (`settings.UTILISER_BLUME = True`).
- [x] Implémentation des seuils, paniers et zone tampon anti-churn : [apps/portfolio/services/allocation.py](../apps/portfolio/services/allocation.py), [apps/portfolio/services/simulateur_allocation.py](../apps/portfolio/services/simulateur_allocation.py).
- [x] Historique des allocations hebdomadaires calculé et persisté : `python manage.py calculer_allocations` → 471 semaines, régimes neutre (207) / haussier (182) / baissier (82).

## Phase 4 — Backtest

- [x] Moteur de simulation semaine par semaine (positions, transactions, coûts) : [apps/portfolio/services/backtest_engine.py](../apps/portfolio/services/backtest_engine.py), commande `python manage.py lancer_backtest`.
- [x] Correctif de stabilisation du HMM (whipsaw) : prior de transition collant + filtre de persistance causal (cf. [03_modele_hmm.md](../docs/03_modele_hmm.md) section 9). Turnover total réduit de 1697 à 787 sur 471 semaines.
- [x] Modèle de rééquilibrage par entrées/sorties uniquement (pas de rebéquilibrage forcé à l'équipondération chaque semaine) pour limiter les coûts artificiels.
- [x] Calcul des métriques de performance (Sharpe, Sortino, Calmar, VaR, alpha/bêta) : [apps/portfolio/services/metriques.py](../apps/portfolio/services/metriques.py).
- [x] Comparaison stratégie vs CAC40 buy & hold : résultats dans [05_backtest_metriques.md](../docs/05_backtest_metriques.md) section 7 (stratégie sous-performe sur la période de test, documenté comme constat honnête).

## Phase 5 — Interface Django

- [x] Squelette du projet Django (apps `market_data`, `regimes`, `portfolio`, `dashboard`).
- [x] Intégration Tailwind CSS (`django-tailwind`, app `theme`).
- [x] Vues et templates : accueil (KPIs), performance (Chart.js), régimes (courbe colorée par régime), bêtas (tableau classé), allocations (historique filtrable par date).
- [x] Bouton de relance de backtest depuis l'interface (`call_command` synchrone).
- [x] Graphiques Chart.js (performance, régimes superposés au CAC40).

## Phase 6 — Finalisation

- [x] Documentation des limites (survivorship bias, hypothèses simplificatrices) : cf. [05_backtest_metriques.md](05_backtest_metriques.md) sections 7-8.
- [x] Tests unitaires sur les fonctions critiques : `apps/portfolio/tests.py` (métriques, allocation, anti-churn), `apps/regimes/tests.py` (filtre de persistance). `python -m pytest -q` → 9/9 passés.
- [ ] Rédaction du rapport / support de soutenance (hors périmètre code).

## Prochaine étape immédiate

Une fois ce paramétrage validé, la prochaine action est de démarrer la **Phase 1 (Données)** : mise en place du projet Django, de la structure de dossiers, et du script d'import Yahoo Finance vers DuckDB.
