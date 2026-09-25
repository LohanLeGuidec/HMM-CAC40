"""Construction des variables d'observation du HMM à partir de DuckDB.

Variables (cf. docs/03_modele_hmm.md, section 3 révisée) :

- ``tendance_longue`` : rendement log cumulé du CAC40 sur ``HMM_FENETRE_TENDANCE_LONGUE_JOURS``
  (60 j). C'est la variable qui porte la *direction* du marché et sert à étiqueter les états.
- ``tendance_courte`` : rendement log cumulé sur ``HMM_FENETRE_TENDANCE_COURTE_JOURS`` (20 j),
  pour réagir plus vite aux retournements.
- ``volatilite_log`` : log de la volatilité réalisée glissante annualisée (20 j). Le log rend la
  distribution plus proche d'une gaussienne (la vol brute est très asymétrique à droite).
- ``variation_spread`` (optionnelle, ``HMM_UTILISER_SPREAD``) : variation du spread France -
  Allemagne sur ``HMM_SPREAD_VARIATION_JOURS``, décalée de ``HMM_SPREAD_DECALAGE_MOIS``.

Pourquoi plus de rendement quotidien ni de niveau de spread :
- le rendement quotidien est dominé par le bruit : ses moyennes par état ne diffèrent que de
  ~0,02 écart-type, le HMM ne pouvait donc pas s'en servir pour séparer hausse et baisse ;
- le *niveau* du spread est non stationnaire (0,44 en moyenne sur le train, 0,55-0,83 sur le
  test, soit +2,5 écarts-types) : il faisait basculer tout le test dans un même état.

Fuite d'information corrigée : la série FRED est une *moyenne mensuelle* datée du 1er du mois
puis propagée en journalier. Sans décalage, le 1er novembre on connaissait déjà la moyenne de
tout novembre. Le spread d'un mois M n'est utilisé qu'à partir du mois M + 1.
"""

import numpy as np
import pandas as pd
from django.conf import settings

def decaler_spread(spread: pd.DataFrame, dates_cibles: pd.Series, decalage_mois: int) -> pd.Series:
    """Aligne le spread sur ``dates_cibles`` en n'utilisant que des valeurs publiées.

    La valeur datée d pour la série FRED mensuelle n'est connue qu'à partir de d + decalage_mois.
    Retourne une série alignée sur ``dates_cibles`` (NaN tant qu'aucune valeur n'est publiée).
    """
    serie = spread.dropna(subset=["spread_taux"]).copy()
    serie["date_disponible"] = pd.to_datetime(serie["date"]) + pd.DateOffset(months=decalage_mois)
    serie = serie.sort_values("date_disponible")[["date_disponible", "spread_taux"]]
    cibles = pd.DataFrame({"date": pd.to_datetime(dates_cibles)}).reset_index(drop=True)
    aligne = pd.merge_asof(
        cibles.sort_values("date"), serie, left_on="date", right_on="date_disponible", direction="backward"
    )
    return aligne.set_index("date")["spread_taux"]


def construire_observations(con) -> pd.DataFrame:
    """Retourne un DataFrame indexé par date avec les variables d'observation du HMM.

    La première colonne est toujours ``tendance_longue`` (utilisée pour l'étiquetage des états).
    """
    rendements = con.execute(
        "SELECT date, rendement_log FROM rendements WHERE ticker = ? ORDER BY date",
        [settings.TICKER_BENCHMARK],
    ).fetchdf()
    if rendements.empty:
        return pd.DataFrame()
    rendements["date"] = pd.to_datetime(rendements["date"])
    observations = rendements.set_index("date")
    r = observations["rendement_log"]

    observations["tendance_longue"] = r.rolling(settings.HMM_FENETRE_TENDANCE_LONGUE_JOURS).sum()
    observations["tendance_courte"] = r.rolling(settings.HMM_FENETRE_TENDANCE_COURTE_JOURS).sum()
    volatilite = r.rolling(settings.HMM_FENETRE_VOLATILITE_JOURS).std() * np.sqrt(252)
    observations["volatilite_log"] = np.log(volatilite)

    colonnes = ["tendance_longue", "tendance_courte", "volatilite_log"]

    if settings.HMM_UTILISER_SPREAD:
        spread = con.execute("SELECT date, spread_taux FROM spread_taux ORDER BY date").fetchdf()
        spread_publie = decaler_spread(spread, observations.index.to_series(), settings.HMM_SPREAD_DECALAGE_MOIS)
        observations["spread_publie"] = spread_publie.to_numpy()
        observations["variation_spread"] = observations["spread_publie"].diff(settings.HMM_SPREAD_VARIATION_JOURS)
        colonnes.append("variation_spread")

    # Les premiers jours n'ont pas de fenêtre complète : on les retire
    return observations[colonnes].dropna()
