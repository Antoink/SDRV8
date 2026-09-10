# -*- coding: utf-8 -*-
"""
report_prepa.py
=================
Construction du rapport HTML "Préparation Physique".

Ce module reprend la logique de l'ancienne fonction build_prepa_report,
mais s'appuie sur les briques communes de html_components.py (carte
métrique, header, footer, légende, CSS) pour éliminer la duplication avec
report_kine.py. Le rendu visuel final est inchangé.
"""
from __future__ import annotations

from config import SDR_RED, GREEN, DARK, GROUPES_AVEC_RADAR_DEDIE, GREEN_TEXT
from data_loader import find_column, is_inverted
from stats_engine import (
    calculate_percentile, calculate_zscore, get_norm_info, get_value_for_metric,
)
from rapport_charts import create_radar_chart, create_evolution_chart, note_bruit_mesure
from html_components import (
    REPORT_CSS, get_metric_card_html, get_theme_card_html, get_zscore_gauge_html,
    get_legend_html, get_header_html, get_footer_html, get_trend_html,
    photo_or_placeholder_html, build_card_grid_html,
)

# Marqueur utilisé pour découper le rapport quand on assemble le mode "Commun"
MARQUEUR_RECO = "<!-- MARQUEUR_RECO -->"


def _anthro_html(anthro: dict):
    age_val = str(anthro.get("Age", "-")).strip()
    taille_val = str(anthro.get("Taille", "-")).strip()
    poids_val = str(anthro.get("Poids", "-")).strip()
    age_html = f"{age_val} <span style='font-size:7pt; color:#666; font-weight:normal;'>ans</span>" if age_val != "-" else "-"
    taille_html = f"{taille_val} <span style='font-size:7pt; color:#666; font-weight:normal;'>cm</span>" if taille_val != "-" else "-"
    poids_html = f"{poids_val} <span style='font-size:7pt; color:#666; font-weight:normal;'>kg</span>" if poids_val != "-" else "-"
    return age_html, taille_html, poids_html


def build_prepa_report(
    player_name, row, df_ref, df_full, poste, lateralite, anthro,
    selected_metrics, use_relative, radar_labels, radar_values,
    themes, dominant, weak, strat_salle, strat_terrain,
    photo_b64, logo_b64, logo_ext, staff_evals, current_session, df_prev_session,
    rdv_date, entretien_date, context_test, ref_group_label, comp_zscores,
    groupes_prepa: dict, is_commun: bool = False,
) -> str:
    # --- Cartes métriques regroupées ---------------------------------------------------
    metric_cards_by_group = {}
    group_radar_html = {}
    for group, labels in groupes_prepa.items():
        cards = []
        is_dedicated_radar_group = group in GROUPES_AVEC_RADAR_DEDIE
        radar_pct_labels, radar_pct_values = [], []
        for label in labels:
            if label not in selected_metrics:
                continue
            col = find_column(df_full, label)
            use_rel = use_relative.get(label, False)
            value = get_value_for_metric(row, df_full, col, use_rel) if col else None
            # POURQUOI : en génération en lot (plusieurs joueurs, mêmes KPI
            # cochées), tous les joueurs n'ont pas forcément passé chaque
            # test. Plutôt qu'afficher une carte avec un tiret "-" (bruit
            # visuel, laisse penser à une donnée manquante à investiguer),
            # on retire silencieusement la métrique du rapport de CE joueur
            # si elle n'a pas de valeur. Ce comportement s'applique aussi
            # en génération individuelle (cohérence).
            if value is None:
                continue
            unit = _unit_with_rel(label, use_rel)
            _, pct = calculate_percentile(df_ref, col, value, use_rel)
            norm_txt, norm_color = get_norm_info(label, value, use_rel, df_ref=df_ref, col=col)
            z_score = calculate_zscore(df_ref, col, value, use_rel)
            prev_val = None
            if df_prev_session is not None and col in df_prev_session.columns:
                prev_val = get_value_for_metric(df_prev_session.iloc[0], df_full, col, use_rel)
            trend_html = get_trend_html(value, prev_val, label, is_inverted)
            eval_data = staff_evals.get(label)
            cards.append(get_metric_card_html(
                label, value, unit, pct, z_score, eval_data, trend_html, norm_txt, norm_color,
                report_mode_label="Préparation Physique", is_report=True, is_kine=False,
                full_width=is_dedicated_radar_group, styled=(group == "Vitesse / GPS"),
            ))
            if pct is not None:
                radar_pct_labels.append(label.replace(" (1080)", "").strip())
                radar_pct_values.append(pct)
        if cards:
            metric_cards_by_group[group] = cards
            if is_dedicated_radar_group and len(radar_pct_labels) >= 3:
                radar_b64_group = create_radar_chart(radar_pct_labels, radar_pct_values)
                if group == "Vitesse / GPS":
                    # Bloc "vedette" de la page 1 : le radar doit dominer
                    # visuellement (60% de la largeur), les cartes de
                    # données restent secondaires (40%) pour ne pas
                    # écraser le graphique.
                    group_radar_html[group] = (
                        f'<div class="no-break" style="display:flex; justify-content:space-between; align-items:center; gap:14px;">'
                        f'<div style="width:60%; text-align:center;">'
                        f'<img src="data:image/png;base64,{radar_b64_group}" style="width:100%; max-width:560px;">'
                        f'<div style="font-size:7pt; color:#999; font-style:italic;">Percentile par rapport à : {ref_group_label}</div>'
                        f'</div>'
                        f'<div style="width:37%; display:flex; flex-direction:column; gap:8px;">{"".join(cards)}</div>'
                        f'</div>'
                    )
                else:
                    # Mise en page façon bloc Biodex : radar à gauche (50%), KPI
                    # empilés verticalement à droite (48%), pleine largeur de page.
                    group_radar_html[group] = (
                        f'<div class="no-break" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">'
                        f'<div style="width:50%; text-align:center;">'
                        f'<img src="data:image/png;base64,{radar_b64_group}" style="width:100%; max-width:320px;">'
                        f'<div style="font-size:6.5pt; color:#999; font-style:italic;">Percentile par rapport à : {ref_group_label}</div>'
                        f'</div>'
                        f'<div style="width:48%; display:flex; flex-direction:column; gap:6px;">{"".join(cards)}</div>'
                        f'</div>'
                    )

    # Le bloc Vitesse/GPS est retiré des groupes "page 2" pour être affiché
    # en tête de la page 1, avant même le radar composite principal — de
    # façon totalement autonome (son propre z-score en pleine largeur, son
    # propre radar+cartes, sa propre légende), avant que le reste du
    # rapport (z-scores des autres groupes + radar composite) ne suive
    # comme d'habitude.
    gps_radar_block = group_radar_html.pop("Vitesse / GPS", "")
    metric_cards_by_group.pop("Vitesse / GPS", None)
    if gps_radar_block:
        gps_zscore_html = ""
        gps_zscore_data = comp_zscores.get("Vitesse / GPS")
        if gps_zscore_data:
            gps_zscore_html = f"""
            <div style="margin-bottom:10px; display:flex;">
                {get_zscore_gauge_html("Vitesse / GPS", gps_zscore_data["score"], gps_zscore_data["count"])}
            </div>
            """
        gps_radar_block = f"""
        <div class="no-break" style="margin-bottom:20px; padding-bottom:16px; border-bottom:2px solid #eee;">
            <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:11pt; text-transform:uppercase; border-bottom:2px solid {SDR_RED}; padding-bottom:4px; margin-bottom:10px;">Vitesse / GPS</div>
            {gps_zscore_html}
            {gps_radar_block}
            {get_legend_html(compact=True)}
        </div>
        """

    metrics_html = ""
    for group, cards in metric_cards_by_group.items():
        # Si le radar dédié a bien été construit, les cartes sont déjà
        # intégrées dedans (colonne de droite) -> pas de second rendu.
        # Sinon (ex: moins de 3 métriques dispo pour ce joueur), on revient
        # au rendu standard pour ne pas perdre les cartes.
        has_dedicated_radar = group in group_radar_html
        cards_block = "" if has_dedicated_radar else build_card_grid_html(cards, per_row=2, gap_px=8)
        metrics_html += f"""
        <div class="no-break" style="margin-bottom:12px;">
            <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                <span>{group}</span>
            </div>
            {group_radar_html.get(group, "")}
            {cards_block}
        </div>
        """

    # --- Indices composites (z-scores) --------------------------------------------------
    # Vitesse/GPS est exclu ici : il a son propre z-score dans son bloc
    # dédié plus bas (autonome, pleine largeur, avant tout le reste).
    zscore_html = ""
    if comp_zscores:
        zscore_html = f"""
        <div style="margin-bottom:20px;">
            <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:12px;">INDICES COMPOSITES (Z-SCORES)</div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; justify-content:flex-start;">
        """
        for group, data in comp_zscores.items():
            if group in groupes_prepa and group != "Vitesse / GPS":
                zscore_html += get_zscore_gauge_html(group, data["score"], data["count"])
        zscore_html += "</div></div>"

    # --- Radar & légende -----------------------------------------------------------------
    radar_b64 = create_radar_chart(radar_labels, radar_values) if radar_labels else ""
    radar_html = (
        f'<div class="no-break" style="text-align:center; margin: 5px 0;"><img src="data:image/png;base64,{radar_b64}" style="width:100%; max-width:450px;"></div>'
        if radar_b64 else "<p style='font-size:8pt; color:#999; text-align:center;'>Aucune variable sélectionnée pour le radar.</p>"
    )
    legend_html = get_legend_html(compact=True)

    themes_html = "".join(get_theme_card_html(t, is_report=True) for t in themes) or \
        "<p style='margin:0; font-size:9pt; color:#999;'>Aucune recommandation thématique définie.</p>"

    # --- En-tête ---------------------------------------------------------------------------
    age_html, taille_html, poids_html = _anthro_html(anthro)
    photo_img = photo_or_placeholder_html(photo_b64, player_name[:1])
    logo_img = f'<img src="data:image/{logo_ext};base64,{logo_b64}" style="width:75px; margin-bottom:5px;">' if logo_b64 else ""
    context_html = f"<div style='margin-top:10px; font-size:8.5pt; color:#666; overflow-wrap: break-word;'><b>Contexte du test :</b> {context_test}</div>" if context_test else ""
    header_html = get_header_html(player_name, poste, lateralite, age_html, taille_html, poids_html,
                                   context_html, photo_img, logo_img, ref_group_label, n_ref=len(df_ref))

    # --- Courbes d'évolution longitudinale (max 4, priorité aux indicateurs clés) --------
    top_metrics = [m for m in ("Vmax", "CMJ 2JB", "VMA", "Peak Force CMJ") if m in selected_metrics]
    if len(top_metrics) < 4:
        for m in selected_metrics:
            if m not in top_metrics and "Distance" not in m and "(G)" not in m and "(D)" not in m:
                top_metrics.append(m)
            if len(top_metrics) == 4:
                break

    evol_charts, has_evolution = "", False
    for m in top_metrics:
        col = find_column(df_full, m)
        if col:
            b64_chart = create_evolution_chart(df_full, player_name, col, m, use_relative.get(m, False))
            if b64_chart:
                evol_charts += (
                    '<div class="no-break" style="text-align:center; background:#fff; border:1px solid #eee; '
                    'border-radius:8px; padding:10px; margin-bottom:15px; width: calc(50% - 8px); box-sizing:border-box;">'
                    f'<img src="data:image/png;base64,{b64_chart}" style="width:100%; max-width:400px;"></div>'
                )
                has_evolution = True

    # --- Synthèse / stratégie -------------------------------------------------------------
    dominant_txt = (dominant or "").strip()
    weak_txt = (weak or "").strip()
    strat_salle_txt = (strat_salle or "").strip()
    strat_terrain_txt = (strat_terrain or "").strip()
    strategy_html = f"""
        <div class="no-break" style="padding:10px 14px; margin-bottom:10px; border-radius:6px; border-left:6px solid #3498DB; background:#f0f7fd; word-wrap: break-word; overflow-wrap: break-word;">
            <div style="color:#3498DB; font-weight:bold; font-size:9pt; margin-bottom:4px;">STRATÉGIE SALLE</div>
            <div style="font-size:8.5pt; color:#333; white-space: pre-wrap; margin:0; padding:0;">{strat_salle_txt}</div>
        </div>
        <div class="no-break" style="padding:10px 14px; margin-bottom:10px; border-radius:6px; border-left:6px solid #8E44AD; background:#f9f0fd; word-wrap: break-word; overflow-wrap: break-word;">
            <div style="color:#8E44AD; font-weight:bold; font-size:9pt; margin-bottom:4px;">STRATÉGIE TERRAIN</div>
            <div style="font-size:8.5pt; color:#333; white-space: pre-wrap; margin:0; padding:0;">{strat_terrain_txt}</div>
        </div>
    """

    doc_html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">{REPORT_CSS}</head><body>
    <div class="report-container">
        <div class="report-section">
            {header_html}
            {gps_radar_block}
            {zscore_html}
            {radar_html}
            {legend_html}
        </div>

        <div class="page-break"></div>
        <div class="report-section">
            <div class="no-break" style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 16px;">
                <h2 style="margin:0; color:{DARK}; font-size:14pt; text-transform:uppercase;">Détail des Métriques</h2>
                <div style="font-size:10pt; color:#666; font-weight:bold;">{player_name}</div>
            </div>
            {metrics_html}
        </div>

{MARQUEUR_RECO}
        <div class="page-break"></div>
        <div class="report-section">
            <div class="no-break" style="display:flex; align-items:center; gap: 20px; border-bottom: 3px solid {SDR_RED}; padding-bottom: 15px; margin-bottom: 20px;">
                {photo_img}
                <div>
                    <h1 style="margin:0; color:{SDR_RED}; font-size:24pt; text-transform:uppercase; line-height:1; overflow-wrap: break-word;">{player_name}</h1>
                    <div style="font-size:12pt; font-weight:bold; color:#555; text-transform:uppercase; margin-top:4px;">Bilan, Thématiques & Entretien</div>
                </div>
            </div>

            <div class="no-break" style="margin-bottom: 20px; margin-top: 10px;">
                <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:12px;">RECOMMANDATIONS THÉMATIQUES</div>
                <div style="display: flex; flex-wrap: wrap; gap: 15px;">{themes_html}</div>
            </div>

            <div class="no-break" style="margin-top:20px;">
                <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:12px;">SYNTHÈSE</div>
                <div class="no-break" style="padding:10px 14px; margin-bottom:10px; border-radius:6px; border-left:6px solid {GREEN}; background:#eefaf3; word-wrap: break-word; overflow-wrap: break-word;">
                    <div style="color:{GREEN_TEXT}; font-weight:bold; font-size:9pt; margin-bottom:4px;">POINT(S) FORT(S)</div>
                    <div style="font-size:8.5pt; color:#333; white-space: pre-wrap; margin:0; padding:0;">{dominant_txt}</div>
                </div>
                <div class="no-break" style="padding:10px 14px; margin-bottom:10px; border-radius:6px; border-left:6px solid {SDR_RED}; background:#fef5f5; word-wrap: break-word; overflow-wrap: break-word;">
                    <div style="color:{SDR_RED}; font-weight:bold; font-size:9pt; margin-bottom:4px;">AXES D'AMÉLIORATION</div>
                    <div style="font-size:8.5pt; color:#333; white-space: pre-wrap; margin:0; padding:0;">{weak_txt}</div>
                </div>
                {strategy_html}
            </div>

            <div class="no-break" style="margin-top:20px; border:1px solid #ccc; border-radius:8px; padding:15px; background:#fafafa;">
                <div style="font-weight:bold; color:#555; font-size:9pt; margin-bottom:8px; text-transform:uppercase;">Conclusion de l'entretien</div>
                <div style="display:flex; justify-content:space-between; font-size:8.5pt; margin-bottom:8px;">
                    <div><b>Date de l'entretien :</b> {entretien_date if entretien_date else "...................."}</div>
                </div>
                <div style="font-size:8.5pt;"><b>Prochain RDV / Test :</b> {rdv_date if rdv_date else "........................................"}</div>
            </div>
        </div>
    """

    if has_evolution:
        doc_html += f"""
        <div class="page-break"></div>
        <div class="report-section">
            <div class="no-break" style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 20px;">
                <h2 style="margin:0; color:{DARK}; font-size:14pt; text-transform:uppercase;">Suivi Longitudinal</h2>
                <div style="font-size:10pt; color:#666; font-weight:bold;">{player_name}</div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap:15px;">{evol_charts}</div>
            <div class="no-break" style="margin-top:20px; text-align:center; font-size:8pt; color:#666; font-style:italic;">
                {note_bruit_mesure()}
            </div>
        </div>
        """

    doc_html += f"""
        {get_footer_html()}
    </div>
    </body></html>
    """
    return doc_html


def _unit_with_rel(label: str, use_rel: bool) -> str:
    from config import UNITS
    unit = UNITS.get(label, "")
    return f"{unit}/kg" if (use_rel and unit) else unit