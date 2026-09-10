import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os
import re

from charts import build_radar
from data_utils import last_valid_value

SDR_RED = "#D71920"
SDR_DARK = "#2B2B2B"

TESTS_INVERSES = [
    "Temps 0-5 1080", "Temps total 1080", "Tau 1080", "T90 1080", 
    "Test 1km (s)", "Temps sur 10m", "Test 1km", "Tau", "T90"
]

def is_inverse(var_name):
    return any(inv.lower() in str(var_name).lower() for inv in TESTS_INVERSES)

def get_category(col_name):
    c = str(col_name).lower()
    if "1080" in c: return "Force-Vitesse 1080"
    if any(x in c for x in ["gps", "vitesse", "accel", "decel", "distance", "m/s", "km/h", "1km", "10m"]): return "Vitesse/GPS"
    if any(x in c for x in ["souplesse", "flex"]): return "Souplesse"
    if any(x in c for x in ["poids", "masse", "isak", "skinfold", "graisse"]): return "Composition corporelle"
    return "Force bas du corps"

def show_evolution_page(df_unfiltered):
    df_unfiltered = df_unfiltered.copy()
    if 'Joueur' in df_unfiltered.columns:
        df_unfiltered['Joueur'] = df_unfiltered['Joueur'].astype(str).str.strip()
        df_unfiltered = df_unfiltered[
            (df_unfiltered['Joueur'].notna()) & 
            (df_unfiltered['Joueur'] != '') & 
            (df_unfiltered['Joueur'].str.lower() != 'nan')
        ]

    time_col = "Session exact" if "Session exact" in df_unfiltered.columns else "Session"
    if "Date" in df_unfiltered.columns and not "Session exact" in df_unfiltered.columns:
        time_col = "Date"
    
    if not time_col or time_col not in df_unfiltered.columns:
        st.error("Erreur : La colonne de date/session est introuvable dans votre fichier.")
        return
        
    df_unfiltered[time_col] = pd.to_datetime(df_unfiltered[time_col], format='%d/%m/%Y', errors='coerce').fillna(
        pd.to_datetime(df_unfiltered[time_col], errors='coerce', dayfirst=True)
    )

    st.markdown(f"""
    <style>
    .stSelectbox label, .stRadio label, .stMultiSelect label {{ font-weight: bold; color: {SDR_DARK}; }}
    div[data-testid="metric-container"] {{
        background-color: #ffffff;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
        border-left: 5px solid {SDR_RED};
    }}
    .filter-box {{
        background-color: #f8f9fa; 
        padding: 20px; 
        border-radius: 12px; 
        border: 1px solid #dee2e6; 
        margin-bottom: 25px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }}
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"<h2 style='text-align: center; color: {SDR_RED}; font-weight: 900; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 30px; text-shadow: 1px 1px 2px rgba(0,0,0,0.1);'>Suivi Longitudinal</h2>", unsafe_allow_html=True)

    # Bandeau "en développement" -- sur demande explicite du département
    # performance : cet onglet reste utilisable mais son contenu actuel
    # n'est pas jugé satisfaisant, une refonte est prévue. Le signaler
    # clairement évite qu'un lecteur (agent, direction...) le prenne pour un
    # résultat final déjà validé.
    st.warning("🚧 **Onglet en développement** — le contenu actuel de cette page n'est pas encore jugé satisfaisant par le département performance. Une refonte est prévue ; à interpréter avec prudence en attendant.")

    cols_exclues = ["Player ID", "Age", "Numero", "N° GPS", "Date de Naissance", "Taille (cm)", "Poids (kg)", "Masse grasse", time_col, "Session exact", "Date", "Session", "Equipe", "Poste", "Position", "Joueur_Code", "Pied départ 1080"]
    
    for col in df_unfiltered.columns:
        if col not in cols_exclues and col != 'Joueur':
            if df_unfiltered[col].dtype == 'object' or pd.api.types.is_string_dtype(df_unfiltered[col]):
                cleaned = df_unfiltered[col].astype(str).str.replace(r'[\s\u202F\xa0]+', '', regex=True).str.replace(',', '.', regex=False)
                df_unfiltered[col] = pd.to_numeric(cleaned, errors='coerce')

    numeric_cols = [c for c in df_unfiltered.columns if c not in cols_exclues and pd.api.types.is_numeric_dtype(df_unfiltered[c])]

    # Remplacement global de tous les 0 par NaN (aucune valeur légitime n'est à 0)
    for c in numeric_cols:
        df_unfiltered[c] = df_unfiltered[c].replace(0, np.nan)

    st.markdown("<div class='filter-box'>", unsafe_allow_html=True)
    
    player_counts = df_unfiltered['Joueur'].value_counts()
    players_with_multiple_sessions = player_counts[player_counts >= 2].index.tolist()
    
    valid_indicators_per_player = {}
    
    for p in sorted(players_with_multiple_sessions):
        df_p = df_unfiltered[df_unfiltered['Joueur'] == p]
        valid_cols = [c for c in numeric_cols if df_p[c].notna().sum() >= 2]
        if valid_cols:
            valid_indicators_per_player[p] = valid_cols
            
    available_players = sorted(list(valid_indicators_per_player.keys()))

    if not available_players:
        st.warning("Aucun joueur n'a été testé au moins 2 fois avec des données valides.")
        st.markdown("</div>", unsafe_allow_html=True)
        return
        
    selected_player = st.selectbox("Sélectionnez un joueur :", available_players, index=0)
    st.markdown("</div>", unsafe_allow_html=True)

    if not selected_player:
        return

    # Check Blessures -- historique local + nouveau doc kiné fusionnés (même
    # source que l'onglet PROFIL INDIVIDUEL, cf. profiling.load_injury_data)
    # au lieu du seul fichier local d'avant : sinon les blessures saisies
    # dans le nouveau Google Sheet n'apparaissaient jamais ici. Import
    # différé (pas en haut du fichier) car profiling.py importe déjà
    # evolution.py -- un import en tête de fichier créerait une boucle.
    df_bless_player = pd.DataFrame(columns=["Joueur", "Localisation", "Detail", "Date", "Duree"])
    try:
        from profiling import load_injury_data
        df_b = load_injury_data()
        if not df_b.empty and 'Joueur' in df_b.columns:
            # Le doc kiné (nouveau Google Sheet) stocke parfois juste le nom
            # de famille ("gadou") plutôt que "Nom Prénom" complet -- même
            # tolérance de correspondance ("le nom complet du joueur COMMENCE
            # PAR la valeur du doc kiné") que l'onglet PROFIL INDIVIDUEL
            # (cf. profiling.py, HISTORIQUE & CARTOGRAPHIE MÉDICALE) : une
            # égalité stricte manquait silencieusement ces entrées.
            p_sel_clean = selected_player.strip().lower()
            df_bless_player = df_b[df_b['Joueur'].apply(lambda x: p_sel_clean.startswith(str(x).strip().lower()))].copy()
            if not df_bless_player.empty:
                df_bless_player['Date_dt'] = pd.to_datetime(df_bless_player['Date'], errors='coerce', dayfirst=True)
                st.error(f"🏥 **Alerte Blessure** : Ce joueur a {len(df_bless_player)} entrée(s) dans le registre des blessures.")
    except Exception:
        pass

    df_player = df_unfiltered[(df_unfiltered['Joueur'] == selected_player) & (df_unfiltered[time_col].notna())].copy()
    df_player = df_player.sort_values(by=time_col)
    available_vars = sorted(valid_indicators_per_player.get(selected_player, []))
    
    groupes_dispos = ["Force bas du corps", "Vitesse/GPS", "Souplesse", "Composition corporelle", "Force-Vitesse 1080"]

    poste_col = "Poste" if "Poste" in df_unfiltered.columns else ("Position" if "Position" in df_unfiltered.columns else None)
    # Dernière valeur RENSEIGNÉE (pas `.iloc[-1]`, qui peut tomber sur une
    # ligne "virtuelle" du fichier 1080 séparé, vide sur cette colonne).
    player_poste = last_valid_value(df_player, poste_col) if poste_col else None

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Evolution", 
        "Multi-Tests", 
        "Comparaison", 
        "Radar", 
        "Benchmarking",
        "1080 Sprint"
    ])

    with tab1:
        st.markdown(f"<h4 style='color:{SDR_DARK}; margin-bottom: 15px;'>Evolution detaillée d'un indicateur</h4>", unsafe_allow_html=True)
        
        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            cat_tab1 = st.radio("Famille de tests :", ["Toutes"] + groupes_dispos, horizontal=True, key="cat_tab1")
        with col_f2:
            vars_tab1 = available_vars if cat_tab1 == "Toutes" else [v for v in available_vars if get_category(v) == cat_tab1]
            selected_var = st.selectbox("Indicateur :", vars_tab1, key="var_tab1") if vars_tab1 else None
            
        if selected_var:
            df_p_var = df_player.dropna(subset=[selected_var])
            if len(df_p_var) >= 2:
                # Détection d'outliers intra-joueur
                mean_p = df_p_var[selected_var].mean()
                std_p = df_p_var[selected_var].std()
                if pd.notna(std_p) and std_p > 0:
                    outliers = df_p_var[abs(df_p_var[selected_var] - mean_p) > 3 * std_p]
                    if not outliers.empty:
                        st.warning(f"⚠️ {len(outliers)} valeur(s) potentiellement aberrante(s) (hors ±3 écarts-types de son historique) détectée(s) pour ce test.")

                overall_mean = df_unfiltered[selected_var].mean()
                n_count = df_unfiltered[selected_var].count()
                
                val_debut = df_p_var.iloc[0][selected_var]
                val_fin = df_p_var.iloc[-1][selected_var]
                pct_change = ((val_fin - val_debut) / val_debut) * 100 if val_debut != 0 else 0
                
                if is_inverse(selected_var):
                    max_idx = df_p_var[selected_var].idxmin()
                    val_max = df_p_var.loc[max_idx, selected_var]
                    pct_change = -pct_change
                else:
                    max_idx = df_p_var[selected_var].idxmax()
                    val_max = df_p_var.loc[max_idx, selected_var]
                    
                date_max = df_p_var.loc[max_idx, time_col].strftime('%d/%m/%Y')
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(f"Initiale ({df_p_var.iloc[0][time_col].strftime('%d/%m/%Y')})", f"{val_debut:.2f}")
                c2.metric(f"Finale ({df_p_var.iloc[-1][time_col].strftime('%d/%m/%Y')})", f"{val_fin:.2f}", f"{pct_change:+.1f}% (Evolution)")
                c3.metric(f"Ecart / Moyenne (n={n_count})", f"{(val_fin - overall_mean):.2f}" if pd.notna(overall_mean) else "-")
                c4.metric("Record Personnel", f"{val_max:.2f}")
                c4.caption(f"Date : {date_max}")

                fig = go.Figure()
                min_v = df_p_var[selected_var].min()
                max_v = df_p_var[selected_var].max()
                
                if pd.notna(overall_mean):
                    min_v, max_v = min(min_v, overall_mean), max(max_v, overall_mean)
                    fig.add_trace(go.Scatter(
                        x=df_p_var[time_col], y=[overall_mean]*len(df_p_var), mode='lines', 
                        name='Moyenne Equipe', line=dict(color='#adb5bd', width=3, dash='dash')
                    ))
                
                fig.add_trace(go.Scatter(
                    x=df_p_var[time_col], y=df_p_var[selected_var], mode='lines+markers+text', 
                    name=selected_player, line=dict(color=SDR_DARK, width=4), 
                    marker=dict(size=12, color=SDR_RED, line=dict(color='white', width=2)), 
                    text=df_p_var[selected_var].round(2), textposition='top center', textfont=dict(weight='bold')
                ))
                
                delta = max_v - min_v
                padding = delta * 0.15 if delta > 0 else (max_v * 0.1 if max_v != 0 else 1)

                fig.update_layout(
                    height=400, yaxis_title=selected_var, xaxis=dict(tickformat="%d/%m/%Y"),
                    hovermode="x unified", margin=dict(t=20, b=20, l=10, r=10),
                    yaxis=dict(range=[min_v - padding, max_v + padding] if not is_inverse(selected_var) else [max_v + padding, min_v - padding]),
                    legend=dict(orientation="h", y=1.1)
                )

                # Repères blessures (demande 09/2026) : une ligne verticale
                # pointillée par blessure connue de ce joueur, pour croiser
                # visuellement une baisse/plateau de performance avec un
                # épisode de blessure -- sans changer l'échelle Y du graphique
                # (add_vline ne touche que l'axe X).
                if not df_bless_player.empty and 'Date_dt' in df_bless_player.columns:
                    x_min, x_max = df_p_var[time_col].min(), df_p_var[time_col].max()
                    for _, b in df_bless_player.dropna(subset=['Date_dt']).iterrows():
                        if x_min <= b['Date_dt'] <= x_max:
                            loc_txt = str(b.get('Localisation', '')).strip() or "Blessure"
                            fig.add_vline(
                                x=b['Date_dt'], line_width=1.5, line_dash="dot", line_color="#D71920",
                                annotation_text=f"🏥 {loc_txt}", annotation_position="top",
                                annotation=dict(font_size=10, font_color="#D71920"),
                            )

                st.plotly_chart(fig, width='stretch')

    with tab2:
        st.markdown(f"<h4 style='color:{SDR_DARK}; margin-bottom: 15px;'>Evolution sur plusieurs tests simultanement (Normalises en %)</h4>", unsafe_allow_html=True)
        
        cat_tab2 = st.radio("Famille de tests :", groupes_dispos, horizontal=True, key="cat_tab2")
        vars_tab2 = [v for v in available_vars if get_category(v) == cat_tab2]
        
        if vars_tab2:
            multi_vars = st.multiselect("Sélectionnez les tests à comparer (4 max) :", vars_tab2, default=vars_tab2[:min(4, len(vars_tab2))], max_selections=4, key="multi_vars")
            
            if multi_vars:
                col_g, col_t = st.columns([2.5, 1.5])
                with col_g:
                    fig_multi = go.Figure()
                    for var in multi_vars:
                        df_temp = df_player.dropna(subset=[var]).copy()
                        if not df_temp.empty:
                            global_max = df_unfiltered[var].max()
                            if global_max > 0:
                                if is_inverse(var):
                                    df_temp['Norm_Value'] = 100 - ((df_temp[var] / global_max) * 100)
                                else:
                                    df_temp['Norm_Value'] = (df_temp[var] / global_max) * 100
                                    
                                fig_multi.add_trace(go.Scatter(
                                    x=df_temp[time_col], y=df_temp['Norm_Value'], mode='lines+markers', name=var,
                                    hovertemplate=f"<b>{var}</b><br>Valeur réelle: %{{customdata:.2f}}<extra></extra>",
                                    customdata=df_temp[var],
                                    marker=dict(size=8), line=dict(width=3)
                                ))
                    fig_multi.update_layout(
                        height=400, yaxis_title="Score Normalisé (Plus haut = Meilleur)", xaxis=dict(tickformat="%d/%m/%Y"), 
                        hovermode="x unified", legend=dict(orientation="h", y=1.1),
                        yaxis=dict(range=[0, 110]), margin=dict(l=10, r=10, t=10, b=10)
                    )
                    st.plotly_chart(fig_multi, width='stretch')
                
                with col_t:
                    st.markdown("<h6 style='margin-top: 15px; text-align:center;'>Récapitulatif (Dernière vs Initiale)</h6>", unsafe_allow_html=True)
                    recap_data = []
                    for var in multi_vars:
                        df_temp = df_player.dropna(subset=[var])
                        if len(df_temp) >= 2:
                            v_init = df_temp.iloc[0][var]
                            v_act = df_temp.iloc[-1][var]
                            delta = v_act - v_init
                            recap_data.append({"Test": var, "Init.": v_init, "Actuel": v_act, "Delta": delta})
                    
                    if recap_data:
                        df_recap = pd.DataFrame(recap_data)
                        st.dataframe(df_recap.style.format({"Init.": "{:.2f}", "Actuel": "{:.2f}", "Delta": "{:+.2f}"}), hide_index=True, width='stretch')
                    else:
                        st.info("Données insuffisantes pour le tableau.")
        else:
            st.info("Aucun test disponible dans cette catégorie pour ce joueur.")

    with tab3:
        st.markdown(f"<h4 style='color:{SDR_DARK}; margin-bottom: 15px;'>Comparaison Sessions (Evolutions Significatives)</h4>", unsafe_allow_html=True)
        dates_dispos = df_player[time_col].dt.strftime('%d/%m/%Y').unique().tolist()
        
        if len(dates_dispos) >= 2:
            col_d, col_g = st.columns([1, 2])
            with col_d:
                selected_dates_str = st.multiselect("Sessions à comparer (2 dates max) :", dates_dispos, default=[dates_dispos[0], dates_dispos[-1]], max_selections=2, key="dates_tab3")
            with col_g:
                cat_tab3 = st.radio("Famille de tests :", groupes_dispos, horizontal=True, key="cat_tab3")
                
            vars_tab3 = [v for v in available_vars if get_category(v) == cat_tab3]
            selected_vars_tab3 = st.multiselect("Quels tests comparer (8 max) :", vars_tab3, default=vars_tab3[:min(8, len(vars_tab3))], max_selections=8, key="vars_tab3")
            
            if len(selected_dates_str) == 2 and selected_vars_tab3:
                selected_dates = pd.to_datetime(selected_dates_str, format='%d/%m/%Y').sort_values()
                selected_dates_str_sorted = selected_dates.strftime('%d/%m/%Y').tolist()
                
                comp_data = []
                for var in selected_vars_tab3:
                    df_d1 = df_player[df_player[time_col] == selected_dates[0]]
                    df_d2 = df_player[df_player[time_col] == selected_dates[1]]
                    
                    v1 = df_d1.iloc[-1].get(var, np.nan) if not df_d1.empty else np.nan
                    v2 = df_d2.iloc[-1].get(var, np.nan) if not df_d2.empty else np.nan
                    
                    if pd.notna(v1) and pd.notna(v2):
                        diff = v2 - v1
                        pct = (diff / v1 * 100) if v1 != 0 else 0
                        
                        if is_inverse(var):
                            pct = -pct
                            
                        comp_data.append({"Test": var, "V1": v1, "V2": v2, "Evolution": diff, "Progression (%)": pct, "Abs_Prog": abs(pct)})
                
                if comp_data:
                    df_comp = pd.DataFrame(comp_data)
                    df_comp = df_comp.sort_values(by="Abs_Prog", ascending=True)
                    
                    colors = []
                    for pct in df_comp['Progression (%)']:
                        if pct >= 3: colors.append('#27AE60')
                        elif pct <= -3: colors.append('#D71920')
                        else: colors.append('#adb5bd')
                    
                    fig_bar = go.Figure()
                    fig_bar.add_trace(go.Bar(
                        x=df_comp['Progression (%)'], y=df_comp['Test'], orientation='h',
                        marker_color=colors, text=df_comp['Progression (%)'].apply(lambda x: f"{x:+.1f}%"),
                        textposition='auto'
                    ))
                    
                    fig_bar.update_layout(
                        height=max(350, len(comp_data) * 45), xaxis_title="Progression (%) — (Seuil de signification : ±3%)",
                        yaxis_title="", margin=dict(l=10, r=10, t=30, b=20),
                        title=f"Evolution ({selected_dates_str_sorted[0]} ➔ {selected_dates_str_sorted[1]})"
                    )
                    st.plotly_chart(fig_bar, width='stretch')
                else:
                    st.info("Aucun test commun valide entre ces deux dates pour cette sélection.")
            else:
                st.warning("Veuillez sélectionner exactement 2 dates et au moins 1 test.")

    with tab4:
        st.markdown(f"<h4 style='color:{SDR_DARK}; margin-bottom: 15px;'>Profil Radar</h4>", unsafe_allow_html=True)
        
        col_f1, col_f2 = st.columns([1.5, 1])
        with col_f1:
            cat_tab4 = st.radio("Famille de tests :", groupes_dispos, horizontal=True, key="cat_tab4")
        with col_f2:
            ref_choice = st.radio("Référence :", ["Record personnel", "Séance précédente", "Moyenne du poste"], horizontal=True, key="ref_rad")
            
        vars_tab4 = [v for v in available_vars if get_category(v) == cat_tab4]
        radar_vars = st.multiselect("Sélectionnez les tests pour le radar (6 max) :", vars_tab4, default=vars_tab4[:min(6, len(vars_tab4))], max_selections=6, key="radar_vars")
        
        dates_radar = df_player[time_col].dt.strftime('%d/%m/%Y').unique().tolist()
        if radar_vars and dates_radar:
            sel_date_radar = st.selectbox("Session à analyser :", dates_radar)
            d_rad = pd.to_datetime(sel_date_radar, format='%d/%m/%Y')
            
            prev_dates = [d for d in pd.to_datetime(dates_radar, format='%d/%m/%Y') if d < d_rad]
            d_prev = prev_dates[-1] if prev_dates else None
            
            row_rad = df_player[df_player[time_col] == d_rad].iloc[-1]
            row_prev = df_player[df_player[time_col] == d_prev].iloc[-1] if d_prev else None
            
            session_vals, ref_vals, cats = [], [], []
            for var in radar_vars:
                v_ses = row_rad.get(var, np.nan)
                v_max_global = df_unfiltered[var].max()
                
                v_ref = np.nan
                if ref_choice == "Record personnel":
                    v_ref = df_player[var].min() if is_inverse(var) else df_player[var].max()
                elif ref_choice == "Séance précédente" and row_prev is not None:
                    v_ref = row_prev.get(var, np.nan)
                elif ref_choice == "Moyenne du poste" and poste_col and player_poste:
                    v_ref = df_unfiltered[df_unfiltered[poste_col] == player_poste][var].mean()
                
                if pd.notna(v_ses) and pd.notna(v_ref) and pd.notna(v_max_global) and v_max_global > 0:
                    cats.append(var)
                    if is_inverse(var):
                        session_vals.append(100 - ((v_ses / v_max_global) * 100))
                        ref_vals.append(100 - ((v_ref / v_max_global) * 100))
                    else:
                        session_vals.append((v_ses / v_max_global) * 100)
                        ref_vals.append((v_ref / v_max_global) * 100)
            
            if cats:
                # Radar unifié (style SDR partagé avec les autres pages -- voir charts.build_radar) ;
                # ce radar utilisait encore son propre go.Scatterpolar brut, oublié lors de
                # l'unification des radars de l'app.
                fig_rad = build_radar(
                    cats,
                    [
                        {"name": ref_choice, "values": ref_vals, "color": "#adb5bd", "dash": True, "fill": False, "width": 2},
                        {"name": f"Session {sel_date_radar}", "values": session_vals, "color": SDR_RED, "fill": False, "width": 3},
                    ],
                    value_range=(0, 110),
                )
                st.plotly_chart(fig_rad, width='stretch', config={'displayModeBar': False})
            else:
                st.info("Données insuffisantes pour comparer la session avec cette référence.")

    with tab5:
        st.markdown(f"<h4 style='color:{SDR_DARK}; margin-bottom: 15px;'>Benchmarking Contextuel (Z-Scores)</h4>", unsafe_allow_html=True)
        
        df_bench = df_unfiltered.copy()
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            if "Equipe" in df_unfiltered.columns:
                equipes_dispos = df_unfiltered["Equipe"].dropna().unique().tolist()
                sel_equipe = st.selectbox("Filtrer par Equipe :", ["Toutes"] + equipes_dispos)
                if sel_equipe != "Toutes":
                    df_bench = df_unfiltered[df_unfiltered["Equipe"] == sel_equipe]
            else:
                st.write("")
                
        with col_f2:
            cat_tab5 = st.radio("Famille de tests :", ["Toutes"] + groupes_dispos, horizontal=True, key="cat_tab5")
            
        with col_f3:
            vars_tab5 = available_vars if cat_tab5 == "Toutes" else [v for v in available_vars if get_category(v) == cat_tab5]
            bench_var = st.selectbox("Indicateur a comparer :", vars_tab5, key="bench_var") if vars_tab5 else None
            
        if bench_var:
            player_record = df_player[bench_var].min() if is_inverse(bench_var) else df_player[bench_var].max()
            team_mean = df_bench[bench_var].mean()
            team_std = df_bench[bench_var].std()
            team_count = df_bench['Joueur'].nunique()
            
            best_per_player = df_bench.groupby('Joueur')[bench_var].agg('min' if is_inverse(bench_var) else 'max').dropna()
            if not best_per_player.empty:
                ranks = best_per_player.rank(method='min', ascending=is_inverse(bench_var))
                total_ranked = len(ranks)
                player_rank = ranks.get(selected_player, np.nan)
                rank_str = f"{int(player_rank)}e / {total_ranked}" if pd.notna(player_rank) else "N/A"
            else:
                rank_str = "N/A"
            
            st.markdown("<div style='background-color:#ffffff; padding:15px; border-radius:10px; border:1px solid #e9ecef; margin-bottom: 20px;'>", unsafe_allow_html=True)
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric(f"Record Personnel ({selected_player})", f"{player_record:.2f}" if pd.notna(player_record) else "-", f"Rang : {rank_str}")
            
            if poste_col and player_poste and pd.notna(player_poste):
                df_poste = df_bench[df_bench[poste_col] == player_poste]
                poste_mean = df_poste[bench_var].mean()
                poste_std = df_poste[bench_var].std()
                poste_count = df_poste['Joueur'].nunique()
                
                z_poste = (player_record - poste_mean) / poste_std if pd.notna(poste_std) and poste_std != 0 else np.nan
                if is_inverse(bench_var) and pd.notna(z_poste): z_poste = -z_poste
                
                col_m2.metric(f"Moyenne Poste ({player_poste})", f"{poste_mean:.2f} (n={poste_count})" if pd.notna(poste_mean) else "-", f"Z-Score : {z_poste:+.2f}" if pd.notna(z_poste) else None, delta_color="normal")
            else:
                col_m2.metric("Moyenne Poste", "N/A")
                
            z_team = (player_record - team_mean) / team_std if pd.notna(team_std) and team_std != 0 else np.nan
            if is_inverse(bench_var) and pd.notna(z_team): z_team = -z_team
                
            col_m3.metric(f"Moyenne Globale Filtre", f"{team_mean:.2f} (n={team_count})" if pd.notna(team_mean) else "-", f"Z-Score : {z_team:+.2f}" if pd.notna(z_team) else None, delta_color="normal")
            st.markdown("</div>", unsafe_allow_html=True)

    with tab6:
        st.markdown(f"<h4 style='color:{SDR_DARK}; margin-bottom: 15px;'>Suivi 1080 Sprint</h4>", unsafe_allow_html=True)
        
        type_test_1080 = st.radio(
            "Type de protocole :",
            ["Acceleration", "Force-Vitesse"],
            horizontal=True
        )
        
        metrics_map = {
            "Acceleration": [
                "Amax 1080 (m/s²)", "Vmax 15m 1080 (m/s)", "Vmax 15m 1080 (Km/h)", "Temps total 1080 (s)", "Temps 0-5 1080 (s)"
            ],
            "Force-Vitesse": [
                "Amax", "Pmax", "F0", "V0", "Tau", "T90", "D90", "Momentum", "Unloaded Speed"
            ]
        }
        
        all_cols = df_unfiltered.columns.tolist()
        current_metrics = []
        for expected in metrics_map[type_test_1080]:
            match = next((col for col in all_cols if str(col).strip().lower() == str(expected).strip().lower() or str(col).strip().lower() == f"{str(expected).strip().lower()} 1080"), None)
            if match:
                current_metrics.append(match)
        
        df_1080 = df_player.copy()
        if "Distance 1080 (m)" in df_1080.columns and current_metrics:
            distances_dispo = df_1080.dropna(subset=current_metrics, how='all')["Distance 1080 (m)"].dropna().unique().tolist()
            if distances_dispo:
                sel_dist = st.selectbox("Distance associee au test (m) :", sorted(distances_dispo))
                df_1080 = df_1080[df_1080["Distance 1080 (m)"] == sel_dist]

        if not current_metrics:
            st.info(f"Les colonnes requises pour le test '{type_test_1080}' sont introuvables dans votre fichier de donnees.")
        elif df_1080.empty or df_1080[current_metrics].dropna(how='all').empty:
            st.info(f"Aucune donnee trouvee pour le test '{type_test_1080}' a cette distance.")
        elif len(df_1080.dropna(how='all', subset=current_metrics)) < 2:
            st.warning("1080 : pas encore assez de séances pour ce joueur pour afficher une courbe d'évolution.")
        else:
            if "Pied départ 1080" in df_1080.columns:
                pieds_val = df_1080["Pied départ 1080"].dropna().unique()
                if len(pieds_val) > 0:
                    st.caption(f"**Information** - Pied(s) de départ enregistré(s) : {', '.join(map(str, pieds_val))}")

            fig_1080 = go.Figure()
            for metric in current_metrics:
                if "Charge " not in metric: 
                    df_temp = df_1080.dropna(subset=[metric])
                    if not df_temp.empty:
                        max_m = df_unfiltered[metric].max()
                        if max_m > 0:
                            if is_inverse(metric):
                                norm_vals = 100 - ((df_temp[metric] / max_m) * 100)
                            else:
                                norm_vals = (df_temp[metric] / max_m) * 100
                                
                            fig_1080.add_trace(go.Scatter(
                                x=df_temp[time_col], y=norm_vals, mode='lines+markers', name=metric,
                                hovertemplate=f"<b>{metric}</b><br>Valeur brute: %{{customdata:.2f}}<extra></extra>",
                                customdata=df_temp[metric], marker=dict(size=8), line=dict(width=3)
                            ))
                            
            if len(fig_1080.data) > 0:
                fig_1080.update_layout(
                    height=350, yaxis_title="Score Normalisé", xaxis=dict(tickformat="%d/%m/%Y"), 
                    hovermode="x unified", legend=dict(orientation="h", y=1.1), margin=dict(t=10, b=10)
                )
                st.plotly_chart(fig_1080, width='stretch')
            
            st.markdown("<h5 style='color:#2B2B2B; margin-top:20px;'>Valeurs Brutes :</h5>", unsafe_allow_html=True)
            cols_to_show = [time_col] + current_metrics
            if "Distance 1080 (m)" in df_1080.columns and "Distance 1080 (m)" not in cols_to_show:
                cols_to_show.insert(1, "Distance 1080 (m)")
                
            df_brut_1080 = df_1080[cols_to_show].dropna(how='all', subset=current_metrics).copy()
            if pd.api.types.is_datetime64_any_dtype(df_brut_1080[time_col]):
                df_brut_1080[time_col] = df_brut_1080[time_col].dt.strftime('%d/%m/%Y')
            st.dataframe(df_brut_1080, width='stretch', hide_index=True)

        st.markdown("<hr style='border: 1px dashed #e9ecef;'>", unsafe_allow_html=True)
        st.markdown(f"<h5 style='color:{SDR_DARK};'>Rapports PDF 1080</h5>", unsafe_allow_html=True)

        dossier_1080 = os.path.join(os.getcwd(), "1080")
        player_nom_clean = selected_player.replace(" ", "").lower()
        pdf_files = []

        if os.path.exists(dossier_1080):
            for fichier in os.listdir(dossier_1080):
                if fichier.replace("_", "").replace(" ", "").lower().startswith(player_nom_clean) and fichier.lower().endswith(".pdf"):
                    pdf_files.append(fichier)

        if pdf_files:
            pdf_files.sort(reverse=True)
            
            pdf_options = {}
            for pdf in pdf_files:
                match_date = re.search(r'\d{4}-\d{2}-\d{2}', pdf)
                if match_date:
                    date_str = match_date.group(0)
                    date_fr = pd.to_datetime(date_str).strftime('%d/%m/%Y')
                    pdf_options[f"Session du {date_fr}"] = pdf
                else:
                    pdf_options[pdf] = pdf

            sel_label = st.selectbox("Selectionnez le rapport a consulter :", list(pdf_options.keys()))
            sel_pdf = pdf_options[sel_label]

            pdf_path = os.path.join(dossier_1080, sel_pdf)
            try:
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()

                st.download_button(
                    label=f"Telecharger : {sel_pdf}",
                    data=pdf_bytes,
                    file_name=sel_pdf,
                    mime="application/pdf",
                    width='stretch'
                )

                if st.button("AFFICHER CE RAPPORT PDF", key=f"show_pdf_{sel_pdf}", width='stretch'):
                    st.pdf(pdf_bytes, height=700)
            except Exception as e:
                st.error("Erreur lors de la lecture du fichier PDF.")
        else:
            st.info(f"Aucun rapport PDF trouve pour {selected_player} dans le dossier '1080'.")