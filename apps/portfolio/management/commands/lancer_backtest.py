"""Lance le backtest complet sur la période de test et calcule les métriques de performance.

Usage : python manage.py lancer_backtest
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.market_data.services import duckdb_store
from apps.portfolio.models import ExecutionBacktest
import pandas as pd

from apps.portfolio.services import (
    allocation_probabiliste,
    backtest_engine,
    beta_store,
    metriques,
    transactions_store,
    valeur_store,
)
from apps.regimes.services import regimes_store


class Command(BaseCommand):
    help = "Simule le portefeuille jour par jour sur la période de test et calcule les métriques."

    def handle(self, *args, **options):
        con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)

        self.stdout.write("Simulation du backtest (rééquilibrage hebdomadaire, coûts de transaction)...")
        self._verifier_allocations_a_jour(con)
        valeurs, transactions = backtest_engine.simuler_backtest(con)

        taux_sans_risque = con.execute(
            "SELECT AVG(taux) FROM taux_sans_risque WHERE date BETWEEN ? AND ?",
            [str(valeurs.index.min()), str(valeurs.index.max())],
        ).fetchone()[0]

        nb_lignes_valeurs = valeur_store.enregistrer_valeurs(con, valeurs)
        nb_lignes_transactions = transactions_store.enregistrer_transactions(con, transactions)
        comparaisons = self._simuler_comparaisons(con, valeurs, taux_sans_risque)
        valeur_store.enregistrer_comparaisons(con, comparaisons)
        con.close()

        metriques_portefeuille = metriques.calculer_toutes_les_metriques(
            valeurs["valeur_portefeuille"], taux_sans_risque
        )
        metriques_benchmark = metriques.calculer_toutes_les_metriques(
            valeurs["valeur_benchmark"], taux_sans_risque
        )
        alpha_annualise, beta_portefeuille = metriques.alpha_beta_vs_benchmark(
            metriques.rendements_quotidiens(valeurs["valeur_portefeuille"]),
            metriques.rendements_quotidiens(valeurs["valeur_benchmark"]),
        )
        cout_transactions_total = transactions["cout"].sum() if not transactions.empty else 0.0

        ExecutionBacktest.objects.create(
            date_debut_test=valeurs.index.min(),
            date_fin_test=valeurs.index.max(),
            capital_initial=settings.CAPITAL_INITIAL,
            capital_final_portefeuille=valeurs["valeur_portefeuille"].iloc[-1],
            rendement_annualise_portefeuille=metriques_portefeuille["rendement_annualise"],
            volatilite_portefeuille=metriques_portefeuille["volatilite_annualisee"],
            sharpe_portefeuille=metriques_portefeuille["sharpe"],
            sortino_portefeuille=metriques_portefeuille["sortino"],
            calmar_portefeuille=metriques_portefeuille["calmar"],
            max_drawdown_portefeuille=metriques_portefeuille["max_drawdown"],
            var_95_portefeuille=metriques_portefeuille["var_95"],
            capital_final_benchmark=valeurs["valeur_benchmark"].iloc[-1],
            rendement_annualise_benchmark=metriques_benchmark["rendement_annualise"],
            volatilite_benchmark=metriques_benchmark["volatilite_annualisee"],
            sharpe_benchmark=metriques_benchmark["sharpe"],
            max_drawdown_benchmark=metriques_benchmark["max_drawdown"],
            alpha_annualise=alpha_annualise,
            beta_portefeuille=beta_portefeuille,
            taux_sans_risque_moyen=taux_sans_risque,
            cout_transactions_total=cout_transactions_total,
        )

        self.stdout.write(self.style.SUCCESS(f"{nb_lignes_valeurs} jours simulés, {nb_lignes_transactions} transactions."))
        self._afficher_rapport(metriques_portefeuille, metriques_benchmark, valeurs, alpha_annualise, beta_portefeuille, cout_transactions_total)

    def _afficher_rapport(self, m_portefeuille, m_benchmark, valeurs, alpha, beta, cout_total):
        self.stdout.write(self.style.SUCCESS("\n=== Stratégie HMM ==="))
        self.stdout.write(f"  Capital final          : {valeurs['valeur_portefeuille'].iloc[-1]:,.0f} €")
        self.stdout.write(f"  Rendement annualisé     : {m_portefeuille['rendement_annualise']:.2%}")
        self.stdout.write(f"  Volatilité annualisée   : {m_portefeuille['volatilite_annualisee']:.2%}")
        self.stdout.write(f"  Sharpe / Sortino / Calmar : {m_portefeuille['sharpe']:.2f} / {m_portefeuille['sortino']:.2f} / {m_portefeuille['calmar']:.2f}")
        self.stdout.write(f"  Max Drawdown            : {m_portefeuille['max_drawdown']:.2%}")
        self.stdout.write(f"  VaR 95%                 : {m_portefeuille['var_95']:.2%}")
        self.stdout.write(f"  Coûts de transaction totaux : {cout_total:,.0f} €")

        self.stdout.write(self.style.SUCCESS("\n=== CAC40 (buy & hold) ==="))
        self.stdout.write(f"  Capital final          : {valeurs['valeur_benchmark'].iloc[-1]:,.0f} €")
        self.stdout.write(f"  Rendement annualisé     : {m_benchmark['rendement_annualise']:.2%}")
        self.stdout.write(f"  Volatilité annualisée   : {m_benchmark['volatilite_annualisee']:.2%}")
        self.stdout.write(f"  Sharpe                  : {m_benchmark['sharpe']:.2f}")
        self.stdout.write(f"  Max Drawdown            : {m_benchmark['max_drawdown']:.2%}")

        self.stdout.write(self.style.SUCCESS("\n=== Comparaison ==="))
        self.stdout.write(f"  Alpha annualisé vs CAC40 : {alpha:.2%}")
        self.stdout.write(f"  Bêta du portefeuille     : {beta:.2f}")


    def _simuler_comparaisons(self, con, valeurs, taux_sans_risque) -> pd.DataFrame:
        """Rejoue les autres modes d'allocation sur les mêmes dates (mêmes paniers, mêmes
        garde-fous) pour comparer la stratégie retenue. Rien n'est persisté hormis les valeurs."""
        betas = beta_store.lire_betas(con)
        regimes = regimes_store.lire_regimes(con)
        dates_test = set(pd.to_datetime(regimes.loc[regimes["ensemble"] == "test", "date"]))
        lignes = []
        self.stdout.write(self.style.SUCCESS("\n=== Comparaison des modes d'allocation (même période) ==="))
        for mode in allocation_probabiliste.MODES:
            if mode == settings.ALLOCATION_MODE:
                serie = valeurs["valeur_portefeuille"]
            else:
                allocations = allocation_probabiliste.construire_allocations(betas, regimes, mode=mode)
                allocations = allocations[pd.to_datetime(allocations["date"]).isin(dates_test)]
                serie = backtest_engine.simuler_backtest(con, allocations)[0]["valeur_portefeuille"]
            m = metriques.calculer_toutes_les_metriques(serie, taux_sans_risque)
            marqueur = "  <- retenu" if mode == settings.ALLOCATION_MODE else ""
            self.stdout.write(
                f"  {allocation_probabiliste.NOMS_MODES[mode]:28s} rdt {m['rendement_annualise']:6.2%}  "
                f"Sharpe {m['sharpe']:5.2f}  MDD {m['max_drawdown']:7.2%}{marqueur}"
            )
            lignes.append(pd.DataFrame({"date": serie.index, "strategie": mode, "valeur": serie.to_numpy()}))
        return pd.concat(lignes, ignore_index=True)


    def _verifier_allocations_a_jour(self, con) -> None:
        """Avertit si les allocations enregistrées ne correspondent plus aux réglages actuels
        (ex. ALLOCATION_MODE modifié sans relancer calculer_allocations)."""
        enregistrees = backtest_engine.charger_allocations_test(con)
        if enregistrees.empty:
            return
        attendues = allocation_probabiliste.construire_allocations(
            beta_store.lire_betas(con), regimes_store.lire_regimes(con)
        )
        cle = ["date", "ticker"]
        for tableau in (enregistrees, attendues):
            tableau["date"] = pd.to_datetime(tableau["date"])
        comparaison = enregistrees[cle + ["poids"]].merge(
            attendues[cle + ["poids"]], on=cle, how="left", suffixes=("", "_attendu")
        )
        ecart = (comparaison["poids"] - comparaison["poids_attendu"].fillna(0)).abs().max()
        if ecart > 1e-6:
            self.stdout.write(self.style.WARNING(
                "ATTENTION : les allocations enregistrées ne correspondent pas aux réglages actuels "
                f"(ALLOCATION_MODE = '{settings.ALLOCATION_MODE}'). Lancez d'abord : python manage.py calculer_allocations"
            ))
