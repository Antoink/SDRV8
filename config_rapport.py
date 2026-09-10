import pandas as pd
import re
import unicodedata

SDR_RED = "#D71920"

# ==========================================
# 1. MAPPING DES COLONNES (UI -> EXCEL)
# ==========================================
COL_MAPPING = {
    # --- INFO JOUEUR & ANTHROPO ---
    "Joueur": "Joueur", "Equipe": "Equipe", "Age": "Age", 
    "Poids": "Poids (kg)", "Taille": "Taille (cm)", "Masse Grasse": "Masse grasse",
    "Poste": "Poste", "Position": "Position",
    
    # --- TESTS PHYSIQUES ---
    "Knee To Wall (G)": "Knee to wall G", "Knee To Wall (D)": "Knee to wall D",
    "Sit And Reach": "Sit and reach",
    "Somme ADD": "Somme ADD", "Adducteurs (G)": "Adducteur G", "Adducteurs (D)": "Adducteur D",
    "Ratio Squeeze": "Ratio Squeeze (ADD/ABD)",
    "Somme ABD": "Somme ABD", "Abducteurs (G)": "Abducteur G", "Abducteurs (D)": "Abducteur D",
    "Nordic Ischio (G)": "Nordic G", "Nordic Ischio (D)": "Nordic D",
    "Inverseur (G)": "Inverseur G", "Inverseur (D)": "Inverseur D",
    "Everseur (G)": "Everseur G", "Everseur (D)": "Everseur D",
    "Endurance Heel Raise (G)": "Endurance Heel Raise G", "Endurance Heel Raise (D)": "Endurance Heel Raise D",
    
    
    
    # --- SAUTS & EXPLOSIVITE ---
    "CMJ 2JB": "CMJ 2JB", 
    "Peak Force CMJ": "Peak Force CMJ", 
    "RFD CMJ": "RFD CMJ", 
    "RSI CMJ": "RSI", 
    "Squat belt (N)": "Squat belt (N)",
    "Wattbike (6s)": "Wattbike 6s (W)",
    
    # --- COURSE & METABOLIQUE ---
    "SV1": "SV1", "SV2": "SV2", "FC": "FC", "VMA": "VMA",
    "Distance Totale": "Distance totale", "Distance HSR": "Distance HSR", "Distance Sprint (92% Vimax)": "Distance Sprint (92% Vimax)",
    "Vmax": "Vmax", "Amax": "Amax", "Dmax": "Dmax",
    "Temps sur 10m": "Temps sur 10m", "Test 1km (s)": "Test 1km (s)",
    
    # --- ISOCINETISME ---
    "Q Conc 60° (G)": "Q G conc 60°/s", "Q Conc 60° (D)": "Q Dt conc 60°/s",
    "Q Conc 240° (G)": "Q G conc 240°/s", "Q Conc 240° (D)": "Q Dt conc 240°/s",
    "IJ Conc 60° (G)": "IJ G conc 60°/s", "IJ Conc 60° (D)": "IJ Dt conc 60°/s",
    "IJ Conc 240° (G)": "IJ G conc 240°/s", "IJ Conc 240° (D)": "IJ Dt conc 240°/s",
    "IJ Exc 30° (G)": "IJ G Exc 30°/s", "IJ Exc 30° (D)": "IJ Dt exc 30°/s", 
    # --- ISAK NUTRITION ---
    "Triceps": "Isak_triceps", "Subscapulaire": "Isak_sousscapulaire", "Biceps": "Isak_biceps",
    "Crête iliaque": "Isak_crete", "Supraspinale": "Isak_supraspinale", "Abdominal": "Isak_abdominal", 
    "Cuisse ISAK": "Isak_cuisse", "Jambe ISAK": "Isak_jambe", "Somme 8 plis": "Somme de 8 plis (mm)",
    "Endomorphie": "Endomorphie", "Mésomorphie": "Mésomorphie", "Éctomorphie": "Éctomorphie",
    "Tissu Adipeux": "Tissu Adipeux (%)", "Tissu Musculaire": "Tissu Musculaire (%)",
    "Tissu Osseux": "Tissu Osseux (%)", "Tissu Résiduel": "Tissu Résiduel (%)",

    # --- 1080 SPRINT ---
    "Temps total 1080": "Temps total 1080 (s)", "Amax 1080": "Amax 1080 (m/s²)",
    "Pmax 1080": "Pmax 1080 (W)", "Vmax 15m 1080": "Vmax 15m 1080 (m/s)",
    "Tau 1080": "Tau 1080 (s)", "T90 1080": "T90 1080 (s)", "D90 1080": "D90 1080 (m)",
    "Momentum 1080": "Momentum 1080 (Kg*m/s)", "F0 1080": "F0 1080 (N)", "V0 1080": "V0 1080 (m/s)"
}

# ==========================================
# 2. STRUCTURE DES MENUS DÉROULANTS & COMPARATEUR
# ==========================================
OFFICIAL_STRUCTURE = {
    "PROFILAGE MOTEUR": [
        "Knee To Wall (G)", "Knee To Wall (D)", "Sit And Reach",
        "Somme ADD", "Somme ABD", "Ratio Squeeze",
        "Adducteurs (G)", "Adducteurs (D)", 
        "Abducteurs (G)", "Abducteurs (D)",
        "Nordic Ischio (G)", "Nordic Ischio (D)",
        "Inverseur (G)", "Inverseur (D)", "Everseur (G)", "Everseur (D)",
        "Endurance Heel Raise (G)", "Endurance Heel Raise (D)",
        
    ],
    "PROFILAGE ATHLÉTIQUE": [
        "CMJ 2JB", "Peak Force CMJ", "RFD CMJ", "RSI CMJ",
        "Wattbike (6s)", "Squat belt (N)"
    ],
    "PROFILAGE PHYSIOLOGIQUE": [
        "VMA", "SV1", "SV2", "FC", "Temps sur 10m", "Test 1km (s)",
        "Distance Totale", "Distance HSR", "Distance Sprint (92% Vimax)",
        "Vmax", "Amax", "Dmax"
    ],

    "COMPOSITION CORPORELLE (ISAK)": [
        "Somme 8 plis", "Triceps", "Subscapulaire", "Biceps", "Crête iliaque", 
        "Supraspinale", "Abdominal", "Cuisse ISAK", "Jambe ISAK",
        "Tissu Adipeux", "Tissu Musculaire", "Tissu Osseux"
    ],
    "1080 SPRINT": [
        "Temps total 1080", "Amax 1080", "Pmax 1080", "Vmax 15m 1080", 
        "F0 1080", "V0 1080", "Tau 1080", "Momentum 1080"
    ]
}

TEAM_STRUCTURE = OFFICIAL_STRUCTURE.copy()
TEAM_STRUCTURE["ANALYSE DÉTAILLÉE (BIODEX)"] = [
    "Q Conc 60° (G)", "Q Conc 60° (D)", "Q Conc 240° (G)", "Q Conc 240° (D)",
    "IJ Conc 60° (G)", "IJ Conc 60° (D)", "IJ Conc 240° (G)", "IJ Conc 240° (D)",
    "IJ Exc 30° (G)", "IJ Exc 30° (D)"
]

# ==========================================
# 3. NORMES & UNITES 
# ==========================================
REPORT_NORMES = {
    "VMA": 15, "Vmax": 32, "CMJ 2JB": 40, "Peak Force CMJ": 2000,
    "Nordic": 30, "Adducteur": 4, "Knee To Wall (G)": 9, "Knee To Wall (D)": 9,
    "Sit And Reach": 20, "Distance HSR": 800,
    "Distance Totale": 8000, "Amax": 5, "Dmax": 5, "Distance Sprint (92% Vimax)": 60,
    "Somme ADD": 34, "Somme ABD": 34, "Ratio Squeeze": [0.90, 1.10],
    "Nordic Ischio (G)": 0.7, "Nordic Ischio (D)": 0.7,
    "Q Conc 60° (G)": 2.8, "Q Conc 60° (D)": 2.8,
    "Q Conc 240° (G)": 1.9, "Q Conc 240° (D)": 1.9,
    "IJ Conc 60° (G)": 1.5, "IJ Conc 60° (D)": 1.5,
    "IJ Conc 240° (G)": 1.2, "IJ Conc 240° (D)": 1.2,
    "IJ Exc 30° (G)": 2.0, "IJ Exc 30° (D)": 2.0,
    "Wattbike (6s)": 1100, "Squat belt (N)": 1500,
    "Temps sur 10m": 1.90, "Test 1km (s)": 220,
    # NORMES ISAK (Rappel : les plis sont inversés dans ton code, donc < 45 = Vert)
    "Somme 8 plis": 45, "Triceps": 5, "Subscapulaire": 7, "Biceps": 3, 
    "Crête iliaque": 7, "Supraspinale": 6, "Abdominal": 8, "Cuisse ISAK": 8, "Jambe ISAK": 4,
    
    # NORMES 1080 SPRINT
    "Temps total 1080": 2.55, # (Inversé : < 2.55s = Vert)
    "Amax 1080": 7.5, 
    "Pmax 1080": 1500,        # Valeur Absolue (le mode relatif la divisera par le poids)
    "Vmax 15m 1080": 7.8,
    "F0 1080": 650,           # Valeur Absolue
    "V0 1080": 9.0,
    "Tau 1080": 1.05,         # (Inversé)

    # --- Normes fusionnées depuis profiling_report.py (12/2026) ---
    # ATTENTION Antoine : "FC" est un pouls de fin d'effort et n'a normalement
    # pas de sens comme "objectif à dépasser" comme les autres tests. Je l'ai
    # gardée pour ne rien perdre de l'existant, mais à valider/retirer avec toi.
    "FC": 180,
    "SV1": 14, "SV2": 16,
    "Inverseur": 20, "Everseur": 18,
    "Endurance Heel Raise": 30,
    "Nb Accélérations": 50, "Nb Décélérations": 50,
    "CMJ 1JB": 20, "Drop jump": 30,
}

# NOTE MÉTHODOLOGIQUE (12/2026) : avant la fusion, "VMA" valait 15 ici et 18
# dans profiling_report.py -> un même joueur pouvait être vert dans le
# classement/comparateur et orange dans son rapport PDF pour la même valeur.
# On garde 15 (valeur déjà utilisée par 3 modules sur 4) par défaut. À
# confirmer avec toi : si 18 est la bonne valeur, un seul changement ici
# suffira désormais à corriger toute l'application.

# ==========================================
# 3bis. NORMES GPS PAR POSTE (objectifs club, 09/2026)
# ==========================================
# Demande explicite (09/2026) : les objectifs GPS ("Distance Totale",
# "Distance HSR"...) ne doivent plus être UN SEUL chiffre pour tout le
# monde (REPORT_NORMES ci-dessus) mais un objectif PAR POSTE ("un latéral
# doit pouvoir faire X, un défenseur Y..."), pour que les révélations/
# jeunes voient directement où ils se situent par rapport au niveau PRO.
#
# Valeurs calculées UNE FOIS à partir d'un export de seuils joueurs PRO
# (fichier fourni par le département, 25 joueurs de champ + gardiens,
# session Pré-saison) : moyenne par poste large (DÉFENSEUR/MILIEU/
# ATTAQUANT/GARDIEN -- même regroupement que le radar par poste
# d'Analyse Collective, cf. team_profiling.get_poste_large), en excluant
# les valeurs à 0 (trous de données GPS constatés pour certains joueurs
# sur cet export, ex: max speed=0 -- traité comme "non mesuré", pas comme
# un vrai 0). Objectifs FIXES tant que le département ne fournit pas un
# nouvel export (pas de source live -- voir la remarque du 09/2026 : "les
# seuils ne devraient pas bouger, ce sont des objectifs club").
#
# "Distance Sprint (92% Vimax)" ci-dessous réutilise l'objectif "distance
# zone 6" de l'export -- ATTENTION Antoine : ce n'est pas rigoureusement
# la même définition que la colonne "Distance Sprint (92% Vimax)" déjà
# suivie dans l'appli (zone de vitesse absolue vs seuil relatif au Vmax du
# joueur) ; les deux dérivent la distance "sprint" différemment. Réutilisé
# ici comme l'objectif le plus proche disponible -- à valider avec toi si
# tu veux une distinction plus stricte plus tard.
#
# "Nb Accélérations"/"Nb Décélérations" : objectif ajouté même si l'appli
# ne suit pas encore ces valeurs joueur par joueur en continu (pas de
# colonne dans le fichier principal aujourd'hui) -- prêt pour le jour où
# ce sera suivi, la carte affichera "-" pour la valeur en attendant.
#
# Échantillon par poste (25 joueurs PRO) : DÉFENSEUR n=8, ATTAQUANT n=7,
# MILIEU n=6, GARDIEN n=4 -- petit échantillon, à reconsolider si l'effectif
# PRO ou les seuils évoluent.
REPORT_NORMES_PAR_POSTE = {
    "Distance Totale": {"ATTAQUANT": 10768.9, "DÉFENSEUR": 10764.4, "MILIEU": 11567.2, "GARDIEN": 5893.0},
    "Distance HSR": {"ATTAQUANT": 1318.3, "DÉFENSEUR": 1015.2, "MILIEU": 1020.2, "GARDIEN": 40.8},
    "Distance Sprint (92% Vimax)": {"ATTAQUANT": 479.1, "DÉFENSEUR": 314.0, "MILIEU": 269.5, "GARDIEN": 2.2},
    "Nb Accélérations": {"ATTAQUANT": 98.0, "DÉFENSEUR": 101.0, "MILIEU": 99.0, "GARDIEN": 61.0},
    "Nb Décélérations": {"ATTAQUANT": 97.0, "DÉFENSEUR": 95.6, "MILIEU": 114.2, "GARDIEN": 42.2},
    # "Vmax" volontairement PAS ici (demande explicite 09/2026) : reste la
    # norme unique existante pour tout le monde (REPORT_NORMES["Vmax"] = 32
    # km/h), pas d'objectif par poste pour cet indicateur précis.
}

RELATIVE_NORM_KEYS = [
    "Nordic Ischio (G)", "Nordic Ischio (D)",
    "Q Conc 60° (G)", "Q Conc 60° (D)",
    "Q Conc 240° (G)", "Q Conc 240° (D)",
    "IJ Conc 60° (G)", "IJ Conc 60° (D)",
    "IJ Conc 240° (G)", "IJ Conc 240° (D)",
    "IJ Exc 30° (G)", "IJ Exc 30° (D)"
]

UNITS = {
    "Peak Force CMJ": "N",
    "RFD CMJ": "N/s",
    "RSI CMJ": "m/s",
    "Squat belt (N)": "N", "CMJ 2JB": "cm", "Knee To Wall (G)": "cm", "Knee To Wall (D)": "cm", 
    "Sit And Reach": "cm", "Somme ADD": "N", "Somme ABD": "N",
    "Adducteurs (G)": "N", "Adducteurs (D)": "N", "Abducteurs (G)": "N", "Abducteurs (D)": "N",
    "Nordic Ischio (G)": "Kg", "Nordic Ischio (D)": "Kg",
    "Inverseur (G)": "Kg", "Inverseur (D)": "Kg", "Everseur (G)": "Kg", "Everseur (D)": "Kg",
    "Endurance Heel Raise (G)": "Reps", "Endurance Heel Raise (D)": "Reps",

    "Wattbike (6s)": "W", "SV1": "km/h", "SV2": "km/h", "FC": "bpm", "VMA": "km/h",
    "Distance Totale": "m", "Distance HSR": "m", "Distance Sprint (92% Vimax)": "m",
    "Vmax": "km/h", "Amax": "m/s²", "Dmax": "m/s²", "Temps sur 10m": "s", "Test 1km (s)": "s",
    "Q Conc 60° (G)": "Nm", "Q Conc 60° (D)": "Nm", "Q Conc 240° (G)": "Nm", "Q Conc 240° (D)": "Nm",
    "IJ Conc 60° (G)": "Nm", "IJ Conc 60° (D)": "Nm", "IJ Conc 240° (G)": "Nm", "IJ Conc 240° (D)": "Nm",
    "IJ Exc 30° (G)": "Nm", "IJ Exc 30° (D)": "Nm",
    "Ratio Squeeze": "", "Ratio Mixte (G)": "", "Ratio Mixte (D)": "",
    # UNITÉS ISAK
    "Triceps": "mm", "Subscapulaire": "mm", "Biceps": "mm", "Crête iliaque": "mm",
    "Supraspinale": "mm", "Abdominal": "mm", "Cuisse ISAK": "mm", "Jambe ISAK": "mm",
    "Somme 8 plis": "mm",
    "Tissu Adipeux": "%", "Tissu Musculaire": "%", "Tissu Osseux": "%", "Tissu Résiduel": "%",
    
    # UNITÉS 1080 SPRINT
    "Temps total 1080": "s", "Amax 1080": "m/s²", "Pmax 1080": "W", 
    "Vmax 15m 1080": "m/s", "Tau 1080": "s", "T90 1080": "s", "D90 1080": "m", 
    "Momentum 1080": "kg*m/s", "F0 1080": "N", "V0 1080": "m/s",

    # --- Unités fusionnées depuis profiling_report.py (12/2026) ---
    "CMJ 1JB (G)": "cm", "CMJ 1JB (D)": "cm", "Drop jump": "cm",
    "Nb Accélérations": "", "Nb Décélérations": "",
}


# ==========================================
# 4. FONCTIONS PARTAGÉES (une seule version dans toute l'appli)
# ==========================================
# Avant : chaque fichier (utils.py, classement.py, comparateur.py,
# profiling_report.py, team_profiling.py...) avait sa PROPRE version de
# is_inverted(), avec des listes de mots-clés légèrement différentes.
# Risque concret : un même test pouvait être considéré "plus c'est bas mieux
# c'est" sur une page et l'inverse sur une autre. On centralise ici, et
# chaque module importe cette fonction au lieu de la redéfinir.
INVERTED_KEYWORDS = [
    'temps', 'chrono', '10m', '5-0-5', '505', 'agilité',
    'masse grasse', 'landing', '1km',
    # Plis cutanés ISAK (mm) : une valeur plus faible = moins de masse
    # grasse = meilleur profil pour un athlète -> logique "inversée" comme
    # un chrono. Repéré uniquement dans profiling.py avant cette fusion :
    # les autres pages (comparateur, classement...) ne l'appliquaient pas
    # aux plis ISAK, ce qui pouvait donner un mauvais sens de couleur/tri.
    'triceps', 'subscapulaire', 'biceps', 'iliaque', 'supraspinale',
    'abdominal', 'cuisse', 'jambe', 'somme 8 plis', 'somme de 8 plis',
    # 1080 Sprint : tau et t90 sont des temps de montée en vitesse -> plus
    # petit = plus explosif = meilleur.
    'tau', 't90',
]


def is_inverted_metric(label: str) -> bool:
    """
    Renvoie True si, pour ce test, une valeur PLUS FAIBLE est meilleure
    (ex: un temps de sprint, un temps sur 1km). Renvoie False si une valeur
    PLUS ÉLEVÉE est meilleure (ex: une VMA, une force). Sert à savoir dans
    quel sens trier/colorer un indicateur.
    """
    label_lower = str(label).lower()
    return any(keyword in label_lower for keyword in INVERTED_KEYWORDS)