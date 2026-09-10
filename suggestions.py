# -*- coding: utf-8 -*-
"""
suggestions.py
================
Suggestion automatique de 3 thématiques de travail prioritaires pour un
joueur, à partir de :
1. son ratio squeeze ADD/ABD (risque pubalgie),
2. ses asymétries G/D (> 15% d'écart),
3. ses percentiles les plus faibles (< 33%) sur les métriques cadrées par
   THEME_MAPPING.

Le staff peut ensuite modifier, compléter ou retirer ces suggestions dans
l'UI : ce module ne fait que proposer un point de départ, il ne décide de
rien à la place du staff.
"""
from __future__ import annotations

import uuid

from config import (
    THEME_MAPPING, PLAYER_KPI_PRIORITAIRE, KPI_WEEKLY_PLAN, KPI_WEEKLY_PLAN_DAYS_ORDER,
    GROUPES_PREPA, GROUPES_KINE, GROUPE_VERS_QUALITE,
)
from data_loader import find_column, clean_numeric_value
from stats_engine import calculate_percentile


def get_theme_suggestions_advanced(row, df) -> list[dict]:
    suggestions = []

    col_ratio = find_column(df, "Ratio Squeeze")
    val_ratio = clean_numeric_value(row.get(col_ratio), col_ratio) if col_ratio else None
    if val_ratio and (val_ratio < 0.85 or val_ratio > 1.15):
        suggestions.append({
            "etat": "Prévention de", "qualite": "Blessure (Ratio)", "zone": "Hanche / Pubis", "score": 100,
            "detail": f"Ratio squeeze {val_ratio:.2f} (hors zone 0.85–1.15)",
        })

    for base in ["Adducteurs", "Abducteurs", "Nordic Ischio", "Inverseur", "Everseur"]:
        col_g = find_column(df, f"{base} (G)")
        col_d = find_column(df, f"{base} (D)")
        v_g = clean_numeric_value(row.get(col_g), col_g) if col_g else None
        v_d = clean_numeric_value(row.get(col_d), col_d) if col_d else None
        if v_g and v_d and max(v_g, v_d) > 0:
            diff = abs(v_g - v_d) / max(v_g, v_d) * 100
            if diff >= 15:
                suggestions.append({
                    "etat": "Rééquilibrage de", "qualite": "Force", "zone": base, "score": diff + 50,
                    "detail": f"Asymétrie {diff:.0f}% (G {v_g:.1f} / D {v_d:.1f})",
                })

    for label, (qualite, zone) in THEME_MAPPING.items():
        col = find_column(df, label)
        val = clean_numeric_value(row.get(col), col) if col else None
        if val is None:
            continue
        _, pct = calculate_percentile(df, col, val)
        if pct is not None and pct < 33:
            suggestions.append({
                "etat": "En manque de", "qualite": qualite, "zone": zone, "score": 100 - pct,
                "detail": f"{label} : percentile {round(pct)}% vs groupe",
            })

    seen, uniq = set(), []
    for s in sorted(suggestions, key=lambda x: x["score"], reverse=True):
        key = (s["etat"], s["qualite"], s["zone"])
        if key not in seen:
            seen.add(key)
            uniq.append({
                "id": str(uuid.uuid4()), "etat": s["etat"], "qualite": s["qualite"], "zone": s["zone"],
                "objectif": "", "freq": "1x/sem", "moment": "Pré séance", "detail": s.get("detail", ""),
            })
    return uniq[:3]


def auto_point_fort(row, df_full, df_ref, selected_metrics: set, use_relative: dict) -> str:
    """
    Propose une phrase simple mettant en avant la meilleure QUALITÉ du
    joueur (Force, Vitesse, Endurance...) plutôt qu'une métrique précise
    avec sa valeur exacte — plus adapté à un point fort d'entretien qu'un
    résultat de test brut. Basé sur le groupe de la métrique où le joueur a
    le meilleur percentile vs le groupe de référence. Purement indicatif :
    à valider/reformuler par le staff avant sauvegarde.
    """
    label_to_group = {}
    for grp, labels in {**GROUPES_PREPA, **GROUPES_KINE}.items():
        if grp not in GROUPE_VERS_QUALITE:
            continue  # groupe sans qualité associée (ex: ISAK) -> jamais retenu comme "point fort"
        for lbl in labels:
            label_to_group[lbl] = grp

    best_label, best_pct = None, -1
    for label in selected_metrics:
        grp = label_to_group.get(label)
        if grp is None:
            continue  # métrique hors des groupes qualifiés (ex: ISAK, Ratio Mixte)
        col = find_column(df_full, label)
        if not col:
            continue
        use_rel = use_relative.get(label, False)
        val = clean_numeric_value(row.get(col), col)
        if val is None:
            continue
        if use_rel:
            w = clean_numeric_value(row.get("Poids (kg)"), "Poids (kg)")
            if w and w > 0:
                val = val / w
            else:
                continue
        _, pct = calculate_percentile(df_ref, col, val, use_rel)
        if pct is not None and pct > best_pct:
            best_pct = pct
            best_label = label
    if best_label is None:
        return ""

    return GROUPE_VERS_QUALITE[label_to_group[best_label]]


def auto_forces_faiblesses(row, df_full, df_ref, selected_metrics: set, use_relative: dict,
                            seuil_fort: int = 66, seuil_faible: int = 33) -> dict:
    """
    Calcule 100% AUTOMATIQUEMENT les points forts et axes de travail d'un
    joueur, à partir de ses résultats (percentile de chaque test sélectionné
    vs le groupe de référence) -- AUCUNE saisie humaine n'intervient ici,
    sur demande explicite du département performance (seules Stratégie
    Salle et Stratégie Terrain restent du texte libre rempli par le staff).

    Principe volontaire du seuillage : on "flashe" tout ce qui n'est pas
    franchement bon (percentile < seuil_fort = 66, soit sous le tiers
    "Bon"/"Top"), MÊME les écarts mineurs (33-66%) qui ne sont pas
    alarmants en soi -- charge ensuite au préparateur physique de juger,
    joueur par joueur, si c'est pertinent à travailler ou pas. Rien n'est
    caché sous prétexte que ce n'est "pas si grave".

    Retourne :
        {
            "forts":   [{"label", "pct"}, ...],  # pct >= seuil_fort (66)
            "moyens":  [{"label", "pct"}, ...],  # seuil_faible <= pct < seuil_fort
            "faibles": [{"label", "pct"}, ...],  # pct < seuil_faible (33)
            "dominant_text": str,  # phrase prête pour le rapport (Points forts)
            "weak_text": str,      # phrase prête pour le rapport (Axes de travail)
        }
    """
    resultats = []
    for label in selected_metrics:
        col = find_column(df_full, label)
        if not col:
            continue
        use_rel = use_relative.get(label, False)
        val = clean_numeric_value(row.get(col), col)
        if val is None:
            continue
        if use_rel:
            w = clean_numeric_value(row.get("Poids (kg)"), "Poids (kg)")
            if w and w > 0:
                val = val / w
            else:
                continue
        _, pct = calculate_percentile(df_ref, col, val, use_rel)
        if pct is None:
            continue
        resultats.append({"label": label, "pct": round(pct)})

    forts = sorted((r for r in resultats if r["pct"] >= seuil_fort), key=lambda r: -r["pct"])
    moyens = sorted((r for r in resultats if seuil_faible <= r["pct"] < seuil_fort), key=lambda r: r["pct"])
    faibles = sorted((r for r in resultats if r["pct"] < seuil_faible), key=lambda r: r["pct"])

    if forts:
        dominant_text = ", ".join(f"{r['label']} (Top {max(1, 100 - r['pct'])}%)" for r in forts[:4]) + "."
    else:
        dominant_text = "Aucun test au-dessus du seuil « Bon » (Top 34%) sur cette session — profil homogène, sans point fort net vs le groupe de référence."

    axes = faibles + moyens
    if axes:
        weak_text = ", ".join(f"{r['label']} ({r['pct']}%)" for r in axes[:5]) + "."
    else:
        weak_text = "Aucun axe de travail détecté sur les tests sélectionnés pour cette session."

    return {"forts": forts, "moyens": moyens, "faibles": faibles, "dominant_text": dominant_text, "weak_text": weak_text}


def resolve_kpi_for_player(player_name: str, current_weak_text: str = "") -> str | None:
    """
    Détermine le KPI à utiliser pour les auto-remplissages : priorité au
    texte ACTUELLEMENT saisi dans "Axes d'amélioration" s'il correspond
    exactement à l'une des 5 catégories connues (respecte une modification
    manuelle du staff), sinon repli sur le KPI prioritaire par défaut du
    joueur (config.PLAYER_KPI_PRIORITAIRE).
    """
    text = (current_weak_text or "").strip()
    if text in KPI_WEEKLY_PLAN:
        return text
    # Lookup insensible aux espaces superflus : config.PLAYER_KPI_PRIORITAIRE
    # a eu au moins 2 entrées avec un espace en début de nom (pour matcher un
    # espace parasite alors présent dans le fichier Excel/Sheet) -- mais le
    # chargement des données (utils.load_data) nettoie déjà ces noms avec
    # .strip(), donc la clé espacée ne matchait plus jamais le nom réel du
    # joueur une fois les données chargées. On normalise des deux côtés pour
    # ne plus jamais dépendre de l'orthographe exacte (espaces) du fichier.
    if player_name in PLAYER_KPI_PRIORITAIRE:
        return PLAYER_KPI_PRIORITAIRE[player_name]
    target = str(player_name).strip().lower()
    for k, v in PLAYER_KPI_PRIORITAIRE.items():
        if str(k).strip().lower() == target:
            return v
    return None


def get_kpi_auto_fill(player_name: str, current_weak_text: str = ""):
    """
    Retourne {"kpi": str, "weak": str, "strat_salle": str, "strat_terrain": str}
    à partir du plan d'individualisation (config.PLAYER_KPI_PRIORITAIRE +
    config.KPI_WEEKLY_PLAN), ou None si aucun KPI n'a pu être déterminé
    (cf. le README pour la liste des joueurs non résolus à compléter
    manuellement dans config.py).

    Stratégie Salle et Stratégie Terrain reçoivent EXACTEMENT le même texte
    (les recommandations du département performance pour ce KPI) — sur
    demande explicite, plus de répartition par mot-clé Vélo/HIIT.
    """
    kpi = resolve_kpi_for_player(player_name, current_weak_text)
    if not kpi:
        return None
    plan_text = "Se référer aux recommandations du Département Performance."
    return {"kpi": kpi, "weak": kpi, "strat_salle": plan_text, "strat_terrain": plan_text}