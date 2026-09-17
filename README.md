# Stratégie HMM CAC40

Projet M2 Big Data : détection de régimes de marché (HMM) sur le CAC40 et allocation
d'un portefeuille d'actions par bêta, pour tenter de battre l'indice.

## Documentation

Toute la spécification du projet est dans [docs/](docs/) (01 à 07, à lire dans l'ordre).

## Installation

```
activate.cmd          # crée le venv et installe requirements/base.txt + dev.txt
```

## Pipeline (ordre d'exécution)

```
python manage.py import_donnees_marche      # Yahoo Finance + FRED -> DuckDB
python manage.py importer_taux_sans_risque
python manage.py entrainer_hmm               # régimes de marché (walk-forward)
python manage.py calculer_betas              # bêta glissant + momentum
python manage.py calculer_allocations        # allocation probabiliste par régime
python manage.py lancer_backtest             # simulation + métriques
python manage.py exporter_powerbi            # export des données en CSV pour Power BI
python manage.py runserver                   # dashboard sur http://127.0.0.1:8000
```

## Tests

```
python -m pytest -q
```

## Résultat actuel (cf. docs/05_backtest_metriques.md)

La stratégie sous-performe le CAC40 sur la période de test (-4.21% vs +4.60%
annualisé), pour des raisons diagnostiquées et documentées (pas un bug) : effet
rebond post-krach inhérent à un détecteur de régime rétrospectif, et écart
structurel entre un portefeuille stock-picking et un indice pondéré par
capitalisation.
