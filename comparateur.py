import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import base64
import re
import numpy as np
from config_rapport import COL_MAPPING, OFFICIAL_STRUCTURE, UNITS
from charts import build_radar

SDR_RED = "#D71920"
SDR_BLUE = "#1E3A8A"

# Sous-groupes "par qualité physique", UNIQUEMENT pour le radar, à
# l'intérieur des catégories existantes (kiné/salle/terrain, cf.
# OFFICIAL_STRUCTURE) qui restent la structure principale de l'appli --
# celle que le staff utilise déjà partout. Réflexion : un radar à 12-18 axes
# mélangeant mobilité, force add/abd, force ischios/cheville... n'a pas de
# forme lisible, MÊME à 2 joueurs, parce que les axes ne représentent pas
# la même chose. On garde donc "kiné/salle/terrain" comme découpage
# principal (c'est ainsi que le staff pense les tests), mais SEULEMENT là
# où une catégorie est surchargée, on subdivise son radar en 2-3 petits
# radars par qualité -- le tableau et les barres, eux, restent inchangés et
# montrent TOUJOURS tous les tests de la catégorie complète.
# Une catégorie absente d'ici garde son radar unique tel qu'avant (ex:
# PROFILAGE ATHLÉTIQUE, COMPOSITION CORPORELLE, 1080 SPRINT : déjà assez
# homogènes/courtes pour rester lisibles en un seul radar).
RADAR_SOUS_GROUPES = {
    "PROFILAGE MOTEUR": {
        "Knee To Wall (G)": "Mobilité", "Knee To Wall (D)": "Mobilité", "Sit And Reach": "Mobilité",
        "Ratio Squeeze": "Force Hanche (Add/Abd)", "Adducteurs (G)": "Force Hanche (Add/Abd)",
        "Adducteurs (D)": "Force Hanche (Add/Abd)", "Abducteurs (G)": "Force Hanche (Add/Abd)",
        "Abducteurs (D)": "Force Hanche (Add/Abd)",
        "Nordic Ischio (G)": "Chaîne Post. & Cheville", "Nordic Ischio (D)": "Chaîne Post. & Cheville",
        "Inverseur (G)": "Chaîne Post. & Cheville", "Inverseur (D)": "Chaîne Post. & Cheville",
        "Everseur (G)": "Chaîne Post. & Cheville", "Everseur (D)": "Chaîne Post. & Cheville",
        "Endurance Heel Raise (G)": "Chaîne Post. & Cheville", "Endurance Heel Raise (D)": "Chaîne Post. & Cheville",
    },
    "PROFILAGE PHYSIOLOGIQUE": {
        "VMA": "Endurance", "SV1": "Endurance", "SV2": "Endurance", "FC": "Endurance", "Test 1km (s)": "Endurance",
        "Temps sur 10m": "Vitesse & GPS", "Distance Totale": "Vitesse & GPS", "Distance HSR": "Vitesse & GPS",
        "Distance Sprint (92% Vimax)": "Vitesse & GPS", "Vmax": "Vitesse & GPS", "Amax": "Vitesse & GPS", "Dmax": "Vitesse & GPS",
    },
}

SENS_KPI = {
    "Temps sur 10m": "min", "Test 1km (s)": "min",
    "Masse Grasse Plis (mm)": "min", "Masse grasse": "min"
}

# ==========================================
# FONCTIONS UTILITAIRES
# ==========================================

@st.cache_data(ttl=600, show_spinner=False)
def img_to_b64(img_path):
    try:
        with open(img_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return ""

@st.cache_data(ttl=600, show_spinner=False)
def get_best_photo_path(player_name):
    # POURQUOI @st.cache_data ici : Streamlit relance tout le script à chaque
    # interaction -- sans cache, chaque page qui affiche plusieurs joueurs
    # (équipe, comparateur, clustering...) refaisait un os.listdir() complet
    # du dossier Photos (des centaines de fichiers) PAR JOUEUR À CHAQUE CLIC.
    # C'était la source de lenteur la plus nette de l'appli.
    folder = None
    for f_name in ["Photo", "Photos"]:
        if os.path.exists(f_name):
            folder = f_name
            break

    if not folder: return None

    files_map = {f.lower(): f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))}
    clean_name = player_name.strip()
    parts = clean_name.split()
    
    name_formats = [clean_name.lower()] 
    if len(parts) >= 2:
        nom = parts[-1].lower() 
        prenom = " ".join(parts[:-1]).lower() 
        name_formats.append(f"{nom} {prenom}") 
        name_formats.append(nom) 
        
    for fmt in name_formats:
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            if (fmt + ext) in files_map:
                return os.path.join(folder, files_map[fmt + ext])
    return None

# find_col / is_inverted / calculate_percentile -> logique partagée dans
# data_utils.py (voir son en-tête : ces fonctions existaient en plusieurs
# copies légèrement différentes selon les fichiers, avec parfois une
# protection anti-collision GPS/1080 absente ou incomplète, ce qui a causé
# de vrais bugs de percentile).
from data_utils import find_column_in_df as find_col, is_inverted, calculate_percentile as _calculate_percentile


def clean_val(val):
    try:
        if pd.isna(val) or str(val).strip() == "" or str(val) == "#VALEUR!": return None
        # Retire les espaces normaux/insécables (séparateur de milliers FR,
        # ex: "1 463,62") avant conversion -- sans ça float() levait une
        # exception sur toute valeur >= 1000 et affichait "-" à la place.
        val_str = re.sub(r'\s+', '', str(val)).replace(',', '.')
        return float(val_str)
    except Exception:
        return None

def format_number(val):
    if pd.isna(val) or str(val).strip() == "-" or str(val).strip() == "": return "-"
    try:
        f_val = float(str(val).replace(',', '.'))
        if f_val.is_integer(): return str(int(f_val))
        return str(f_val)
    except:
        return str(val)

def calculate_percentile(df, col_name, value):
    if col_name not in df.columns or value is None:
        return 0
    _, percentile = _calculate_percentile(df, col_name, value)
    return percentile

def clean_val_display(val, unit):
    return f"{val} {unit}" if val and val != "-" and val != "" else "N/A"

def format_date_str(d):
    if not d or pd.isna(d) or str(d).strip() == "-": return ""
    try:
        dt = pd.to_datetime(str(d), errors='raise', dayfirst=True)
        return dt.strftime('%d/%m/%Y')
    except:
        return str(d).split()[0]

def get_best_season_record_paired(df_player):
    if df_player.empty: return {}
    virtual_row = df_player.iloc[-1].to_dict()
    date_col = "Session exact" if "Session exact" in df_player.columns else "Session"
    
    # --- 1. CORRECTION ANTHROPO (Récupérer la dernière valeur non-vide) ---
    colonnes_base = ['Age', 'Taille (cm)', 'Poids (kg)', 'Masse grasse', 'Poste', 'Position', 'Equipe', 'Masse Grasse Plis (mm)', 'Somme de 8 plis (mm)']
    for col_base in colonnes_base:
        if col_base in df_player.columns:
            valides = df_player[col_base].dropna()
            if not valides.empty:
                virtual_row[col_base] = valides.iloc[-1]
    # ----------------------------------------------------------------------
    
    pairs = []
    for label, col_g in COL_MAPPING.items():
        if str(label).endswith("(G)"):
            label_d = str(label).replace("(G)", "(D)")
            if label_d in COL_MAPPING:
                pairs.append((col_g, COL_MAPPING[label_d]))
                
    handled_cols = set()
    
    def clean_series(series):
        return pd.to_numeric(series.astype(str).str.replace(r'[\s\u202F\xa0]+', '', regex=True).str.replace(',', '.', regex=False), errors='coerce')
    
    for g_col, d_col in pairs:
        if g_col in df_player.columns and d_col in df_player.columns:
            s_g = clean_series(df_player[g_col])
            s_d = clean_series(df_player[d_col])
            
            valid_mask = s_g.notna() & s_d.notna()
            if valid_mask.any():
                s_sum = s_g[valid_mask] + s_d[valid_mask]
                best_idx = s_sum.idxmax() 
                
                virtual_row[g_col] = s_g.loc[best_idx]
                virtual_row[d_col] = s_d.loc[best_idx]
                
                date_val = df_player.loc[best_idx, date_col] if date_col and pd.notna(df_player.loc[best_idx, date_col]) else "-"
                virtual_row[f"{g_col}_date"] = date_val
                virtual_row[f"{d_col}_date"] = date_val
                
            handled_cols.update([g_col, d_col])
            
    for col in df_player.columns:
        # On ignore les colonnes déjà traitées
        if col in handled_cols or col in colonnes_base or col in [date_col, 'Joueur', 'Date']: continue
        series_num = clean_series(df_player[col])
        if not series_num.dropna().empty:
            is_min = (col in SENS_KPI and SENS_KPI[col] == "min") or is_inverted(col)
            if is_min:
                best_idx = series_num.idxmin()
            else:
                best_idx = series_num.idxmax()
                
            virtual_row[col] = series_num.loc[best_idx]
            date_val = df_player.loc[best_idx, date_col] if date_col and pd.notna(df_player.loc[best_idx, date_col]) else "-"
            virtual_row[f"{col}_date"] = date_val
            
    return virtual_row

# ==========================================
# PAGE PRINCIPALE
# ==========================================

# Couleurs d'identité par profil (jusqu'à 4). Rouge/bleu = les 2 couleurs
# historiques du comparateur 1 vs 1 ; violet/orange ajoutées pour les
# profils 3 et 4 -- demande explicite d'ouvrir le comparateur à plus de 2
# joueurs (un agent qui positionne son joueur face à plusieurs profils
# comparables ne pouvait pas le faire avant).
PROFILE_COLORS = [SDR_RED, SDR_BLUE, "#8E44AD", "#F39C12"]


@st.cache_data(show_spinner=False)
def _best_data_coverage_players(df: pd.DataFrame, equipe: str | None, n: int = 2) -> list[str]:
    """
    Renvoie les `n` joueurs (d'une équipe donnée, ou de tout le club si
    absente/non trouvée) avec le PLUS de tests renseignés, toutes sessions
    confondues -- pour proposer par défaut, à l'ouverture du Comparateur,
    des exemples "parlants" (profils complets) plutôt qu'un choix
    alphabétique arbitraire qui tombe souvent sur un joueur avec peu de
    données remplies.
    """
    if df.empty or 'Joueur' not in df.columns:
        return []
    test_cols = [c for c in set(COL_MAPPING.values()) if c in df.columns]
    if not test_cols:
        return []
    df_scope = df
    if equipe and 'Equipe' in df.columns:
        df_eq = df[df['Equipe'].astype(str) == equipe]
        if not df_eq.empty:
            df_scope = df_eq
    coverage = df_scope.groupby('Joueur')[test_cols].apply(lambda g: g.notna().any(axis=0).sum())
    ranked = coverage.sort_values(ascending=False)
    return list(ranked.head(n).index)


def show_comparateur_page(df):
    st.markdown(f"<h2 style='text-align: center; color: {SDR_RED}; font-weight: 900; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 25px;'>Comparateur de Profils</h2>", unsafe_allow_html=True)

    col_session = "Session" if "Session" in df.columns else next((c for c in df.columns if 'session' in str(c).lower()), None)
    if not col_session:
        st.warning("Aucune colonne Session trouvée dans les données.")
        return

    equipes_dispos = sorted(df['Equipe'].dropna().astype(str).unique()) if 'Equipe' in df.columns else ["N/A"]

    n_profils = st.radio("Nombre de profils à comparer", [2, 3, 4], horizontal=True, key="n_profils_cmp")

    # Équipe par défaut = PRO (si dispo), et pour les 2 premiers profils, les
    # 2 joueurs de cette équipe avec le plus de tests renseignés -- un
    # exemple de comparaison "parlant" dès l'ouverture de l'onglet, plutôt
    # qu'un choix alphabétique qui tombe souvent sur des profils incomplets.
    # Ça ne s'applique qu'au premier affichage : dès que l'utilisateur choisit
    # autre chose, son choix (mémorisé par les clés eq{i}/j{i}) prend le dessus.
    default_equipe = "PRO" if "PRO" in equipes_dispos else (equipes_dispos[0] if equipes_dispos else None)
    default_best_players = _best_data_coverage_players(df, default_equipe, n=2) if default_equipe else []

    cols_sel = st.columns(n_profils)
    profils = []
    for i, col in enumerate(cols_sel):
        color = PROFILE_COLORS[i]
        with col:
            st.markdown(f"<div style='border-left: 4px solid {color}; padding-left: 8px; margin-bottom: 10px;'><b style='color:{color}; font-size:14px;'>PROFIL {i+1}</b></div>", unsafe_allow_html=True)
            eq_default_idx = equipes_dispos.index(default_equipe) if default_equipe in equipes_dispos else 0
            eq = st.selectbox("Équipe", equipes_dispos, index=eq_default_idx, key=f"eq{i}", label_visibility="collapsed")
            joueurs_eq = sorted(df[df['Equipe'] == eq]['Joueur'].dropna().unique()) if 'Equipe' in df.columns else sorted(df['Joueur'].dropna().unique())
            if eq == default_equipe and i < len(default_best_players) and default_best_players[i] in joueurs_eq:
                j_default = joueurs_eq.index(default_best_players[i])
            else:
                j_default = min(i, len(joueurs_eq) - 1) if joueurs_eq else 0
            j = st.selectbox("Joueur", joueurs_eq, key=f"j{i}", index=j_default, label_visibility="collapsed") if joueurs_eq else None
            if j:
                sessions_j = ["🏆 Record de Saison"] + sorted(df[(df['Equipe'] == eq) & (df['Joueur'] == j)][col_session].dropna().astype(str).unique()) if 'Equipe' in df.columns else []
                sess = st.selectbox("Session", sessions_j, key=f"s{i}", label_visibility="collapsed")
            else:
                sess = None
        profils.append({"joueur": j, "session": sess, "color": color})

    if any(p["joueur"] is None or p["session"] is None for p in profils):
        return

    # Doublons stricts (même joueur + même session) -> comparaison inutile
    seen = set()
    for p in profils:
        cle = (p["joueur"], p["session"])
        if cle in seen:
            st.warning("Veuillez sélectionner des profils différents (joueur et/ou session).")
            return
        seen.add(cle)

    # --- GÉNÉRATION DES LIGNES VIRTUELLES ---
    try:
        for p in profils:
            j, sess = p["joueur"], p["session"]
            if sess == "🏆 Record de Saison":
                p["row"] = get_best_season_record_paired(df[df['Joueur'] == j])
            else:
                row_dict = df[(df['Joueur'] == j) & (df[col_session].astype(str) == sess)].iloc[0].to_dict()
                date_e = row_dict.get("Session exact", sess)
                for k in list(row_dict.keys()):
                    row_dict[f"{k}_date"] = date_e
                p["row"] = row_dict
    except Exception:
        st.error("Données introuvables pour cette sélection.")
        return

    # --- EN-TÊTE VISUEL (photos + VS entre chaque profil) ---
    header_html = "<div style='display:flex; flex-direction:row; align-items:center; justify-content:center; flex-wrap:wrap; gap:14px; width:100%; margin-bottom:30px;'>"
    for i, p in enumerate(profils):
        j, sess, color, row_p = p["joueur"], p["session"], p["color"], p["row"]
        photo = get_best_photo_path(j)
        img_src = f"data:image/png;base64,{img_to_b64(photo)}" if photo else ""
        html_img = f'<img src="{img_src}" style="width:100px; height:100px; object-fit:cover; object-position:top center; border-radius:50%; border:4px solid {color}; box-shadow:0 6px 15px rgba(0,0,0,0.15); flex-shrink:0;">' if img_src else f'<div style="width:100px; height:100px; border-radius:50%; border:4px solid {color}; background:#eee; display:flex; align-items:center; justify-content:center; color:#666; font-size:12px; font-weight:bold; flex-shrink:0;">PHOTO</div>'
        t_clean = clean_val(row_p.get('Taille (cm)'))
        age, taille, poids = format_number(row_p.get('Age')), f"{t_clean:.1f}" if t_clean is not None else "-", format_number(row_p.get('Poids (kg)'))
        meta = f"{clean_val_display(age, 'ans')} | {clean_val_display(taille, 'cm')} | {clean_val_display(poids, 'kg')}"
        header_html += "<div style='display:flex; flex-direction:column; align-items:center; text-align:center; min-width:140px;'>"
        header_html += html_img
        header_html += f"<h3 style='color:{color}; margin:8px 0 0 0; font-weight:900; font-size:16px; text-transform:uppercase;'>{j}</h3>"
        header_html += f"<p style='color:#555; margin:4px 0 0 0; font-size:12px; line-height:1.4;'><span style='background:{color}18; color:{color}; padding:2px 8px; border-radius:4px; font-weight:bold;'>{row_p.get('Equipe', 'N/A')}</span><br><b>{row_p.get('Position', 'N/A')}</b><br>{meta}<br><span style='font-style:italic; font-size:11px; color:#666;'><b>{sess}</b></span></p>"
        header_html += "</div>"
        if i < len(profils) - 1:
            header_html += "<div style='flex:0 0 auto; text-align:center;'><div style='background:#2b2b2b; color:white; display:flex; align-items:center; justify-content:center; width:42px; height:42px; border-radius:50%; font-weight:900; font-style:italic; font-size:14px; box-shadow:0 4px 10px rgba(0,0,0,0.2);'>VS</div></div>"
    header_html += "</div>"
    st.markdown(header_html, unsafe_allow_html=True)

    # Au-delà de 2 profils, le radar devient vite illisible (courbes qui se
    # superposent). Le tableau et les barres, eux, restent lisibles à 4 --
    # donc on les garde complets, et on limite juste le RADAR à 2 profils
    # affichés à la fois, choisis par l'utilisateur (par défaut les 2
    # premiers). Rien n'est perdu : le détail des 4 reste dans le tableau.
    radar_idx = list(range(len(profils)))
    if len(profils) > 2:
        st.markdown("<div style='font-size:13px; color:#555; margin-top:4px;'>👁️ Profils affichés sur le <b>radar</b> (2 max, pour rester lisible — le tableau et les barres affichent toujours les 4) :</div>", unsafe_allow_html=True)
        radar_options = [f"Profil {i+1} — {p['joueur']}" for i, p in enumerate(profils)]
        radar_sel = st.multiselect(
            "Profils sur le radar", radar_options, default=radar_options[:2],
            max_selections=2, label_visibility="collapsed", key="radar_profils_sel",
        )
        radar_idx = [i for i, opt in enumerate(radar_options) if opt in radar_sel]
        if not radar_idx:
            radar_idx = list(range(min(2, len(profils))))

    # --- GRAPHIQUES ET TABLEAUX ---
    for cat_title, items in OFFICIAL_STRUCTURE.items():
        if "isociné" in cat_title.lower() or "biodex" in cat_title.lower(): continue

        labels = []
        norm_series = [[] for _ in profils]
        raw_series = [[] for _ in profils]
        table_data = []

        for label in items:
            if any(b in label for b in ["Q Conc", "IJ Conc", "IJ Exc", "Ratio Mixte"]): continue

            col_name = find_col(df, label)
            if not col_name: continue

            vals = [clean_val(p["row"].get(col_name)) for p in profils]
            if all(v is None for v in vals): continue

            unit = UNITS.get(label, "")
            unit_str = f" {unit}" if unit else ""

            mean_val = None
            clean_team_col = df[col_name].astype(str).str.replace(',', '.').replace(['#VALEUR!', '#DIV/0!', 'nan', 'None', ''], None)
            valid_team_vals = pd.to_numeric(clean_team_col, errors='coerce').dropna()
            if not valid_team_vals.empty: mean_val = valid_team_vals.mean()

            labels.append(label)
            vals_str = [f"{v:.1f}{unit_str}" if v is not None else "-" for v in vals]
            pcts = [calculate_percentile(df, col_name, v) if v is not None else 0 for v in vals]
            for i in range(len(profils)):
                raw_series[i].append(vals_str[i])
                norm_series[i].append(pcts[i])

            mean_str = f"{float(mean_val):.1f}{unit_str}" if pd.notna(mean_val) else "-"

            # Meilleur profil sur ce test (respecte le sens inversé, ex. temps
            # sur 10m : plus petit = meilleur). Pas de "meilleur" affiché en
            # cas d'égalité stricte entre au moins deux profils.
            inverted = is_inverted(col_name)
            valid_idx = [i for i, v in enumerate(vals) if v is not None]
            best_i = None
            if len(valid_idx) >= 2:
                best_i = min(valid_idx, key=lambda i: vals[i]) if inverted else max(valid_idx, key=lambda i: vals[i])
                if sum(1 for i in valid_idx if vals[i] == vals[best_i]) > 1:
                    best_i = None

            cells = []
            for i, p in enumerate(profils):
                d_str = format_date_str(p["row"].get(f"{col_name}_date", ""))
                d_html = f"<br><span style='font-size:10px; color:#707070; font-weight:normal; font-style:italic;'>{d_str}</span>" if d_str else ""
                is_best = (i == best_i)
                v_color = p["color"] if is_best else "#333"
                star = " 🏆" if is_best else ""
                cells.append(f"<span style='color:{v_color}; font-weight:bold;'>{vals_str[i]}{star}</span>{d_html}")

            table_data.append({"Test": label, "cells": cells, "Moy_Equipe": mean_str})

        if labels:
            st.markdown(f"<h3 style='color:{SDR_RED}; margin-top:40px; text-transform:uppercase; font-weight:900; border-bottom:3px solid {SDR_RED}; padding-bottom:10px; margin-bottom:30px; font-size:24px; letter-spacing:1px;'>{cat_title}</h3>", unsafe_allow_html=True)

            hover_pct = "%{theta}<br>Valeur : <b>%{customdata}</b><br>Score : %{r:.0f}%<extra></extra>"
            sous_groupes_cat = RADAR_SOUS_GROUPES.get(cat_title)

            def _radar_series(idx_labels):
                """Séries filtrées sur un sous-ensemble d'indices de `labels`."""
                return [
                    {
                        "name": p["joueur"],
                        "values": [norm_series[i][k] for k in idx_labels],
                        "raw_values": [raw_series[i][k] for k in idx_labels],
                        "color": p["color"], "width": 3, "hovertemplate": hover_pct,
                    }
                    for i, p in enumerate(profils) if i in radar_idx
                ]

            if sous_groupes_cat:
                # Catégorie surchargée (kiné, terrain...) : un radar plus
                # petit PAR QUALITÉ physique plutôt qu'un seul radar géant
                # où les axes n'ont plus rien à voir entre eux (mobilité +
                # force + symétrie mélangées = forme illisible). Le tableau
                # et les barres, eux, gardent TOUS les tests de la catégorie.
                groupes_ordre = []
                groupes_idx = {}
                for k, lbl in enumerate(labels):
                    grp = sous_groupes_cat.get(lbl)
                    if not grp:
                        continue
                    if grp not in groupes_idx:
                        groupes_idx[grp] = []
                        groupes_ordre.append(grp)
                    groupes_idx[grp].append(k)
                groupes_ordre = [g for g in groupes_ordre if len(groupes_idx[g]) >= 2]

                if groupes_ordre:
                    cols_radars = st.columns(len(groupes_ordre))
                    for col, grp in zip(cols_radars, groupes_ordre):
                        with col:
                            st.markdown(f"<div style='text-align:center; font-size:13px; font-weight:800; color:#555; text-transform:uppercase; margin-bottom:4px;'>{grp}</div>", unsafe_allow_html=True)
                            idx_grp = groupes_idx[grp]
                            fig_radar_grp = build_radar(
                                [labels[k] for k in idx_grp],
                                _radar_series(idx_grp),
                                height=320,
                                margin=dict(l=30, r=30, t=20, b=10),
                            )
                            st.plotly_chart(fig_radar_grp, width='stretch', config={'displayModeBar': False}, key=f"radar_{cat_title}_{grp}")

                fig_bars = go.Figure()
                for i, p in enumerate(profils):
                    fig_bars.add_trace(go.Bar(y=labels, x=norm_series[i], orientation='h', name=p["joueur"], marker_color=p["color"], text=raw_series[i], textposition='auto', insidetextanchor='end', textfont=dict(color='white', weight='bold', size=11), hoverinfo='skip'))
                fig_bars.update_layout(
                    barmode='group', bargap=0.2, bargroupgap=0.05, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(visible=False, range=[0, 115]), yaxis=dict(showgrid=False, tickfont=dict(size=12, color="#444", weight="bold"), categoryorder='array', categoryarray=labels[::-1]),
                    margin=dict(l=10, r=20, t=30, b=10), height=max(450, 28 * len(labels)), showlegend=(len(profils) > 2)
                )
                st.plotly_chart(fig_bars, width='stretch')
            else:
                # Catégorie déjà homogène/courte (salle, composition, 1080) :
                # comportement d'origine, un seul radar à côté des barres.
                col_radar, col_bars = st.columns(2)
                with col_radar:
                    fig_radar = build_radar(
                        labels,
                        _radar_series(list(range(len(labels)))),
                        height=450,
                        margin=dict(l=60, r=60, t=40, b=10),
                    )
                    st.plotly_chart(fig_radar, width='stretch', config={'displayModeBar': False})

                with col_bars:
                    fig_bars = go.Figure()
                    for i, p in enumerate(profils):
                        fig_bars.add_trace(go.Bar(y=labels, x=norm_series[i], orientation='h', name=p["joueur"], marker_color=p["color"], text=raw_series[i], textposition='auto', insidetextanchor='end', textfont=dict(color='white', weight='bold', size=11), hoverinfo='skip'))
                    fig_bars.update_layout(
                        barmode='group', bargap=0.2, bargroupgap=0.05, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(visible=False, range=[0, 115]), yaxis=dict(showgrid=False, tickfont=dict(size=12, color="#444", weight="bold"), categoryorder='array', categoryarray=labels[::-1]),
                        margin=dict(l=10, r=20, t=30, b=10), height=450, showlegend=(len(profils) > 2)
                    )
                    st.plotly_chart(fig_bars, width='stretch')

            st.markdown("<h5 style='color:#555; margin-top:15px; font-size:14px; border-bottom:2px solid #eee; padding-bottom:5px;'> Détails</h5>", unsafe_allow_html=True)
            t_html = "<table style='width:100%; border-collapse:collapse; font-size:13px; text-align:center; font-family:sans-serif; margin-bottom: 20px;'>"
            t_html += "<tr style='background-color:#f8f9fa; color:#111; border-bottom:2px solid #ccc;'><th style='padding:10px; text-align:left;'>Test Physique</th>"
            for p in profils:
                t_html += f"<th style='padding:10px; color:{p['color']}; font-size:14px;'>{p['joueur']}</th>"
            t_html += "<th style='padding:10px; color:#666;'>Moy. Équipe</th></tr>"

            for r_data in table_data:
                t_html += f"<tr style='border-bottom:1px solid #eee;'><td style='padding:8px; text-align:left; font-weight:bold; color:#444;'>{r_data['Test']}</td>"
                for cell in r_data["cells"]:
                    t_html += f"<td style='padding:8px; font-size:14px;'>{cell}</td>"
                t_html += f"<td style='padding:8px; color:#666; font-style:italic;'>{r_data['Moy_Equipe']}</td></tr>"
            t_html += "</table>"
            st.markdown(t_html, unsafe_allow_html=True)
        else:
            st.info(f"Aucune donnée disponible pour ces profils dans la catégorie {cat_title}.")