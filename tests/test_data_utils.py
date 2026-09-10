# =============================================================================
# tests/test_data_utils.py
# =============================================================================
# Tests des fonctions PARTAGÉES de data_utils.py (nettoyage de données,
# percentile, résolution de colonne). Ce sont exactement les fonctions dont
# une version buguée a produit de vrais problèmes dans le rapport PDF des
# joueurs (ex: percentile faux à cause d'une virgule décimale non nettoyée) —
# ces tests existent pour que ce type de régression ne puisse plus repasser
# inaperçu.
#
# Lancer : pytest   (depuis le dossier du projet, après
#          pip install -r requirements-dev.txt)
# =============================================================================

import pandas as pd
import pytest

from data_utils import (
    calculate_percentile,
    clean_numeric_value,
    clean_numeric_series,
    find_column_in_df,
    format_pct_display,
    is_inverted,
)


# --- clean_numeric_value -----------------------------------------------------

def test_clean_numeric_value_virgule_decimale_fr():
    # C'est exactement le cas qui a fait planter le percentile d'Amax dans
    # le rapport d'un joueur : "7,10" doit donner 7.10, pas None.
    assert clean_numeric_value("7,10") == 7.10


def test_clean_numeric_value_deja_un_float():
    assert clean_numeric_value(7.1) == 7.1


def test_clean_numeric_value_vide_ou_manquant():
    assert clean_numeric_value("") is None
    assert clean_numeric_value("-") is None
    assert clean_numeric_value(None) is None
    assert clean_numeric_value(pd.NA) is None


def test_clean_numeric_value_texte_non_numerique():
    assert clean_numeric_value("#VALEUR!") is None


# --- clean_numeric_series -----------------------------------------------------

def test_clean_numeric_series_virgules_et_espaces_insecables():
    s = pd.Series(["7,10", "1 234,5", "5.2", None, "#VALEUR!"])
    result = clean_numeric_series(s)
    assert result.tolist() == pytest.approx([7.1, 1234.5, 5.2, float("nan"), float("nan")], nan_ok=True)


# --- calculate_percentile ----------------------------------------------------

def test_calculate_percentile_metrique_normale_plus_grand_est_mieux():
    df = pd.DataFrame({"Amax": ["5", "6", "7", "8", "9"]})
    # Un joueur à 9 (le max) doit être au 100e percentile.
    _, pct = calculate_percentile(df, "Amax", 9)
    assert pct == 100
    # Un joueur à 5 (le min) doit être au percentile le plus bas.
    _, pct_min = calculate_percentile(df, "Amax", 5)
    assert pct_min == 20  # 1 valeur sur 5 est <= 5


def test_calculate_percentile_metrique_inversee_plus_petit_est_mieux():
    # "Temps sur 10m" : un temps plus faible est meilleur (cf. INVERTED_KEYWORDS).
    df = pd.DataFrame({"Temps sur 10m": ["1.5", "1.6", "1.7", "1.8"]})
    _, pct = calculate_percentile(df, "Temps sur 10m", 1.5)  # le meilleur temps
    assert pct == 100


def test_calculate_percentile_gere_les_virgules_decimales_fr_dans_le_pool():
    # Reproduction du bug réel : une colonne avec des valeurs au format FR
    # ("7,10") ne doit PAS voir son pool de comparaison tronqué.
    df = pd.DataFrame({"Amax": ["7,10", "6,50", "8,00", "5,90", "7,80"]})
    _, pct = calculate_percentile(df, "Amax", 7.10)
    # Sans nettoyage, ces 5 valeurs deviendraient toutes NaN -> pool vide -> 0.
    assert pct > 0
    assert pct == 60  # 3 valeurs sur 5 sont <= 7.10


def test_calculate_percentile_colonne_absente():
    df = pd.DataFrame({"Amax": ["7"]})
    mean_val, pct = calculate_percentile(df, "Colonne Inexistante", 7)
    assert (mean_val, pct) == (0, 0)


def test_calculate_percentile_ratio_squeeze_symetrique():
    # Pour un ratio (équilibre G/D), plus la valeur est proche de 1.0,
    # meilleur le percentile — ni "plus grand" ni "plus petit" n'est "mieux".
    df = pd.DataFrame({"Ratio Squeeze": ["1.0", "0.8", "1.2", "0.5", "1.5"]})
    _, pct = calculate_percentile(df, "Ratio Squeeze", 1.0)
    assert pct == 100  # rien n'est plus proche de 1.0 que 1.0 lui-même


# --- format_pct_display -------------------------------------------------------

def test_format_pct_display_mode_app():
    assert format_pct_display(90) == "Top 10%"
    assert format_pct_display(50) == "Moyen"
    assert format_pct_display(10) == "10%"


def test_format_pct_display_jamais_flop():
    # C'est la garantie demandée (09/2026) : le mot "Flop" ne doit JAMAIS
    # apparaître, ni dans l'appli interactive ni dans les rapports exportés
    # -- mal interprété par des lecteurs non-spécialistes (agents, direction).
    assert "Flop" not in format_pct_display(10)
    assert "Flop" not in format_pct_display(10, mode="export")
    assert format_pct_display(10, mode="export") == "10%"
    assert format_pct_display(90, mode="export") == "Top 10%"


def test_format_pct_display_valeur_manquante():
    assert format_pct_display(None) == ""
    assert format_pct_display(float("nan")) == ""


# --- find_column_in_df : anti-collision GPS vs 1080 --------------------------

def test_find_column_in_df_ne_confond_pas_vmax_gps_et_vmax_1080():
    df = pd.DataFrame(columns=["Vmax", "Vmax 15m 1080 (m/s)"])
    assert find_column_in_df(df, "Vmax") == "Vmax"
    assert find_column_in_df(df, "Vmax 15m 1080") == "Vmax 15m 1080 (m/s)"


def test_find_column_in_df_colonne_absente():
    df = pd.DataFrame(columns=["Amax"])
    assert find_column_in_df(df, "Colonne Qui Nexiste Pas") is None


# --- is_inverted --------------------------------------------------------------

def test_is_inverted_temps_est_inverse():
    assert is_inverted("Temps sur 10m") is True


def test_is_inverted_force_nest_pas_inverse():
    assert is_inverted("Amax") is False
