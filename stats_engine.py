# -*- coding: utf-8 -*-
"""
stats_engine.py
================
Calculs statistiques utilisés pour situer un joueur par rapport à un groupe
de référence : percentile, z-score, évaluation automatique par rapport aux
normes du staff.

RAPPEL MÉTHODOLOGIQUE (à garder en tête pour le comité de pilotage / tes
articles) :
- Le **percentile** et le **z-score** sont calculés sur la distribution
  réelle du groupe de référence sélectionné (club, équipe, poste...). Ce
  sont des indicateurs *relatifs*, dépendants de la taille et de la
  composition de l'échantillon (n). Avec n < 8, la variance estimée est peu
  fiable → l'app avertit et propose un repli automatique vers un groupe
  plus large (cf. `N_REF_MIN` dans config.py).
- La **norme** (NORMES_ABSOLUES / NORMES_RELATIVES) est un repère
  opérationnel fixé par le staff, pas une valeur calibrée statistiquement.
  Le statut "Acquis / Proche / Non Acquis" doit être présenté comme un
  repère pédagogique, pas comme un résultat inférentiel.
- Différence solide vs tendance : avec de petits effectifs (souvent le cas
  ici : un groupe de comparaison par poste peut être n=5-10), privilégie la
  taille d'effet (le z-score en est une, au signe près) plutôt qu'un
  jugement binaire sur un seuil de percentile arbitraire.
"""
from __future__ import annotations

import pandas as pd

from config import NORMES_ABSOLUES, NORMES_RELATIVES, DARK, GREEN, SDR_RED, UNITS
from data_loader import is_inverted, clean_numeric_value


def get_column_series(df: pd.DataFrame, col: str, use_rel: bool = False) -> pd.Series | None:
    """
    Retourne la série de valeurs valides (non NaN) d'une colonne, déjà
    nettoyée en amont par data_loader.load_and_clean_excel.
    Si `use_rel=True`, on ramène chaque valeur au poids (valeur relative /kg).

    NOTE PERF : contrairement à l'ancienne version, on n'appelle plus
    pd.to_numeric ici — le DataFrame est déjà propre. Ça évite de refaire
    ce travail à chaque carte affichée (avant : recalculé pour chaque
    joueur x chaque métrique x chaque rerun Streamlit).
    """
    if col is None or col not in df.columns:
        return None
    series = df[col]
    if use_rel and "Poids (kg)" in df.columns:
        weights = df["Poids (kg)"]
        series = series / weights
    return series.dropna()


def calculate_percentile(df_ref: pd.DataFrame, col: str, value, use_rel: bool = False):
    """
    Retourne (moyenne_du_groupe, percentile_du_joueur).
    Le percentile est la proportion du groupe de référence que le joueur
    dépasse (ou dont il fait mieux, pour les métriques inversées comme un
    temps de sprint).
    """
    if col is None or value is None:
        return None, None
    series = get_column_series(df_ref, col, use_rel)
    if series is None or series.empty:
        return None, None

    if "Ratio Squeeze" in col:
        # Cas particulier : l'optimum est 1.0 (équilibre ADD/ABD), pas un extrême.
        d_all = (series - 1.0).abs()
        d_val = abs(value - 1.0)
        pct = (d_all >= d_val).mean() * 100
        return series.mean(), pct

    inverted = is_inverted(col)
    pct = (series >= value).mean() * 100 if inverted else (series <= value).mean() * 100
    return series.mean(), pct


def calculate_zscore(df_ref: pd.DataFrame, col: str, value, use_rel: bool = False):
    """
    Z-score du joueur par rapport au groupe de référence : (valeur - moyenne) / écart-type.
    Retourne None si l'échantillon est trop petit (< 2) pour estimer un écart-type.
    Pour les métriques inversées, le signe est retourné pour que "positif = mieux" partout.
    """
    if col is None or value is None:
        return None
    series = get_column_series(df_ref, col, use_rel)
    if series is None or series.empty or len(series) < 2:
        return None
    mean_val = series.mean()
    std_val = series.std()
    if std_val == 0:
        return 0
    z = (value - mean_val) / std_val
    if "Ratio Squeeze" in col:
        return -abs(z)
    if is_inverted(col):
        z = -z
    return z


def get_value_for_metric(row, df: pd.DataFrame, col: str, use_rel: bool):
    """Valeur (brute ou relative au poids) d'une métrique pour une ligne joueur donnée."""
    val = clean_numeric_value(row.get(col), col)
    if use_rel and val is not None:
        w = clean_numeric_value(row.get("Poids (kg)"), "Poids (kg)")
        if w and w > 0:
            val = val / w
        else:
            val = None
    return val


def get_norm_info(label: str, value, use_rel: bool = False, df_ref: pd.DataFrame = None, col: str = None):
    """
    Retourne (texte de la norme, couleur) pour affichage sur une carte métrique.

    Si aucune norme fixe n'est définie pour cette métrique (cas des métriques
    retirées de config.py car jugées non pertinentes après vérification sur
    les données réelles — ex: Squat belt, Amax, Dmax — ou des nouvelles
    métriques comme le sprint 1080/15m et les sites ISAK), l'objectif devient
    dynamiquement la MOYENNE du groupe de référence actuellement sélectionné
    par le staff dans la sidebar (`df_ref`) : au-dessus de la moyenne = dans
    l'objectif, en dessous = pas dans l'objectif. Ça s'adapte automatiquement
    au niveau comparé (PRO, Elite, U17...) plutôt que d'imposer un seuil
    unique à tout le monde.
    """
    norm_dict = NORMES_RELATIVES if use_rel else NORMES_ABSOLUES
    label_clean = label.replace("(G)", "").replace("(D)", "").strip()
    key = next((k for k in norm_dict if k in label_clean), None)

    if key is None or value is None:
        if key is None and value is not None and df_ref is not None and col is not None:
            series = get_column_series(df_ref, col, use_rel)
            if series is not None and len(series) >= 2:
                mean_val = series.mean()
                inverted = is_inverted(label)
                txt = f"{'<' if inverted else '>'} {mean_val:.1f} (grp)"
                ok = (value <= mean_val) if inverted else (value >= mean_val)
                return txt, (GREEN if ok else SDR_RED)
        return "-", DARK
    norm = norm_dict[key]
    inverted = is_inverted(label)

    if isinstance(norm, list):
        low, high = norm
        txt = f"{low} - {high}"
        ok = low <= value <= high
    else:
        txt = f"< {norm}" if inverted else f"> {norm}"
        ok = (value <= norm) if inverted else (value >= norm)
    return txt, (GREEN if ok else SDR_RED)


def get_kine_radar_pct(label: str, val, df_ref: pd.DataFrame, col: str, use_rel: bool, row_data) -> float:
    """% par rapport à l'objectif pour le radar kiné (borné entre 50% et 150%)."""
    if val is None:
        return 0
    label_clean = label.replace("(G)", "").replace("(D)", "").strip()
    norm_dict = NORMES_RELATIVES if use_rel else NORMES_ABSOLUES
    target = norm_dict.get(label_clean)

    if target is None:
        series = get_column_series(df_ref, col, use_rel)
        target = series.median() if series is not None and not series.empty else 0

    if target == 0:
        return 0

    cible_brute = target * row_data.get("Poids (kg)", 1) if use_rel else target
    if is_inverted(label):
        pct = (cible_brute / val) * 100
    else:
        pct = (val / cible_brute) * 100
    return max(50, min(pct, 150))


def auto_eval_metric(label: str, value, pct, use_rel: bool = False, df_ref: pd.DataFrame = None, col: str = None):
    """
    Statut auto ("Acquis" / "Proche" / "Non Acquis") + texte d'objectif,
    proposé par défaut au staff (qui peut le modifier manuellement dans l'UI).
    """
    if value is None:
        return "Non Acquis", ""
    norm_dict = NORMES_RELATIVES if use_rel else NORMES_ABSOLUES
    label_clean = label.replace("(G)", "").replace("(D)", "").strip()
    key = next((k for k in norm_dict if k in label_clean), None)
    unit = UNITS.get(label, "")

    if not key:
        # NOUVEAU : pas de norme fixe pour cette métrique -> repli sur la
        # moyenne du groupe de référence (même critère que get_norm_info,
        # pour que la couleur de la carte et ce badge soient toujours cohérents).
        if df_ref is not None and col is not None:
            series = get_column_series(df_ref, col, use_rel)
            if series is not None and len(series) >= 2:
                mean_val = series.mean()
                inverted = is_inverted(label)
                ok = (value <= mean_val) if inverted else (value >= mean_val)
                if ok:
                    return "Acquis", ""
                return "Non Acquis", f"Cible : {'<' if inverted else '>'} {mean_val:.1f} (grp) {unit}"
        return "Non Acquis", ""

    norm = norm_dict[key]
    inverted = is_inverted(label)
    if isinstance(norm, list):
        if norm[0] <= value <= norm[1]:
            return "Acquis", ""
        return ("Proche" if norm[0] * 0.95 <= value else "Non Acquis"), f"Cible: {norm[0]}-{norm[1]} {unit}"

    if (not inverted and value >= norm * 0.95) or (inverted and value <= norm * 1.05):
        acquis = (not inverted and value >= norm) or (inverted and value <= norm)
        return ("Acquis" if acquis else "Proche"), ""
    return "Non Acquis", f"Cible: {'<' if inverted else '>'} {norm} {unit}"


def get_ref_dataframe(niveau: str, df_base, r, a_range, col_age, col_poste, min_age_file, max_age_file):
    """
    Construit le groupe de référence pour un joueur donné, selon le niveau
    hiérarchique choisi (Club entier / Équipe / Poste large / Position précise)
    et la fenêtre d'âge. Fonction partagée entre le flux interactif (un
    joueur à la fois) et la génération en lot (batch_engine.py), pour que
    les deux utilisent EXACTEMENT la même définition du groupe de comparaison.
    """
    d = df_base.copy()
    lbl = ""
    if niveau == "Club entier":
        lbl = "Club"
    elif niveau == "Équipe":
        d = d[d["Equipe"] == r.get("Equipe")]
        lbl = f"Équipe {r.get('Equipe')}"
    elif niveau == "Poste large":
        d = d[d[col_poste] == r.get(col_poste)]
        lbl = f"Poste {r.get(col_poste)}"
    elif niveau == "Position précise":
        p = r.get("Position", r.get(col_poste))
        d = d[d["Position"] == p] if "Position" in d.columns else d[d[col_poste] == p]
        lbl = f"Position {p}"
    if col_age and (a_range[0] > min_age_file or a_range[1] < max_age_file):
        d = d[(d[col_age] >= a_range[0]) & (d[col_age] <= a_range[1])]
        lbl += f", {a_range[0]}-{a_range[1]} ans"
    return d, lbl


def resolve_ref_group(niveau, df_session, row, age_range, col_age, col_poste, min_age_file, max_age_file, n_ref_min):
    """
    Applique get_ref_dataframe() puis le repli automatique en cascade si
    l'effectif est trop faible (< n_ref_min). Retourne (df_ref, label_final, n_ref).
    Centralise une logique auparavant seulement présente dans app.py, pour
    que le batch obtienne le même comportement de repli que le mode interactif.
    """
    df_ref, ref_label = get_ref_dataframe(niveau, df_session, row, age_range, col_age, col_poste, min_age_file, max_age_file)
    n_ref = len(df_ref)
    if n_ref >= n_ref_min:
        return df_ref, ref_label, n_ref

    niveaux_repli = ["Club entier", "Équipe", "Poste large", "Position précise"]
    idx_actuel = niveaux_repli.index(niveau)
    for i in range(idx_actuel - 1, -1, -1):
        d_repli, l_repli = get_ref_dataframe(niveaux_repli[i], df_session, row, age_range, col_age, col_poste, min_age_file, max_age_file)
        if len(d_repli) >= n_ref_min:
            return d_repli, l_repli, len(d_repli)

    df_ref, ref_label = get_ref_dataframe("Club entier", df_session, row, (min_age_file, max_age_file), col_age, col_poste, min_age_file, max_age_file)
    return df_ref, ref_label, len(df_ref)


def compute_group_zscores(df_session, df_ref, row, groupes: dict, selected_metrics, use_relative: dict, find_column_fn):
    """
    Calcule, pour chaque groupe de métriques (ex: 'Saut', 'Aérobie'...), le
    z-score composite moyen du joueur = moyenne des z-scores des métriques
    sélectionnées de ce groupe qui sont calculables.
    Retourne {groupe: {"score": z_moyen, "count": nb_métriques_utilisées}}.
    """
    comp_zscores = {}
    for group, labels in groupes.items():
        z_list = []
        for label in labels:
            if label not in selected_metrics:
                continue
            col = find_column_fn(df_session, label)
            use_rel = use_relative.get(label, False)
            val = get_value_for_metric(row, df_session, col, use_rel) if col else None
            z = calculate_zscore(df_ref, col, val, use_rel)
            if z is not None:
                z_list.append(z)
        if z_list:
            comp_zscores[group] = {"score": sum(z_list) / len(z_list), "count": len(z_list)}
    return comp_zscores
