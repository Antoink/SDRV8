# -*- coding: utf-8 -*-
"""
planning.py
============
Génération du "planning type" hebdomadaire d'un joueur, organisé autour du
jour de match (Match Day) : MD-2, MD-1, MD, MD+1, MD+2, MD+3, chacun
découpé en Matin / Après-midi.

Ce planning est rempli manuellement par le staff (aucun calcul automatique
ici, contrairement au reste de l'app) : ce module ne fait que structurer et
mettre en forme visuellement ce que le staff a saisi.

DESIGN
------
Le rendu est volontairement différent du rapport de profilage (grille
hebdomadaire en paysage plutôt que fiche en portrait), car l'usage est
différent : un coup d'œil rapide sur toute la semaine plutôt qu'une lecture
détaillée page par page. La charte graphique (rouge/blanc Stade de Reims,
logo) est reprise à l'identique — le thème visuel plus poussé sera affiné
plus tard sur indication du staff.
"""
from __future__ import annotations

JOURS = ["MD-2", "MD-1", "MD", "MD+1", "MD+2", "MD+3"]
MOMENTS = ["Matin", "Après-midi"]

# Catégories d'activités proposées. Couleurs choisies pour rester lisibles
# sur fond blanc et cohérentes avec la charte SDR (rouge = coeur du métier
# terrain, le reste décliné en teintes distinctes pour un repérage rapide).
# NOTE : pas d'emoji ici — les polices emoji couleur ne sont pas disponibles
# sur un serveur de rendu PDF (WeasyPrint), ce qui produisait des icônes
# cassées/illisibles. La distinction se fait uniquement par couleur + texte,
# via une puce ronde dessinée en CSS (fiable partout, y compris à l'impression).
CATEGORIES = {
    "Entraînement": {"color": "#D71920"},
    "Renforcement": {"color": "#F39C12"},
    "Soins": {"color": "#3498DB"},
    "Protocole Récup": {"color": "#1ABC9C"},
    "Prévention": {"color": "#27AE60"},
    "Mobilité": {"color": "#16A085"},
    "Conditionnement": {"color": "#2980B9"},
    "Vidéo / Analyse": {"color": "#8E44AD"},
    "Nutrition": {"color": "#B8860B"},
    "Repos": {"color": "#7F8C8D"},
}

SDR_RED = "#D71920"
DARK = "#222222"


def _auto_tags_for_activity(activity_text: str) -> list[str]:
    """Déduit une ou plusieurs catégories (config.CATEGORIES) à partir du texte d'activité du plan département, pour l'auto-remplissage du planning individuel."""
    text = activity_text.lower()
    tags = []
    if "off" in text:
        tags.append("Repos")
    if "musculation" in text or "squat keiser" in text or "abdos" in text or "gainage" in text:
        tags.append("Renforcement")
    if "mobilité" in text or "rom" in text:
        tags.append("Mobilité")
    if "réactivité" in text:
        tags.append("Renforcement")
    if "prévention" in text:
        tags.append("Prévention")
    if "vélo" in text or "velo" in text or "hiit" in text:
        tags.append("Conditionnement")
    if not tags:
        tags.append("Entraînement")
    # dédoublonne en gardant l'ordre
    seen = set()
    return [t for t in tags if not (t in seen or seen.add(t))]


def empty_planning() -> dict:
    """Structure vide : un slot {tags: [], note: ''} par jour x moment."""
    return {jour: {moment: {"tags": [], "note": ""} for moment in MOMENTS} for jour in JOURS}


def autofill_planning_from_kpi(kpi: str) -> dict:
    """
    Pré-remplit la grille MD-2..MD+3 à partir du plan hebdomadaire du
    département pour le KPI donné (config.KPI_WEEKLY_PLAN). L'activité du
    jour est placée en "Matin" (le département ne précise pas Matin/Aprem) ;
    "Après-midi" reste vide pour que le staff y ajoute Soins/Récup/etc.
    propres au joueur si besoin. Le "MD+4 / MD-3" du plan département n'a
    pas d'équivalent dans cette grille à 6 jours et n'est pas utilisé ici.
    """
    from config import KPI_WEEKLY_PLAN
    plan = KPI_WEEKLY_PLAN.get(kpi, {})
    data = empty_planning()
    for jour in JOURS:
        activity = plan.get(jour, "")
        if not activity:
            continue
        data[jour]["Matin"] = {"tags": _auto_tags_for_activity(activity), "note": activity}
    return data


def _tag_pill_html(tag: str) -> str:
    meta = CATEGORIES.get(tag, {"color": "#999"})
    dot = f'<span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:{meta["color"]}; margin-right:5px; vertical-align:middle;"></span>'
    return (
        f'<span style="display:inline-block; background:{meta["color"]}18; '
        f'color:{meta["color"]}; border:1px solid {meta["color"]}55; border-radius:12px; padding:3px 9px 3px 7px; '
        f'font-size:8pt; font-weight:700; margin:2px 3px 0 0; white-space:nowrap;">{dot}<span style="vertical-align:middle;">{tag}</span></span>'
    )


def _slot_cell_html(slot: dict) -> str:
    """Contenu d'une cellule du tableau (un jour x un moment)."""
    tags = slot.get("tags", [])
    note = (slot.get("note") or "").strip()
    if not tags and not note:
        return '<td style="padding:10px 8px; border:1px solid #eee; text-align:center; color:#ccc; font-size:8pt; font-style:italic; vertical-align:top;">—</td>'
    pills = "".join(_tag_pill_html(t) for t in tags)
    note_html = f'<div style="font-size:7.5pt; color:#555; margin-top:5px; line-height:1.3;">{note}</div>' if note else ""
    return f'<td style="padding:10px 8px; border:1px solid #eee; vertical-align:top;">{pills}{note_html}</td>'


def _planning_table_html(planning_data: dict) -> str:
    """
    Tableau : une colonne par jour (MD-2 -> MD+3), une ligne d'en-tête avec
    les jours, puis une ligne "Matin" et une ligne "Après-midi" en dessous —
    lecture d'un coup d'œil façon emploi du temps.
    """
    header_cells = "".join(
        f'<th style="padding:10px 8px; text-align:center; background:{SDR_RED if j == "MD" else "#2c2c2c"}; '
        f'color:#fff; font-size:11pt; font-weight:900; border:1px solid #fff;">{j}{" (Match)" if j == "MD" else ""}</th>'
        for j in JOURS
    )
    rows_html = ""
    for moment in MOMENTS:
        cells = "".join(_slot_cell_html(planning_data.get(j, {}).get(moment, {})) for j in JOURS)
        rows_html += (
            f'<tr><td style="padding:8px; background:#f8f9fa; font-weight:800; color:#666; '
            f'font-size:8pt; text-transform:uppercase; border:1px solid #eee; white-space:nowrap;">{moment}</td>{cells}</tr>'
        )
    return f"""
    <table style="width:100%; border-collapse:collapse; table-layout:fixed;">
        <tr><td style="border:1px solid #fff;"></td>{header_cells}</tr>
        {rows_html}
    </table>
    """


def _legend_html() -> str:
    items = "".join(_tag_pill_html(t) for t in CATEGORIES)
    return f"""
    <div style="margin-top:16px; padding:10px 14px; background:#f8f9fa; border:1px solid #eee; border-radius:8px;">
        <div style="font-size:7pt; font-weight:800; color:#666; text-transform:uppercase; margin-bottom:6px;">Légende</div>
        <div>{items}</div>
    </div>
    """


def build_planning_html(player_name: str, poste: str, planning_data: dict, logo_b64: str = "",
                         logo_ext: str = "png", week_label: str = "") -> str:
    """Construit le HTML complet (paysage A4) du planning hebdomadaire d'un joueur, sous forme de tableau."""
    table_html = _planning_table_html(planning_data)
    logo_img = f'<img src="data:image/{logo_ext};base64,{logo_b64}" style="height:70px;">' if logo_b64 else ""
    week_html = f'<div style="font-size:9pt; color:#666; margin-top:2px;">{week_label}</div>' if week_label else ""

    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
        body {{ font-family: 'Helvetica','Arial',sans-serif; background:#eee; margin:0; padding:0;
                -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
        .container {{ background:#fff; max-width:297mm; margin:10px auto; padding:12mm; box-sizing:border-box;
                      box-shadow:0 0 10px rgba(0,0,0,0.1); }}
        @media print {{
            @page {{ size: A4 landscape; margin: 10mm; }}
            body {{ background:#fff; }}
            .container {{ margin:0; box-shadow:none; max-width:100%; padding:0; }}
        }}
    </style>
    </head><body>
    <div class="container">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid {SDR_RED}; padding-bottom:12px; margin-bottom:16px;">
            <div>
                <div style="font-size:9pt; color:#666; font-weight:700; text-transform:uppercase; letter-spacing:1px;">Département Performance</div>
                <h1 style="margin:2px 0 0 0; color:{SDR_RED}; font-size:22pt; text-transform:uppercase; font-weight:900;">Planning Type Hebdomadaire</h1>
                <div style="font-size:12pt; font-weight:800; color:{DARK}; margin-top:4px;">{player_name} <span style="color:#999; font-weight:600;">— {poste}</span></div>
                {week_html}
            </div>
            {logo_img}
        </div>
        {table_html}
        {_legend_html()}
        <div style="margin-top:18px; font-size:7pt; color:#707070; text-align:right;">Document confidentiel — usage interne club</div>
    </div>
    </body></html>
    """


def build_kpi_department_plan_html(logo_b64: str = "", logo_ext: str = "png") -> str:
    """
    Construit le document (A4 paysage) du plan hebdomadaire du département
    performance par groupe de KPI — le tableau "GROUPES DE TRAVAIL" du
    document de réflexion individualisation, tel quel (indépendant d'un
    joueur en particulier, à la différence de build_planning_html). Sert de
    document de référence pour le staff, téléchargeable en HTML/PDF.
    """
    from config import KPI_WEEKLY_PLAN, KPI_WEEKLY_PLAN_DAYS_ORDER

    kpi_groups = list(KPI_WEEKLY_PLAN.keys())
    short_labels = {
        "Développement du RFD": "RFD",
        "Développement de la force": "Force",
        "Prévention des blessures": "Prévention",
        "Développement de la répétition des efforts": "Répétition des efforts",
        "Optimisation de la composition corporelle": "Composition corporelle",
    }

    header_cells = "".join(
        f'<th style="padding:10px 12px; text-align:left; background:{SDR_RED}; color:#fff; font-size:9pt; text-transform:uppercase;">{short_labels.get(g, g)}</th>'
        for g in kpi_groups
    )
    rows_html = ""
    for day in KPI_WEEKLY_PLAN_DAYS_ORDER:
        is_match_day = day == "MD"
        row_bg = "#fff5f5" if is_match_day else ("#fafafa" if KPI_WEEKLY_PLAN_DAYS_ORDER.index(day) % 2 else "#fff")
        cells = "".join(
            f'<td style="padding:10px 12px; font-size:8.5pt; color:#333; border-bottom:1px solid #eee;">{KPI_WEEKLY_PLAN[g].get(day, "-")}</td>'
            for g in kpi_groups
        )
        rows_html += (
            f'<tr style="background:{row_bg};">'
            f'<td style="padding:10px 12px; font-weight:900; color:{SDR_RED if is_match_day else DARK}; border-bottom:1px solid #eee; white-space:nowrap;">{day}</td>'
            f'{cells}</tr>'
        )

    logo_img = f'<img src="data:image/{logo_ext};base64,{logo_b64}" style="height:70px;">' if logo_b64 else ""

    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
        body {{ font-family: 'Helvetica','Arial',sans-serif; background:#eee; margin:0; padding:0;
                -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
        .container {{ background:#fff; max-width:297mm; margin:10px auto; padding:12mm; box-sizing:border-box;
                      box-shadow:0 0 10px rgba(0,0,0,0.1); }}
        table {{ width:100%; border-collapse:collapse; }}
        @media print {{
            @page {{ size: A4 landscape; margin: 10mm; }}
            body {{ background:#fff; }}
            .container {{ margin:0; box-shadow:none; max-width:100%; padding:0; }}
        }}
    </style>
    </head><body>
    <div class="container">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid {SDR_RED}; padding-bottom:12px; margin-bottom:20px;">
            <div>
                <div style="font-size:9pt; color:#666; font-weight:700; text-transform:uppercase; letter-spacing:1px;">Département Performance</div>
                <h1 style="margin:2px 0 0 0; color:{SDR_RED}; font-size:22pt; text-transform:uppercase; font-weight:900;">Plan Hebdomadaire par Groupe de KPI</h1>
                <div style="font-size:9pt; color:#666; margin-top:4px;">Individualisation — semaine type autour du jour de match</div>
            </div>
            {logo_img}
        </div>
        <table>
            <tr><th style="padding:10px 12px; text-align:left; background:#2c2c2c; color:#fff; font-size:9pt; text-transform:uppercase;">Jour</th>{header_cells}</tr>
            {rows_html}
        </table>
        <div style="margin-top:16px; font-size:7.5pt; color:#999; font-style:italic;">
            MD = jour de match. MD+4 et MD-3 correspondent au même jour du cycle hebdomadaire (semaine à 1 match).
        </div>
        <div style="margin-top:18px; font-size:7pt; color:#707070; text-align:right;">Document confidentiel — usage interne club</div>
    </div>
    </body></html>
    """


def build_kpi_focus_plan_html(player_name: str, poste: str, kpi: str, logo_b64: str = "", logo_ext: str = "png") -> str:
    """
    Extrait du plan hebdomadaire département : UNE seule colonne (le KPI à
    développer pour ce joueur), plutôt que les 5 groupes du tableau complet.
    Généré automatiquement à partir de l'axe d'amélioration du joueur —
    aucune saisie manuelle nécessaire (contrairement à l'ancien planning
    Matin/Après-midi par joueur, retiré sur demande du staff). Style repris
    du tableau de référence du département (en-tête rouge, ligne du jour de
    match mise en évidence, lignes alternées).
    """
    from config import KPI_WEEKLY_PLAN, KPI_WEEKLY_PLAN_DAYS_ORDER

    plan = KPI_WEEKLY_PLAN.get(kpi, {})
    rows_html = ""
    for i, day in enumerate(KPI_WEEKLY_PLAN_DAYS_ORDER):
        is_match_day = day == "MD"
        if is_match_day:
            row_bg = "#fce8e8"
        else:
            row_bg = "#fafafa" if i % 2 else "#fff"
        activity = plan.get(day, "-")
        rows_html += (
            f'<tr style="background:{row_bg};">'
            f'<td style="padding:12px 16px; font-weight:900; color:{SDR_RED if is_match_day else DARK}; border-bottom:1px solid #eee; white-space:nowrap; width:140px;">{day}</td>'
            f'<td style="padding:12px 16px; font-size:10pt; color:#333; border-bottom:1px solid #eee;">{activity}</td>'
            f'</tr>'
        )

    logo_img = f'<img src="data:image/{logo_ext};base64,{logo_b64}" style="height:70px;">' if logo_b64 else ""

    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
        body {{ font-family: 'Helvetica','Arial',sans-serif; background:#eee; margin:0; padding:0;
                -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
        .container {{ background:#fff; max-width:210mm; margin:10px auto; padding:14mm; box-sizing:border-box;
                      box-shadow:0 0 10px rgba(0,0,0,0.1); }}
        table {{ width:100%; border-collapse:collapse; }}
        @media print {{
            @page {{ size: A4 portrait; margin: 12mm; }}
            body {{ background:#fff; }}
            .container {{ margin:0; box-shadow:none; max-width:100%; padding:0; }}
        }}
    </style>
    </head><body>
    <div class="container">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid {SDR_RED}; padding-bottom:12px; margin-bottom:20px;">
            <div>
                <div style="font-size:9pt; color:#666; font-weight:700; text-transform:uppercase; letter-spacing:1px;">Département Performance</div>
                <h1 style="margin:2px 0 0 0; color:{SDR_RED}; font-size:20pt; text-transform:uppercase; font-weight:900;">Plan Hebdomadaire</h1>
                <div style="font-size:12pt; font-weight:800; color:{DARK}; margin-top:4px;">{player_name} <span style="color:#999; font-weight:600;">— {poste}</span></div>
            </div>
            {logo_img}
        </div>
        <table>
            <tr><th style="padding:12px 16px; text-align:left; background:{SDR_RED}; color:#fff; font-size:11pt; text-transform:uppercase; width:140px;">Jour</th>
                <th style="padding:12px 16px; text-align:left; background:{SDR_RED}; color:#fff; font-size:11pt; text-transform:uppercase;">{kpi}</th></tr>
            {rows_html}
        </table>
        <div style="margin-top:16px; font-size:7.5pt; color:#999; font-style:italic;">
            MD = jour de match. MD+4 et MD-3 correspondent au même jour du cycle hebdomadaire (semaine à 1 match).
        </div>
        <div style="margin-top:18px; font-size:7pt; color:#707070; text-align:right;">Document confidentiel — usage interne club</div>
    </div>
    </body></html>
    """