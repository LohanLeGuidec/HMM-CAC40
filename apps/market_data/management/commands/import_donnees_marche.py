"""Commande d'import des données de marché : Yahoo Finance + FRED -> DuckDB.

Usage : python manage.py import_donnees_marche
"""

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.market_data.models import ImportDonneesMarche
from apps.market_data.services import duckdb_store, fred_fetcher, yahoo_fetcher

# Seuils de nettoyage définis dans docs/02_donnees_marche.md
LIMITE_FORWARD_FILL_JOURS = 2
SEUIL_EXCLUSION_MANQUANTES = 0.05


def taux_manquantes_depuis_cotation(prix_ajustes: pd.Series) -> float:
    """Part de valeurs manquantes calculée à partir de la première cotation du titre.

    Les jours antérieurs à l'introduction en bourse ne sont pas des "trous" : sans cette
    règle, un historique depuis 2000 exclurait toute action cotée plus tard (Legrand 2006,
    Edenred 2010, Worldline 2014...). Retourne 1.0 si le titre n'a aucune cotation.
    """
    premiere_cotation = prix_ajustes.first_valid_index()
    if premiere_cotation is None:
        return 1.0
    return float(prix_ajustes.loc[premiere_cotation:].isna().mean())


class Command(BaseCommand):
    help = "Importe l'historique (Yahoo Finance, depuis DATE_DEBUT_HISTORIQUE) et le spread de taux (FRED) dans DuckDB."

    def handle(self, *args, **options):
        date_debut = settings.DATE_DEBUT_HISTORIQUE
        date_fin = settings.DATE_FIN_HISTORIQUE

        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)

        # 1. Téléchargement du benchmark : sert de calendrier de référence des jours de bourse
        self.stdout.write("Téléchargement du benchmark CAC40 (^FCHI)...")
        prix_benchmark = yahoo_fetcher.telecharger_historique(
            settings.TICKER_BENCHMARK, date_debut, date_fin
        )
        if prix_benchmark.empty:
            self.stderr.write("Impossible de télécharger le benchmark, import interrompu.")
            return
        calendrier_bourse = prix_benchmark.index

        self._importer_ticker(con, settings.TICKER_BENCHMARK, "CAC 40", prix_benchmark, calendrier_bourse)

        # 2. Téléchargement de l'univers d'actions du CAC40
        univers = pd.read_csv(settings.UNIVERS_CAC40_CSV)
        for _, ligne in univers.iterrows():
            ticker, nom = ligne["ticker"], ligne["nom"]
            self.stdout.write(f"Téléchargement de {ticker} ({nom})...")
            try:
                prix = yahoo_fetcher.telecharger_historique(ticker, date_debut, date_fin)
                self._importer_ticker(con, ticker, nom, prix, calendrier_bourse)
            except Exception as erreur:  # une action indisponible ne doit pas bloquer les autres
                self._enregistrer_echec(ticker, nom, date_debut, date_fin, str(erreur))
                self.stderr.write(f"  échec : {erreur}")

        # 3. Spread de taux France - Allemagne (FRED)
        self.stdout.write("Téléchargement du spread de taux France - Allemagne (FRED)...")
        try:
            spread = fred_fetcher.telecharger_spread_taux(
                date_debut,
                date_fin,
                settings.FRED_SERIE_TAUX_FRANCE,
                settings.FRED_SERIE_TAUX_ALLEMAGNE,
            )
            # Série mensuelle FRED propagée sur le calendrier boursier journalier (forward-fill)
            spread_journalier = spread.reindex(calendrier_bourse, method="ffill")
            duckdb_store.enregistrer_spread_taux(con, spread_journalier)
            self.stdout.write(self.style.SUCCESS(f"  {len(spread_journalier)} jours de spread enregistrés."))
        except Exception as erreur:
            self.stderr.write(f"  échec du téléchargement du spread de taux : {erreur}")

        con.close()
        self.stdout.write(self.style.SUCCESS("Import terminé."))

    def _importer_ticker(self, con, ticker, nom, prix, calendrier_bourse):
        """Nettoie, valide et enregistre l'historique d'un ticker."""
        prix_aligne = prix.reindex(calendrier_bourse)
        prix_nettoye = prix_aligne.ffill(limit=LIMITE_FORWARD_FILL_JOURS)

        taux_manquantes = taux_manquantes_depuis_cotation(prix_nettoye["adj_close"])

        if taux_manquantes > SEUIL_EXCLUSION_MANQUANTES:
            self._enregistrer_exclusion(ticker, nom, taux_manquantes)
            self.stdout.write(
                self.style.WARNING(
                    f"  exclu : {taux_manquantes:.1%} de valeurs manquantes (seuil {SEUIL_EXCLUSION_MANQUANTES:.0%})"
                )
            )
            return

        prix_final = prix_nettoye.dropna(subset=["adj_close"])
        nb_lignes = duckdb_store.enregistrer_prix(con, ticker, prix_final)
        duckdb_store.calculer_et_enregistrer_rendements(con, ticker)

        ImportDonneesMarche.objects.update_or_create(
            ticker=ticker,
            defaults={
                "nom": nom,
                "date_debut_historique": settings.DATE_DEBUT_HISTORIQUE,
                "date_fin_historique": settings.DATE_FIN_HISTORIQUE,
                "nb_lignes_importees": nb_lignes,
                "taux_valeurs_manquantes": taux_manquantes,
                "statut": "ok",
                "message_erreur": "",
            },
        )
        premiere_date = prix_final.index.min()
        self.stdout.write(self.style.SUCCESS(f"  {nb_lignes} lignes importées (depuis le {premiere_date:%Y-%m-%d})."))

    def _enregistrer_exclusion(self, ticker, nom, taux_manquantes):
        ImportDonneesMarche.objects.update_or_create(
            ticker=ticker,
            defaults={
                "nom": nom,
                "date_debut_historique": settings.DATE_DEBUT_HISTORIQUE,
                "date_fin_historique": settings.DATE_FIN_HISTORIQUE,
                "nb_lignes_importees": 0,
                "taux_valeurs_manquantes": taux_manquantes,
                "statut": "exclu",
                "message_erreur": "Taux de valeurs manquantes supérieur au seuil de 5 %.",
            },
        )

    def _enregistrer_echec(self, ticker, nom, date_debut, date_fin, message_erreur):
        ImportDonneesMarche.objects.update_or_create(
            ticker=ticker,
            defaults={
                "nom": nom,
                "date_debut_historique": date_debut,
                "date_fin_historique": date_fin,
                "nb_lignes_importees": 0,
                "taux_valeurs_manquantes": 1.0,
                "statut": "echec",
                "message_erreur": message_erreur,
            },
        )
