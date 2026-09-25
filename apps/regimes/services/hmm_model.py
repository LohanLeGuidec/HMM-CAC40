"""Entraînement, étiquetage, alignement et décodage causal du HMM Gaussien de régimes.

Principes (cf. docs/03_modele_hmm.md) :

1. Étiquetage par la **tendance moyenne** de chaque état (1re variable d'observation) :
   état à la tendance la plus basse = baissier, la plus haute = haussier.
2. **Alignement** d'un ré-entraînement à l'autre : chaque nouvel état est associé à l'état
   le plus proche du modèle précédent (affectation hongroise sur les moyennes), pour que
   « haussier » garde le même sens tout au long du walk-forward.
3. **Décodage causal** : filtre forward (probabilités filtrées P(état_t | obs_1..t)), jamais
   Viterbi ni forward-backward, qui utilisent des observations futures.
"""

import numpy as np
from django.conf import settings
from hmmlearn.hmm import GaussianHMM
from scipy.optimize import linear_sum_assignment
from scipy.special import logsumexp

LABELS_PAR_RANG = ["baissier", "neutre", "haussier"]  # tri croissant par tendance moyenne
INDICE_VARIABLE_ETIQUETAGE = 0  # tendance_longue, 1re colonne de features.construire_observations


class Standardiseur:
    """Standardisation (z-score) ajustée une seule fois sur le train, jamais recalculée."""

    def __init__(self):
        self.moyennes = None
        self.ecarts_types = None

    def ajuster(self, observations: np.ndarray) -> "Standardiseur":
        self.moyennes = observations.mean(axis=0)
        self.ecarts_types = observations.std(axis=0)
        return self

    def transformer(self, observations: np.ndarray) -> np.ndarray:
        return (observations - self.moyennes) / self.ecarts_types


def entrainer_modele(observations_standardisees: np.ndarray, n_etats: int, graine_aleatoire: int = 42) -> GaussianHMM:
    """Entraîne un HMM Gaussien à covariance diagonale.

    Plusieurs initialisations aléatoires (``HMM_NB_INITIALISATIONS``) sont essayées et la
    meilleure log-vraisemblance est retenue : l'EM de Baum-Welch converge vers des optima
    locaux, une seule graine rend le résultat fragile d'un ré-entraînement à l'autre.
    Un prior de transition "collant" (diagonale renforcée) favorise la persistance d'état.
    """
    prior_transition = np.ones((n_etats, n_etats))
    np.fill_diagonal(prior_transition, settings.HMM_TRANSMAT_PRIOR_DIAGONAL)

    meilleur_modele, meilleur_score = None, -np.inf
    for essai in range(settings.HMM_NB_INITIALISATIONS):
        modele = GaussianHMM(
            n_components=n_etats,
            covariance_type="diag",
            n_iter=200,
            random_state=graine_aleatoire + essai,
            transmat_prior=prior_transition,
        )
        modele.fit(observations_standardisees)
        score = modele.score(observations_standardisees)
        if score > meilleur_score:
            meilleur_modele, meilleur_score = modele, score
    return meilleur_modele


def etiqueter_etats(modele: GaussianHMM) -> dict:
    """Associe chaque état à un label en triant les états par tendance moyenne croissante."""
    tendances = modele.means_[:, INDICE_VARIABLE_ETIQUETAGE]
    ordre = np.argsort(tendances)
    return {int(etat): LABELS_PAR_RANG[rang] for rang, etat in enumerate(ordre)}


def aligner_sur_modele_precedent(modele: GaussianHMM, modele_precedent: GaussianHMM, mapping_precedent: dict) -> dict:
    """Associe chaque état du nouveau modèle à l'état le plus proche du modèle précédent.

    Affectation hongroise sur la distance euclidienne entre moyennes (espace standardisé).
    Si l'alignement contredit l'ordre des tendances (ex. un "haussier" hérité dont la tendance
    est devenue la plus basse), on retombe sur l'étiquetage par tendance : le sens économique
    prime sur la continuité.
    """
    couts = np.linalg.norm(modele.means_[:, None, :] - modele_precedent.means_[None, :, :], axis=2)
    lignes, colonnes = linear_sum_assignment(couts)
    mapping = {int(etat): mapping_precedent[int(etat_prec)] for etat, etat_prec in zip(lignes, colonnes)}

    tendances = modele.means_[:, INDICE_VARIABLE_ETIQUETAGE]
    ordre_aligne = [etat for label in LABELS_PAR_RANG for etat, lab in mapping.items() if lab == label]
    if list(np.argsort(tendances)) != ordre_aligne:
        return etiqueter_etats(modele)
    return mapping


def _log_vraisemblances_emission(modele: GaussianHMM, observations: np.ndarray) -> np.ndarray:
    """log p(x_t | état k) pour une gaussienne diagonale, matrice (T, K)."""
    variances = np.array([np.diag(c) for c in modele.covars_])  # (K, D)
    ecarts = observations[:, None, :] - modele.means_[None, :, :]  # (T, K, D)
    return -0.5 * (np.log(2 * np.pi * variances)[None, :, :] + ecarts**2 / variances[None, :, :]).sum(axis=2)


def probabilites_filtrees(modele: GaussianHMM, observations: np.ndarray) -> np.ndarray:
    """Filtre forward : P(état_t | x_1..x_t), matrice (T, K). Strictement causal."""
    log_emission = _log_vraisemblances_emission(modele, observations)
    log_transition = np.log(modele.transmat_ + 1e-300)
    log_alpha = np.empty_like(log_emission)
    log_alpha[0] = np.log(modele.startprob_ + 1e-300) + log_emission[0]
    log_alpha[0] -= logsumexp(log_alpha[0])
    for t in range(1, len(observations)):
        log_alpha[t] = logsumexp(log_alpha[t - 1][:, None] + log_transition, axis=0) + log_emission[t]
        log_alpha[t] -= logsumexp(log_alpha[t])
    return np.exp(log_alpha)


def decoder_regimes(modele: GaussianHMM, observations_standardisees: np.ndarray, mapping: dict):
    """Décode les régimes de façon causale (filtre forward).

    Retourne (labels, probabilites_par_label, log_vraisemblance). Le label du jour t est l'état
    de plus forte probabilité filtrée, calculée uniquement avec les observations jusqu'à t.
    """
    probabilites = probabilites_filtrees(modele, observations_standardisees)
    labels = [mapping[int(etat)] for etat in probabilites.argmax(axis=1)]
    etat_par_label = {label: etat for etat, label in mapping.items()}
    probabilites_par_label = {label: probabilites[:, etat_par_label[label]] for label in LABELS_PAR_RANG}
    log_vraisemblance = float(modele.score(observations_standardisees))
    return labels, probabilites_par_label, log_vraisemblance


def lisser_persistance(labels: list[str], min_jours: int) -> list[str]:
    """Filtre causal : un changement de régime n'est confirmé que s'il persiste au moins
    `min_jours` jours consécutifs ; sinon le régime précédemment confirmé est maintenu.

    Purement causal (ne regarde jamais en avant) : utilisable en walk-forward sans fuite
    d'information.
    """
    if not labels:
        return labels

    regime_confirme = labels[0]
    candidat = labels[0]
    compteur_candidat = 1
    resultat = [regime_confirme]

    for label in labels[1:]:
        if label == candidat:
            compteur_candidat += 1
        else:
            candidat = label
            compteur_candidat = 1

        if candidat != regime_confirme and compteur_candidat >= min_jours:
            regime_confirme = candidat

        resultat.append(regime_confirme)

    return resultat
