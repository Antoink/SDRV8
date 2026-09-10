import streamlit as st
import pandas as pd
import base64
import os
import re
import unicodedata
import numpy as np
# scipy.stats N'EST PAS importé ici au niveau module, volontairement : il ne
# sert qu'à UN seul appel (stats.percentileofscore, tout en bas de
# _render_tab_indiv) mais coûte à lui seul ~0.5s à l'import -- payés à
# CHAQUE lancement de l'appli puisque profiling.py est chargé sans
# condition par main.py. Importé localement dans _render_tab_indiv() à la
# place (voir plus bas), où le coût ne survient qu'à l'usage réel.
from PIL import Image, ImageDraw
from pitch_profiling import render_position_pitch
import io
import plotly.graph_objects as go

from utils import SDR_RED, load_data, get_kpi_card_html

from team_profiling import show_team_page, get_poste_large
from clustering import show_clustering_page

from config_rapport import OFFICIAL_STRUCTURE, TEAM_STRUCTURE, REPORT_NORMES, REPORT_NORMES_PAR_POSTE, UNITS, RELATIVE_NORM_KEYS
from data_utils import (
    remove_accents, is_inverted, clean_numeric_value,
    get_column_stats, calculate_percentile, format_pct_display, find_column_in_df,
    last_valid_value,
)

# ajouts en cours 
from evolution import show_evolution_page
from comparateur import show_comparateur_page, get_best_season_record_paired
from charts import build_radar
from rapport_page import show_rapport_page
# Trouve la zone des imports en haut de profiling.py et ajoute :
from classement import show_classement_page
from glossary import annotate_glossary_terms
import glob



# Mapping pour faire correspondre les Libellés UI -> Colonnes Excel
# Mapping pour faire correspondre les Libellés UI -> Colonnes Excel
COL_MAPPING = {
    "Knee To Wall (D)": "Knee to wall D", "Knee To Wall (G)": "Knee to wall G",
    "Sit And Reach": "Sit and reach",
    "Somme ADD": "Somme ADD", "Adducteurs (G)": "Adducteur G", "Adducteurs (D)": "Adducteur D",
    "Ratio Squeeze": "Ratio Squeeze (ADD/ABD)", "Somme ABD": "Somme ABD",
    "Abducteurs (G)": "Abducteur G", "Abducteurs (D)": "Abducteur D",
    "Nordic Ischio (G)": "Nordic G", "Nordic Ischio (D)": "Nordic D",
    "Inverseur (G)": "Inverseur G", "Inverseur (D)": "Inverseur D",
    "Everseur (G)": "Everseur G", "Everseur (D)": "Everseur D",
    "Endurance Heel Raise (G)": "Endurance Heel Raise G", "Endurance Heel Raise (D)": "Endurance Heel Raise D",
    
    
    # ---- SAUTS (Mise à jour) ----
    "CMJ 2JB": "CMJ 2JB", 
    "Drop jump": "Drop jump",
    "Peak Force CMJ": "Peak Force CMJ", 
    "RFD CMJ": "RFD CMJ", 
    "RSI CMJ": "RSI",
    # -----------------------------
    
    "Wattbike (6s)": "Wattbike 6s (W)", "Squat belt (N)": "Squat belt (N)",
    "SV1": "SV1", "SV2": "SV2", "FC": "FC", "VMA": "VMA",
    "Distance Totale": "Distance totale", "Distance HSR": "Distance HSR", "Distance Sprint (92% Vimax)": "Distance Sprint (92% Vimax)",
    "Nb Accélérations": "Nb Acc", "Nb Décélérations": "Nb Dec",
    "Vmax": "Vmax", "Amax": "Amax", "Dmax": "Dmax", "Temps sur 10m": "Temps sur 10m", "Test 1km (s)": "Test 1km (s)",
    "Q Conc 60° (G)": "Q G conc 60°/s", "Q Conc 60° (D)": "Q Dt conc 60°/s",
    "Q Conc 240° (G)": "Q G conc 240°/s", "Q Conc 240° (D)": "Q Dt conc 240°/s",
    "IJ Conc 60° (G)": "IJ G conc 60°/s", "IJ Conc 60° (D)": "IJ Dt conc 60°/s",
    "IJ Conc 240° (G)": "IJ G conc 240°/s", "IJ Conc 240° (D)": "IJ Dt conc 240°/s",
    "IJ Exc 30° (G)": "IJ G Exc 30°/s", "IJ Exc 30° (D)": "IJ Dt exc 30°/s",
    # ---- ISAK NUTRITION ----
    # ---- ISAK NUTRITION ----
    "Triceps": "Isak_triceps", "Subscapulaire": "Isak_sousscapulaire", "Biceps": "Isak_biceps",
    "Crête iliaque": "Isak_crete", "Supraspinale": "Isak_supraspinale", "Abdominal": "Isak_abdominal", 
    "Cuisse ISAK": "Isak_cuisse", "Jambe ISAK": "Isak_jambe",
    "Endomorphie": "Endomorphie", "Mésomorphie": "Mésomorphie", "Éctomorphie": "Éctomorphie",
    "Tissu Adipeux": "Tissu Adipeux", "Tissu Musculaire": "Tissu Musculaire",
    "Tissu Osseux": "Tissu Osseux", "Tissu Résiduel": "Tissu Résiduel",

    # ---- 1080 SPRINT ----
    "Temps total 1080": "Temps total 1080 (s)",
    "Amax 1080": "Amax 1080 (m/s²)",
    "Pmax 1080": "Pmax 1080 (W)",
    "Vmax 15m 1080": "Vmax 15m 1080 (m/s)",
    "Tau 1080": "Tau 1080 (s)",
    "T90 1080": "T90 1080 (s)",
    "D90 1080": "D90 1080 (m)",
    "Momentum 1080": "Momentum 1080 (Kg*m/s)",
    "F0 1080": "F0 1080 (N)",
    "V0 1080": "V0 1080 (m/s)"
}

KEYWORD_MAPPING = {
    "Taille": ["taille", "height"], "Poids": ["poids", "weight"],
    "Masse Grasse Plis (mm)": ["masse grasse", "fat", "img"], "Age":["age", "âge"],
    "Numéro": ["numero", "numéro", "number", "maillot"],
    "Poste": ["poste", "position"], "Latéralité": ["latéralité", "laterality", "pied"],
    "Knee To Wall (D)": ["knee to wall d", "ktw d"], "Knee To Wall (G)": ["knee to wall g", "ktw g"],
    "Sit And Reach": ["sit and reach", "souplesse"],
    "Adducteurs (G)": ["adducteur g", "add g"], "Adducteurs (D)": ["adducteur d", "add d"],
    "Abducteurs (G)": ["abducteur g", "abd g"], "Abducteurs (D)": ["abducteur d", "abd d"],
    "Nordic Ischio (G)": ["nordic g"], "Nordic Ischio (D)": ["nordic d"],
    "Inverseur (G)": ["inverseur g"], "Inverseur (D)": ["inverseur d"],
    "Everseur (G)": ["everseur g"], "Everseur (D)": ["everseur d"],
    "Endurance Heel Raise (G)": ["endurance heel raise g"], "Endurance Heel Raise (D)": ["endurance heel raise d"],
    
    "Q Conc 60° (G)": ["q g conc 60"], "Q Conc 60° (D)": ["q dt conc 60"],
    "Q Conc 240° (G)": ["q g conc 240"], "Q Conc 240° (D)": ["q dt conc 240"],
    "IJ Conc 60° (G)": ["ij g conc 60"], "IJ Conc 60° (D)": ["ij dt conc 60"],
    "IJ Conc 240° (G)": ["ij g conc 240"], "IJ Conc 240° (D)": ["ij dt conc 240"],
    "IJ Exc 30° (G)": ["ij g exc 30"], "IJ Exc 30° (D)": ["ij dt exc 30"],
    "Ratio Mixte (G)": ["ratio mixte g", "mixte g"],
    "Ratio Mixte (D)": ["ratio mixte dt", "mixte d", "mixte dt", "ratio mixte d"],
    
    # ---- SAUTS (Mise à jour) ----
    "CMJ 2JB": ["cmj 2jb", "cmj"], 
    "Drop jump": ["drop jump"],
    "Peak Force CMJ": ["peak force cmj", "force max cmj", "pic de force max (n)"],
    "RFD CMJ": ["rfd cmj", "pic de rfd max (n/s)"],
    "RSI CMJ": ["rsi cmj", "mrsi", "mrsi (jh/ct) (m/s)"],
    # -----------------------------
    
    "Wattbike (6s)": ["wattbike"], "Squat belt (N)": ["squat belt", "squat"],
    "VMA": ["vma"], "SV1": ["sv1"], "SV2": ["sv2"], "FC": ["fc"],
    "Temps sur 10m": ["temps sur 10m", "chrono 10m", "10m"],
    "Distance Totale": ["distance totale", "total dist"], "Distance HSR": ["distance hsr", "hsr"],
    "Distance Sprint (92% Vimax)" : ["distance sprint", "sprint"],
    "Nb Accélérations": ["nb acc"], "Nb Décélérations": ["nb dec"],
    "Vmax": ["vmax"], "Amax": ["amax"], "Dmax": ["dmax"], "Test 1km (s)": ["1km", "test 1km"],

    # ---- ISAK NUTRITION ----
    "Triceps": ["isak_triceps", "triceps"], "Subscapulaire": ["isak_sousscapulaire", "sousscapulaire"], 
    "Biceps": ["isak_biceps", "biceps"], "Crête iliaque": ["isak_crete", "crete", "crête"], 
    "Supraspinale": ["isak_supraspinale", "supraspinale"], "Abdominal": ["isak_abdominal", "abdominal"], 
    "Cuisse ISAK": ["isak_cuisse", "cuisse"], "Jambe ISAK": ["isak_jambe", "jambe"],
    "Endomorphie": ["endomorphie", "endo"], "Mésomorphie": ["mésomorphie", "meso"], "Éctomorphie": ["éctomorphie", "ecto"],
    "Somme 8 plis": ["somme 8", "somme de 8 plis"],

    # ---- 1080 SPRINT ----
    "Temps total 1080": ["temps total 1080", "temps total 1080 (s)"],
    "Amax 1080": ["amax 1080", "amax 1080 (m/s²)"],
    "Pmax 1080": ["pmax 1080", "pmax 1080 (w)"],
    "Vmax 15m 1080": ["vmax 15m 1080", "vmax 15m 1080 (m/s)"],
    "Tau 1080": ["tau 1080", "tau 1080 (s)"],
    "T90 1080": ["t90 1080", "t90 1080 (s)"],
    "D90 1080": ["d90 1080", "d90 1080 (m)"],
    "Momentum 1080": ["momentum 1080", "momentum 1080 (kg*m/s)"],
    "F0 1080": ["f0 1080", "f0 1080 (n)"],
    "V0 1080": ["v0 1080", "v0 1080 (m/s)"]
}

REL_COL_MAPPING = {
    "Somme ADD": "Somme ADD (N/kg)", "Somme ABD": "Somme ABD (N/kg)",
    "Adducteurs (G)": "Adducteur G (N/kg)", "Adducteurs (D)": "Adducteur D (N/kg)",
    "Abducteurs (G)": "Abducteur G (N/kg)", "Abducteurs (D)": "Abducteur D (N/kg)",
    "Nordic Ischio (G)": "Nordic G (Kg/kg)", "Nordic Ischio (D)": "Nordic D (Kg/kg)",
    
    "Q Conc 60° (G)": "Q G conc 60°/s (N/kg)", "Q Conc 60° (D)": "Q Dt conc 60°/s (N/kg)",
    "Q Conc 240° (G)": "Q G conc 240°/s (N/kg)", "Q Conc 240° (D)": "Q Dt conc 240°/s (N/kg)",
    "IJ Conc 60° (G)": "IJ G conc 60°/s (N/kg)", "IJ Conc 60° (D)": "IJ Dt conc 60°/s (N/kg)",
    "IJ Conc 240° (G)": "IJ G conc 240°/s (N/kg)", "IJ Conc 240° (D)": "IJ Dt conc 240°/s (N/kg)",
    "IJ Exc 30° (G)": "IJ G Exc 30°/s (N/kg)", "IJ Exc 30° (D)": "IJ Dt exc 30°/s (N/kg)",
    "Q Exc 30° (G)": "Q G exc 30°/s (N/kg)", "Q Exc 30° (D)": "Q Dt exc 30°/s (N/kg)",

    # ---- 1080 SPRINT ----
    "Pmax 1080": "Pmax 1080 (W/Kg)",
    "F0 1080": "F0 1080 (N/kg)"
}

SOURCES_CONFIG = {
    "Q Conc 60°": "Scientifique", "Q Conc 240°": "Scientifique", 
    "IJ Conc 60°": "Scientifique", "IJ Conc 240°": "Scientifique", "IJ Exc 30°": "Scientifique"
}


TARGET_MEDIAN_TESTS = {
    "Wattbike (6s)": "Wattbike 6s (W)",
    "Peak Force CMJ": "Peak Force CMJ",
    "RFD CMJ": "RFD CMJ",
    "RSI CMJ": "RSI",
    "SV1": "SV1",
    "SV2": "SV2",
}

SENS_KPI = {
    "Temps sur 10m": "min",
    "Test 1km (s)": "min",
    "Masse Grasse Plis (mm)": "min",
    "Masse grasse": "min"
}

def get_best_season_record(df_player):
    virtual_row = df_player.iloc[-1].to_dict()
    record_dict = {}
    
    date_col = "Session exact" if "Session exact" in df_player.columns else "Session"
    if date_col not in df_player.columns:
        date_col = None
        
    for col in df_player.columns:
        clean_series = df_player[col].astype(str).str.replace(r'[\s\u202F\xa0]+', '', regex=True).str.replace(',', '.', regex=False)
        series_num = pd.to_numeric(clean_series, errors='coerce')
        if not series_num.dropna().empty:
            if col in SENS_KPI and SENS_KPI[col] == "min":
                best_idx = series_num.idxmin()
            elif is_inverted(col):
                best_idx = series_num.idxmin()
            else:
                best_idx = series_num.idxmax()
                
            best_val = series_num.loc[best_idx]
            virtual_row[col] = best_val
            
            date_val = df_player.loc[best_idx, date_col] if date_col and pd.notna(df_player.loc[best_idx, date_col]) else "-"
            virtual_row[f"{col}_date"] = date_val
            
            record_dict[col] = {"valeur": best_val, "session": date_val}
            
    return virtual_row, record_dict


    
def _load_injury_data_local():
    """Fichier local historique (Blessures.xlsx/.csv) -- gardé comme base
    des saisons précédentes (voir load_injury_data)."""
    import os
    import pandas as pd
    import unicodedata
    try:
        if os.path.exists("Blessures.xlsx"):
            df = pd.read_excel("Blessures.xlsx")
        elif os.path.exists("Blessures.csv"):
            df = pd.read_csv("Blessures.csv", sep=None, engine="python")
        else:
            return pd.DataFrame(columns=["Joueur", "Localisation", "Detail", "Date", "Duree"])

        col_map = {}
        for c in df.columns:
            c_str = unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('utf-8').upper().strip()

            if c_str == '@' or c_str == 'JOUEUR': col_map[c] = 'Joueur'
            elif 'DATE' in c_str: col_map[c] = 'Date'
            elif 'DIAGNOSTIC' in c_str or 'DETAIL' in c_str: col_map[c] = 'Detail'
            elif 'DUREE' in c_str or 'ABS' in c_str or 'INDISPONIBILITE' in c_str: col_map[c] = 'Duree'
            elif 'LOCALISATION' in c_str: col_map[c] = 'Localisation'

        df = df.rename(columns=col_map)

        for req in ["Joueur", "Localisation", "Detail", "Date", "Duree"]:
            if req not in df.columns: df[req] = ""

        df["Joueur"] = df["Joueur"].astype(str).str.strip().str.lower()
        df["Localisation"] = df["Localisation"].astype(str).str.strip()
        return df
    except Exception:
        return pd.DataFrame(columns=["Joueur", "Localisation", "Detail", "Date", "Duree"])


def _load_injury_data_sheet():
    """
    Fichier "Suivi Blessures" (Google Sheet kiné, gid=649800536) -- nouvelles
    blessures saisies par le staff kiné à partir de maintenant (voir
    load_injury_data pour la fusion avec l'historique local).

    STRUCTURE DE CE GOOGLE SHEET (différente du fichier local) :
    2 lignes d'en-tête (une ligne de titres généraux + une ligne de
    sous-titres) -- pandas ne lit que la 1ère comme en-tête, donc la 2e
    ("Circonstances", "Localisation", "Tissu", "Côté"...) arrive comme une
    ligne de DONNÉES à ignorer (elle n'a pas de nom de joueur, comme
    toutes les lignes vides du bas du fichier -- un seul filtre "@" non
    vide suffit à les exclure toutes les deux).
    Colonnes utiles : "@"=Joueur, "DATE"=Date, colonne n°4 (0-indexée)
    ="Localisation" (zone du corps), colonne n°5="Tissu", colonne
    n°6="Côté", "DIAGNOSTIC"=Detail, "DURÉE ABS"=Duree (jours d'absence).
    Les positions n°4/5/6 (colonnes sans nom clair, "Unnamed: 4/5/6") sont
    lues par POSITION plutôt que par nom -- à corriger si la structure du
    Google Sheet change un jour (ex: colonne insérée/déplacée).
    """
    import pandas as pd
    try:
        url = "https://docs.google.com/spreadsheets/d/1NntrOQuV37dfBbOeREMxwUuV-d0nmSRww-UXsIzVTCA/export?format=csv&gid=649800536"
        raw = pd.read_csv(url)
    except Exception:
        return pd.DataFrame(columns=["Joueur", "Localisation", "Detail", "Date", "Duree"])

    if "@" not in raw.columns or len(raw.columns) < 9:
        return pd.DataFrame(columns=["Joueur", "Localisation", "Detail", "Date", "Duree"])

    raw = raw[raw["@"].notna()].copy()  # exclut la ligne de sous-titres + les lignes vides du bas
    cols = list(raw.columns)
    loc_brute = raw[cols[4]].astype(str).str.strip() if len(cols) > 4 else pd.Series("", index=raw.index)
    cote_brut = raw[cols[6]].astype(str).str.strip().str.upper() if len(cols) > 6 else pd.Series("", index=raw.index)

    # Ce Google Sheet donne la zone du corps et le côté dans 2 colonnes
    # séparées ("Genou" + "Droit"), alors que la cartographie corporelle
    # (generate_heatmap_body_svg) attend un libellé combiné avec le côté
    # entre parenthèses, format hérité du fichier local (ex: "Adducteurs
    # (D)") -- cette table fait la conversion. "Genou" est volontairement
    # approximatif (LCA/LCP/ménisque/rotule partagent quasi la même
    # position sur le schéma, faute de plus de détail structurel ici) ; les
    # zones sans "(G)/(D)" dans la cartographie (Tête, Rachis) restent
    # telles quelles, sans côté.
    BODY_PART_MAP = {
        "TETE": "Tête", "EPAULE": "Épaule", "MEMBRES SUPERIEURS": "Membre Supérieur",
        "RACHIS": "Lombaire / Dos", "HANCHE/BASSIN/PSOAS": "Psoas",
        "ADDUCTEURS": "Adducteurs", "QUADRICEPS": "Droit Fémoral",
        "I-J": "Ischio-jambiers", "GENOU": "LCA",
        "MOLLET (S)": "Triceps Sural / Mollet", "CHEVILLE": "LLE Cheville - Entorse",
        "PIED(S) / DOIGTS DE PIED": "Pied / Orteil",
    }
    NO_SIDE = {"Tête", "Lombaire / Dos"}  # zones sans variante (G)/(D) dans la cartographie

    def _combine(loc, cote):
        base = BODY_PART_MAP.get(loc.strip().upper(), loc.strip())
        if not base:
            return ""
        if base in NO_SIDE:
            return base
        side = "G" if cote.startswith("G") else ("D" if cote.startswith("D") else None)
        return f"{base} ({side})" if side else base

    df = pd.DataFrame({
        "Joueur": raw["@"].astype(str).str.strip().str.lower(),
        "Date": raw.get("DATE", ""),
        "Localisation": [
            _combine(loc, cote) for loc, cote in zip(loc_brute.fillna(""), cote_brut.fillna(""))
        ],
        "Detail": raw.get("DIAGNOSTIC", ""),
        "Duree": raw.get("DURÉE ABS", ""),
    })
    df["Detail"] = df["Detail"].fillna("").astype(str)
    return df


@st.cache_data
def load_injury_data():
    """
    Combine l'historique local (Blessures.xlsx, saisons précédentes) et le
    nouveau Google Sheet kiné (Suivi Blessures, nouvelles entrées) -- sur
    demande explicite : le fichier local reste la référence pour les
    saisons déjà passées, le Google Sheet reçoit les nouvelles blessures
    saisies à partir de maintenant.

    Dédoublonnage sur (Joueur, Date) : si la MÊME blessure existe dans les
    deux sources (même joueur, même date), on garde la version du Google
    Sheet (plus détaillée -- diagnostic complet) plutôt que d'additionner
    deux fois la même blessure dans l'historique du joueur.
    """
    import pandas as pd
    df_local = _load_injury_data_local()
    df_sheet = _load_injury_data_sheet()
    if df_sheet.empty:
        return df_local
    if df_local.empty:
        return df_sheet
    combined = pd.concat([df_local, df_sheet], ignore_index=True)
    # Date normalisée (jour/mois/année réels, pas la représentation texte
    # brute) pour la clé de dédoublonnage : le fichier local a des dates
    # Excel ("2025-12-16 00:00:00"), le Google Sheet des dates en texte
    # ("16/12/2025") -- une comparaison de texte brut ne matchait jamais,
    # laissant passer des doublons (même blessure, même joueur, même jour).
    date_norm = pd.to_datetime(combined["Date"], errors="coerce", dayfirst=True).dt.strftime("%Y-%m-%d")
    dedup_key = combined["Joueur"].astype(str) + "|" + date_norm.fillna(combined["Date"].astype(str))
    # keep="last" : le Google Sheet (ajouté en dernier dans le concat) gagne
    # en cas de doublon exact (Joueur, Date).
    return combined[~dedup_key.duplicated(keep="last")]

@st.cache_data
def load_data_from_source(source):
    try:
        df = pd.read_excel(source, header=0)
        cols_lower = {str(c).lower().strip(): c for c in df.columns}
        target = next((cols_lower[k] for k in ['joueur', 'nom', 'name'] if k in cols_lower), None)
        if not target: return pd.DataFrame(), "Colonne 'Joueur' introuvable dans le fichier."
        df = df.dropna(subset=[target]).rename(columns={target: 'Joueur'})
        df['Joueur'] = df['Joueur'].astype(str).str.title().str.strip()
        return df, None
    except Exception as e: return pd.DataFrame(), str(e)

import unicodedata
import os
import re

def super_clean_name(name):
    """Nettoyeur extrême pour faire correspondre le nom du profilage et du CMJ"""
    if pd.isna(name): return ""
    clean = unicodedata.normalize('NFKD', str(name)).encode('ASCII', 'ignore').decode('utf-8').lower()
    words = re.findall(r'[a-z]+', clean)
    words.sort() 
    return "".join(words)

def parse_cmj_raw_file(filepath):
    """
    Extrait les métriques clés (Force Max, Puissance Max, mRSI, RFD Poussée,
    RFD Freinage, Hauteur de saut) directement depuis un fichier CMJ brut
    exporté par Kinvent (section 'Paramètres' en tête de fichier), et convertit
    les forces de kgf en Newtons.
    Retourne un dict ou None si le fichier n'a pas pu être lu/reconnu.
    """
    G = 9.80665

    def to_float(s):
        s = str(s).strip().replace(",", ".")
        if s == "" or s.upper() == "NA":
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return None

    poids = None
    metrics = {}

    # Lignes "simples" : label en colonne 0, valeur (Total Abs / Moyenne) en colonne 1
    wanted_simple = {
        "Pic de Force Max (kg)": "force_max_kg",
        "Pic de Puissance Max (W)": "puissance_max_w",
        "mRSI (JH/CT) (m/s)": "mrsi",
        "Pic de RFD Max (kg/s)": "rfd_poussee_kgs",
        "Hauteur de saut (Vitesse) (cm)": "hauteur_cm",
    }
    # Lignes "phase" : "Nom de phase,Nom de métrique,valeur..." -> valeur en colonne 2
    wanted_phase = {
        ("Phase de Freinage", "RFD Excentrique (kg/s)"): "rfd_freinage_kgs",
    }

    for line in lines:
        line = line.rstrip("\n").rstrip("\r")
        if not line:
            continue
        parts = line.split(",")
        label0 = parts[0].strip()

        if label0.startswith("Poids de corps") and len(parts) > 1:
            poids = to_float(parts[1])
            continue

        if label0 in wanted_simple and len(parts) > 1:
            key = wanted_simple[label0]
            if key not in metrics:
                metrics[key] = to_float(parts[1])
            continue

        if len(parts) > 2:
            label1 = parts[1].strip()
            if (label0, label1) in wanted_phase:
                key = wanted_phase[(label0, label1)]
                if key not in metrics:
                    metrics[key] = to_float(parts[2])

    if not metrics and poids is None:
        return None

    def to_newton(v):
        return v * G if v is not None else None

    return {
        "Pic de Force Max (N)": to_newton(metrics.get("force_max_kg")),
        "Pic de Puissance Max (W)": metrics.get("puissance_max_w"),
        "mRSI (JH/CT) (m/s)": metrics.get("mrsi"),
        "Pic de RFD Max (N/s)": to_newton(metrics.get("rfd_poussee_kgs")),
        "Phase de Freinage - RFD Excentrique (N/s)": to_newton(metrics.get("rfd_freinage_kgs")),
        "Hauteur de saut (Vitesse) (cm)": metrics.get("hauteur_cm"),
        "Poids de corps (kg)": poids,
    }

def format_date_str(d):
            if not d or pd.isna(d) or str(d).strip() == "-":
                return ""
            try:
                # On tente de forcer une vraie lecture de date pour l'afficher en JJ/MM/AAAA
                dt = pd.to_datetime(str(d), errors='raise', dayfirst=True)
                return dt.strftime('%d/%m/%Y')
            except:
                # Si c'est du texte pur ou une erreur, on renvoie le premier mot (ex: 06/07/2026)
                return str(d).split()[0]

@st.cache_data(ttl=600)
def load_cmj_master(dossier_brut="CMJ_Brut"):
    """
    Construit le tableau de comparaison CMJ de toute l'équipe.
    Source principale : tous les fichiers bruts trouvés dans CMJ_Brut (auto-extraits).
    Complément : CMJ20262027.csv (fichier consolidé manuel), utilisé uniquement
    pour les joueurs qui n'auraient pas encore de fichier brut correspondant.
    """
    # 1. Extraction automatique depuis CMJ_Brut
    rows = []
    if os.path.exists(dossier_brut):
        for f in os.listdir(dossier_brut):
            if not f.lower().endswith(".csv"):
                continue
            data = parse_cmj_raw_file(os.path.join(dossier_brut, f))
            if not data:
                continue
            nom_joueur = f[:-4].replace("_", " ").strip()
            row = {"Joueur": nom_joueur}
            row.update(data)
            rows.append(row)
    df_auto = pd.DataFrame(rows)
    if not df_auto.empty:
        df_auto['Joueur_Code'] = df_auto['Joueur'].apply(super_clean_name)

    # 2. Fichier consolidé manuel (ancien système), en complément uniquement
    df_manual = pd.DataFrame()
    if os.path.exists("CMJ20262027.csv"):
        try:
            df_manual = pd.read_csv("CMJ20262027.csv", sep=";", encoding="utf-8-sig")
        except Exception:
            try:
                df_manual = pd.read_csv("CMJ20262027.csv", sep=";", encoding="latin1")
            except Exception:
                df_manual = pd.DataFrame()
        if not df_manual.empty:
            df_manual.columns = [str(c).strip() for c in df_manual.columns]
            if 'Joueur' in df_manual.columns:
                df_manual['Joueur_Code'] = df_manual['Joueur'].apply(super_clean_name)

    # 3. Fusion : priorité aux données brutes auto-extraites (les plus à jour),
    #    complétées par le fichier manuel pour les joueurs qui n'ont pas (encore)
    #    de fichier brut dans CMJ_Brut.
    if df_auto.empty and df_manual.empty:
        return pd.DataFrame()
    if df_auto.empty:
        return df_manual
    if df_manual.empty:
        return df_auto

    codes_auto = set(df_auto['Joueur_Code'])
    df_manual_complement = df_manual[~df_manual['Joueur_Code'].isin(codes_auto)]
    df_final = pd.concat([df_auto, df_manual_complement], ignore_index=True, sort=False)
    return df_final

def find_raw_cmj_file(player_name, dossier_brut="CMJ_Brut"):
    """
    Cherche le fichier CMJ brut d'un joueur dans le dossier CMJ_Brut,
    quel que soit le format exact du nom de fichier (espace/underscore,
    accents, ordre Nom/Prénom, casse...).
    """
    if not os.path.exists(dossier_brut):
        return None
    target_code = super_clean_name(player_name)
    for f in os.listdir(dossier_brut):
        if not f.lower().endswith(".csv"):
            continue
        nom_fichier_sans_ext = f[:-4]
        # on remplace les underscores par des espaces pour que "LEONI_Théo"
        # soit traité comme "LEONI Théo"
        nom_fichier_sans_ext = nom_fichier_sans_ext.replace("_", " ")
        if super_clean_name(nom_fichier_sans_ext) == target_code:
            return os.path.join(dossier_brut, f)
    return None


def check_has_cmj(p_name, df):
    # 1. Le joueur a-t-il une ligne dans le fichier consolidé CMJ20262027.csv ?
    if not df.empty and 'Joueur_Code' in df.columns:
        if super_clean_name(p_name) in df['Joueur_Code'].values:
            return True
    # 2. Sinon, a-t-il au moins un fichier brut dans CMJ_Brut ?
    return find_raw_cmj_file(p_name) is not None

@st.dialog("Analyse Biomécanique du Saut (CMJ)", width="large")
def show_cmj_details(player_name, df_cmj):
    import plotly.graph_objects as go
    import pandas as pd
    import os
    import re
    import unicodedata
    
    st.markdown("""
    <style>
        div[role="dialog"] {
            width: 75vw !important;
            max-width: 1400px !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    if df_cmj.empty or 'Joueur_Code' not in df_cmj.columns:
        st.warning("Fichier de données CMJ introuvable.")
        return

    def parse_val(v):
        if pd.isna(v) or str(v).strip().lower() in ['nan', 'na', 'none', '']: return 0.0
        try: return float(str(v).replace(",", ".").replace(" ", ""))
        except: return 0.0

    target_code = super_clean_name(player_name)
    row_cmj = df_cmj[df_cmj['Joueur_Code'] == target_code]
    
    if row_cmj.empty:
        st.error(f"Aucune donnée trouvée pour {player_name}.")
        return

    rc = row_cmj.iloc[0]

    def get_cmj_pct(col, val):
        if val == 0: return 0
        s = pd.to_numeric(df_cmj[col], errors='coerce').dropna()
        if s.empty: return 0
        return (s <= val).mean() * 100

    # --- 1. EXTRACTION DES KPIs ---
    metrics = {
        "Force Max (N)": {"col": "Pic de Force Max (N)", "val": parse_val(rc.get("Pic de Force Max (N)"))},
        "Puissance Max (W)": {"col": "Pic de Puissance Max (W)", "val": parse_val(rc.get("Pic de Puissance Max (W)"))},
        "mRSI": {"col": "mRSI (JH/CT) (m/s)", "val": parse_val(rc.get("mRSI (JH/CT) (m/s)"))},
        "RFD Poussée (N/s)": {"col": "Pic de RFD Max (N/s)", "val": parse_val(rc.get("Pic de RFD Max (N/s)"))},
        "RFD Freinage (N/s)": {"col": "Phase de Freinage - RFD Excentrique (N/s)", "val": parse_val(rc.get("Phase de Freinage - RFD Excentrique (N/s)"))},
        "Hauteur (cm)": {"col": "Hauteur de saut (Vitesse) (cm)", "val": parse_val(rc.get("Hauteur de saut (Vitesse) (cm)"))}
    }

    for k, v in metrics.items():
        v["pct"] = get_cmj_pct(v["col"], v["val"])

    st.markdown(f"<h3 style='color:#D71920; text-align:center; margin-bottom:15px; text-transform:uppercase;'>{player_name} - PROFIL CMJ</h3>", unsafe_allow_html=True)
    
    # --- 2. AFFICHAGE DES CARTES (KPIs) VIA ST.COLUMNS ---
    cols_kpi = st.columns(6)
    
    for idx, (label, data) in enumerate(metrics.items()):
        val = data["val"]
        pct = data["pct"]
        rank = max(1, 100 - int(pct)) 
        
        c_bar = "#D71920" if pct < 33 else "#F39C12" if pct < 66 else "#27AE60" if pct < 95 else "#00E5FF"
        
        val_str = f"{val:.1f}" if val < 100 else f"{val:.0f}"
        if label == "mRSI": val_str = f"{val:.2f}"
        
        unit = label.split('(')[-1].replace(')','') if '(' in label else ""
        title = label.split(' (')[0]

        with cols_kpi[idx]:
            st.markdown(f"""
            <div style='background:#fff; border-radius:8px; padding:12px; border:1px solid #eee; border-top:4px solid {c_bar}; box-shadow:0 2px 5px rgba(0,0,0,0.02); margin-bottom: 20px;'>
                <div style='font-size:11px; color:#555; font-weight:900; text-transform:uppercase; margin-bottom:5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>{title}</div>
                <div style='font-size:18px; font-weight:900; color:#111;'>{val_str} <span style='font-size:10px; color:#666;'>{unit}</span></div>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-top:8px; border-top:1px solid #f9f9f9; padding-top:5px;'>
                    <span style='font-size:9px; color:#707070; font-weight:bold;'>CLASS.</span>
                    <span style='font-size:11px; font-weight:900; color:{c_bar};'>Top {rank}%</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    col_g1, col_g2 = st.columns([1, 1.8])
    
    # --- 3. RADAR CHART COMPARATIF ---
    with col_g1:
        st.markdown("<div style='text-align:center; font-weight:bold; font-size:14px; margin-bottom:5px; color:#333;'>Profil Comparatif vs Équipe (Percentiles)</div>", unsafe_allow_html=True)
        
        labels_radar = ["Force Max", "Puissance", "mRSI", "RFD Poussée", "RFD Freinage", "Hauteur"]
        vals_radar = [metrics["Force Max (N)"]["pct"], metrics["Puissance Max (W)"]["pct"], metrics["mRSI"]["pct"], metrics["RFD Poussée (N/s)"]["pct"], metrics["RFD Freinage (N/s)"]["pct"], metrics["Hauteur (cm)"]["pct"]]
        
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=[33]*6, theta=labels_radar, mode='lines', line_color='rgba(0,0,0,0)', fill='toself', fillcolor='rgba(215, 25, 32, 0.1)', hoverinfo='skip'))
        fig_radar.add_trace(go.Scatterpolar(r=[66]*6, theta=labels_radar, mode='lines', line_color='rgba(0,0,0,0)', fill='none', hoverinfo='skip'))
        fig_radar.add_trace(go.Scatterpolar(r=[100]*6, theta=labels_radar, mode='lines', line_color='rgba(0,0,0,0)', fill='tonext', fillcolor='rgba(39, 174, 96, 0.1)', hoverinfo='skip'))
        fig_radar.add_trace(go.Scatterpolar(r=vals_radar + [vals_radar[0]], theta=labels_radar + [labels_radar[0]], fill='toself', name=player_name, line=dict(color="#423D3D", width=2), marker=dict(size=6, color="#423D3D"), fillcolor='rgba(5, 5, 5, 0.4)'))
        
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100], tickvals=[33, 66], ticktext=["", ""], gridcolor="#ccc"), angularaxis=dict(tickfont=dict(size=11, weight="bold"))), showlegend=False, height=350, margin=dict(l=40, r=40, t=20, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_radar, width='stretch', config={'displayModeBar': False})

    # --- 4. COURBE FORCE-TEMPS RÉELLE (1000 HZ) ---
    with col_g2:
        st.markdown("<div style='text-align:center; font-weight:bold; font-size:14px; margin-bottom:5px; color:#333;'>Courbe Réelle Force-Temps (1000 Hz)</div>", unsafe_allow_html=True)
        
        dossier_brut = "CMJ_Brut"
        fichier_brut_trouve = find_raw_cmj_file(player_name, dossier_brut)

        if fichier_brut_trouve:
            try:
                # Lecture plus robuste
                with open(fichier_brut_trouve, 'r', encoding='utf-8', errors='ignore') as f: 
                    lines = f.readlines()

                # Recherche automatique du début des données (évite de chercher "Données brutes")
                raw_data_start = -1
                for i, line in enumerate(lines):
                    # Cherche une ligne qui contient des nombres séparés par virgule
                    parts = line.split(',')
                    if len(parts) >= 5 and parts[0].replace('.', '').strip().isdigit():
                        raw_data_start = i
                        break

                # Le fichier Kinvent contient DEUX blocs de données brutes à la suite :
                # 1) "Données brutes" -> temps, Phases, Force Totale, Force G, Force D (5 colonnes) -> celui qu'on veut
                # 2) "Données brutes du canal" -> valeurs individuelles de chaque capteur (10 colonnes)
                # On s'arrête donc à la première ligne vide qui suit, pour ne jamais lire le 2e bloc.
                raw_data_end = len(lines)
                if raw_data_start != -1:
                    for j in range(raw_data_start, len(lines)):
                        if lines[j].strip() == "":
                            raw_data_end = j
                            break

                G_FORCE = 9.80665  # conversion kgf -> Newtons (les valeurs brutes Kinvent sont en kg)

                parsed_data = []
                if raw_data_start != -1:
                    for i in range(raw_data_start, raw_data_end):
                        parts = lines[i].strip().split(',')
                        if len(parts) < 5:
                            continue
                        try:
                            parsed_data.append((
                                float(parts[0]),
                                float(parts[2]) * G_FORCE,
                                float(parts[3]) * G_FORCE,
                                float(parts[4]) * G_FORCE,
                            ))
                        except ValueError: continue

                    if parsed_data:
                        df_curve = pd.DataFrame(parsed_data, columns=['Time', 'Force_Tot', 'Force_G', 'Force_D'])
                        t_peak = df_curve.loc[df_curve['Force_Tot'].idxmax(), 'Time']
                        df_curve = df_curve[df_curve['Time'] >= (t_peak - 1.5)]
                        
                        fig_ft = go.Figure()
                        fig_ft.add_trace(go.Scatter(x=df_curve['Time'], y=df_curve['Force_G'], name='Gauche', line=dict(color='#1E3A8A')))
                        fig_ft.add_trace(go.Scatter(x=df_curve['Time'], y=df_curve['Force_D'], name='Droite', line=dict(color='#888888')))
                        fig_ft.add_trace(go.Scatter(x=df_curve['Time'], y=df_curve['Force_Tot'], name='Total', line=dict(color='#D71920')))
                        
                        fig_ft.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor='rgba(0,0,0,0)', xaxis_title="Temps (s)", yaxis_title="Force (N)", hovermode="x unified")
                        st.plotly_chart(fig_ft, width='stretch', config={'displayModeBar': False})
                    else:
                        st.info("Données vides.")
            except Exception as e:
                st.error(f"Erreur lecture: {e}")
        else:
            st.info(f"Fichier non trouvé pour : {player_name} (Cherché: {dossier_brut}/{player_name}.csv)")
@st.cache_data(ttl=5)
def load_all_data():
    url = "https://docs.google.com/spreadsheets/d/1P1hxqlqO03L3nBnnchnKjbw22LIPXqi2/export?format=csv&gid=795853830"
    try:
        df = pd.read_csv(url)
        cols_lower = {str(c).lower().strip(): c for c in df.columns}
        target = next((cols_lower[k] for k in ['joueur', 'nom', 'name'] if k in cols_lower), None)
        if not target: return pd.DataFrame(), "Colonne 'Joueur' introuvable"
        df = df.dropna(subset=[target]).rename(columns={target: 'Joueur'})
        df['Joueur'] = df['Joueur'].astype(str).str.title().str.strip()
        return df, None
    except Exception as e:
        st.error(f"Erreur avec le Google Sheet : {e}")
        pass
        
    possible_files = [
        "Profilage 2026-2027_2.xlsx",
        "Profilage 2026-2027.xlsx", 
        "Profilage 2026-2027.csv"
    ]
    found_file = None
    for f in possible_files:
        if os.path.exists(f):
            found_file = f
            break
    if not found_file: 
        return pd.DataFrame(), "Fichier introuvable"
    return load_data_from_source(found_file)
    
def generate_heatmap_body_svg(injury_counts):
    img_filename = "anatomie_corps.png"
    if not os.path.exists(img_filename) and os.path.exists("anatomie_corps.jpg"):
        img_filename = "anatomie_corps.jpg"
        
    svg_w, svg_h = 600, 600 
    
    try:
        with open(img_filename, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        ext = "jpeg" if "jpg" in img_filename else "png"
        bg_html = f'<image href="data:image/{ext};base64,{img_b64}" width="{svg_w}" height="{svg_h}" x="0" y="0" preserveAspectRatio="xMidYMid meet" />'
    except Exception:
        bg_html = f'<rect width="{svg_w}" height="{svg_h}" fill="#f8f9fa" />'

    coords = {
        "Tête": (175, 45),
        "Épaule (G)": (234, 144), "Épaule (D)": (113, 144),
        "Membre Supérieur (G)": (260, 235), "Membre Supérieur (D)": (103, 235), 
        "Lombaire / Dos": (420, 260), "Symphyse / Pubalgie": (175, 295),
        "Psoas (G)": (195, 290), "Psoas (D)": (150, 290),
        "Fessiers (G)": (390, 305), "Fessiers (D)": (440, 305),
        "Droit Fémoral (G)": (210, 350), "Droit Fémoral (D)": (140, 350),
        "Ischio-jambiers (G)": (385, 355), "Ischio-jambiers (D)": (446, 355),
        "Adducteurs (G)": (195, 330), "Adducteurs (D)": (155, 330),
        "LCA (G)": (202, 416), "LCA (D)": (146, 416),
        "LCP (G)": (385, 416), "LCP (D)": (446, 416),
        "LLI Genou (G)": (185, 416), "LLI Genou (D)": (165, 416),
        "LLE Genou (G)": (217, 416), "LLE Genou (D)": (131, 416),
        "Ménisque (G)": (202, 416), "Ménisque (D)": (146, 416),
        "Rotule / Cartilage (G)": (202, 416), "Rotule / Cartilage (D)": (146, 416),
        "Tendon Rotulien (G)": (202, 435), "Tendon Rotulien (D)": (146, 435),
        "Triceps Sural / Mollet (G)": (385, 480), "Triceps Sural / Mollet (D)": (446, 480),
        "Tendon d'Achille (G)": (400, 544), "Tendon d'Achille (D)": (445, 544),
        "LLE Cheville - Entorse (G)": (210, 535), "LLE Cheville - Entorse (D)": (140, 535),
        "Syndesmose (G)": (200, 530), "Syndesmose (D)": (150, 530),
        "5ème Métatarsien (G)": (210, 545), "5ème Métatarsien (D)": (140, 545),
        "Pied / Orteil (G)": (200, 539), "Pied / Orteil (D)": (150, 544),
        "Aponévrose Plantaire (G)": (400, 555), "Aponévrose Plantaire (D)": (445, 555)
    }

    markers = ""
    for inj, count in injury_counts.items():
        if inj in coords:
            x, y = coords[inj]
            markers += f'<circle cx="{x}" cy="{y}" r="16" fill="rgba(52, 152, 219, 0.4)" stroke="#3498DB" stroke-width="2"/>'
            if count > 1:
                markers += f'<circle cx="{x+10}" cy="{y-10}" r="8" fill="#D71920"/><text x="{x+10}" y="{y-6}" font-size="10" font-family="Arial" font-weight="bold" fill="white" text-anchor="middle">{count}</text>'
            else:
                markers += f'<circle cx="{x}" cy="{y}" r="4" fill="#3498DB"/>'

    svg_code = f"""
    <svg viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" style="background:#fff; border-radius:10px; border:1px solid #eee;">
        {bg_html}
        {markers}
    </svg>
    """
    svg_b64 = base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')
    return f'<div style="display:flex; justify-content:center;"><img src="data:image/svg+xml;base64,{svg_b64}" style="max-height:430px; width:auto; max-width:100%; object-fit:contain; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius:10px;"></div>'

@st.cache_data
def _find_and_read_metamax_pdf(p_sel):
    """
    Cherche le PDF Metamax/Pacelab du joueur dans TestsMetamax/ et le lit.
    Mis en cache par joueur : ces fichiers ne changent pas pendant qu'on
    utilise l'app, inutile de rescanner le dossier et relire le PDF à
    chaque rerun (même quand on interagit avec autre chose sur la page).
    Renvoie (chemin, contenu_bytes) ou (None, None) si rien trouvé.
    """
    parts = p_sel.split()
    if len(parts) >= 2:
        nom = parts[0].lower()
        prenom = " ".join(parts[1:]).lower()
    else:
        nom = p_sel.lower()
        prenom = ""

    dossier_cible_lower = f"{prenom} {nom}".strip()

    if prenom:
        prefixe_fichier_lower = f"sdr_{prenom.replace(' ', '_')}_{nom.replace(' ', '_')}"
    else:
        prefixe_fichier_lower = f"sdr_{nom.replace(' ', '_')}"

    dossier_racine = os.path.join(os.getcwd(), "TestsMetamax")
    pdf_path = None

    if os.path.exists(dossier_racine):
        for dossier in os.listdir(dossier_racine):
            if dossier.lower() == dossier_cible_lower:
                chemin_dossier_joueur = os.path.join(dossier_racine, dossier)
                if os.path.isdir(chemin_dossier_joueur):
                    for fichier in os.listdir(chemin_dossier_joueur):
                        f_lower = fichier.lower()
                        if f_lower.startswith(prefixe_fichier_lower) and "cap" in f_lower and f_lower.endswith(".pdf"):
                            pdf_path = os.path.join(chemin_dossier_joueur, fichier)
                            break
                break

    if not pdf_path:
        return None, None

    with open(pdf_path, "rb") as f:
        return pdf_path, f.read()


@st.cache_data
def _list_1080_pdfs(p_sel):
    """
    Liste les rapports PDF 1080 Sprint disponibles pour un joueur. Mis en
    cache : le dossier 1080/ ne change pas pendant qu'on utilise l'app,
    inutile de le rescanner à chaque rerun.
    """
    dossier_1080 = os.path.join(os.getcwd(), "1080")
    player_1080_name = p_sel.replace(" ", "").lower()
    pdf_1080_files = []
    if os.path.exists(dossier_1080):
        for fichier in os.listdir(dossier_1080):
            if fichier.replace("_", "").replace(" ", "").lower().startswith(player_1080_name) and fichier.lower().endswith(".pdf"):
                pdf_1080_files.append(fichier)
    pdf_1080_files.sort(reverse=True)
    return pdf_1080_files


@st.cache_data
def _read_pdf_bytes(path):
    """Lit un fichier PDF depuis le disque. Mis en cache par chemin."""
    with open(path, "rb") as f:
        return f.read()


@st.cache_data
def _load_exercise_db():
    """
    Recherche et charge le fichier "Exercices_Renfo" (csv ou xlsx).
    Mis en cache : ce fichier ne change pas pendant qu'on utilise l'app —
    inutile de rescanner le dossier et de le relire à chaque rerun.
    """
    for f in os.listdir():
        if "Exercices_Renfo" in f and f.endswith((".csv", ".xlsx")):
            return pd.read_csv(f) if f.endswith(".csv") else pd.read_excel(f)
    return None


def get_recommendations_v3(player_row, df_all):
    try:
        df_exos = _load_exercise_db()
        if df_exos is None:
            return [], [], None

        liste_noms_exos = sorted(df_exos['Exercice'].dropna().unique().tolist())
        potential_recos = []
        
        # 1. Analyse des Déficits (Profilage Athlétique & Physiologique UNIQUEMENT)
        kpis_critiques = {
            "CMJ 2JB": "CMJ", "Vmax": "Vmax", "Squat belt (N)": "Squat",
            "Adducteurs (G)": "Adducteurs", "Nordic Ischio (G)": "Nordic"
        }
        
        for metric_ui, keyword in kpis_critiques.items():
            col = find_column_in_df(df_all, metric_ui)
            val = clean_numeric_value(player_row.get(col))
            if val is not None:
                _, pct = calculate_percentile(df_all, col, val)
                
                # Couleurs et niveaux selon priorité
                if pct < 33: 
                    niv, color = "PRIORITE FORTE", "#D71920" # Rouge
                elif pct < 66: 
                    niv, color = "PRIORITE MOYENNE", "#F39C12" # Orange
                else: 
                    niv, color = "PRIORITE FAIBLE", "#27AE60" # Vert
                
                score_priorite = 100 - pct
                matches = df_exos[df_exos['Cible (Variables du profilage)'].astype(str).str.contains(keyword, na=False, case=False)]
                
                # LIMITE À 2 EXERCICES MAX PAR TEST pour équilibrer la programmation
                for _, exo in matches.head(2).iterrows():
                    d_exo = exo.to_dict()
                    d_exo.update({'priorite_score': score_priorite, 'niveau': niv, 'couleur': color, 
                                 'pourquoi': f"Déficit sur le test {keyword} (Classé dans les {int(pct)}% les plus faibles)."})
                    potential_recos.append(d_exo)

        # La partie médicale (asymétrie, adducteurs, etc.) a été supprimée.

        if not potential_recos: return [], liste_noms_exos, df_exos

        # Tri et suppression des doublons
        df_recos = pd.DataFrame(potential_recos).sort_values('priorite_score', ascending=False)
        # On garde les 4 exercices les plus prioritaires au total
        top_recos = df_recos.drop_duplicates(subset=['Exercice']).head(4).to_dict('records')
        return top_recos, liste_noms_exos, df_exos
        
    except Exception:
        return [], [], None
    
# remove_accents, is_inverted, clean_numeric_value, get_column_stats et
# calculate_percentile vivent maintenant dans data_utils.py (partagees avec
# profiling_report.py, comparateur.py, team_profiling.py -- voir l'en-tete
# de ce module : ces fonctions existaient en plusieurs copies legerement
# differentes, ce qui a cause de vrais bugs de percentile).

@st.cache_data
def _get_ranked_column(df, col_name):
    """
    Classe tous les joueurs sur une colonne donnée. Mis en cache : ce
    classement ne dépend pas du joueur affiché, donc pas besoin de le
    refaire à chaque fois que calculate_rank_info() est appelée pour un
    joueur différent (des dizaines de fois par rendu de page).
    """
    valid_data = pd.to_numeric(df[col_name], errors='coerce').dropna()
    if valid_data.empty:
        return None
    inverted = is_inverted(col_name)
    return valid_data, valid_data.rank(method='min', ascending=inverted)


def calculate_rank_info(df, col_name, value):
    if col_name not in df.columns or pd.isna(value): return "-", "-"
    ranked_info = _get_ranked_column(df, col_name)
    if ranked_info is None: return "-", "-"
    valid_data, ranked = ranked_info
    try:
        matches = ranked[valid_data == float(value)]
        if not matches.empty:
            player_rank = int(matches.iloc[0])
            total = len(valid_data)
            return player_rank, total
        return "-", "-"
    except: return "-", "-"

# calcul des asymétries
def get_asymmetry(df_row, metric_label, df):
    if "(G)" not in metric_label: return None
    metric_label_d = metric_label.replace("(G)", "(D)")
    col_g = find_column_in_df(df, metric_label)
    col_d = find_column_in_df(df, metric_label_d)
    if not col_g or not col_d: return None
    val_g = clean_numeric_value(df_row.get(col_g))
    val_d = clean_numeric_value(df_row.get(col_d))
    if val_g is None or val_d is None: return None
    try:
        max_val = max(val_g, val_d)
        if max_val == 0: return 0
        diff = (abs(val_g - val_d) / max_val) * 100
        return diff
    except: return None

# get_cleaned_columns / find_column_in_df -> deplacees dans data_utils.py.

# trouver le numéro (au cas ou ça change)
def find_number_column(df):
    cols_map = {remove_accents(str(c)).lower().strip(): c for c in df.columns}
    targets = ['n° gps', 'n°gps', 'numero', 'numéro', 'number', 'maillot', 'shirt', 'n°']
    for t in targets:
        if t in cols_map: return cols_map[t]
    for c_clean, c_original in cols_map.items():
        if c_clean.startswith("num") or c_clean.startswith("n°"): return c_original
    return None

@st.cache_data(ttl=600, show_spinner=False)
def img_to_b64(img_path):
    try:
        with open(img_path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

# ajout des photos des joueurs
@st.cache_data(ttl=600, show_spinner=False)
def get_best_photo_path(player_name):
    # @st.cache_data : évite un os.listdir() complet du dossier Photos par
    # joueur à chaque rerun Streamlit (cf. comparateur.img_to_b64 pour le détail).
    folder = "Photos"
    if not os.path.exists(folder): return None

    files_map = {f.lower(): f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))}
    
    clean_name = player_name.strip()
    parts = clean_name.split()
    
    candidates = []
    candidates.append(clean_name)
    
    if len(parts) > 1:
        inverted = f"{parts[-1]} {' '.join(parts[:-1])}"
        candidates.append(inverted)
        
        candidates.append(f"{' '.join(parts[1:])} {parts[0]}")

    extensions = [".jpg", ".png", ".jpeg"]
    
    for cand in candidates:
        for ext in extensions:
            target_key = f"{cand}{ext}".lower()
            if target_key in files_map:
                return os.path.join(folder, files_map[target_key])
            
    return None



# NB : create_radar_chart / create_multi_radar_chart (matplotlib) qui vivaient
# ici n'étaient jamais appelées (code mort) et ont été supprimées. Les radars
# affichés dans l'app passent par charts.build_radar (Plotly) ; le radar du
# rapport PDF/HTML vit dans profiling_report.py.


def smart_format(val):
    if pd.isna(val) or val is None or val == "": return "-"
    try:
        val_float = float(val)
        if val_float == 0: return "0"
        if val_float % 1 == 0: return f"{int(val_float)}"
        return f"{val_float:.2f}"
    except: return "-"

def get_clean_label(label):
    return label.replace("(G)", "").replace("(D)", "").strip()

def get_unit(label):
    unit = UNITS.get(label, UNITS.get(get_clean_label(label), ""))
    if not unit:
        l = str(label).lower()
        if "temps" in l or "tau" in l or "t90" in l: return "s"
        if "amax" in l: return "m/s²"
        if "pmax" in l: return "W"
        if "vmax" in l or "v0" in l: return "m/s"
        if "d90" in l: return "m"
        if "momentum" in l: return "kg*m/s"
        if "f0" in l: return "N"
    return unit
def get_col_name(label):
    return COL_MAPPING.get(label, label)

def get_rel_col_name(label):
    return REL_COL_MAPPING.get(label, None)

def get_source(label):
    return SOURCES_CONFIG.get(get_clean_label(label), "Club")

def get_effective_norm(label, norm_val, effective_mode, poids_joueur):
    """
    Adapte une norme de REPORT_NORMES au mode d'affichage courant (Absolu/Relatif).
    Certaines normes (RELATIVE_NORM_KEYS) sont stockées EN RELATIF dans REPORT_NORMES
    (ex: Nordic Ischio, Biodex...), d'autres sont stockées EN ABSOLU (ex: Peak Force CMJ).
    Sans cette conversion, la norme affichée/comparée ne correspond pas à l'unité
    réellement affichée dès qu'on bascule le mode Absolu/Relatif.
    """
    if effective_mode is None or not poids_joueur or poids_joueur <= 0:
        return norm_val

    is_norm_relative = label in RELATIVE_NORM_KEYS or get_clean_label(label) in RELATIVE_NORM_KEYS

    def convert(v):
        if is_norm_relative and not effective_mode:
            return v * poids_joueur   # norme relative -> on l'exprime en absolu
        if not is_norm_relative and effective_mode:
            return v / poids_joueur   # norme absolue -> on l'exprime en relatif
        return v

    if isinstance(norm_val, (list, tuple)):
        return tuple(convert(v) for v in norm_val)
    return convert(norm_val)

def get_norme_valeur(found_key, poste_groupe=None):
    """
    Valeur de norme brute pour `found_key` (une clé de REPORT_NORMES) --
    objectif PAR POSTE (REPORT_NORMES_PAR_POSTE) s'il existe pour cet
    indicateur ET ce poste, sinon repli sur l'objectif unique historique
    (REPORT_NORMES). Voir config_rapport.py pour le détail des valeurs
    GPS par poste (demande 09/2026).
    """
    par_poste = REPORT_NORMES_PAR_POSTE.get(found_key)
    if par_poste and poste_groupe and poste_groupe in par_poste:
        return par_poste[poste_groupe]
    return REPORT_NORMES[found_key]


def get_norm_text(label, effective_mode=None, poids_joueur=None, poste_groupe=None):
    col_clean = str(label).replace("(G)", "").replace("(D)", "").strip()

    found_key = col_clean if col_clean in REPORT_NORMES else next((k for k in REPORT_NORMES.keys() if k in col_clean), None)

    if not found_key: return "-"

    norm_val = get_effective_norm(label, get_norme_valeur(found_key, poste_groupe), effective_mode, poids_joueur)
    
    unit_abs = get_unit(label)
    unit_abs_lower = unit_abs.lower()

    is_speed = (any(x in unit_abs_lower for x in ["m/s", "km/h"]) or any(x in label.lower() for x in ["vmax", "v0", "speed"])) and "²" not in unit_abs_lower
    
    if is_speed and isinstance(norm_val, (int, float)):
        is_kmh_native = norm_val > 15 or "km/h" in unit_abs_lower
        val_kmh = norm_val if is_kmh_native else norm_val * 3.6
        val_ms = norm_val / 3.6 if is_kmh_native else norm_val
        
        show_ms = st.session_state.get("show_ms_global", False)
        
        norm_val = val_ms if show_ms else val_kmh
        unit_abs = "m/s" if show_ms else "km/h"
        unit_abs_lower = unit_abs.lower()

    if effective_mode:
        unit_display = "N/kg" if "n" in unit_abs_lower else "W/kg" if "w" in unit_abs_lower else "kg/kg" if "kg" in unit_abs_lower else unit_abs
    else:
        unit_display = unit_abs
        
    suffix = f" {unit_display}"
    
    if isinstance(norm_val, (list, tuple)):
        low, high = norm_val
        if is_inverted(label):
            return f"Obj: < {smart_format(low)}{suffix}"
        else:
            return f"Obj: {smart_format(low)} - {smart_format(high)}{suffix}"
    else:
        if is_inverted(label):
            return f"Obj: < {smart_format(norm_val)}{suffix}"
        else:
            return f"Obj: {smart_format(norm_val)}{suffix}"

def get_bar_color(pct):
    if pct < 33: return "#D71920"
    if pct < 66: return "#F39C12"
    if pct < 95: return "#27AE60"
    return "#2DC4F6"

def get_status_data_local(label, value, effective_mode=None, poids_joueur=None, poste_groupe=None):
    val = clean_numeric_value(value)
    if val is None: return "#888", "-", "#888" 
    
    col_clean = str(label).replace("(G)", "").replace("(D)", "").strip()
    
    # On force la recherche du nom exact en priorité
    found_key = col_clean if col_clean in REPORT_NORMES else next((k for k in REPORT_NORMES.keys() if k in col_clean), None)
    
    if not found_key: return "#444444", "-", "#111111"
    
    if "Ratio Squeeze" in col_clean:
        if 0.90 <= val <= 1.10:
            return "#27AE60", "🟢", "#27AE60"
        else:
            return "#D71920", "🔴", "#D71920"

    found_key = next((k for k in REPORT_NORMES.keys() if k in col_clean), None)

    if not found_key: return "#444444", "-", "#111111"

    norm_val = get_effective_norm(label, get_norme_valeur(found_key, poste_groupe), effective_mode, poids_joueur)
    c_bad, c_avg, c_good = "#D71920", "#F39C12", "#27AE60"
    
    if isinstance(norm_val, (list, tuple)):
        low, high = norm_val
        if is_inverted(label):
            if val < low: return c_good, "Bon", c_good
            elif val <= high: return c_avg, "Moyen", c_avg
            else: return c_bad, "Mauvais", c_bad
        else:
            if val < low: return c_bad, "Mauvais", c_bad
            elif val < high: return c_avg, "Moyen", c_avg
            else: return c_good, "Bon", c_good
    else:
        if is_inverted(label):
            if val <= norm_val: return c_good, "🟢", c_good
            else: return c_bad, "🔴", c_bad
        else:
            if val >= norm_val: return c_good, "🟢", c_good
            else: return c_bad, "🔴", c_bad

def get_rel_display_smart(row_data, label_name, abs_val, p_poids):
    rel_col = get_rel_col_name(label_name)
    unit_abs = get_unit(label_name).lower()
    
    if rel_col and rel_col in row_data:
        val = clean_numeric_value(row_data[rel_col])
        if val: 
             u = "W/kg" if "w" in unit_abs else "N/kg" if "n" in unit_abs else "kg/kg" if "kg" in unit_abs else ""
             return f"{val:.2f} {u}"
    
    if p_poids and p_poids > 0 and abs_val is not None:
        if "n" in unit_abs: return f"{(abs_val/p_poids):.2f} N/kg"
        elif "w" in unit_abs or "watt" in label_name.lower(): return f"{(abs_val/p_poids):.2f} W/kg"
        elif "kg" in unit_abs: return f"{(abs_val/p_poids):.2f} kg/kg"
        
    return None

def get_tooltip_html(row, label):
    rel_col = get_rel_col_name(label)
    if rel_col and rel_col in row:
        val_rel = clean_numeric_value(row[rel_col])
        if val_rel is not None:
            unit_abs = get_unit(label).lower()
            unit_rel = "N/kg" if "n" in unit_abs else "W/kg" if "w" in unit_abs else "kg/kg" if "kg" in unit_abs else ""
            return f"title='Relatif: {val_rel:.2f} {unit_rel}'"
    return ""

def get_asym_badge_info(val_l, val_r, df_data, col_l, col_r):
    if val_l is None or val_r is None: return None, None
    
    if "Knee" in col_l or "KTW" in col_l:
         max_l = pd.to_numeric(df_data[col_l], errors='coerce').max()
         max_r = pd.to_numeric(df_data[col_r], errors='coerce').max()
         ref = max(max_l, max_r) if (pd.notna(max_l) and pd.notna(max_r)) else 0
         if ref == 0: return 0, ""
         pct = (abs(val_l - val_r) / ref) * 100
    else:
         if max(val_l, val_r) == 0: return 0, ""
         pct = (abs(val_l - val_r) / max(val_l, val_r)) * 100
         
    side = "G" if val_l < val_r else "D"
    return pct, side


def inject_custom_css():
    st.markdown(f"""
    <style>
        /* Titres de section principaux en Rouge */
        .section-header {{ font-size: 20px; font-weight: 900; color: {SDR_RED}; margin-top: 30px; margin-bottom: 15px; padding-left: 12px; border-left: 6px solid {SDR_RED}; border-bottom: 2px solid #eee; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }}
        
        .kpi-card {{ background-color: #ffffff; border-radius: 8px; padding: 15px; margin-bottom: 15px; height: 100%; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border: 1px solid #eee; transition: transform 0.2s; }}
        .kpi-card:hover {{ transform: translateY(-2px); border-color: {SDR_RED}; box-shadow: 0 4px 12px rgba(215,25,32,0.15); }}
        .kpi-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 5px; }}
        .kpi-val {{ font-size: 24px; font-weight: 900; color: #111; margin: 5px 0; }}
        .progress-bg {{ background-color: #f0f0f0; height: 6px; border-radius: 3px; overflow: hidden; margin-top: 8px; }}
        .progress-fill {{ height: 100%; border-radius: 3px; }}
        .kpi-footer {{ display: flex; justify-content: space-between; font-size: 10px; color: #666; margin-top: 4px; }}
        
        /* EN-TÊTE DU JOUEUR (HERO) AVEC FORT CONTRASTE ROUGE */
        .hero-container {{ background: #ffffff; border-top: 4px solid {SDR_RED}; border-bottom: 4px solid {SDR_RED}; padding: 25px; border-radius: 12px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 20px rgba(215,25,32,0.08); margin-bottom: 25px; }}
        .hero-left {{ display: flex; align-items: center; gap: 25px; }}
        .hero-photo {{ width: 120px; height: 120px; border-radius: 12px; border: 4px solid {SDR_RED}; object-fit: cover; box-shadow: 0 4px 10px rgba(215,25,32,0.2); background: #fff; }}
        .hero-details {{ display: flex; flex-direction: column; }}
        
        /* Nom en rouge massif */
        .hero-name {{ font-size: 42px; font-weight: 900; color: {SDR_RED}; text-transform: uppercase; line-height: 1; margin-bottom: 6px; text-shadow: 1px 1px 0px rgba(0,0,0,0.05); }}
        /* Numéro en badge rouge */
        .hero-number {{ display: inline-block; background-color: {SDR_RED}; color: #ffffff; padding: 2px 10px; border-radius: 4px; font-size: 18px; font-weight: 900; margin-bottom: 8px; width: max-content; }}
        .hero-meta {{ font-size: 16px; font-weight: 800; color: #555; text-transform: uppercase; letter-spacing: 1px; }}
        
        /* Séparation et Infos de droite */
        .hero-right {{ display: flex; gap: 40px; padding-right: 20px; border-left: 2px dashed #eee; padding-left: 40px; }}
        .stat-box {{ display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .stat-label {{ font-size: 12px; font-weight: 800; color: #555; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
        /* Valeurs (Âge, Taille, Poids) en Rouge */
        .stat-value {{ font-size: 32px; font-weight: 900; color: {SDR_RED}; }}
    </style>""", unsafe_allow_html=True)

# NB : load_data_from_source() est définie plus haut (ligne ~252, avec
# @st.cache_data) — une redéfinition identique mais SANS cache existait ici
# et l'écrasait silencieusement (la version cachée n'était donc jamais
# utilisée). Supprimée pour que le cache soit bien actif.



# format_pct_display -> deplacee dans data_utils.py (mode='app' par defaut).



def show_profiling_page(df_main=None):
    inject_custom_css()
    
    st.markdown("""<div style='position:absolute; top:-50px; left:0; font-size:10px; color:#666; font-weight:bold;'>Antoine Kaczmarek - DEPARTEMENT PERFORMANCE - STADE DE REIMS</div>""", unsafe_allow_html=True)

    import base64

    logo_sdr_tag = ""
    logo_dept_tag = ""

    # --- LOGO SDR ---
    if os.path.exists("logo_sdr.png"):
        with open("logo_sdr.png", "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        # Hauteur augmentée pour le milieu
        logo_sdr_tag = "<img src='data:image/png;base64," + b64 + "' style='height:280px; object-fit:contain;'/>"

    # --- LOGO DEPARTEMENT PERF ---
    nom_fichier_perf = "Departement Perf.png" 
    if os.path.exists(nom_fichier_perf):
        with open(nom_fichier_perf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        # Hauteur augmentée pour la gauche
        logo_dept_tag = "<img src='data:image/png;base64," + b64 + "' style='height:100px; object-fit:contain;'/>"

    header_html = (
        "<div style='display:flex; align-items:center; justify-content:space-between; width:100%; padding:15px 0; border-bottom: 3px solid " + SDR_RED + "; margin-bottom: 20px;'>"
            
            # 1. GAUCHE : Logo Dept Perf
            "<div style='flex: 1; display:flex; justify-content:flex-start;'>"
                + logo_dept_tag +
            "</div>"
            
            # 2. MILIEU : Logo SDR
            "<div style='flex: 1; display:flex; justify-content:center;'>"
                + logo_sdr_tag +
            "</div>"
            
            # 3. DROITE : Profilage
            "<div style='flex: 1; display:flex; flex-direction:column; align-items:flex-end; gap:2px;'>"
                "<span style='font-size:60px; font-weight:900; color:" + SDR_RED + "; text-transform:uppercase; letter-spacing:3px; line-height:1;'>PROFILAGE</span>"
                "<span style='font-size:20px; font-weight:600; color:#555; letter-spacing:2px;'>Saison 2026-2027</span>"
            "</div>"
            
        "</div>"
    )

    st.markdown(header_html, unsafe_allow_html=True)
    # Plus besoin du st.markdown("---") car je l'ai intégré directement dans le header via border-bottom

    if df_main is not None and not df_main.empty:
        df = df_main
    else:
        df, erreur = load_all_data()

    if df.empty:
        st.error(erreur)
        st.stop()

    # Gardé AVANT le filtre équipe global ci-dessous, pour l'onglet RAPPORT
    # uniquement (voir plus bas, _render_tab_rapport) : ce filtre global ne
    # doit s'appliquer qu'aux 6 autres onglets. L'onglet RAPPORT a son PROPRE
    # sélecteur d'équipe interne (nécessaire pour comparer/profiler un joueur
    # d'une équipe à celle d'une autre), et sa fonctionnalité "+ Ajouter des
    # joueurs individuels hors équipe" (génération en lot) a besoin de VOIR
    # les joueurs des AUTRES équipes pour pouvoir les ajouter.
    # BUG CORRIGÉ (09/2026) : avant ce correctif, l'onglet RAPPORT recevait
    # le DataFrame déjà filtré sur UNE SEULE équipe (le filtre global
    # ci-dessous) -- son sélecteur "+ Ajouter des joueurs individuels"
    # n'avait donc JAMAIS aucun joueur à proposer (liste toujours vide,
    # champ désactivé), quelle que soit l'équipe choisie.
    df_toutes_equipes = df

    # 1. Filtre Global : On ne filtre QUE l'équipe ici
    if "Equipe" in df.columns:
        equipes = sorted(df["Equipe"].dropna().astype(str).unique())

        # On cherche l'index de "PRO", sinon on prend 0 par défaut
        default_index = equipes.index("PRO") if "PRO" in equipes else 0

        sel_equipe = st.selectbox("Equipe :", equipes, index=default_index)
        df = df[df["Equipe"].astype(str) == sel_equipe]

    # 2. Création des 3 onglets
    tab_indiv, tab_team, tab_comp, tab_evol, tab_cluster, tab_classement, tab_rapport, tab_export = st.tabs(["PROFIL INDIVIDUEL", "ANALYSE COLLECTIVE", "COMPARATEUR", "ÉVOLUTION LONGITUDINALE", "PROFILS DE JOUEURS (IA)", "CLASSEMENT", "RAPPORT", "EXPORT"])
    
    # -- ONGLET 1 : INDIVIDUEL --
    @st.fragment
    def _render_tab_indiv():
        from scipy import stats

        df_indiv = df.copy()
        
        all_players = sorted(df_indiv['Joueur'].dropna().unique())
        if not all_players: 
            st.warning("Aucun joueur trouvé.")
            st.stop()
            
        p_sel = st.selectbox("Joueur :", all_players, key="choix_joueur_indiv")
        df_player = df_indiv[df_indiv['Joueur'] == p_sel]
        
        # 1. Sélection de la session (Ajout de l'option Record Synchronisé)
        sessions_indiv = ["🏆 Record de Saison"] + sorted(df_player['Session'].dropna().astype(str).unique())
        sess_sel = st.selectbox("Session :", sessions_indiv, key="sess_select_indiv")
        
        # 2. Application de la logique
        if sess_sel == "🏆 Record de Saison":
            row_dict = get_best_season_record_paired(df_player)

            # Sécurisation des métadonnées : dernière valeur NON VIDE de la
            # colonne (pas juste `.iloc[-1]`, qui peut tomber sur une ligne
            # "virtuelle" du fichier 1080 séparé -- ces lignes n'ont que les
            # colonnes 1080 remplies, tout le reste (Poste, Equipe...) y est
            # vide -- prendre la dernière valeur RENSEIGNÉE évite d'afficher
            # un poste vide juste parce que la ligne 1080 est chronologiquement
            # après la vraie session physique dans le tableau.
            def _last_valid(col, default='N/A'):
                if col not in df_player.columns:
                    return default
                s = df_player[col].dropna()
                return s.iloc[-1] if not s.empty else default

            row_dict['Joueur'] = p_sel
            row_dict['Session'] = "🏆 Record de Saison"
            row_dict['Equipe'] = _last_valid('Equipe')
            row_dict['Poste'] = _last_valid('Poste', _last_valid('Position', 'N/A'))
            if 'Date' not in row_dict or pd.isna(row_dict.get('Date')):
                row_dict['Date'] = _last_valid('Date', 'Bilan')
                
            row = pd.Series(row_dict)
            report_records = {} # On vide car les dates sont déjà gérées par la nouvelle fonction
        else:
            row = df_player[df_player['Session'].astype(str) == sess_sel].iloc[0]
            report_records = {}
        
        poids_col_name = find_column_in_df(df_indiv, "Poids")
        poids_joueur = clean_numeric_value(row.get(poids_col_name))
            
        
        
        col_poste = find_column_in_df(df, "Poste")
        col_lat = find_column_in_df(df, "Latéralité")
        col_num = find_number_column(df)

        try:
            val_num = f"N° {int(float(row[col_num]))}" if (col_num and col_num in row and pd.notna(row[col_num])) else ""
        except:
            val_num = f"N° {row[col_num]}" if (col_num and col_num in row and pd.notna(row[col_num])) else ""

        # Attributs FIXES du joueur (ne changent pas de session en session) :
        # cherchés sur TOUT df_player (dernière valeur renseignée), pas
        # seulement la ligne `row` de la session affichée -- le "Record de
        # Saison" (recalculé colonne par colonne) et certaines sessions
        # peuvent très bien ne pas porter ces valeurs texte (cf. le même
        # souci déjà rencontré et corrigé pour le poste secondaire).
        def _static_attr(col_name, fallback=None, prefer_specific=False):
            col = find_column_in_df(df, col_name)
            if not col or col not in df_player.columns:
                return fallback
            if not prefer_specific:
                return last_valid_value(df_player, col, fallback)
            # BUG CORRIGÉ (09/2026) : un joueur avec une ligne "Rehab" en plus
            # de sa ligne "Pré-saison" peut y avoir un code de poste moins
            # précis (ex: "EXC" générique au lieu de "EXCG") -- "dernière
            # valeur renseignée" (last_valid_value) prenait alors ce code
            # générique s'il arrivait après dans le tableau, perdant le côté
            # G/D pourtant connu. On préfère ici la valeur la PLUS PRÉCISE
            # (la plus longue, ex: "EXCG" > "EXC") parmi toutes les sessions
            # du joueur, plutôt que la simple dernière renseignée.
            valides = df_player[col].dropna()
            valides = valides[valides.astype(str).str.strip().str.lower() != "nan"]
            return max(valides, key=lambda v: len(str(v))) if not valides.empty else fallback

        # Poste précis affiché (hero + terrain) : "PositionPrincipale" (ex:
        # "DLG" = Défenseur Latéral Gauche) en 1er choix -- c'est la colonne
        # précise ajoutée par le staff -- puis "Position" (ancien nom, au
        # cas où), puis "Poste" (catégorie large : Défenseur/Milieu/...) en
        # dernier repli si aucune position précise n'est renseignée.
        val_poste = _static_attr("PositionPrincipale", prefer_specific=True) or _static_attr("Position") or _static_attr("Poste") or "-"
        val_lat = _static_attr("Latéralité") or "-"

        # Poste "large" (DÉFENSEUR/MILIEU/ATTAQUANT/GARDIEN) du joueur --
        # même regroupement que le radar par poste d'Analyse Collective
        # (team_profiling.get_poste_large) -- utilisé pour choisir l'objectif
        # GPS PAR POSTE (REPORT_NORMES_PAR_POSTE, cf. config_rapport.py) au
        # lieu de l'objectif générique unique, notamment utile pour situer
        # un joueur Révélation/Espoir/Elite par rapport au niveau PRO.
        poste_groupe_norme = get_poste_large(val_poste) if val_poste != "-" else None

        meta_text = f"{val_poste} | {val_lat}"
        if val_num:
            meta_text += f" | {val_num}"

        anthro_vals = {}
        for label in ["Age","Taille", "Poids", "Masse Grasse Plis (mm)"]:
            col_name = find_column_in_df(df, label)
            val = clean_numeric_value(row.get(col_name))
            if label == "Age": unit = " ans"
            elif label == "Taille": unit = " cm"
            elif label == "Poids": unit = " kg"
            else: unit = " mm"
            
            if label == "Taille" and val is not None:
                anthro_vals[label] = f"{val:.1f}{unit}"
            else:
                anthro_vals[label] = f"{smart_format(val)}{unit}" if val else "-"
        
        use_relative = st.toggle("Afficher en valeurs Relatives (N/kg, W/kg)", key="use_relative_mode")
        photo_path = get_best_photo_path(p_sel) 
        img_src = f"data:image/png;base64,{img_to_b64(photo_path)}" if photo_path else ""
        img_html = f'<img src="{img_src}" class="hero-photo">' if img_src else '<div class="hero-photo" style="display:flex;align-items:center;justify-content:center;background:#222;color:#555;font-size:10px;">PHOTO</div>'
        
        st.markdown(f"""
<style>
.stat-box {{ white-space: nowrap; font-size: 0.9em; }}
</style>
<div class="hero-container">
<div class="hero-left">{img_html}<div class="hero-details"><div class="hero-name">{p_sel}</div><div class="hero-meta">{meta_text}</div></div></div>
<div class="hero-right">
<div class="stat-box"><div class="stat-label">AGE</div><div class="stat-value">{anthro_vals['Age']}</div></div>
<div class="stat-box"><div class="stat-label">TAILLE</div><div class="stat-value">{anthro_vals['Taille']}</div></div>
<div class="stat-box"><div class="stat-label">POIDS</div><div class="stat-value">{anthro_vals['Poids']}</div></div>
<div class="stat-box"><div class="stat-label">Plis cutanés</div><div class="stat-value">{anthro_vals['Masse Grasse Plis (mm)']}</div></div>
</div>
</div>
""", unsafe_allow_html=True)

        # --- POSTE(S) JOUABLE(S) : première brique du "profilage
        # technico-tactique" à venir. Poste principal = "PositionPrincipale"
        # (poste précis, ex: "DLG" = Défenseur Latéral Gauche -- calculé
        # juste au-dessus dans val_poste) ; poste(s) secondaire(s) =
        # "PositionSecondaire" (même format). "G"/"D"/"C" en fin de code =
        # Gauche/Droite/Centre (cf. pitch_profiling.py).
        st.markdown(f"<h4 style='color:{SDR_RED}; margin-top:10px;'>⚽ Poste(s) jouable(s)</h4>", unsafe_allow_html=True)
        st.warning("🚧 **Profilage technico-tactique en construction** — le terrain ci-dessous affiche déjà le poste principal et le(s) poste(s) secondaire(s). Les données technico-tactiques détaillées viendront s'y ajouter progressivement.")
        with st.container():
            _raw_sec = _static_attr("PositionSecondaire", prefer_specific=True) or _static_attr("Postes Secondaires")
            _postes_sec = [p.strip() for p in str(_raw_sec).split(",") if p.strip()] if _raw_sec else []
            st.markdown(render_position_pitch(val_poste, _postes_sec, val_lat), unsafe_allow_html=True)

        # --- RÉSUMÉ EN UN COUP D'ŒIL ---
        # Carte de synthèse compacte, dans le même esprit "rapide en haut,
        # détails plus bas" que l'onglet RAPPORT : évite d'avoir à dérouler
        # toute la page (plusieurs milliers de lignes) pour se faire une
        # idée du joueur. Calcul 100% automatique (percentiles vs groupe de
        # référence), pas de saisie humaine ici.
        _synthese_metrics = {
            "CMJ 2JB", "RSI CMJ", "Peak Force CMJ", "RFD CMJ", "Wattbike 6s (W)", "Squat belt (N)",
            "VMA", "SV1", "SV2", "Test 1km (s)", "Amax", "Dmax", "Vmax",
            "Distance HSR", "Distance Totale", "Distance Sprint (92% Vimax)",
            "Sit and Reach", "Knee To Wall (G)", "Knee To Wall (D)",
            "Adducteurs (G)", "Adducteurs (D)", "Abducteurs (G)", "Abducteurs (D)",
            "Nordic Ischio (G)", "Nordic Ischio (D)", "Endurance Heel Raise (G)", "Endurance Heel Raise (D)",
            "Inverseur (G)", "Inverseur (D)", "Everseur (G)", "Everseur (D)",
        }
        # NB : calcul refait ici avec les fonctions de data_utils.py (celles
        # déjà utilisées partout ailleurs sur cette page pour les percentiles
        # affichés), plutôt qu'avec suggestions.auto_forces_faiblesses --
        # cette dernière suppose un DataFrame déjà nettoyé par
        # data_loader.load_and_clean_excel (écosystème RAPPORT), alors que
        # cette page travaille sur le DataFrame brut Google Sheets/Excel.
        _synth_forts, _synth_moyens, _synth_faibles = [], [], []
        for _label in _synthese_metrics:
            _col_synth = find_column_in_df(df_indiv, _label)
            if not _col_synth:
                continue
            _val_synth = clean_numeric_value(row.get(_col_synth))
            if _val_synth is None:
                continue
            _, _pct_synth = calculate_percentile(df_indiv, _col_synth, _val_synth)
            if _pct_synth is None:
                continue
            _entry_synth = (_label, round(_pct_synth))
            if _pct_synth >= 66:
                _synth_forts.append(_entry_synth)
            elif _pct_synth >= 33:
                _synth_moyens.append(_entry_synth)
            else:
                _synth_faibles.append(_entry_synth)
        _synth_forts.sort(key=lambda e: -e[1])
        _synth_moyens.sort(key=lambda e: e[1])
        _synth_faibles.sort(key=lambda e: e[1])
        _n_forts, _n_moyens, _n_faibles = len(_synth_forts), len(_synth_moyens), len(_synth_faibles)

        _df_inj_synth = load_injury_data()
        _p_sel_clean_synth = str(p_sel).strip().lower()
        _inj_synth = _df_inj_synth[_df_inj_synth['Joueur'].apply(lambda x: _p_sel_clean_synth.startswith(str(x)))]
        _n_blessures_actives = 0
        if not _inj_synth.empty:
            _today_synth = pd.Timestamp.now().normalize()
            for _, _r_inj in _inj_synth.iterrows():
                _d_inj = pd.to_datetime(str(_r_inj['Date'])[:10], errors='coerce', dayfirst=True)
                try:
                    _dur_inj = float(str(_r_inj['Duree']).replace('.0', '').strip())
                except Exception:
                    _dur_inj = 0
                if pd.notna(_d_inj) and (_d_inj + pd.Timedelta(days=_dur_inj)) >= _today_synth:
                    _n_blessures_actives += 1

        st.markdown(f"""
<div style="display:flex; gap:15px; flex-wrap:wrap; margin:6px 0 20px 0;">
    <div style="flex:1; min-width:160px; background:#eafaf1; border-left:4px solid #27AE60; border-radius:8px; padding:14px 18px;">
        <div style="font-size:26px; font-weight:900; color:#27AE60;">{_n_forts}</div>
        <div style="font-size:11px; font-weight:800; color:#555; text-transform:uppercase;">Point(s) fort(s)</div>
    </div>
    <div style="flex:1; min-width:160px; background:#fff8ec; border-left:4px solid #F39C12; border-radius:8px; padding:14px 18px;">
        <div style="font-size:26px; font-weight:900; color:#F39C12;">{_n_moyens + _n_faibles}</div>
        <div style="font-size:11px; font-weight:800; color:#555; text-transform:uppercase;">Axe(s) de travail</div>
    </div>
    <div style="flex:1; min-width:160px; background:{'#fdecea' if _n_blessures_actives else '#f4f6f9'}; border-left:4px solid {'#D71920' if _n_blessures_actives else '#999'}; border-radius:8px; padding:14px 18px;">
        <div style="font-size:26px; font-weight:900; color:{'#D71920' if _n_blessures_actives else '#666'};">{_n_blessures_actives}</div>
        <div style="font-size:11px; font-weight:800; color:#555; text-transform:uppercase;">Blessure(s) en cours</div>
    </div>
</div>
""", unsafe_allow_html=True)

        # Détail du résumé, replié par défaut : demande explicite de pouvoir
        # voir CE QUI compose les 3 chiffres ci-dessus, mais seulement au
        # clic -- pas affiché directement pour ne pas alourdir le haut de
        # page.
        with st.expander("🔎 Voir le détail du résumé"):
            _dcol1, _dcol2, _dcol3 = st.columns(3)
            with _dcol1:
                st.markdown("**🟢 Points forts**")
                if _synth_forts:
                    for _lbl, _pct in _synth_forts:
                        st.markdown(f"<div style='font-size:13px; margin-bottom:4px;'>{annotate_glossary_terms(_lbl)} — <b style='color:#27AE60;'>{format_pct_display(_pct)}</b></div>", unsafe_allow_html=True)
                else:
                    st.caption("Aucun.")
            with _dcol2:
                st.markdown("**🟠 Axes de travail**")
                _axes_synth = _synth_moyens + _synth_faibles
                if _axes_synth:
                    for _lbl, _pct in _axes_synth:
                        st.markdown(f"<div style='font-size:13px; margin-bottom:4px;'>{annotate_glossary_terms(_lbl)} — <b style='color:#F39C12;'>{format_pct_display(_pct)}</b></div>", unsafe_allow_html=True)
                else:
                    st.caption("Aucun.")
            with _dcol3:
                st.markdown("**🔴 Blessures en cours**")
                if _n_blessures_actives:
                    for _, _r_inj in _inj_synth.iterrows():
                        _d_inj_disp = pd.to_datetime(str(_r_inj['Date'])[:10], errors='coerce', dayfirst=True)
                        try:
                            _dur_inj_disp = float(str(_r_inj['Duree']).replace('.0', '').strip())
                        except Exception:
                            _dur_inj_disp = 0
                        if pd.notna(_d_inj_disp) and (_d_inj_disp + pd.Timedelta(days=_dur_inj_disp)) >= pd.Timestamp.now().normalize():
                            st.markdown(f"<div style='font-size:13px; margin-bottom:4px;'>{str(_r_inj['Localisation']).strip()} <span style='color:#767676;'>({_d_inj_disp.strftime('%d/%m/%Y')})</span></div>", unsafe_allow_html=True)
                else:
                    st.caption("Aucune.")
            st.caption("Résumé calculé automatiquement à partir des résultats disponibles pour ce joueur — détail complet plus bas sur cette page.")

        # 1. Configuration
        radar_config = [
            {"label": "Vmax", "cols": ["Vmax"]},
            {"label": "Amax", "cols": ["Amax"]},
            {"label": "Dmax", "cols": ["Dmax"]},
            {"label": "Dist. Totale", "cols": ["Distance Totale"]},
            {"label": "Dist. HSR", "cols": ["Distance HSR"]},
            {"label": "Sprint (>92%)", "cols": ["Distance Sprint (92% Vimax)"]}
        ]
        
        # 2. Préparation des données
        row_updated = df[df['Joueur'] == p_sel].iloc[0]
        radar_labels = []
        radar_values = []
        table_rows_data = []

        for item in radar_config:
            radar_labels.append(item['label'])
            sum_p = 0
            count = 0
            
            val_str = "-"
            norm_str = ""
            actual_col_key = item['cols'][0] # On garde la vraie colonne par défaut
            
            for col_key in item['cols']:
                col_name = COL_MAPPING.get(col_key, col_key)
                val = clean_numeric_value(row_updated.get(col_name))
                
                if col_name and val is not None:
                    actual_col_key = col_key # On sauvegarde le VRAI nom trouvé
                    try:
                        _, p = calculate_percentile(df, col_name, val)
                        sum_p += p
                        count += 1
                        
                        unit = UNITS.get(col_key, "")
                        if val > 100: 
                            val_str = f"{int(val)} {unit}"
                        else: 
                            val_str = f"{val:.2f} {unit}"
                        
                        raw_norm = get_norm_text(col_key)
                        if raw_norm != "-":
                            norm_str = raw_norm
                            
                    except: pass
            
            final_score = sum_p / count if count > 0 else 0
            radar_values.append(final_score)
            
            table_rows_data.append({
                "label": item['label'], 
                "actual_col": actual_col_key, 
                "value_display": val_str,
                "norm_display": norm_str,
                "score": int(final_score)
            })

        # 3. Affichage
        c_radar, c_table = st.columns([3, 2])
        
        # ==========================================

        with c_radar:
            import plotly.graph_objects as go
            
            radar_hover_texts = []
            for r_data in table_rows_data:
                lbl = r_data['label']
                actual_lbl = r_data.get('actual_col', lbl) # On utilise le vrai nom
                val_fmt = r_data['value_display']
                norm_txt = r_data['norm_display'].replace('Obj: ', '') if r_data['norm_display'] and r_data['norm_display'] != "()" else "-"
                
                score = r_data.get('score', 0)
                is_empty = score is None or pd.isna(score)
                
                if norm_txt == "-":
                    status_desc = "Pas d'objectif"
                    status_color = "#888"
                else:
                    col_abs = get_col_name(actual_lbl)
                    val_abs = clean_numeric_value(row.get(col_abs))
                    status_res = get_status_data_local(actual_lbl, val_abs)
                    c_stat = status_res[0] if len(status_res) > 0 else "#ccc"
                    if c_stat in ["#27AE60", "#00E5FF"]:
                        status_desc = "🟢"
                        status_color = "#27AE60"
                    else:
                        status_desc = "🔴"
                        status_color = "#D71920"
                
                pct_disp = format_pct_display(score) if not is_empty else "-"
                
                hover_html = (
                    f"<b>{lbl.upper()}</b><br><br>"
                    f"Valeur : <b>{val_fmt}</b><br>"
                    f"Objectif : {norm_txt}<br>"
                    f"Statut : <span style='color:{status_color}; font-weight:bold;'>{status_desc}</span><br>"
                    f"Classement : <b>{pct_disp}</b>"
                )
                radar_hover_texts.append(hover_html)
                
            if radar_labels:
                fig_main_radar = build_radar(
                    radar_labels,
                    [{
                        "name": "Profil",
                        "values": radar_values,
                        "color": "#423D3D",
                        "fill_opacity": 0.4,
                        "width": 2,
                        "hovertext": radar_hover_texts,
                    }],
                    zones=[
                        (33, 'rgba(215, 25, 32, 0.15)'),   # Zone 0-33 (Rouge - Flop)
                        (66, None),                         # Limite 33-66 (Moyen - fond transparent)
                        (95, 'rgba(39, 174, 96, 0.15)'),    # Zone 66-95 (Vert - Top)
                        (100, 'rgba(0, 229, 255, 0.15)'),   # Zone 95-100 (Bleu - Élite)
                    ],
                    radial_tickvals=[33, 66, 100],
                    radial_ticktext=["33", "66", ""],
                    tick_font_size=11,
                    grid_color="#ccc",
                    legend=False,
                    height=380,
                )

                st.plotly_chart(fig_main_radar, width='stretch', config={'displayModeBar': False})

        with c_table:
            st.markdown("""
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; padding:0 5px; border-bottom:2px solid #eee; padding-bottom:5px;'>
                <span style='color:#555; font-size:12px; font-weight:bold; letter-spacing:1px;'>INDICATEURS CLÉS</span>
                <span style='color:#777; font-size:10px; display:flex; align-items:center;'>
                    SCORE (PERCENTILE) &nbsp;
                    <span title="Le score sur 100 représente le classement du joueur par rapport au reste du groupe." style="cursor:help; font-size:14px;">ℹ️</span>
                </span>
            </div>
            """, unsafe_allow_html=True)

            html_content = "<div style='display:flex; flex-direction:column; gap:10px; margin-bottom:20px; width: 100%;'>"
            
            for row_data in table_rows_data:
                label = row_data['label']
                actual_lbl = row_data.get('actual_col', label)
                score = row_data.get('score', None)
                
                if score is None or pd.isna(score):
                    pct_color = "#eee"
                    pct_html = "<div style='color:#666; font-weight:bold; font-size:12px;'>-</div>"
                else:
                    pct_color = "#00E5FF" if score >= 95 else "#27AE60" if score >= 66 else "#F39C12" if score >= 33 else "#D71920"
                    score_txt = format_pct_display(score)
                    pct_html = f"<div style='color:{pct_color}; font-weight:900; font-size:13px;'>{score_txt}</div>"
                
                val_disp = row_data.get('value_display', '-')
                norm_disp = row_data.get('norm_display', '-')
                
                col_abs_name = get_col_name(actual_lbl)
                date_val = format_date_str(row.get(f"{col_abs_name}_date", ""))
                date_html = f"<div style='font-size:10px; color:#707070; font-style:italic; font-weight:normal; text-transform:none; margin-top:2px;'>{date_val}</div>" if date_val else ""
                
                if norm_disp in ["-", "()", ""]:
                    norm_color = "#eee"
                    status_text = "Pas d'objectif"
                    norm_tooltip = "Aucun objectif défini"
                else:
                    val_abs_ref = clean_numeric_value(row.get(col_abs_name))
                    status_res = get_status_data_local(actual_lbl, val_abs_ref)
                    c_stat = status_res[0] if len(status_res) > 0 else "#111"
                    
                    if c_stat in ["#27AE60", "#00E5FF"]:
                        norm_color = "#27AE60"
                        status_text = "🟢"
                    else:
                        norm_color = "#D71920"
                        status_text = "🔴"
                    
                    norm_tooltip = f"📅 {date_val} | " + norm_disp if date_val else norm_disp

                val_color = "#111"

                html_content += (
                    f"<div style='width: 100%; background-color:#fff; border-radius:8px; padding:12px 15px; border:1px solid #eee; border-left:6px solid {norm_color}; border-right:6px solid {pct_color}; box-shadow: 0 2px 5px rgba(0,0,0,0.03); display:flex; align-items:center; justify-content:space-between;'>"
                    f"<div style='flex:1.2;'>"
                    f"<div style='color:#333; font-weight:900; font-size:13px; text-transform:uppercase;'>{label}{date_html}</div>"
                    f"</div>"
                    f"<div style='flex:1; text-align:center;'>"
                    f"<div style='font-size:22px; font-weight:900; color:{val_color}; line-height:1;'>{val_disp}</div>"
                    f"</div>"
                    f"<div style='flex:1.8; display:flex; justify-content:space-between; border-left:1px solid #f0f0f0; padding-left:15px;'>"
                    f"<div style='text-align:left;'>"
                    f"<div style='font-size:9px; color:#707070; font-weight:bold; text-transform:uppercase;'>Statut</div>"
                    f"<div style='font-size:11px; font-weight:bold; color:{norm_color}; cursor:help;' title='{norm_tooltip}'>{status_text} <span style='font-size:9px;'>ℹ️</span></div>"
                    f"</div>"
                    f"<div style='text-align:right;'>"
                    f"<div style='font-size:9px; color:#707070; font-weight:bold; text-transform:uppercase;'>Class.</div>"
                    f"{pct_html}"
                    f"</div>"
                    f"</div>"
                    f"</div>"
                )

            html_content += "</div>"
            st.markdown(html_content, unsafe_allow_html=True)

        use_relative = st.session_state.get("use_relative_mode", False)

        st.markdown("""
        <div style="background-color: #f9f9f9; padding: 15px; border-radius: 8px; border: 1px solid #eee; margin-top: 20px; margin-bottom: 30px; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 20px;">
            <div>
                <div style="font-weight: 900; color: #555; font-size: 11px; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 1px;"> Par rapport à l'Objectif</div>
                <div style="display: flex; gap: 15px; font-size: 13px; font-weight: bold;">
                    <span style="color: #27AE60;">🟢 Objectif Atteint</span>
                    <span style="color: #D71920;">🔴 Sous l'objectif</span>
                </div>
            </div>
            <div style="border-left: 2px dashed #ddd; padding-left: 20px;">
                <div style="font-weight: 900; color: #555; font-size: 11px; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 1px;"> Par rapport au Groupe (Classement)</div>
                <div style="display: flex; gap: 15px; font-size: 13px; font-weight: bold;">
                    <span style="color: #00E5FF;">🔵 Élite (Top 5%)</span>
                    <span style="color: #27AE60;">🟢 Bon (Top 34%)</span>
                    <span style="color: #F39C12;">🟠 Moyen (33-66%)</span>
                    <span style="color: #D71920;">🔴 Axe de travail (< 33%)</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        def get_data_smart(label, use_rel_mode):
            """
            Récupère intelligemment les données (Absolues ou Relatives) pour un indicateur.
            Retourne : (Valeur, Colonne_utilisée_pour_percentile, Unité, Label_Secondaire, Mode)
            """
            col_abs = get_col_name(label)
            val_abs = clean_numeric_value(row.get(col_abs))
            unit_abs = get_unit(label)
            
            # Insensible à la casse (gère "Kg" et "kg")
            unit_abs_lower = unit_abs.lower()
            
            # --- INTERCEPTION VITESSES (Nouveauté) ---
            is_speed = (any(x in unit_abs_lower for x in ["m/s", "km/h"]) or any(x in label.lower() for x in ["vmax", "v0", "speed"])) and "²" not in unit_abs_lower
            
            if is_speed and val_abs is not None:
                # Si > 15, physiquement c'est du km/h. Sinon, c'est du m/s.
                is_kmh_native = val_abs > 15 or "km/h" in unit_abs_lower
                
                val_kmh = val_abs if is_kmh_native else val_abs * 3.6
                val_ms = val_abs / 3.6 if is_kmh_native else val_abs
                
                show_ms = st.session_state.get("show_ms_global", False)
                
                # Application de la bascule
                val_final = val_ms if show_ms else val_kmh
                unit_final = "m/s" if show_ms else "km/h"
                sub_txt = f"{val_kmh:.1f} km/h" if show_ms else f"{val_ms:.2f} m/s"
                
                _, pct = calculate_percentile(df, col_abs, val_abs)
                return val_final, pct, unit_final, sub_txt, "abs"

            is_force_or_power = any(u in unit_abs_lower for u in ["n", "w", "kg"]) and "cm" not in unit_abs_lower and "s" not in unit_abs_lower

            # MODE ABSOLU
            if not use_rel_mode or not is_force_or_power or val_abs is None:
                _, pct = calculate_percentile(df, col_abs, val_abs)
                rel_txt = get_rel_display_smart(row, label, val_abs, poids_joueur)
                
                # AJOUT : Conversion automatique m/s -> km/h
                if unit_abs_lower == "m/s" and val_abs is not None:
                    rel_txt = f"{val_abs * 3.6:.1f} km/h"
                    
                return val_abs, pct, unit_abs, rel_txt, "abs"

            # MODE RELATIF
            # On cherche D'ABORD si la colonne existe dans ton dictionnaire REL_COL_MAPPING
            col_rel = get_rel_col_name(label)
            if col_rel not in df.columns:
                col_rel = None
            
            # Si pas trouvée dans le dictionnaire, on devine le suffixe
            if not col_rel:
                potential_suffixes = [" (N/kg)", " (W/kg)", " (kg/kg)", " (Kg/kg)", " N/kg", " W/kg", " kg/kg", " Kg/kg", " (Relatif)", " Relatif"]
                for suff in potential_suffixes:
                    candidate = col_abs + suff
                    if candidate in df.columns:
                        col_rel = candidate
                        break
                
                if not col_rel and "(" in col_abs:
                    base = col_abs.split("(")[0].strip()
                    for suff in potential_suffixes:
                        candidate = base + suff
                        if candidate in df.columns:
                            col_rel = candidate
                            break

            # 2. Utilisation de la colonne relative trouvée
            if col_rel:
                val_rel = clean_numeric_value(row.get(col_rel))
                _, pct_rel = calculate_percentile(df, col_rel, val_rel)
                unit_rel = "N/kg" if "n" in unit_abs_lower else "W/kg" if "w" in unit_abs_lower else "kg/kg" if "kg" in unit_abs_lower else "ratio"
                sub_txt = f"{smart_format(val_abs)} {unit_abs}"
                return val_rel, pct_rel, unit_rel, sub_txt, "rel"

            # 3. Calcul manuel si aucune colonne relative n'est trouvée
            elif poids_joueur and poids_joueur > 0 and val_abs is not None:
                val_rel = val_abs / poids_joueur
                unit_rel = "N/kg" if "n" in unit_abs_lower else "W/kg" if "w" in unit_abs_lower else "kg/kg" if "kg" in unit_abs_lower else "ratio"
                col_poids_name = find_column_in_df(df, "Poids")
                
                if col_poids_name:
                    try:
                        series_perf = pd.to_numeric(df[col_abs], errors='coerce')
                        series_poids = pd.to_numeric(df[col_poids_name], errors='coerce')
                        
                        serie_rel = series_perf / series_poids.replace(0, np.nan)
                        
                        clean_series = serie_rel.dropna()
                        # percentileofscore renvoie NaN sur une série vide
                        # (ex: poids manquant chez tout le groupe de
                        # comparaison) -> plantait plus loin (int(NaN)) dans
                        # les cartes qui affichent ce percentile.
                        pct_rel = stats.percentileofscore(clean_series, val_rel, kind='weak') if not clean_series.empty else 0

                        sub_txt = f"{smart_format(val_abs)} {unit_abs}"
                        return val_rel, pct_rel, unit_rel, sub_txt, "rel"
                    except Exception:
                        pass 

            # Repli sur le mode absolu si le calcul relatif échoue
            _, pct = calculate_percentile(df, col_abs, val_abs)
            return val_abs, pct, unit_abs, None, "abs"


        def render_single_kpi(label, subtitle=None, mode_override=None):
            effective_mode = mode_override if mode_override is not None else use_relative
            val, pct, unit, sub_text, mode = get_data_smart(label, effective_mode)
            is_empty = val is None or pd.isna(val) or val == "" or str(val).strip() == "-"
            
            unit_display = unit if not is_empty else ""
            pct_color = "#eee"
            pct_html = '<div style="font-size:13px; font-weight:900; color:#666;">-</div>'
            
            if is_empty:
                norm_color, status_text, norm_tooltip = "#eee", "Pas d'objectif", "Aucune donnée disponible"
            elif label in TARGET_MEDIAN_TESTS:
                col_name = TARGET_MEDIAN_TESTS[label]
                median_val = pd.to_numeric(df[col_name], errors='coerce').median()
                if not is_empty and val >= median_val:
                    norm_color, status_text, norm_tooltip = "#27AE60", "🟢", f"Valeur: {val:.2f} | Médiane: {median_val:.2f}"
                else:
                    norm_color, status_text, norm_tooltip = "#D71920", "🔴", f"Valeur: {val:.2f} | Médiane: {median_val:.2f}"
            else:
                norm_txt_raw = get_norm_text(label, effective_mode, poids_joueur, poste_groupe_norme).replace('Obj: ', '')
                status_res = get_status_data_local(label, val, effective_mode, poids_joueur, poste_groupe_norme)
                norm_color = status_res[0] if len(status_res) > 0 else "#eee"
                status_text = "🟢" if norm_color == "#27AE60" else "🔴"
                norm_tooltip = f"Objectif : {norm_txt_raw}".strip()
                if label in REPORT_NORMES_PAR_POSTE and poste_groupe_norme in REPORT_NORMES_PAR_POSTE.get(label, {}):
                    norm_tooltip += f" (norme {poste_groupe_norme.lower()})"

            if not is_empty and pct is not None and not pd.isna(pct):
                pct_color = get_bar_color(pct)
                pct_text = format_pct_display(pct)
                pct_html = f'<div style="font-size:13px; font-weight:900; color:{pct_color};">{pct_text}</div>'

            val_display = f"{smart_format(val)}" if not is_empty else "-"
            
            # --- DATE EN HAUT A DROITE ---
            col_abs = get_col_name(label)
            date_val = format_date_str(row.get(f"{col_abs}_date", ""))
            
            # Annotation glossaire (CMJ, RSI, RFD, DSI...) : survol du sigle
            # -> définition, sans changer visuellement la carte (juste un
            # discret soulignement pointillé, cf. glossary.py).
            display_label = annotate_glossary_terms(label)
            if date_val:
                display_label = f"{display_label} <span style='float:right; font-size:10px; color:#707070; font-weight:normal; font-style:italic; text-transform:none;'>{date_val}</span>"
                norm_tooltip = f"📅 {date_val} | " + norm_tooltip
                
            sub_title_html = f" <span style='font-size:11px; color:#707070; font-style:italic; text-transform:none;'>{subtitle}</span>" if subtitle else ""
            tip = get_tooltip_html(row, label)

            html_str = get_kpi_card_html(
                label=display_label, 
                val_display=val_display, 
                unit_display=unit_display, 
                norm_color=norm_color, 
                pct_color=pct_color, 
                pct_html=pct_html, 
                status_text=status_text, 
                norm_tooltip=norm_tooltip, 
                tip=tip, 
                subtitle_html=sub_title_html
            )
            st.markdown(html_str, unsafe_allow_html=True)

        def render_pair_kpi(l_label, r_label, mode_override=None):
            clean_lbl = get_clean_label(l_label)
            found_key = next((k for k in REPORT_NORMES.keys() if k in clean_lbl), None)
            norm_val = REPORT_NORMES.get(found_key) if found_key else None
            
            force_relative = use_relative
            if norm_val is not None and isinstance(norm_val, (int, float)) and norm_val < 30:
                force_relative = True

            effective_mode = mode_override if mode_override is not None else force_relative

            val_l, pct_l, unit_l, sub_l, _ = get_data_smart(l_label, effective_mode)
            val_r, pct_r, unit_r, sub_r, _ = get_data_smart(r_label, effective_mode)
            
            col_l_abs, col_r_abs = get_col_name(l_label), get_col_name(r_label)
            val_l_abs, val_r_abs = clean_numeric_value(row.get(col_l_abs)), clean_numeric_value(row.get(col_r_abs))
            asym_pct, weak_side = get_asym_badge_info(val_l_abs, val_r_abs, df, col_l_abs, col_r_abs)
            
            asym_html = ""
            if asym_pct is not None:
                if asym_pct < 10:
                    asym_html = f"<div style='background:rgba(39, 174, 96, 0.1); border:1px solid #27AE60; color:#27AE60; padding:4px 10px; border-radius:4px; font-size:11px; font-weight:bold;'>Équilibré ({asym_pct:.0f}%)</div>"
                elif 10 <= asym_pct < 15:
                    asym_html = f"<div style='background:rgba(243, 156, 18, 0.1); border:1px solid #F39C12; color:#F39C12; padding:4px 10px; border-radius:4px; font-size:11px; font-weight:bold;'>⚠ Déficit {weak_side} ({asym_pct:.0f}%)</div>"
                else:
                    asym_html = f"<div style='background:rgba(215, 25, 32, 0.1); border:1px solid #D71920; color:#D71920; padding:4px 10px; border-radius:4px; font-size:11px; font-weight:bold;'>🔴 Déficit {weak_side} ({asym_pct:.0f}%)</div>"

            def get_side_html(label, val, pct, unit, side_name, side_color):
                is_empty = val is None or pd.isna(val) or val == "" or str(val).strip() == "-"
                display_val = f"{smart_format(val)}" if not is_empty else "-"
                display_unit = unit if not is_empty else ""
                norm_txt_raw = "-"
                status_color = "#eee"
                
                # --- FORMATAGE DE LA DATE : On garde que YYYY-MM-DD ---
                col_abs = get_col_name(label)
                raw_date = row.get(f"{col_abs}_date", "")
                date_val = str(raw_date).split()[0] if raw_date and str(raw_date).strip() != "-" else ""
                
                # Positionnement en haut à droite avec "position:absolute"
                date_html = f"<span style='position:absolute; top:-2px; right:0px; font-size:9px; color:#707070; font-style:italic; font-weight:normal;'>{date_val}</span>" if date_val else ""

                if not is_empty:
                    norm_txt_raw = get_norm_text(label, effective_mode, poids_joueur).replace('Obj: ', '')
                    if date_val:
                        norm_txt_raw = f"📅 {date_val} | " + norm_txt_raw
                    status_res = get_status_data_local(label, val, effective_mode, poids_joueur)
                    status_color = status_res[0] if len(status_res) > 0 else "#eee"
                        
                pct_color = get_bar_color(pct) if not is_empty and pct is not None else "#eee"
                pct_text = format_pct_display(pct) if not is_empty and pct is not None else "-"
                
                return (
                    f"<div style='flex:1; padding:10px; border-radius:8px; border:1px solid #eee; border-top:4px solid {side_color}; background:#fafafa; margin:0 5px;'>"
                    f"<div style='text-align:center; font-weight:900; color:{side_color}; margin-bottom:10px; font-size:14px; position:relative;'>{side_name} {date_html}</div>"
                    f"<div style='text-align:center; margin-bottom:15px;'>"
                    f"<div style='font-size:26px; font-weight:900; color:#111; line-height:1;'>{display_val} <span style='font-size:12px; color:#666;'>{display_unit}</span></div>"
                    f"</div>"
                    f"<div style='display:flex; justify-content:space-between; align-items:flex-end; border-top:1px solid #eee; padding-top:8px;'>"
                    f"<div style='text-align:left;'>"
                    f"<div style='font-size:9px; color:#707070; text-transform:uppercase; font-weight:bold;'>Objectif</div>"
                    f"<div style='width:12px; height:12px; border-radius:50%; background:{status_color}; margin-top:2px;' title='{norm_txt_raw}'></div>"
                    f"</div>"
                    f"<div style='text-align:right;'>"
                    f"<div style='font-size:9px; color:#707070; text-transform:uppercase; font-weight:bold;'>Class.</div>"
                    f"<div style='font-size:12px; font-weight:900; color:{pct_color};'>{pct_text}</div>"
                    f"</div>"
                    f"</div>"
                    f"</div>"
                )

            clean_title = get_clean_label(l_label)
            html_str = (
                f"<div class='kpi-card' style='width: 100%; padding: 15px; margin-bottom: 20px; background: white; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 4px 10px rgba(0,0,0,0.05);'>"
                f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; border-bottom:1px solid #eee; padding-bottom:8px;'>"
                f"<div style='font-size:16px; font-weight:900; color:black; text-transform:uppercase;'>{clean_title}</div>"
                f"{asym_html}"
                f"</div>"
                f"<div style='display:flex; justify-content:space-between; margin:0 -5px;'>"
                f"{get_side_html(l_label, val_l, pct_l, unit_l, 'GAUCHE', '#3498db')}"
                f"{get_side_html(r_label, val_r, pct_r, unit_r, 'DROITE', '#e74c3c')}"
                f"</div>"
                f"</div>"
            )
            st.markdown(html_str, unsafe_allow_html=True)

        

        def render_wellness_combined():
            val_s = clean_numeric_value(row.get("Score Sommeil"))
            _, pct_s = calculate_percentile(df, "Score Sommeil", val_s)
            col_s = get_bar_color(pct_s)
            
            val_n = clean_numeric_value(row.get("Score Nutrition"))
            _, pct_n = calculate_percentile(df, "Score Nutrition", val_n)
            col_n = get_bar_color(pct_n)

            st.markdown(f"""
<div class="kpi-card" style="padding:20px; background:#fff; border-radius:10px; border:1px solid #eee; margin-bottom:20px;">
<div class="kpi-lbl" style="font-size:18px; font-weight:900; color:{SDR_RED}; text-transform:uppercase; margin-bottom:15px; border-bottom:2px solid #eee; padding-bottom:10px;">BIEN-ÊTRE & RÉCUPÉRATION</div>
<div style="display:flex; gap:30px;">
<div style="flex:1;">
<div style="display:flex; align-items:center; margin-bottom:10px;">
<span style="font-size:24px; margin-right:10px;">💤</span>
<div>
<div style="font-size:14px; color:#666; font-weight:bold;">SOMMEIL</div>
<div style="font-size:32px; font-weight:bold; color:#111; line-height:1;">{smart_format(val_s)}<span style="font-size:16px; color:#666;">/10</span></div>
</div>
</div>
<div class="progress-bg" style="height:12px; margin-bottom:5px;">
<div style="width:{max(5, int(pct_s))}%; height:100%; background:{col_s}; border-radius:6px;"></div>
</div>
<div style="text-align:right; font-size:12px; font-weight:bold; color:{col_s};">Meilleur que {int(pct_s)}% de l'équipe</div>
</div>
<div style="width:1px; background:#eee;"></div>
<div style="flex:1;">
<div style="display:flex; align-items:center; margin-bottom:10px;">
<span style="font-size:24px; margin-right:10px;">🥦</span>
<div>
<div style="font-size:14px; color:#666; font-weight:bold;">NUTRITION</div>
<div style="font-size:32px; font-weight:bold; color:#111; line-height:1;">{smart_format(val_n)}<span style="font-size:16px; color:#666;">/12</span></div>
</div>
</div>
<div class="progress-bg" style="height:12px; margin-bottom:5px;">
<div style="width:{max(5, int(pct_n))}%; height:100%; background:{col_n}; border-radius:6px;"></div>
</div>
<div style="text-align:right; font-size:12px; font-weight:bold; color:{col_n};">Meilleur que {int(pct_n)}% de l'équipe</div>
</div>
</div>
</div>""", unsafe_allow_html=True)

        def render_subheader(title):
            st.markdown(f"<div style='color:{SDR_RED}; font-size:15px; font-weight:900; margin-top:20px; margin-bottom:10px; border-left:4px solid {SDR_RED}; padding-left:10px; text-transform:uppercase;'>{title}</div>", unsafe_allow_html=True)

        def render_muscle_group_card(title_main, l_label, r_label, sum_label):
            effective_mode = use_relative

            val_l, pct_l, unit_l, sub_l, _ = get_data_smart(l_label, effective_mode)
            val_r, pct_r, unit_r, sub_r, _ = get_data_smart(r_label, effective_mode)
            val_s, pct_s, unit_s, sub_s, _ = get_data_smart(sum_label, effective_mode)
            # Filet de sécurité : en mode "valeurs relatives", le percentile
            # (stats.percentileofscore) peut renvoyer NaN sur un cas
            # dégénéré (série vide après nettoyage, poids manquant...).
            # int(NaN) plante -- on retombe sur 0 (barre vide) plutôt que de
            # faire planter tout l'onglet.
            pct_l = 0 if pd.isna(pct_l) else pct_l
            pct_r = 0 if pd.isna(pct_r) else pct_r
            pct_s = 0 if pd.isna(pct_s) else pct_s

            txt_l = get_status_data_local(l_label, clean_numeric_value(row.get(get_col_name(l_label))))[2] if len(get_status_data_local(l_label, 0))==3 else "#111"
            txt_r = get_status_data_local(r_label, clean_numeric_value(row.get(get_col_name(r_label))))[2] if len(get_status_data_local(r_label, 0))==3 else "#111"
            txt_s = get_status_data_local(sum_label, clean_numeric_value(row.get(get_col_name(sum_label))))[2] if len(get_status_data_local(sum_label, 0))==3 else "#111"
            
            norm_s = get_norm_text(sum_label).replace('Obj: ', '')
            asym_pct, weak_side = get_asym_badge_info(clean_numeric_value(row.get(get_col_name(l_label))), clean_numeric_value(row.get(get_col_name(r_label))), df, get_col_name(l_label), get_col_name(r_label))
            
            # --- DATE PROPRE ---
            date_l = format_date_str(row.get(f"{get_col_name(l_label)}_date", ""))
            dl_html = f" <span style='font-size:10px; color:#707070; font-weight:normal; font-style:italic; margin-left:5px;'>{date_l}</span>" if date_l else ""
            
            date_r = format_date_str(row.get(f"{get_col_name(r_label)}_date", ""))
            dr_html = f" <span style='font-size:10px; color:#707070; font-weight:normal; font-style:italic; margin-left:5px;'>{date_r}</span>" if date_r else ""

            date_s = format_date_str(row.get(f"{get_col_name(sum_label)}_date", ""))
            ds_html = f" <span style='font-size:11px; color:#707070; font-weight:normal; font-style:italic; margin-left:8px;'>{date_s}</span>" if date_s else ""
            
            if date_s: norm_s = f"📅 {date_s} | " + norm_s

            asym_html = ""
            if asym_pct is not None:
                if asym_pct < 10: asym_html = f"<div style='background:rgba(39, 174, 96, 0.1); border:1px solid #27AE60; color:#27AE60; padding:6px; border-radius:6px; font-size:12px; font-weight:bold; text-align:center; margin-bottom:12px;'>Équilibré ({asym_pct:.0f}%)</div>"
                elif 10 <= asym_pct < 15: asym_html = f"<div style='background:rgba(243, 156, 18, 0.1); border:1px solid #F39C12; color:#F39C12; padding:6px; border-radius:6px; font-size:12px; font-weight:bold; text-align:center; margin-bottom:12px;'>⚠ Attention {weak_side} ({asym_pct:.0f}%)</div>"
                else: asym_html = f"<div style='background:rgba(215, 25, 32, 0.1); border:1px solid #D71920; color:#D71920; padding:6px; border-radius:6px; font-size:12px; font-weight:bold; text-align:center; margin-bottom:12px;'>Déficit {weak_side} ({asym_pct:.0f}%)</div>"

            st.markdown (f"""
<div class="kpi-card">
<div class="kpi-lbl" style="font-size:16px; font-weight:bold; color:#333; text-transform:uppercase; letter-spacing:1px; margin-bottom:12px; border-bottom:1px solid #eee; padding-bottom:5px;">{title_main}</div>
{asym_html}
<div style="background:#f9f9f9; padding:10px; border-radius:8px; margin-bottom:12px; border:1px solid #eee;">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
<span style="color:#3498db; font-weight:900;">G {dl_html}</span>
<span style="font-size:16px; font-weight:bold; color:{txt_l}">{smart_format(val_l)} <span style="font-size:10px; color:#666;">{unit_l}</span></span>
<span style="font-size:10px; background:#fff; color:#555; border:1px solid #ddd; padding:2px 6px; border-radius:3px;">{sub_l if sub_l else '-'}</span>
</div>
<div class="progress-bg" style="margin-top:0; margin-bottom:8px;">
<div style="width:{max(5, int(pct_l))}%; height:100%; background:{get_bar_color(pct_l)}; border-radius:3px;"></div>
</div>
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
<span style="color:#e74c3c; font-weight:900;">D {dr_html}</span>
<span style="font-size:16px; font-weight:bold; color:{txt_r}">{smart_format(val_r)} <span style="font-size:10px; color:#666;">{unit_r}</span></span>
<span style="font-size:10px; background:#fff; color:#555; border:1px solid #ddd; padding:2px 6px; border-radius:3px;">{sub_r if sub_r else '-'}</span>
</div>
<div class="progress-bg" style="margin-top:0;">
<div style="width:{max(5, int(pct_r))}%; height:100%; background:{get_bar_color(pct_r)}; border-radius:3px;"></div>
</div>
</div>
<div style="margin-top:5px; border-top:1px dashed #ccc; padding-top:10px;">
<div style="display:flex; justify-content:space-between; align-items:end; margin-bottom:5px;">
<span style="font-size:12px; font-weight:bold; color:#555;">FORCE TOTALE {ds_html}</span>
<div style="text-align:right; line-height:1.2;">
<div style="font-size:20px; font-weight:900; color:{txt_s};">{smart_format(val_s)} <span style="font-size:12px; color:#666;">{unit_s}</span></div>
<div style="font-size:11px; color:#777; font-weight:bold;">{sub_s if sub_s else '-'}</div>
</div>
</div>
<div style="display:flex; justify-content:space-between; margin-bottom:2px;">
<span style="font-size:11px; color:#666; font-weight:bold;">NORME: <span style="color:#111;">{norm_s}</span></span>
<span style="font-size:11px; color:{get_bar_color(pct_s)}; font-weight:bold;">{format_pct_display(pct_s)}</span>
</div>
<div class="progress-bg" style="margin-top:0;">
<div style="width:{max(5, int(pct_s))}%; height:100%; background:{get_bar_color(pct_s)}; border-radius:4px;"></div>
</div>
</div>
</div>""", unsafe_allow_html=True)

        def render_wellness_combined():
            val_s = clean_numeric_value(row.get("Score Sommeil"))
            _, pct_s = calculate_percentile(df, "Score Sommeil", val_s)
            col_s = get_bar_color(pct_s)
            
            val_n = clean_numeric_value(row.get("Score Nutrition"))
            _, pct_n = calculate_percentile(df, "Score Nutrition", val_n)
            col_n = get_bar_color(pct_n)

            st.markdown(f"""
<div class="kpi-card" style="padding:20px; background:#fff; border-radius:10px; border:1px solid #eee; margin-bottom:20px;">
<div class="kpi-lbl" style="font-size:18px; font-weight:bold; color:#111; text-transform:uppercase; margin-bottom:15px; border-bottom:1px solid #eee; padding-bottom:10px;">BIEN-ÊTRE & RÉCUPÉRATION</div>
<div style="display:flex; gap:30px;">
<div style="flex:1;">
<div style="display:flex; align-items:center; margin-bottom:10px;">
<span style="font-size:24px; margin-right:10px;">💤</span>
<div>
<div style="font-size:14px; color:#666; font-weight:bold;">SOMMEIL</div>
<div style="font-size:32px; font-weight:bold; color:#111; line-height:1;">{smart_format(val_s)}<span style="font-size:16px; color:#666;">/10</span></div>
</div>
</div>
<div class="progress-bg" style="height:12px; margin-bottom:5px;">
<div style="width:{max(5, int(pct_s))}%; height:100%; background:{col_s}; border-radius:6px;"></div>
</div>
<div style="text-align:right; font-size:12px; font-weight:bold; color:{col_s};">Meilleur que {int(pct_s)}% de l'équipe</div>
</div>
<div style="width:1px; background:#eee;"></div>
<div style="flex:1;">
<div style="display:flex; align-items:center; margin-bottom:10px;">
<span style="font-size:24px; margin-right:10px;">🥦</span>
<div>
<div style="font-size:14px; color:#666; font-weight:bold;">NUTRITION</div>
<div style="font-size:32px; font-weight:bold; color:#111; line-height:1;">{smart_format(val_n)}<span style="font-size:16px; color:#666;">/12</span></div>
</div>
</div>
<div class="progress-bg" style="height:12px; margin-bottom:5px;">
<div style="width:{max(5, int(pct_n))}%; height:100%; background:{col_n}; border-radius:6px;"></div>
</div>
<div style="text-align:right; font-size:12px; font-weight:bold; color:{col_n};">Meilleur que {int(pct_n)}% de l'équipe</div>
</div>
</div>
</div>""", unsafe_allow_html=True)

        def render_subheader(title, group_toggle=False):
            if not group_toggle:
                st.markdown(f"<div style='color:#555; font-size:14px; font-weight:bold; margin-top:20px; margin-bottom:10px; border-left:3px solid #E74C3C; padding-left:10px;'>{title}</div>", unsafe_allow_html=True)
                return use_relative

            # --- Bouton de groupe : bascule Absolu/Relatif pour TOUS les KPIs de cette batterie ---
            gkey = f"rel_group_{re.sub(r'[^a-zA-Z0-9]', '_', title)}_{p_sel}"
            if gkey not in st.session_state:
                st.session_state[gkey] = use_relative

            col_t, col_b = st.columns([5, 1])
            with col_t:
                st.markdown(f"<div style='color:#555; font-size:14px; font-weight:bold; margin-top:20px; margin-bottom:10px; border-left:3px solid #E74C3C; padding-left:10px;'>{title}</div>", unsafe_allow_html=True)
            with col_b:
                btn_txt = "⇄ Voir en relatif (/kg)" if not st.session_state[gkey] else "⇄ Voir en absolu"
                if st.button(btn_txt, key=f"btn_{gkey}", help="Basculer Absolu/Relatif pour tous les tests de cette section"):
                    st.session_state[gkey] = not st.session_state[gkey]
                    st.rerun()
            return st.session_state[gkey]

        st.markdown(f"<div class='section-header' style='font-size:22px; margin-top:30px; margin-bottom:10px; border-bottom:2px solid #555; padding-bottom:5px;'>HISTORIQUE & CARTOGRAPHIE MÉDICALE</div>", unsafe_allow_html=True)
        
        c_inj_sel, c_inj_vis = st.columns([1, 1])
        
        df_injuries = load_injury_data()
        p_sel_clean = str(p_sel).strip().lower()
        player_injuries = df_injuries[df_injuries['Joueur'].apply(lambda x: p_sel_clean.startswith(str(x)))]
        
        if not player_injuries.empty:
            injury_counts = player_injuries['Localisation'].value_counts().to_dict()
            details_list = []
            html_injuries = ""
            for _, r in player_injuries.iterrows():
                date_str = str(r['Date'])[:10] if pd.notna(r['Date']) and str(r['Date']).strip() else '?'
                
                duree_val = str(r['Duree']).replace('.0', '').strip() if pd.notna(r['Duree']) else ''
                duree_html = ""
                duree_txt = ""
                
                if duree_val and duree_val.lower() not in ['nan', 'nat', 'none', '', '-']:
                    try:
                        d = float(duree_val)
                        if d <= 14: c_dur = "#27AE60"
                        elif d <= 30: c_dur = "#F39C12"
                        else: c_dur = "#D71920"
                        duree_html = f" <span style='color:{c_dur}; font-weight:900;'>({int(d)}j)</span>"
                    except:
                        duree_html = f" ({duree_val}j)"
                    duree_txt = f" ({duree_val}j)"
                    
                loc = str(r['Localisation']).strip()
                diag = str(r['Detail']).strip()
                
                details_list.append(f"📅 {date_str} | {loc}{duree_txt}\n↳ {diag}")
                html_injuries += f"<div style='margin-bottom:12px; border-bottom:1px dashed #eee; padding-bottom:8px;'><div style='font-size:13px;'><span style='color:#D71920; font-weight:bold;'>📅 {date_str}</span> | <span style='font-weight:bold; color:#333;'>{loc}</span>{duree_html}</div><div style='font-size:11px; color:#666; font-style:italic; margin-top:3px; padding-left:20px;'>↳ {diag}</div></div>"
                
            antecedents_auto = "\n\n".join(details_list)
        else:
            injury_counts = {}
            antecedents_auto = "Aucun antécédent répertorié."
            html_injuries = "<div style='color:#666; font-style:italic; text-align:center; padding-top:20px;'>Aucun antécédent répertorié.</div>"
            
        key_injuries = f"injuries_{p_sel}"
        key_ante = f"ante_{p_sel}"
        
        st.session_state[key_injuries] = injury_counts
        st.session_state[key_ante] = antecedents_auto

        with c_inj_sel:
            st.markdown("<div style='font-weight:bold; color:#444; margin-bottom:5px; text-transform:uppercase;'>Compte-rendu Clinique :</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='height:400px; overflow-y:auto; background:#fff; padding:15px; border-radius:8px; border:1px solid #eee; box-shadow:inset 0 2px 4px rgba(0,0,0,0.02);'>{html_injuries}</div>", unsafe_allow_html=True)

        
        with c_inj_vis:
            body_svg_code = generate_heatmap_body_svg(injury_counts)
            st.components.v1.html(body_svg_code, height=450)

        

# ==========================================
        # NUTRITION & COMPOSITION CORPORELLE (ISAK)
        # ==========================================
        st.markdown(f"<div class='section-header' style='font-size:22px; margin-top:40px; margin-bottom:10px; border-bottom:2px solid #555; padding-bottom:5px;'>COMPOSITION CORPORELLE (ISAK)</div>", unsafe_allow_html=True)
        
        # --- 1. VUE PRINCIPALE : TOILE D'ARAIGNÉE ET SOMATOTYPE ---
        c_nutri1, c_nutri2 = st.columns([1, 1])
        
        with c_nutri1:
            st.markdown("<div style='text-align:center; font-weight:bold; font-size:14px; margin-bottom:10px; color:#333; text-transform:uppercase;'>Cartographie des 8 Plis (mm)</div>", unsafe_allow_html=True)
            
            plis_labels = ["Triceps", "Subscapulaire", "Biceps", "Crête iliaque", "Supraspinale", "Abdominal", "Cuisse ISAK", "Jambe ISAK"]
            plis_display_labels = ["Triceps", "Subscapulaire", "Biceps", "Crête iliaque", "Supraspinale", "Abdominal", "Cuisse", "Jambe"]
            plis_vals = [clean_numeric_value(row.get(get_col_name(l))) for l in plis_labels]
            
            plis_vals_clean = [v if v is not None else 0 for v in plis_vals]
            somme_plis = sum(plis_vals_clean)
            
            import plotly.graph_objects as go
            
            if somme_plis > 0:
                plis_closed = plis_vals_clean + [plis_vals_clean[0]]
                labels_closed = plis_display_labels + [plis_display_labels[0]]
                
                fig_plis = go.Figure()
                fig_plis.add_trace(go.Scatterpolar(
                    r=plis_closed, theta=labels_closed, fill='toself', name=p_sel,
                    line=dict(color="#D71920", width=2), marker=dict(size=6, color="#D71920"),
                    fillcolor='rgba(215, 25, 32, 0.2)'
                ))
                fig_plis.update_layout(
                    polar=dict(
                        radialaxis=dict(
                            visible=True, 
                            range=[0, 15],         # <--- C'est ICI qu'on fixe l'échelle !
                            gridcolor="#eee"
                        ),
                        angularaxis=dict(
                            tickfont=dict(size=11, weight="bold"), 
                            gridcolor="#eee"
                        )
                    ),
                    showlegend=False, 
                    height=350, 
                    margin=dict(l=40, r=40, t=20, b=20), 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_plis, width='stretch', config={'displayModeBar': False})
                st.markdown(f"<div style='text-align:center; font-size:16px; font-weight:900; color:{SDR_RED};'>SOMME DES 8 PLIS : {somme_plis:.1f} mm</div>", unsafe_allow_html=True)
            else:
                st.info("Plis cutanés non renseignés.")

        with c_nutri2:
            st.markdown("<div style='text-align:center; font-weight:bold; font-size:14px; margin-bottom:10px; color:#333; text-transform:uppercase;'>Somatotype</div>", unsafe_allow_html=True)
            
            endo = clean_numeric_value(row.get(get_col_name("Endomorphie"))) or 0
            meso = clean_numeric_value(row.get(get_col_name("Mésomorphie"))) or 0
            ecto = clean_numeric_value(row.get(get_col_name("Éctomorphie"))) or 0
            
            if endo > 0 or meso > 0 or ecto > 0:
                fig_soma = go.Figure(go.Scatterternary({
                    'mode': 'markers', 'a': [endo], 'b': [meso], 'c': [ecto],
                    'marker': {'color': '#1E3A8A', 'size': 14, 'line': {'width': 2, 'color': 'white'}},
                    'hovertemplate': f"<b>{p_sel}</b><br>Endo: {endo}<br>Meso: {meso}<br>Ecto: {ecto}<extra></extra>"
                }))
                fig_soma.update_layout({
                    'ternary': {
                        'sum': endo + meso + ecto,
                        'aaxis': {'title': 'Endomorphie', 'min': 0, 'linewidth': 2, 'ticks': 'outside'},
                        'baxis': {'title': 'Mésomorphie', 'min': 0, 'linewidth': 2, 'ticks': 'outside'},
                        'caxis': {'title': 'Ectomorphie', 'min': 0, 'linewidth': 2, 'ticks': 'outside'}
                    },
                    'height': 350, 'margin': dict(l=20, r=20, t=30, b=20), 'paper_bgcolor': 'rgba(0,0,0,0)'
                })
                st.plotly_chart(fig_soma, width='stretch', config={'displayModeBar': False})
            else:
                st.info("Données de Somatotype incomplètes. Ajoutez Endomorphie, Mésomorphie et Éctomorphie dans l'Excel.")

        # --- 2. VUE DÉTAILLÉE : KPIs ET CAMEMBERT ---
        with st.expander("📊 ANALYSE DÉTAILLÉE & FRACTIONNEMENT TISSULAIRE", expanded=False):
            st.markdown("<div style='font-size:14px; font-weight:bold; color:#555; text-transform:uppercase; margin-bottom:15px;'>Indicateurs des Plis Cutanés (mm)</div>", unsafe_allow_html=True)
            
            c_pli1, c_pli2, c_pli3, c_pli4 = st.columns(4)
            with c_pli1: render_single_kpi("Triceps")
            with c_pli2: render_single_kpi("Subscapulaire")
            with c_pli3: render_single_kpi("Biceps")
            with c_pli4: render_single_kpi("Crête iliaque")
            
            c_pli5, c_pli6, c_pli7, c_pli8 = st.columns(4)
            with c_pli5: render_single_kpi("Supraspinale")
            with c_pli6: render_single_kpi("Abdominal")
            with c_pli7: render_single_kpi("Cuisse ISAK")
            with c_pli8: render_single_kpi("Jambe ISAK")

            st.markdown("<hr style='border:1px dashed #eee;'>", unsafe_allow_html=True)
            st.markdown("<div style='text-align:center; font-weight:bold; font-size:16px; margin-top:20px; color:#333; text-transform:uppercase;'>Fractionnement Tissulaire</div>", unsafe_allow_html=True)
            
            adip = clean_numeric_value(row.get(get_col_name("Tissu Adipeux"))) or 0
            musc = clean_numeric_value(row.get(get_col_name("Tissu Musculaire"))) or 0
            osse = clean_numeric_value(row.get(get_col_name("Tissu Osseux"))) or 0
            resi = clean_numeric_value(row.get(get_col_name("Tissu Résiduel"))) or 0
            
            if sum([adip, musc, osse, resi]) > 0:
                fig_pie = go.Figure(data=[go.Pie(
                    labels=['Tissu Musculaire', 'Tissu Adipeux', 'Tissu Osseux', 'Tissu Résiduel'], 
                    values=[musc, adip, osse, resi], hole=.4,
                    marker=dict(colors=['#D71920', '#F39C12', '#BDC3C7', '#34495E'], line=dict(color='#FFFFFF', width=2)),
                    textinfo='label+percent', textposition='outside'
                )])
                fig_pie.update_layout(showlegend=False, height=400, margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, width='stretch', config={'displayModeBar': False})
            else:
                st.info("Données tissulaires incomplètes. Ajoutez Tissu Adipeux, Musculaire, Osseux et Résiduel dans l'Excel.")

# PROFILAGE MOTEUR 
        st.markdown(f"<div class='section-header' style='font-size:22px; margin-top:30px; margin-bottom:10px; border-bottom:2px solid #555; padding-bottom:5px;'>KINÉ</div>", unsafe_allow_html=True)
        render_subheader("MOBILITÉ")
        render_single_kpi("Sit And Reach")
        render_pair_kpi("Knee To Wall (G)", "Knee To Wall (D)")

        render_subheader("ADDUCTEURS & ABDUCTEURS")
        c_add, c_sq, c_abd = st.columns([1.3, 0.7, 1.3])
        with c_add: render_muscle_group_card("ADDUCTEURS", "Adducteurs (G)", "Adducteurs (D)", "Somme ADD")
        with c_sq: 
            st.markdown("<br><br>", unsafe_allow_html=True)
            render_single_kpi("Ratio Squeeze")
        with c_abd: render_muscle_group_card("ABDUCTEURS", "Abducteurs (G)", "Abducteurs (D)", "Somme ABD")

        mode_ischio = render_subheader("ISCHIO-JAMBIERS", group_toggle=True)
        render_pair_kpi("Nordic Ischio (G)", "Nordic Ischio (D)", mode_override=mode_ischio)
        
        render_subheader("MOLLETS")
        render_pair_kpi("Endurance Heel Raise (G)", "Endurance Heel Raise (D)")


        mode_pieds = render_subheader("PIEDS", group_toggle=True)
        c_ped1, c_ped2 = st.columns(2)
        with c_ped1 : render_pair_kpi("Inverseur (G)", "Inverseur (D)", mode_override=mode_pieds)
        with c_ped2: render_pair_kpi("Everseur (G)", "Everseur (D)", mode_override=mode_pieds)
         

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-bottom:15px; font-size:18px; font-weight:900; color:{SDR_RED}; border-bottom:2px solid {SDR_RED}; padding-bottom:5px; text-transform:uppercase;'>RADAR BIODEX (VALEURS RELATIVES)</div>", unsafe_allow_html=True)
        
        targets = {
            "Q 60°": 3.1,
            "Q 240°": 2.2,
            "IJ 60°": 1.8,
            "IJ 240°": 1.5,
            "IJ Exc 30°": 2.4
        }
        
        biodex_full_config = [
            {"label": "Q 60°", "g_rel": "Q G conc 60°/s (N/kg)", "d_rel": "Q Dt conc 60°/s (N/kg)", "g_raw": "Q G conc 60°/s", "d_raw": "Q Dt conc 60°/s"},
            {"label": "Q 240°", "g_rel": "Q G conc 240°/s (N/kg)", "d_rel": "Q Dt conc 240°/s (N/kg)", "g_raw": "Q G conc 240°/s", "d_raw": "Q Dt conc 240°/s"},
            {"label": "IJ 60°", "g_rel": "IJ G conc 60°/s (N/kg)", "d_rel": "IJ Dt conc 60°/s (N/kg)", "g_raw": "IJ G conc 60°/s", "d_raw": "IJ Dt conc 60°/s"},
            {"label": "IJ 240°", "g_rel": "IJ G conc 240°/s (N/kg)", "d_rel": "IJ Dt conc 240°/s (N/kg)", "g_raw": "IJ G conc 240°/s", "d_raw": "IJ Dt conc 240°/s"},
            {"label": "IJ Exc 30°", "g_rel": "IJ G Exc 30°/s (N/kg)", "d_rel": "IJ Dt exc 30°/s (N/kg)", "g_raw": "IJ G Exc 30°/s", "d_raw": "IJ Dt exc 30°/s"}
        ]

        radar_cats, vals_l_rel, vals_r_rel, vals_norm, table_data = [], [], [], [], []

        for item in biodex_full_config:
            lbl = item["label"]
            radar_cats.append(lbl)
            val_norm_rel = targets.get(lbl, 0)
            vals_norm.append(val_norm_rel)
            
            real_col_g_raw = find_column_in_df(df, item["g_raw"]) or item["g_raw"]
            real_col_d_raw = find_column_in_df(df, item["d_raw"]) or item["d_raw"]
            v_g_raw = clean_numeric_value(row.get(real_col_g_raw))
            v_d_raw = clean_numeric_value(row.get(real_col_d_raw))

            real_col_g_rel = find_column_in_df(df, item["g_rel"]) or item["g_rel"]
            real_col_d_rel = find_column_in_df(df, item["d_rel"]) or item["d_rel"]
            v_g_rel = clean_numeric_value(row.get(real_col_g_rel))
            v_d_rel = clean_numeric_value(row.get(real_col_d_rel))
            
            if v_g_rel is None and v_g_raw is not None and poids_joueur:
                v_g_rel = v_g_raw / poids_joueur
            if v_d_rel is None and v_d_raw is not None and poids_joueur:
                v_d_rel = v_d_raw / poids_joueur

            vals_l_rel.append(v_g_rel if v_g_rel is not None else 0)
            vals_r_rel.append(v_d_rel if v_d_rel is not None else 0)

            s_lsi, c_lsi = "-", "#888"
            if v_g_raw is not None and v_d_raw is not None:
                mx = max(v_g_raw, v_d_raw)
                if mx > 0:
                    lsi = ((v_d_raw - v_g_raw) / mx) * 100
                    s_lsi = f"{lsi:.0f}%"
                    c_lsi = "#D71920" if abs(lsi) > 10 else ("#F39C12" if abs(lsi) > 5 else "#27AE60")
            
            target_abs = f"{val_norm_rel * poids_joueur:.0f}" if poids_joueur and poids_joueur > 0 else "-"
            table_data.append({"label": lbl, "target": target_abs, "v_g": f"{v_g_raw:.0f}" if v_g_raw is not None else "-", "v_d": f"{v_d_raw:.0f}" if v_d_raw is not None else "-", "lsi": s_lsi, "c_lsi": c_lsi})
        col_radar, col_table = st.columns([1.2, 1]) 
        with col_radar:
            if not radar_cats:
                st.warning("Aucune donnée Biodex configurée trouvée.")
            else:
                import plotly.graph_objects as go
                max_data = max(max(vals_l_rel), max(vals_r_rel), max(vals_norm))
                limit_scale = max(4.0, max_data * 1.1)
                cats_closed = radar_cats + [radar_cats[0]]
                l_closed = vals_l_rel + [vals_l_rel[0]]
                r_closed = vals_r_rel + [vals_r_rel[0]]
                n_closed = vals_norm + [vals_norm[0]]
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(r=n_closed, theta=cats_closed, fill='toself', name='Objectif', mode='lines', line=dict(color='#2ECC71', dash='dash', width=2), fillcolor='rgba(46, 204, 113, 0.1)', hoverinfo='skip'))
                fig.add_trace(go.Scatterpolar(r=l_closed, theta=cats_closed, name='Gauche', mode='lines+markers', fill='toself', line=dict(color='#1ABC9C', width=3), marker=dict(size=8, color='#1ABC9C', symbol='circle'), fillcolor='rgba(26, 188, 156, 0.15)', hoveron='points', hovertemplate='<b>Gauche</b><br>%{theta}: <b>%{r:.2f}</b> N/kg<extra></extra>'))
                fig.add_trace(go.Scatterpolar(r=r_closed, theta=cats_closed, name='Droite', mode='lines+markers', fill='toself', line=dict(color='#9B59B6', width=3), marker=dict(size=8, color='#9B59B6', symbol='circle'), fillcolor='rgba(155, 89, 182, 0.15)', hoveron='points', hovertemplate='<b>Droite</b><br>%{theta}: <b>%{r:.2f}</b> N/kg<extra></extra>'))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, limit_scale], showticklabels=True, tickfont=dict(color="#555", size=9), gridcolor="#eee", linecolor="#eee", layer="below traces"), angularaxis=dict(tickfont=dict(color="#111", size=12, weight="bold"), gridcolor="#eee", linecolor="#eee", layer="below traces"), bgcolor='rgba(0,0,0,0)'), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=40, r=40, t=20, b=20), showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5, font=dict(color="#111", size=12)), height=350, hovermode="closest")
                st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

        with col_table:
            st.markdown(f"<br><div style='text-align:center; font-size:15px; font-weight:900; color:{SDR_RED}; margin-bottom:10px; text-transform:uppercase;'>Résultats Détaillés (Nm)</div>", unsafe_allow_html=True)
            html_rows = ""
            for item in table_data:
                html_rows += f"<tr style='border-bottom:1px solid #eee;'><td style='padding:6px; color:#555;'>{item['label']}</td><td style='text-align:center; color:#666; font-weight:bold;'>{item['target']}</td><td style='text-align:center; color:#111; font-weight:bold;'>{item['v_g']}</td><td style='text-align:center; color:#111; font-weight:bold;'>{item['v_d']}</td><td style='text-align:center; color:{item['c_lsi']}; font-weight:bold;'>{item['lsi']}</td></tr>"
            col_rm_g, col_rm_d = find_column_in_df(df, "Ratio Mixte G") or "Ratio Mixte G", find_column_in_df(df, "Ratio Mixte D") or "Ratio Mixte D"
            val_rm_g, val_rm_d = clean_numeric_value(row.get(col_rm_g)), clean_numeric_value(row.get(col_rm_d))

            def get_ratio_color(val):
                if val is None: return "#888"
                return "#D71920" if val < 0.8 else ("#F39C12" if val <= 1.0 else "#27AE60")

            s_rm_g = f"{val_rm_g:.2f}" if val_rm_g is not None else "-"
            s_rm_d = f"{val_rm_d:.2f}" if val_rm_d is not None else "-"
            html_rows += f"<tr style='border-top:2px solid #ccc; background-color:#f9f9f9;'><td style='padding:6px; font-weight:bold; color:#111;'>Ratio Mixte</td><td style='text-align:center;'>-</td><td style='text-align:center; font-weight:bold; color:{get_ratio_color(val_rm_g)};'>{s_rm_g}</td><td style='text-align:center; font-weight:bold; color:{get_ratio_color(val_rm_d)};'>{s_rm_d}</td><td style='text-align:center;'>-</td></tr>"
            st.markdown(f"<table style='width:100%; border-collapse:collapse; font-size:12px; font-family:sans-serif;'><tr style='background-color:#f0f0f0; color:#333; text-transform:uppercase; font-size:10px;'><th style='padding:8px; text-align:left;'>Test</th><th style='padding:8px; text-align:center;'>Obj. (Nm)</th><th style='padding:8px; text-align:center;'>G (Nm)</th><th style='padding:8px; text-align:center;'>D (Nm)</th><th style='padding:8px; text-align:center;'>LSI</th></tr>{html_rows}</table>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:11px; color:#666; font-style:italic; margin-top:5px;'>* L'objectif brut (Nm) est calculé en multipliant la norme relative (N/kg) par le poids du joueur.</div>", unsafe_allow_html=True)

    
        # ==========================================
        # SALLE
        # ==========================================
        st.markdown(f"<div class='section-header' style='font-size:22px; margin-top:40px; margin-bottom:10px; border-bottom:2px solid #555; padding-bottom:5px;'>SALLE</div>", unsafe_allow_html=True)

        mode_cmj = render_subheader("Counter Movement Jump", group_toggle=True)
        
        df_cmj_master = load_cmj_master()
        has_details = check_has_cmj(p_sel, df_cmj_master)
        
        c_cmj1, c_cmj2, c_cmj3, c_cmj4 = st.columns(4)
        with c_cmj1: render_single_kpi("CMJ 2JB", mode_override=mode_cmj)
        with c_cmj2: render_single_kpi("RSI CMJ", mode_override=mode_cmj)
        with c_cmj3: render_single_kpi("Peak Force CMJ", mode_override=mode_cmj)
        with c_cmj4: render_single_kpi("RFD CMJ", mode_override=mode_cmj)
        
        if has_details:
            st.markdown("<br>", unsafe_allow_html=True)
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                st.markdown("""
                <style>
                div.stButton > button:first-child {
                    background-color: #f9f9f9;
                    color: #D71920;
                    border: 2px solid #D71920;
                    border-radius: 8px;
                    font-weight: 900;
                }
                div.stButton > button:first-child:hover {
                    background-color: #D71920;
                    color: #ffffff;
                }
                </style>""", unsafe_allow_html=True)
                
                if st.button("📊 ANALYSE DÉTAILLÉE", key="btn_details_cmj", width='stretch'):
                    show_cmj_details(p_sel, df_cmj_master)

        st.markdown("<hr style='border:1px dashed #eee; margin-top:30px; margin-bottom:30px;'>", unsafe_allow_html=True)
        
        mode_puissance = render_subheader("PUISSANCE & FORCE", group_toggle=True)
        c_sal5, c_sal6, c_sal7 = st.columns(3)
        with c_sal5: render_single_kpi("Drop jump", mode_override=mode_puissance)
        with c_sal6: render_single_kpi("Wattbike (6s)", mode_override=mode_puissance)
        with c_sal7: render_single_kpi("Squat belt (N)", mode_override=mode_puissance)
        val_cmj_dsi = clean_numeric_value(row.get(get_col_name("Peak Force CMJ")))
        val_squat_dsi = clean_numeric_value(row.get(get_col_name("Squat belt (N)")))
        
        if val_cmj_dsi and val_squat_dsi and val_squat_dsi > 0:
            dsi_val = val_cmj_dsi / val_squat_dsi
            if dsi_val < 0.33:
                dsi_color, dsi_text = "#D71920", "DOMINANT FORCE"
            elif dsi_val > 0.46:
                dsi_color, dsi_text = "#3498DB", "DOMINANT VITESSE"
            else:
                dsi_color, dsi_text = "#27AE60", "ÉQUILIBRÉ"
                
            st.markdown(f"""
            <div class="kpi-card" style="padding:15px; border-left:6px solid {dsi_color}; margin-top:20px;">
                <div style="font-size:14px; font-weight:900; color:#333; text-transform:uppercase;">DYNAMIC STRENGTH INDEX ({annotate_glossary_terms("DSI")})</div>
                <div style="display:flex; align-items:center; gap:20px; margin-top:10px; margin-bottom:15px;">
                    <div style="font-size:36px; font-weight:900; color:{dsi_color}; line-height:1;">{dsi_val:.2f}</div>
                    <div style="font-size:14px; font-weight:bold; color:{dsi_color}; background:#f9f9f9; padding:8px 12px; border-radius:6px; border:1px solid #eee;">
                        {dsi_text}
                    </div>
                </div>
                <div style="font-size:11px; color:#555; border-top:1px dashed #ccc; padding-top:10px; display:flex; justify-content:space-between;">
                    <div><span style="color:#D71920; font-weight:900;">&lt; 0.33</span> Force</div>
                    <div><span style="color:#27AE60; font-weight:900;">0.33 - 0.46</span> Équilibré</div>
                    <div><span style="color:#3498DB; font-weight:900;">&gt; 0.46</span> Vitesse</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        # ==========================================
        # TERRAIN
        # ==========================================
        st.markdown(f"<div class='section-header' style='font-size:22px; margin-top:40px; margin-bottom:10px; border-bottom:2px solid #555; padding-bottom:5px;'>TERRAIN</div>", unsafe_allow_html=True)

        render_subheader("PHYSIOLOGIE ET CARDIO")
        c_phy1, c_phy2 = st.columns(2)
        with c_phy1: render_single_kpi("VMA")
        with c_phy2: render_single_kpi("FC")
        
        c_phy3, c_phy4 = st.columns(2)
        with c_phy3: render_single_kpi("SV1")
        with c_phy4: render_single_kpi("SV2")
        
        render_single_kpi("Test 1km (s)")
        
        pdf_path, pdf_bytes = _find_and_read_metamax_pdf(p_sel)

        if pdf_path:
            st.markdown("<br>", unsafe_allow_html=True)
            
            st.markdown("""
            <style>
            .btn-metamax > button:first-child {
                background-color: #f0f8ff;
                color: #1E3A8A;
                border: 2px solid #1E3A8A;
                border-radius: 8px;
                font-weight: 900;
            }
            .btn-metamax > button:first-child:hover {
                background-color: #1E3A8A;
                color: #ffffff;
            }
            </style>""", unsafe_allow_html=True)
            
            st.markdown('<div class="btn-metamax">', unsafe_allow_html=True)

            # 2. On place le bouton de téléchargement en dehors du "if st.button"
            # Ainsi, il est toujours visible, il connaît "pdf_bytes", et il ne plantera pas
            st.download_button(
                label="📥 Télécharger le PDF (Recommandé si l'affichage bug)", 
                data=pdf_bytes, 
                file_name=f"Rapport_Metamax_{p_sel.replace(' ', '_')}.pdf", 
                mime="application/pdf"
            )

            # 3. Affichage natif via st.pdf() (remplace l'ancien iframe base64,
            # qui est bloqué par les navigateurs sur Streamlit Cloud car l'app
            # elle-même tourne déjà dans un iframe : un data-URI PDF dans un
            # iframe imbriqué est couramment bloqué par la politique de sécurité
            # du navigateur, même si ça fonctionne en local sans ce problème)
            if st.button("🫁 AFFICHER LE RAPPORT PHYSIOLOGIQUE COMPLET (PACELAB)", key="btn_pdf_metamax", width='stretch'):
                st.pdf(pdf_bytes, height=800)
                
            st.markdown('</div>', unsafe_allow_html=True)
            
        render_subheader("ACCÉLÉRATION")
        render_single_kpi("Temps sur 10m")

        render_subheader("GPS")
        c_gps1, c_gps2, c_gps3 = st.columns(3)
        with c_gps1: render_single_kpi("Amax")
        with c_gps2: render_single_kpi("Dmax")
        with c_gps3: render_single_kpi("Vmax")
        
        c_gps4, c_gps5 = st.columns(2)
        with c_gps4: render_single_kpi("Nb Accélérations")
        with c_gps5: render_single_kpi("Nb Décélérations")

        c_gps6, c_gps7, c_gps8 = st.columns(3)
        with c_gps6: render_single_kpi("Distance HSR")
        with c_gps7: render_single_kpi("Distance Totale")
        with c_gps8: render_single_kpi("Distance Sprint (92% Vimax)")

        st.markdown("<br>", unsafe_allow_html=True) 

# ==========================================
        
        # 1080 SPRINT (Bascule instantanée)
        # ==========================================
        # ==========================================
        # 1080 SPRINT (Bascule instantanée & Indépendant)
        # ==========================================
        # ==========================================
        # 1080 SPRINT (Bascule instantanée & Indépendant)
        # ==========================================
        @st.fragment
        def afficher_section_1080():
            df_1080 = df_player.dropna(subset=["Temps total 1080 (s)"])
            
            if df_1080.empty:
                st.markdown(f"<div class='section-header' style='font-size:22px; margin-top:40px; margin-bottom:10px; border-bottom:2px solid #555; padding-bottom:5px;'>1080 SPRINT</div>", unsafe_allow_html=True)
                st.info("🏃 Aucune donnée 1080 Sprint trouvée pour ce joueur.")
                return
            
            dist_col = "Distance 1080 (m)"
            distances_dispos = sorted(df_1080[dist_col].dropna().unique().tolist())
            if not distances_dispos: distances_dispos = [15]
            
            # --- 1. TITRE PRINCIPAL ---
            st.markdown(f"<div class='section-header' style='font-size:22px; margin-top:30px; margin-bottom:20px; border-bottom:2px solid #555; padding-bottom:5px;'>1080 SPRINT</div>", unsafe_allow_html=True)
            
            # --- 2. BANDEAU DE CONTRÔLES (Filtres & Unités) ---
            st.markdown("<div style='background-color:#f9f9f9; padding:15px 20px; border-radius:8px; border:1px solid #eee; margin-bottom:25px;'>", unsafe_allow_html=True)
            c_ctrl1, c_ctrl2 = st.columns(2)
            with c_ctrl1:
                sel_dist = st.selectbox("Distance du sprint (m) :", distances_dispos, index=0, key=f"dist_1080_{p_sel}")
            with c_ctrl2:
                # La marge invisible permet d'aligner le toggle exactement avec la selectbox
                st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
                st.session_state["show_ms_global"] = st.toggle("⏱️ Afficher les vitesses en m/s", value=st.session_state.get("show_ms_global", False))
            st.markdown("</div>", unsafe_allow_html=True)

            # --- 3. SYNCHRONISATION DES DONNÉES ---
            row_1080 = df_1080[df_1080[dist_col] == sel_dist].iloc[-1]
            
            for col in df_1080.columns:
                if "1080" in str(col):
                    row[col] = row_1080[col]
                    if "Date" in df_1080.columns and pd.notna(row_1080["Date"]):
                        row[f"{col}_date"] = row_1080["Date"]
                    elif "Session exact" in df_1080.columns and pd.notna(row_1080["Session exact"]):
                        row[f"{col}_date"] = row_1080["Session exact"]
            
            # --- 4. SOUS-TITRE (Qui gère déjà le toggle Absolu/Relatif) ---
            mode_1080 = render_subheader("MÉTRIQUES PRINCIPALES", group_toggle=True)
            st.markdown("<div style='margin-bottom:15px;'></div>", unsafe_allow_html=True)
                
            # --- 5. AFFICHAGE DES CARTES ---
            c_1080_1, c_1080_2, c_1080_3 = st.columns(3)
            with c_1080_1: render_single_kpi("Temps total 1080", mode_override=mode_1080)
            with c_1080_2: render_single_kpi("Amax 1080", mode_override=mode_1080)
            with c_1080_3: render_single_kpi("Pmax 1080", mode_override=mode_1080)
            
            c_1080_4, c_1080_5 = st.columns(2)
            with c_1080_4: render_single_kpi("Vmax 15m 1080", mode_override=mode_1080)
            
            with c_1080_5: 
                v15_raw = clean_numeric_value(row.get(get_col_name("Vmax 15m 1080")))
                vgps_raw = clean_numeric_value(row.get(get_col_name("Vmax")))
                
                if v15_raw and vgps_raw and vgps_raw > 0:
                    v15_kmh = v15_raw if v15_raw > 15 else v15_raw * 3.6
                    vgps_kmh = vgps_raw if vgps_raw > 15 else vgps_raw * 3.6
                    
                    pct_vmax = (v15_kmh / vgps_kmh) * 100
                    
                    if pct_vmax >= 90: c_pct, stat_pct = "#27AE60", "🟢"
                    elif pct_vmax >= 85: c_pct, stat_pct = "#F39C12", "🟠"
                    else: c_pct, stat_pct = "#D71920", "🔴"
                    
                    html_pct = get_kpi_card_html(
                        label="% Vmax 15m (vs GPS)", val_display=f"{pct_vmax:.1f}", unit_display="%", 
                        norm_color=c_pct, pct_color=c_pct, pct_html="<div style='color:#666; font-size:12px;'>-</div>", 
                        status_text=stat_pct, norm_tooltip=f"Vmax 15m ({v15_kmh:.1f} km/h) / Vmax GPS ({vgps_kmh:.1f} km/h)", tip="", subtitle_html=""
                    )
                    st.markdown(html_pct, unsafe_allow_html=True)
                else:
                    st.markdown(get_kpi_card_html(
                        label="% Vmax 15m (vs GPS)", val_display="-", unit_display="%", norm_color="#eee", 
                        pct_color="#eee", pct_html="-", status_text="⚪", norm_tooltip="Données manquantes", tip="", subtitle_html=""
                    ), unsafe_allow_html=True)

            # --- ANALYSE COMPLÉMENTAIRE ---
            with st.expander("🔬 ANALYSE COMPLÉMENTAIRE 1080 (PROFIL FORCE-VITESSE)", expanded=False):
                st.markdown("<div style='font-size:14px; font-weight:bold; color:#555; text-transform:uppercase; margin-bottom:15px;'>MÉTRIQUES AVANCÉES</div>", unsafe_allow_html=True)
                
                c_comp1, c_comp2, c_comp3 = st.columns(3)
                with c_comp1: render_single_kpi("F0 1080", mode_override=mode_1080)
                with c_comp2: render_single_kpi("V0 1080", mode_override=mode_1080)
                with c_comp3: render_single_kpi("Tau 1080", mode_override=mode_1080)
                
                c_comp4, c_comp5, c_comp6 = st.columns(3)
                with c_comp4: render_single_kpi("Momentum 1080", mode_override=mode_1080)
                with c_comp5: render_single_kpi("T90 1080", mode_override=mode_1080)
                with c_comp6: render_single_kpi("D90 1080", mode_override=mode_1080)

                # --- PROFIL FORCE-VITESSE ---
                st.markdown("<hr style='border:1px dashed #eee;'>", unsafe_allow_html=True)
                
                f0_val = clean_numeric_value(row.get(get_col_name("F0 1080")))
                v0_val = clean_numeric_value(row.get(get_col_name("V0 1080")))
                pied_val = str(row.get("Pied départ 1080", "-")).strip()
                dist_val = sel_dist
                
                if f0_val and v0_val and v0_val > 0:
                    # Le Bandeau très visuel
                    st.markdown(f'''
                    <div style="display:flex; justify-content:space-around; align-items:center; background:#f0f2f6; padding:15px; border-radius:10px; border-left:5px solid {SDR_RED}; margin-bottom:20px;">
                        <div style="text-align:center;">
                            <div style="font-size:11px; color:#555; font-weight:bold; text-transform:uppercase;">Distance</div>
                            <div style="font-size:18px; color:#111; font-weight:900;">{dist_val} m</div>
                        </div>
                        <div style="text-align:center; border-left:1px solid #ddd; padding-left:20px;">
                            <div style="font-size:11px; color:#555; font-weight:bold; text-transform:uppercase;">Pied de départ</div>
                            <div style="font-size:18px; color:#111; font-weight:900;">{pied_val}</div>
                        </div>
                        <div style="text-align:center; border-left:1px solid #ddd; padding-left:20px;">
                            <div style="font-size:11px; color:#D71920; font-weight:bold; text-transform:uppercase;">Force Max (F0)</div>
                            <div style="font-size:24px; color:#D71920; font-weight:900;">{f0_val:.0f} <span style="font-size:14px;">N</span></div>
                        </div>
                        <div style="text-align:center; border-left:1px solid #ddd; padding-left:20px;">
                            <div style="font-size:11px; color:#3498DB; font-weight:bold; text-transform:uppercase;">Vitesse Max (V0)</div>
                            <div style="font-size:24px; color:#3498DB; font-weight:900;">{v0_val:.2f} <span style="font-size:14px;">m/s</span></div>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
                    
                    if dist_val <= 20:
                        st.warning(f"⚠️ **Sprint Court ({dist_val}m) :** La V0 théorique et la Pmax peuvent être sous-estimées.")

                    import numpy as np
                    import plotly.graph_objects as go
                    
                    v_arr = np.linspace(0, v0_val, 100)
                    f_arr = f0_val * (1 - (v_arr / v0_val))
                    p_arr = f_arr * v_arr
                    
                    fig_fv = go.Figure()
                    fig_fv.add_trace(go.Scatter(x=v_arr, y=f_arr, mode='lines', name='Force (N)', line=dict(color='#D71920', width=3)))
                    fig_fv.add_trace(go.Scatter(x=v_arr, y=p_arr, mode='lines', name='Puissance (W)', line=dict(color='#3498DB', width=3, dash='dot'), yaxis='y2'))
                    
                    fig_fv.add_annotation(x=0, y=f0_val, text=f"<b>F0 = {f0_val:.0f} N</b>", showarrow=True, arrowhead=2, arrowcolor="#D71920", ax=40, ay=20, font=dict(color="#D71920", size=12), bgcolor="rgba(255,255,255,0.8)")
                    fig_fv.add_annotation(x=v0_val, y=0, text=f"<b>V0 = {v0_val:.2f} m/s</b>", showarrow=True, arrowhead=2, arrowcolor="#3498DB", ax=-40, ay=-30, font=dict(color="#3498DB", size=12), bgcolor="rgba(255,255,255,0.8)")
                    
                    fig_fv.update_layout(
                        title=dict(text="Profil Force-Vitesse-Puissance", font=dict(size=14, color="#333", family="sans-serif")),
                        xaxis=dict(title=dict(text="Vitesse (m/s)"), showgrid=True, gridcolor='#eee'),
                        yaxis=dict(title=dict(text="<b>Force (N)</b>", font=dict(color='#D71920')), tickfont=dict(color='#D71920'), showgrid=False, rangemode='tozero'),
                        yaxis2=dict(title=dict(text="<b>Puissance (W)</b>", font=dict(color='#3498DB')), tickfont=dict(color='#3498DB'), anchor='x', overlaying='y', side='right', showgrid=False, rangemode='tozero'),
                        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
                        height=400, margin=dict(l=20, r=20, t=60, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_fv, width='stretch', config={'displayModeBar': False})
                else:
                    st.info("Données F0 ou V0 insuffisantes pour modéliser le profil Force-Vitesse.")

            # --- RAPPORTS 1080 (PDF) ---
            dossier_1080 = os.path.join(os.getcwd(), "1080")
            pdf_1080_files = _list_1080_pdfs(p_sel)

            if pdf_1080_files:
                st.markdown("<hr style='border:1px dashed #eee;'>", unsafe_allow_html=True)
                st.markdown("<div style='font-size:14px; font-weight:bold; color:#555; text-transform:uppercase; margin-bottom:15px;'>RAPPORTS 1080 (PDF)</div>", unsafe_allow_html=True)

                sel_pdf = st.selectbox("Sélectionner le rapport :", pdf_1080_files, key=f"sel_pdf_1080_{p_sel}")

                if sel_pdf:
                    pdf_1080_path = os.path.join(dossier_1080, sel_pdf)
                    pdf_1080_bytes = _read_pdf_bytes(pdf_1080_path)

                    st.markdown("""
                    <style>
                    .btn-1080 > button:first-child {
                        background-color: #f0f8ff;
                        color: #1E3A8A;
                        border: 2px solid #1E3A8A;
                        border-radius: 8px;
                        font-weight: 900;
                    }
                    .btn-1080 > button:first-child:hover {
                        background-color: #1E3A8A;
                        color: #ffffff;
                    }
                    </style>""", unsafe_allow_html=True)

                    st.markdown('<div class="btn-1080">', unsafe_allow_html=True)
                    st.download_button(
                        label="📥 Télécharger le Rapport PDF",
                        data=pdf_1080_bytes,
                        file_name=sel_pdf,
                        mime="application/pdf",
                        width='stretch'
                    )

                    if st.button("🗎 AFFICHER LE RAPPORT PDF", key=f"btn_show_1080_pdf_{p_sel}", width='stretch'):
                        st.pdf(pdf_1080_bytes, height=800)
                    st.markdown('</div>', unsafe_allow_html=True)

        # On appelle la section
        afficher_section_1080()

        def get_smart_recos(player_row, df_all):
            try:
                import os
                df_exos = None
                for f in os.listdir():
                    if "Exercices_Renfo" in f and f.endswith((".csv", ".xlsx")):
                        if f.endswith(".csv"): df_exos = pd.read_csv(f)
                        else: df_exos = pd.read_excel(f)
                        break
                        
                if df_exos is None:
                    return [], [], None
                    
                all_exos_list = df_exos['Exercice'].dropna().unique().tolist()
                potential_recos = []
                
                kpis_critiques = {
                    "CMJ (cm)": "CMJ", "Vmax": "Vmax", "Squat Keiser": "Squat",
                    "Adducteurs (G)": "Adducteurs", "Nordic Ischio (G)": "Nordic"
                }
                
                for metric_ui, keyword in kpis_critiques.items():
                    col = find_column_in_df(df_all, metric_ui)
                    val = clean_numeric_value(player_row.get(col))
                    if val is not None:
                        _, pct = calculate_percentile(df_all, col, val)
                        
                        # Attribution de la priorité et de la couleur
                        if pct < 33: 
                            niv_texte = "PRIORITE FORTE"
                            couleur = "#D71920" # Rouge
                        elif pct < 66: 
                            niv_texte = "PRIORITE MOYENNE"
                            couleur = "#F39C12" # Orange
                        else: 
                            niv_texte = "PRIORITE FAIBLE"
                            couleur = "#27AE60" # Vert
                        
                        score_priorite = 100 - pct
                        matches = df_exos[df_exos['Cible (Variables du profilage)'].astype(str).str.contains(keyword, na=False, case=False)]
                        for _, exo in matches.iterrows():
                            d_exo = exo.to_dict()
                            d_exo['priorite_score'] = score_priorite
                            d_exo['niveau'] = niv_texte
                            d_exo['couleur'] = couleur
                            d_exo['pourquoi'] = f"Manque de performance sur le test {keyword} (Le joueur est classé dans les {int(pct)}% les plus faibles de l'équipe)."
                            potential_recos.append(d_exo)

                paires_lsi = [("Adducteurs (G)", "Adducteurs (D)", "Adducteurs"), 
                              ("Nordic Ischio (G)", "Nordic Ischio (D)", "Ischios")]
                
                for g, d, label in paires_lsi:
                    asym = get_asymmetry(player_row, g, df_all)
                    if asym and asym > 10:
                        niv_texte = "URGENCE ABSOLUE" if asym > 15 else "PRIORITE FORTE"
                        couleur = "#D71920" # Toujours rouge pour une asymétrie
                        score_asym = (200 + asym) if asym > 15 else (150 + asym)
                        matches = df_exos[df_exos['Catégorie (Couleur)'].astype(str).str.contains("Jaune", na=False)]
                        for _, exo in matches.iterrows():
                            d_exo = exo.to_dict()
                            d_exo['priorite_score'] = score_asym
                            d_exo['niveau'] = niv_texte
                            d_exo['couleur'] = couleur
                            d_exo['pourquoi'] = f"Asymétrie importante détectée ({int(asym)}%) entre les {label} gauche et droit. Risque de blessure élevé."
                            potential_recos.append(d_exo)

                if not potential_recos: 
                    return [], all_exos_list, df_exos

                recos_finales = pd.DataFrame(potential_recos).sort_values('priorite_score', ascending=False)
                top_recos = recos_finales.drop_duplicates(subset=['Exercice']).head(4).to_dict('records')
                
                return top_recos, all_exos_list, df_exos
                
            except Exception as e:
                return [], [], None

        # Exécution de la fonction
        # --- SYSTÈME DE PROGRAMMATION CONSEILLÉE ---
        recos_auto, liste_tous_exos, df_exos_ref = get_recommendations_v3(row, df)
        
        st.markdown("<div class='section-header'>Programmation Conseillée</div>", unsafe_allow_html=True)
        
        # Sélection multiple d'exercices bonus
        if df_exos_ref is not None and liste_tous_exos:
            exos_bonus = st.multiselect("Ajouter des exercices additionnels (Bonus) :", liste_tous_exos, key=f"bonus_multi_{p_sel}")
            
            for eb in exos_bonus:
                if not any(r['Exercice'] == eb for r in recos_auto):
                    det = df_exos_ref[df_exos_ref['Exercice'] == eb].iloc[0].to_dict()
                    det.update({
                        'niveau': "AJOUT MANUEL", 
                        'couleur': "#1E3A8A", # Bleu SDR
                        'pourquoi': "Exercice sélectionné manuellement par le préparateur physique."
                    })
                    recos_auto.append(det)


        # Affichage des cartes d'exercices
        if recos_auto:
            cols = st.columns(len(recos_auto))
            for i, exo in enumerate(recos_auto):
                with cols[i]:
                    bg = exo.get('couleur', '#555555')
                    # Nettoyage des dates Excel (ex: 03-avr -> 3-4)
                    ser = str(exo.get('Séries', '3')).replace('03-avr', '3-4').replace('02-mars', '2-3')
                    rep = str(exo.get('Reps', '10')).replace('05-oct', '5-10')
                    
                    st.markdown(f"""
                        <div style="background:{bg}; color:white; padding:15px; border-radius:10px; min-height:250px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                            <div style="font-size:10px; font-weight:bold; background:rgba(0,0,0,0.2); display:inline-block; padding:3px 8px; border-radius:4px; margin-bottom:10px;">{exo.get('niveau', 'INFO')}</div>
                            <div style="font-size:16px; font-weight:900; margin-bottom:10px; line-height:1.2;">{exo.get('Exercice', '-')}</div>
                            <div style="font-size:12px; margin-bottom:4px;"><b>Séries :</b> {ser}</div>
                            <div style="font-size:12px; margin-bottom:10px;"><b>Reps :</b> {rep}</div>
                            <div style="font-size:11px; margin-bottom:10px; font-style:italic; opacity:0.9;">{exo.get('Focus', '-')}</div>
                            <div style="font-size:10px; border-top:1px solid rgba(255,255,255,0.2); padding-top:8px;">
                                <b>Pourquoi ?</b><br>{exo.get('pourquoi', '')}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        
        # La génération du rapport (points forts/axes/stratégie, aperçu,
        # téléchargement HTML/PDF) a été déplacée dans son propre onglet
        # "RAPPORT" (voir rapport_page.show_rapport_page) — c'est
        # maintenant l'outil complet issu de reims_profiling (persistance
        # GitHub/JSON des commentaires, historique, génération en lot,
        # planning hebdo...), qui remplace ce qu'il y avait ici.
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("ℹ️ Détail des Objectifs & Sources", expanded=False):
            data_norms = []
            seen_metrics = set()
            for cat, variables in OFFICIAL_STRUCTURE.items():
                for var in variables:
                    clean_name = get_clean_label(var)
                    if clean_name in seen_metrics: continue
                    seen_metrics.add(clean_name)
                    norm_val = get_norm_text(var).replace("Obj: ", "")
                    source = get_source(var)
                    data_norms.append({"Catégorie": cat, "Indicateur": clean_name, "Objectif": norm_val, "Source": source})
            st.dataframe(pd.DataFrame(data_norms), width='stretch', hide_index=True)
    with tab_indiv:
        _render_tab_indiv()

        with tab_team:
            # @st.fragment : interagir avec les filtres/sélecteurs de cet
            # onglet ne recalcule plus que cet onglet (plus tout le script,
            # y compris le clustering ML ou le profil individuel).
            @st.fragment
            def _render_tab_team():
                df_team_view = df.copy()
                col_session = "Session" if "Session" in df.columns else next((c for c in df_team_view.columns if 'session' in str(c).lower()), None)

                if col_session:
                    # 1. On ajoute l'option Record de Saison
                    sessions_dispos = ["🏆 Record de Saison"] + sorted(df_team_view[col_session].dropna().astype(str).unique())
                    sel_session_team = st.selectbox("Session :", sessions_dispos, key="sess_team")

                    # 2. Si l'utilisateur choisit le Record de Saison, on reconstruit le DataFrame collectif
                    if sel_session_team == "🏆 Record de Saison":
                        records = []
                        for j in df_team_view['Joueur'].dropna().unique():
                            df_j = df_team_view[df_team_view['Joueur'] == j]
                            if not df_j.empty:
                                # On calcule le record synchronisé pour ce joueur
                                row_j = get_best_season_record_paired(df_j)

                                # On s'assure que les métadonnées cruciales pour l'affichage d'équipe soient
                                # préservées -- dernière valeur RENSEIGNÉE (pas juste `.iloc[-1]`, qui peut
                                # tomber sur une ligne "virtuelle" du fichier 1080 séparé, vide sur ces
                                # colonnes -- voir data_utils.last_valid_value).
                                row_j['Joueur'] = j
                                row_j['Equipe'] = last_valid_value(df_j, 'Equipe', 'N/A')
                                row_j['Poste'] = last_valid_value(df_j, 'Poste', last_valid_value(df_j, 'Position', 'N/A'))
                                row_j[col_session] = "🏆 Record de Saison"

                                records.append(row_j)

                        if records:
                            df_team_view = pd.DataFrame(records)
                        else:
                            df_team_view = pd.DataFrame(columns=df.columns)
                    else:
                        # Comportement classique si session normale sélectionnée
                        df_team_view = df_team_view[df_team_view[col_session].astype(str) == sel_session_team]

                # Appel de la page collective. df_toutes_equipes (pas `df`,
                # filtré sur 1 équipe par le sélecteur global) : nécessaire
                # pour l'overlay "standard PRO" du radar par poste, qui doit
                # pouvoir comparer l'équipe affichée à la PRO même si elle
                # n'est pas l'équipe sélectionnée.
                show_team_page(df_team_view, TEAM_STRUCTURE, df_toutes_equipes)

            _render_tab_team()

        with tab_evol:
            @st.fragment
            def _render_tab_evol():
                show_evolution_page(df)
            _render_tab_evol()

        with tab_comp:
            @st.fragment
            def _render_tab_comp():
                df_comp, source_comp = load_data()
                show_comparateur_page(df_comp)
            _render_tab_comp()

        with tab_cluster:
            @st.fragment
            def _render_tab_cluster():
                show_clustering_page(df)
            _render_tab_cluster()

        # Dans profiling.py
        with tab_classement:
            @st.fragment
            def _render_tab_classement():
                show_classement_page(df)
            _render_tab_classement()

        with tab_rapport:
            @st.fragment
            def _render_tab_rapport():
                # df_toutes_equipes (pas `df`, filtré sur 1 équipe par le
                # sélecteur global) : voir le commentaire à sa définition.
                show_rapport_page(df_toutes_equipes)
            _render_tab_rapport()

        with tab_export:
            @st.fragment
            def _render_tab_export():
                # df_toutes_equipes : l'export doit pouvoir couvrir toutes
                # les équipes en une fois (ex: "le poids de tous les
                # joueurs"), pas seulement celle du sélecteur global.
                from export_page import show_export_page
                show_export_page(df_toutes_equipes)
            _render_tab_export()
