import streamlit as st
import pandas as pd
import numpy as np
import base64
import os
import difflib
import unicodedata
# =============================================================================
# 1. CONSTANTES & CONFIGURATION
# =============================================================================

SDR_RED = "#D71920"
BLACK = "#000000"
WHITE = "#FFFFFF"
SDR_GREY = "#F0F2F6"

def local_css():
    """Injecte le CSS global pour la sidebar et les titres."""
    st.markdown(f"""
    <style>
    [data-testid="stSidebar"] {{ background-color: {SDR_RED}; }}
    [data-testid="stSidebar"] *, [data-testid="stSidebar"] span, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1 {{ color: white !important; }}
    h1, h2, h3 {{ color: {SDR_RED} !important; }}

    /* Filet de sécurité responsive GLOBAL : beaucoup de blocs HTML custom de
    l'app (photos, cartes KPI...) ont une largeur fixe en pixels pensée pour
    un écran de bureau. Ces règles évitent un débordement horizontal sur
    mobile/tablette SANS toucher au HTML de chaque page une par une. */
    img {{ max-width: 100%; height: auto; }}
    .hero-photo, .id-card img {{ max-width: 100%; }}

    /* Tooltip des sigles du glossaire (glossary.annotate_glossary_terms) --
    en CSS plutôt que l'attribut `title` natif, pour marcher aussi au TAP
    sur mobile/tablette (agents, direction), pas seulement au survol
    souris. `tabindex="0"` sur le span le rend focusable au tap -> :focus
    déclenche le même tooltip que :hover. */
    .glossary-term {{ border-bottom: 1px dotted #999; cursor: help; position: relative; outline: none; }}
    .glossary-term::after {{
        content: attr(data-tooltip);
        display: none;
        position: absolute; left: 0; bottom: 125%;
        background: #222; color: #fff; text-align: left;
        padding: 6px 9px; border-radius: 6px; font-size: 11px; font-weight: normal;
        white-space: normal; width: max-content; max-width: 240px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25); z-index: 1000;
    }}
    .glossary-term:hover::after, .glossary-term:focus::after {{ display: block; }}

    /* Tableaux HTML larges (nombreuses colonnes de tests) : scroll
    horizontal contenu dans le tableau plutôt qu'un débordement de toute
    la page, illisible sur petit écran. */
    @media (max-width: 768px) {{
        table {{ display: block; overflow-x: auto; white-space: nowrap; -webkit-overflow-scrolling: touch; }}
    }}

    /* Ajustement mobile */
    @media (max-width: 768px) {{
        .hero-container {{ flex-direction: column; text-align: center; }}
        .hero-right {{ justify-content: center; margin-top: 10px; }}
        .hero-photo {{ width: 90px !important; height: 90px !important; }}
        /* Les blocs custom "carte joueur"/en-tête (largeurs fixes ~120px
        pour la photo) redeviennent raisonnables sur petit écran. */
        img[style*="width: 120px"], img[style*="width:120px"] {{ width: 90px !important; height: 90px !important; }}
        div[style*="width: 120px"], div[style*="width:120px"] {{ width: 90px !important; height: 90px !important; }}
    }}
    </style>
    """, unsafe_allow_html=True)

# utils.py

def init_relative_mode():
    if 'use_relative' not in st.session_state:
        st.session_state.use_relative = False






# =============================================================================
# 2. GESTION DES IMAGES
# =============================================================================

@st.cache_data(ttl=600, show_spinner=False)
def img_to_b64(image_path):
    """Convertit une image locale en chaîne base64 pour l'intégrer au HTML."""
    if not image_path or not os.path.exists(image_path):
        return ""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception as e:
        return ""

@st.cache_data(ttl=600, show_spinner=False)
def get_best_photo_path(player_name):
    """Cherche la photo du joueur dans le dossier Photos.

    @st.cache_data : évite un os.listdir() complet du dossier Photos par
    joueur à chaque rerun Streamlit (l'appli relance tout le script à
    chaque interaction) -- gain net sur toutes les pages qui affichent
    plusieurs joueurs (équipe, comparateur, clustering...).
    """
    folder = "Photos"
    if not os.path.exists(folder): return None

    # Création d'un map {nom_fichier_lower: nom_fichier_reel}
    files_map = {f.lower(): f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))}
    
    clean_name = player_name.strip()
    parts = clean_name.split()
    
    # Stratégies de recherche (Nom complet, Nom Prénom, Prénom Nom)
    candidates = [clean_name]
    if len(parts) > 1:
        candidates.append(f"{parts[-1]} {' '.join(parts[:-1])}") # NOM Prénom
        candidates.append(f"{' '.join(parts[1:])} {parts[0]}")   # Prénom NOM
    
    extensions = [".jpg", ".png", ".jpeg"]
    
    for cand in candidates:
        for ext in extensions:
            target_key = f"{cand}{ext}".lower()
            if target_key in files_map:
                return os.path.join(folder, files_map[target_key])
    return None

# =============================================================================
# 3. LOGIQUE MÉTIER & CALCULS
# =============================================================================

def is_inverted(label):
    # Délègue à la version unique et partagée (voir config_rapport.py,
    # section 4). On garde cette fonction ici pour ne pas casser les appels
    # existants (utils.is_inverted(...)) ailleurs dans l'appli.
    from config_rapport import is_inverted_metric
    return is_inverted_metric(label)

# utils.py

@st.cache_data(ttl=60)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1P1hxqlqO03L3nBnnchnKjbw22LIPXqi2/export?format=csv&gid=795853830"
    try:
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        cols_lower = {str(c).lower().strip(): c for c in df.columns}
        target = next((cols_lower[k] for k in ['joueur', 'nom', 'name'] if k in cols_lower), None)
        if target:
            df = df.dropna(subset=[target]).rename(columns={target: 'Joueur'})
            df['Joueur'] = df['Joueur'].astype(str).str.strip()
            df = merge_1080_data(df)
            return df, "Google Sheets"
    except Exception:
        pass

    files = ["Profilage 2026-2027.xlsx", "Profilage 2026-2027.csv"]
    for f in files:
        if os.path.exists(f):
            try:
                df = pd.read_excel(f, header=0) if f.endswith('.xlsx') else pd.read_csv(f)
                df.columns = [str(c).strip() for c in df.columns]
                cols_lower = {str(c).lower().strip(): c for c in df.columns}
                target = next((cols_lower[k] for k in ['joueur', 'nom', 'name'] if k in cols_lower), None)
                if target:
                    df = df.dropna(subset=[target]).rename(columns={target: 'Joueur'})
                    df['Joueur'] = df['Joueur'].astype(str).str.strip()
                    df = merge_1080_data(df)
                    return df, f"Local ({f})"
            except Exception:
                continue
    return pd.DataFrame(), "Aucun"


# =============================================================================
# 2bis. 1080 SPRINT — fichier Google Sheet séparé (depuis le 10/09/2026)
# =============================================================================
# POURQUOI un fichier séparé : sur demande explicite (plus simple à mettre à
# jour pour le staff sans toucher au fichier principal). Ce fichier a UNE
# ligne par joueur (pas de colonne Date/Session comme le fichier principal) :
# selon le département performance, ce sont pour l'instant des tests de
# pré-saison, donc tous rattachés à la même session "Pré-saison". Si une
# colonne "Date" est ajoutée un jour dans ce Google Sheet (pour de nouveaux
# tests en cours de saison), elle sera automatiquement reprise comme date
# précise de la session -- rien à changer dans ce code à ce moment-là.
URL_1080 = "https://docs.google.com/spreadsheets/d/19tP2BvWh0-iFFYBX5cxct5Itp4Fzg6Mu/export?format=csv&gid=1797140653"

# Colonne du fichier 1080 -> colonne attendue par le reste de l'appli (déjà
# utilisée telle quelle dans profiling.py/config_rapport.py -- inchangée
# pour ne rien casser des rapports, radars, normes... qui lisent déjà ces
# noms de colonnes précis).
_MAPPING_1080 = {
    "Pied départ": "Pied départ 1080",
    "Distance (m)": "Distance 1080 (m)",
    "Temps total (s)": "Temps total 1080 (s)",
    "Pmax (W)": "Pmax 1080 (W)",
    "Pmax (W/Kg)": "Pmax 1080 (W/Kg)",
    "Vmax 15m (m/s)": "Vmax 15m 1080 (m/s)",
    "Tau (s)": "Tau 1080 (s)",
    "T90 (s)": "T90 1080 (s)",
    "D90 (m)": "D90 1080 (m)",
    "Momentum (Kg*m/s)": "Momentum 1080 (Kg*m/s)",
    "F0 (N)": "F0 1080 (N)",
    "F0 (N/kg)": "F0 1080 (N/kg)",
    "V0 (m/s)": "V0 1080 (m/s)",
    "Poids (Kg)": "Poids (kg)",
    # "Amax 1080 (m/s²)" a déjà le bon nom dans le fichier source -> pas de
    # renommage nécessaire pour cette colonne.
}


@st.cache_data(ttl=60, show_spinner=False)
def load_1080_data() -> pd.DataFrame:
    """
    Charge le fichier 1080 séparé et renvoie un DataFrame déjà aux noms de
    colonnes attendus par le reste de l'appli (voir _MAPPING_1080), une
    ligne "session virtuelle" par joueur -- à concaténer (pd.concat) au
    DataFrame principal, PAS à fusionner dessus : ces lignes n'ont que les
    colonnes 1080 + Joueur/Equipe/Session remplies, le reste est vide, et
    c'est déjà le pattern que l'appli sait gérer partout ailleurs (une ligne
    par session, colonnes non testées cette session-là = vides).
    Renvoie un DataFrame vide si le fichier est indisponible (échec
    silencieux : ne doit jamais faire planter le chargement des données
    principales).
    """
    try:
        df = pd.read_csv(URL_1080)
    except Exception:
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]
    if "Joueur" not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=["Joueur"])
    df["Joueur"] = df["Joueur"].astype(str).str.strip()

    df = df.rename(columns={k: v for k, v in _MAPPING_1080.items() if k in df.columns})

    # Session "Pré-saison" par défaut. Si une colonne Date existe (pas le
    # cas aujourd'hui), elle devient la date précise de la session -- le
    # libellé "Pré-saison" reste sur toutes les lignes tant que le staff ne
    # dit pas autre chose, mais l'ordre chronologique (Session exact/Date)
    # suivra quand même la vraie date renseignée.
    df["Session"] = "Pré-saison"
    if "Date" in df.columns:
        df["Session exact"] = df["Date"]

    return df


def _normalize_name(name) -> str:
    """Nom de joueur sans accents, casse, ni espaces superflus -- pour
    rapprocher deux fichiers qui n'orthographient pas toujours un nom à
    l'identique (ex: "Théo" / "Theo")."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.strip().upper().split())


def merge_1080_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Intègre les lignes du fichier 1080 séparé (load_1080_data) dans le
    DataFrame principal `df`. Ne modifie pas `df` si le fichier 1080 est
    vide/indisponible (repli silencieux -- l'appli continue de fonctionner
    sans les données 1080, comme avant l'ajout de ce fichier séparé).

    POURQUOI on réécrit l'Equipe du fichier 1080 avec celle du fichier
    principal : les deux fichiers ne sont pas toujours d'accord sur
    l'équipe d'un joueur (catégories d'âge suivies différemment d'un
    fichier à l'autre -- ex: un joueur en "ELITE" dans le fichier principal
    mais étiqueté "REVELATION" dans le fichier 1080). Sans ce correctif, un
    joueur qui n'est PAS dans une équipe apparaissait quand même dans le
    sélecteur de cette équipe, juste parce que sa ligne 1080 le disait --
    le fichier principal (où l'équipe est suivie session par session) fait
    foi ; le fichier 1080 ne sert que pour les valeurs 1080 elles-mêmes.

    BUG CORRIGÉ (09/2026) : ce module concaténait AVANT chaque ligne 1080
    comme une ligne de session à part entière, même quand le joueur avait
    DÉJÀ une ligne "Pré-saison" dans le fichier principal (le cas de la
    quasi-totalité des joueurs testés au 1080, puisque c'est un test de
    pré-saison). Résultat concret : le groupe de comparaison "Équipe PRO"
    affichait n=50 alors que l'équipe PRO ne compte que ~30 joueurs -- 17
    d'entre eux comptaient double (leur ligne normale + leur ligne 1080
    "virtuelle"), ce qui gonflait aussi artificiellement leur poids dans
    tous les calculs de percentile utilisant une colonne 1080.
    Corrigé : quand une ligne (Joueur, Session) existe déjà dans `df`, les
    colonnes 1080 sont fusionnées DANS cette ligne (comme n'importe quel
    autre test de la même session) plutôt que d'en créer une nouvelle.
    Seuls les joueurs du fichier 1080 SANS AUCUNE ligne correspondante déjà
    présente (cas rare : nouveau joueur pas encore dans le fichier
    principal) se voient ajouter une ligne "Pré-saison" dédiée.
    """
    df_1080 = load_1080_data()
    if df_1080.empty:
        return df
    if "Equipe" in df.columns and "Joueur" in df.columns:
        equipe_reference = (
            df.dropna(subset=["Equipe"])
            .drop_duplicates(subset=["Joueur"], keep="last")
            .set_index("Joueur")["Equipe"]
        )
        df_1080["Equipe"] = df_1080["Joueur"].map(equipe_reference).fillna(df_1080["Equipe"])

    if "Joueur" not in df.columns or "Session" not in df.columns:
        return pd.concat([df, df_1080], ignore_index=True, sort=False)

    df = df.copy()
    # Dernier index de df vu pour chaque (Joueur, Session) -- cible de la
    # fusion s'il y en a une (garde le dernier en cas de lignes dupliquées
    # préexistantes dans le fichier principal, cohérent avec le reste de
    # l'appli -- voir data_utils.last_valid_value).
    key_to_idx = {}
    # Index normalisé (sans accents/casse) par session, pour rattraper une
    # orthographe LÉGÈREMENT différente entre les 2 fichiers (ex: "Jordy"
    # dans le fichier principal vs "Jordi" dans le fichier 1080) -- sans
    # cette tolérance, ce joueur se retrouvait dupliqué sous 2 orthographes
    # différentes au lieu d'être reconnu comme le même.
    norm_index_by_session = {}
    for idx, j, s in zip(df.index, df["Joueur"], df["Session"]):
        key_to_idx[(j, s)] = idx
        norm = _normalize_name(j)
        norm_index_by_session.setdefault(s, {}).setdefault(norm, []).append((j, idx))

    rows_to_append = []
    unmatched_names = []
    for _, r1080 in df_1080.iterrows():
        joueur_1080, session_1080 = r1080.get("Joueur"), r1080.get("Session")
        key = (joueur_1080, session_1080)
        target_idx = key_to_idx.get(key)
        if target_idx is None:
            # Pas de correspondance exacte -> on tente une correspondance
            # approximative (accents/casse tolérés + légère différence
            # d'orthographe) parmi les joueurs de la MÊME session, pour
            # éviter un doublon silencieux type "Jordy" / "Jordi".
            candidats = norm_index_by_session.get(session_1080, {})
            norm_1080 = _normalize_name(joueur_1080)
            close = difflib.get_close_matches(norm_1080, candidats.keys(), n=2, cutoff=0.82)
            if len(close) == 1 and len(candidats[close[0]]) == 1:
                nom_reel, target_idx = candidats[close[0]][0]
                unmatched_names.append((joueur_1080, nom_reel))
            else:
                rows_to_append.append(r1080)
                continue
        for col, val in r1080.items():
            if col == "Joueur" or pd.isna(val):
                continue
            if col not in df.columns:
                df[col] = pd.NA
            df.at[target_idx, col] = val

    if rows_to_append:
        df = pd.concat([df, pd.DataFrame(rows_to_append)], ignore_index=True, sort=False)
    return df


# =============================================================================
# 3bis. CHARGEMENT DEPUIS POSTGRESQL (nouvelle source, en plus de load_data())
# =============================================================================

def _get_postgres_config():
    """
    Lit les paramètres de connexion PostgreSQL depuis .streamlit/secrets.toml
    (section [postgres]) si présents, sinon utilise les valeurs par défaut du
    conteneur Docker local `sdr-postgres` créé pour le développement.
    """
    defaults = {
        "host": "localhost",
        "port": "5432",
        "dbname": "profilage",
        "user": "sdr_admin",
        "password": "sdr_dev_password",
    }
    try:
        if "postgres" in st.secrets:
            return {**defaults, **dict(st.secrets["postgres"])}
    except Exception:
        pass
    return defaults


@st.cache_data(ttl=60)
def load_data_postgres():
    """
    Charge les données joueurs depuis la base PostgreSQL (schéma flexible :
    tables `joueurs` + `sessions` + `mesures`) et renvoie un DataFrame avec
    les MÊMES noms de colonnes que load_data() (les noms d'origine du
    fichier Excel / Google Sheet), pour pouvoir comparer ou remplacer
    facilement l'une par l'autre dans le reste de l'app.

    La table `mesures` stocke une ligne par test (colonne, valeur) plutôt
    qu'une colonne SQL par test : on la "repivote" ici en DataFrame large,
    une colonne par test -- comme un fichier Excel classique.

    Ne remplace PAS load_data() : les deux fonctions coexistent.
    """
    from sqlalchemy import create_engine
    from database.column_mapping import IDENTITY_COLUMNS_REVERSE, SESSION_COLUMNS_REVERSE

    cfg = _get_postgres_config()
    url = f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"

    try:
        engine = create_engine(url)

        # 1. Identité + session : une ligne par (joueur, session), comme le sheet d'origine
        df_meta = pd.read_sql(
            """
            SELECT s.id AS session_id, j.nom, j.n_gps, j.lateralite, j.poste, j.position,
                   j.date_de_naissance, j.equipe, s.session_label, s.session_date
            FROM sessions s
            JOIN joueurs j ON j.id = s.joueur_id
            """,
            engine,
        )

        # 2. Toutes les mesures, en format long (une ligne par test)
        df_long = pd.read_sql(
            "SELECT session_id, nom_test, valeur_num, valeur_texte FROM mesures",
            engine,
        )
    except Exception as e:
        return pd.DataFrame(), f"Erreur PostgreSQL : {e}"

    if df_meta.empty:
        return pd.DataFrame(), "PostgreSQL"

    # On combine valeur_num/valeur_texte en une seule colonne, puis on repivote
    # nom_test en colonnes -- chaque nom_test redevient un nom de colonne Excel
    df_long["valeur"] = df_long["valeur_num"].astype(object)
    mask_texte = df_long["valeur"].isna() & df_long["valeur_texte"].notna()
    df_long.loc[mask_texte, "valeur"] = df_long.loc[mask_texte, "valeur_texte"]

    if not df_long.empty:
        df_wide = df_long.pivot_table(
            index="session_id", columns="nom_test", values="valeur", aggfunc="first"
        ).reset_index()
    else:
        df_wide = pd.DataFrame({"session_id": []})

    df = df_meta.merge(df_wide, on="session_id", how="left").drop(columns=["session_id"])

    # On renomme les colonnes SQL d'identité/session vers les noms Excel d'origine
    # (les colonnes de tests portent déjà leur nom Excel d'origine : rien à faire)
    rename_map = {**IDENTITY_COLUMNS_REVERSE, **SESSION_COLUMNS_REVERSE}
    df = df.rename(columns=rename_map)

    if "Joueur" in df.columns:
        df = df.dropna(subset=["Joueur"])
        df["Joueur"] = df["Joueur"].astype(str).str.strip()

    return df, "PostgreSQL"

# =============================================================================
# 4. GÉNÉRATION DE GRAPHIQUES (RADAR)
# =============================================================================
# NB : le radar matplotlib réellement utilisé pour le rapport PDF/HTML vit dans
# profiling_report.py (create_radar_chart). La copie qui était ici n'était
# jamais appelée (code mort) et a été supprimée — voir charts.py pour les
# radars Plotly de l'app.


def get_kpi_card_html(label, val_display, unit_display, norm_color, pct_color, pct_html, status_text, norm_tooltip, tip, subtitle_html=""):
    """Template HTML pur pour une carte KPI individuelle."""
    # Remplacer SDR_RED par ta couleur personnalisée ici si besoin (ex: #333333)
    title_color = "#090809" 
    
    return f"""
    <div class='kpi-card' style='width: 100%; padding: 15px; margin-bottom: 20px; background: white; border-radius: 12px; border: 1px solid #eee; border-left: 6px solid {norm_color}; border-right: 6px solid {pct_color}; box-shadow: 0 4px 10px rgba(0,0,0,0.05);' {tip}>
        <div style='font-size:14px; font-weight:900; color:{title_color}; text-transform:uppercase; margin-bottom:12px; text-align:center;'>
            {label}{subtitle_html}
        </div>
        <div style='text-align:center; margin-bottom:15px;'>
            <div style='font-size:9px; color:#707070; text-transform:uppercase; font-weight:bold; letter-spacing:1px; margin-bottom:2px;'>Valeur</div>
            <div style='font-size:32px; font-weight:900; color:#111; line-height:1;'>
                {val_display} <span style='font-size:14px; color:#666;'>{unit_display}</span>
            </div>
        </div>
        <div style='display:flex; justify-content:space-between; align-items:flex-end; border-top:1px solid #f0f0f0; padding-top:10px;'>
            <div style='text-align:left;'>
                <div style='font-size:9px; color:#707070; text-transform:uppercase; font-weight:bold;'>Objectif</div>
                <div style='font-size:11px; font-weight:bold; color:{norm_color}; cursor:help;' title='{norm_tooltip}'>
                    {status_text} <span style='font-size:9px;'>ℹ️</span>
                </div>
            </div>
            <div style='text-align:right;'>
                <div style='font-size:9px; color:#707070; text-transform:uppercase; font-weight:bold;'>Classement</div>
                {pct_html}
            </div>
        </div>
    </div>
    """