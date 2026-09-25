"""Tests du nettoyage des données de marché (cf. docs/02_donnees_marche.md)."""

import numpy as np
import pandas as pd

from apps.market_data.management.commands.import_donnees_marche import taux_manquantes_depuis_cotation


def test_jours_avant_introduction_en_bourse_ne_comptent_pas_comme_manquants():
    # 80 jours avant la cotation, puis 20 jours cotés dont 1 trou
    prix = pd.Series([np.nan] * 80 + [10.0] * 10 + [np.nan] + [10.0] * 9)
    assert taux_manquantes_depuis_cotation(prix) == 1 / 20


def test_titre_sans_aucune_cotation_est_entierement_manquant():
    assert taux_manquantes_depuis_cotation(pd.Series([np.nan] * 5)) == 1.0
