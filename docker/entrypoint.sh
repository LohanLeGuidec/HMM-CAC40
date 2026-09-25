#!/bin/sh
# Démarrage du conteneur : base Django, données de marché si absentes, puis serveur.
set -e

mkdir -p data

# Première exécution : reprendre la base Django du projet si elle existe (historique des imports,
# entraînements et backtests), sinon elle est créée par migrate.
if [ ! -f "$DJANGO_SQLITE_PATH" ] && [ -f db.sqlite3 ]; then
    echo "Copie de db.sqlite3 vers $DJANGO_SQLITE_PATH"
    cp db.sqlite3 "$DJANGO_SQLITE_PATH"
fi

python manage.py migrate --noinput

# Pipeline complet si la base DuckDB n'existe pas encore (ou si RECALCULER=1).
# Nécessite un accès Internet (Yahoo Finance et FRED) ; compter plusieurs minutes.
if [ ! -f data/marche.duckdb ] || [ "$RECALCULER" = "1" ]; then
    echo "Calcul du pipeline complet..."
    python manage.py import_donnees_marche
    python manage.py importer_taux_sans_risque
    python manage.py entrainer_hmm
    python manage.py calculer_betas
    python manage.py calculer_allocations
    python manage.py lancer_backtest
fi

exec "$@"
