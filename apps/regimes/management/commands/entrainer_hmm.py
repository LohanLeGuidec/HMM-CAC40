"""Commande d'entraînement du HMM et de détection des régimes de marché (walk-forward).

Usage : python manage.py entrainer_hmm
"""

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.market_data.services import duckdb_store
from apps.regimes.models import EntrainementHMM
from apps.regimes.services import features, hmm_model, regimes_store


class Command(BaseCommand):
    help = "Entraîne le HMM (train initial + walk-forward sur le test) et enregistre les régimes détectés."

    def handle(self, *args, **options):
        con = duckdb_store.obtenir_connexion(settings.DUCKDB_PATH)

        observations = features.construire_observations(con)
        if observations.empty:
            self.stderr.write("Aucune observation disponible : lancez d'abord import_donnees_marche.")
            return

        dates = observations.index
        valeurs = observations.to_numpy()
        n = len(valeurs)
        indice_split = int(n * settings.SPLIT_TRAIN_RATIO)

        # La standardisation est ajustée UNE SEULE FOIS sur le train, jamais recalculée (cf. docs/03).
        standardiseur = hmm_model.Standardiseur().ajuster(valeurs[:indice_split])
        valeurs_standardisees = standardiseur.transformer(valeurs)

        EntrainementHMM.objects.all().delete()
        morceaux_resultats = []

        # 1. Entraînement initial sur la période train (70 %)
        self.stdout.write(f"Entraînement initial sur {indice_split} observations (train)...")
        modele = hmm_model.entrainer_modele(valeurs_standardisees[:indice_split], settings.HMM_NB_ETATS)
        mapping = hmm_model.etiqueter_etats(modele)
        # Décodage causal (filtre forward) : le régime du jour t n'utilise que les données <= t.
        labels, probas, log_vraisemblance = hmm_model.decoder_regimes(
            modele, valeurs_standardisees[:indice_split], mapping
        )
        labels = hmm_model.lisser_persistance(labels, settings.HMM_PERSISTANCE_MIN_JOURS)
        morceaux_resultats.append(
            self._construire_dataframe_resultats(
                dates[:indice_split], labels, probas, "train", dates[indice_split - 1]
            )
        )
        EntrainementHMM.objects.create(
            type_entrainement="initial",
            date_debut_fenetre=dates[0].date(),
            date_fin_fenetre=dates[indice_split - 1].date(),
            nb_observations=indice_split,
            log_vraisemblance=log_vraisemblance,
            date_application_debut=dates[0].date(),
            date_application_fin=dates[indice_split - 1].date(),
        )

        # 2. Walk-forward sur la période test : ré-entraînement périodique (fenêtre expansive)
        modele_precedent, mapping_precedent = modele, mapping
        frequence = settings.HMM_FREQUENCE_REENTRAINEMENT_JOURS
        for debut_morceau in range(indice_split, n, frequence):
            fin_morceau = min(debut_morceau + frequence, n)
            self.stdout.write(
                f"Ré-entraînement walk-forward sur {debut_morceau} observations, "
                f"application du {dates[debut_morceau].date()} au {dates[fin_morceau - 1].date()}..."
            )
            modele = hmm_model.entrainer_modele(valeurs_standardisees[:debut_morceau], settings.HMM_NB_ETATS)
            # Les états du nouveau modèle héritent des labels des états les plus proches du
            # modèle précédent : "haussier" garde le même sens d'un ré-entraînement à l'autre.
            mapping = hmm_model.aligner_sur_modele_precedent(modele, modele_precedent, mapping_precedent)
            modele_precedent, mapping_precedent = modele, mapping
            # Filtre forward sur tout l'historique disponible jusqu'à la fin de la tranche :
            # causal, donc le label du jour t ne dépend que des observations <= t (aucune
            # donnée de la suite de la tranche n'est utilisée, contrairement à Viterbi).
            labels_complets, probas_completes, log_vraisemblance = hmm_model.decoder_regimes(
                modele, valeurs_standardisees[:fin_morceau], mapping
            )
            labels_complets = hmm_model.lisser_persistance(labels_complets, settings.HMM_PERSISTANCE_MIN_JOURS)
            labels = labels_complets[debut_morceau:fin_morceau]
            probas = {cle: valeurs[debut_morceau:fin_morceau] for cle, valeurs in probas_completes.items()}
            morceaux_resultats.append(
                self._construire_dataframe_resultats(
                    dates[debut_morceau:fin_morceau], labels, probas, "test", dates[debut_morceau - 1]
                )
            )
            EntrainementHMM.objects.create(
                type_entrainement="walk_forward",
                date_debut_fenetre=dates[0].date(),
                date_fin_fenetre=dates[debut_morceau - 1].date(),
                nb_observations=debut_morceau,
                log_vraisemblance=log_vraisemblance,
                date_application_debut=dates[debut_morceau].date(),
                date_application_fin=dates[fin_morceau - 1].date(),
            )

        resultats_complets = pd.concat(morceaux_resultats)
        nb_lignes = regimes_store.enregistrer_regimes(con, resultats_complets)
        con.close()

        self.stdout.write(self.style.SUCCESS(f"{nb_lignes} jours de régimes enregistrés dans regimes_marche."))
        self._afficher_repartition(resultats_complets)

    def _construire_dataframe_resultats(self, dates_periode, labels, probas, ensemble, date_fin_entrainement):
        return pd.DataFrame(
            {
                "date": dates_periode,
                "regime": labels,
                "proba_haussier": probas["haussier"],
                "proba_neutre": probas["neutre"],
                "proba_baissier": probas["baissier"],
                "ensemble": ensemble,
                "date_fin_entrainement": date_fin_entrainement.date(),
            }
        ).set_index("date")

    def _afficher_repartition(self, resultats: pd.DataFrame) -> None:
        repartition = resultats.groupby(["ensemble", "regime"]).size()
        self.stdout.write("Répartition des régimes détectés :")
        self.stdout.write(str(repartition))
