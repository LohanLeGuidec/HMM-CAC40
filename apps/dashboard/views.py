"""Vues du dashboard : lecture des résultats (DuckDB + SQLite) et rendu des templates."""

import json

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import redirect, render

from apps.dashboard.evenements import EVENEMENTS_MARCHE
from apps.market_data.services import duckdb_store
from apps.portfolio.models import ExecutionAllocation, ExecutionBacktest, ExecutionCalculBeta
from apps.portfolio.services import allocation_probabiliste, allocations_store, beta_store, metriques, valeur_store
from apps.portfolio.services.allocation import seuils_beta
from apps.regimes.models import EntrainementHMM
from apps.regimes.services import regimes_store


def _classer_beta(beta: float, seuils: tuple) -> str:
    """Classe un bêta avec les seuils utilisés par l'allocation (fixes ou quantiles du jour)."""
    seuil_defensif, seuil_neutre_bas, seuil_neutre_haut, seuil_offensif = seuils
    if beta < seuil_defensif:
        return "défensif"
    if seuil_neutre_bas <= beta <= seuil_neutre_haut:
        return "neutre"
    if beta > seuil_offensif:
        return "offensif"
    return "zone grise"


def accueil(request):
    dernier_backtest = ExecutionBacktest.objects.first()
    dernier_calcul_beta = ExecutionCalculBeta.objects.first()
    derniere_allocation = ExecutionAllocation.objects.first()
    dernier_entrainement_hmm = EntrainementHMM.objects.order_by("-date_execution").first()
    contexte = {
        "backtest": dernier_backtest,
        "nom_mode": allocation_probabiliste.NOMS_MODES.get(settings.ALLOCATION_MODE, settings.ALLOCATION_MODE),
        "calcul_beta": dernier_calcul_beta,
        "allocation": derniere_allocation,
        "entrainement_hmm": dernier_entrainement_hmm,
    }
    return render(request, "dashboard/accueil.html", contexte)


# Couleurs des courbes de la page Performance (stratégie retenue en vert, CAC40 en gris)
COULEURS_STRATEGIES = {"rebond": "#34d399", "suiveur": "#f59e0b", "equipondere": "#60a5fa"}


def performance(request):
    con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)
    valeurs = valeur_store.lire_valeurs(con)
    comparaisons = valeur_store.lire_comparaisons(con)
    con.close()

    backtest = ExecutionBacktest.objects.first()
    contexte = {
        "backtest": backtest,
        "a_des_donnees": not valeurs.empty,
        "nom_mode": allocation_probabiliste.NOMS_MODES.get(settings.ALLOCATION_MODE, settings.ALLOCATION_MODE),
    }
    if valeurs.empty:
        return render(request, "dashboard/performance.html", contexte)

    valeurs["date"] = pd.to_datetime(valeurs["date"])
    dates = valeurs["date"]
    taux = backtest.taux_sans_risque_moyen if backtest else 0.0
    courbes = {settings.ALLOCATION_MODE: valeurs.set_index("date")["valeur_portefeuille"]}
    if not comparaisons.empty:
        comparaisons["date"] = pd.to_datetime(comparaisons["date"])
        for mode, groupe in comparaisons.groupby("strategie"):
            courbes.setdefault(mode, groupe.set_index("date")["valeur"])

    strategies = []
    for mode in [settings.ALLOCATION_MODE] + [m for m in allocation_probabiliste.MODES if m != settings.ALLOCATION_MODE]:
        if mode not in courbes:
            continue
        serie = courbes[mode].reindex(dates).ffill()
        strategies.append({
            "nom": allocation_probabiliste.NOMS_MODES[mode], "serie": serie, "couleur": COULEURS_STRATEGIES.get(mode, "#e2e8f0"),
            "retenu": mode == settings.ALLOCATION_MODE, "pointille": False,
        })
    strategies.append({
        "nom": "CAC40 (achat-conservation)", "serie": valeurs.set_index("date")["valeur_benchmark"],
        "couleur": "#94a3b8", "retenu": False, "pointille": True,
    })
    for s in strategies:
        m = metriques.calculer_toutes_les_metriques(s["serie"], taux)
        s.update({
            "capital": float(s["serie"].iloc[-1]), "rendement": m["rendement_annualise"],
            "volatilite": m["volatilite_annualisee"], "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"],
        })

    contexte.update({
        "labels_json": json.dumps(dates.dt.strftime("%Y-%m-%d").tolist()),
        "series_json": json.dumps([
            {"nom": s["nom"], "valeurs": s["serie"].round(0).tolist(), "couleur": s["couleur"],
             "retenu": s["retenu"], "pointille": s["pointille"]}
            for s in strategies
        ]),
        "strategies": [{k: v for k, v in s.items() if k != "serie"} for s in strategies],
    })
    return render(request, "dashboard/performance.html", contexte)


def regimes(request):
    con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)
    regimes_df = regimes_store.lire_regimes(con)

    if regimes_df.empty:
        try:
            call_command("import_donnees_marche")
            call_command("entrainer_hmm")
        except Exception:
            con.close()
            return render(request, "dashboard/regimes.html", {"a_des_donnees": False})

        con.close()
        con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)
        regimes_df = regimes_store.lire_regimes(con)

    prix_benchmark = con.execute(
        "SELECT date, adj_close FROM prix_ohlcv WHERE ticker = ? ORDER BY date", [settings.TICKER_BENCHMARK]
    ).fetchdf()
    con.close()

    contexte = {"a_des_donnees": not regimes_df.empty}
    if regimes_df.empty:
        return render(request, "dashboard/regimes.html", contexte)

    # Dates normalisées des deux côtés (DuckDB renvoie des datetime64).
    prix_benchmark["date"] = pd.to_datetime(prix_benchmark["date"]).dt.normalize()
    regimes_df["date"] = pd.to_datetime(regimes_df["date"]).dt.normalize()
    colonnes_probas = [c for c in ("proba_haussier", "proba_neutre", "proba_baissier") if c in regimes_df.columns]
    fusion = prix_benchmark.merge(regimes_df[["date", "regime", "ensemble", *colonnes_probas]], on="date", how="inner")
    fusion = fusion.dropna(subset=["adj_close"])
    regime_labels = fusion["regime"].astype(str).tolist()

    prix_cac40 = fusion["adj_close"].round(2).tolist()
    couleurs_regimes = []
    for regime in fusion["regime"].astype(str):
        if regime == "haussier":
            couleurs_regimes.append("#34d399")
        elif regime == "neutre":
            couleurs_regimes.append("#fbbf24")
        else:
            couleurs_regimes.append("#f87171")

    train_end_date = regimes_df[regimes_df["ensemble"] == "train"]["date"].max()
    contexte.update(
        {
            "labels_json": json.dumps(fusion["date"].dt.strftime("%Y-%m-%d").tolist()),
            "regime_labels_json": json.dumps(regime_labels),
            # Probabilités filtrées du HMM (confiance du modèle), arrondies pour alléger la page
            "probas_json": json.dumps(
                {c.replace("proba_", ""): fusion[c].round(3).fillna(0).tolist() for c in colonnes_probas}
            ),
            "prix_json": json.dumps(prix_cac40),
            "regime_colors_json": json.dumps(couleurs_regimes),
            # str(Timestamp) donnait "2023-09-13 00:00:00" -> jamais trouvé dans les labels.
            "train_end_date": json.dumps(train_end_date.strftime("%Y-%m-%d")) if pd.notna(train_end_date) else "null",
            "evenements_json": json.dumps(EVENEMENTS_MARCHE, ensure_ascii=False),
            "allocation_json": json.dumps({
                "mode": settings.ALLOCATION_MODE,
                "nom": allocation_probabiliste.NOMS_MODES.get(settings.ALLOCATION_MODE, settings.ALLOCATION_MODE),
                "panier_par_regime": {
                    regime: allocation_probabiliste.NOMS_PANIERS[panier]
                    for regime, panier in allocation_probabiliste.PANIER_PAR_REGIME.get(settings.ALLOCATION_MODE, {}).items()
                },
            }, ensure_ascii=False),
        }
    )
    return render(request, "dashboard/regimes.html", contexte)


def betas(request):
    con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)
    betas_df = beta_store.lire_betas(con)
    con.close()

    contexte = {"a_des_donnees": not betas_df.empty}
    if betas_df.empty:
        return render(request, "dashboard/betas.html", contexte)

    derniere_date = betas_df["date"].max()
    derniers = betas_df[betas_df["date"] == derniere_date].sort_values("beta_ajuste", ascending=False)

    seuils = seuils_beta(derniers["beta_ajuste"])
    univers = pd.read_csv(settings.UNIVERS_CAC40_CSV).set_index("ticker")
    lignes = []
    for _, ligne in derniers.iterrows():
        info = univers.loc[ligne["ticker"]] if ligne["ticker"] in univers.index else None
        lignes.append(
            {
                "ticker": ligne["ticker"],
                "nom": info["nom"] if info is not None else ligne["ticker"],
                "secteur": info["secteur"] if info is not None else "",
                "beta_brut": round(ligne["beta_brut"], 3),
                "beta_ajuste": round(ligne["beta_ajuste"], 3),
                "momentum_63j": round(ligne["momentum_63j"], 4),
                "classe": _classer_beta(ligne["beta_ajuste"], seuils),
            }
        )

    contexte.update({"date_reference": derniere_date, "lignes": lignes})
    return render(request, "dashboard/betas.html", contexte)


def allocations(request):
    con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)
    allocations_df = allocations_store.lire_allocations(con)
    con.close()

    contexte = {"a_des_donnees": not allocations_df.empty}
    if allocations_df.empty:
        return render(request, "dashboard/allocations.html", contexte)

    dates_disponibles = sorted(allocations_df["date"].unique(), reverse=True)
    date_choisie = request.GET.get("date")
    date_reference = pd.Timestamp(date_choisie) if date_choisie else dates_disponibles[0]

    lignes = (
        allocations_df[allocations_df["date"] == date_reference]
        .sort_values("poids", ascending=False)
        .to_dict("records")
    )

    contexte.update(
        {
            "date_reference": date_reference,
            "dates_disponibles": dates_disponibles,
            "lignes": lignes,
        }
    )
    return render(request, "dashboard/allocations.html", contexte)


def relancer_backtest(request):
    if request.method == "POST":
        try:
            # Les allocations sont recalculées d'abord : elles dépendent des réglages
            # (ALLOCATION_MODE, seuils de bêta...) qui ont pu changer depuis le dernier calcul.
            call_command("calculer_allocations")
            call_command("lancer_backtest")
            messages.success(request, "Allocations recalculées et backtest relancé avec succès.")
        except Exception as erreur:
            messages.error(request, f"Échec du backtest : {erreur}")
    return redirect("dashboard:accueil")
