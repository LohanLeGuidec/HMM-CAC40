"""Chocs de marché majeurs affichés sur le graphique des régimes (page /regimes/).

Chaque événement est daté du jour du choc (ou de l'annonce) ; le graphique le place sur le
premier jour de bourse suivant. Seuls les événements couverts par les données sont affichés.
Pour en ajouter un, il suffit d'ajouter une ligne à la liste.

Catégories : "financier", "geopolitique", "sanitaire", "politique".
"""

EVENEMENTS_MARCHE = [
    {"date": "2000-03-10", "nom": "Éclatement de la bulle internet", "categorie": "financier",
     "description": "Pic du Nasdaq ; début d'un marché baissier de 3 ans (CAC40 -65 % jusqu'en mars 2003)."},
    {"date": "2001-09-11", "nom": "Attentats du 11 septembre", "categorie": "geopolitique",
     "description": "Fermeture de Wall Street 4 jours ; forte chute des marchés européens."},
    {"date": "2003-03-20", "nom": "Invasion de l'Irak", "categorie": "geopolitique",
     "description": "Début de la guerre en Irak ; point bas du marché baissier post-bulle."},
    {"date": "2007-08-09", "nom": "Début de la crise des subprimes", "categorie": "financier",
     "description": "BNP Paribas gèle trois fonds exposés aux crédits immobiliers américains."},
    {"date": "2008-09-15", "nom": "Faillite de Lehman Brothers", "categorie": "financier",
     "description": "Paroxysme de la crise financière mondiale."},
    {"date": "2010-05-03", "nom": "Crise grecque : 1er plan d'aide", "categorie": "financier",
     "description": "Début de la crise des dettes souveraines en zone euro."},
    {"date": "2011-08-05", "nom": "Crise de la dette euro / note US dégradée", "categorie": "financier",
     "description": "S&P retire le AAA des États-Unis ; contagion à l'Italie et l'Espagne."},
    {"date": "2015-08-24", "nom": "Krach chinois", "categorie": "financier",
     "description": "« Lundi noir » après la dévaluation du yuan."},
    {"date": "2016-06-24", "nom": "Brexit", "categorie": "politique",
     "description": "Victoire du « Leave » au référendum britannique."},
    {"date": "2018-10-10", "nom": "Correction fin 2018", "categorie": "financier",
     "description": "Hausse des taux de la Fed et guerre commerciale États-Unis - Chine."},
    {"date": "2020-02-24", "nom": "Krach du COVID-19", "categorie": "sanitaire",
     "description": "Propagation en Italie ; CAC40 -38 % en un mois, confinements."},
    {"date": "2022-02-24", "nom": "Invasion de l'Ukraine", "categorie": "geopolitique",
     "description": "La Russie envahit l'Ukraine ; choc énergétique et inflation."},
    {"date": "2023-03-10", "nom": "Faillite de Silicon Valley Bank", "categorie": "financier",
     "description": "Crise bancaire régionale américaine, puis sauvetage de Credit Suisse."},
    {"date": "2023-10-09", "nom": "Guerre Israël - Hamas", "categorie": "geopolitique",
     "description": "Attaque du Hamas du 7 octobre et début de la guerre à Gaza."},
    {"date": "2024-06-10", "nom": "Dissolution de l'Assemblée nationale", "categorie": "politique",
     "description": "Annoncée le 9 juin au soir ; hausse du spread France - Allemagne."},
    {"date": "2024-08-05", "nom": "Krach du yen (carry trade)", "categorie": "financier",
     "description": "Hausse des taux japonais ; débouclage du carry trade, VIX > 60 en séance."},
    {"date": "2025-04-02", "nom": "Droits de douane américains", "categorie": "geopolitique",
     "description": "« Liberation Day » : droits de douane généralisés annoncés par Donald Trump."},
    {"date": "2025-06-13", "nom": "Guerre Israël - Iran", "categorie": "geopolitique",
     "description": "Frappes israéliennes sur l'Iran, puis frappes américaines le 22 juin (« guerre des 12 jours »)."},
    {"date": "2026-02-28", "nom": "Guerre États-Unis / Israël - Iran", "categorie": "geopolitique",
     "description": "Frappes sur l'Iran puis blocage du détroit d'Ormuz ; CAC40 -8,9 % en mars 2026."},
]
