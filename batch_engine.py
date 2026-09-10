# -*- coding: utf-8 -*-
"""
batch_engine.py
=================
Génération en lot des rapports de profilage pour plusieurs joueurs à la fois.

PRINCIPE
--------
Le staff choisit un ensemble de KPI (une seule fois) + un ensemble de
joueurs (équipes entières + ajouts individuels), et l'app produit un
rapport par joueur, en respectant pour chacun :
- son propre groupe de référence (recalculé par joueur, cf. stats_engine.resolve_ref_group),
- la liste de KPI demandée, MOINS celles qu'il n'a pas testées (retrait
  automatique — voir le commentaire dans report_prepa.py / report_kine.py),
- ses éventuels réglages déjà sauvegardés (texte d'entretien, évaluations
  staff, thèmes) — pas de re-saisie manuelle nécessaire pour lancer un lot.

Ce module ne connaît rien de Streamlit : il peut être testé/appelé
indépendamment (voir smoke_test_batch.py).
"""
from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import dataclass, field

from config import COL_MAPPING, GROUPES_PREPA, N_REF_MIN
from data_loader import find_column, clean_numeric_value, safe_get
from stats_engine import (
    resolve_ref_group, compute_group_zscores, calculate_percentile, get_value_for_metric,
)
from rapport_charts import create_radar_chart, create_radar_chart_kine
from stats_engine import get_kine_radar_pct
from report_prepa import build_prepa_report, MARQUEUR_RECO
from report_kine import build_kine_report, MARQUEUR_DETAIL_START, MARQUEUR_DETAIL_END
from pdf_export import is_pdf_export_available, html_to_pdf_bytes
from suggestions import get_kpi_auto_fill, auto_forces_faiblesses


@dataclass
class BatchConfig:
    """Paramètres communs à tous les joueurs du lot (identiques à ceux de l'écran interactif)."""
    report_mode: str  # "Préparation Physique" | "Kiné / Prévention" | "Commun (Complet)"
    selected_metrics: set
    use_relative: dict
    niveau_ref: str
    age_range: tuple
    col_age: str | None
    context_test: str = "Pré-saison"
    export_pdf: bool = True
    force_pro_comparison_players: frozenset = frozenset()  # joueurs à toujours comparer à l'équipe PRO (ex: ajouts individuels Elite/Espoir dans un lot PRO)


def _radar_selection_prepa(row, df_session, df_ref, selected_metrics, use_relative, find_col_fn):
    labels = sorted(
        m for m in selected_metrics
        if m in GROUPES_PREPA.get("Force", []) or m in GROUPES_PREPA.get("Puissance", []) or m in GROUPES_PREPA.get("Saut", [])
    )[:8]
    radar_labels, radar_values = [], []
    for label in labels:
        col = find_col_fn(df_session, label)
        use_rel = use_relative.get(label, False)
        value = get_value_for_metric(row, df_session, col, use_rel) if col else None
        if value is None:
            continue
        _, pct = calculate_percentile(df_ref, col, value, use_rel)
        if pct is not None:
            radar_labels.append(label.replace("(G)", "").replace("(D)", "").strip())
            radar_values.append(pct)
    return radar_labels, radar_values


def _radar_selection_kine(row, df_session, df_ref, selected_metrics, use_relative, find_col_fn):
    biodex_bases = {"Q Conc 60°", "Q Conc 240°", "IJ Conc 60°", "IJ Conc 240°", "IJ Exc 30°"}
    bases = set()
    for m in selected_metrics:
        if "(G)" in m or "(D)" in m:
            base = m.replace("(G)", "").replace("(D)", "").strip()
            if base not in biodex_bases:
                bases.add(base)
    labels = sorted(bases)[:8]
    radar_labels, radar_g, radar_d = [], [], []
    for base in labels:
        col_g, col_d = find_col_fn(df_session, f"{base} (G)"), find_col_fn(df_session, f"{base} (D)")
        v_g = get_value_for_metric(row, df_session, col_g, use_relative.get(f"{base} (G)", False)) if col_g else None
        v_d = get_value_for_metric(row, df_session, col_d, use_relative.get(f"{base} (D)", False)) if col_d else None
        if v_g is None and v_d is None:
            continue
        p_g = get_kine_radar_pct(f"{base} (G)", v_g, df_ref, col_g, use_relative.get(f"{base} (G)", False), row)
        p_d = get_kine_radar_pct(f"{base} (D)", v_d, df_ref, col_d, use_relative.get(f"{base} (D)", False), row)
        radar_labels.append(base)
        radar_g.append(p_g)
        radar_d.append(p_d)
    return radar_labels, radar_g, radar_d


def build_report_for_player(
    player: str, df_session, df_full, cfg: BatchConfig, saved_data_for_player: dict,
    photo_b64: str = "", logo_b64: str = "", logo_ext: str = "png",
) -> tuple[str, str]:
    """
    Construit le rapport HTML complet d'un joueur pour la configuration
    de lot donnée. Retourne (nom_fichier_sans_extension, html).
    """
    df_team_rows = df_session[df_session["Joueur"] == player]
    if df_team_rows.empty:
        raise ValueError(f"Joueur introuvable dans la session sélectionnée : {player}")
    row = df_team_rows.iloc[0]

    col_poste = COL_MAPPING["Poste"]
    p_age = clean_numeric_value(row.get("Age"), "Age")
    anthro = {"Age": int(p_age) if p_age is not None else "-", "Taille": safe_get(row, "Taille (cm)"), "Poids": safe_get(row, "Poids (kg)")}
    # "PositionPrincipale" (poste précis, ex: "DLG") en 1er choix, puis
    # COL_MAPPING["Poste"] (ancienne colonne "Position", absente depuis le
    # passage à Poste/PositionPrincipale/PositionSecondaire) en repli --
    # même correctif que rapport_page.py, ici pour la génération en lot.
    poste = safe_get(row, "PositionPrincipale")
    if poste == "-":
        poste = safe_get(row, col_poste)
    if poste == "-" and "Poste" in row.index:
        poste = safe_get(row, "Poste")
    lateralite = safe_get(row, "Latéralité")

    min_age_file = int(df_session[cfg.col_age].min(skipna=True)) if cfg.col_age and df_session[cfg.col_age].notna().any() else 14
    max_age_file = int(df_session[cfg.col_age].max(skipna=True)) if cfg.col_age and df_session[cfg.col_age].notna().any() else 35
    if min_age_file >= max_age_file:
        max_age_file = min_age_file + 1

    if player in cfg.force_pro_comparison_players:
        # Joueur ajouté individuellement au lot (ex: Elite/Espoir surclassé) :
        # comparé à l'équipe PRO plutôt qu'à sa propre équipe, quel que soit
        # le niveau de référence choisi pour le reste du lot.
        df_ref = df_session[df_session["Equipe"] == "PRO"]
        if cfg.col_age and (cfg.age_range[0] > min_age_file or cfg.age_range[1] < max_age_file):
            df_ref = df_ref[(df_ref[cfg.col_age] >= cfg.age_range[0]) & (df_ref[cfg.col_age] <= cfg.age_range[1])]
        n_ref = len(df_ref)
        if n_ref < N_REF_MIN:
            # Repli : pas assez de PRO dans la fenêtre d'âge -> PRO entier sans filtre d'âge.
            df_ref = df_session[df_session["Equipe"] == "PRO"]
            n_ref = len(df_ref)
        ref_label = "Équipe PRO"
    else:
        df_ref, ref_label, n_ref = resolve_ref_group(
            cfg.niveau_ref, df_session, row, cfg.age_range, cfg.col_age, col_poste, min_age_file, max_age_file, N_REF_MIN,
        )
    ref_group_label = f"{ref_label} (n={n_ref})"

    groupes_pour_zscores = {**GROUPES_PREPA}
    from config import GROUPES_KINE
    groupes_pour_zscores.update(GROUPES_KINE)
    comp_zscores = compute_group_zscores(df_session, df_ref, row, groupes_pour_zscores, cfg.selected_metrics, cfg.use_relative, find_column)

    # Réglages déjà sauvegardés pour ce joueur/session (stratégies + thèmes -- texte libre du staff).
    staff_evals = saved_data_for_player.get("staff_evals", {})
    themes = saved_data_for_player.get("themes", [])
    strat_salle = saved_data_for_player.get("strat_salle", "")
    strat_terrain = saved_data_for_player.get("strat_terrain", "")
    entretien_date = saved_data_for_player.get("entretien_date", "")
    rdv_date = saved_data_for_player.get("rdv_date", "")
    antecedents = saved_data_for_player.get("antecedents", "")
    leg_overrides = saved_data_for_player.get("leg_overrides")

    # POINTS FORTS / AXES DE TRAVAIL : 100% automatiques (cf. rapport_page.py
    # et suggestions.auto_forces_faiblesses) -- calculés à partir des
    # résultats de CE joueur, jamais lus depuis une saisie sauvegardée.
    ff = auto_forces_faiblesses(row, df_full, df_ref, cfg.selected_metrics, cfg.use_relative)
    dominant, weak = ff["dominant_text"], ff["weak_text"]

    # AUTO-REMPLISSAGE DES STRATÉGIES EN LOT : si le staff n'a RIEN sauvegardé
    # pour ce joueur (cas fréquent en génération en lot sur toute une équipe),
    # on reprend le plan d'individualisation. Une valeur déjà sauvegardée par
    # le staff n'est JAMAIS écrasée : l'auto-remplissage ne comble que les
    # champs vides.
    kpi_auto = get_kpi_auto_fill(player, weak)
    if kpi_auto:
        if not strat_salle:
            strat_salle = kpi_auto["strat_salle"]
        if not strat_terrain:
            strat_terrain = kpi_auto["strat_terrain"]

    common_args = dict(
        row=row, df_ref=df_ref, df_full=df_full, poste=poste, lateralite=lateralite, anthro=anthro,
        selected_metrics=cfg.selected_metrics, use_relative=cfg.use_relative,
        themes=themes, dominant=dominant, weak=weak, strat_salle=strat_salle, strat_terrain=strat_terrain,
        photo_b64=photo_b64, logo_b64=logo_b64, logo_ext=logo_ext, staff_evals=staff_evals,
        current_session=None, df_prev_session=None, rdv_date=rdv_date, entretien_date=entretien_date,
        context_test=cfg.context_test, ref_group_label=ref_group_label, comp_zscores=comp_zscores,
    )

    if cfg.report_mode == "Préparation Physique":
        radar_labels, radar_values = _radar_selection_prepa(row, df_session, df_ref, cfg.selected_metrics, cfg.use_relative, find_column)
        html = build_prepa_report(player, radar_labels=radar_labels, radar_values=radar_values, groupes_prepa=GROUPES_PREPA, **common_args)
    elif cfg.report_mode == "Kiné / Prévention":
        radar_labels, radar_g, radar_d = _radar_selection_kine(row, df_session, df_ref, cfg.selected_metrics, cfg.use_relative, find_column)
        html = build_kine_report(player, radar_labels=radar_labels, radar_values=radar_g, antecedents=antecedents,
                                  leg_overrides=leg_overrides, radar_vals_d=radar_d, **common_args)
    else:
        radar_labels_p, radar_values_p = _radar_selection_prepa(row, df_session, df_ref, cfg.selected_metrics, cfg.use_relative, find_column)
        radar_labels_k, radar_g, radar_d = _radar_selection_kine(row, df_session, df_ref, cfg.selected_metrics, cfg.use_relative, find_column)
        html_prepa = build_prepa_report(player, radar_labels=radar_labels_p, radar_values=radar_values_p, groupes_prepa=GROUPES_PREPA, is_commun=True, **common_args)
        html_kine = build_kine_report(player, radar_labels=radar_labels_k, radar_values=radar_g, antecedents=antecedents,
                                       leg_overrides=leg_overrides, radar_vals_d=radar_d, is_commun=True, **common_args)
        parts_prepa = html_prepa.split(MARQUEUR_RECO)
        parts_kine = html_kine.split(MARQUEUR_DETAIL_START)[1].split(MARQUEUR_DETAIL_END)[0]
        html = parts_prepa[0] + parts_kine + MARQUEUR_RECO + parts_prepa[1]

    return f"Profilage_{player.replace(' ', '_')}", html


def build_batch_zip(
    players: list[str], df_session, df_full, cfg: BatchConfig, saved_data_all: dict,
    key_suffix_fn, progress_callback=None, photo_lookup_fn=None, logo=("", "png"),
) -> tuple[bytes, list[str]]:
    """
    Génère un ZIP contenant un PDF (ou HTML si PDF indisponible) par joueur.
    `key_suffix_fn(player)` doit retourner la clé utilisée dans saved_data_all
    (ex: f"{player}_{session}"), pour retrouver les réglages déjà sauvegardés.
    `photo_lookup_fn(player)` retourne le base64 de la photo du joueur (ou "").
    Retourne (contenu_zip, liste_erreurs).
    """
    logo_b64, logo_ext = logo
    pdf_ok = cfg.export_pdf and is_pdf_export_available()
    errors = []
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, player in enumerate(players):
            if progress_callback:
                progress_callback(i, len(players), player)
            try:
                saved_for_player = saved_data_all.get(key_suffix_fn(player), {})
                photo_b64 = photo_lookup_fn(player) if photo_lookup_fn else ""
                filename, html = build_report_for_player(
                    player, df_session, df_full, cfg, saved_for_player,
                    photo_b64=photo_b64, logo_b64=logo_b64, logo_ext=logo_ext,
                )
                if pdf_ok:
                    try:
                        pdf_bytes = html_to_pdf_bytes(html)
                        zf.writestr(f"{filename}.pdf", pdf_bytes)
                    except Exception as e:
                        # Repli HTML pour CE joueur si la conversion PDF échoue,
                        # sans faire échouer tout le lot.
                        zf.writestr(f"{filename}.html", html)
                        errors.append(f"{player} : PDF a échoué ({e}), HTML fourni à la place.")
                else:
                    zf.writestr(f"{filename}.html", html)
            except Exception as e:
                errors.append(f"{player} : échec de génération ({e}).")

    if progress_callback:
        progress_callback(len(players), len(players), "Terminé")

    return buf.getvalue(), errors
