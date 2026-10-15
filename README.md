# Stratégie HMM CAC40

Projet de M2 Big Data portant sur la détection de régimes de marché via un Hidden Markov Model (HMM) appliqué au CAC40, puis sur l’allocation dynamique d’un portefeuille d’actions à partir d’un signal de bêta et de momentum.

L’objectif est d’évaluer si la combinaison d’un modèle de régimes de marché et d’une allocation probabiliste permet de surperformer l’indice de référence sur des périodes de stress et de reprise.

## Vue d’ensemble

- Détection des régimes de marché via HMM
- Importation des données de marché et des taux sans risque
- Estimation des betas glissants et du momentum
- Calcul d’allocations conditionnelles par régime
- Backtest d’une stratégie de portefeuille
- Export de données pour Power BI
- Dashboard Django pour visualisation

## Démonstration

https://github.com/user-attachments/assets/bdf0662e-8ae9-495c-bbc3-db94172a5594

## Architecture du projet

```
apps/
├── dashboard/          # interface utilisateur et visualisation
├── market_data/        # import, stockage et export des données marché
├── portfolio/          # portefeuille, backtest et métriques
├── regimes/            # entraînement HMM et gestion des régimes
├── ...
config/                 # settings Django et URLs
requirements/           # dépendances Python
theme/                  # frontend / templates thématiques
docs/                   # cahier des charges et documentation technique
```

## Documentation

La spécification complète du projet est disponible dans le dossier [docs/](docs/) et doit être lue dans l’ordre :

1. 01_cahier_des_charges.md
2. 02_donnees_marche.md
3. 03_modele_hmm.md
4. 04_beta_allocation.md
5. 05_backtest_metriques.md
6. 06_architecture_technique.md
7. 07_roadmap.md

## Installation

```bash
activate.cmd
```

Cette commande prépare l’environnement virtuel et installe les dépendances listées dans `requirements/base.txt` et `requirements/dev.txt`.

## Pipeline d’exécution

```bash
python manage.py import_donnees_marche      # Yahoo Finance + FRED -> DuckDB
python manage.py importer_taux_sans_risque
python manage.py entrainer_hmm               # régimes de marché (walk-forward)
python manage.py calculer_betas              # bêta glissant + momentum
python manage.py calculer_allocations        # allocation probabiliste par régime
python manage.py lancer_backtest             # simulation + métriques
python manage.py exporter_powerbi            # export des données en CSV pour Power BI
python manage.py runserver                   # dashboard sur http://127.0.0.1:8000
```

## Lancer avec Docker

Prérequis : [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et démarré.

```bash
docker compose up --build        # construit l'image et lance le tableau de bord
```

Le tableau de bord est ensuite disponible sur http://localhost:8000.

- Le dossier `data/` est partagé avec le conteneur : la base DuckDB et la base Django y sont conservées d'un lancement à l'autre.
- Si `data/marche.duckdb` n'existe pas (par exemple après un `git clone`), le conteneur lance automatiquement tout le pipeline au premier démarrage (import Yahoo Finance et FRED, HMM, bêtas, allocations, backtest). Il faut un accès Internet et compter plusieurs minutes.
- Pour tout recalculer : passer `RECALCULER: "1"` dans `docker-compose.yml`, puis relancer `docker compose up`.

Commandes utiles :

```bash
docker compose up -d                                          # lancer en arrière-plan
docker compose logs -f                                        # suivre les journaux
docker compose exec web python manage.py lancer_backtest      # lancer une commande dans le conteneur
docker compose exec web python -m pytest -q                   # tests
docker compose down                                           # arrêter
```

## Tests

```bash
python -m pytest -q
```

## Résultat actuel

Les résultats de référence ci-dessous sont ceux du backtest sur la période de test **octobre 2018 à septembre 2026**, avec un capital initial de 1 000 000 €. Les portefeuilles sont valorisés au cours de clôture, sans dividendes ; le CAC 40 est l’indice de prix ^FCHI.

| Stratégie | Rendement annualisé | Sharpe | Drawdown maximal |
|---|---:|---:|---:|
| **Rebond (HMM)** — allocation contrariante selon les probabilités de régime | **8,5 %** | **0,39** | -38,3 % |
| **1/3 par panier (sans HMM)** — répartition égale entre les paniers défensif, neutre et offensif | 7,2 % | 0,32 | **-36,6 %** |
| **CAC 40** — achat-conservation de l’indice | 6,1 % | 0,26 | -38,6 % |
| **Suiveur (HMM)** — allocation suivant directement le régime détecté | 5,7 % | 0,21 | -38,7 % |

Sur cette période, la stratégie de rebond obtient le rendement annualisé et le Sharpe les plus élevés. Le portefeuille 1/3 par panier, lui, ne dépend pas du signal HMM et affiche le drawdown maximal le plus faible parmi ces quatre résultats. Ces performances historiques ne garantissent pas les performances futures : la stratégie de rebond dépend notamment des reprises après les phases baissières, et l’univers d’actions actuel du CAC 40 introduit un biais de survivance. Les trois portefeuilles actifs sélectionnent des actions de l’univers CAC 40 ; ils ne répliquent pas l’indice, dont les pondérations sont fondées sur la capitalisation.

Les chiffres, la méthodologie et les limites sont détaillés dans [docs/04_beta_allocation.md](docs/04_beta_allocation.md) et [docs/05_backtest_metriques.md](docs/05_backtest_metriques.md).

## Objectif du dépôt

Ce dépôt sert de base de travail pour un projet académique et de démonstration technique sur :

- la détection de régimes de marché ;
- la construction d’un portefeuille multi-actifs ;
- l’évaluation empirique d’une stratégie de rotation de bêta ;
- la visualisation des résultats via Django et Power BI.
