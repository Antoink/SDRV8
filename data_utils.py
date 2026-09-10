# =============================================================================
# data_utils.py — Nettoyage de données et calculs de percentile PARTAGÉS
# =============================================================================
# Avant ce module, chaque page (profiling.py, profiling_report.py,
# comparateur.py, team_profiling.py) avait sa PROPRE version de ces fonctions,
# légèrement différente à chaque fois. Ça a causé plusieurs bugs concrets :
# - profiling_report.py ne nettoyait pas les virgules décimales FR ("7,10")
#   ni les espaces insécables avant de calculer un percentile -> pool de
#   comparaison tronqué en silence -> percentile faux dans le rapport PDF
#   (ex: Amax d'un joueur affiché "Flop 1%" alors que l'app affichait "Top 25%").
# - find_column_in_df existait en 4 versions différentes (profiling.py,
#   profiling_report.py, team_profiling.py, comparateur.py), avec une
#   protection anti-collision GPS/1080 absente ou incomplète selon le fichier.
#
# Toute la logique de nettoyage/percentile/résolution de colonne vit
# maintenant ICI, une seule fois. Les fichiers qui l'utilisaient avant
# importent désormais ces fonctions au lieu d'en garder une copie locale.
# =============================================================================

import re
import unicodedata

import pandas as pd
import streamlit as st

from config_rapport import COL_MAPPING, is_inverted_metric


def remove_accents(input_str):
    """Retire les accents d'une chaîne (pour les comparaisons de libellés)."""
    if not isinstance(input_str, str):
        return str(input_str)
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def last_valid_value(df_subset: pd.DataFrame, col: str, default=None):
    """
    Dernière valeur NON VIDE de `col` dans `df_subset` (généralement les
    lignes d'un même joueur), plutôt que `.iloc[-1]` qui prend la DERNIÈRE
    LIGNE SANS SE SOUCIER de si elle a une valeur pour cette colonne.

    BUG CORRIGÉ (09/2026) : plusieurs pages (profiling.py, classement.py,
    evolution.py) reconstruisaient les métadonnées fixes d'un joueur (Poste,
    Equipe, Position...) pour l'affichage "Record de Saison" avec
    `df_joueur.iloc[-1].get(col, ...)`. Ça marchait tant que le fichier de
    données n'avait qu'un type de ligne par joueur. Depuis l'ajout du
    fichier 1080 séparé (concaténé en lignes de session supplémentaires,
    qui n'ont QUE les colonnes 1080 remplies), la dernière ligne d'un
    joueur est souvent cette ligne 1080 -- et ces colonnes texte (Poste,
    Equipe...) y sont vides, donc `.iloc[-1].get(...)` renvoyait NaN/None
    au lieu de retomber sur le vrai poste/équipe du joueur.
    """
    if col not in df_subset.columns:
        return default
    valides = df_subset[col].dropna()
    if valides.empty:
        return default
    valides = valides[valides.astype(str).str.strip().str.lower() != "nan"]
    return valides.iloc[-1] if not valides.empty else default


def is_inverted(label):
    """
    True si, pour ce test, une valeur PLUS FAIBLE est meilleure (ex: un temps
    de sprint). Version unique et partagée -> voir config_rapport.py.
    """
    return is_inverted_metric(label)


def clean_numeric_value(val):
    """
    Convertit UNE valeur brute (str Excel/Sheets, virgule FR ou point) en float.

    BUG CORRIGÉ (09/2026) : cette fonction ne retirait pas les espaces
    (normaux ou insécables \\xa0/\\u202f) utilisés par Google Sheets/Excel
    comme séparateur de milliers en export FR. Résultat concret : "1 463,62"
    (Pmax 1080 d'un joueur) était tronqué au premier groupe de chiffres et
    lu comme "1" -> affiché "1 W" au lieu de ~1463 W. `clean_numeric_series`
    (juste au-dessus, pour une colonne entière) faisait déjà ce nettoyage
    correctement ; il manquait ici, sur la version "une seule valeur".
    """
    if pd.isna(val) or val == "" or val == "-":
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        val_str = re.sub(r'\s+', '', str(val)).replace(',', '.')
        match = re.search(r"[-+]?\d*\.\d+|\d+", val_str)
        if match:
            return float(match.group())
        return None
    except Exception:
        return None


def clean_numeric_series(series):
    """
    Convertit une Series entière en numérique, en gérant les virgules
    décimales FR ET les espaces (normaux ou insécables \\xa0 / \\u202F) des
    séparateurs de milliers. C'est CE nettoyage qui manquait dans certaines
    versions du code et faussait les percentiles calculés sur toute une
    colonne.
    """
    clean = series.astype(str).str.replace(r'[\s \xa0]+', '', regex=True).str.replace(',', '.', regex=False)
    return pd.to_numeric(clean, errors='coerce')


@st.cache_data
def get_column_stats(df, col_name):
    """Valeurs numériques valides d'une colonne + leur moyenne (mis en cache)."""
    if col_name not in df.columns:
        return None, 0
    valid_values = clean_numeric_series(df[col_name]).dropna()
    if valid_values.empty:
        return None, 0
    return valid_values, valid_values.mean()


def calculate_percentile(df, col_name, value):
    """
    Percentile d'une valeur au sein d'une colonne (0-100, sens de la métrique
    géré via is_inverted). Retourne (moyenne_colonne, percentile).
    """
    if pd.isna(value):
        return 0, 0
    valid_values, mean_val = get_column_stats(df, col_name)
    if valid_values is None:
        return 0, 0

    if "Ratio Squeeze" in col_name:
        # Cas particulier : plus la valeur est PROCHE de 1.0 (équilibre
        # parfait G/D), meilleur le percentile — ni "plus grand" ni "plus
        # petit" n'a de sens ici.
        distances = abs(valid_values - 1.0)
        val_dist = abs(value - 1.0)
        percentile = (distances >= val_dist).mean() * 100
        return mean_val, percentile

    if is_inverted(col_name):
        percentile = (valid_values >= value).mean() * 100
    else:
        percentile = (valid_values <= value).mean() * 100
    return mean_val, percentile


def format_pct_display(pct, mode="app"):
    """
    Formatage texte d'un percentile pour l'affichage.
    mode="app"    : vocabulaire interne (Top X% / Moyen / X%).
    mode="export" : pour les rapports HTML/PDF donnés aux joueurs.

    BUG CORRIGÉ (09/2026) : le mot "Flop" (mode="app" uniquement, avant)
    pouvait mal être interprété par un lecteur non-spécialiste (agent,
    direction...) qui voit l'appli en plus des rapports exportés -- retiré
    partout, pas seulement des exports. Les deux modes affichent maintenant
    juste le percentile en dessous de 33%, sans qualificatif.
    """
    if pct is None or pd.isna(pct):
        return ""
    try:
        val = int(pct)
    except Exception:
        return ""

    if val >= 66:
        return f"Top {max(1, 100 - val)}%"
    if val >= 33:
        return "Moyen"
    return f"{val}%"


@st.cache_data
def _get_cleaned_columns(columns_tuple):
    return [remove_accents(str(c)).lower().strip() for c in columns_tuple]


def find_column_in_df(df, label, col_mapping=None):
    """
    Résout un libellé UI (ex: "Vmax", "Amax 1080") vers le vrai nom de
    colonne du DataFrame. Gère explicitement la collision GPS/1080 (ex:
    "Vmax" ne doit jamais matcher "Vmax 15m 1080 (m/s)" et vice-versa) —
    c'était la principale source de divergence entre les 4 anciennes
    versions de cette fonction.

    col_mapping : par défaut le COL_MAPPING partagé de config_rapport.py ;
    passer un dict différent pour les rares pages (ex: profiling_report.py)
    qui ont volontairement leur propre mapping de mise en page.
    """
    if col_mapping is None:
        col_mapping = COL_MAPPING
    col_map_lower = {k.lower(): v for k, v in col_mapping.items()}
    label_lower = str(label).lower().strip()
    if label_lower in col_map_lower:
        mapped = col_map_lower[label_lower]
        if mapped in df.columns:
            return mapped

    label_str = label_lower
    cherche_1080 = "1080" in label_str
    cherche_gps = any(x in label_str for x in ["vmax", "amax", "dmax"]) and not cherche_1080

    label_no_paren = re.sub(r'\(.*?\)', '', label_str)
    label_clean = re.sub(r'[^a-z0-9]', '', label_no_paren)

    df_cols_clean = _get_cleaned_columns(tuple(df.columns))

    # 1. Correspondance exacte nettoyée
    for idx, col_str in enumerate(df_cols_clean):
        col_no_paren = re.sub(r'\(.*?\)', '', col_str)
        col_clean = re.sub(r'[^a-z0-9]', '', col_no_paren)
        if label_clean == col_clean:
            return df.columns[idx]

    # 2. Recherche par mot-clé avec sécurité anti-collision GPS/1080
    mots = re.findall(r'[a-z0-9]+', label_no_paren)
    if not mots:
        return None
    mot_principal = mots[0]

    for idx, col_str in enumerate(df_cols_clean):
        if cherche_gps and "1080" in col_str:
            continue
        if cherche_1080 and "1080" not in col_str:
            continue
        if mot_principal not in col_str:
            continue
        if len(mots) > 1 and not cherche_1080:
            mot_secondaire = mots[1]
            if mot_secondaire not in col_str:
                continue
        return df.columns[idx]

    return None
