"""Exporte les résultats DuckDB dans des CSV prêts pour Power BI.

Usage : python manage.py exporter_powerbi
"""

from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.market_data.services import duckdb_store


TABLES_A_EXPORTER = (
    "prix_ohlcv",
    "rendements",
    "spread_taux",
    "taux_sans_risque",
    "regimes_marche",
    "beta_glissant",
    "allocations_hebdomadaires",
    "valeur_portefeuille",
    "valeur_comparaisons",
    "transactions",
)


class Command(BaseCommand):
    help = "Exporte les indicateurs et résultats dans data/powerbi au format CSV."

    def handle(self, *args, **options):
        dossier_export = Path(settings.DATA_DIR) / "powerbi"
        dossier_export.mkdir(parents=True, exist_ok=True)

        con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)
        tables_existantes = {
            ligne[0]
            for ligne in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }

        nb_tables = 0
        for nom_table in TABLES_A_EXPORTER:
            if nom_table not in tables_existantes:
                continue

            donnees = con.execute(f"SELECT * FROM {nom_table}").fetchdf()
            chemin_csv = dossier_export / f"{nom_table}.csv"
            donnees.to_csv(chemin_csv, index=False, encoding="utf-8-sig")
            nb_tables += 1
            self.stdout.write(f"  {nom_table}: {len(donnees)} lignes -> {chemin_csv}")

        con.close()
        self.stdout.write(
            self.style.SUCCESS(
                f"{nb_tables} fichiers exportés dans {dossier_export}."
            )
        )