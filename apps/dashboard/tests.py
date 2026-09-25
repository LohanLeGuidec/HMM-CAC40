from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from apps.dashboard.templatetags.percentage import percentage
from apps.dashboard.views import regimes


class DashboardPercentageTests(TestCase):
    def test_percentage_multiplie_par_100(self):
        assert percentage(-0.0421) == pytest.approx(-4.21)
        assert percentage(0.1234) == pytest.approx(12.34)


class DashboardRegimesViewTests(TestCase):
    def test_regimes_charge_automatiquement_donnees_manquantes(self):
        request = RequestFactory().get("/dashboard/regimes/")
        con_vide = MagicMock()
        con_pleine = MagicMock()
        con_pleine.execute.return_value.fetchdf.side_effect = [
            pd.DataFrame({"date": ["2024-01-01"], "adj_close": [100.0]}),
        ]

        with patch("apps.dashboard.views.duckdb_store.obtenir_connexion", side_effect=[con_vide, con_pleine]), patch(
            "apps.dashboard.views.regimes_store.lire_regimes",
            side_effect=[pd.DataFrame(), pd.DataFrame({"date": ["2024-01-01"], "regime": ["haussier"], "ensemble": ["train"]})],
        ), patch("apps.dashboard.views.call_command") as mock_call, patch(
            "apps.dashboard.views.render",
            return_value=object(),
        ) as mock_render:
            regimes(request)

        assert mock_call.call_count == 2
        mock_call.assert_any_call("import_donnees_marche")
        mock_call.assert_any_call("entrainer_hmm")
        mock_render.assert_called_once()

    def test_template_regime_affiche_prix_et_couleurs(self):
        context = {
            "a_des_donnees": True,
            "labels_json": '["2024-01-01", "2024-01-02"]',
            "regime_labels_json": '["baissier", "haussier"]',
            "train_end_date": '"2024-01-01"',
            "prix_json": "[95.0, 101.0]",
            "regime_colors_json": '["#f87171", "#34d399"]',
        }

        html = render_to_string("dashboard/regimes.html", context)

        assert "data: prixCAC40" in html
        assert "#f87171" in html
        assert "prix_json" not in html
