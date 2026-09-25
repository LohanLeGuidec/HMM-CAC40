"""Calcul du bêta glissant et du momentum de chaque action (cf. docs/04_beta_allocation.md)."""

import numpy as np
import pandas as pd
from django.conf import settings

from .calendrier import dates_rebalancement


def _rendements_ticker(con, ticker: str) -> pd.Series:
    df = con.execute(
        "SELECT date, rendement_log FROM rendements WHERE ticker = ? ORDER BY date", [ticker]
    ).fetchdf()
    return df.set_index("date")["rendement_log"]


def calculer_betas_glissants(con, tickers: list[str], benchmark: str, fenetre: int) -> pd.DataFrame:
    """Calcule le bêta glissant (brut et ajusté Blume) et le momentum de chaque ticker.

    Aucune fuite d'information : au jour t, seules les observations précédant (et incluant)
    t sont utilisées.
    """
    rendements_benchmark = _rendements_ticker(con, benchmark)
    # Dates de rééquilibrage issues du calendrier du benchmark (et non du 1er ticker de la
    # liste) : avec un historique depuis 2000, les actions n'ont pas toutes la même date de
    # début. Une action n'apparaît qu'aux dates où elle a déjà `fenetre` jours d'historique.
    dates_periode = dates_rebalancement(pd.DatetimeIndex(rendements_benchmark.index), settings.FREQUENCE_REEQUILIBRAGE)
    resultats = []

    for ticker in tickers:
        rendements_actif = _rendements_ticker(con, ticker)
        aligne = pd.concat(
            [rendements_actif, rendements_benchmark], axis=1, keys=["actif", "benchmark"]
        ).dropna()

        covariance = aligne["actif"].rolling(fenetre).cov(aligne["benchmark"])
        variance = aligne["benchmark"].rolling(fenetre).var()
        beta_brut = (covariance / variance).dropna()

        # Momentum : rendement cumulé sur la fenêtre glissante (cf. settings.MOMENTUM_FENETRE_JOURS)
        momentum = np.expm1(
            aligne["actif"].rolling(settings.MOMENTUM_FENETRE_JOURS).sum()
        ).reindex(beta_brut.index)

        beta_periode = beta_brut.reindex(dates_periode).dropna()
        momentum_periode = momentum.reindex(beta_periode.index)
        beta_ajuste = (2 / 3) * beta_periode + (1 / 3) * 1.0

        resultats.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "beta_brut": beta_periode,
                    "beta_ajuste": beta_ajuste,
                    "momentum_63j": momentum_periode,
                }
            )
        )

    tableau = pd.concat(resultats)
    tableau.index.name = "date"
    return tableau.reset_index()
