# -*- coding: utf-8 -*-
"""
rapport_page.py
================
Onglet RAPPORT d'appV3 -- integration du module de rapport de profilage
(anciennement l'application independante 'reims_profiling').

Ce fichier est une adaptation MECANIQUE de reims_profiling/app.py : tout le
contenu (UI, logique) est identique, seuls 2 changements ont ete faits :
  1. Le tout est enveloppe dans show_rapport_page(df), appelee depuis un
     nouvel onglet de profiling.py, au lieu d'etre un script Streamlit
     autonome (st.set_page_config retire : deja fait par main.py).
  2. Le chargement Excel local (locate_excel_file/load_and_clean_excel) est
     remplace par load_and_clean_from_dataframe(df) : le DataFrame vient du
     Google Sheet deja charge par appV3, plus besoin de copier/mettre a jour
     un fichier Excel a la main.
  3. st.sidebar.* -> st.* (appV3 n'utilise pas de sidebar ailleurs dans
     l'app -- les controles de cet onglet restent dans la zone principale,
     comme les autres onglets).
  4. "Points forts" / "Axes d'amélioration" : sur demande du département
     performance, ces deux champs sont passés de texte libre (rempli par le
     staff) à un calcul 100% automatique à partir des résultats du joueur
     (voir suggestions.auto_forces_faiblesses) -- seules Stratégie Salle et
     Stratégie Terrain restent du texte libre.
Tous les modules qu'il utilise (config.py, data_loader.py, stats_engine.py,
rapport_charts.py, html_components.py, suggestions.py, report_prepa.py,
report_kine.py, persistence.py, pdf_export.py, batch_engine.py, planning.py)
sont des copies A L'IDENTIQUE de reims_profiling -- rien n'y a ete modifie,
hormis le renommage charts.py -> rapport_charts.py (collision avec le
charts.py Plotly de appV3) et l'ajout de load_and_clean_from_dataframe dans
data_loader.py (fonction neuve, additive).
"""
from __future__ import annotations

from __future__ import annotations
import base64
import os
import uuid
from datetime import datetime
import pandas as pd
import streamlit as st
from config import (
    SDR_RED, GREEN, BLUE_ELITE, DARK,
    COL_MAPPING, GROUPES_PREPA, GROUPES_KINE, KINE_LABELS, UNITS,
    ETATS_ACTIONS, QUALITES_PHYSIQUES, ZONES_CIBLEES, BIODEX_TARGETS, BIODEX_CONFIG,
    N_REF_MIN, GREEN_TEXT, BLUE_ELITE_TEXT,
)
from data_loader import (
    find_column, clean_numeric_value, locate_excel_file, load_and_clean_excel, safe_get,
)
from stats_engine import (
    calculate_percentile, calculate_zscore, get_value_for_metric, auto_eval_metric,
    get_kine_radar_pct, compute_group_zscores,
)
from rapport_charts import create_radar_chart, create_radar_chart_kine
from html_components import get_metric_card_html, get_theme_card_html, get_trend_html
from suggestions import get_theme_suggestions_advanced, get_kpi_auto_fill, auto_forces_faiblesses
from report_prepa import build_prepa_report, MARQUEUR_RECO
from report_kine import build_kine_report, MARQUEUR_DETAIL_START, MARQUEUR_DETAIL_END
from persistence import load_profiling_data_raw, save_profiling_data, PLANNING_FILE_PATH
from pdf_export import is_pdf_export_available, html_to_pdf_bytes
from batch_engine import BatchConfig, build_batch_zip
from planning import build_kpi_department_plan_html, build_kpi_focus_plan_html
from data_loader import is_inverted
from stats_engine import get_ref_dataframe, resolve_ref_group  # noqa: E402 (import positionné ici volontairement, après calcul de col_age/min_age_file/max_age_file)
from data_loader import find_column as _fc  # noqa (déjà importé, alias explicite pour clarté locale)

from data_loader import load_and_clean_from_dataframe


@st.cache_data(show_spinner="Chargement des données de profilage...")
def _cached_load(file_path: str, mtime: float) -> pd.DataFrame:
    # `mtime` fait partie de la clé de cache : si le fichier Excel est
    # remplacé/mis à jour (nouvelle saison, nouvelle session), le cache est
    # automatiquement invalidé sans qu'il soit nécessaire de relancer l'app.
    return load_and_clean_excel(file_path, sheet_name=EXCEL_SHEET)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_profiling_data(_secrets_marker: str) -> dict:
    # `_secrets_marker` n'est utilisé que pour la clé de cache (permet de
    # forcer un rafraîchissement en changeant sa valeur juste après une
    # sauvegarde réussie, via st.cache_data.clear() ciblé plus bas).
    return load_profiling_data_raw(st.secrets)


@st.cache_data(show_spinner=False)
def _cached_radar_chart(labels: tuple, values: tuple) -> str:
    from rapport_charts import create_radar_chart
    return create_radar_chart(list(labels), list(values))


@st.cache_data(show_spinner=False)
def _cached_radar_chart_kine(labels: tuple, values_g: tuple, values_d: tuple) -> str:
    from rapport_charts import create_radar_chart_kine
    return create_radar_chart_kine(list(labels), list(values_g), list(values_d))


@st.cache_data(show_spinner=False)
def _cached_isak_radar(labels: tuple, values: tuple, max_scale: float) -> str:
    from rapport_charts import create_isak_radar
    return create_isak_radar(list(labels), list(values), max_scale)


@st.cache_data(show_spinner=False)
def _cached_biodex_radar(cats: tuple, vals_l: tuple, vals_r: tuple, vals_norm: tuple) -> str:
    from rapport_charts import create_biodex_radar_matplotlib
    return create_biodex_radar_matplotlib(list(cats), list(vals_l), list(vals_r), list(vals_norm))


@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_planning_data(_secrets_marker: str) -> dict:
    return load_profiling_data_raw(st.secrets, file_path=PLANNING_FILE_PATH)


@st.cache_data(show_spinner=False)
def _get_best_photo_path(player_name: str):
    folder = "Photos"
    if not os.path.exists(folder):
        return None
    from data_loader import remove_accents
    clean_player = remove_accents(player_name).lower()
    player_parts = clean_player.split()
    for f in os.listdir(folder):
        full = os.path.join(folder, f)
        if not os.path.isfile(full):
            continue
        clean_filename = remove_accents(f).lower()
        if all(part in clean_filename for part in player_parts):
            return full
    return None


@st.cache_data(show_spinner=False)
def _img_to_b64(img_path):
    try:
        if not img_path or not os.path.exists(img_path):
            return ""
        with open(img_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def _get_logo_b64():
    return _cached_get_logo_b64()


@st.cache_data(show_spinner=False)
def _cached_get_logo_b64():
    b64 = _img_to_b64("logo_sdr.png")
    if b64:
        return b64, "png"
    b64 = _img_to_b64("logo_sdr.ico")
    return (b64, "x-icon") if b64 else ("", "png")



def _render_report_download_section(pdf_ready, key_prefix="dl"):
    """
    Affiche le résultat du dernier rapport généré (HTML/PDF + aperçu), à
    partir de st.session_state["_last_report_html"] -- factorisé pour être
    appelé à la fois depuis la génération rapide (haut de page) et depuis la
    section détaillée (bas de page) : les deux partagent le même état, donc
    le dernier rapport généré (peu importe lequel des deux boutons a été
    cliqué) s'affiche aux DEUX endroits.

    `key_prefix` DOIT être différent à chaque appel sur une même page (ici :
    appelée deux fois) pour que les widgets (bouton PDF désactivé, case
    aperçu) n'entrent pas en collision d'ID Streamlit.
    """
    if "_last_report_html" not in st.session_state:
        return
    html_report = st.session_state["_last_report_html"]
    p_report = st.session_state["_last_report_player"]

    # POURQUOI ce cache : WeasyPrint est coûteux (plusieurs centaines de ms
    # à quelques secondes selon la taille du rapport). Sans ce cache, le PDF
    # était recalculé DEUX FOIS (bouton téléchargement + onglet aperçu) à
    # CHAQUE rerun Streamlit -- c'est-à-dire à chaque interaction n'importe
    # où dans l'app, pas seulement quand on clique sur "Générer" ou "PDF".
    # On ne recalcule maintenant que si le contenu HTML du rapport a changé.
    pdf_bytes, pdf_error = None, None
    if pdf_ready:
        if st.session_state.get("_last_pdf_source") != html_report:
            try:
                st.session_state["_last_pdf_bytes"] = html_to_pdf_bytes(html_report)
                st.session_state["_last_pdf_error"] = None
            except Exception as e:
                st.session_state["_last_pdf_bytes"] = None
                st.session_state["_last_pdf_error"] = str(e)
            st.session_state["_last_pdf_source"] = html_report
        pdf_bytes = st.session_state["_last_pdf_bytes"]
        pdf_error = st.session_state["_last_pdf_error"]

    b_html, b_pdf = st.columns(2)
    with b_html:
        b64_html = base64.b64encode(html_report.encode("utf-8")).decode("utf-8")
        st.markdown(
            f'<a href="data:text/html;base64,{b64_html}" download="Profilage_{p_report}.html">'
            f'<button style="width:100%; background:{SDR_RED}; color:white; padding:10px 18px; border:none; border-radius:5px; font-weight:bold; cursor:pointer;">📄 TÉLÉCHARGER LE HTML</button></a>',
            unsafe_allow_html=True,
        )
    with b_pdf:
        if pdf_ready:
            if pdf_bytes:
                st.download_button("📑 TÉLÉCHARGER LE PDF", data=pdf_bytes,
                                    file_name=f"Profilage_{p_report}.pdf", mime="application/pdf",
                                    width='stretch', type="primary", key=f"{key_prefix}_pdf_btn_{p_report}")
            else:
                st.error(f"Échec de la génération PDF : {pdf_error}")
        else:
            st.button("📑 PDF indisponible", disabled=True, width='stretch', key=f"{key_prefix}_pdf_disabled_{p_report}")

    show_preview = st.checkbox(
        "Afficher l'aperçu (HTML/PDF) ci-dessous", value=False, key=f"{key_prefix}_show_preview_{p_report}",
        help="Décoché par défaut : afficher l'aperçu renvoie le rapport complet (300-600 Ko) au "
             "navigateur à chaque interaction dans l'app, même sans rapport avec l'aperçu. "
             "Les boutons de téléchargement ci-dessus fonctionnent sans avoir besoin de l'activer.",
    )
    if show_preview:
        tab_html, tab_pdf = st.tabs(["Aperçu HTML", "Aperçu PDF"])
        with tab_html:
            st.components.v1.html(html_report, height=900, scrolling=True)
        with tab_pdf:
            if pdf_ready:
                if pdf_bytes:
                    # <iframe>, pas <embed> : st.components.v1.html rend son
                    # contenu dans un iframe "sandboxé", et Chrome refuse d'y
                    # charger un <embed>/<object> PDF (traité comme un plugin
                    # -> "the frame into which the plugin is loading is
                    # sandboxed", aperçu silencieusement vide). Un <iframe>
                    # pointant vers le même data URI déclenche la visionneuse
                    # PDF native du navigateur à la place, qui elle fonctionne
                    # dans ce contexte.
                    b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
                    st.components.v1.html(
                        f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="850px" style="border:none;"></iframe>',
                        height=870,
                    )
                else:
                    st.error(f"Aperçu PDF indisponible : {pdf_error}")
            else:
                st.caption("Aperçu PDF indisponible dans cet environnement (voir `packages.txt`).")


def _generate_quick_report(p_sel, row, df, df_session, df_ref, ref_group_label, poste, lateralite,
                            anthro, report_mode, GROUPES, antecedents_kine, leg_overrides,
                            sel_session, df_prev_session, saved_data_player):
    """
    Construit le rapport HTML en mode "génération rapide" : TOUS les
    indicateurs disponibles pour ce joueur/session sont automatiquement
    inclus (un indicateur sans donnée n'apparaît simplement pas), avec des
    évaluations/objectifs par défaut (auto_eval_metric) et les variables
    radar par défaut (mêmes 8 premières, triées, que la présélection des
    multiselects de la section détaillée). Aucune case à cocher à ouvrir.

    Reproduit volontairement (sans les widgets Streamlit) la même logique de
    calcul que la section détaillée plus bas -- dupliquée plutôt que
    partagée pour ne pas risquer de casser le flux détaillé existant en le
    réorganisant.
    """
    use_relative = saved_data_player.get("use_relative", {})

    # 1. Sélection automatique : tout indicateur avec une donnée valide pour ce joueur/session.
    selected_metrics = set()
    for grp, lbls in GROUPES.items():
        if report_mode == "Kiné / Prévention" and "Biodex" in grp:
            continue
        for l in lbls:
            c = find_column(df_session, l)
            if c and pd.notna(row.get(c)):
                selected_metrics.add(l)

    # 2. Évaluations par défaut (statut/objectif calculés automatiquement,
    #    ou repris s'ils avaient déjà été sauvegardés pour ce joueur/session).
    staff_evals = {}
    saved_evals = saved_data_player.get("staff_evals", {})
    for group, labels in GROUPES.items():
        for label in labels:
            if label not in selected_metrics:
                continue
            col = find_column(df_session, label)
            use_rel = use_relative.get(label, False)
            v_metric = get_value_for_metric(row, df_session, col, use_rel) if col else None
            _, v_pct = calculate_percentile(df_ref, col, v_metric, use_rel) if col and v_metric is not None else (None, None)
            statut_def, obj_def = auto_eval_metric(label, v_metric, v_pct, use_rel, df_ref=df_ref, col=col)
            saved_eval = saved_evals.get(label, {})
            statut = saved_eval.get("statut", statut_def)
            obj_val = saved_eval.get("objectif", obj_def) if statut != "Acquis" else ""
            delai_val = saved_eval.get("delai", "") if statut != "Acquis" else ""
            staff_evals[label] = {"statut": statut, "objectif": obj_val, "delai": delai_val}

    # 3. Variables radar par défaut (mêmes règles que les multiselects "Choix
    #    radar Prépa/Kiné" de la section détaillée, sans widget : 8 premières triées).
    radar_labels_prepa, radar_values_prepa = [], []
    radar_labels_kine, radar_values_kine, radar_vals_d_kine = [], [], []
    if report_mode in ["Préparation Physique", "Commun (Complet)"]:
        radar_options_prepa = sorted(m for m in selected_metrics if m in GROUPES_PREPA.get("Force", []) or m in GROUPES_PREPA.get("Puissance", []) or m in GROUPES_PREPA.get("Saut", []))
        for label in radar_options_prepa[:8]:
            col = find_column(df_session, label)
            use_rel = use_relative.get(label, False)
            value = get_value_for_metric(row, df_session, col, use_rel) if col else None
            _, pct = calculate_percentile(df_ref, col, value, use_rel) if col and value is not None else (None, None)
            if pct is not None:
                radar_labels_prepa.append(label.replace("(G)", "").replace("(D)", "").strip())
                radar_values_prepa.append(pct)
    if report_mode in ["Kiné / Prévention", "Commun (Complet)"]:
        biodex_bases = ["Q Conc 60°", "Q Conc 240°", "IJ Conc 60°", "IJ Conc 240°", "IJ Exc 30°"]
        base_kine_metrics = set()
        for m in selected_metrics:
            if "(G)" in m or "(D)" in m:
                base = m.replace("(G)", "").replace("(D)", "").strip()
                if base not in biodex_bases:
                    base_kine_metrics.add(base)
        for base in sorted(base_kine_metrics)[:8]:
            col_g, col_d = find_column(df_session, f"{base} (G)"), find_column(df_session, f"{base} (D)")
            v_g = get_value_for_metric(row, df_session, col_g, use_relative.get(f"{base} (G)", False)) if col_g else None
            v_d = get_value_for_metric(row, df_session, col_d, use_relative.get(f"{base} (D)", False)) if col_d else None
            p_g = get_kine_radar_pct(f"{base} (G)", v_g, df_ref, col_g, use_relative.get(f"{base} (G)", False), row)
            p_d = get_kine_radar_pct(f"{base} (D)", v_d, df_ref, col_d, use_relative.get(f"{base} (D)", False), row)
            radar_labels_kine.append(base)
            radar_values_kine.append(p_g)
            radar_vals_d_kine.append(p_d)

    groupes_pour_zscores = {g: l for g, l in GROUPES.items() if not (g == "Ratio Mixte" and report_mode == "Préparation Physique")}
    comp_zscores = compute_group_zscores(df_session, df_ref, row, groupes_pour_zscores, selected_metrics, use_relative, find_column)

    # 4. Points forts / Axes de travail -- même calcul 100% automatique que
    #    la section détaillée (voir suggestions.auto_forces_faiblesses).
    ff = auto_forces_faiblesses(row, df_session, df_ref, selected_metrics, use_relative)
    dominant, weak = ff["dominant_text"], ff["weak_text"]

    # 5. Stratégies : reprises si déjà sauvegardées pour ce joueur/session,
    #    sinon depuis le plan d'individualisation -- jamais inventées.
    kpi_auto = get_kpi_auto_fill(p_sel, weak)
    strat_salle = saved_data_player.get("strat_salle") or (kpi_auto["strat_salle"] if kpi_auto else "")
    strat_terrain = saved_data_player.get("strat_terrain") or (kpi_auto["strat_terrain"] if kpi_auto and report_mode in ["Préparation Physique", "Commun (Complet)"] else "")

    photo_b64 = _img_to_b64(_get_best_photo_path(p_sel))
    logo_b64, logo_ext = _get_logo_b64()

    common_args = dict(
        row=row, df_ref=df_ref, df_full=df, poste=poste, lateralite=lateralite, anthro=anthro,
        selected_metrics=selected_metrics, use_relative=use_relative,
        themes=saved_data_player.get("themes", []), dominant=dominant, weak=weak,
        strat_salle=strat_salle, strat_terrain=strat_terrain,
        photo_b64=photo_b64, logo_b64=logo_b64, logo_ext=logo_ext, staff_evals=staff_evals,
        current_session=sel_session, df_prev_session=df_prev_session,
        rdv_date=saved_data_player.get("rdv_date", ""), entretien_date=saved_data_player.get("entretien_date", ""),
        context_test="Pré-saison", ref_group_label=ref_group_label, comp_zscores=comp_zscores,
    )

    if report_mode == "Préparation Physique":
        return build_prepa_report(p_sel, radar_labels=radar_labels_prepa, radar_values=radar_values_prepa,
                                   groupes_prepa=GROUPES_PREPA, **common_args)
    elif report_mode == "Kiné / Prévention":
        return build_kine_report(p_sel, radar_labels=radar_labels_kine, radar_values=radar_values_kine,
                                  antecedents=antecedents_kine, leg_overrides=leg_overrides,
                                  radar_vals_d=radar_vals_d_kine, **common_args)
    else:
        html_prepa = build_prepa_report(p_sel, radar_labels=radar_labels_prepa, radar_values=radar_values_prepa,
                                         groupes_prepa=GROUPES_PREPA, is_commun=True, **common_args)
        html_kine = build_kine_report(p_sel, radar_labels=radar_labels_kine, radar_values=radar_values_kine,
                                       antecedents=antecedents_kine, leg_overrides=leg_overrides,
                                       radar_vals_d=radar_vals_d_kine, is_commun=True, **common_args)
        parts_prepa = html_prepa.split(MARQUEUR_RECO)
        parts_kine = html_kine.split(MARQUEUR_DETAIL_START)[1].split(MARQUEUR_DETAIL_END)[0]
        return parts_prepa[0] + parts_kine + MARQUEUR_RECO + parts_prepa[1]


def show_rapport_page(df):
    """
    Onglet RAPPORT -- genere les rapports Prepa/Kine/Commun (+ lot + planning).
    `df` : le DataFrame deja charge par appV3 (Google Sheets).
    """
    # st.set_page_config() retiré : déjà appelé une fois par main.py (appV3).
    st.title("Rapport de Profilage Individuel")
    report_mode = st.radio("Type de rapport", ["Préparation Physique", "Kiné / Prévention", "Commun (Complet)"], horizontal=True)
    if report_mode == "Préparation Physique":
        GROUPES = GROUPES_PREPA
    elif report_mode == "Kiné / Prévention":
        GROUPES = GROUPES_KINE
    else:
        GROUPES = {**GROUPES_PREPA, **GROUPES_KINE}
    # Donnees deja chargees et fournies par appV3 (Google Sheets) --
    # remplace le chargement Excel local d'origine (voir data_loader.load_and_clean_from_dataframe).
    df = load_and_clean_from_dataframe(df)
    col_session = "Session" if "Session" in df.columns else None
    sessions_list, sel_session, df_prev_session = [], None, None
    if col_session:
        sessions_list = sorted(df[col_session].dropna().unique().tolist())
        default_idx = len(sessions_list) - 1
        for i, s in enumerate(sessions_list):
            if "pré-saison" in str(s).lower() or "pre-saison" in str(s).lower():
                default_idx = i
                break
        sel_session = st.selectbox("Session Analysée", sessions_list, index=default_idx)
        df_session = df[df[col_session] == sel_session]
    else:
        df_session = df
    teams = sorted(df_session["Equipe"].dropna().astype(str).unique().tolist())
    if not teams:
        st.warning("Aucune équipe trouvée pour cette sélection.")
        st.stop()
    default_team_idx = teams.index("PRO") if "PRO" in teams else 0
    team_sel = st.selectbox("Équipe", teams, index=default_team_idx)
    df_team = df_session[df_session["Equipe"] == team_sel]
    players = sorted(df_team["Joueur"].dropna().unique().tolist())
    if not players:
        st.warning("Aucun joueur trouvé pour cette équipe.")
        st.stop()
    p_sel = st.selectbox("Joueur à profiler", players)
    row = df_team[df_team["Joueur"] == p_sel].iloc[0]
    prev_session_val = None
    if col_session and len(sessions_list) > 1:
        curr_idx = sessions_list.index(sel_session)
        if curr_idx > 0:
            prev_session_val = sessions_list[curr_idx - 1]
            df_prev_filter = df[(df["Joueur"] == p_sel) & (df[col_session] == prev_session_val)]
            if not df_prev_filter.empty:
                df_prev_session = df_prev_filter
    # "PositionPrincipale" (poste précis, ex: "DLG") en 1er choix, puis
    # COL_MAPPING["Poste"] (ancienne colonne "Position", absente depuis le
    # passage à Poste/PositionPrincipale/PositionSecondaire) en repli.
    poste = safe_get(row, "PositionPrincipale")
    if poste == "-":
        poste = safe_get(row, COL_MAPPING["Poste"])
    if poste == "-" and "Poste" in row.index:
        poste = safe_get(row, "Poste")
    lateralite = safe_get(row, "Latéralité")
    p_age = clean_numeric_value(row.get("Age"), "Age")
    anthro = {"Age": int(p_age) if p_age is not None else "-", "Taille": safe_get(row, "Taille (cm)"), "Poids": safe_get(row, "Poids (kg)")}
    key_suffix = f"{p_sel}_{sel_session}"
    if report_mode in ["Kiné / Prévention", "Commun (Complet)"]:
        st.markdown("---")
        st.subheader("Contexte & Antécédents")
        antecedents_kine = st.text_input("Antécédents médicaux (ex: ischio, pubalgie, cheville...)", key=f"ant_{key_suffix}")

        st.markdown("---")
        st.subheader("Latéralité (Correction)")
        lat_val = str(lateralite).strip().upper()
        default_frappe = "G" if lat_val == "G" else "D"
        default_appui = "G" if default_frappe == "D" else "D"
        jambe_frappe = st.selectbox("Jambe Dominante (Frappe)", ["D", "G"], index=0 if default_frappe == "D" else 1, key=f"frappe_{key_suffix}")
        jambe_appui = st.selectbox("Jambe d'Appui", ["G", "D"], index=0 if default_appui == "G" else 1, key=f"appui_{key_suffix}")
        leg_overrides = {"frappe": jambe_frappe, "appui": jambe_appui}
    else:
        antecedents_kine = ""
        leg_overrides = None
    st.markdown("---")
    st.subheader("Groupe de Comparaison")
    col_age = "Age" if "Age" in df.columns else None
    min_age_file = int(df_session[col_age].min(skipna=True)) if col_age and df_session[col_age].notna().any() else 14
    max_age_file = int(df_session[col_age].max(skipna=True)) if col_age and df_session[col_age].notna().any() else 35
    if min_age_file >= max_age_file:
        max_age_file = min_age_file + 1
    age_range = st.slider("Fenêtre d'âge", min_value=min_age_file, max_value=max_age_file, value=(min_age_file, max_age_file))

    # Comparaison forcée au groupe PRO -- demande explicite : pour un joueur
    # Révélation/Elite/Espoir surclassé, situer directement son niveau par
    # rapport aux pros plutôt que par rapport à sa propre équipe (même
    # logique que "force_pro_comparison_players" côté génération en lot,
    # mais ici pour le flux interactif à un seul joueur).
    joueur_equipe = str(row.get("Equipe", "")).strip()
    force_pro = False
    if joueur_equipe and joueur_equipe != "PRO" and "PRO" in df_session["Equipe"].dropna().astype(str).unique():
        force_pro = st.checkbox(
            f"⭐ Comparer uniquement au groupe PRO (au lieu de « {joueur_equipe} »)",
            value=False,
            help="Utile pour situer un joueur Révélation/Elite/Espoir surclassé par rapport au niveau professionnel, indépendamment du niveau hiérarchique choisi ci-dessous.",
        )

    choix_niveau = st.selectbox("Niveau hiérarchique", ["Club entier", "Équipe", "Poste large", "Position précise"], index=1, disabled=force_pro)

    if force_pro:
        df_ref = df_session[df_session["Equipe"].astype(str) == "PRO"]
        if col_age and (age_range[0] > min_age_file or age_range[1] < max_age_file):
            _df_ref_age = df_ref[(df_ref[col_age] >= age_range[0]) & (df_ref[col_age] <= age_range[1])]
            if len(_df_ref_age) >= N_REF_MIN:
                df_ref = _df_ref_age
        ref_label, n_ref = "Équipe PRO", len(df_ref)
        if n_ref < N_REF_MIN:
            st.warning(f"⚠️ Échantillon PRO réduit (n={n_ref}). Percentile peu fiable — privilégie le z-score comme taille d'effet plutôt qu'un jugement de percentile brut.")
    else:
        _df_ref_demande, _ref_label_demande = get_ref_dataframe(choix_niveau, df_session, row, age_range, col_age, COL_MAPPING["Poste"], min_age_file, max_age_file)
        _n_ref_demande = len(_df_ref_demande)
        if _n_ref_demande < N_REF_MIN:
            st.warning(f"⚠️ Échantillon réduit (n={_n_ref_demande}) pour « {choix_niveau} ». Percentile peu fiable — privilégie le z-score comme taille d'effet plutôt qu'un jugement de percentile brut.")
            forcer = st.checkbox("Forcer le calcul quand même (ignorer le repli automatique)", value=False)
            if forcer:
                df_ref, ref_label, n_ref = _df_ref_demande, _ref_label_demande, _n_ref_demande
            else:
                df_ref, ref_label, n_ref = resolve_ref_group(choix_niveau, df_session, row, age_range, col_age, COL_MAPPING["Poste"], min_age_file, max_age_file, N_REF_MIN)
                if n_ref < N_REF_MIN:
                    st.error(f"Effectif toujours insuffisant même après repli sur « {ref_label} » (n={n_ref}). Interprète les percentiles avec beaucoup de prudence.")
                else:
                    st.info(f"Repli automatique appliqué sur : {ref_label} (n={n_ref})")
        else:
            df_ref, ref_label, n_ref = _df_ref_demande, _ref_label_demande, _n_ref_demande
    ref_group_label = f"{ref_label} (n={n_ref})"

    saved_data_all = _cached_load_profiling_data(st.session_state.get("_profiling_cache_marker", "v0"))
    saved_data_player = saved_data_all.get(key_suffix, {})

    # =========================================================================
    # GÉNÉRATION RAPIDE -- en haut de page, volontairement : pour un usage
    # courant ("je veux juste le rapport"), pas besoin de descendre jusqu'aux
    # cases à cocher. TOUS les indicateurs avec une donnée valide pour ce
    # joueur/session sont automatiquement inclus (un indicateur sans donnée
    # n'apparaît simplement pas). La section détaillée plus bas (sélection
    # précise des tests, objectifs, thématiques...) reste disponible pour qui
    # veut personnaliser avant de régénérer.
    # =========================================================================
    st.markdown("---")
    st.markdown("##### 🚀 Génération rapide du rapport")
    st.caption(
        "Inclut automatiquement tous les indicateurs pour lesquels ce joueur a une donnée sur cette "
        "session (rien à cocher) — pour choisir précisément les tests, ajuster un objectif ou ajouter "
        "une thématique de travail, la section détaillée est plus bas sur cette page."
    )
    pdf_ready_quick = is_pdf_export_available()
    if not pdf_ready_quick:
        st.caption("ℹ️ Export PDF indisponible dans cet environnement (dépendances système manquantes — voir `packages.txt`). Le rapport reste disponible en HTML.")
    if st.button("🚀 Générer le rapport maintenant", type="primary", width='stretch', key=f"quick_gen_{key_suffix}"):
        with st.spinner("Génération du rapport..."):
            html_report = _generate_quick_report(
                p_sel, row, df, df_session, df_ref, ref_group_label, poste, lateralite, anthro,
                report_mode, GROUPES, antecedents_kine, leg_overrides, sel_session, df_prev_session,
                saved_data_player,
            )
        st.session_state["_last_report_html"] = html_report
        st.session_state["_last_report_player"] = p_sel
        st.success("Rapport généré — tous les indicateurs disponibles ont été inclus automatiquement.")
    _render_report_download_section(pdf_ready_quick, key_prefix="top")

    st.markdown("---")
    st.markdown(f"<h2 style='color:{SDR_RED};'>🔧 Section détaillée (optionnel)</h2>", unsafe_allow_html=True)
    st.caption("Ce qui suit permet de choisir précisément les tests, ajuster un objectif, ajouter une thématique de travail, saisir un entretien... La génération rapide ci-dessus suffit pour un rapport standard.")
    st.subheader("Variables & Évaluation")
    player_metrics_key = f"selected_metrics_{key_suffix}"
    if player_metrics_key not in st.session_state:
        if "selected_metrics" in saved_data_player:
            st.session_state[player_metrics_key] = set(saved_data_player["selected_metrics"])
        else:
            auto_sel = set()
            for grp, lbls in GROUPES.items():
                if report_mode == "Kiné / Prévention" and "Biodex" in grp:
                    continue
                for l in lbls:
                    c = find_column(df_session, l)
                    if c and pd.notna(row.get(c)):
                        auto_sel.add(l)
            st.session_state[player_metrics_key] = auto_sel
    if "use_relative" not in st.session_state:
        st.session_state.use_relative = saved_data_player.get("use_relative", {})
    staff_evals = {}
    for group, labels in GROUPES.items():
        with st.expander(group, expanded=False):
            for label in labels:
                col = find_column(df_session, label)
                has_data = col is not None
                checked = st.checkbox(label, value=(label in st.session_state[player_metrics_key]),
                                       key=f"chk_{label}_{key_suffix}", disabled=not has_data)
                if not checked:
                    st.session_state[player_metrics_key].discard(label)
                    continue

                st.session_state[player_metrics_key].add(label)
                unit = UNITS.get(label, "")
                can_be_rel = unit in ["N", "W", "Nm"] and "Poids (kg)" in df_session.columns
                if can_be_rel:
                    st.session_state.use_relative[label] = st.checkbox(
                        f"→ Relatif ({unit}/kg)", value=st.session_state.use_relative.get(label, False),
                        key=f"rel_{label}_{key_suffix}",
                    )

                st.markdown(f"**Statut pour {label}**")
                v_metric = get_value_for_metric(row, df_session, col, st.session_state.use_relative.get(label, False)) if col else None
                _, v_pct = calculate_percentile(df_ref, col, v_metric, st.session_state.use_relative.get(label, False)) if col and v_metric is not None else (None, None)
                statut_def, obj_def = auto_eval_metric(label, v_metric, v_pct, st.session_state.use_relative.get(label, False), df_ref=df_ref, col=col)

                statut_opts = ["Acquis", "Proche", "Non Acquis"]
                saved_eval = saved_data_player.get("staff_evals", {}).get(label, {})
                saved_statut = saved_eval.get("statut", statut_def)
                idx_statut = statut_opts.index(saved_statut) if saved_statut in statut_opts else 0
                statut = st.radio("Acquis ?", statut_opts, horizontal=True, key=f"statut_{label}_{key_suffix}", index=idx_statut)

                obj_val, delai_val = "", ""
                if statut != "Acquis":
                    saved_obj = saved_eval.get("objectif", obj_def)
                    if report_mode == "Préparation Physique":
                        obj_val = st.text_input("Objectif", value=saved_obj, key=f"obj_{label}_{key_suffix}")
                    else:
                        c_obj, c_delai = st.columns(2)
                        with c_obj:
                            obj_val = st.text_input("Objectif", value=saved_obj, key=f"obj_{label}_{key_suffix}")
                        with c_delai:
                            delai_opts = ["", "1 semaine", "2 semaines", "3 semaines", "1 mois", "2 mois", "+ de 3 mois"]
                            saved_delai = saved_eval.get("delai", "")
                            delai_idx = delai_opts.index(saved_delai) if saved_delai in delai_opts else 0
                            delai_val = st.selectbox("Délai", delai_opts, index=delai_idx, key=f"delai_{label}_{key_suffix}")
                staff_evals[label] = {"statut": statut, "objectif": obj_val, "delai": delai_val}
                st.markdown("---")
    selected_metrics = st.session_state[player_metrics_key]
    photo_b64_ui = _img_to_b64(_get_best_photo_path(p_sel))
    img_html_ui = (
        f'<img src="data:image/png;base64,{photo_b64_ui}" style="width: 120px; height: 120px; border-radius: 12px; border: 4px solid {SDR_RED}; object-fit: cover; object-position: top center; box-shadow: 0 4px 10px rgba(215,25,32,0.2); background: #fff;">'
        if photo_b64_ui else
        f'<div style="width: 120px; height: 120px; border-radius: 12px; border: 4px solid {SDR_RED}; display:flex; align-items:center; justify-content:center; text-align:center; background:#eee; font-size:36px; font-weight:bold; color:#707070; box-shadow: 0 4px 10px rgba(215,25,32,0.2); line-height:120px;">{p_sel[:1]}</div>'
    )
    age_val, taille_val, poids_val = str(anthro.get("Age", "-")).strip(), str(anthro.get("Taille", "-")).strip(), str(anthro.get("Poids", "-")).strip()
    age_html_ui = f"{age_val} <span style='font-size:14px; color:#666; font-weight:normal;'>ans</span>" if age_val != "-" else "-"
    taille_html_ui = f"{taille_val} <span style='font-size:14px; color:#666; font-weight:normal;'>cm</span>" if taille_val != "-" else "-"
    poids_html_ui = f"{poids_val} <span style='font-size:14px; color:#666; font-weight:normal;'>kg</span>" if poids_val != "-" else "-"
    _name_font_px = 26 if len(p_sel) > 22 else (34 if len(p_sel) > 16 else 42)
    st.markdown(f"""
    <div style="background: #ffffff; border-top: 4px solid {SDR_RED}; border-bottom: 4px solid {SDR_RED}; padding: 25px; border-radius: 12px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 20px rgba(215,25,32,0.08); margin-bottom: 25px; overflow-wrap: break-word;">
        <div style="display: flex; align-items: center; gap: 25px;">
            {img_html_ui}
            <div style="display: flex; flex-direction: column;">
                <div style="font-size: {_name_font_px}px; font-weight: 900; color: {SDR_RED}; text-transform: uppercase; line-height: 1.15; margin-bottom: 6px;">{p_sel}</div>
                <div style="font-size: 16px; font-weight: 800; color: #555; text-transform: uppercase; letter-spacing: 1px;">{poste} · {lateralite}</div>
                <div style="font-size: 12px; font-weight: 600; color: {GREEN_TEXT}; margin-top: 8px;">Comparaison : {ref_group_label}</div>
            </div>
        </div>
        <div style="display: flex; gap: 40px; padding-right: 20px; border-left: 2px dashed #eee; padding-left: 40px;">
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center;">
                <div style="font-size: 12px; font-weight: 800; color: #555; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">Âge</div>
                <div style="font-size: 32px; font-weight: 900; color: {SDR_RED};">{age_html_ui}</div>
            </div>
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center;">
                <div style="font-size: 12px; font-weight: 800; color: #555; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">Taille</div>
                <div style="font-size: 32px; font-weight: 900; color: {SDR_RED};">{taille_html_ui}</div>
            </div>
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center;">
                <div style="font-size: 12px; font-weight: 800; color: #555; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">Poids</div>
                <div style="font-size: 32px; font-weight: 900; color: {SDR_RED};">{poids_html_ui}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    context_test = st.selectbox("Contexte du test", ["Pré-saison", "En saison", "Reprise", "Fin de saison"], key=f"contexte_{key_suffix}")
    groupes_pour_zscores = {g: l for g, l in GROUPES.items() if not (g == "Ratio Mixte" and report_mode == "Préparation Physique")}
    comp_zscores = compute_group_zscores(df_session, df_ref, row, groupes_pour_zscores, selected_metrics, st.session_state.use_relative, find_column)
    c1, c2 = st.columns([1.5, 1])
    with c1:
        st.markdown("**Aperçu des variables sélectionnées**")
        if not selected_metrics:
            st.caption("Sélectionne des variables dans la barre latérale pour construire le rapport.")

        sorted_groups_ui = list(GROUPES.items())
        prioritaires_ui = []
        if report_mode in ["Kiné / Prévention", "Commun (Complet)"] and antecedents_kine:
            from report_kine import _prioritize_by_antecedents
            prioritaires_ui = _prioritize_by_antecedents(selected_metrics, antecedents_kine)
            if prioritaires_ui:
                sorted_groups_ui.insert(0, ("Priorité Antécédents", prioritaires_ui))

        for group, labels in sorted_groups_ui:
            if group == "Ratio Mixte" and report_mode not in ["Kiné / Prévention", "Commun (Complet)"]:
                continue
            group_cards_html = ""
            for label in labels:
                if label not in selected_metrics:
                    continue
                if group != "Priorité Antécédents" and label in prioritaires_ui:
                    continue
                col = find_column(df_session, label)
                use_rel = st.session_state.use_relative.get(label, False)
                value = get_value_for_metric(row, df_session, col, use_rel) if col else None
                unit = UNITS.get(label, "")
                if use_rel and unit:
                    unit = f"{unit}/kg"
                _, pct = calculate_percentile(df_ref, col, value, use_rel) if col and value is not None else (None, None)
                z_score = calculate_zscore(df_ref, col, value, use_rel) if col and value is not None else None
                prev_val = None
                if df_prev_session is not None and col in df_prev_session.columns:
                    prev_val = get_value_for_metric(df_prev_session.iloc[0], df_session, col, use_rel)
                trend_html = get_trend_html(value, prev_val, label, is_inverted)
                from stats_engine import get_norm_info
                norm_txt, norm_color = get_norm_info(label, value, use_rel, df_ref=df_ref, col=col)
                eval_data = staff_evals.get(label)
                group_cards_html += get_metric_card_html(
                    label, value, unit, pct, z_score, eval_data, trend_html, norm_txt, norm_color,
                    report_mode_label=report_mode, is_report=False,
                    is_kine=(report_mode in ["Kiné / Prévention", "Commun (Complet)"] and label in KINE_LABELS),
                )
            if group_cards_html:
                st.markdown(f"<div style='font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:6px; margin-bottom:10px; margin-top:15px;'>{group}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='display:flex; flex-wrap:wrap; gap:8px;'>{group_cards_html}</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("**Variables pour le radar**")
        radar_labels_prepa, radar_values_prepa = [], []
        radar_labels_kine, radar_values_kine, radar_vals_d_kine = [], [], []

        if report_mode in ["Préparation Physique", "Commun (Complet)"]:
            if report_mode == "Commun (Complet)":
                st.markdown("*(Radar Préparation Physique)*")
            radar_options_prepa = sorted([m for m in selected_metrics if m in GROUPES_PREPA.get("Force", []) or m in GROUPES_PREPA.get("Puissance", []) or m in GROUPES_PREPA.get("Saut", [])])
            radar_selection_prepa = st.multiselect("Choix radar Prépa", radar_options_prepa, default=radar_options_prepa[:8], label_visibility="collapsed", key=f"radar_sel_prepa_{key_suffix}")
            for label in radar_selection_prepa:
                col = find_column(df_session, label)
                use_rel = st.session_state.use_relative.get(label, False)
                value = get_value_for_metric(row, df_session, col, use_rel) if col else None
                _, pct = calculate_percentile(df_ref, col, value, use_rel) if col and value is not None else (None, None)
                if pct is not None:
                    radar_labels_prepa.append(label.replace("(G)", "").replace("(D)", "").strip())
                    radar_values_prepa.append(pct)
            radar_gps_labels, radar_gps_values = [], []
            for label in GROUPES_PREPA.get("Vitesse / GPS", []):
                if label not in selected_metrics:
                    continue
                col = find_column(df_session, label)
                value = get_value_for_metric(row, df_session, col, False) if col else None
                _, pct = calculate_percentile(df_ref, col, value, False) if col and value is not None else (None, None)
                if pct is not None:
                    radar_gps_labels.append(label)
                    radar_gps_values.append(pct)
            if len(radar_gps_labels) >= 3:
                st.markdown(f"<div style='margin-bottom:10px; font-size:16px; font-weight:900; color:{SDR_RED}; border-bottom:2px solid {SDR_RED}; padding-bottom:5px; text-transform:uppercase;'>RADAR VITESSE / GPS</div>", unsafe_allow_html=True)
                st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{_cached_radar_chart(tuple(radar_gps_labels), tuple(radar_gps_values))}" style="width:100%; max-width:380px;"></div>', unsafe_allow_html=True)

            if radar_labels_prepa:
                st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{_cached_radar_chart(tuple(radar_labels_prepa), tuple(radar_values_prepa))}" style="width:100%; max-width:380px;"></div>', unsafe_allow_html=True)
            else:
                st.caption("Sélectionne au moins une variable numérique pour afficher le radar Prépa.")

            radar_1080_labels, radar_1080_values = [], []
            for label in GROUPES_PREPA.get("Sprint 1080 (15m)", []):
                if label not in selected_metrics:
                    continue
                col = find_column(df_session, label)
                value = get_value_for_metric(row, df_session, col, False) if col else None
                _, pct = calculate_percentile(df_ref, col, value, False) if col and value is not None else (None, None)
                if pct is not None:
                    radar_1080_labels.append(label.replace(" (1080)", "").strip())
                    radar_1080_values.append(pct)
            if len(radar_1080_labels) >= 3:
                st.markdown(f"<div style='margin-top:20px; margin-bottom:10px; font-size:16px; font-weight:900; color:{SDR_RED}; border-bottom:2px solid {SDR_RED}; padding-bottom:5px; text-transform:uppercase;'>RADAR SPRINT 1080 (15M)</div>", unsafe_allow_html=True)
                st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{_cached_radar_chart(tuple(radar_1080_labels), tuple(radar_1080_values))}" style="width:100%; max-width:320px;"></div>', unsafe_allow_html=True)

        if report_mode in ["Kiné / Prévention", "Commun (Complet)"]:
            if report_mode == "Commun (Complet)":
                st.markdown("*(Radar Kiné / Prévention)*")
            biodex_bases = ["Q Conc 60°", "Q Conc 240°", "IJ Conc 60°", "IJ Conc 240°", "IJ Exc 30°"]
            base_kine_metrics = set()
            for m in selected_metrics:
                if "(G)" in m or "(D)" in m:
                    base = m.replace("(G)", "").replace("(D)", "").strip()
                    if base not in biodex_bases:
                        base_kine_metrics.add(base)
            radar_options_kine = sorted(base_kine_metrics)
            radar_selection_kine = st.multiselect("Choix radar Kiné (bases G/D)", radar_options_kine, default=radar_options_kine[:8], label_visibility="collapsed", key=f"radar_sel_kine_{key_suffix}")

            for base in radar_selection_kine[:8]:
                col_g, col_d = find_column(df_session, f"{base} (G)"), find_column(df_session, f"{base} (D)")
                v_g = get_value_for_metric(row, df_session, col_g, st.session_state.use_relative.get(f"{base} (G)", False)) if col_g else None
                v_d = get_value_for_metric(row, df_session, col_d, st.session_state.use_relative.get(f"{base} (D)", False)) if col_d else None
                p_g = get_kine_radar_pct(f"{base} (G)", v_g, df_ref, col_g, st.session_state.use_relative.get(f"{base} (G)", False), row)
                p_d = get_kine_radar_pct(f"{base} (D)", v_d, df_ref, col_d, st.session_state.use_relative.get(f"{base} (D)", False), row)
                radar_labels_kine.append(base)
                radar_values_kine.append(p_g)
                radar_vals_d_kine.append(p_d)

            if radar_labels_kine:
                st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{_cached_radar_chart_kine(tuple(radar_labels_kine), tuple(radar_values_kine), tuple(radar_vals_d_kine))}" style="width:100%; max-width:380px;"></div>', unsafe_allow_html=True)
                st.markdown("<div style='text-align:center; font-size:12px; color:#666; margin-top:5px;'>Radar Kiné : % par rapport à l'objectif (Cible = 100%, plage affichée 50%-150%).<br>Seuils : <span style='color:#D71920;'>Rouge &lt;80%</span>, <span style='color:#F39C12;'>Orange 80-100%</span>, <span style='color:#27AE60;'>Vert 100-120%</span>, <span style='color:#00E5FF;'>Bleu &gt;120%</span>.</div>", unsafe_allow_html=True)
            else:
                st.caption("Sélectionne au moins une paire de variables numériques (G/D) pour afficher le radar Kiné.")

            from report_kine import isak_radar_data
            from rapport_charts import create_isak_radar
            from config import ISAK_RADAR_MAX_MM
            isak_labels, isak_values = isak_radar_data(row, df_session, selected_metrics)
            if isak_labels:
                st.markdown(f"<div style='margin-top:20px; margin-bottom:10px; font-size:16px; font-weight:900; color:{SDR_RED}; border-bottom:2px solid {SDR_RED}; padding-bottom:5px; text-transform:uppercase;'>RADAR ISAK (PLIS CUTANÉS, MM)</div>", unsafe_allow_html=True)
                st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{_cached_isak_radar(tuple(isak_labels), tuple(isak_values), ISAK_RADAR_MAX_MM)}" style="width:100%; max-width:340px;"></div>', unsafe_allow_html=True)

            st.markdown(f"<div style='margin-top:30px; margin-bottom:15px; font-size:18px; font-weight:900; color:{SDR_RED}; border-bottom:2px solid {SDR_RED}; padding-bottom:5px; text-transform:uppercase;'>RADAR BIODEX (VALEURS RELATIVES)</div>", unsafe_allow_html=True)

            radar_cats, vals_l_rel, vals_r_rel, vals_norm, table_data = [], [], [], [], []
            poids_joueur = clean_numeric_value(row.get("Poids (kg)"))
            for item in BIODEX_CONFIG:
                lbl = item["label"]
                radar_cats.append(lbl)
                val_norm_rel = BIODEX_TARGETS.get(lbl, 0)
                vals_norm.append(val_norm_rel)
                v_g_rel = clean_numeric_value(row.get(find_column(df_session, item["g_rel"]) or item["g_rel"]))
                v_d_rel = clean_numeric_value(row.get(find_column(df_session, item["d_rel"]) or item["d_rel"]))
                vals_l_rel.append(v_g_rel if v_g_rel is not None else 0)
                vals_r_rel.append(v_d_rel if v_d_rel is not None else 0)
                v_g_raw = clean_numeric_value(row.get(find_column(df_session, item["g_raw"]) or item["g_raw"]))
                v_d_raw = clean_numeric_value(row.get(find_column(df_session, item["d_raw"]) or item["d_raw"]))
                s_lsi, c_lsi = "-", "#888"
                if v_g_raw is not None and v_d_raw is not None:
                    mx = max(v_g_raw, v_d_raw)
                    if mx > 0:
                        lsi = ((v_d_raw - v_g_raw) / mx) * 100
                        s_lsi, c_lsi = f"{lsi:.0f}%", ("#D71920" if abs(lsi) > 10 else ("#F39C12" if abs(lsi) > 5 else "#27AE60"))
                target_abs = f"{val_norm_rel * poids_joueur:.0f}" if poids_joueur and poids_joueur > 0 else "-"
                table_data.append({
                    "label": lbl, "target": target_abs,
                    "v_g": f"{v_g_raw:.0f}" if v_g_raw is not None else "-",
                    "v_d": f"{v_d_raw:.0f}" if v_d_raw is not None else "-",
                    "lsi": s_lsi, "c_lsi": c_lsi,
                })

            col_radar, col_table = st.columns([1.2, 1])
            with col_radar:
                if not radar_cats:
                    st.warning("Aucune donnée Biodex configurée trouvée.")
                else:
                    import plotly.graph_objects as go
                    limit_scale = max(4.0, max(vals_l_rel + vals_r_rel + vals_norm) * 1.1)
                    cats_closed = radar_cats + [radar_cats[0]]
                    fig = go.Figure()
                    fig.add_trace(go.Scatterpolar(r=vals_norm + [vals_norm[0]], theta=cats_closed, fill="toself", name="Objectif", mode="lines", line=dict(color="#2ECC71", dash="dash", width=2), fillcolor="rgba(46, 204, 113, 0.1)", hoverinfo="skip"))
                    fig.add_trace(go.Scatterpolar(r=vals_l_rel + [vals_l_rel[0]], theta=cats_closed, name="Gauche", mode="lines+markers", fill="toself", line=dict(color="#1ABC9C", width=3), marker=dict(size=8, color="#1ABC9C"), fillcolor="rgba(26, 188, 156, 0.15)", hovertemplate="<b>Gauche</b><br>%{theta}: <b>%{r:.2f}</b> N/kg<extra></extra>"))
                    fig.add_trace(go.Scatterpolar(r=vals_r_rel + [vals_r_rel[0]], theta=cats_closed, name="Droite", mode="lines+markers", fill="toself", line=dict(color="#9B59B6", width=3), marker=dict(size=8, color="#9B59B6"), fillcolor="rgba(155, 89, 182, 0.15)", hovertemplate="<b>Droite</b><br>%{theta}: <b>%{r:.2f}</b> N/kg<extra></extra>"))
                    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, limit_scale], tickfont=dict(color="#555", size=9), gridcolor="#eee"), angularaxis=dict(tickfont=dict(color="#111", size=12), gridcolor="#eee"), bgcolor="rgba(0,0,0,0)"), paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=40, r=40, t=20, b=20), legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"), height=350)
                    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

            with col_table:
                st.markdown(f"<br><div style='text-align:center; font-size:15px; font-weight:900; color:{SDR_RED}; margin-bottom:10px; text-transform:uppercase;'>Résultats Détaillés (Nm)</div>", unsafe_allow_html=True)
                html_rows = "".join(
                    f"<tr style='border-bottom:1px solid #eee;'><td style='padding:6px; color:#555;'>{it['label']}</td><td style='text-align:center; color:#666; font-weight:bold;'>{it['target']}</td><td style='text-align:center; color:#111; font-weight:bold;'>{it['v_g']}</td><td style='text-align:center; color:#111; font-weight:bold;'>{it['v_d']}</td><td style='text-align:center; color:{it['c_lsi']}; font-weight:bold;'>{it['lsi']}</td></tr>"
                    for it in table_data
                )
                col_rm_g = find_column(df_session, "Ratio Mixte (G)") or "Ratio Mixte (G)"
                col_rm_d = find_column(df_session, "Ratio Mixte (D)") or "Ratio Mixte (D)"
                val_rm_g, val_rm_d = clean_numeric_value(row.get(col_rm_g)), clean_numeric_value(row.get(col_rm_d))

                def _ratio_color(val):
                    return "#888" if val is None else ("#D71920" if val < 0.8 else ("#F39C12" if val <= 1.0 else "#27AE60"))

                s_rm_g = f"{val_rm_g:.2f}" if val_rm_g is not None else "-"
                s_rm_d = f"{val_rm_d:.2f}" if val_rm_d is not None else "-"
                html_rows += f"<tr style='border-top:2px solid #ccc; background-color:#f9f9f9;'><td style='padding:6px; font-weight:bold; color:#111;'>Ratio Mixte</td><td style='text-align:center;'>-</td><td style='text-align:center; font-weight:bold; color:{_ratio_color(val_rm_g)};'>{s_rm_g}</td><td style='text-align:center; font-weight:bold; color:{_ratio_color(val_rm_d)};'>{s_rm_d}</td><td style='text-align:center;'>-</td></tr>"
                st.markdown(f"<table style='width:100%; border-collapse:collapse; font-size:12px; font-family:sans-serif;'><tr style='background-color:#f0f0f0; color:#333; text-transform:uppercase; font-size:10px;'><th style='padding:8px; text-align:left;'>Test</th><th style='padding:8px; text-align:center;'>Obj. (Nm)</th><th style='padding:8px; text-align:center;'>G (Nm)</th><th style='padding:8px; text-align:center;'>D (Nm)</th><th style='padding:8px; text-align:center;'>LSI</th></tr>{html_rows}</table>", unsafe_allow_html=True)
                st.markdown("<div style='font-size:11px; color:#666; font-style:italic; margin-top:5px;'>* L'objectif brut (Nm) est calculé en multipliant la norme relative (N/kg) par le poids du joueur.</div>", unsafe_allow_html=True)

        st.markdown(f"""
        <div style="margin-top:15px; padding:10px; background:#f8f9fa; border:1px solid #e9ecef; border-radius:8px; font-size:12px; color:#495057;">
            <div style="font-weight:bold; color:#333; margin-bottom:8px;">📊 PAR RAPPORT AU GROUPE ({ref_group_label})</div>
            <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center;">
                <span style="display:flex; align-items:center; gap:5px; font-weight:bold; color:{BLUE_ELITE_TEXT};"><div style="width:12px; height:4px; border-radius:2px; background:{BLUE_ELITE};"></div> Élite (≥ 95% / Z ≥ 1.65)</span>
                <span style="display:flex; align-items:center; gap:5px; font-weight:bold; color:{GREEN_TEXT};"><div style="width:12px; height:4px; border-radius:2px; background:{GREEN};"></div> Bon (≥ 66%)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Recommandations Thématiques")
    st.caption(
        "Section 100% manuelle : rien n'est pré-rempli automatiquement. Une suggestion algorithmique "
        "non validée par le staff n'est pas assez fiable pour figurer dans un rapport transmis au joueur."
    )
    key_themes = f"themes_{key_suffix}"
    if key_themes not in st.session_state:
        # POURQUOI ne rien auto-suggérer par défaut : les suggestions ci-dessous
        # (get_theme_suggestions_advanced) sont de simples heuristiques (seuils
        # d'asymétrie, percentile < 33%...), pas une évaluation clinique. Les
        # pré-remplir silencieusement risquait de faire passer une hypothèse
        # algorithmique pour une recommandation validée. Elles restent
        # disponibles à la demande via le bouton "indicatif" ci-dessous.
        st.session_state[key_themes] = saved_data_player.get("themes", [])
    with st.expander("💡 Voir des pistes indicatives (non validées, à vérifier avant tout ajout)", expanded=False):
        st.caption("Basé sur des seuils simples (asymétrie > 15%, percentile < 33%...). Ne remplace pas ton jugement clinique/terrain.")
        pistes = get_theme_suggestions_advanced(row, df_session)
        if not pistes:
            st.caption("Aucune piste détectée par les heuristiques pour ce joueur.")
        for p in pistes:
            c_p1, c_p2 = st.columns([4, 1])
            with c_p1:
                detail = p.get("detail", "")
                detail_html = f" &nbsp;<span style='color:#888; font-size:12px;'>({detail})</span>" if detail else ""
                st.markdown(f"**{p['etat']} {p['qualite']}** — {p['zone']}{detail_html}", unsafe_allow_html=True)
            with c_p2:
                if st.button("Ajouter", key=f"add_piste_{p['id']}_{key_suffix}"):
                    if len(st.session_state[key_themes]) < 3:
                        st.session_state[key_themes].append(p)
                        st.rerun()
                    else:
                        st.warning("Max 3 recommandations pour faciliter l'entretien.")
    ct1, ct2, ct3, ct4 = st.columns([2, 2, 2, 1])
    with ct1:
        sel_etat = st.selectbox("État / Action", ETATS_ACTIONS)
    with ct2:
        sel_qualite = st.selectbox("Qualité physique", QUALITES_PHYSIQUES)
    with ct3:
        sel_zone = st.selectbox("Zone ciblée", ZONES_CIBLEES)
    with ct4:
        st.write("")
        st.write("")
        if st.button("Ajouter", width='stretch'):
            if len(st.session_state[key_themes]) < 3:
                st.session_state[key_themes].append({"id": str(uuid.uuid4()), "etat": sel_etat, "qualite": sel_qualite, "zone": sel_zone, "objectif": "", "freq": "1x/sem", "moment": "Pré séance"})
                st.rerun()
            else:
                st.warning("Max 3 recommandations pour faciliter l'entretien.")
    if st.session_state[key_themes]:
        for i, t in enumerate(st.session_state[key_themes]):
            tid = t.get("id", str(i))
            cols_t = st.columns([2, 1.5, 1.5, 2, 1])
            with cols_t[0]:
                st.markdown(get_theme_card_html(t, is_report=False), unsafe_allow_html=True)
            with cols_t[1]:
                freq_opts = ["1x/sem", "2x/sem", "3x/sem", "4x/sem", "5x+/sem"]
                t["freq"] = st.selectbox("Fréquence", freq_opts, index=freq_opts.index(t.get("freq", "1x/sem")), key=f"freq_{tid}_{key_suffix}")
            with cols_t[2]:
                mom_opts = ["Pré séance", "Post séance", "Maison"]
                t["moment"] = st.selectbox("Moment", mom_opts, index=mom_opts.index(t.get("moment", "Pré séance")), key=f"mom_{tid}_{key_suffix}")
            with cols_t[3]:
                t["objectif"] = st.text_input("Objectif", value=t.get("objectif", ""), key=f"obj_th_{tid}_{key_suffix}")
            with cols_t[4]:
                st.write("")
                st.write("")
                if st.button("Retirer", key=f"del_{tid}_{key_suffix}"):
                    st.session_state[key_themes].pop(i)
                    st.rerun()
    else:
        st.caption("Aucune recommandation thématique. Utilise les menus ci-dessus pour en ajouter.")
    st.markdown("---")
    st.subheader("Entretien & Synthèse")
    _last_modified_by = saved_data_player.get('modified_by', '')
    _last_modified_suffix = f" par **{_last_modified_by}**" if _last_modified_by else ""
    st.caption(f"Dernière modification : {saved_data_player.get('last_modified', 'Jamais')}{_last_modified_suffix}")
    if prev_session_val is not None:
        prev_key_suffix = f"{p_sel}_{prev_session_val}"
        saved_data_prev = saved_data_all.get(prev_key_suffix, {})
        if saved_data_prev:
            if st.button(f"📋 Reprendre les réglages de la session « {prev_session_val} »"):
                # On copie le texte libre, les évaluations et les thèmes de la
                # session précédente. Écrase les champs actuels : on ne
                # fusionne pas silencieusement pour éviter un mélange confus
                # entre deux sessions.
                st.session_state[f"strat_salle_{key_suffix}"] = saved_data_prev.get("strat_salle", "")
                st.session_state[f"strat_terrain_{key_suffix}"] = saved_data_prev.get("strat_terrain", "")
                st.session_state[key_themes] = saved_data_prev.get("themes", [])
                st.session_state[player_metrics_key] = set(saved_data_prev.get("selected_metrics", []))
                st.session_state.use_relative = saved_data_prev.get("use_relative", {})
                st.success(f"Réglages de « {prev_session_val} » repris. Vérifie/ajuste avant de sauvegarder.")
                st.rerun()
        else:
            st.caption(f"ℹ️ Aucun réglage sauvegardé pour « {prev_session_val} » à reprendre.")
    history = saved_data_player.get("history", [])
    if history:
        with st.expander(f"🕘 Historique des sauvegardes ({len(history)})", expanded=False):
            for h in reversed(history):
                c_h1, c_h2 = st.columns([4, 1])
                with c_h1:
                    _h_by = f" (par {h.get('modified_by')})" if h.get('modified_by') else ""
                    st.caption(f"**{h.get('timestamp', '?')}**{_h_by} — Points forts (à l'époque) : {(h.get('dominant') or '—')[:60]}")
                with c_h2:
                    if st.button("Restaurer", key=f"restore_{h.get('timestamp')}_{key_suffix}"):
                        st.session_state[f"strat_salle_{key_suffix}"] = h.get("strat_salle", "")
                        st.session_state[f"strat_terrain_{key_suffix}"] = h.get("strat_terrain", "")
                        st.session_state[key_themes] = h.get("themes", [])
                        st.success(f"Version du {h.get('timestamp')} restaurée (pas encore sauvegardée — clique sur 💾 pour valider).")
                        st.rerun()
    # --- POINTS FORTS / AXES DE TRAVAIL : 100% AUTOMATIQUES ---
    # Sur demande explicite du département performance : plus aucune saisie
    # humaine sur ces deux champs, calculés uniquement à partir des résultats
    # du joueur (percentile de chaque test sélectionné vs le groupe de
    # référence choisi plus haut). Seules Stratégie Salle / Stratégie
    # Terrain, plus bas, restent du texte libre rempli par le staff.
    st.markdown("##### 🤖 Points forts / Axes de travail — calculés automatiquement")
    st.caption(
        "Basés uniquement sur les résultats de ce joueur (percentile de chaque test coché "
        "ci-dessus vs le « Groupe de Comparaison » choisi plus haut) — rien à saisir ici. "
        "Tout ce qui n'est pas franchement bon est signalé, même les écarts mineurs (33-66%) : "
        "au préparateur physique de juger ensuite si c'est pertinent à travailler pour CE joueur."
    )
    ff = auto_forces_faiblesses(row, df_session, df_ref, selected_metrics, st.session_state.use_relative)
    dominant, weak = ff["dominant_text"], ff["weak_text"]

    def _flash_badge(label, pct, color):
        return (f"<span style='display:inline-block; background:{color}; color:white; font-weight:bold; "
                f"font-size:12px; padding:4px 10px; border-radius:14px; margin:3px 5px 3px 0;'>{label} · {pct}%</span>")

    badges_html = "".join(_flash_badge(r["label"], r["pct"], "#27AE60") for r in ff["forts"])
    badges_html += "".join(_flash_badge(r["label"], r["pct"], "#F39C12") for r in ff["moyens"])
    badges_html += "".join(_flash_badge(r["label"], r["pct"], SDR_RED) for r in ff["faibles"])
    if badges_html:
        st.markdown(badges_html, unsafe_allow_html=True)
    else:
        st.caption("Aucune métrique sélectionnée avec un percentile calculable pour cette session.")

    c_fort, c_faible = st.columns(2)
    with c_fort:
        st.markdown(
            f"<div style='background:#eafaf1; border-left:4px solid #27AE60; border-radius:6px; "
            f"padding:10px 14px; min-height:70px;'><b>Points forts</b><br>"
            f"<span style='font-size:13px;'>{dominant}</span></div>",
            unsafe_allow_html=True,
        )
    with c_faible:
        st.markdown(
            f"<div style='background:#fdecea; border-left:4px solid {SDR_RED}; border-radius:6px; "
            f"padding:10px 14px; min-height:70px;'><b>Axes de travail</b><br>"
            f"<span style='font-size:13px;'>{weak}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    c_ent1, c_ent2 = st.columns(2)
    with c_ent1:
        entretien_date = st.text_input("Date de l'entretien", value=saved_data_player.get("entretien_date", ""), key=f"ent_date_{key_suffix}")
    with c_ent2:
        rdv_date = st.text_input("Prochain RDV / Test", value=saved_data_player.get("rdv_date", ""), key=f"rdv_date_{key_suffix}")

    kpi_info = get_kpi_auto_fill(p_sel, weak)
    if kpi_info:
        if st.button("🔄 Pré-remplir les stratégies", width='stretch',
                     help="Remplit Stratégie Salle / Stratégie Terrain à partir du plan "
                          "d'individualisation de ce joueur (config.PLAYER_KPI_PRIORITAIRE). "
                          "Reste éditable avant sauvegarde — rien n'est enregistré tant que tu "
                          "ne cliques pas sur 💾."):
            st.session_state[f"strat_salle_{key_suffix}"] = kpi_info["strat_salle"]
            if report_mode in ["Préparation Physique", "Commun (Complet)"]:
                st.session_state[f"strat_terrain_{key_suffix}"] = kpi_info["strat_terrain"]
            st.success("Stratégies pré-remplies ci-dessous — relis et ajuste avant de sauvegarder.")
            st.rerun()
    else:
        st.caption(
            "ℹ️ Aucun KPI prioritaire connu pour ce joueur dans le plan d'individualisation "
            "(nom absent du document source — complète `PLAYER_KPI_PRIORITAIRE` dans "
            "`config.py` si besoin). Les stratégies restent à saisir manuellement ci-dessous."
        )

    d1, d2 = st.columns(2)
    with d1:
        if report_mode in ["Préparation Physique", "Commun (Complet)"]:
            strat_salle = st.text_area("Stratégie Salle", value=saved_data_player.get("strat_salle", ""), key=f"strat_salle_{key_suffix}", height=100)
        else:
            strat_salle = st.text_area("Stratégie de prise en charge", value=saved_data_player.get("strat_salle", ""), key=f"strat_salle_{key_suffix}", height=100)
    with d2:
        if report_mode in ["Préparation Physique", "Commun (Complet)"]:
            strat_terrain = st.text_area("Stratégie Terrain", value=saved_data_player.get("strat_terrain", ""), key=f"strat_terrain_{key_suffix}", height=100)
        else:
            strat_terrain = ""
    if st.button("💾 Sauvegarder Profilage"):
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        # Historique : on garde un instantané des champs texte/thèmes AVANT
        # d'écraser avec les nouvelles valeurs, pour pouvoir revenir en arrière.
        # Limité aux 20 dernières versions pour ne pas faire grossir le JSON indéfiniment.
        history = saved_data_player.get("history", [])
        if saved_data_player:  # rien à archiver si c'est la toute première sauvegarde
            history = history + [{
                "timestamp": saved_data_player.get("last_modified", now_str),
                "modified_by": saved_data_player.get("modified_by", ""),
                "dominant": saved_data_player.get("dominant", ""),
                "weak": saved_data_player.get("weak", ""),
                "strat_salle": saved_data_player.get("strat_salle", ""),
                "strat_terrain": saved_data_player.get("strat_terrain", ""),
                "themes": saved_data_player.get("themes", []),
            }]
            history = history[-20:]

        # Traçabilité : qui a fait cette sauvegarde -- voir le champ "Intervenant"
        # dans la sidebar (main.py). Pas un vrai compte utilisateur (mot de
        # passe toujours partagé), juste une attribution déclarative.
        modified_by = (st.session_state.get("current_user_name") or "").strip() or "Non renseigné"

        saved_data_all[key_suffix] = {
            "entretien_date": entretien_date, "rdv_date": rdv_date, "dominant": dominant, "weak": weak,
            "strat_salle": strat_salle, "strat_terrain": strat_terrain,
            "themes": st.session_state[key_themes], "selected_metrics": list(st.session_state[player_metrics_key]),
            "use_relative": st.session_state.use_relative, "staff_evals": staff_evals,
            "last_modified": now_str, "modified_by": modified_by, "history": history,
        }
        with st.spinner("Sauvegarde en cours..."):
            success, message = save_profiling_data(st.secrets, saved_data_all, key_suffix)
            if success:
                st.success(message)
                # Invalide le cache de lecture pour que la prochaine lecture reflète l'écriture.
                st.session_state["_profiling_cache_marker"] = str(uuid.uuid4())
                _cached_load_profiling_data.clear()
                st.rerun()
            else:
                st.error(message)
    st.markdown("---")
    st.info("💡 **Astuce impression HTML :** décoche 'En-têtes et pieds de page' dans les options d'impression du navigateur (Ctrl+P) pour retirer les URL en haut/bas de page.")
    pdf_ready = is_pdf_export_available()
    if not pdf_ready:
        st.caption("ℹ️ Export PDF indisponible dans cet environnement (dépendances système manquantes — voir `packages.txt`). Le rapport reste disponible en HTML.")
    if st.button("Générer le rapport", type="primary"):
        photo_b64 = _img_to_b64(_get_best_photo_path(p_sel))
        logo_b64, logo_ext = _get_logo_b64()

        common_args = dict(
            row=row, df_ref=df_ref, df_full=df, poste=poste, lateralite=lateralite, anthro=anthro,
            selected_metrics=selected_metrics, use_relative=st.session_state.use_relative,
            themes=st.session_state[key_themes], dominant=dominant, weak=weak,
            strat_salle=strat_salle, strat_terrain=strat_terrain,
            photo_b64=photo_b64, logo_b64=logo_b64, logo_ext=logo_ext, staff_evals=staff_evals,
            current_session=sel_session, df_prev_session=df_prev_session, rdv_date=rdv_date,
            entretien_date=entretien_date, context_test=context_test,
            ref_group_label=ref_group_label, comp_zscores=comp_zscores,
        )

        if report_mode == "Préparation Physique":
            html_report = build_prepa_report(p_sel, radar_labels=radar_labels_prepa, radar_values=radar_values_prepa,
                                              groupes_prepa=GROUPES_PREPA, **common_args)
        elif report_mode == "Kiné / Prévention":
            html_report = build_kine_report(p_sel, radar_labels=radar_labels_kine, radar_values=radar_values_kine,
                                             antecedents=antecedents_kine, leg_overrides=leg_overrides,
                                             radar_vals_d=radar_vals_d_kine, **common_args)
        else:
            html_prepa = build_prepa_report(p_sel, radar_labels=radar_labels_prepa, radar_values=radar_values_prepa,
                                             groupes_prepa=GROUPES_PREPA, is_commun=True, **common_args)
            html_kine = build_kine_report(p_sel, radar_labels=radar_labels_kine, radar_values=radar_values_kine,
                                           antecedents=antecedents_kine, leg_overrides=leg_overrides,
                                           radar_vals_d=radar_vals_d_kine, is_commun=True, **common_args)
            parts_prepa = html_prepa.split(MARQUEUR_RECO)
            parts_kine = html_kine.split(MARQUEUR_DETAIL_START)[1].split(MARQUEUR_DETAIL_END)[0]
            html_report = parts_prepa[0] + parts_kine + MARQUEUR_RECO + parts_prepa[1]

        st.session_state["_last_report_html"] = html_report
        st.session_state["_last_report_player"] = p_sel
        st.success("Rapport généré.")
    _render_report_download_section(pdf_ready, key_prefix="bottom")
    st.markdown("---")
    with st.expander("📊 Plan Hebdomadaire par Groupe de KPI (document département)", expanded=False):
        st.caption(
            "Document de référence collectif (indépendant du joueur sélectionné ci-dessus) — "
            "le tableau RFD / Force / Prévention / Répétition des efforts / Composition corporelle "
            "du plan d'individualisation, prêt à imprimer/partager."
        )
        if st.button("🖼️ Générer le document", key="gen_kpi_dept_plan"):
            logo_b64_dept, logo_ext_dept = _get_logo_b64()
            st.session_state["_last_dept_plan_html"] = build_kpi_department_plan_html(logo_b64_dept, logo_ext_dept)

        if "_last_dept_plan_html" in st.session_state:
            dept_plan_html = st.session_state["_last_dept_plan_html"]
            b64_dept_html = base64.b64encode(dept_plan_html.encode("utf-8")).decode("utf-8")

            dept_pdf_bytes, dept_pdf_error = None, None
            if pdf_ready:
                if st.session_state.get("_last_dept_pdf_source") != dept_plan_html:
                    try:
                        st.session_state["_last_dept_pdf_bytes"] = html_to_pdf_bytes(dept_plan_html)
                        st.session_state["_last_dept_pdf_error"] = None
                    except Exception as e:
                        st.session_state["_last_dept_pdf_bytes"] = None
                        st.session_state["_last_dept_pdf_error"] = str(e)
                    st.session_state["_last_dept_pdf_source"] = dept_plan_html
                dept_pdf_bytes = st.session_state["_last_dept_pdf_bytes"]
                dept_pdf_error = st.session_state["_last_dept_pdf_error"]

            bd1, bd2 = st.columns(2)
            with bd1:
                st.markdown(
                    f'<a href="data:text/html;base64,{b64_dept_html}" download="Plan_Hebdomadaire_KPI.html">'
                    f'<button style="width:100%; background:{SDR_RED}; color:white; padding:10px 18px; border:none; border-radius:5px; font-weight:bold; cursor:pointer;">📄 TÉLÉCHARGER LE HTML</button></a>',
                    unsafe_allow_html=True,
                )
            with bd2:
                if pdf_ready:
                    if dept_pdf_bytes:
                        st.download_button("📑 TÉLÉCHARGER LE PDF", data=dept_pdf_bytes,
                                            file_name="Plan_Hebdomadaire_KPI.pdf", mime="application/pdf",
                                            width='stretch', key="dl_dept_plan_pdf")
                    else:
                        st.error(f"Échec de la génération PDF : {dept_pdf_error}")
                else:
                    st.button("📑 PDF indisponible", disabled=True, width='stretch', key="dl_dept_plan_pdf_disabled")

            if st.checkbox("Afficher l'aperçu du document", value=False, key="show_dept_plan_preview"):
                st.components.v1.html(dept_plan_html, height=500, scrolling=True)
    st.markdown("---")
    with st.expander("📅 Plan Hebdomadaire dédié au KPI", expanded=False):
        st.caption(
            "Extrait automatique du plan département : uniquement la colonne correspondant "
            "à l'axe d'amélioration actuel du joueur. Rien à saisir manuellement — le contenu "
            "vient du plan collectif ci-dessus (📊 Plan Hebdomadaire par Groupe de KPI)."
        )

        planning_key_suffix = f"{p_sel}_{sel_session}"
        _current_weak_for_kpi_plan = st.session_state.get(f"weak_{key_suffix}", saved_data_player.get("weak", ""))
        kpi_for_focus_plan = get_kpi_auto_fill(p_sel, _current_weak_for_kpi_plan)

        if not kpi_for_focus_plan:
            st.caption("ℹ️ Aucun KPI déterminé pour ce joueur (cf. section Entretien & Synthèse) — plan indisponible.")
        else:
            st.caption(f"KPI de ce joueur : **{kpi_for_focus_plan['kpi']}**")
            if st.button("🖼️ Générer le plan", key=f"gen_kpi_focus_{planning_key_suffix}", type="primary"):
                logo_b64_focus, logo_ext_focus = _get_logo_b64()
                st.session_state["_last_kpi_focus_html"] = build_kpi_focus_plan_html(
                    p_sel, poste, kpi_for_focus_plan["kpi"], logo_b64=logo_b64_focus, logo_ext=logo_ext_focus,
                )

            if "_last_kpi_focus_html" in st.session_state:
                kpi_focus_html = st.session_state["_last_kpi_focus_html"]
                b64_kpi_focus_html = base64.b64encode(kpi_focus_html.encode("utf-8")).decode("utf-8")

                kpi_focus_pdf_bytes, kpi_focus_pdf_error = None, None
                if pdf_ready:
                    if st.session_state.get("_last_kpi_focus_pdf_source") != kpi_focus_html:
                        try:
                            st.session_state["_last_kpi_focus_pdf_bytes"] = html_to_pdf_bytes(kpi_focus_html)
                            st.session_state["_last_kpi_focus_pdf_error"] = None
                        except Exception as e:
                            st.session_state["_last_kpi_focus_pdf_bytes"] = None
                            st.session_state["_last_kpi_focus_pdf_error"] = str(e)
                        st.session_state["_last_kpi_focus_pdf_source"] = kpi_focus_html
                    kpi_focus_pdf_bytes = st.session_state["_last_kpi_focus_pdf_bytes"]
                    kpi_focus_pdf_error = st.session_state["_last_kpi_focus_pdf_error"]

                bf1, bf2 = st.columns(2)
                with bf1:
                    st.markdown(
                        f'<a href="data:text/html;base64,{b64_kpi_focus_html}" download="Plan_{p_sel}.html">'
                        f'<button style="width:100%; background:{SDR_RED}; color:white; padding:10px 18px; border:none; border-radius:5px; font-weight:bold; cursor:pointer;">📄 TÉLÉCHARGER LE HTML</button></a>',
                        unsafe_allow_html=True,
                    )
                with bf2:
                    if pdf_ready:
                        if kpi_focus_pdf_bytes:
                            st.download_button("📑 TÉLÉCHARGER LE PDF", data=kpi_focus_pdf_bytes,
                                                file_name=f"Plan_{p_sel}.pdf", mime="application/pdf",
                                                width='stretch', key=f"dl_kpi_focus_pdf_{planning_key_suffix}")
                        else:
                            st.error(f"Échec de la génération PDF : {kpi_focus_pdf_error}")
                    else:
                        st.button("📑 PDF indisponible", disabled=True, width='stretch', key=f"dl_kpi_focus_pdf_disabled_{planning_key_suffix}")

                if st.checkbox("Afficher l'aperçu", value=False, key=f"show_kpi_focus_preview_{planning_key_suffix}"):
                    st.components.v1.html(kpi_focus_html, height=500, scrolling=True)
    st.markdown("---")
    with st.expander("🗂️ Génération en lot (plusieurs joueurs)", expanded=False):
        st.caption(
            "Produit un rapport par joueur avec les KPI cochées dans la barre latérale. "
            "Si un joueur n'a pas une KPI donnée, elle est automatiquement retirée de SON rapport "
            "(pas de case vide). Le texte d'entretien / thèmes / évaluations proviennent des réglages "
            "déjà sauvegardés pour chaque joueur (rien n'est généré automatiquement à leur place)."
        )

        batch_teams = st.multiselect(
            "Équipes à inclure", teams, default=[team_sel],
            help="Toutes les équipes définies dans la colonne 'Equipe' du fichier (PRO, Elite, Espoir, U17...).",
        )
        batch_team_players = sorted(df_session[df_session["Equipe"].isin(batch_teams)]["Joueur"].dropna().unique().tolist()) if batch_teams else []

        autres_joueurs = sorted(set(players_all := df_session["Joueur"].dropna().unique().tolist()) - set(batch_team_players))
        batch_extra_players = st.multiselect(
            "+ Ajouter des joueurs individuels (hors équipes ci-dessus)", autres_joueurs,
            help="Ex : intégrer 2-3 joueurs Élite/Espoir surclassés dans un lot PRO, sans prendre toute leur équipe.",
        )

        batch_players = batch_team_players + [p for p in batch_extra_players if p not in batch_team_players]
        st.caption(f"→ {len(batch_players)} joueur(s) sélectionné(s) pour le lot.")

        batch_export_pdf = st.checkbox("Exporter en PDF (sinon HTML)", value=pdf_ready, disabled=not pdf_ready)
        if not pdf_ready:
            st.caption("PDF indisponible dans cet environnement → le lot sera généré en HTML.")

        if st.button("🚀 Lancer la génération en lot", type="primary", disabled=not batch_players):
            cfg = BatchConfig(
                report_mode=report_mode,
                selected_metrics=selected_metrics,
                use_relative=st.session_state.use_relative,
                niveau_ref=choix_niveau,
                age_range=age_range,
                col_age=col_age,
                context_test=context_test,
                export_pdf=batch_export_pdf,
                force_pro_comparison_players=frozenset(batch_extra_players),
            )
            logo_b64_batch, logo_ext_batch = _get_logo_b64()

            progress_bar = st.progress(0.0, text="Démarrage...")

            def _on_progress(done, total, current_player):
                progress_bar.progress(done / total if total else 1.0, text=f"{done}/{total} — {current_player}")

            zip_bytes, batch_errors = build_batch_zip(
                batch_players, df_session, df, cfg, saved_data_all,
                key_suffix_fn=lambda pl: f"{pl}_{sel_session}",
                progress_callback=_on_progress,
                photo_lookup_fn=lambda pl: _img_to_b64(_get_best_photo_path(pl)),
                logo=(logo_b64_batch, logo_ext_batch),
            )
            progress_bar.empty()

            if batch_errors:
                with st.expander(f"⚠️ {len(batch_errors)} avertissement(s) pendant la génération"):
                    for err in batch_errors:
                        st.warning(err)

            st.success(f"{len(batch_players)} rapport(s) généré(s).")
            st.download_button(
                "📦 Télécharger le lot (.zip)", data=zip_bytes,
                file_name=f"Profilage_lot_{team_sel}_{sel_session}.zip", mime="application/zip",
                type="primary",
            )