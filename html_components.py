# -*- coding: utf-8 -*-
"""
html_components.py
====================
Briques HTML réutilisables par les deux générateurs de rapport
(report_prepa.py et report_kine.py).

POURQUOI CE FICHIER EXISTE
---------------------------
Dans l'ancien script, la carte métrique, la légende, le CSS d'impression
étaient copiés-collés à l'identique dans build_prepa_report ET
build_kine_report (~150 lignes dupliquées). Le risque : corriger un bug
d'affichage dans un rapport et oublier l'autre (ce qui s'est déjà produit :
les tailles de police différaient légèrement entre le CSS des deux
fonctions). Ici, une seule version = une seule correction à faire.
"""
from __future__ import annotations

import re

from config import SDR_RED, GREEN, ORANGE, BLUE_ELITE, DARK, N_REF_MIN, GREEN_TEXT, ORANGE_TEXT, BLUE_ELITE_TEXT

# ---------------------------------------------------------------------------
# CSS commun (identique pour les deux rapports + le mode "Commun")
# ---------------------------------------------------------------------------
REPORT_CSS = f"""
<style>
    body {{ font-family: 'Helvetica', 'Arial', sans-serif; background: #eee; margin:0; padding:0;
            -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
    .report-container {{ background: white; max-width: 210mm; margin: 10px auto; box-shadow: 0 0 10px rgba(0,0,0,0.1);
                          padding: 10mm 15mm 20mm 15mm; box-sizing: border-box; position: relative; }}
    .page-break {{ page-break-before: always; margin: 0; padding: 0; }}
    .no-break {{ page-break-inside: avoid; break-inside: avoid; }}
    .keep-with-next {{ page-break-after: avoid; break-after: avoid; }}
    .footer-print {{ display: none; }}

    @media print {{
        @page {{ size: A4; margin: 10mm 15mm; }}
        body {{ background: white; margin: 0; padding: 0; }}
        .report-container {{ margin: 0; box-shadow: none; max-width: 100%; padding: 0; width: 100%; }}
        .page-break {{ margin-top: 0; padding-top: 0; }}
        .footer-print {{ display: flex !important; position: fixed; bottom: 0; left: 0; right: 0;
                          justify-content: space-between; font-size: 7pt; color: #707070;
                          border-top: 1px solid #eee; padding: 5px 0 0 0; background: white; }}
    }}
</style>
"""


def get_percentile_color(pct) -> str:
    if pct is None:
        return "#888"
    pct = max(0, min(100, pct))
    if pct < 33:
        return SDR_RED
    if pct < 66:
        return ORANGE
    if pct < 95:
        return GREEN
    return BLUE_ELITE


def get_percentile_bar_html(pct) -> str:
    if pct is None:
        return ""
    pct = max(0, min(100, pct))
    marker_color = get_percentile_color(pct)
    return (
        f'<div style="position:relative; width:100%; height:6px; border-radius:3px; margin-top:6px; '
        f'background:linear-gradient(90deg, {SDR_RED} 0%, {SDR_RED} 33%, {ORANGE} 33%, {ORANGE} 66%, '
        f'{GREEN} 66%, {GREEN} 95%, {BLUE_ELITE} 95%, {BLUE_ELITE} 100%); opacity:0.3;">'
        f'<div style="position:absolute; left:calc({pct}% - 3px); top:-3px; width:6px; height:12px; '
        f'background:{marker_color}; opacity:1; border-radius:2px; border:1px solid white; '
        f'box-shadow:0 1px 2px rgba(0,0,0,0.4);"></div></div>'
    )


def format_pct(pct) -> str:
    if pct is None:
        return "-"
    p = int(pct)
    if p >= 33:
        return f"Top {max(1, 100 - p)}%" if p >= 66 else f"{p}%"
    return f"{max(1, p)}%"


def get_zscore_gauge_html(group: str, z, count: int) -> str:
    if z is None:
        return ""
    z_clamped = max(-2.0, min(2.0, z))
    pct = (z_clamped + 2) / 4 * 100

    if z < -1.0:
        label, col = "Très en dessous", SDR_RED
    elif z < -0.5:
        label, col = "En dessous", ORANGE
    elif z < 0.5:
        label, col = "Dans la moyenne", "#888"
    elif z < 1.65:
        label, col = "Au-dessus", GREEN
    else:
        label, col = "Élite", BLUE_ELITE

    return f"""
    <div class="no-break" style="margin-bottom:6px; background:#fff; border:1px solid #eee; border-radius:6px; padding:5px 10px; box-shadow:0 1px 2px rgba(0,0,0,0.05); min-width: 250px; flex: 1;">
        <div style="display:flex; justify-content:space-between; margin-bottom:2px; font-size:8pt; font-weight:bold; color:#444;">
            <span>{group} <span style="font-size:6.5pt; color:#666; font-weight:normal;">({count})</span></span>
            <span style="color:{col};">{label}</span>
        </div>
        <div style="position:relative; width:100%; height:6px; border-radius:3px; background:linear-gradient(90deg, {SDR_RED} 0%, {ORANGE} 25%, #ddd 50%, {GREEN} 75%, {BLUE_ELITE} 100%); opacity:0.6;">
            <div style="position:absolute; left:calc({pct}% - 3px); top:-3px; width:6px; height:12px; background:#333; border-radius:3px; border:1px solid #fff; box-shadow:0 1px 2px rgba(0,0,0,0.5);"></div>
        </div>
        <div style="display:flex; justify-content:space-between; margin-top:4px; font-size:5pt; color:#707070;">
            <span>-2 SD</span><span>Moyenne</span><span>+2 SD</span>
        </div>
    </div>
    """


def get_trend_html(curr_val, prev_val, label: str, is_inverted_fn) -> str:
    if curr_val is None or prev_val is None:
        return ""
    delta = curr_val - prev_val
    if abs(delta) < 0.01:
        return "<span style='font-size:7pt; color:#666;'>→ (=)</span>"
    is_good = (delta > 0) if not is_inverted_fn(label) else (delta < 0)
    col = GREEN if is_good else SDR_RED
    arr = "↗" if delta > 0 else "↘"
    sign = "+" if delta > 0 else ""
    return f"<span style='font-size:8pt; color:{col}; font-weight:bold; margin-left:6px;'>{arr} {sign}{delta:.2f}</span>"


def build_card_grid_html(cards: list, per_row: int, gap_px: int = 8) -> str:
    """
    Regroupe une liste de cartes en grille via un vrai tableau HTML
    (<table>), une ligne par rangée de `per_row` cartes.

    POURQUOI UN TABLEAU ET NON UN CONTENEUR FLEX : WeasyPrint a un bug de
    pagination avec les conteneurs flex (`display:flex`) — même avec
    `page-break-inside: avoid` posé sur chaque carte ET sur chaque rangée
    individuellement, une carte peut se retrouver tranchée en deux si la
    limite de page tombe au milieu. Les tableaux HTML, eux, ont une
    pagination beaucoup plus fiable et mature dans WeasyPrint (déjà
    éprouvé sur les tableaux Biodex/ISAK/plan département du rapport, qui
    n'ont jamais ce problème) : une ligne de tableau (<tr>) ne se coupe
    jamais au milieu, elle bascule entièrement sur la page suivante si
    elle ne tient pas.

    Chaque carte arrive avec sa propre largeur en pourcentage calculée
    pour un ancien conteneur flex (ex: "width: calc(25% - 5px);
    display:inline-block;") — cette largeur est neutralisée ici
    (remplacée par 100% du <td>, qui porte lui-même la vraie largeur de
    colonne) pour éviter un double calcul de pourcentage imbriqué.
    """
    if not cards:
        return ""
    # Neutralise la largeur/affichage internes de chaque carte : c'est
    # maintenant le <td> qui porte la largeur de colonne.
    normalized_cards = [
        re.sub(r"width:\s*calc\([^)]*\);", "width:100%;", re.sub(r"display:\s*inline-block;", "display:block;", card))
        for card in cards
    ]
    rows = [normalized_cards[i:i + per_row] for i in range(0, len(normalized_cards), per_row)]
    col_width = 100 / per_row
    trs = []
    for row in rows:
        tds = "".join(
            f'<td style="width:{col_width}%; padding:0 {gap_px // 2}px {gap_px}px {gap_px // 2}px; vertical-align:top;">{card}</td>'
            for card in row
        )
        tds += '<td style="width:{}%;"></td>'.format(col_width) * (per_row - len(row))
        trs.append(f"<tr>{tds}</tr>")
    return f'<table style="width:100%; border-collapse:collapse; table-layout:fixed;"><tbody>{"".join(trs)}</tbody></table>'


def get_metric_card_html(label, value, unit, pct, z_score, eval_data, trend_html,
                          norm_txt, norm_color, report_mode_label: str,
                          is_report: bool = False, is_kine: bool = False, full_width: bool = False,
                          styled: bool = False) -> str:
    """Carte d'affichage d'une métrique (valeur + percentile + objectif)."""
    val_str = "-" if value is None else (f"{int(value)}" if float(value).is_integer() else f"{value:.2f}")
    label_disp = label.replace("(G)", "· G").replace("(D)", "· D")
    pct_color = get_percentile_color(pct)

    pdc_html = ""
    if unit == "N/kg" and value is not None:
        pdc_html = f"<span style='font-size:9pt; color:#666; font-weight:normal; margin-left:6px;'>&middot; &approx;{value/9.81:.2f}&times; PDC</span>"

    z_html = f"<span style='font-size:7.5pt; color:#666; font-weight:normal; margin-left:8px;'>(Z: {z_score:.2f})</span>" if z_score is not None else ""

    eval_html = ""
    if eval_data:
        if eval_data["statut"] == "Acquis":
            eval_html = f"<div style='margin-top:6px; padding-top:4px; border-top:1px solid #eee; font-size:7.5pt; color:{GREEN_TEXT}; font-weight:bold;'>Objectif Acquis</div>"
        elif eval_data["statut"] == "Proche":
            eval_html = f"<div style='margin-top:6px; padding-top:4px; border-top:1px solid #eee; font-size:7.5pt; color:{ORANGE_TEXT}; font-weight:bold;'>Proche de l'objectif</div>"
        else:
            obj_str = eval_data.get("objectif", "N/A")
            delai_str = eval_data.get("delai", "")
            if report_mode_label == "Préparation Physique" or not delai_str or delai_str == "Aucun":
                eval_html = f"<div style='margin-top:6px; padding-top:4px; border-top:1px solid #eee; font-size:7.5pt; color:{SDR_RED};'><b>Non Acquis</b> | Obj: <b>{obj_str}</b></div>"
            else:
                eval_html = f"<div style='margin-top:6px; padding-top:4px; border-top:1px solid #eee; font-size:7.5pt; color:{SDR_RED};'><b>Non Acquis</b> | Obj: <b>{obj_str}</b> | Délai: <b>{delai_str}</b></div>"

    bar_html = get_percentile_bar_html(pct)

    if styled:
        # Présentation "vedette" pour le bloc Vitesse/GPS (page 1, pleine
        # largeur) : le RADAR doit dominer visuellement (60% de la
        # largeur, cf. report_prepa.py), ces cartes restent secondaires et
        # compactes (40%) pour ne pas écraser le graphique.
        return f"""<div class="no-break" style="background:linear-gradient(180deg, {norm_color}14, #fff 45%); border:1px solid #eee; border-top:3px solid {norm_color}; border-radius:6px; padding:6px 10px; box-shadow:0 1px 3px rgba(0,0,0,0.05); width:100%; box-sizing:border-box; margin-bottom:0;">
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
                <span style="font-size:7.5pt; font-weight:800; color:#555; text-transform:uppercase; letter-spacing:0.3px;">{label_disp}{z_html}</span>
                <span style="font-size:6.5pt; color:{norm_color}; font-weight:bold;">Obj. {norm_txt}</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:3px;">
                <div style="font-size:14pt; font-weight:900; color:{DARK};">{val_str} <span style="font-size:7pt; color:#666; font-weight:normal;">{unit}</span></div>
                <div style="font-size:8pt; font-weight:900; color:{pct_color};">{format_pct(pct)}</div>
            </div>
            {bar_html}
        </div>"""

    if full_width:
        # Empilement vertical dans une colonne étroite (ex: à côté d'un radar,
        # façon bloc Biodex) : prend 100% de la largeur DE SA COLONNE, pas de
        # la page entière. Tailles compactes pour empiler plusieurs cartes
        # sans occuper trop de hauteur.
        width_style, pad, font_val, font_lbl, font_unit = "width: 100%;", "6px 10px", "11pt", "6.5pt", "6.5pt"
    elif is_report:
        if is_kine:
            width_style, pad, font_val, font_lbl, font_unit = "width: calc(33.333% - 6px);", "4px 6px", "10pt", "5.5pt", "5.5pt"
        else:
            width_style, pad, font_val, font_lbl, font_unit = "width: calc(50% - 6px);", "8px 10px", "14pt", "7.5pt", "7.5pt"
    else:
        width_style, pad, font_val, font_lbl, font_unit = "width: calc(50% - 4px);", "12px 14px", "18pt", "9pt", "9pt"

    return f"""<div class="no-break" style="background:#fff; border:1px solid #eee; border-left:3px solid {norm_color}; border-radius:4px; padding:{pad}; box-shadow:0 1px 2px rgba(0,0,0,0.03); {width_style} display:inline-block; vertical-align:top; margin-bottom:8px; box-sizing:border-box;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; row-gap:2px;">
            <div style="font-size:{font_lbl}; font-weight:bold; color:#555; text-transform:uppercase; overflow-wrap: break-word;">{label_disp}{z_html}</div>
            <div style="font-size:6.5pt; color:{norm_color}; font-weight:bold; white-space:nowrap;">Obj. {norm_txt}</div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:4px;">
            <div style="font-size:{font_val}; font-weight:900; color:{DARK};">{val_str} <span style="font-size:{font_unit}; color:#666;">{unit}</span>{pdc_html}{trend_html}</div>
            <div style="font-size:7.5pt; font-weight:900; color:{pct_color};">{format_pct(pct)}</div>
        </div>
        {bar_html}{eval_html}
    </div>"""


def get_theme_card_html(theme: dict, is_report: bool = False) -> str:
    couleur = SDR_RED if theme["etat"] in ("En manque de", "Prévention de", "Rééquilibrage de") else GREEN
    w_style = "width: calc(33.333% - 10px); display: inline-block; flex-grow: 1; min-width: 200px;" if is_report else "width: 100%; display: block;"
    return f"""
    <div class="no-break" style="background:#fff; border-left:4px solid {couleur}; padding:12px; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.05); border: 1px solid #eee; box-sizing: border-box; overflow-wrap: break-word; {w_style}">
        <div style="font-size:7pt; color:{couleur}; font-weight:bold; text-transform:uppercase; margin-bottom:4px; background: rgba(0,0,0,0.03); display: inline-block; padding: 2px 6px; border-radius: 3px;">{theme['etat']}</div>
        <div style="font-size:10pt; font-weight:900; color:#333; line-height:1.2;">{theme['qualite']}</div>
        <div style="font-size:8pt; color:#666; margin-top:4px;">Zone : {theme['zone']}</div>
        <div style="font-size:7.5pt; color:#444; margin-top:6px; border-top:1px dashed #eee; padding-top:4px;">
            <b>Obj:</b> {theme.get('objectif', '-')} <br>
            <b>Fréq:</b> {theme.get('freq', '-')} | <b>Moment:</b> {theme.get('moment', '-')}
        </div>
    </div>
    """


def get_legend_html(compact: bool = True) -> str:
    margin_top = "5px" if compact else "15px"
    return f"""
    <div style="margin-top:{margin_top}; margin-bottom:0px; padding:12px; background:#f8f9fa; border:1px solid #e9ecef; border-radius:8px; font-size:8pt; color:#495057; box-shadow: 0 2px 4px rgba(0,0,0,0.02); width:100%; box-sizing:border-box;">
        <div style="display:flex; justify-content:space-around; align-items:flex-start;">
            <div style="flex:1;">
                <div style="font-weight:bold; color:#333; margin-bottom:6px; font-size:7.5pt; letter-spacing:0.5px;">STATUT OBJECTIF</div>
                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                    <span style="display:flex; align-items:center; gap:4px; font-weight:bold; color:{GREEN_TEXT};"><div style="width:8px; height:8px; border-radius:50%; background:{GREEN};"></div> Acquis</span>
                    <span style="display:flex; align-items:center; gap:4px; font-weight:bold; color:{ORANGE_TEXT};"><div style="width:8px; height:8px; border-radius:50%; background:{ORANGE};"></div> Proche</span>
                    <span style="display:flex; align-items:center; gap:4px; font-weight:bold; color:{SDR_RED};"><div style="width:8px; height:8px; border-radius:50%; background:{SDR_RED};"></div> Non Acquis</span>
                </div>
            </div>
            <div style="flex:2; border-left:1px dashed #ccc; padding-left:15px;">
                <div style="font-weight:bold; color:#333; margin-bottom:6px; font-size:7.5pt; letter-spacing:0.5px;">RANG (Percentile vs Référence)</div>
                <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center;">
                    <span style="display:flex; align-items:center; gap:4px; font-weight:bold; color:{BLUE_ELITE_TEXT};"><div style="width:10px; height:4px; border-radius:2px; background:{BLUE_ELITE};"></div> Élite (≥ 95% / Z ≥ 1.65)</span>
                    <span style="display:flex; align-items:center; gap:4px; font-weight:bold; color:{GREEN_TEXT};"><div style="width:10px; height:4px; border-radius:2px; background:{GREEN};"></div> Bon (≥ 66%)</span>
                    <span style="display:flex; align-items:center; gap:4px; font-weight:bold; color:{ORANGE_TEXT};"><div style="width:10px; height:4px; border-radius:2px; background:{ORANGE};"></div> Moyen (≥ 33%)</span>
                    <span style="display:flex; align-items:center; gap:4px; font-weight:bold; color:{SDR_RED};"><div style="width:10px; height:4px; border-radius:2px; background:{SDR_RED};"></div> (&lt; 33%)</span>
                </div>
            </div>
        </div>
    </div>
    """


def _ref_group_badge_html(ref_group_label: str, n_ref: int | None) -> str:
    """
    Badge "Comparé à : ..." en tête de rapport. Vert (comme avant) quand
    l'effectif de comparaison est suffisant (>= N_REF_MIN) ou inconnu ;
    orange avec une mise en garde explicite quand n < N_REF_MIN -- pour
    qu'un lecteur du PDF (agent, direction...) voie la limite de fiabilité
    même s'il n'a jamais vu l'avertissement affiché côté appli interactive
    au moment du choix du groupe (cf. rapport_page.py).
    """
    small_sample = n_ref is not None and n_ref < N_REF_MIN
    bg = "#fff4e5" if small_sample else "#eefaf3"
    border = ORANGE if small_sample else GREEN
    warning = (
        f'<span style="margin-left:8px; font-weight:normal; font-style:italic;">'
        f'⚠️ Échantillon réduit (n={n_ref} &lt; {N_REF_MIN}) — percentile à interpréter avec prudence, '
        f'privilégier le z-score.</span>'
        if small_sample else ""
    )
    return f"""
        <div class="no-break" style="font-size:8pt; color:#666; background:{bg}; border:1px solid {border}; padding:6px 12px; border-radius:4px; display:inline-block; margin-bottom:15px; font-weight:bold; overflow-wrap: break-word;">
            Comparé à : {ref_group_label}{warning}
        </div>
    """


def get_header_html(player_name, poste, lateralite, age_html, taille_html, poids_html,
                     context_html, photo_img, logo_img, ref_group_label, n_ref: int | None = None) -> str:
    """Bloc d'en-tête commun (photo, identité, anthropométrie, logo) des deux rapports."""
    # Taille de police adaptative : un nom long (ex: "MAMBUKU JEAN TRYFOSE")
    # en 26pt fixe passait sur 2 lignes et chevauchait le poste juste en
    # dessous. On réduit la taille au-delà d'un certain nombre de
    # caractères, et on force un peu d'espace pour absorber un éventuel
    # retour à la ligne malgré tout (nom très long + fenêtre étroite).
    name_len = len(player_name)
    if name_len > 22:
        name_font_size = "16pt"
    elif name_len > 16:
        name_font_size = "20pt"
    else:
        name_font_size = "26pt"

    return f"""
        <div class="no-break" style="display:flex; justify-content:space-between; align-items:center; border-bottom: 3px solid {SDR_RED}; padding-bottom: 15px; margin-bottom: 15px;">
            <div style="display:flex; align-items:center; gap: 20px; flex-grow:1; min-width:0;">
                {photo_img}
                <div style="flex-grow:1; min-width:0; display:flex; flex-direction:column; justify-content:center;">
                    <div style="display:flex; align-items:baseline; gap:12px; margin-bottom:6px;">
                        <h1 style="margin:0; color:{SDR_RED}; font-size:{name_font_size}; font-weight:900; text-transform:uppercase; line-height:1.15; overflow-wrap: break-word;">
                            {player_name}
                        </h1>
                    </div>
                    <div style="font-size:11pt; font-weight:bold; color:#555; margin-bottom:12px; text-transform:uppercase; letter-spacing:0.5px;">
                        {poste} &bull; {lateralite}
                    </div>
                    <div style="display:flex; gap:10px;">
                        <div style="flex:1; background:#f8f9fa; border:1px solid #eee; padding:6px; border-radius:6px; text-align:center;">
                            <span style="color:#666; font-size:7pt; text-transform:uppercase; display:block;">Âge</span>
                            <span style="font-weight:900; font-size:11pt; color:{DARK};">{age_html}</span>
                        </div>
                        <div style="flex:1; background:#f8f9fa; border:1px solid #eee; padding:6px; border-radius:6px; text-align:center;">
                            <span style="color:#666; font-size:7pt; text-transform:uppercase; display:block;">Taille</span>
                            <span style="font-weight:900; font-size:11pt; color:{DARK};">{taille_html}</span>
                        </div>
                        <div style="flex:1; background:#f8f9fa; border:1px solid #eee; padding:6px; border-radius:6px; text-align:center;">
                            <span style="color:#666; font-size:7pt; text-transform:uppercase; display:block;">Poids</span>
                            <span style="font-weight:900; font-size:11pt; color:{DARK};">{poids_html}</span>
                        </div>
                    </div>
                    {context_html}
                </div>
            </div>
            <div style="text-align:right; border-left:2px solid #eee; padding-left:20px; margin-left:20px; width:110px; flex-shrink:0;">
                {logo_img}
                <div style="font-weight:900; color:#333; font-size:8.5pt; text-transform:uppercase; line-height:1.3; margin-top:5px; overflow-wrap: break-word;">
                    Département<br><span style="color:{SDR_RED}">Performance</span>
                </div>
            </div>
        </div>
        {_ref_group_badge_html(ref_group_label, n_ref)}
    """


def get_footer_html() -> str:
    return """
        <div class="footer-print">
            <span>Département Performance · Stade de Reims</span>
            <span>Document confidentiel — usage interne club</span>
        </div>
    """


def photo_or_placeholder_html(photo_b64: str, initial: str, size: int = 110) -> str:
    if photo_b64:
        return (f'<img src="data:image/png;base64,{photo_b64}" style="width:{size}px; height:{size}px; '
                f'object-fit:cover; object-position:top center; display:block; border-radius:12px; '
                f'border:2px solid #eee; box-shadow: 0 4px 10px rgba(0,0,0,0.08); flex-shrink:0;">')
    return (f'<div style="width:{size}px; height:{size}px; background:#f0f0f0; display:flex; align-items:center; '
            f'justify-content:center; text-align:center; color:#707070; font-weight:bold; font-size:32px; '
            f'border-radius:12px; border:2px solid #eee; box-shadow: 0 4px 10px rgba(0,0,0,0.08); '
            f'flex-shrink:0; line-height:{size}px;">{initial}</div>')