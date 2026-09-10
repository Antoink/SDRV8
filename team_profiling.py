import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
# plotly.express (px) : importé localement dans show_team_page() plus bas,
# pas ici -- import lourd, alourdissait le lancement de toute l'appli alors
# que team_profiling.py est chargé sans condition au démarrage. `altair`
# était importé ici mais jamais utilisé (mort) : supprimé.

SDR_RED = "#D71920"

def update_from_select():
    # On vérifie que la clé existe avant d'essayer de la lire
    if "manual_player_picker" in st.session_state:
        st.session_state.selected_player_profiling = st.session_state.manual_player_picker

# remove_accents / find_column_in_df / clean_numeric_series / is_inverted_metric
# viennent maintenant de data_utils.py (partagees avec profiling.py,
# profiling_report.py, comparateur.py -- voir l'en-tete de ce module : ces
# fonctions existaient en plusieurs copies legerement differentes, avec une
# protection anti-collision GPS/1080 tantot absente tantot incomplete selon
# le fichier).
from data_utils import (
    remove_accents, find_column_in_df, clean_numeric_series, clean_numeric_value,
    calculate_percentile, get_column_stats, is_inverted as is_inverted_metric,
)
from charts import build_radar

# Regroupement des tests par qualité physique -- UNIQUEMENT pour les vues
# d'ensemble collectives ci-dessous (heatmap, radar par poste). Contrairement
# au Comparateur (où l'on garde le découpage kiné/salle/terrain, plus
# familier pour comparer 2 joueurs test par test), ici on agrège beaucoup de
# joueurs à la fois -- un découpage transversal par qualité physique est
# plus parlant pour une vue "gros grain" du groupe.
QUALITES_PHYSIQUES = {
    "Force Max": ["Squat belt (N)", "Peak Force CMJ"],
    "Puissance / Explosivité": ["CMJ 2JB", "RFD CMJ", "RSI CMJ", "Wattbike (6s)"],
    "Vitesse / Accélération": ["Vmax", "Amax", "Dmax", "Temps sur 10m"],
    "Endurance": ["VMA", "SV1", "SV2", "Test 1km (s)"],
    "Mobilité": ["Sit And Reach", "Knee To Wall (G)", "Knee To Wall (D)"],
    "Force spé. membres inf.": [
        "Adducteurs (G)", "Adducteurs (D)", "Abducteurs (G)", "Abducteurs (D)",
        "Nordic Ischio (G)", "Nordic Ischio (D)", "Inverseur (G)", "Inverseur (D)",
        "Everseur (G)", "Everseur (D)", "Endurance Heel Raise (G)", "Endurance Heel Raise (D)",
    ],
}

POSTE_COLORS = {"GARDIEN": "#F39C12", "DÉFENSEUR": "#1E3A8A", "MILIEU": "#27AE60", "ATTAQUANT": "#D71920", "AUTRE": "#8E44AD"}

def get_unit(label):
    l = label.lower()
    if "ratio" in l or "nb " in l: return ""
    if "n/kg" in l: return "N/kg"
    if "w/kg" in l: return "W/kg"
    if "m/s2" in l or "m/s²" in l: return "m/s²"
    if "%" in l or "img" in l: return "%"
    if "amax" in l or "dmax" in l: return "m/s²"
    if "conc" in l or "exc" in l or "nm" in l: return "Nm"
    if "1rm" in l or "poids" in l: return "kg"
    if "watt" in l or "keiser" in l or "tirage" in l or "couché" in l: return "W"
    if "add" in l or "abd" in l or "nordic" in l or "force" in l or "landing" in l: return "N"
    if "vma" in l or "vmax" in l or "vitesse" in l: return "km/h"
    if "cmj" in l or "saut" in l or "taille" in l or "reach" in l or "knee" in l: return "cm"
    if "temps" in l or "chrono" in l or "10m" in l or "505" in l: return "s"
    if "distance" in l or "landmine" in l: return "m"
    if "score" in l: return "pts"
    if "rfd" in l: return "N/s"
    if "rpd" in l: return "W/s"
    return ""

def get_poste_large(position):
    pos = str(position).upper().strip()
    if "GB" in pos: return "GARDIEN"
    if "DC" in pos or "DL" in pos: return "DÉFENSEUR"
    if "MD" in pos or "MC" in pos or "MO" in pos: return "MILIEU"
    if "EXC" in pos or "AT" in pos: return "ATTAQUANT"
    return "AUTRE"

def _render_heatmap_joueurs(df_ref, df_viz_base, structure_dict):
    """
    Vue d'ensemble Joueur × Indicateur : un percentile par cellule (vs
    `df_ref`, le groupe filtré au-dessus), coloré vert->rouge. Pensé pour
    répondre à un vrai manque : aujourd'hui il faut ouvrir un indicateur à
    la fois pour voir "qui est en difficulté sur quoi" dans le groupe.
    """
    st.markdown("---")
    st.markdown(f"<h4 style='color:{SDR_RED};'>Vue d'ensemble : Joueur × Indicateur</h4>", unsafe_allow_html=True)
    st.caption("Percentile de chaque joueur sur les tests sélectionnés, par rapport au groupe filtré ci-dessus. Vert = fort, rouge = axe de travail.")

    c_cat, c_items = st.columns([1, 2])
    with c_cat:
        cat_heat = st.selectbox("Catégorie de tests :", list(structure_dict.keys()), key="heatmap_cat")
    items_heat = structure_dict[cat_heat]
    with c_items:
        sel_items = st.multiselect("Tests à inclure :", items_heat, default=items_heat[:8], key="heatmap_items")

    if not sel_items:
        st.info("Sélectionne au moins un test.")
        return

    joueurs_h = sorted(df_viz_base['Joueur'].dropna().unique())
    if not joueurs_h:
        st.info("Aucun joueur disponible pour cette sélection.")
        return

    # Colonnes résolues UNE FOIS (pas une fois par joueur) : find_column_in_df
    # compare le label à toutes les colonnes du DataFrame, inutile de le
    # refaire `len(joueurs) x len(tests)` fois pour le même résultat.
    cols_resolved = [find_column_in_df(df_ref, label) for label in sel_items]

    pct_matrix, raw_matrix = [], []
    for j in joueurs_h:
        row_j = df_viz_base[df_viz_base['Joueur'] == j]
        pct_row, raw_row = [], []
        for col in cols_resolved:
            val = None
            if col and col in row_j.columns:
                valides = row_j[col].dropna()
                if not valides.empty:
                    val = clean_numeric_value(valides.iloc[-1])
            if val is None:
                pct_row.append(None)
                raw_row.append("-")
            else:
                _, pct = calculate_percentile(df_ref, col, val)
                pct_row.append(pct)
                raw_row.append(f"{val:.1f}")
        pct_matrix.append(pct_row)
        raw_matrix.append(raw_row)

    fig_heat = go.Figure(data=go.Heatmap(
        z=pct_matrix, x=sel_items, y=joueurs_h, text=raw_matrix,
        texttemplate="%{text}", textfont=dict(size=11, weight='bold'),
        colorscale='RdYlGn', zmin=0, zmax=100,
        hovertemplate="<b>%{y}</b><br>%{x}<br>Valeur : %{text}<br>Percentile : %{z:.0f}%<extra></extra>",
        colorbar=dict(title="Pctl.", ticksuffix="%"),
    ))
    fig_heat.update_layout(
        height=max(320, 34 * len(joueurs_h) + 80),
        margin=dict(l=10, r=10, t=20, b=100),
        xaxis=dict(tickangle=-35, side='top'),
        template="simple_white",
    )
    st.plotly_chart(fig_heat, width='stretch', config={'displayModeBar': False})


def _render_radar_postes(df_ref, df_viz_base, df_pro_ref=None):
    """
    Radar de synthèse par poste : un axe = une qualité physique (cf.
    QUALITES_PHYSIQUES), une ligne = la moyenne des percentiles du poste sur
    tous les tests de cette qualité. Vue "gros grain" pour repérer si un
    poste est structurellement en retard sur une qualité -- complète la
    heatmap (fine, joueur par joueur) sans la remplacer.
    """
    st.markdown("---")
    st.markdown(f"<h4 style='color:{SDR_RED};'>Profil de synthèse par poste</h4>", unsafe_allow_html=True)
    st.caption("Percentile moyen du poste sur chaque qualité physique, vs le groupe filtré ci-dessus.")

    postes_dispo = sorted(df_viz_base['Poste_Groupe'].dropna().unique())
    if len(postes_dispo) < 2:
        st.info("Pas assez de postes différents dans la sélection actuelle pour ce tracé.")
        return

    show_pro_overlay = False
    if df_pro_ref is not None and not df_pro_ref.empty:
        show_pro_overlay = st.checkbox(
            "⭐ Superposer le standard PRO (référence par poste)",
            value=False,
            key="radar_postes_pro_overlay",
            help="Pour chaque poste affiché, ajoute une ligne pointillée montrant où se "
                 "situe la moyenne des PRO de CE MÊME poste, sur l'échelle de percentile "
                 "du groupe actuellement affiché -- utile pour situer une catégorie de "
                 "formation (ex: ESPOIR) par rapport au niveau professionnel, poste par poste.",
        )

    postes_arr = df_viz_base['Poste_Groupe'].to_numpy()
    postes_pro_dispo = []
    pro_postes_arr = None
    if show_pro_overlay:
        postes_pro_dispo = [p for p in postes_dispo if p in set(df_pro_ref['Poste_Groupe'].dropna().unique())]
        pro_postes_arr = df_pro_ref['Poste_Groupe'].to_numpy()

    axes, series_par_poste = [], {p: [] for p in postes_dispo}
    series_pro_par_poste = {p: [] for p in postes_pro_dispo}
    for qualite, tests in QUALITES_PHYSIQUES.items():
        # Percentile de chaque joueur sur chaque test de cette qualité,
        # calculé de façon VECTORISÉE (une comparaison matricielle numpy par
        # test) plutôt qu'avec une boucle `df.iterrows()` -- iterrows() est
        # notoirement très lent en pandas (recrée un objet Series à chaque
        # ligne), et ici il tournait pour CHAQUE test de CHAQUE qualité
        # physique sur TOUTE l'équipe : c'était la source de lenteur la plus
        # nette de cet onglet, sensible dès qu'on changeait n'importe quel
        # filtre en haut de la page (même un filtre qui ne concerne pas ce
        # bloc), puisque la page entière se recalcule à chaque interaction.
        pct_par_poste = {p: [] for p in postes_dispo}
        pct_par_poste_pro = {p: [] for p in postes_pro_dispo}
        has_data = False
        for label in tests:
            col = find_column_in_df(df_ref, label)
            if not col or col not in df_viz_base.columns:
                continue
            valid_values, _ = get_column_stats(df_ref, col)
            if valid_values is None:
                continue
            vv = np.asarray(valid_values, dtype=float)
            player_vals = pd.to_numeric(
                df_viz_base[col].astype(str).str.replace(r'[\s \xa0]+', '', regex=True).str.replace(',', '.', regex=False),
                errors='coerce',
            ).to_numpy(dtype=float)
            valid_mask = ~np.isnan(player_vals)
            if not valid_mask.any():
                continue
            if is_inverted_metric(label):
                pct_arr = (vv[:, None] >= player_vals[None, :]).mean(axis=0) * 100
            else:
                pct_arr = (vv[:, None] <= player_vals[None, :]).mean(axis=0) * 100
            has_data = True
            for p in postes_dispo:
                mask = valid_mask & (postes_arr == p)
                if mask.any():
                    pct_par_poste[p].extend(pct_arr[mask].tolist())

            if show_pro_overlay and col in df_pro_ref.columns:
                pro_vals = pd.to_numeric(
                    df_pro_ref[col].astype(str).str.replace(r'[\s \xa0]+', '', regex=True).str.replace(',', '.', regex=False),
                    errors='coerce',
                ).to_numpy(dtype=float)
                pro_valid_mask = ~np.isnan(pro_vals)
                if pro_valid_mask.any():
                    if is_inverted_metric(label):
                        pct_arr_pro = (vv[:, None] >= pro_vals[None, :]).mean(axis=0) * 100
                    else:
                        pct_arr_pro = (vv[:, None] <= pro_vals[None, :]).mean(axis=0) * 100
                    for p in postes_pro_dispo:
                        mask = pro_valid_mask & (pro_postes_arr == p)
                        if mask.any():
                            pct_par_poste_pro[p].extend(pct_arr_pro[mask].tolist())
        if not has_data:
            continue
        axes.append(qualite)
        for p in postes_dispo:
            vals = pct_par_poste[p]
            series_par_poste[p].append(round(sum(vals) / len(vals)) if vals else 0)
        for p in postes_pro_dispo:
            vals = pct_par_poste_pro[p]
            series_pro_par_poste[p].append(round(sum(vals) / len(vals)) if vals else 0)

    if len(axes) < 3:
        st.info("Pas assez de qualités physiques renseignées dans la sélection actuelle pour ce tracé.")
        return

    series_traces = [
        {"name": p, "values": series_par_poste[p], "color": POSTE_COLORS.get(p, "#555"), "width": 3}
        for p in postes_dispo
    ]
    if show_pro_overlay:
        for p in postes_pro_dispo:
            series_traces.append({
                "name": f"PRO — {p}",
                "values": series_pro_par_poste[p],
                "color": POSTE_COLORS.get(p, "#555"),
                "width": 2,
                "dash": True,
                "fill": False,
            })
        if not postes_pro_dispo:
            st.caption("ℹ️ Aucun poste en commun avec le groupe PRO pour cette sélection.")

    fig_postes = build_radar(
        axes,
        series_traces,
        height=480,
    )
    st.plotly_chart(fig_postes, width='stretch', config={'displayModeBar': False})


def show_team_page(df, structure_dict, df_all_teams=None):
    import plotly.express as px

    df = df.copy()
    col_position = find_column_in_df(df, "Position")
    
    if col_position:
        df['Poste_Groupe'] = df[col_position].apply(get_poste_large)
    else:
        col_poste_excel = find_column_in_df(df, "Poste")
        if col_poste_excel:
            df['Poste_Groupe'] = df[col_poste_excel].astype(str).str.upper()
        else:
            df['Poste_Groupe'] = "AUTRE"

    st.markdown(f"<h2 style='color:{SDR_RED}; border-bottom:1px solid {SDR_RED}; padding-bottom:5px;'>ANALYSE COLLECTIVE</h2>", unsafe_allow_html=True)
    
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    if 'selected_player_profiling' not in st.session_state:
        st.session_state.selected_player_profiling = None

    st.markdown("   ")
  
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        cat_sel = st.selectbox("Catégorie : ", list(structure_dict.keys()))
    with c2:
        metric_sel = st.selectbox("Indicateur : ", structure_dict[cat_sel])
    
    col_name = find_column_in_df(df, metric_sel)
    
    with c3:
        filter_type = st.radio("Filtre d'effectif :", ["Groupe entier", "Par Poste (Général)", "Par Position (Détaillée)"], horizontal=True)
        col_filter = None
        sel_options = []
        
        if filter_type == "Par Poste (Général)":
            col_filter = "Poste_Groupe"
        elif filter_type == "Par Position (Détaillée)":
            col_filter = col_position

        if col_filter and col_filter in df.columns:
            all_options = sorted(df[col_filter].dropna().unique())
            sel_options = st.multiselect("Sélectionnez :", all_options, default=all_options)

    if not col_name:
        st.error("Données introuvables.")
        return

    df_main = df.copy()
    if col_filter and sel_options:
        df_main = df_main[df_main[col_filter].isin(sel_options)]

    df_main['Valeur_Clean'] = clean_numeric_series(df_main[col_name])
    df_main = df_main.dropna(subset=['Valeur_Clean', 'Joueur'])
    
    inverted = is_inverted_metric(metric_sel)
    avg_val = df_main['Valeur_Clean'].mean()
    unit = get_unit(metric_sel)

    st.markdown("---")

    st.subheader(f"Classement Équipe : {metric_sel}")

    if inverted:
        df_sorted = df_main.sort_values('Valeur_Clean', ascending=True)
    else:
        df_sorted = df_main.sort_values('Valeur_Clean', ascending=False)

    color_col = "Poste_Groupe" if filter_type != "Groupe entier" else None
    
    fig_all = px.bar(
        df_sorted, 
        x='Joueur', 
        y='Valeur_Clean',
        color=color_col, 
        text='Valeur_Clean',
        color_discrete_sequence=[SDR_RED, 'black', '#555', '#888'] if color_col else [SDR_RED]
    )
    
    fig_all.add_hline(y=avg_val, line_dash="dash", line_color="#333", annotation_text=f"Moyenne : {avg_val:.2f}")
    fig_all.update_traces(texttemplate='%{text:.2f}', textposition='outside')
    # 1. Calculer le maximum pour donner de l'air en haut
    y_max = df_sorted['Valeur_Clean'].max()
    
    fig_all.update_layout(
        xaxis_title="", 
        yaxis_title=f"{metric_sel} ({unit})",
        template="simple_white",
        height=600,
        margin=dict(t=80, b=100, l=50, r=50),
        xaxis=dict(tickangle=-45),
        # FORÇAGE DE LA HAUTEUR : On ajoute 15% de marge en haut du max
        yaxis=dict(range=[0, y_max * 1.15]) 
    )
    
    st.plotly_chart(fig_all, width='stretch')

    # --- CRÉATION DE LA LISTE DE TOUTES LES VARIABLES DISPONIBLES ---
    # On ajoute 'Poste_Groupe' ici pour qu'il ne soit pas supprimé lors du nettoyage !
    colonnes_interdites = [
        'Joueur', 'N° GPS', 'Latéralité', 'Poste', 'Position', 'Poste_Groupe',
        'Date de Naissance', 'DT exact', 'Session exact', 'Session', 'Equipe', 'Player ID', 'Numero'
    ]

    df_viz_base = df.copy()
    if col_filter and sel_options:
        df_viz_base = df_viz_base[df_viz_base[col_filter].isin(sel_options)]

    # Nettoyage systématique pour capter Poids, Taille, etc.
    for col in df_viz_base.columns:
        if col not in colonnes_interdites and not str(col).endswith("_date"):
            df_viz_base[col] = clean_numeric_series(df_viz_base[col])

    # Référence PRO pour l'overlay du radar par poste (demande 09/2026) :
    # préparée ici avec le MÊME nettoyage que df_viz_base pour être
    # directement comparable. None si on regarde déjà l'équipe PRO
    # elle-même (overlay non pertinent dans ce cas) ou si le DataFrame
    # toutes équipes n'a pas été fourni par l'appelant.
    df_pro_viz = None
    if df_all_teams is not None and "Equipe" in df_all_teams.columns and not (df["Equipe"].astype(str) == "PRO").all():
        df_pro_raw = df_all_teams[df_all_teams["Equipe"].astype(str) == "PRO"].copy()
        if not df_pro_raw.empty:
            if col_position and col_position in df_pro_raw.columns:
                df_pro_raw['Poste_Groupe'] = df_pro_raw[col_position].apply(get_poste_large)
            else:
                col_poste_excel_pro = find_column_in_df(df_pro_raw, "Poste")
                df_pro_raw['Poste_Groupe'] = (
                    df_pro_raw[col_poste_excel_pro].astype(str).str.upper() if col_poste_excel_pro else "AUTRE"
                )
            for col in df_pro_raw.columns:
                if col not in colonnes_interdites and not str(col).endswith("_date"):
                    df_pro_raw[col] = clean_numeric_series(df_pro_raw[col])
            df_pro_viz = df_pro_raw

    available_vars = [
        v for v in df_viz_base.columns
        if pd.api.types.is_numeric_dtype(df_viz_base[v])
        and v not in colonnes_interdites
        and not str(v).endswith("_date")
        and df_viz_base[v].notna().any()
    ]
    available_vars = sorted(available_vars)

    # "Analyse croisée" juste en dessous du graphique en barres (demande
    # explicite du département performance), AVANT la heatmap/le radar par
    # poste plus bas.
    st.markdown("---")
    st.markdown(f"<h4 style='color:{SDR_RED};'>Analyse croisée (Nuage de points)</h4>", unsafe_allow_html=True)

    if len(available_vars) < 2:
        st.warning("Pas assez de données numériques disponibles pour cette sélection.")
    else:
        c_sc1, c_sc2 = st.columns(2)
        with c_sc1:
            def_x = 0
            for i, k in enumerate(available_vars):
                if "vmax" in k.lower(): 
                    def_x = i
                    break
            scat_x = st.selectbox("Axe X (Horizontal)", available_vars, index=def_x, key="scat_x")
            
        with c_sc2:
            def_y = 1 if len(available_vars) > 1 else 0
            for i, k in enumerate(available_vars):
                if "cmj" in k.lower() or "saut" in k.lower(): 
                    def_y = i
                    break
            scat_y = st.selectbox("Axe Y (Vertical)", available_vars, index=def_y, key="scat_y")

        df_scatter = df_viz_base.dropna(subset=[scat_x, scat_y, 'Joueur']).copy()
        
        if not df_scatter.empty and len(df_scatter) > 1:
            mean_x = df_scatter[scat_x].mean()
            mean_y = df_scatter[scat_y].mean()
            
            # --- CALCUL DE LA CORRÉLATION ---
            corr_matrix = np.corrcoef(df_scatter[scat_x], df_scatter[scat_y])
            r = corr_matrix[0, 1]
            r_squared = r**2
            
            # --- AFFICHAGE DU GRAPHIQUE ---
            fig_scatter = px.scatter(
                df_scatter,
                x=scat_x, y=scat_y,
                color='Poste_Groupe',   # Sépare les couleurs par poste
                symbol='Poste_Groupe',  # Sépare les formes géométriques par poste
                text='Joueur',
                hover_data=['Joueur', 'Poste_Groupe'],
                color_discrete_sequence=[SDR_RED, '#111111', '#888888', '#F39C12', '#3498DB'] 
            )
            fig_scatter.add_vline(x=mean_x, line_width=1, line_dash="dash", line_color=SDR_RED)
            fig_scatter.add_hline(y=mean_y, line_width=1, line_dash="dash", line_color=SDR_RED)
            
            # Ajustement visuel pour que le texte et les formes soient bien visibles
            fig_scatter.update_traces(textposition='top center', marker=dict(size=14, line=dict(width=1.5, color='white')))
            
            fig_scatter.update_layout(
                title=f"{scat_x} vs {scat_y}",
                xaxis_title=scat_x, yaxis_title=scat_y,
                template="simple_white", height=550,
                legend_title_text="Postes"
            )
            st.plotly_chart(fig_scatter, width='stretch')

            # --- AFFICHAGE DU R ET R² ---
            if abs(r) > 0.9: strength = " Très Forte"
            elif abs(r) > 0.7: strength = "Forte"
            elif abs(r) > 0.4: strength = "Modérée"
            elif abs(r) > 0.2: strength = "Faible"
            else: strength = " Très Faible"
            
            st.markdown(f"""
            <div style='background-color:#f0f2f6; padding:15px; border-radius:8px; border-left:5px solid {SDR_RED};'>
                <div style='font-weight:bold; color:{SDR_RED};'>Analyse statistique :</div>
                Corrélation de Pearson (r) : <b>{r:.3f}</b> | Coefficient de détermination (R²) : <b>{r_squared:.3f}</b>
                <br><span style='font-size:0.9em; color:#555;'>La corrélation est considérée comme <b>{strength}</b>.</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("Pas assez de données pour calculer une corrélation (il faut au moins 2 joueurs).")

    _render_heatmap_joueurs(df, df_viz_base, structure_dict)
    _render_radar_postes(df, df_viz_base, df_pro_viz)

    st.markdown("---")

    st.subheader("Distribution des joueurs")
    
    if len(available_vars) > 0:
        dist_kpi = st.selectbox("Indicateur à analyser :", available_vars, index=0, key="dist_kpi_interactive")
        
        # Filtrage strict sur la variable choisie
        df_viz = df_viz_base.dropna(subset=[dist_kpi, 'Joueur']).copy()

        if not df_viz.empty:
            unit_d = get_unit(dist_kpi)
            mean_val = df_viz[dist_kpi].mean()
            
            all_p_list = sorted(df_viz['Joueur'].unique())
            
            col_sel_manual, _ = st.columns([1, 2])
            with col_sel_manual:
                curr_idx = 0
                if st.session_state.selected_player_profiling in all_p_list:
                    curr_idx = all_p_list.index(st.session_state.selected_player_profiling)
                
                def update_from_select():
                    st.session_state.selected_player_profiling = st.session_state.manual_player_picker
                
                manual_sel = st.selectbox(
                    "Sélectionner un joueur (ou cliquer sur le graphique) :", 
                    all_p_list, 
                    index=curr_idx,
                    key="manual_player_picker",
                    on_change=update_from_select
                )

            np.random.seed(42) 
            df_viz['Y_Jitter'] = np.random.uniform(-0.15, 0.15, size=len(df_viz))

            current_selection = st.session_state.selected_player_profiling
            if not current_selection:
                 current_selection = manual_sel
                 st.session_state.selected_player_profiling = manual_sel

            df_viz['SortOrder'] = df_viz['Joueur'].apply(lambda x: 1 if x == current_selection else 0)
            df_viz = df_viz.sort_values('SortOrder', ascending=True)

            colors = []
            sizes = []
            opacities = []
            lines_width = []
            lines_color = []

            for p in df_viz['Joueur']:
                if p == current_selection:
                    colors.append(SDR_RED)
                    sizes.append(25)
                    opacities.append(1.0)
                    lines_width.append(2)
                    lines_color.append('black')
                else:
                    colors.append("#888888")
                    sizes.append(12)
                    opacities.append(0.6)
                    lines_width.append(1)
                    lines_color.append('white')

            df_viz['Color'] = colors
            df_viz['Size'] = sizes
            df_viz['Opacity'] = opacities
            
            fig_interactive = go.Figure()

            fig_interactive.add_trace(go.Scatter(
                x=df_viz[dist_kpi],
                y=df_viz['Y_Jitter'], 
                mode='markers',
                text=df_viz['Joueur'],
                customdata=df_viz['Joueur'].values,
                marker=dict(
                    color=colors,
                    size=sizes,
                    opacity=opacities,
                    line=dict(width=lines_width, color=lines_color),
                    symbol='circle'
                ),
                hovertemplate="<b>%{text}</b><br>Valeur: %{x:.2f}<extra></extra>",
                showlegend=False
            ))

            fig_interactive.add_vline(x=mean_val, line_width=2, line_dash="dash", line_color=SDR_RED, 
                                      annotation_text="Moy", annotation_position="top right")

            fig_interactive.update_layout(
                title=f"Distribution : {dist_kpi}",
                xaxis_title=f"Valeur ({unit_d})",
                yaxis=dict(showticklabels=False, range=[-0.5, 0.5], showgrid=False),
                height=250,
                margin=dict(l=20, r=20, t=40, b=20),
                template="simple_white",
                clickmode='event+select',
                dragmode='zoom'
            )

            event = st.plotly_chart(
                fig_interactive, 
                on_select="rerun", 
                selection_mode="points", 
                width='stretch',
                key="dist_chart_interactive"
            )

            if event and event.get("selection") and event["selection"]["points"]:
                clicked_point = event["selection"]["points"][0]
                clicked_name = clicked_point.get("customdata")
                if clicked_name and clicked_name != st.session_state.selected_player_profiling:
                    st.session_state.selected_player_profiling = clicked_name
                    st.rerun()

            st.markdown("---")

            # Dans team_profiling.py, localise l'affichage des détails du joueur sélectionné (vers le bas du fichier) :
            sel_p = st.session_state.selected_player_profiling
            if sel_p:
                player_row = df_viz[df_viz['Joueur'] == sel_p]
                if not player_row.empty:
                    val_p = player_row[dist_kpi].iloc[0]
                    diff = val_p - mean_val
                    
                    st.markdown(f"<h3 style='text-align: center; color:{SDR_RED};'>{sel_p}</h3>", unsafe_allow_html=True)
                    
                    # AJOUT SÉCURITÉ : Affichage de la date du test si elle existe
                    # Dans le cas d'un Record de Saison, la date peut dépendre du test sélectionné
                    date_col = f"Date_{dist_kpi}" # Ta fonction de record génère souvent des colonnes "Date_Nom du Test"
                    if date_col in player_row.columns and pd.notna(player_row[date_col].iloc[0]):
                        date_str = pd.to_datetime(player_row[date_col].iloc[0]).strftime('%d/%m/%Y')
                        st.markdown(f"<p style='text-align: center; color: gray; font-style: italic;'>Test réalisé le : {date_str}</p>", unsafe_allow_html=True)
                    elif 'Date' in player_row.columns and pd.notna(player_row['Date'].iloc[0]):
                        date_str = pd.to_datetime(player_row['Date'].iloc[0]).strftime('%d/%m/%Y')
                        st.markdown(f"<p style='text-align: center; color: gray; font-style: italic;'>Date de session : {date_str}</p>", unsafe_allow_html=True)
                    
                    col_metrics = st.columns(3)
                    col_metrics[0].metric("Valeur", f"{val_p:.2f} {unit_d}")
                    col_metrics[1].metric("Moyenne", f"{mean_val:.2f} {unit_d}")
                    
                    is_good = (diff < 0) if is_inverted_metric(dist_kpi) else (diff > 0)
                    col_metrics[2].metric("Écart", f"{diff:+.2f} {unit_d}", 
                                          delta_color="normal" if is_good else "inverse")
            else:
                st.info("Sélectionnez un joueur pour voir les détails.")
        else:
            st.warning("Aucune donnée disponible pour cet indicateur.")
    else:
        st.warning("Aucune variable numérique n'est disponible dans les données.")