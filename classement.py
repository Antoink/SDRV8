import base64
import os

import streamlit as st
import pandas as pd
from config_rapport import COL_MAPPING, TEAM_STRUCTURE, UNITS, is_inverted_metric
from comparateur import get_best_photo_path, img_to_b64, get_best_season_record_paired # Ajout de l'import ici
from utils import load_data
from data_utils import last_valid_value
from pdf_export import is_pdf_export_available, html_to_pdf_bytes

SDR_RED = "#D71920"
SDR_BLACK = "#1a1a1a"

# --- UTILITAIRES ---
def is_inverted(label):
    # Version unique et partagée -> voir config_rapport.py, section 4.
    return is_inverted_metric(label)

def get_unit(label):
    return UNITS.get(label, "")

import re

def clean_val(val):
    try:
        if pd.isna(val) or str(val).strip() == "" or str(val) == "#VALEUR!": return None
        val_str = re.sub(r'[\s\u202F\xa0]+', '', str(val)).replace(',', '.')
        return float(val_str)
    except: return None

def find_col(df, label):
    if label in COL_MAPPING and COL_MAPPING[label] in df.columns: return COL_MAPPING[label]
    label_clean = "".join(c for c in label.lower() if c.isalnum())
    for col in df.columns:
        if label_clean == "".join(c for c in str(col).lower() if c.isalnum()): return col
    return None

# --- AFFICHAGE PODIUM ---
def render_podium(top3):
    # Conserve ta fonction de podium actuelle intacte ici...
    pass


# --- PDF STYLISÉ (thème Stade de Reims) --------------------------------------
# Demande (09/2026) : un classement "présentable" à afficher/imprimer, pas
# juste un CSV brut -- logo + Département Performance en en-tête (même
# habillage que le reste de l'appli, cf. profiling.py/rapport_page.py),
# page 1 = podium (top 3 ou top 5), page 2 = classement complet en tableau.
# Réutilise pdf_export.html_to_pdf_bytes (WeasyPrint), déjà utilisé partout
# ailleurs dans l'appli pour les rapports PDF -- même repli HTML si
# WeasyPrint est indisponible sur l'environnement (cf. is_pdf_export_available).
@st.cache_data(show_spinner=False)
def _classement_logo_b64(filename):
    if not os.path.exists(filename):
        return ""
    try:
        with open(filename, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def build_classement_pdf_html(df_clean, choix_kpi, sel_session, unit, choix_equipes, joueurs_blesses=None):
    joueurs_blesses = joueurs_blesses or set()
    logo_sdr = _classement_logo_b64("logo_sdr.png")
    logo_dept = _classement_logo_b64("Departement Perf.png")

    nb_podium = 5 if len(df_clean) >= 5 else min(3, len(df_clean))
    podium = df_clean.head(nb_podium)
    reste = df_clean.iloc[nb_podium:]

    RANK_STYLE = {
        1: ("#D4AF37", "🥇"),
        2: ("#A6A6A6", "🥈"),
        3: ("#B08D57", "🥉"),
    }

    podium_cards = ""
    for _, r in podium.iterrows():
        rang = int(r["Rang"])
        accent, medal = RANK_STYLE.get(rang, (SDR_RED, ""))
        photo_path = get_best_photo_path(r["Joueur"])
        photo_b64 = img_to_b64(photo_path) if photo_path else ""
        photo_html = (
            f'<img src="data:image/png;base64,{photo_b64}" style="width:70px; height:70px; object-fit:cover; border-radius:50%; border:3px solid {accent};" />'
            if photo_b64 else
            f'<div style="width:70px; height:70px; border-radius:50%; border:3px solid {accent}; background:#f0f0f0; display:flex; align-items:center; justify-content:center; font-size:26px; font-weight:900; color:{accent};">{rang}</div>'
        )
        podium_cards += f"""
        <div style="display:flex; align-items:center; gap:18px; background:#fff; border:1px solid #eee; border-left:6px solid {accent}; border-radius:8px; padding:14px 20px; margin-bottom:12px; box-shadow:0 2px 6px rgba(0,0,0,0.06);">
            <div style="font-size:22px; font-weight:900; color:{accent}; width:34px; text-align:center;">{medal or f"#{rang}"}</div>
            {photo_html}
            <div style="flex:1;">
                <div style="font-size:17px; font-weight:800; color:{SDR_BLACK};">{r['Joueur']}</div>
                <div style="font-size:12px; color:#777; text-transform:uppercase; letter-spacing:0.5px;">{r['Equipe']}</div>
            </div>
            <div style="font-size:20px; font-weight:900; color:{SDR_RED};">{r['Valeur_Display']}</div>
        </div>
        """

    table_rows = "".join(
        f"<tr><td>{int(r['Rang'])}</td><td>{r['Joueur']}{' 🏥' if str(r['Joueur']).strip().lower() in joueurs_blesses else ''}</td><td>{r['Equipe']}</td><td>{r['Valeur_Display']}</td></tr>"
        for _, r in df_clean.iterrows()
    )

    equipes_txt = ", ".join(choix_equipes) if choix_equipes else "Toutes"
    date_gen = pd.Timestamp.now().strftime("%d/%m/%Y")

    html = f"""
    <html><head><meta charset="utf-8">
    <style>
        @page {{ size: A4; margin: 18mm 16mm; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; color: {SDR_BLACK}; margin:0; }}
        .header {{ display:flex; align-items:center; justify-content:space-between; border-bottom:3px solid {SDR_RED}; padding-bottom:12px; margin-bottom:22px; }}
        .header img {{ height:60px; object-fit:contain; }}
        .header .title {{ text-align:right; }}
        .header .title .main {{ font-size:30px; font-weight:900; color:{SDR_RED}; letter-spacing:2px; text-transform:uppercase; }}
        .header .title .sub {{ font-size:13px; color:#555; font-weight:600; }}
        .meta {{ font-size:12px; color:#666; margin-bottom:18px; }}
        .meta b {{ color:{SDR_BLACK}; }}
        h2.section {{ color:{SDR_RED}; border-bottom:1px solid {SDR_RED}; padding-bottom:4px; font-size:18px; text-transform:uppercase; letter-spacing:1px; }}
        table.classement {{ width:100%; border-collapse:collapse; margin-top:10px; font-size:12px; }}
        table.classement th {{ background:{SDR_RED}; color:#fff; padding:8px 10px; text-align:left; }}
        table.classement td {{ padding:6px 10px; border-bottom:1px solid #eee; }}
        table.classement tr:nth-child(even) {{ background:#fafafa; }}
        .page-break {{ page-break-before: always; }}
        .footer {{ margin-top:20px; font-size:10px; color:#999; text-align:center; border-top:1px solid #eee; padding-top:8px; }}
    </style></head>
    <body>
        <div class="header">
            <img src="data:image/png;base64,{logo_dept}" />
            <img src="data:image/png;base64,{logo_sdr}" />
            <div class="title">
                <div class="main">Classement</div>
                <div class="sub">Saison 2026-2027</div>
            </div>
        </div>
        <div class="meta">
            Indicateur : <b>{choix_kpi} ({unit})</b> &nbsp;|&nbsp; Session : <b>{sel_session}</b> &nbsp;|&nbsp;
            Équipes incluses : <b>{equipes_txt}</b> &nbsp;|&nbsp; Généré le <b>{date_gen}</b>
        </div>

        <h2 class="section">🏆 Top {nb_podium}</h2>
        {podium_cards}

        <div class="page-break"></div>
        <div class="header">
            <img src="data:image/png;base64,{logo_dept}" />
            <img src="data:image/png;base64,{logo_sdr}" />
            <div class="title">
                <div class="main">Classement complet</div>
                <div class="sub">{choix_kpi}</div>
            </div>
        </div>
        <table class="classement">
            <thead><tr><th>Rang</th><th>Joueur</th><th>Équipe</th><th>Valeur</th></tr></thead>
            <tbody>{table_rows}</tbody>
        </table>

        <div class="footer">Antoine Kaczmarek — Département Performance — Stade de Reims</div>
    </body></html>
    """
    return html

# --- PAGE PRINCIPALE UNIQUE ---
def show_classement_page(df_dummy):
    # On ajoute ", _" pour séparer le DataFrame de la source (qu'on ignore ici)
    df, _ = load_data()
    
    # Titre + emplacement du bouton d'export en haut à droite -- le bouton
    # est rempli plus bas (une fois le classement filtré/calculé), mais ce
    # placeholder réserve sa place ici pour qu'il apparaisse en haut de page
    # et pas seulement après avoir tout déroulé.
    col_title, col_export, col_export_pdf = st.columns([4, 1.3, 1.3])
    with col_title:
        st.markdown(f"<h2 style='color: {SDR_RED};'>CLASSEMENT GÉNÉRAL</h2>", unsafe_allow_html=True)
    with col_export:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        export_placeholder = st.empty()
    with col_export_pdf:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        export_pdf_placeholder = st.empty()

    if "Session" not in df.columns:
        st.error("Colonne 'Session' introuvable dans le fichier.")
        return

    # 1. Sélection de la session avec intégration du Record de Saison
    sessions_dispos = ["🏆 Record de Saison"] + sorted(df["Session"].dropna().unique().astype(str))
    sel_session = st.selectbox("Session :", sessions_dispos, key="sess_classement")
    
    # 2. Application de la logique de Record Synchronisé ou de session fixe
    if sel_session == "🏆 Record de Saison":
        records = []
        for j in df['Joueur'].dropna().unique():
            df_j = df[df['Joueur'] == j]
            if not df_j.empty:
                row_j = get_best_season_record_paired(df_j)
                row_j['Joueur'] = j
                # Dernière valeur RENSEIGNÉE (pas `.iloc[-1]` qui peut tomber sur une
                # ligne "virtuelle" du fichier 1080, vide sur cette colonne).
                row_j['Equipe'] = last_valid_value(df_j, 'Equipe', 'N/A')
                records.append(row_j)
        df_session = pd.DataFrame(records)
    else:
        df_session = df[df["Session"].astype(str) == sel_session].copy()
    
    # 3. Choix des catégories (Equipes)
    toutes_equipes = sorted(df_session["Equipe"].dropna().unique().astype(str))
    choix_equipes = st.multiselect("Catégories à inclure dans le classement :", toutes_equipes, default=toutes_equipes)
    choix_kpi = st.selectbox("Indicateur :", list(UNITS.keys()))

    df_filtered = df_session[df_session["Equipe"].astype(str).isin(choix_equipes)].copy() if choix_equipes else df_session.copy()

    col_name = find_col(df_filtered, choix_kpi)
    if not col_name: 
        st.warning(f"Indicateur '{choix_kpi}' non trouvé.")
        return

    df_filtered['Valeur_Clean'] = df_filtered[col_name].apply(clean_val)
    df_clean = df_filtered.dropna(subset=['Valeur_Clean', 'Joueur']).copy()
    
    if df_clean.empty: 
        st.info("Aucune donnée disponible.")
        return

    # Tri selon l'indicateur (temps vs. force)
    df_clean = df_clean.sort_values(by='Valeur_Clean', ascending=is_inverted(choix_kpi))
    df_clean['Valeur_Display'] = df_clean['Valeur_Clean'].apply(lambda x: f"{x:.2f} {get_unit(choix_kpi)}")
    df_clean['Rang'] = range(1, len(df_clean) + 1)
    
    # Rendu du Podium
    render_podium(df_clean.head(3))
    
    
    # Joueurs blessés (historique + nouveau doc kiné, même source que PROFIL
    # INDIVIDUEL/ÉVOLUTION) -- pertinent ici pour repérer d'un coup d'œil,
    # dans un classement, un joueur qui a un passif de blessure récent
    # plutôt que de découvrir le contexte seulement page par page. Import
    # différé : profiling.py importe déjà classement.py (boucle sinon).
    noms_blesses_bruts = set()
    try:
        from profiling import load_injury_data
        df_inj = load_injury_data()
        if not df_inj.empty and 'Joueur' in df_inj.columns:
            noms_blesses_bruts = set(df_inj['Joueur'].astype(str).str.strip().str.lower())
    except Exception:
        pass

    # Le doc kiné stocke parfois juste le nom de famille ("gadou") plutôt
    # que "Nom Prénom" complet -- même tolérance de correspondance que
    # l'onglet PROFIL INDIVIDUEL (voir evolution.py pour la même remarque) :
    # un joueur est marqué "blessé" si son nom complet COMMENCE PAR une des
    # valeurs brutes du doc kiné.
    def _est_blesse(nom_joueur):
        nj = str(nom_joueur).strip().lower()
        return any(nj.startswith(nb) for nb in noms_blesses_bruts)

    joueurs_blesses = {j for j in df_clean['Joueur'].dropna().unique() if _est_blesse(j)}
    joueurs_blesses = {str(j).strip().lower() for j in joueurs_blesses}

    st.markdown("### Classement complet", unsafe_allow_html=True)
    if joueurs_blesses:
        st.caption("🏥 = joueur avec un passif de blessure enregistré (toutes saisons confondues).")
    table_html = f"""
    <style>
        .custom-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-family: sans-serif; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .custom-table th {{ background-color: {SDR_RED}; color: white; padding: 12px; text-align: left; font-weight: bold; border: 1px solid #ddd; }}
        .custom-table td {{ padding: 10px; border-bottom: 1px solid #ddd; border-right: 1px solid #eee; color: black; }}
        .custom-table tr:nth-child(even) {{ background-color: #f8f8f8; }}
    </style>
    <table class='custom-table'>
        <thead><tr><th>Rang</th><th>Joueur</th><th>Catégorie</th><th>Valeur</th></tr></thead>
        <tbody>
    """
    for _, row in df_clean.iterrows():
        blesse_badge = " 🏥" if str(row['Joueur']).strip().lower() in joueurs_blesses else ""
        table_html += f"<tr><td>{row['Rang']}</td><td>{row['Joueur']}{blesse_badge}</td><td>{row['Equipe']}</td><td>{row['Valeur_Display']}</td></tr>"
    table_html += "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)

    # Export CSV -- pour partage rapide (réunion, Excel) sans avoir à
    # recopier le tableau à la main. Rendu dans le placeholder réservé en
    # haut à droite de la page (cf. début de la fonction).
    csv_export = df_clean[['Rang', 'Joueur', 'Equipe', 'Valeur_Display']].rename(
        columns={'Valeur_Display': f'{choix_kpi} ({get_unit(choix_kpi)})' if get_unit(choix_kpi) else choix_kpi}
    )
    export_placeholder.download_button(
        "⬇️ Exporter (CSV)",
        data=csv_export.to_csv(index=False, sep=';').encode('utf-8-sig'),
        file_name=f"Classement_{choix_kpi}_{sel_session}.csv".replace(" ", "_"),
        mime="text/csv",
        width='stretch',
    )

    # Export PDF stylisé (thème SDR : logo + Département Performance, podium
    # en page 1, classement complet en page 2) -- repli HTML si WeasyPrint
    # est indisponible sur l'environnement (même pattern que rapport_page.py).
    pdf_ready = is_pdf_export_available()
    classement_html = build_classement_pdf_html(df_clean, choix_kpi, sel_session, get_unit(choix_kpi), choix_equipes, joueurs_blesses)
    nom_fichier_pdf = f"Classement_{choix_kpi}_{sel_session}".replace(" ", "_")
    if pdf_ready:
        try:
            classement_pdf_bytes = html_to_pdf_bytes(classement_html)
            export_pdf_placeholder.download_button(
                "🏆 Exporter (PDF)",
                data=classement_pdf_bytes,
                file_name=f"{nom_fichier_pdf}.pdf",
                mime="application/pdf",
                width='stretch',
            )
        except Exception:
            export_pdf_placeholder.download_button(
                "🏆 Exporter (HTML)",
                data=classement_html.encode("utf-8"),
                file_name=f"{nom_fichier_pdf}.html",
                mime="text/html",
                width='stretch',
            )
    else:
        export_pdf_placeholder.download_button(
            "🏆 Exporter (HTML)",
            data=classement_html.encode("utf-8"),
            file_name=f"{nom_fichier_pdf}.html",
            mime="text/html",
            width='stretch',
            help="Export PDF indisponible dans cet environnement (dépendances système manquantes) — export HTML stylisé à la place.",
        )