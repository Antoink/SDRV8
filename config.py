# -*- coding: utf-8 -*-
"""
config.py
=========
Toutes les constantes du projet : couleurs, mapping des colonnes Excel,
normes physiques, unités, groupes de métriques pour l'UI et les rapports.

POURQUOI un fichier dédié ?
---------------------------
Dans l'ancien script, ces constantes étaient mélangées avec la logique de
calcul et le HTML, au milieu de 2000+ lignes. Résultat : impossible de
retrouver rapidement "où est définie la norme du CMJ" ou "quelle est la
couleur du rouge SDR". En isolant tout ici :
- une seule source de vérité, réutilisable par data_loader / stats_engine /
  charts / report_*.py sans dépendance circulaire ;
- si le staff change une norme (ex : cible VMA) ou une couleur de charte
  graphique, une seule ligne à modifier ;
- ce fichier peut être versionné et discuté en comité de pilotage
  indépendamment du code de calcul.
"""

# ---------------------------------------------------------------------------
# Charte graphique
# ---------------------------------------------------------------------------
SDR_RED = "#D71920"
GREEN = "#27AE60"
ORANGE = "#F39C12"
BLUE_ELITE = "#00E5FF"
DARK = "#333333"

# Variantes "texte" de GREEN/ORANGE/BLUE_ELITE, plus foncées, à utiliser
# quand la couleur sert de COULEUR DE TEXTE sur fond blanc/clair (légendes,
# statuts...), pas quand elle sert juste de pastille/fond décoratif.
# POURQUOI : les couleurs vives ci-dessus, lisibles en pastille ou en fond
# de badge, tombent sous le ratio de contraste WCAG AA (4.5:1) une fois
# utilisées comme couleur de texte sur blanc -- particulièrement
# BLUE_ELITE (~1.5:1, quasi illisible) et ORANGE (~2.2:1). Ces 3 variantes
# gardent la même teinte perçue mais passent AA (~4.7 à 6:1).
GREEN_TEXT = "#1E8449"
ORANGE_TEXT = "#B34700"
BLUE_ELITE_TEXT = "#006C8C"

# ---------------------------------------------------------------------------
# Mapping "label lisible" -> "nom de colonne réel dans le fichier Excel"
# ---------------------------------------------------------------------------
# POURQUOI : le nom des colonnes Excel change parfois d'une saison à l'autre
# (accents, espaces, unités ajoutées...). Ce dictionnaire découple le nom
# affiché au staff du nom de colonne technique. `find_column()` (dans
# data_loader.py) s'appuie dessus en priorité, puis retombe sur une
# recherche floue si la colonne n'est pas trouvée telle quelle.
COL_MAPPING = {
    "Joueur": "Joueur", "Equipe": "Equipe", "Age": "Age",
    "Poids": "Poids (kg)", "Taille": "Taille (cm)", "Masse Grasse": "Masse grasse",
    "Poste": "Position", "Latéralité": "Latéralité",
    "Sit And Reach": "Sit and reach", "Knee To Wall (D)": "Knee to wall D", "Knee To Wall (G)": "Knee to wall G",
    "Adducteurs (G)": "Adducteur G", "Adducteurs (D)": "Adducteur D",
    "Somme ADD": "Somme ADD", "Ratio Squeeze": "Ratio Squeeze (ADD/ABD)",
    "Abducteurs (G)": "Abducteur G", "Abducteurs (D)": "Abducteur D", "Somme ABD": "Somme ABD",
    "Nordic Ischio (G)": "Nordic G", "Nordic Ischio (D)": "Nordic D",
    "Inverseur (G)": "Inverseur G", "Inverseur (D)": "Inverseur D",
    "Everseur (G)": "Everseur G", "Everseur (D)": "Everseur D",
    "Endurance Heel Raise (G)": "Endurance Heel Raise G", "Endurance Heel Raise (D)": "Endurance Heel Raise D",
    "CMJ 2JB": "CMJ 2JB", "Peak Force CMJ": "Peak Force CMJ", "RFD CMJ": "RFD CMJ",
    "RSI CMJ": "RSI", "Drop jump": "Drop jump",
    "Wattbike (6s)": "Wattbike 6s (W)", "Squat belt (N)": "Squat belt (N)",
    "VMA": "VMA", "FC": "FC", "SV1": "SV1", "SV2": "SV2", "Test 1km (s)": "Test 1km (s)",
    "Temps sur 10m": "Temps sur 10m",
    "Amax": "Amax", "Dmax": "Dmax", "Vmax": "Vmax",
    "Distance HSR": "Distance HSR", "Distance Totale": "Distance totale",
    "Distance Sprint (92% Vimax)": "Distance Sprint (92% Vimax)",
    "Q Conc 60° (G)": "Q G conc 60°/s", "Q Conc 60° (D)": "Q Dt conc 60°/s",
    "Q Conc 240° (G)": "Q G conc 240°/s", "Q Conc 240° (D)": "Q Dt conc 240°/s",
    "IJ Conc 60° (G)": "IJ G conc 60°/s", "IJ Conc 60° (D)": "IJ Dt conc 60°/s",
    "IJ Conc 240° (G)": "IJ G conc 240°/s", "IJ Conc 240° (D)": "IJ Dt conc 240°/s",
    "IJ Exc 30° (G)": "IJ G Exc 30°/s", "IJ Exc 30° (D)": "IJ Dt exc 30°/s",
    "Ratio Mixte (G)": "Ratio Mixte G", "Ratio Mixte (D)": "Ratio Mixte D",
    "Isak Triceps": "Isak_triceps", "Isak Sous-scapulaire": "Isak_sousscapulaire",
    "Isak Biceps": "Isak_biceps", "Isak Crête iliaque": "Isak_crete",
    "Isak Supra-épineux": "Isak_supraspinale", "Isak Abdominal": "Isak_abdominal",
    "Isak Cuisse": "Isak_cuisse", "Isak Jambe": "Isak_jambe",
    "Temps 15m (1080)": "Temps total 1080 (s)", "Temps 5m (1080)": "Temps 0-5 1080 (s)",
    "Vitesse Max 15m (1080)": "Vmax 1080 (Km/h)", "Amax 1080": "Amax 1080 (m/s²)",
}

# ---------------------------------------------------------------------------
# Groupes de métriques (pour l'UI sidebar + regroupement dans le rapport)
# ---------------------------------------------------------------------------
GROUPES_PREPA = {
    "Vitesse / GPS": ["Amax", "Dmax", "Vmax", "Distance HSR",
                       "Distance Totale", "Distance Sprint (92% Vimax)"],
    "Puissance": ["Wattbike (6s)"],
    "Force": ["Squat belt (N)"],
    "Saut": ["CMJ 2JB", "Peak Force CMJ", "RFD CMJ", "RSI CMJ", "Drop jump"],
    "Aérobie": ["VMA", "FC", "SV1", "SV2", "Test 1km (s)"],
    "Sprint 1080 (15m)": ["Temps 15m (1080)", "Temps 5m (1080)", "Vitesse Max 15m (1080)", "Amax 1080"],
}

GROUPES_KINE = {
    "Mobilité": ["Sit And Reach", "Knee To Wall (G)", "Knee To Wall (D)"],
    "Adducteurs & Abducteurs": [
        "Adducteurs (G)", "Adducteurs (D)", "Somme ADD",
        "Abducteurs (G)", "Abducteurs (D)", "Somme ABD", "Ratio Squeeze",
    ],
    "Ischio-Jambiers": ["Nordic Ischio (G)", "Nordic Ischio (D)"],
    "Mollets": ["Endurance Heel Raise (G)", "Endurance Heel Raise (D)"],
    "Pieds": ["Inverseur (G)", "Inverseur (D)", "Everseur (G)", "Everseur (D)"],
    "Biodex - Concentrique": [
        "Q Conc 60° (G)", "Q Conc 60° (D)", "Q Conc 240° (G)", "Q Conc 240° (D)",
        "IJ Conc 60° (G)", "IJ Conc 60° (D)", "IJ Conc 240° (G)", "IJ Conc 240° (D)",
    ],
    "Biodex - Excentrique": ["IJ Exc 30° (G)", "IJ Exc 30° (D)", "Ratio Mixte (G)", "Ratio Mixte (D)"],
    "Composition Corporelle (ISAK)": [
        "Isak Triceps", "Isak Sous-scapulaire", "Isak Biceps", "Isak Crête iliaque",
        "Isak Supra-épineux", "Isak Abdominal", "Isak Cuisse", "Isak Jambe",
    ],
}

# Labels des 8 sites ISAK, dans l'ordre standard du protocole (utilisé pour
# le radar dédié — cf. report_kine.py::_isak_radar_data).
ISAK_LABELS = [
    "Isak Triceps", "Isak Sous-scapulaire", "Isak Biceps", "Isak Crête iliaque",
    "Isak Supra-épineux", "Isak Abdominal", "Isak Cuisse", "Isak Jambe",
]
ISAK_RADAR_MAX_MM = 15  # échelle du radar (mm) — cohérent avec la plage réelle observée sur le fichier (1.5-14mm)

# Groupes de métriques (au sein de GROUPES_PREPA) pour lesquels on affiche en
# plus un mini-radar dédié dans le rapport (percentile 0-100, même logique
# que le radar principal). Pratique pour un ensemble de tests cohérents
# (ex: le sprint 1080/15m) qu'on veut visualiser d'un coup d'œil sans que
# le staff ait à le sélectionner manuellement dans le radar principal.
GROUPES_AVEC_RADAR_DEDIE = ["Sprint 1080 (15m)", "Vitesse / GPS"]

# ---------------------------------------------------------------------------
# Plan d'individualisation (document "Réflexion individualisation")
# ---------------------------------------------------------------------------
# KPI prioritaire par joueur (clé = valeur EXACTE de la colonne "Joueur" du
# fichier Excel). Utilisé pour pré-remplir "Axes d'amélioration".
#
# IMPORTANT : seuls les joueurs identifiés SANS AMBIGUÏTÉ entre le document
# source (prénoms/surnoms) et le roster PRO du fichier Excel sont inclus
# ici. 6 prénoms du document n'ont pas pu être associés avec certitude à un
# joueur du fichier (Quentin, JP, JP Célestin, Chams, Mansour, Amine) car
# soit le prénom seul est ambigu (plusieurs joueurs possibles), soit aucun
# joueur du roster PRO ne correspond. Pour les ajouter : complète ce
# dictionnaire avec `"NOM Prénom exact (colonne Joueur)": "Développement du
# RFD"` (ou une autre valeur de KPI_WEEKLY_PLAN ci-dessous).
#
# Cas particulier Daramy : le document liste "Optimisation de la
# composition corporelle", mais remplacé ici par "Développement de la
# répétition des efforts" sur demande explicite du staff (contre-indication
# connue non reflétée dans le document source).
PLAYER_KPI_PRIORITAIRE = {
    "AKIEME Sergio": "Développement du RFD",
    "DARAMY Mohammed": "Développement de la répétition des efforts",  # override staff (doc source: composition corporelle)
    "DEBONDT Mael": "Développement du RFD",
    "DIARRASSOUBA Tidiane": "Développement de la répétition des efforts",
    "EL KACHATI Youssef": "Développement de la force",
    "FOFANA Yaya": "Prévention des blessures",
    "GADOU Arone": "Développement de la répétition des efforts",
    "GBANE Mory": "Prévention des blessures",
    "GUINDO Daouda": "Développement de la force",
    "HULSMANN RITZY Tom": "Développement du RFD",
    "KOTTO Samuel": "Développement de la force",
    "LEONI Theo": "Développement de la force",  # "Théo" et "Théo D." partagent le même KPI dans le document
    "MAMBUKU Jean Tryfose": "Optimisation de la composition corporelle",
    "NAKAMURA Keito": "Développement du RFD",
    "NTAMON Elie": "Développement du RFD",
    "OKUMU Joseph": "Prévention des blessures",
    "OMERAGIC Edin": "Développement de la force",
    "OTOMEWO John": "Optimisation de la composition corporelle",
    "SAUVAGE Alexis": "Développement de la force",
    "SIEBATCHEU Jordy": "Développement du RFD",
    "SOUMANO Sambou": "Développement de la répétition des efforts",
    "SYLLA Lenny": "Prévention des blessures",
    "SYLLA Soumaila": "Optimisation de la composition corporelle",
    "TIA Martial": "Prévention des blessures",
    "ZOHOURI Armel": "Développement du RFD",
    # Ajoutés suite à confirmation du staff (certains sont Espoir/Elite,
    # intégrés au plan d'individualisation aux côtés du groupe PRO) :
    "KASHI Amine": "Optimisation de la composition corporelle",
    "PATRICK John": "Développement du RFD",
    "CELESTIN Jean Philippe": "Développement de la répétition des efforts",
    # BUG CORRIGÉ (09/2026) : ces 2 clés avaient un espace en début de nom
    # ("orthographe exacte" d'un espace parasite alors présent dans le
    # fichier) -- mais utils.load_data() nettoie déjà les noms de joueurs
    # avec .strip() au chargement, donc la clé espacée ne matchait plus
    # JAMAIS le nom réel une fois les données en mémoire : la stratégie
    # "Se référer aux recommandations du Département Performance" ne
    # s'affichait jamais pour ces 2 joueurs. Espaces retirés ; la recherche
    # dans suggestions.resolve_kpi_for_player est de toute façon désormais
    # insensible aux espaces, pour ne plus jamais reproduire ce bug.
    "KOURANFAL Chamsedin": "Développement de la force",
    "OKWARO Manzur": "Développement de la répétition des efforts",
    "PARIS Quentin": "Développement de la force",
}

# Plan hebdomadaire du département performance, par groupe de KPI (colonnes
# du tableau "GROUPES DE TRAVAIL" du document). Sert à pré-remplir les
# stratégies Salle/Terrain. La séparation Salle/Terrain n'est pas explicite
# dans le document source : elle est déduite ici par mot-clé (Vélo/HIIT =
# Terrain, le reste = Salle) — à ajuster si cette convention ne correspond
# pas à l'usage réel du staff (cf. README).
KPI_WEEKLY_PLAN = {
    "Développement du RFD": {
        "MD": "Mobilité", "MD+1": "OFF", "MD+2": "Musculation haut du corps - RFD",
        "MD+3": "Musculation bas du corps - 1080 / RFD",
        "MD+4 / MD-3": "Musculation bas du corps verticale - Squat Keiser / RFD",
        "MD-2": "Musculation haut du corps - RFD", "MD-1": "Réactivité",
    },
    "Développement de la force": {
        "MD": "Mobilité", "MD+1": "OFF", "MD+2": "Musculation haut du corps - Force",
        "MD+3": "Musculation bas du corps - Force",
        "MD+4 / MD-3": "Musculation bas du corps verticale - Squat Keiser / Force",
        "MD-2": "Musculation haut du corps - Force", "MD-1": "Mobilité / ROM",
    },
    "Prévention des blessures": {
        "MD": "Prévention spécifique", "MD+1": "Vélo Z2", "MD+2": "Prévention soft avec kiné",
        "MD+3": "Prévention orientée Force", "MD+4 / MD-3": "Prévention orientée Force",
        "MD-2": "Prévention soft / orientation RFD", "MD-1": "Mobilité",
    },
    "Développement de la répétition des efforts": {
        "MD": "Vélo", "MD+1": "Vélo Z2", "MD+2": "Vélo Z3", "MD+3": "HIIT",
        "MD+4 / MD-3": "HIIT", "MD-2": "Vélo Z3", "MD-1": "Vélo Z2",
    },
    "Optimisation de la composition corporelle": {
        "MD": "Vélo + gainage", "MD+1": "Vélo Z2", "MD+2": "Abdos / gainage + vélo Z3",
        "MD+3": "Abdos / gainage + HIIT", "MD+4 / MD-3": "Abdos / gainage + HIIT",
        "MD-2": "Abdos / gainage + vélo Z3", "MD-1": "Abdos / gainage + vélo Z2",
    },
}
KPI_WEEKLY_PLAN_DAYS_ORDER = ["MD", "MD+1", "MD+2", "MD+3", "MD+4 / MD-3", "MD-2", "MD-1"]

# Correspondance groupe de métriques -> qualité physique "simple", pour le
# point fort auto (config.QUALITES_PHYSIQUES). Sert à dire "Force" ou
# "Vitesse" plutôt que citer une métrique précise avec sa valeur exacte.
GROUPE_VERS_QUALITE = {
    "Puissance": "Puissance", "Force": "Force", "Saut": "Explosivité", "Aérobie": "Endurance",
    "Vitesse / GPS": "Vitesse", "Sprint 1080 (15m)": "Vitesse",
    "Mobilité": "Mobilité", "Adducteurs & Abducteurs": "Force", "Ischio-Jambiers": "Force",
    "Mollets": "Force", "Pieds": "Stabilité", "Biodex - Concentrique": "Force", "Biodex - Excentrique": "Force",
    # Composition Corporelle (ISAK) volontairement absente : un pli cutané
    # n'est pas une "qualité" à mettre en avant de la même façon.
}

KINE_LABELS = [
    "Q Conc 60° (G)", "Q Conc 60° (D)", "Q Conc 240° (G)", "Q Conc 240° (D)",
    "IJ Conc 60° (G)", "IJ Conc 60° (D)", "IJ Conc 240° (G)", "IJ Conc 240° (D)",
    "IJ Exc 30° (G)", "IJ Exc 30° (D)", "Nordic Ischio (G)", "Nordic Ischio (D)",
    "Adducteurs (G)", "Adducteurs (D)", "Abducteurs (G)", "Abducteurs (D)",
    "Inverseur (G)", "Inverseur (D)", "Everseur (G)", "Everseur (D)",
]

# ---------------------------------------------------------------------------
# Normes (seuils cibles utilisés pour le statut "Acquis / Non acquis")
# ---------------------------------------------------------------------------
# ATTENTION méthodologique : ce sont des seuils opérationnels fixés par le
# staff (repères d'entraînement), PAS des valeurs statistiquement calibrées
# sur ta base. Elles ne doivent pas être présentées comme telles dans la
# thèse : le percentile / z-score (calculé dans stats_engine.py à partir de
# la distribution réelle du groupe de référence) est la mesure rigoureuse ;
# la norme est un repère pédagogique pour le staff terrain.
NORMES_ABSOLUES = {
    "VMA": 16, "FC": 180, "SV1": 14, "SV2": 16, "Vmax": 32, "CMJ 2JB": 40, "Drop jump": 30,
    "Knee To Wall": 9, "Sit And Reach": 20, "Distance HSR": 800,
    "Distance Totale": 8000, "Distance Sprint (92% Vimax)": 60,
    "Somme ADD": 35, "Somme ABD": 35, "Ratio Squeeze": [0.90, 1.10],
    "Adducteur": 26, "Abducteur": 26, "Nordic": 36,
    "Inverseur": 10, "Everseur": 10, "Endurance Heel Raise": 15,
    "Wattbike": 1100, "Temps sur 10m": 1.90, "Test 1km (s)": 220,
    "Peak Force CMJ": 2000, "RFD CMJ": 10000, "RSI": 2.5,
    # RETIRÉES (non pertinentes) : "Amax": 5, "Dmax": 5, "Squat belt": 1500.
    # Vérifié sur les données réelles PRO (n=28-30, session Pré-saison) : le minimum
    # observé dépasse déjà largement ces seuils (Squat belt min=2461N pour un seuil
    # à 1500N ; Amax min=6.3 pour un seuil à 5 ; Dmax min=7.6 pour un seuil à 5).
    # Résultat : 100% des joueurs étaient "Acquis" à tous les coups, seuil qui ne
    # discrimine rien. Ces métriques utilisent désormais l'objectif dynamique
    # (moyenne du groupe de référence sélectionné) — voir stats_engine.get_norm_info.
}

NORMES_RELATIVES = {
    "Wattbike": 15.0, "Peak Force CMJ": 25.0, "Adducteur": 0.2, "Nordic": 0.08,
    # RETIRÉES (non pertinentes en version relative) : "Squat belt": 20.0 (même
    # constat qu'en absolu, seuil toujours trivialement dépassé), "Abducteur": 0.2
    # (minimum observé 0.22 > 0.2, seuil jamais discriminant), "Inverseur": 0.2 et
    # "Everseur": 0.18 (à l'inverse, quasi aucun joueur PRO ne les atteint : moyenne
    # observée 0.126 et 0.136 respectivement — seuils irréalistes pour l'effectif
    # actuel). Basculées sur l'objectif dynamique.
}

REPORT_NORMES = {**NORMES_ABSOLUES, **NORMES_RELATIVES}

UNITS = {
    "Knee To Wall (G)": "cm", "Knee To Wall (D)": "cm", "Sit And Reach": "cm",
    "Somme ADD": "Kg", "Somme ABD": "Kg", "Ratio Squeeze": "",
    "Adducteurs (G)": "Kg", "Adducteurs (D)": "Kg", "Abducteurs (G)": "Kg", "Abducteurs (D)": "Kg",
    "Nordic Ischio (G)": "Kg", "Nordic Ischio (D)": "Kg",
    "Inverseur (G)": "Kg", "Inverseur (D)": "Kg",
    "Everseur (G)": "Kg", "Everseur (D)": "Kg",
    "Endurance Heel Raise (G)": "reps", "Endurance Heel Raise (D)": "reps",
    "Q Conc 60° (G)": "Nm", "Q Conc 60° (D)": "Nm", "Q Conc 240° (G)": "Nm", "Q Conc 240° (D)": "Nm",
    "IJ Conc 60° (G)": "Nm", "IJ Conc 60° (D)": "Nm", "IJ Conc 240° (G)": "Nm", "IJ Conc 240° (D)": "Nm",
    "IJ Exc 30° (G)": "Nm", "IJ Exc 30° (D)": "Nm",
    "CMJ 2JB": "cm", "Peak Force CMJ": "N", "RFD CMJ": "N/s", "RSI CMJ": "", "Drop jump": "cm",
    "Wattbike (6s)": "W", "Squat belt (N)": "N",
    "VMA": "km/h", "Vmax": "km/h", "Temps sur 10m": "s", "Test 1km (s)": "s",
    "SV1": "km/h", "SV2": "km/h", "FC": "bpm",
    "Distance Totale": "m", "Distance HSR": "m", "Distance Sprint (92% Vimax)": "m",
    "Amax": "m/s²", "Dmax": "m/s²",
    "Ratio Mixte (G)": "", "Ratio Mixte (D)": "",
    "Isak Triceps": "mm", "Isak Sous-scapulaire": "mm", "Isak Biceps": "mm", "Isak Crête iliaque": "mm",
    "Isak Supra-épineux": "mm", "Isak Abdominal": "mm", "Isak Cuisse": "mm", "Isak Jambe": "mm",
    "Temps 15m (1080)": "s", "Temps 5m (1080)": "s", "Vitesse Max 15m (1080)": "km/h", "Amax 1080": "m/s²",
}

ETATS_ACTIONS = ["En manque de", "Renforcement de", "Maintien de", "Prévention de", "Rééquilibrage de"]
QUALITES_PHYSIQUES = ["Force", "Mobilité", "Puissance", "Vitesse", "Endurance",
                       "Stabilité", "Explosivité", "Réactivité", "Blessure (Ratio)"]
ZONES_CIBLEES = [
    "Pied / Orteil", "Cheville", "Mollets", "Genou",
    "Ischio-jambiers", "Quadriceps", "Adducteurs", "Abducteurs",
    "Hanche", "Hanche / Pubis", "Fessiers", "Bassin",
    "Tronc / Gainage", "Dos / Lombaires", "Cervicales",
    "Épaule", "Coude", "Poignet / Main",
    "Membre supérieur", "Membre inférieur",
    "Chaîne postérieure", "Chaîne antérieure", "Chaîne croisée", "Global",
]

THEME_MAPPING = {
    "CMJ 2JB": ("Puissance", "Membre inférieur"), "Peak Force CMJ": ("Force", "Membre inférieur"),
    "RFD CMJ": ("Explosivité", "Membre inférieur"), "RSI CMJ": ("Réactivité", "Membre inférieur"),
    "Drop jump": ("Réactivité", "Membre inférieur"), "Squat belt (N)": ("Force", "Membre inférieur"),
    "Wattbike (6s)": ("Puissance", "Membre inférieur"), "Vmax": ("Vitesse", "Global"),
    "Somme ADD": ("Force", "Chaîne antérieure"), "Somme ABD": ("Force", "Chaîne antérieure"),
    "Sit And Reach": ("Mobilité", "Chaîne postérieure"),
    "Knee To Wall (D)": ("Mobilité", "Cheville"), "Knee To Wall (G)": ("Mobilité", "Cheville"),
}

# Cibles Biodex (N/kg) utilisées pour le radar isocinétique
BIODEX_TARGETS = {"Q 60°": 3.1, "Q 240°": 2.2, "IJ 60°": 1.8, "IJ 240°": 1.5, "IJ Exc 30°": 2.4}
BIODEX_CONFIG = [
    {"label": "Q 60°", "g_rel": "Q G conc 60°/s (N/kg)", "d_rel": "Q Dt conc 60°/s (N/kg)",
     "g_raw": "Q G conc 60°/s", "d_raw": "Q Dt conc 60°/s"},
    {"label": "Q 240°", "g_rel": "Q G conc 240°/s (N/kg)", "d_rel": "Q Dt conc 240°/s (N/kg)",
     "g_raw": "Q G conc 240°/s", "d_raw": "Q Dt conc 240°/s"},
    {"label": "IJ 60°", "g_rel": "IJ G conc 60°/s (N/kg)", "d_rel": "IJ Dt conc 60°/s (N/kg)",
     "g_raw": "IJ G conc 60°/s", "d_raw": "IJ Dt conc 60°/s"},
    {"label": "IJ 240°", "g_rel": "IJ G conc 240°/s (N/kg)", "d_rel": "IJ Dt conc 240°/s (N/kg)",
     "g_raw": "IJ G conc 240°/s", "d_raw": "IJ Dt conc 240°/s"},
    {"label": "IJ Exc 30°", "g_rel": "IJ G Exc 30°/s (N/kg)", "d_rel": "IJ Dt exc 30°/s (N/kg)",
     "g_raw": "IJ G Exc 30°/s", "d_raw": "IJ Dt exc 30°/s"},
]

# Seuil minimal d'effectif du groupe de référence en-dessous duquel le
# percentile est jugé peu fiable (repli automatique vers un groupe plus large).
N_REF_MIN = 8