"""Tests unitaires des fonctions critiques : métriques et règles d'allocation."""

import numpy as np
import pandas as pd
import pytest
from django.test import override_settings

from apps.portfolio.services import allocation, metriques


def test_rendement_annualise_double_en_un_an():
    valeurs_252 = pd.Series([100.0] + [100.0] * 251 + [200.0])
    resultat = metriques.rendement_annualise(valeurs_252)
    assert resultat == pytest.approx(1.0, rel=1e-6)


def test_max_drawdown_detecte_la_pire_baisse():
    valeurs = pd.Series([100, 120, 90, 110])
    assert metriques.max_drawdown(valeurs) == pytest.approx(90 / 120 - 1)


def test_var_historique_est_negative_pour_serie_avec_pertes():
    rendements = pd.Series([0.01, -0.02, 0.015, -0.03, 0.005, -0.01, 0.02])
    assert metriques.var_historique(rendements, 0.95) < 0


@override_settings(BETA_METHODE_SEUILS="fixes")
def test_trier_candidats_haussier_favorise_beta_eleve_et_momentum_positif():
    candidats = pd.DataFrame(
        {"beta": [1.5, 1.3, 1.8], "momentum": [0.10, -0.05, 0.02]},
        index=["A", "B", "C"],
    )
    resultat = allocation.trier_candidats(candidats, "haussier")
    assert set(resultat) == {"A", "B", "C"}
    assert resultat[0] in {"A", "C"}


@override_settings(BETA_METHODE_SEUILS="fixes")
def test_trier_candidats_exclut_les_beta_hors_seuil():
    candidats = pd.DataFrame({"beta": [1.0, 0.5], "momentum": [0.0, 0.0]}, index=["A", "B"])
    assert allocation.trier_candidats(candidats, "haussier") == []


def test_anti_churn_reset_top10_si_changement_de_regime():
    candidats = [f"T{i}" for i in range(20)]
    panier_precedent = {"T0", "T1", "T18", "T19"}
    resultat = allocation.appliquer_anti_churn(candidats, panier_precedent, "haussier", "baissier")
    assert resultat == set(candidats[:10])


def test_anti_churn_conserve_les_positions_dans_le_buffer():
    candidats = [f"T{i}" for i in range(20)]
    panier_precedent = {"T0", "T12"}
    resultat = allocation.appliquer_anti_churn(candidats, panier_precedent, "haussier", "haussier")
    assert "T12" in resultat
    assert set(candidats[:10]).issubset(resultat)


@override_settings(BETA_METHODE_SEUILS="quantiles", BETA_QUANTILE_COUPURE=0.3)
def test_quantiles_repartissent_toutes_les_actions_en_trois_paniers():
    betas = pd.Series(np.linspace(0.5, 1.5, 30))
    candidats = pd.DataFrame({"beta": betas.to_numpy(), "momentum": 0.0}, index=[f"T{i}" for i in range(30)])
    defensif = set(allocation.trier_candidats(candidats, "baissier"))
    neutre = set(allocation.trier_candidats(candidats, "neutre"))
    offensif = set(allocation.trier_candidats(candidats, "haussier"))
    assert not (defensif & neutre) and not (neutre & offensif) and not (defensif & offensif)
    assert len(defensif | neutre | offensif) == 30  # aucune zone grise
    assert 8 <= len(defensif) <= 10 and 8 <= len(offensif) <= 10


@override_settings(BETA_METHODE_SEUILS="quantiles", BETA_QUANTILE_COUPURE=0.33)
def test_quantiles_suivent_le_niveau_des_betas():
    # Tous les bêtas décalés de +0,5 : les paniers doivent rester les mêmes actions
    base = pd.Series(np.linspace(0.6, 1.4, 12))
    s1 = allocation.seuils_beta(base)
    s2 = allocation.seuils_beta(base + 0.5)
    assert s2[0] == pytest.approx(s1[0] + 0.5) and s2[3] == pytest.approx(s1[3] + 0.5)


PROBAS_BAISSIER = {"haussier": 0.1, "neutre": 0.2, "baissier": 0.7}


def test_rebond_envoie_la_proba_baissiere_au_panier_offensif():
    from apps.portfolio.services.allocation_probabiliste import poids_des_paniers
    poids = poids_des_paniers(PROBAS_BAISSIER, "rebond")
    assert poids == pytest.approx({"offensif": 0.7, "neutre": 0.2, "defensif": 0.1})


def test_suiveur_envoie_la_proba_baissiere_au_panier_defensif():
    from apps.portfolio.services.allocation_probabiliste import poids_des_paniers
    poids = poids_des_paniers(PROBAS_BAISSIER, "suiveur")
    assert poids == pytest.approx({"offensif": 0.1, "neutre": 0.2, "defensif": 0.7})


def test_equipondere_ignore_le_hmm():
    from apps.portfolio.services.allocation_probabiliste import poids_des_paniers
    poids = poids_des_paniers(PROBAS_BAISSIER, "equipondere")
    assert poids == pytest.approx({"offensif": 1 / 3, "neutre": 1 / 3, "defensif": 1 / 3})


def test_plafond_offensif_reporte_l_excedent_sur_le_neutre():
    from apps.portfolio.services.allocation_probabiliste import poids_des_paniers
    poids = poids_des_paniers(PROBAS_BAISSIER, "rebond", plafond_offensif=0.5)
    assert poids == pytest.approx({"offensif": 0.5, "neutre": 0.4, "defensif": 0.1})
    assert sum(poids.values()) == pytest.approx(1.0)


def test_mode_inconnu_refuse():
    from apps.portfolio.services.allocation_probabiliste import poids_des_paniers
    with pytest.raises(ValueError):
        poids_des_paniers(PROBAS_BAISSIER, "inconnu")
