"""Tests unitaires du module de détection de régimes (cf. docs/03_modele_hmm.md)."""

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

from apps.regimes.services.features import decaler_spread
from apps.regimes.services.hmm_model import (
    aligner_sur_modele_precedent,
    etiqueter_etats,
    lisser_persistance,
    probabilites_filtrees,
)


def _modele_fictif(moyennes):
    return type("ModeleFake", (), {"n_components": len(moyennes), "means_": np.array(moyennes)})()


def _modele_gaussien_simple():
    modele = GaussianHMM(n_components=2, covariance_type="diag")
    modele.n_features = 1
    modele.startprob_ = np.array([0.5, 0.5])
    modele.transmat_ = np.array([[0.95, 0.05], [0.05, 0.95]])
    modele.means_ = np.array([[-1.0], [1.0]])
    modele.covars_ = np.array([[0.5], [0.5]])
    return modele


def test_lisser_persistance_ignore_un_flip_isole():
    labels = ["haussier"] * 5 + ["baissier"] + ["haussier"] * 5
    resultat = lisser_persistance(labels, min_jours=3)
    assert resultat == ["haussier"] * 11


def test_lisser_persistance_confirme_un_changement_durable():
    labels = ["haussier"] * 5 + ["baissier"] * 4
    resultat = lisser_persistance(labels, min_jours=3)
    assert resultat[:5] == ["haussier"] * 5
    assert resultat[-1] == "baissier"


def test_etiqueter_etats_trie_par_tendance():
    # colonnes : tendance_longue, tendance_courte, volatilite_log
    modele = _modele_fictif([[0.8, 0.5, -0.6], [-1.5, -1.2, 1.8], [0.0, 0.1, 0.0]])
    mapping = etiqueter_etats(modele)
    assert mapping == {0: "haussier", 1: "baissier", 2: "neutre"}


def test_alignement_conserve_les_labels_malgre_une_permutation_des_etats():
    precedent = _modele_fictif([[-1.5, 1.8], [0.0, 0.0], [0.8, -0.6]])
    mapping_precedent = {0: "baissier", 1: "neutre", 2: "haussier"}
    # Le nouveau modèle a les mêmes états dans un autre ordre, légèrement déplacés
    nouveau = _modele_fictif([[0.7, -0.5], [-1.4, 1.7], [0.1, 0.1]])
    mapping = aligner_sur_modele_precedent(nouveau, precedent, mapping_precedent)
    assert mapping == {0: "haussier", 1: "baissier", 2: "neutre"}


def test_filtre_forward_est_causal():
    """Modifier les observations futures ne doit jamais changer les probabilités passées."""
    modele = _modele_gaussien_simple()
    observations = np.array([[-1.0], [-0.8], [-1.2], [0.9], [1.1]])
    futur_modifie = observations.copy()
    futur_modifie[3:] = -5.0
    p1 = probabilites_filtrees(modele, observations)
    p2 = probabilites_filtrees(modele, futur_modifie)
    np.testing.assert_allclose(p1[:3], p2[:3])
    np.testing.assert_allclose(p1.sum(axis=1), 1.0)


def test_spread_mensuel_decale_d_un_mois():
    """La moyenne FRED de novembre (datée du 1er novembre) n'est utilisable qu'en décembre."""
    spread = pd.DataFrame(
        {"date": pd.to_datetime(["2020-10-01", "2020-11-02", "2020-12-01"]), "spread_taux": [0.3, 0.5, 0.7]}
    )
    dates = pd.Series(pd.to_datetime(["2020-11-02", "2020-11-30", "2020-12-01", "2021-01-04"]))
    aligne = decaler_spread(spread, dates, decalage_mois=1)
    assert aligne.tolist() == [0.3, 0.3, 0.3, 0.7]
