"""Construction des allocations : 3 paniers de bêta pondérés par les régimes du HMM (cf. docs/04).

Les actions sont réparties en 3 paniers par terciles de bêta (défensif / neutre / offensif,
cf. allocation.py). Le poids de chaque panier dépend des probabilités de régime du HMM selon
settings.ALLOCATION_MODE :

- "rebond" (stratégie retenue) : on joue le retour à la moyenne. Le HMM confirme un régime
  avec retard : quand il annonce "baissier", la chute a souvent déjà eu lieu et le marché
  tend à rebondir. P(baissier) va donc au panier OFFENSIF (bêta élevé, qui rebondit le plus),
  P(haussier) au panier DÉFENSIF (on sécurise avant l'essoufflement), P(neutre) au neutre.
- "suiveur" : on suit le régime. P(haussier) -> offensif, P(baissier) -> défensif.
- "equipondere" : 1/3 par panier, sans utiliser le HMM (référence de comparaison).

Garde-fous (calibrés sur la période d'entraînement, cf. docs/04) :
- ALLOCATION_LISSAGE_JOURS : probabilités moyennées sur les N derniers jours de bourse
  (causal), pour éviter les allers-retours coûteux d'un mois sur l'autre ;
- ALLOCATION_PLAFOND_OFFENSIF : poids maximal du panier offensif ; l'excédent va au neutre.

Chaque panier a sa propre continuité (anti-churn) indépendamment des autres.
"""

import pandas as pd
from django.conf import settings

from .allocation import appliquer_anti_churn, trier_candidats

REGIMES = ["haussier", "neutre", "baissier"]
MODES = ("rebond", "suiveur", "equipondere")
NOMS_MODES = {
    "rebond": "Stratégie de rebond (HMM)",
    "suiveur": "HMM suiveur",
    "equipondere": "1/3 par panier (sans HMM)",
}
NOMS_PANIERS = {"offensif": "offensif (bêta élevé)", "neutre": "neutre", "defensif": "défensif (bêta faible)"}
# Panier -> clé de tri utilisée par allocation.trier_candidats
PANIERS = {"offensif": "haussier", "neutre": "neutre", "defensif": "baissier"}
# Régime -> panier privilégié, selon le mode
PANIER_PAR_REGIME = {
    "rebond": {"haussier": "defensif", "neutre": "neutre", "baissier": "offensif"},
    "suiveur": {"haussier": "offensif", "neutre": "neutre", "baissier": "defensif"},
}


def poids_des_paniers(probabilites: dict, mode: str, plafond_offensif: float = 1.0) -> dict:
    """Poids (somme = 1) des paniers offensif / neutre / défensif pour des probabilités de régime."""
    if mode not in MODES:
        raise ValueError(f"ALLOCATION_MODE inconnu : {mode} (attendu : {', '.join(MODES)})")
    if mode == "equipondere":
        poids = {panier: 1 / 3 for panier in PANIERS}
    else:
        poids = {panier: 0.0 for panier in PANIERS}
        for regime, panier in PANIER_PAR_REGIME[mode].items():
            poids[panier] += float(probabilites[regime])
    if poids["offensif"] > plafond_offensif:
        poids["neutre"] += poids["offensif"] - plafond_offensif
        poids["offensif"] = plafond_offensif
    return poids


def construire_allocations(
    betas: pd.DataFrame,
    regimes_journaliers: pd.DataFrame,
    colonne_beta: str | None = None,
    mode: str | None = None,
    lissage_jours: int | None = None,
    plafond_offensif: float | None = None,
) -> pd.DataFrame:
    """Construit l'historique des allocations (date, ticker, poids, regime dominant).

    betas : colonnes ticker, date, beta_brut, beta_ajuste, momentum_63j (dates de rééquilibrage).
    regimes_journaliers : colonnes date, regime, proba_haussier, proba_neutre, proba_baissier (quotidien).
    Les paramètres None reprennent les valeurs de settings (UTILISER_BLUME, ALLOCATION_*).
    """
    if colonne_beta is None:
        colonne_beta = "beta_ajuste" if settings.UTILISER_BLUME else "beta_brut"
    mode = mode or settings.ALLOCATION_MODE
    lissage_jours = lissage_jours or settings.ALLOCATION_LISSAGE_JOURS
    plafond_offensif = settings.ALLOCATION_PLAFOND_OFFENSIF if plafond_offensif is None else plafond_offensif

    regimes_tries = regimes_journaliers.sort_values("date").reset_index(drop=True)
    colonnes_probas = [f"proba_{r}" for r in REGIMES]
    # Moyenne glissante causale des probabilités (jours <= date uniquement)
    probas_lissees = regimes_tries[colonnes_probas].rolling(lissage_jours, min_periods=1).mean()
    dates_regimes = pd.to_datetime(regimes_tries["date"])

    paniers_precedents = {panier: None for panier in PANIERS}
    lignes = []

    for date, groupe in betas.groupby("date"):
        candidats = groupe.set_index("ticker")[[colonne_beta, "momentum_63j"]].rename(
            columns={colonne_beta: "beta", "momentum_63j": "momentum"}
        )

        position = dates_regimes.searchsorted(pd.Timestamp(date), side="right") - 1
        if position < 0:
            continue
        probabilites = {r: probas_lissees.at[position, f"proba_{r}"] for r in REGIMES}
        regime_dominant = max(probabilites, key=probabilites.get)
        poids_paniers = poids_des_paniers(probabilites, mode, plafond_offensif)

        poids_par_ticker: dict[str, float] = {}
        for panier, cle_tri in PANIERS.items():
            candidats_tries = trier_candidats(candidats, cle_tri)
            # Le sous-panier ne bascule jamais "en dur" : on ne compare qu'à sa propre
            # composition passée (buffer top15 toujours actif, jamais de reset top10 strict).
            composition = appliquer_anti_churn(candidats_tries, paniers_precedents[panier], "membre", "membre")
            paniers_precedents[panier] = composition

            if not composition or poids_paniers[panier] <= 0:
                continue
            poids_intra_panier = poids_paniers[panier] / len(composition)
            for ticker in composition:
                poids_par_ticker[ticker] = poids_par_ticker.get(ticker, 0.0) + poids_intra_panier

        for ticker, poids in poids_par_ticker.items():
            lignes.append({"date": date, "ticker": ticker, "poids": poids, "regime": regime_dominant})

    return pd.DataFrame(lignes)


def calculer_turnover(allocations: pd.DataFrame) -> float:
    """Turnover total = somme des variations absolues de poids d'une période à l'autre."""
    if allocations.empty:
        return 0.0
    pivot = allocations.pivot(index="date", columns="ticker", values="poids").fillna(0.0).sort_index()
    return pivot.diff().abs().sum().sum()
