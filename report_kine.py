# -*- coding: utf-8 -*-
"""
report_kine.py
===============
Construction du rapport HTML "Kiné / Prévention" : reprend build_kine_report
en s'appuyant sur les briques communes de html_components.py.
"""
from __future__ import annotations

from config import SDR_RED, GREEN, DARK, GROUPES_KINE, KINE_LABELS, BIODEX_TARGETS, BIODEX_CONFIG, ISAK_LABELS, ISAK_RADAR_MAX_MM, GREEN_TEXT
from data_loader import find_column, clean_numeric_value, is_inverted
from stats_engine import calculate_percentile, calculate_zscore, get_norm_info, get_value_for_metric
from rapport_charts import create_radar_chart_kine, create_biodex_radar_matplotlib, create_isak_radar
from html_components import (
    REPORT_CSS, get_metric_card_html, get_theme_card_html, get_zscore_gauge_html,
    get_legend_html, get_header_html, get_footer_html, get_trend_html,
    photo_or_placeholder_html, build_card_grid_html,
)

MARQUEUR_DETAIL_START = "<!-- MARQUEUR_DETAIL_START -->"
MARQUEUR_DETAIL_END = "<!-- MARQUEUR_DETAIL_END -->"


def _unit_with_rel(label: str, use_rel: bool) -> str:
    from config import UNITS
    unit = UNITS.get(label, "")
    return f"{unit}/kg" if (use_rel and unit) else unit


def _prioritize_by_antecedents(selected_metrics, antecedents: str):
    """Remonte en tête les métriques liées aux antécédents médicaux déclarés."""
    if not antecedents:
        return []
    ant_lower = antecedents.lower()
    prio = []
    for lbl in selected_metrics:
        lbl_lower = lbl.lower()
        is_prio = (
            ("ischio" in ant_lower and any(k in lbl_lower for k in ("ij", "ischio", "mixte")))
            or (("adducteur" in ant_lower or "pubalgie" in ant_lower) and any(k in lbl_lower for k in ("add", "abd", "squeeze")))
            or ("cheville" in ant_lower and "verseur" in lbl_lower)
            or ("quadri" in ant_lower and ("q conc" in lbl_lower or "quadri" in lbl_lower))
        )
        if is_prio:
            prio.append(lbl)
    return prio


def generate_kine_comment(z_dict: dict, avg_z) -> str:
    """Synthèse descriptive automatique du profil kiné/isocinétique (aide à la rédaction, à valider par le staff)."""
    if not z_dict or avg_z is None:
        return ""
    if avg_z < -1.0:
        pos = "très en dessous de la moyenne"
    elif avg_z < -0.5:
        pos = "légèrement en dessous de la moyenne"
    elif avg_z < 0.5:
        pos = "dans la moyenne"
    elif avg_z < 1.65:
        pos = "au-dessus de la moyenne"
    else:
        pos = "dans la zone élite"

    sorted_tests = sorted(z_dict.items(), key=lambda item: item[1])
    bottom_tests = [t[0] for t in sorted_tests[:2] if t[1] < -0.5]
    top_tests = [t[0] for t in sorted_tests[-2:] if t[1] > 0.5]

    text = f"Le profil kiné/isocinétique global se situe <b>{pos}</b> du groupe de référence (Z = {avg_z:.2f}). "
    if top_tests:
        text += f"Les valeurs tirant le profil vers le haut sont : <i>{', '.join(top_tests)}</i>. "
    if bottom_tests:
        text += f"Les points d'attention concernent : <i>{', '.join(bottom_tests)}</i>. "

    return f"""
    <div style="background:#f9f9f9; border-left:4px solid #3498DB; padding:10px; margin-top:10px; border-radius:4px; font-size:8.5pt; color:#444;">
        <div style="font-weight:bold; color:#3498DB; margin-bottom:4px; text-transform:uppercase; font-size:8pt;">Bilan descriptif Kiné / Isocinétisme</div>
        {text}
    </div>
    """


def _get_ratio_color(val):
    if val is None:
        return "#888"
    return "#D71920" if val < 0.8 else ("#F39C12" if val <= 1.0 else "#27AE60")


def _build_biodex_block(row, df_full):
    """Radar Biodex + tableau détaillé (Gauche/Droite/Objectif/LSI). Renvoie le HTML complet du bloc, ou "" si le joueur n'a aucune donnée isocinétique (évite un radar à plat et un tableau de tirets, notamment en génération en lot)."""
    poids_joueur = clean_numeric_value(row.get("Poids (kg)"))

    has_any_data = any(
        clean_numeric_value(row.get(find_column(df_full, item["g_raw"]) or item["g_raw"])) is not None
        or clean_numeric_value(row.get(find_column(df_full, item["d_raw"]) or item["d_raw"])) is not None
        for item in BIODEX_CONFIG
    )
    if not has_any_data:
        return ""

    rcats, r_l_rel, r_r_rel, r_norm, tbl_data = [], [], [], [], []

    for item in BIODEX_CONFIG:
        lbl = item["label"]
        rcats.append(lbl)
        val_norm_rel = BIODEX_TARGETS.get(lbl, 0)
        r_norm.append(val_norm_rel)

        col_g_rel = find_column(df_full, item["g_rel"]) or item["g_rel"]
        col_d_rel = find_column(df_full, item["d_rel"]) or item["d_rel"]
        v_g_rel = clean_numeric_value(row.get(col_g_rel))
        v_d_rel = clean_numeric_value(row.get(col_d_rel))
        r_l_rel.append(v_g_rel if v_g_rel is not None else 0)
        r_r_rel.append(v_d_rel if v_d_rel is not None else 0)

        col_g_raw = find_column(df_full, item["g_raw"]) or item["g_raw"]
        col_d_raw = find_column(df_full, item["d_raw"]) or item["d_raw"]
        v_g_raw = clean_numeric_value(row.get(col_g_raw))
        v_d_raw = clean_numeric_value(row.get(col_d_raw))

        s_lsi, c_lsi = "-", "#888"
        if v_g_raw is not None and v_d_raw is not None:
            mx = max(v_g_raw, v_d_raw)
            if mx > 0:
                lsi = ((v_d_raw - v_g_raw) / mx) * 100
                s_lsi = f"{lsi:.0f}%"
                c_lsi = "#D71920" if abs(lsi) > 10 else ("#F39C12" if abs(lsi) > 5 else "#27AE60")

        target_abs = f"{val_norm_rel * poids_joueur:.0f}" if poids_joueur and poids_joueur > 0 else "-"
        tbl_data.append({
            "label": lbl, "target": target_abs,
            "v_g": f"{v_g_raw:.0f}" if v_g_raw is not None else "-",
            "v_d": f"{v_d_raw:.0f}" if v_d_raw is not None else "-",
            "lsi": s_lsi, "c_lsi": c_lsi,
        })

    biodex_b64 = create_biodex_radar_matplotlib(rcats, r_l_rel, r_r_rel, r_norm)

    h_rows = "".join(
        f"<tr style='border-bottom:1px solid #eee;'><td style='padding:4px; color:#555;'>{it['label']}</td>"
        f"<td style='text-align:center; color:#666; font-weight:bold;'>{it['target']}</td>"
        f"<td style='text-align:center; color:#111; font-weight:bold;'>{it['v_g']}</td>"
        f"<td style='text-align:center; color:#111; font-weight:bold;'>{it['v_d']}</td>"
        f"<td style='text-align:center; color:{it['c_lsi']}; font-weight:bold;'>{it['lsi']}</td></tr>"
        for it in tbl_data
    )

    col_rm_g, col_rm_d = find_column(df_full, "Ratio Mixte (G)"), find_column(df_full, "Ratio Mixte (D)")
    val_rm_g = clean_numeric_value(row.get(col_rm_g)) if col_rm_g else None
    val_rm_d = clean_numeric_value(row.get(col_rm_d)) if col_rm_d else None
    s_rm_g = f"{val_rm_g:.2f}" if val_rm_g is not None else "-"
    s_rm_d = f"{val_rm_d:.2f}" if val_rm_d is not None else "-"
    h_rows += (
        "<tr style='border-top:2px solid #ccc; background-color:#f9f9f9;'>"
        "<td style='padding:4px; font-weight:bold; color:#111;'>Ratio Mixte</td><td style='text-align:center;'>-</td>"
        f"<td style='text-align:center; font-weight:bold; color:{_get_ratio_color(val_rm_g)};'>{s_rm_g}</td>"
        f"<td style='text-align:center; font-weight:bold; color:{_get_ratio_color(val_rm_d)};'>{s_rm_d}</td>"
        "<td style='text-align:center;'>-</td></tr>"
    )

    return f"""
    <div class="no-break" style="margin-bottom:16px;">
        <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid {SDR_RED}; padding-bottom:4px; margin-bottom:12px;">RADAR BIODEX (VALEURS RELATIVES)</div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="width:50%; text-align:center;">
                <img src="data:image/png;base64,{biodex_b64}" style="width:100%; max-width:320px;">
            </div>
            <div style="width:48%;">
                <div style='text-align:center; font-size:9pt; font-weight:900; color:{SDR_RED}; margin-bottom:8px; text-transform:uppercase;'>Résultats Détaillés (Nm)</div>
                <table style='width:100%; border-collapse:collapse; font-size:7.5pt; font-family:sans-serif;'>
                    <tr style='background-color:#f0f0f0; color:#333; text-transform:uppercase; font-size:6.5pt;'>
                        <th style='padding:4px; text-align:left;'>Test</th>
                        <th style='padding:4px; text-align:center;'>Obj. (Nm)</th>
                        <th style='padding:4px; text-align:center;'>G (Nm)</th>
                        <th style='padding:4px; text-align:center;'>D (Nm)</th>
                        <th style='padding:4px; text-align:center;'>LSI</th>
                    </tr>
                    {h_rows}
                </table>
            </div>
        </div>
    </div>
    """


def _build_asymmetry_block(selected_metrics, df_full, row, use_relative, lateralite, leg_overrides):
    pairs = set()
    for m in selected_metrics:
        if "(G)" in m and m != "Ratio Mixte (G)":
            base = m.replace("(G)", "").strip()
            if f"{base} (D)" in selected_metrics:
                pairs.add((base, m, f"{base} (D)"))
    if not pairs:
        return ""

    blocks = []
    for base, g_lbl, d_lbl in pairs:
        c_g, c_d = find_column(df_full, g_lbl), find_column(df_full, d_lbl)
        use_rel = use_relative.get(g_lbl, False) or use_relative.get(d_lbl, False)
        v_g = get_value_for_metric(row, df_full, c_g, use_rel)
        v_d = get_value_for_metric(row, df_full, c_d, use_rel)
        if not (v_g and v_d and max(v_g, v_d) > 0):
            continue

        diff_pct = abs(v_g - v_d) / max(v_g, v_d) * 100
        col_asym = GREEN if diff_pct < 10 else ("#F39C12" if diff_pct <= 15 else SDR_RED)

        if leg_overrides:
            lbl_dom, lbl_app = leg_overrides.get("frappe", "D"), leg_overrides.get("appui", "G")
        else:
            lat_val = str(lateralite).strip().upper()
            lbl_dom, lbl_app = ("D", "G") if lat_val != "G" else ("G", "D")
        v_dom = v_d if lbl_dom == "D" else v_g
        v_app = v_g if lbl_app == "G" else v_d
        deficit = f"Dom ({lbl_dom})" if v_dom < v_app else (f"Appui ({lbl_app})" if v_app < v_dom else "=")

        blocks.append(f"""
        <div class="no-break" style="background:#fff; border-top:3px solid {col_asym}; padding:6px; border-radius:4px; border-bottom:1px solid #eee; border-left:1px solid #eee; border-right:1px solid #eee; font-size:7.5pt; text-align:center; width: calc(25% - 5px); box-sizing:border-box;">
            <div style="font-weight:bold; color:#555; margin-bottom:4px; overflow-wrap: break-word;">{base}</div>
            <div style="font-size:11pt; font-weight:900; color:{col_asym};">{diff_pct:.1f}%</div>
            <div style="color:#666; font-size:6.5pt; margin-top:2px;">Dom: {v_dom:.1f} | App: {v_app:.1f} <br>Déficit: <b>{deficit}</b></div>
        </div>
        """)

    if not blocks:
        return ""
    return f"""
    <div style="margin-bottom:12px;">
        <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:6px;">PROFIL D'ASYMÉTRIE (Jambe Dominante / Appui)</div>
        <div style="font-size:7pt; color:#666; margin-bottom:8px; font-style:italic;">* Seuils indicatifs (&lt;10% vert, 10-15% orange, &gt;15% rouge). À valider par le staff médical. Convention utilisée : Dominante = Frappe.</div>
        {build_card_grid_html(blocks, per_row=4, gap_px=6)}
    </div>
    """


def isak_radar_data(row, df_full, selected_metrics):
    """
    Prépare les données du radar ISAK à partir des sites cochés dans la
    sidebar. Partagée entre le rapport (report_kine.py) et l'aperçu
    interactif (app.py) pour ne pas dupliquer cette logique à deux endroits.
    Retourne (labels_courts, valeurs_mm) — vides si moins de 3 sites
    disponibles (un radar à 1 ou 2 branches n'a pas de sens visuellement).
    """
    labels, values = [], []
    for label in ISAK_LABELS:
        if label not in selected_metrics:
            continue
        col = find_column(df_full, label)
        val = clean_numeric_value(row.get(col), col) if col else None
        if val is None:
            continue
        labels.append(label.replace("Isak ", ""))
        values.append(val)
    if len(labels) < 3:
        return [], []
    return labels, values


def _build_isak_block(row, df_full, selected_metrics):
    """Radar ISAK (plis cutanés, mm) + tableau brut. Renvoie "" si moins de 3 sites sélectionnés/disponibles pour ce joueur."""
    labels, values = isak_radar_data(row, df_full, selected_metrics)
    if not labels:
        return ""

    radar_b64 = create_isak_radar(labels, values, max_scale=ISAK_RADAR_MAX_MM)
    somme_8 = sum(values) if len(values) == 8 else None
    somme_txt = f"<div style='margin-top:8px; font-size:8pt; color:#666;'><b>Somme des {len(values)} plis mesurés :</b> {sum(values):.1f} mm{' (Σ8 complet)' if somme_8 else ' (partiel — tous les sites ne sont pas sélectionnés)'}</div>"

    rows_html = "".join(
        f"<tr style='border-bottom:1px solid #eee;'><td style='padding:4px; color:#555;'>{lbl}</td><td style='text-align:center; color:#111; font-weight:bold;'>{val:.1f}</td></tr>"
        for lbl, val in zip(labels, values)
    )

    return f"""
    <div class="no-break" style="margin-bottom:16px;">
        <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid {SDR_RED}; padding-bottom:4px; margin-bottom:12px;">COMPOSITION CORPORELLE — PROTOCOLE ISAK (PLIS CUTANÉS, MM)</div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="width:50%; text-align:center;">
                <img src="data:image/png;base64,{radar_b64}" style="width:100%; max-width:320px;">
            </div>
            <div style="width:48%;">
                <table style='width:100%; border-collapse:collapse; font-size:7.5pt; font-family:sans-serif;'>
                    <tr style='background-color:#f0f0f0; color:#333; text-transform:uppercase; font-size:6.5pt;'>
                        <th style='padding:4px; text-align:left;'>Site</th><th style='padding:4px; text-align:center;'>Mesure (mm)</th>
                    </tr>
                    {rows_html}
                </table>
                {somme_txt}
            </div>
        </div>
        <div style="font-size:6.5pt; color:#999; margin-top:6px; font-style:italic;">Valeurs descriptives (pas de norme club fixée) — l'échelle du radar est bornée à {ISAK_RADAR_MAX_MM}mm.</div>
    </div>
    """


def build_kine_report(
    player_name, row, df_ref, df_full, poste, lateralite, anthro,
    selected_metrics, use_relative, radar_labels, radar_values,
    themes, dominant, weak, strat_salle, strat_terrain,
    photo_b64, logo_b64, logo_ext, staff_evals, current_session, df_prev_session,
    rdv_date, entretien_date, context_test, ref_group_label, comp_zscores,
    antecedents, leg_overrides, radar_vals_d, is_commun: bool = False,
) -> str:
    from html_components import get_percentile_bar_html, get_percentile_color, format_pct

    sorted_groups = list(GROUPES_KINE.items())
    prioritaires = _prioritize_by_antecedents(selected_metrics, antecedents)
    if prioritaires:
        sorted_groups.insert(0, ("Priorité Antécédents", prioritaires))

    # --- Cartes métriques ------------------------------------------------------------
    metric_cards_by_group = {}
    for group, labels in sorted_groups:
        cards = []
        for label in labels:
            if label not in selected_metrics:
                continue
            if group != "Priorité Antécédents" and antecedents and label in prioritaires:
                continue
            col = find_column(df_full, label)
            use_rel = use_relative.get(label, False)
            value = get_value_for_metric(row, df_full, col, use_rel) if col else None
            # Retrait automatique si le joueur n'a pas cette donnée (cf. report_prepa.py pour le détail).
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
                report_mode_label="Kiné / Prévention", is_report=True, is_kine=True,
            ))
        if cards:
            metric_cards_by_group[group] = cards

    metrics_html = "".join(
        f"""
        <div class="no-break" style="margin-bottom:12px;">
            <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                <span>{group}</span>
            </div>
            {build_card_grid_html(cards, per_row=3, gap_px=6)}
        </div>
        """
        for group, cards in metric_cards_by_group.items()
    )

    asym_html = _build_asymmetry_block(selected_metrics, df_full, row, use_relative, lateralite, leg_overrides)

    # --- Ratio Mixte -------------------------------------------------------------------
    ratio_html = ""
    if "Ratio Mixte (G)" in selected_metrics or "Ratio Mixte (D)" in selected_metrics:
        cards = []
        for lbl in ["Ratio Mixte (G)", "Ratio Mixte (D)"]:
            if lbl not in selected_metrics:
                continue
            c = find_column(df_full, lbl)
            v = clean_numeric_value(row.get(c), c) if c else None
            if v is None:
                continue  # retrait automatique si le joueur n'a pas cette donnée
            _, p = calculate_percentile(df_ref, c, v)
            v_str = f"{v:.2f}"
            cards.append(f"""
                <div class="no-break" style="background:#fff; border:1px solid #eee; border-radius:6px; padding:8px; width: calc(50% - 3px); box-sizing:border-box;">
                    <div style="display:flex; justify-content:space-between; align-items:baseline;">
                        <div style="font-size:7.5pt; font-weight:bold; color:#555; overflow-wrap: break-word;">{lbl}</div>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:2px;">
                        <div style="font-size:12pt; font-weight:900; color:{DARK};">{v_str}</div>
                        <div style="font-size:7.5pt; font-weight:900; color:{get_percentile_color(p)};">{format_pct(p)}</div>
                    </div>
                    {get_percentile_bar_html(p)}
                </div>
            """)
        if cards:
            ratio_html = f"""
            <div style="margin-bottom:12px;">
                <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:6px;">RATIO MIXTE (Fonctionnel Ischio-Jambiers)</div>
                {build_card_grid_html(cards, per_row=2, gap_px=6)}
                <div style="margin-top:8px; border:1px dashed #ccc; padding:10px; border-radius:4px; font-size:8pt; color:#666; min-height:50px;">
                    <i>Espace réservé à l'interprétation du staff médical / préparation physique :</i><br><br>
                </div>
            </div>
            """
        # sinon (cards vide) : aucune des deux valeurs n'existe pour ce joueur -> bloc entièrement omis

    biodex_html = _build_biodex_block(row, df_full)
    isak_html = _build_isak_block(row, df_full, selected_metrics)

    # --- Commentaire descriptif automatique --------------------------------------------
    kine_z_dict = {}
    for label in selected_metrics:
        if label in KINE_LABELS:
            col = find_column(df_full, label)
            use_rel = use_relative.get(label, False)
            val = get_value_for_metric(row, df_full, col, use_rel) if col else None
            z = calculate_zscore(df_ref, col, val, use_rel)
            if z is not None:
                kine_z_dict[label] = z
    avg_kine_z = sum(kine_z_dict.values()) / len(kine_z_dict) if kine_z_dict else None
    # (kine_comment_html calculé mais non inséré dans le gabarit d'origine — conservé
    #  disponible pour insertion future si le staff le souhaite)
    _ = generate_kine_comment(kine_z_dict, avg_kine_z) if avg_kine_z is not None else ""

    # --- Z-scores composites, radar, légende --------------------------------------------
    zscore_html = ""
    if comp_zscores:
        zscore_html = f"""
        <div style="margin-bottom:20px;">
            <div class="keep-with-next" style="font-weight:900; color:{SDR_RED}; font-size:10pt; text-transform:uppercase; border-bottom:2px solid #eee; padding-bottom:4px; margin-bottom:12px;">INDICES COMPOSITES (Z-SCORES)</div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; justify-content:flex-start;">
        """
        for group, data in comp_zscores.items():
            if group in GROUPES_KINE:
                zscore_html += get_zscore_gauge_html(group, data["score"], data["count"])
        zscore_html += "</div></div>"

    radar_b64 = create_radar_chart_kine(radar_labels, radar_values, radar_vals_d) if radar_labels else ""
    radar_html = (
        f'''<div class="no-break" style="text-align:center; margin: 10px 0;">
        <img src="data:image/png;base64,{radar_b64}" style="width:100%; max-width:380px;">
        <div style="font-size:6.5pt; color:#666; margin-top:4px;">Radar Kiné : % par rapport à l'objectif (Cible = 100%, plage affichée 50%-150%). Seuils : <span style="color:#D71920;">Rouge &lt;80%</span>, <span style="color:#F39C12;">Orange 80-100%</span>, <span style="color:#27AE60;">Vert 100-120%</span>, <span style="color:#00E5FF;">Bleu &gt;120%</span>.</div>
        </div>'''
        if radar_b64 else "<p style='font-size:8pt; color:#999; text-align:center;'>Aucune variable sélectionnée pour le radar.</p>"
    )

    themes_html = "".join(get_theme_card_html(t, is_report=True) for t in themes) or \
        "<p style='margin:0; font-size:9pt; color:#999;'>Aucune recommandation thématique définie.</p>"

    age_html, taille_html, poids_html = (
        f"{str(anthro.get('Age', '-')).strip()} <span style='font-size:7pt; color:#666; font-weight:normal;'>ans</span>" if str(anthro.get("Age", "-")).strip() != "-" else "-",
        f"{str(anthro.get('Taille', '-')).strip()} <span style='font-size:7pt; color:#666; font-weight:normal;'>cm</span>" if str(anthro.get("Taille", "-")).strip() != "-" else "-",
        f"{str(anthro.get('Poids', '-')).strip()} <span style='font-size:7pt; color:#666; font-weight:normal;'>kg</span>" if str(anthro.get("Poids", "-")).strip() != "-" else "-",
    )
    photo_img = photo_or_placeholder_html(photo_b64, player_name[:1])
    logo_img = f'<img src="data:image/{logo_ext};base64,{logo_b64}" style="width:75px; margin-bottom:5px;">' if logo_b64 else ""
    context_html = f"<div style='margin-top:10px; font-size:8.5pt; color:#666; overflow-wrap: break-word;'><b>Contexte du test :</b> {context_test}</div>" if context_test else ""
    header_html = get_header_html(player_name, poste, lateralite, age_html, taille_html, poids_html,
                                   context_html, photo_img, logo_img, ref_group_label, n_ref=len(df_ref))

    dominant_txt = (dominant or "").strip()
    weak_txt = (weak or "").strip()
    strat_salle_txt = (strat_salle or "").strip()
    strategy_html = f"""
        <div class="no-break" style="padding:10px 14px; margin-bottom:10px; border-radius:6px; border-left:6px solid #3498DB; background:#f0f7fd; word-wrap: break-word; overflow-wrap: break-word;">
            <div style="color:#3498DB; font-weight:bold; font-size:9pt; margin-bottom:4px;">STRATÉGIE DE PRISE EN CHARGE</div>
            <div style="font-size:8.5pt; color:#333; white-space: pre-wrap; margin:0; padding:0;">{strat_salle_txt}</div>
        </div>
    """

    if is_commun:
        return f"""
{MARQUEUR_DETAIL_START}
        <div class="page-break"></div>
        <div class="report-section">
            <div class="no-break" style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 16px;">
                <h2 style="margin:0; color:{DARK}; font-size:14pt; text-transform:uppercase;">Détail des Métriques (Kiné)</h2>
                <div style="font-size:10pt; color:#666; font-weight:bold;">{player_name}</div>
            </div>
            {zscore_html}
            {radar_html}
            {asym_html}
            {ratio_html}
            {biodex_html}
            {isak_html}
            {metrics_html}
        </div>
{MARQUEUR_DETAIL_END}
        """

    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">{REPORT_CSS}</head><body>
    <div class="report-container">
        <div class="report-section">
            {header_html}
            {zscore_html}
            {radar_html}
            {get_legend_html(compact=False)}
        </div>

        <div class="page-break"></div>
        <div class="report-section">
            <div class="no-break" style="display:flex; justify-content:space-between; align-items:center; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 16px;">
                <h2 style="margin:0; color:{DARK}; font-size:14pt; text-transform:uppercase;">Détail des Métriques</h2>
                <div style="font-size:10pt; color:#666; font-weight:bold;">{player_name}</div>
            </div>
            {asym_html}
            {ratio_html}
            {biodex_html}
            {isak_html}
            {metrics_html}
        </div>

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

        {get_footer_html()}
    </div>
    </body></html>
    """