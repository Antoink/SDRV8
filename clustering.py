import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
# scikit-learn N'EST PAS importé ici au niveau module, volontairement :
# clustering.py est importé sans condition au démarrage de l'appli (via
# profiling.py -> main.py), donc un `import sklearn...` ici retardait le
# LANCEMENT de l'appli pour TOUT LE MONDE (import lourd : scipy, joblib,
# threadpoolctl...), même pour un usage qui ne visite jamais cet onglet.
# Les imports sklearn sont donc faits localement, dans chaque fonction qui
# en a besoin (_suggest_best_k, _cluster_stability, show_clustering_page) --
# le coût ne survient qu'à la première ouverture réelle de cet onglet, et
# les imports suivants sont instantanés (module déjà en cache Python).
from scipy import stats as scipy_stats
from scipy.spatial import ConvexHull, QhullError

from charts import build_radar, SDR_BLUE
from comparateur import calculate_percentile

SDR_RED = "#D71920"
# Même bleu que partout ailleurs dans l'app (charts.py) -- avant, ce module
# utilisait un bleu légèrement différent (#3498DB) pour ses marqueurs, ce qui
# cassait la cohérence des couleurs d'une page à l'autre.
SUP_BLUE = SDR_BLUE

# =============================================================================
# CADRAGE SCIENTIFIQUE DE CETTE PAGE
# =============================================================================
# La méthode (standardisation Z-score -> K-Means sur l'espace complet -> ACP
# utilisée UNIQUEMENT pour la visualisation 2D du même clustering) suit la
# même logique que celle publiée par de Haan et al. (2025, Journal of Sports
# Science and Medicine, 24, 565-577) pour catégoriser des joueurs de football
# par profil physique via K-Means plutôt que par poste. Cette référence sert
# de point d'ancrage pour :
#  - le choix de K (silhouette + coude, comme dans l'article),
#  - le test de stabilité des classes (l'article relance le K-Means 1000 fois
#    et vérifie la cohérence de l'assignation des joueurs -> ici, on relance
#    sur des versions légèrement bruitées des données et on mesure l'accord
#    avec l'Adjusted Rand Index),
#  - le rappel que la puissance statistique d'une analyse de clusters dépend
#    surtout de la SÉPARATION entre les groupes (silhouette), pas de la
#    taille d'échantillon en tant que telle (Dalmaijer, Nord & Astle, 2022,
#    BMC Bioinformatics, 23, 205) — ce qui nuance, sans l'annuler, l'usage
#    prudent qu'il faut avoir de petits effectifs par classe.
# =============================================================================


@st.cache_data
def _suggest_best_k(temp_df: pd.DataFrame):
    """
    Suggère un nombre de clusters (K) via un score de silhouette (teste
    K=2..5), et renvoie aussi les scores testés (pour affichage) ainsi que
    l'inertie (méthode du coude). Mis en cache : ce calcul (KNN + K-Means
    répété) se refaisait sans arrêt à chaque interaction sur la page (tri,
    filtre, etc.) même quand les données filtrées n'avaient pas changé.
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.impute import KNNImputer
    from sklearn.metrics import silhouette_score

    best_k, best_score = 3, -1
    scores, inertias = {}, {}
    try:
        if len(temp_df) >= 4:
            X_temp = KNNImputer(n_neighbors=min(3, len(temp_df))).fit_transform(temp_df)
            X_temp_scaled = StandardScaler().fit_transform(X_temp)
            for k in range(2, min(6, len(X_temp_scaled))):
                km = KMeans(n_clusters=k, n_init='auto', random_state=42).fit(X_temp_scaled)
                score = silhouette_score(X_temp_scaled, km.labels_)
                scores[k] = score
                inertias[k] = km.inertia_
                if score > best_score:
                    best_k, best_score = k, score
    except Exception:
        pass
    return best_k, best_score, scores, inertias


@st.cache_data
def _cluster_stability(X_scaled, n_clusters, n_reps=40, noise_frac=0.05, seed=42):
    """
    Teste la robustesse du clustering plutôt que de se fier à un seul
    résultat : on relance K-Means n_reps fois sur des versions légèrement
    bruitées des données (bruit gaussien ~5% de l'écart-type de chaque
    variable — l'équivalent numérique de la variabilité jour-à-jour d'un
    test physique), et on mesure l'accord entre chaque relance et le
    clustering de référence avec l'Adjusted Rand Index (ARI).
    ARI = 1 : les mêmes joueurs se retrouvent TOUJOURS ensemble, quelle que
              soit la petite perturbation -> classes robustes.
    ARI = 0 : l'accord n'est pas meilleur qu'un regroupement au hasard.
    Inspiré de la vérification de cohérence (1000 relances) faite par
    de Haan et al. (2025, JSSM) sur leur propre clustering de joueurs.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score

    X = np.asarray(X_scaled)
    rng = np.random.default_rng(seed)
    ref_labels = KMeans(n_clusters=n_clusters, n_init='auto', random_state=seed).fit_predict(X)
    stds = X.std(axis=0)
    aris = []
    for i in range(n_reps):
        noise = rng.normal(0, noise_frac * stds, size=X.shape)
        labels_i = KMeans(n_clusters=n_clusters, n_init='auto', random_state=seed + i + 1).fit_predict(X + noise)
        aris.append(adjusted_rand_score(ref_labels, labels_i))
    return float(np.mean(aris)), float(np.std(aris))


def _stability_reading(ari):
    if ari >= 0.75:
        return "🟢 Élevée", "Les mêmes joueurs se retrouvent presque toujours dans la même classe, même avec de petites variations dans les données. Regroupement fiable."
    if ari >= 0.5:
        return "🟠 Modérée", "L'essentiel des joueurs reste groupé de façon cohérente, mais quelques cas proches d'une frontière entre classes peuvent changer de groupe selon la mesure exacte. À interpréter avec un peu de recul."
    return "🔴 Faible", "Le regroupement est sensible à de petites variations des données — probablement parce que les classes ne sont pas franchement séparées (peu de joueurs, variables peu discriminantes, ou variables actives trop corrélées entre elles). Traiter les classes comme indicatives, pas comme un verdict."


def _silhouette_reading(score):
    # Échelle usuelle (Kaufman & Rousseeuw) : > 0.7 structure forte, 0.5-0.7
    # raisonnable, 0.25-0.5 faible mais réelle, < 0.25 pas de structure
    # franche. de Haan et al. (2025) rapportent 0.34 sur un échantillon de
    # taille comparable et l'interprètent comme "hétérogène mais avec des
    # sous-groupes distincts et non chevauchants" -> un score modeste
    # n'invalide pas l'analyse, il invite à la prudence.
    if score >= 0.5:
        return "les classes sont bien séparées."
    if score >= 0.25:
        return "les classes sont réelles mais se chevauchent partiellement (cas fréquent avec des profils physiques d'une même équipe) — comme dans de Haan et al. (2025), qui rapportent un score comparable sur un effectif de taille proche."
    return "les classes se chevauchent beaucoup — à ce niveau, les regrouper reste utile pour explorer les données, mais ne doit pas être présenté comme une catégorisation tranchée."


def _plain_language_cluster_summary(diff_row, threshold=12, max_vars=3):
    """
    Résumé en une phrase, en langage clair, d'une classe -- pour un lecteur
    non-analyste (staff pressé, direction...) qui ne va pas déchiffrer
    "VMA ▲ · Sit and Reach ▼". Reprend la même logique de seuil que
    _label_cluster (variables qui écartent la classe d'au moins `threshold`%
    de la moyenne du groupe), mais formule une phrase au lieu d'un tag.
    """
    sorted_row = diff_row.reindex(diff_row.abs().sort_values(ascending=False).index)
    forts, faibles = [], []
    for var, val in sorted_row.items():
        if len(forts) + len(faibles) >= max_vars or abs(val) < threshold:
            break
        (forts if val > 0 else faibles).append(var)
    if not forts and not faibles:
        return "Profil proche de la moyenne du groupe sur les variables actives -- pas de trait dominant."
    bits = []
    if forts:
        bits.append("plutôt fort en " + ", ".join(forts))
    if faibles:
        bits.append("plus faible en " + ", ".join(faibles))
    return "Profil " + " ; ".join(bits) + "."


def _label_cluster(diff_row, threshold=12):
    """
    Étiquette indicative d'une classe à partir des 1-2 variables qui
    l'écartent le plus de la moyenne du groupe (au-dessus ou en-dessous).
    Pure aide de lecture, générée automatiquement -> à renommer par le staff
    si besoin (voir de Haan et al. 2025, qui nomment ainsi leurs 5 classes :
    "Sprint", "Endurance haute intensité"... plutôt que "Cluster 1, 2, 3").
    """
    sorted_row = diff_row.reindex(diff_row.abs().sort_values(ascending=False).index)
    parts = []
    for var, val in sorted_row.items():
        if len(parts) >= 2 or abs(val) < threshold:
            break
        arrow = "▲" if val > 0 else "▼"
        parts.append(f"{var} {arrow}")
    return " · ".join(parts) if parts else "proche de la moyenne du groupe"


def _anova_pvalue(df_analyse, var, cluster_col='Cluster'):
    """p-value du test (Kruskal-Wallis, non-paramétrique) comparant `var`
    entre les classes — indique si la différence visible sur le graphique de
    profil est statistiquement défendable ou peut s'expliquer par le hasard
    de l'échantillonnage (pertinent vu les petits effectifs par classe)."""
    groups = [g[var].dropna().values for _, g in df_analyse.groupby(cluster_col) if len(g) >= 2]
    if len(groups) < 2 or any(len(g) < 2 for g in groups):
        return None
    try:
        _, p = scipy_stats.kruskal(*groups)
        return p
    except Exception:
        return None


def _explain(title, body_md, expanded=False):
    """Bloc d'explication pédagogique replié sous chaque graphique."""
    with st.expander(f"🔍 {title}", expanded=expanded):
        st.markdown(body_md)


def show_clustering_page(df_raw):
    # Import paresseux de sklearn (voir note en haut du fichier) : ne coûte
    # que la première fois que cet onglet est réellement ouvert.
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    from sklearn.impute import KNNImputer
    from sklearn.metrics import silhouette_score
    import plotly.express as px

    st.markdown(f"""
        <style>
        .stApp {{
            background-color: #f4f6f9;
            font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: #111 !important;
            font-weight: 900 !important;
            letter-spacing: -0.02em;
            text-transform: uppercase;
        }}
        div.stButton > button:first-child {{
            background-color: {SDR_RED};
            color: white;
            border-radius: 8px;
            font-weight: 900;
            padding: 0.6rem 1.2rem;
            border: none;
            box-shadow: 0 4px 10px rgba(215, 25, 32, 0.2);
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #b0141a;
            transform: translateY(-3px);
            box-shadow: 0 8px 15px rgba(215, 25, 32, 0.3);
        }}
        .metric-card {{
            background-color: #ffffff;
            padding: 24px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            text-align: center;
            border: 1px solid #f0f0f0;
            transition: all 0.3s ease;
        }}
        .metric-value {{
            font-size: 2.5rem;
            font-weight: 900;
            color: {SDR_RED};
            margin: 0 0 5px 0;
        }}
        .metric-label {{
            font-size: 0.85rem;
            font-weight: bold;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 0;
        }}
        .metric-title {{
            font-size: 1.3rem;
            font-weight: 900;
            color: #111;
            margin-top: 15px;
            text-transform: uppercase;
        }}
        .id-card {{
            background:#fff; border-radius:10px; padding:14px 10px; text-align:center;
            border:1px solid #eee; box-shadow:0 2px 8px rgba(0,0,0,0.03);
        }}
        .id-card .v {{ font-size:1.6rem; font-weight:900; color:#111; }}
        .id-card .l {{ font-size:0.72rem; font-weight:700; color:#666; text-transform:uppercase; letter-spacing:0.5px; }}
        </style>
    """, unsafe_allow_html=True)

    with st.expander("🎓 Qu'est-ce que ce module et comment l'utiliser ?", expanded=True):
        st.markdown("""
Ce module regroupe automatiquement des joueurs (ou des tests) qui se
ressemblent statistiquement, **sans a priori sur le poste** — l'idée n'est
pas de remplacer le regroupement par poste, mais de vérifier s'il reflète
vraiment les profils physiques, ou si des joueurs de postes différents se
ressemblent plus entre eux que deux joueurs du même poste. C'est exactement
la démarche validée par une étude récente sur des footballeurs élites
([de Haan et al., 2025, *Journal of Sports Science and Medicine*](https://doi.org/10.52082/jssm.2025.565)) :
les auteurs montrent qu'à l'intérieur d'un même poste, la variabilité
individuelle de charge de course est souvent aussi grande qu'*entre* les
postes — et que regrouper les joueurs par profil physique (via K-Means)
donne des groupes plus homogènes et plus utiles pour cibler l'entraînement
qu'un regroupement par poste.

**En 3 étapes :**
1. **Choisir les joueurs et les tests** à analyser (ci-dessous).
2. **Lancer l'analyse** : l'algorithme calcule la distance statistique entre
   chaque joueur (ou chaque test) sur l'ensemble des variables choisies, et
   forme des groupes ("classes") de joueurs proches les uns des autres.
3. **Lire les résultats** : chaque graphique a son propre bloc *"🔍 Comment
   lire ce graphique"* juste en-dessous, avec les noms des joueurs concernés
   par le résultat courant.

**Deux modes possibles :**
- **Profilage Joueurs** : regroupe les LIGNES (les joueurs) — "quels joueurs
  se ressemblent le plus, tous tests confondus ?"
- **Analyse des Tests** : regroupe les COLONNES (les tests) — "quels tests
  mesurent en fait la même chose ?" (utile pour repérer des redondances dans
  ta batterie de tests).

**Important — ce que ça n'est PAS :** un classement de "meilleur" à "moins
bon". Les classes n'ont pas d'ordre : "Classe 1" n'est pas supérieure à
"Classe 3", ce sont juste des étiquettes numériques arbitraires attribuées
par l'algorithme. Un résumé du **profil** de chaque classe (quelles
variables la caractérisent) est affiché automatiquement pour donner un sens
concret à chaque groupe.
        """)

    # NB: df_raw vient déjà de utils.load_data() (mis en cache, source Google
    # Sheets/Postgres/Excel selon la config) — on ne le relit plus depuis un
    # fichier Excel local ici, pour éviter (a) de contourner le cache et
    # (b) d'afficher des données périmées si la vraie source a changé.
    if df_raw.empty or "Joueur" not in df_raw.columns:
        st.warning("Données insuffisantes ou colonne 'Joueur' manquante.")
        return

    df_raw = df_raw.dropna(subset=['Joueur']).copy()

    # --- CORRECTION DES FILTRES INVISIBLES ---
    # On remplace les cases vides par "Non renseigné" pour qu'elles apparaissent dans le filtre
    if "Equipe" in df_raw.columns:
        df_raw["Equipe"] = df_raw["Equipe"].fillna("Non renseigné").astype(str).str.strip().str.upper()
        df_raw["Equipe"] = df_raw["Equipe"].replace({'NAN': "Non renseigné", 'NONE': "Non renseigné"})
        equipes_uniques = sorted(list(df_raw["Equipe"].unique()))
    else:
        equipes_uniques = []

    if "Position" in df_raw.columns:
        df_raw["Position"] = df_raw["Position"].fillna("Non renseigné").astype(str).str.strip().str.upper()
        df_raw["Position"] = df_raw["Position"].replace({'NAN': "Non renseigné", 'NONE': "Non renseigné"})
        postes_uniques = sorted(list(df_raw["Position"].unique()))
    else:
        postes_uniques = []

    if "Session" in df_raw.columns:
        df_raw["Session"] = df_raw["Session"].fillna("Non renseigné").astype(str).str.strip()
        sessions_uniques = sorted(list(df_raw["Session"].unique()))
    else:
        sessions_uniques = []

    st.markdown(f"<h2 style='color:{SDR_RED};'>1. Ciblage de la population</h2>", unsafe_allow_html=True)
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1: choix_equipe = st.multiselect("Équipe(s)", equipes_uniques, default=equipes_uniques)
    with col_f2: choix_poste = st.multiselect("Position(s)", postes_uniques, default=postes_uniques)
    with col_f3: choix_session = st.multiselect("Session(s)", sessions_uniques, default=sessions_uniques)

    df_filtered = df_raw.copy()
    if "Equipe" in df_filtered.columns and choix_equipe: df_filtered = df_filtered[df_filtered["Equipe"].isin(choix_equipe)]
    if "Position" in df_filtered.columns and choix_poste: df_filtered = df_filtered[df_filtered["Position"].isin(choix_poste)]
    if "Session" in df_filtered.columns and choix_session: df_filtered = df_filtered[df_filtered["Session"].isin(choix_session)]

    # --- SÉLECTION MANUELLE DE JOUEURS PRÉCIS (dans TOUT le club, indépendamment
    # des filtres équipe/position ci-dessus) --- pour comparer par exemple 2-3
    # joueurs Élite/Espoir surclassés à un groupe PRO, sans devoir inclure toute
    # leur équipe d'origine.
    tous_joueurs_club = sorted(df_raw['Joueur'].dropna().unique())
    joueurs_manuels = st.multiselect(
        "Restreindre à des joueurs précis (optionnel — cherche dans tout le club, indépendamment des filtres ci-dessus) :",
        tous_joueurs_club,
        default=[],
        help="Laisser vide pour garder la population définie par les filtres Équipe/Position/Session ci-dessus. Si tu sélectionnes des joueurs ici, SEULS ces joueurs seront analysés (les filtres ci-dessus sont ignorés pour eux).",
    )
    if joueurs_manuels:
        df_filtered = df_raw[df_raw['Joueur'].isin(joueurs_manuels)].copy()
        if "Session" in df_filtered.columns and choix_session:
            df_filtered = df_filtered[df_filtered["Session"].isin(choix_session)]
        st.caption(f"→ Analyse restreinte à {len(joueurs_manuels)} joueur(s) sélectionné(s) manuellement, quelle que soit leur équipe.")

    colonnes_texte = ['Joueur', 'N° GPS', 'Latéralité', 'Poste', 'Position', 'Date de Naissance', 'Equipe', 'Session exact', 'Session', 'Player ID', 'Numero', 'Pied départ 1080', 'Pied départ']

    # --- CORRECTION DU NETTOYAGE NUMERIQUE ---
    for col in df_filtered.columns:
        if col not in colonnes_texte:
            if df_filtered[col].dtype == object or pd.api.types.is_string_dtype(df_filtered[col]):
                cleaned = df_filtered[col].astype(str).str.replace(r'[\s \xa0]+', '', regex=True).str.replace(',', '.', regex=False)
                cleaned = cleaned.replace(['-', '', 'nan', 'None', '#VALEUR!', '#DIV/0!'], np.nan)
                df_filtered[col] = pd.to_numeric(cleaned, errors='coerce')
            else:
                df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce')

    st.markdown("---")
    st.markdown(f"<h2 style='color:{SDR_RED};'>2. Sélection des Variables</h2>", unsafe_allow_html=True)

    seuil_na = st.slider("Tolérance aux données manquantes par test (%)", 10, 100, 95)

    colonnes_interdites = [
        'Joueur', 'Player ID', 'N° GPS', 'Latéralité', 'Poste', 'Position',
        'Date de Naissance', 'DT exact', 'Session exact', 'Session', 'Equipe', 'Numero', 'Pied départ 1080', 'Pied départ'
    ]

    available_vars = [
        v for v in df_filtered.columns
        if pd.api.types.is_numeric_dtype(df_filtered[v])
        and (df_filtered[v].isna().mean() * 100) <= seuil_na
        and v not in colonnes_interdites
    ]

    vars_pca_actives = st.multiselect(
        "Variables quantitatives ACTIVES (Servent au calcul de l'ACP) :",
        available_vars,
        default=available_vars[:5] if len(available_vars) >= 5 else available_vars
    )

    vars_sup_quant = st.multiselect(
        "Variables quantitatives SUPPLÉMENTAIRES (Affichées en pointillés, ignorées dans le calcul) :",
        [v for v in available_vars if v not in vars_pca_actives]
    )

    colonnes_qualitatives = [col for col in df_filtered.columns if col in colonnes_texte and col != 'Joueur']
    vars_sup_actives = st.multiselect(
        "Variables de contexte pour l'affichage (Qualitatives) :",
        colonnes_qualitatives,
        default=[c for c in ['Poste', 'Position', 'Session', 'Equipe'] if c in colonnes_qualitatives]
    )

    _explain("Pourquoi standardiser (Z-score) avant de comparer les joueurs ?", """
Un CMJ se mesure en centimètres (~30-45), une VMA en km/h (~14-18), une force
en newtons (~2000-9000). Si on calculait une distance brute entre joueurs sur
ces chiffres tels quels, la force (grands nombres) écraserait totalement le
CMJ dans le calcul, sans raison physiologique. La **standardisation Z-score**
ramène chaque variable à la même échelle (moyenne 0, écart-type 1) avant de
comparer les joueurs — chaque test compte alors pour un poids équivalent
dans le regroupement, quelle que soit son unité d'origine. C'est fait
automatiquement dans cette page (`StandardScaler`), avant le K-Means.
    """)

    # --- CORRECTION DE L'ALERTE DE DONNEES ---
    best_k, best_silhouette, silhouette_scores, inertias = 3, None, {}, {}
    if len(vars_pca_actives) >= 2:
        # On remplace les 0 par NaN, et how='all' garde les joueurs qui ont au moins 1 test réussi
        temp_df = df_filtered[vars_pca_actives].apply(pd.to_numeric, errors='coerce').replace(0, np.nan).dropna(how='all')

        if len(temp_df) > 0:
            n_obs, n_vars = len(temp_df), len(vars_pca_actives)
            ratio = n_obs / n_vars if n_vars else 0

            corr_matrix = temp_df.corr().abs()
            np.fill_diagonal(corr_matrix.values, 0)
            paires_colineaires = [(a, b, corr_matrix.loc[a, b]) for a in corr_matrix.columns for b in corr_matrix.columns if a < b and corr_matrix.loc[a, b] > 0.85]
            if paires_colineaires:
                paires_txt = ", ".join(f"« {a} » / « {b} » (r={r:.2f})" for a, b, r in paires_colineaires[:4])
                st.warning(f"⚠️ Multicolinéarité détectée : {paires_txt} sont corrélées à plus de 0.85 — voir l'explication ci-dessous pour ce que ça change concrètement dans le résultat.")
                _explain("Multicolinéarité : pourquoi c'est un problème pour le clustering ?", f"""
Deux variables corrélées à plus de 0.85 (ex : {paires_colineaires[0][0]} et {paires_colineaires[0][1]}, r={paires_colineaires[0][2]:.2f}) racontent
en grande partie **la même histoire** sur un joueur — s'il est fort sur
l'une, il l'est presque automatiquement sur l'autre.

**Ce que ça cause concrètement ici :**
- **Un test compte "deux fois" sans le vouloir.** La distance entre deux
  joueurs (celle utilisée par le K-Means pour former les classes) s'obtient
  en additionnant l'écart sur CHAQUE variable active. Si deux variables sont
  quasi-redondantes, l'écart qu'elles mesurent est compté deux fois dans le
  total, alors qu'un écart tout aussi réel sur une variable non corrélée
  n'est compté qu'une fois. Le regroupement final se retrouve orienté, sans
  que ce soit voulu, vers la qualité physique mesurée par les variables
  redondantes, au détriment des autres.
- **Le cercle des corrélations et la matrice de contribution (plus bas sur
  cette page) en sont aussi affectés** : deux variables redondantes
  pointent dans la même direction et "gonflent" ensemble l'importance
  apparente d'un seul axe (une seule composante principale), ce qui peut
  donner l'impression trompeuse qu'une qualité physique domine l'analyse
  alors que c'est en fait un doublon de mesure.

**Que faire ?** Retirer une des deux variables corrélées (garder celle la
plus fiable/la plus directement interprétable), ou les laisser si c'est un
choix assumé (ex : tu veux volontiers donner plus de poids à l'explosivité
en gardant plusieurs tests qui la mesurent).
                """)

            if n_vars > 0:
                if ratio < 3:
                    st.error(f"🚫 Rapport joueurs/variables trop faible : {n_obs} joueur(s) pour {n_vars} variable(s) actives ({ratio:.1f} joueur(s) par variable). En-dessous de 3 joueurs par variable, le résultat n'est pas exploitable — voir l'explication ci-dessous.")
                elif ratio < 5:
                    st.warning(f"⚠️ Rapport joueurs/variables limite : {n_obs} joueur(s) pour {n_vars} variable(s) actives ({ratio:.1f} joueur(s) par variable). Sous le seuil usuel de 5 joueurs par variable — voir l'explication ci-dessous.")

                _explain("Trop de variables, pas assez de joueurs : pourquoi c'est un problème ?", f"""
**Situation actuelle : {n_obs} joueur(s) pour {n_vars} variable(s) actives,
soit {ratio:.1f} joueur(s) par variable.**

Une règle de base en statistique multivariée (ACP, clustering) est de
disposer d'au moins **5 observations par variable active** pour que
l'analyse soit réellement interprétable (dans l'idéal, 10 pour 1) — c'est le
même principe qui explique pourquoi on ne peut pas tracer une droite fiable
à partir de 2 points, en pire : ici, chaque variable ajoute une dimension
dans laquelle les points (les joueurs) peuvent se disperser.

**Ce que ça cause concrètement quand ce n'est pas respecté :**
- **La distance entre joueurs perd son sens** ("fléau de la dimension") :
  avec beaucoup de variables et peu de joueurs, presque tous les joueurs
  finissent par être à peu près aussi éloignés les uns des autres dans
  l'espace standardisé — le K-Means peine alors à trouver de vrais groupes
  et peut en inventer là où il n'y en a pas.
- **Les classes obtenues sont instables** : un seul joueur qui change (une
  nouvelle session, une donnée corrigée) peut faire basculer complètement le
  résultat — regarde l'indicateur de stabilité (ARI) plus bas une fois
  l'analyse lancée : c'est justement le symptôme le plus visible de ce
  problème.
- **L'ACP devient peu fiable** : avec autant (ou plus) de variables que de
  joueurs, l'ACP peut "expliquer" 100% de la variance de façon quasi
  triviale (autant d'axes que de joueurs), sans que ça reflète une vraie
  structure dans les données.

**Solutions :** réduire le nombre de variables actives (garder les tests les
plus pertinents/les moins redondants — voir aussi la multicolinéarité
ci-dessus), et/ou élargir la population analysée (inclure plus de sessions
ou plus de joueurs, avec les filtres de l'étape 1).
                """)

            joueurs_complets = temp_df.dropna(how='any').shape[0]
            if joueurs_complets < len(temp_df):
                st.info(f"ℹ️ {len(temp_df) - joueurs_complets} joueur(s) ont des cases vides ou des 0. L'intelligence artificielle (KNN, 3 plus proches voisins) les a estimés pour qu'ils s'affichent sur le graphique — voir le bloc d'explication ci-dessous.")

            best_k, best_silhouette, silhouette_scores, inertias = _suggest_best_k(temp_df)

    if silhouette_scores:
        k_txt = ", ".join(f"K={k} → {s:.2f}" for k, s in silhouette_scores.items())
        _explain("Comment le nombre de classes (K) est-il choisi par défaut ?", f"""
Le nombre de classes proposé par défaut (**K = {best_k}**) n'est pas arbitraire :
il vient du **score de silhouette**, testé pour chaque valeur de K entre 2 et 5
(comme le recommande la même étude de référence) : {k_txt}.

Un score de silhouette mesure, pour chaque joueur, à quel point il est plus
proche des joueurs de SA classe que de ceux des AUTRES classes (échelle de
-1 à +1). Ici, le meilleur score est {best_silhouette:.2f} pour K={best_k} :
{_silhouette_reading(best_silhouette)}

**Tu peux changer K manuellement** (champ "Nombre de groupes" ci-dessous) —
la suggestion automatique est un point de départ, pas une obligation. Un K
plus petit donne des groupes plus larges et plus faciles à interpréter ; un K
plus grand donne des groupes plus fins mais avec moins de joueurs chacun (et
donc moins fiables statistiquement).
        """)

    st.markdown("---")
    st.markdown(f"<h2 style='color:{SDR_RED};'>3. Paramétrage de l'Analyse</h2>", unsafe_allow_html=True)

    col_mode, col_clusters, col_btn = st.columns([2, 1, 1])
    with col_mode:
        mode_analyse = st.radio("Cible de l'algorithme K-Means :", ["👤 Profilage Joueurs (Regrouper les individus)", "📊 Analyse des Tests (Regrouper les variables)"])
    with col_clusters:
        n_clusters = st.number_input("Nombre de groupes", min_value=2, max_value=8, value=best_k)
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_run = st.button("LANCER L'ANALYSE", width='stretch')

    # --- CORRECTION DU CALCUL PCA ET KNN ---
    if btn_run:
        if len(vars_pca_actives) < 2:
            st.error("Sélectionnez au minimum 2 variables actives.")
        else:
            with st.spinner('Calcul de l\'ACP et clustering en cours...'):
                cols_to_keep = ['Joueur'] + vars_sup_actives + vars_pca_actives + vars_sup_quant
                cols_to_keep = list(dict.fromkeys(cols_to_keep))

                df_analyse = df_filtered[cols_to_keep].copy().replace(r'^\s*$', np.nan, regex=True)

                for col in vars_pca_actives + vars_sup_quant:
                    df_analyse[col] = pd.to_numeric(df_analyse[col], errors='coerce').replace(0, np.nan)

                    df_analyse = df_analyse.reset_index(drop=True)

                # Le point clé : how='all' pour garder Zohouri et les autres
                df_analyse = df_analyse.dropna(subset=vars_pca_actives, how='all').reset_index(drop=True)

                if len(df_analyse) >= max(n_clusters, 2):
                    X_raw = df_analyse[vars_pca_actives]

                    # INTELLIGENCE ARTIFICIELLE
                    imputer = KNNImputer(n_neighbors=min(3, len(X_raw)))
                    X_imputed = imputer.fit_transform(X_raw)

                    df_analyse[vars_pca_actives] = X_imputed

                    X_scaled = StandardScaler().fit_transform(X_imputed)

                    pca = PCA(n_components=len(vars_pca_actives))
                    pca_result = pca.fit_transform(X_scaled)

                    st.session_state.update({
                        'df_analyse_complet': df_filtered,
                        'df_analyse': df_analyse,
                        'X_scaled': X_scaled,
                        'vars_pca_actives': vars_pca_actives,
                        'vars_sup_quant': vars_sup_quant,
                        'pca_model': pca,
                        'pca_result': pca_result,
                        'analyse_terminee': True
                    })

                    if mode_analyse == "👤 Profilage Joueurs (Regrouper les individus)":
                        df_analyse['Cluster'] = KMeans(n_clusters=n_clusters, n_init='auto', random_state=42).fit_predict(X_scaled) + 1
                        df_analyse['Cluster'] = df_analyse['Cluster'].astype(str)
                        st.session_state['mode_run'] = 'joueurs'
                        stab_mean, stab_std = _cluster_stability(X_scaled, n_clusters)
                        st.session_state['stability'] = (stab_mean, stab_std)
                        sil = silhouette_score(X_scaled, KMeans(n_clusters=n_clusters, n_init='auto', random_state=42).fit_predict(X_scaled)) if len(df_analyse) > n_clusters else None
                        st.session_state['silhouette_run'] = sil
                    else:
                        var_clusters = KMeans(n_clusters=n_clusters, n_init='auto', random_state=42).fit_predict(X_scaled.T) + 1
                        df_vars = pd.DataFrame({'Variable': vars_pca_actives, 'Cluster': var_clusters.astype(str)})
                        st.session_state['df_vars'] = df_vars
                        st.session_state['mode_run'] = 'tests'
                    st.session_state['df_analyse'] = df_analyse
                else:
                    st.error(f"Volume de données insuffisant : {len(df_analyse)} joueur(s) valides.")

    # ================= AFFICHAGE DES RÉSULTATS =================
    if st.session_state.get('analyse_terminee', False):
        st.markdown("---")
        df_analyse, pca = st.session_state['df_analyse'], st.session_state['pca_model']
        vars_pca_actives = st.session_state['vars_pca_actives']
        vars_sup_quant = st.session_state.get('vars_sup_quant', [])
        pca_result = st.session_state['pca_result']
        mode_run = st.session_state.get('mode_run', 'joueurs')

        n_comp = pca.n_components_
        colors = [SDR_RED, "#111111", "#888888", "#F39C12", "#27AE60", "#3498DB", "#9B59B6", "#34495E"]

        # --- CARTE D'IDENTITÉ DE L'ANALYSE ---
        # Un résumé chiffré de la fiabilité de CE run précis, à lire avant les
        # graphiques eux-mêmes : combien de joueurs, combien de variance
        # réellement capturée par les 2 axes affichés, et (en mode joueurs)
        # la stabilité du regroupement.
        var_2d = pca.explained_variance_ratio_[:2].sum() * 100 if n_comp >= 2 else pca.explained_variance_ratio_[0] * 100
        id_cols = st.columns(4 if mode_run == 'joueurs' else 3)
        with id_cols[0]:
            st.markdown(f"<div class='id-card'><div class='v'>{len(df_analyse)}</div><div class='l'>Joueurs analysés</div></div>", unsafe_allow_html=True)
        with id_cols[1]:
            st.markdown(f"<div class='id-card'><div class='v'>{len(vars_pca_actives)}</div><div class='l'>Variables actives</div></div>", unsafe_allow_html=True)
        with id_cols[2]:
            st.markdown(f"<div class='id-card'><div class='v'>{var_2d:.0f}%</div><div class='l'>Variance visible en 2D</div></div>", unsafe_allow_html=True)
        if mode_run == 'joueurs':
            stab_mean, _ = st.session_state.get('stability', (None, None))
            with id_cols[3]:
                if stab_mean is not None:
                    label, _ = _stability_reading(stab_mean)
                    st.markdown(f"<div class='id-card'><div class='v'>{stab_mean:.2f}</div><div class='l'>Stabilité (ARI) {label}</div></div>", unsafe_allow_html=True)

        if mode_run == 'joueurs':
            n_par_classe = df_analyse['Cluster'].value_counts().min()
            if n_par_classe < 5:
                st.warning(f"⚠️ Au moins une classe ne compte que {n_par_classe} joueur(s). Rappel important (Dalmaijer, Nord & Astle, 2022, *BMC Bioinformatics*) : la fiabilité d'une analyse de clusters dépend surtout de la **séparation** entre les groupes (le score de silhouette ci-dessus), pas seulement du nombre de joueurs — mais avec aussi peu de joueurs dans un groupe, le profil moyen de CETTE classe précise reste fragile : un seul joueur peut fortement le déplacer. Traite les classes les plus petites comme des pistes à confirmer, pas des conclusions.")
            stab_mean, stab_std = st.session_state.get('stability', (None, None))
            if stab_mean is not None:
                label, txt = _stability_reading(stab_mean)
                _explain("Stabilité des classes : peut-on faire confiance à ce regroupement ?", f"""
**Score de stabilité (Adjusted Rand Index) : {stab_mean:.2f} ± {stab_std:.2f}** — {label}

{txt}

*Comment ce score est calculé* : le K-Means a été relancé 40 fois sur des
versions légèrement bruitées des données (± 5% de l'écart-type de chaque
variable — l'ordre de grandeur d'une variabilité de mesure jour-à-jour), et
on a mesuré à chaque fois si les mêmes joueurs se retrouvaient dans les
mêmes classes que le regroupement affiché. 1.0 = accord parfait à chaque
relance, 0.0 = pas mieux qu'un tirage au hasard. C'est l'équivalent, en plus
rapide, de la vérification de cohérence sur 1000 relances faite par de Haan
et al. (2025) sur leur propre clustering de joueurs de football.
                """)

        if mode_run == 'joueurs':
            def get_symbol(poste):
                p = str(poste).lower()
                if 'def' in p or 'déf' in p: return 'circle'
                elif 'att' in p: return 'triangle-up'
                elif 'mil' in p: return 'square'
                elif 'gar' in p: return 'diamond'
                return 'circle'

            def get_poste_category(poste):
                p = str(poste).lower()
                if 'def' in p or 'déf' in p: return 'Défenseur'
                elif 'att' in p: return 'Attaquant'
                elif 'mil' in p: return 'Milieu'
                elif 'gar' in p: return 'Gardien'
                return 'Non défini'

            # Étiquettes indicatives par classe (calculées une fois ici, réutilisées partout)
            diff_pct_all = ((df_analyse.groupby('Cluster')[vars_pca_actives].mean() - df_analyse[vars_pca_actives].mean()) / df_analyse[vars_pca_actives].mean() * 100)
            labels_classes = {c: _label_cluster(diff_pct_all.loc[c]) for c in diff_pct_all.index}

            # --- Résumé en langage clair par classe, verrouillé sur la fiabilité ---
            # POURQUOI un verrou : une phrase du type "groupe plutôt endurance"
            # a l'air d'un constat établi, même quand elle vient d'un
            # clustering instable. On ne l'affiche donc QUE si le regroupement
            # a démontré une stabilité au moins "Modérée" (ARI >= 0.5, cf.
            # _stability_reading) -- sinon on l'annonce explicitement comme non
            # affichable plutôt que de risquer une fausse impression de solidité.
            _stab_mean_for_summary, _ = st.session_state.get('stability', (None, None))
            with st.expander("💬 Résumé en langage clair par classe", expanded=False):
                if _stab_mean_for_summary is None:
                    st.caption("Lance d'abord le clustering pour calculer la stabilité (ARI) avant d'afficher ce résumé.")
                elif _stab_mean_for_summary < 0.5:
                    st.warning(
                        f"⚠️ Stabilité insuffisante (ARI = {_stab_mean_for_summary:.2f} < 0.50) pour résumer les classes en "
                        "langage clair sans risquer une fausse impression de solidité. Les étiquettes techniques "
                        "(ci-dessous, sur les graphiques) restent disponibles mais doivent être traitées comme indicatives."
                    )
                else:
                    for c in sorted(diff_pct_all.index):
                        st.markdown(f"**Classe {c}** — {_plain_language_cluster_summary(diff_pct_all.loc[c])}")
                    st.caption("Généré automatiquement à partir des variables qui écartent le plus chaque classe de la moyenne du groupe. Ne remplace pas ton jugement terrain.")

            st.markdown(f"<h3 style='color:{SDR_RED};'>Projection des individus (La carte des joueurs)</h3>", unsafe_allow_html=True)

            if n_comp >= 2:
                col_x, col_y, col_vide = st.columns([1, 1, 2])
                with col_x: dim_x = st.selectbox("Composante X", range(1, n_comp + 1), index=0, key="dimx")
                with col_y: dim_y = st.selectbox("Composante Y", range(1, n_comp + 1), index=1, key="dimy")

                df_analyse['PCA_X'], df_analyse['PCA_Y'] = pca_result[:, dim_x - 1], pca_result[:, dim_y - 1]
                df_analyse['Catégorie Poste'] = df_analyse['Poste'].apply(get_poste_category) if 'Poste' in df_analyse.columns else 'Non défini'

                fig_pca_map = go.Figure()

                for idx, c in enumerate(sorted(df_analyse['Cluster'].unique())):
                    df_c = df_analyse[df_analyse['Cluster'] == c]
                    color = colors[int(c) % len(colors)]

                    if len(df_c) >= 3:
                        try:
                            pts = df_c[['PCA_X', 'PCA_Y']].values
                            hull = ConvexHull(pts)
                            hull_pts = np.append(pts[hull.vertices], [pts[hull.vertices][0]], axis=0)
                            fig_pca_map.add_trace(go.Scatter(x=hull_pts[:, 0], y=hull_pts[:, 1], mode='lines', fill='toself', fillcolor=color, opacity=0.15, line=dict(color=color, width=1, dash='dot'), showlegend=False, hoverinfo='skip'))
                        except QhullError: pass

                    symbols = df_c['Poste'].apply(get_symbol).tolist() if 'Poste' in df_c.columns else 'circle'
                    hovertemplate = '<b>%{text}</b><br>Classe: ' + str(c) + f' ({labels_classes.get(c, "")})'
                    if 'Poste' in df_c.columns: hovertemplate += '<br>Poste: %{customdata}'

                    fig_pca_map.add_trace(go.Scatter(
                        x=df_c['PCA_X'], y=df_c['PCA_Y'], mode='markers+text', name=f"Classe {c} — {labels_classes.get(c, '')}",
                        text=df_c['Joueur'], textposition="top center",
                        marker=dict(size=14, color=color, symbol=symbols, line=dict(width=1.5, color='white')),
                        hovertemplate=hovertemplate + '<extra></extra>', customdata=df_c['Catégorie Poste']
                    ))

                fig_pca_map.update_layout(
                    xaxis_title=f'CP {dim_x} ({pca.explained_variance_ratio_[dim_x-1]:.1%})',
                    yaxis_title=f'CP {dim_y} ({pca.explained_variance_ratio_[dim_y-1]:.1%})',
                    height=550, template="plotly_white", hovermode="closest",
                    legend=dict(title="Classes (K-Means)", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_pca_map, width='stretch')

                # Repères concrets pour l'explication : joueurs aux extrêmes de l'axe X affiché
                idx_max_x = df_analyse['PCA_X'].idxmax()
                idx_min_x = df_analyse['PCA_X'].idxmin()
                joueur_max_x, joueur_min_x = df_analyse.loc[idx_max_x, 'Joueur'], df_analyse.loc[idx_min_x, 'Joueur']
                top_loadings_x = pd.Series(pca.components_[dim_x - 1], index=vars_pca_actives).reindex(
                    pd.Series(pca.components_[dim_x - 1], index=vars_pca_actives).abs().sort_values(ascending=False).index
                ).head(2)
                loadings_txt = ", ".join(f"« {v} » ({'positivement' if w > 0 else 'négativement'})" for v, w in top_loadings_x.items())

                _explain("Comment lire cette carte ?", f"""
Chaque point est **un joueur**. Deux joueurs proches sur ce graphique ont un
profil physique statistiquement proche sur l'ensemble des tests choisis à
l'étape 2 — pas seulement sur les 2 axes affichés, mais sur TOUTES les
variables actives condensées ici en 2 dimensions lisibles (c'est le principe
de l'ACP : perdre le moins d'information possible en passant d'un espace à
{len(vars_pca_actives)} dimensions à un plan). Les zones colorées en
pointillés sont juste un repère visuel du contour de chaque classe — pas une
zone de confiance statistique.

**Sur ce graphique précis** : l'axe X (CP {dim_x}) explique
{pca.explained_variance_ratio_[dim_x-1]:.0%} de la variabilité totale entre
joueurs, et est tiré surtout par {loadings_txt}. **{joueur_max_x}** est le
joueur le plus à droite (valeurs les plus hautes sur ces variables), à
l'opposé de **{joueur_min_x}**, le plus à gauche.

Le classement K-Means en {len(df_analyse['Cluster'].unique())} classes est
fait sur l'espace complet (pas seulement ce plan 2D) — deux joueurs peuvent
donc apparaître proches ici sans être dans la même classe (ils se
ressemblent sur ces 2 axes mais divergent sur une autre variable, invisible
sur cette vue).
                """)

                st.markdown("---")
                st.markdown(f"<h3 style='color:{SDR_RED};'>Cercle des Corrélations</h3>", unsafe_allow_html=True)

                fig_circle = go.Figure()
                fig_circle.add_shape(type="circle", xref="x", yref="y", x0=-1, y0=-1, x1=1, y1=1, line_color="#cbd5e1", line_width=2)
                fig_circle.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
                fig_circle.add_vline(x=0, line_dash="dash", line_color="#94a3b8")

                loadings_x = pca.components_[dim_x-1] * np.sqrt(pca.explained_variance_[dim_x-1])
                loadings_y = pca.components_[dim_y-1] * np.sqrt(pca.explained_variance_[dim_y-1])

                for i in range(len(vars_pca_actives)):
                    fig_circle.add_shape(type='line', x0=0, y0=0, x1=loadings_x[i], y1=loadings_y[i], line=dict(color='rgba(17, 17, 17, 0.4)', width=2))

                fig_circle.add_trace(go.Scatter(
                    x=loadings_x, y=loadings_y, mode='markers+text', text=vars_pca_actives, textposition="top center",
                    marker=dict(size=10, color=SDR_RED, symbol='diamond'), name='Variables Actives',
                    hovertemplate='<b>%{text}</b><br>X: %{x:.2f}<br>Y: %{y:.2f}<extra></extra>'
                ))

                if vars_sup_quant:
                    sup_x, sup_y, sup_names = [], [], []
                    s_cx = pd.Series(pca_result[:, dim_x - 1])
                    s_cy = pd.Series(pca_result[:, dim_y - 1])
                    for v in vars_sup_quant:
                        s_v = df_analyse[v]
                        cx = s_v.corr(s_cx)
                        cy = s_v.corr(s_cy)
                        if pd.notna(cx) and pd.notna(cy):
                            sup_x.append(cx)
                            sup_y.append(cy)
                            sup_names.append(v)
                            fig_circle.add_shape(type='line', x0=0, y0=0, x1=cx, y1=cy, line=dict(color='rgba(52, 152, 219, 0.6)', width=2, dash='dash'))

                    if sup_x:
                        fig_circle.add_trace(go.Scatter(
                            x=sup_x, y=sup_y, mode='markers+text', text=sup_names, textposition="top center",
                            marker=dict(size=9, color=SUP_BLUE, symbol='circle-open', line=dict(width=2)), name='Variables Supplémentaires',
                            hovertemplate='<b>%{text} (Sup)</b><br>X: %{x:.2f}<br>Y: %{y:.2f}<extra></extra>'
                        ))

                fig_circle.update_layout(
                    xaxis=dict(range=[-1.2, 1.2], scaleanchor="y", scaleratio=1, zeroline=False),
                    yaxis=dict(range=[-1.2, 1.2], zeroline=False),
                    height=600, template="plotly_white", showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_circle, width='stretch')

                proches_centre = [v for i, v in enumerate(vars_pca_actives) if (loadings_x[i]**2 + loadings_y[i]**2) ** 0.5 < 0.4]
                proches_centre_txt = (", ".join(f"« {v} »" for v in proches_centre) + " ne sont " if proches_centre else "aucune variable n'est ") + "pas bien représentées sur ce plan (flèche courte) : leur variabilité s'exprime surtout sur d'autres axes que CP " + f"{dim_x}/CP {dim_y}."

                _explain("Comment lire le cercle des corrélations ?", f"""
Chaque flèche est **un test physique**, pas un joueur. Sa direction et sa
longueur indiquent comment ce test est lié aux 2 axes affichés :
- **Deux flèches qui pointent dans la même direction** = deux tests
  corrélés (un joueur fort sur l'un l'est généralement aussi sur l'autre).
- **Deux flèches à 90°** = tests indépendants l'un de l'autre.
- **Deux flèches opposées** = tests inversement liés.
- **Une flèche longue** (proche du cercle) = ce test est bien représenté sur
  ce plan, la position des joueurs sur la carte ci-dessus le reflète
  fidèlement. **Une flèche courte** = ce test se joue surtout sur un autre
  axe non affiché ici.

Sur ce graphique précis : {proches_centre_txt}

Les variables en pointillés bleus (si présentes) sont les variables
"supplémentaires" (étape 2) : elles n'ont pas participé au calcul du
regroupement, mais leur corrélation avec les axes est affichée à titre
indicatif — utile pour vérifier, par exemple, si l'âge ou le poste
recoupent (ou non) le profil physique.
                """)

            st.markdown("---")
            st.markdown(f"<h3 style='color:{SDR_RED};'>Analyse détaillée par Classe</h3>", unsafe_allow_html=True)
            diff_pct = diff_pct_all

            tabs_clusters = st.tabs([f"Classe {c} — {labels_classes.get(c, '')}" for c in sorted(df_analyse['Cluster'].unique())])
            for i, c in enumerate(sorted(df_analyse['Cluster'].unique())):
                with tabs_clusters[i]:
                    joueurs_de_la_classe = df_analyse.loc[df_analyse['Cluster'] == c, 'Joueur'].tolist()
                    n_c = len(joueurs_de_la_classe)
                    st.markdown(f"**{n_c} joueur(s)** : " + ", ".join(joueurs_de_la_classe))

                    c_diff = diff_pct.loc[c].sort_values(ascending=True)
                    pvals = {var: _anova_pvalue(df_analyse, var) for var in c_diff.index}
                    text_labels = [
                        f"{val:+.1f}%" + (" *" if (pvals.get(var) is not None and pvals[var] < 0.05) else "")
                        for var, val in c_diff.items()
                    ]
                    fig_bar = px.bar(
                        c_diff, orientation='h', color=c_diff.values, color_continuous_scale=['#D71920', '#eeeeee', '#27AE60'],
                        range_color=[-max(abs(c_diff.min()), abs(c_diff.max())), max(abs(c_diff.min()), abs(c_diff.max()))],
                        text=text_labels
                    )
                    fig_bar.add_vline(x=0, line_width=2, line_color="#111", line_dash="dash")
                    fig_bar.update_layout(title="Distance relative à la moyenne du groupe entier (%)", coloraxis_showscale=False, template="plotly_white", height=max(350, len(c_diff)*30))
                    st.plotly_chart(fig_bar, width='stretch')

                    n_signif = sum(1 for p in pvals.values() if p is not None and p < 0.05)
                    _explain("Comment lire ce graphique de profil ?", f"""
Chaque barre compare la **moyenne de la Classe {c}** à la **moyenne de
l'ensemble des joueurs analysés**, pour chaque test. Une barre verte à
+15% signifie : les joueurs de cette classe font, en moyenne, 15% MIEUX que
la moyenne générale sur ce test (ou 15% de moins si le test est du type
"plus petit = meilleur", ex. un temps de sprint — le signe garde toujours
le sens brut de la variable, pas son sens "performance").

**Astérisque (\\*)** : la différence a été testée statistiquement
(test de Kruskal-Wallis, qui compare les classes sans supposer une
distribution normale — adapté aux petits effectifs). Une barre marquée d'un
astérisque a une différence peu probable par hasard (p < 0.05) ; une barre
SANS astérisque peut sembler grande visuellement mais n'est pas confirmée
statistiquement, souvent parce que peu de joueurs sont concernés — à lire
avec prudence. Sur cette classe : {n_signif}/{len(c_diff)} variable(s)
montrent une différence statistiquement confirmée.
                    """)

            st.markdown("---")
            st.markdown(f"<h3 style='color:{SDR_RED};'>Recherche de Similarités</h3>", unsafe_allow_html=True)
            joueurs_dispos = df_analyse['Joueur'].unique()
            joueur_cible = st.selectbox("Individu de référence :", joueurs_dispos)

            if joueur_cible:
                X_scaled_sim = st.session_state['X_scaled']
                idx_cible = df_analyse.index[df_analyse['Joueur'] == joueur_cible].tolist()[-1]
                target_vec = X_scaled_sim[idx_cible]
                distances = np.linalg.norm(X_scaled_sim - target_vec, axis=1)
                max_dist = distances.max()
                similarites = 100 * (1 - (distances / max_dist)) if max_dist > 0 else np.full(len(distances), 100)

                df_sim_calc = df_analyse[['Joueur']].copy()
                df_sim_calc['Distance'], df_sim_calc['Similarité (%)'] = distances, np.round(similarites, 1)
                df_top = df_sim_calc[df_sim_calc['Joueur'] != joueur_cible].sort_values('Distance').drop_duplicates(subset=['Joueur']).head(3)

                cols_m = st.columns(3)
                for i, (idx, row) in enumerate(df_top.iterrows()):
                    with cols_m[i]:
                        st.markdown(f"""
                        <div class="metric-card">
                            <h3 class="metric-value">{row['Similarité (%)']}%</h3>
                            <p class="metric-label">Rang {i+1}</p>
                            <h4 class="metric-title">{row['Joueur']}</h4>
                        </div>
                        """, unsafe_allow_html=True)

                if not df_top.empty:
                    plus_proche = df_top.iloc[0]
                    _explain("Comment lire ce classement de similarité ?", f"""
La "similarité" est calculée à partir de la **distance euclidienne** entre
joueurs dans l'espace standardisé (les mêmes valeurs Z-score que pour le
clustering) : plus deux joueurs ont des valeurs proches sur l'ensemble des
{len(vars_pca_actives)} variables actives, plus la distance est petite,
et plus le pourcentage de similarité affiché est élevé (100% = distance
nulle, 0% = le joueur le plus éloigné de tous ceux analysés).

Ici, **{plus_proche['Joueur']}** est le profil le plus proche de
**{joueur_cible}** ({plus_proche['Similarité (%)']}% de similarité) — pas
forcément dans la même classe K-Means (la similarité individuelle et
l'appartenance à un groupe sont deux lectures complémentaires, pas
identiques : la classe regroupe par proximité MOYENNE à un centre commun,
la similarité ici compare deux joueurs directement entre eux).
                    """)

                    st.markdown("---")
                    joueur_comp = st.selectbox("Comparaison :", df_top['Joueur'].tolist())
                    idx_comp = df_top.index[df_top['Joueur'] == joueur_comp][0]
                    # Normalisation par percentile (rang dans la cohorte analysée, sens
                    # de la métrique géré via is_inverted_metric) plutôt qu'un MinMax brut :
                    # robuste aux valeurs extrêmes et cohérent avec le radar de comparateur.py
                    # (une valeur "moins bonne" au sens du test ne fausse pas la lecture visuelle).
                    pct_cible = [calculate_percentile(df_analyse, var, df_analyse.loc[idx_cible, var]) for var in vars_pca_actives]
                    pct_comp = [calculate_percentile(df_analyse, var, df_analyse.loc[idx_comp, var]) for var in vars_pca_actives]
                    pct_moyenne = [calculate_percentile(df_analyse, var, df_analyse[var].mean()) for var in vars_pca_actives]

                    fig_radar = build_radar(
                        vars_pca_actives,
                        [
                            {"name": joueur_cible, "values": pct_cible, "color": SDR_RED, "fill_opacity": 0.4},
                            {"name": joueur_comp, "values": pct_comp, "color": "#111", "fill_opacity": 0.4},
                            {"name": "Moyenne", "values": pct_moyenne, "color": "#888", "dash": True, "fill": False, "markers": False},
                        ],
                        height=600,
                    )
                    st.plotly_chart(fig_radar, width='stretch', config={'displayModeBar': False})

                    _explain("Comment lire ce radar de comparaison ?", f"""
Chaque axe est un test, et la valeur affichée est le **percentile** de
{joueur_cible} et {joueur_comp} au sein du groupe analysé (100% = meilleure
valeur du groupe sur ce test, 50% = valeur médiane, 0% = plus faible valeur
du groupe) — pas une valeur brute, pour pouvoir comparer des tests dans des
unités différentes sur un même graphique. La ligne pointillée grise
"Moyenne" indique où se situe le joueur théorique moyen du groupe sur
chaque test. Plus la zone colorée d'un joueur dépasse la ligne grise, plus
il est au-dessus de la moyenne du groupe sur ce test précis.
                    """)

        elif mode_run == 'tests':
            df_vars = st.session_state['df_vars']

            st.markdown(f"<h3 style='color:{SDR_RED};'>Composition des Groupes de Tests</h3>", unsafe_allow_html=True)

            cols_groupes = st.columns(len(df_vars['Cluster'].unique()))
            for i, c in enumerate(sorted(df_vars['Cluster'].unique())):
                with cols_groupes[i]:
                    st.markdown(f"**Groupe {c}**")
                    tests = df_vars[df_vars['Cluster'] == c]['Variable'].tolist()
                    for t in tests:
                        st.markdown(f"- {t}")

            _explain("Que veut dire « regrouper les tests » ?", """
Ici, l'algorithme ne regroupe plus des JOUEURS mais des TESTS : deux tests
qui donnent (à peu près) le même classement des joueurs se retrouvent dans
le même groupe — c'est le signe qu'ils mesurent en partie la même qualité
physique, même s'ils portent des noms différents. Concrètement, ça sert à
repérer des redondances dans une batterie de tests (si "Peak Force CMJ" et
"Squat Belt" tombent toujours dans le même groupe, l'un des deux
n'apporte peut-être pas d'information supplémentaire) ou, à l'inverse, à
confirmer que deux tests visent bien des qualités différentes.
            """)

            if n_comp >= 2:
                st.markdown("---")
                st.markdown(f"<h3 style='color:{SDR_RED};'>Cercle des Corrélations (Coloré par Groupes)</h3>", unsafe_allow_html=True)

                col_x, col_y, col_vide = st.columns([1, 1, 2])
                with col_x: dim_x = st.selectbox("Composante X", range(1, n_comp + 1), index=0, key="dimx_test")
                with col_y: dim_y = st.selectbox("Composante Y", range(1, n_comp + 1), index=1, key="dimy_test")

                fig_circle = go.Figure()
                fig_circle.add_shape(type="circle", xref="x", yref="y", x0=-1, y0=-1, x1=1, y1=1, line_color="#cbd5e1", line_width=2)
                fig_circle.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
                fig_circle.add_vline(x=0, line_dash="dash", line_color="#94a3b8")

                loadings_x = pca.components_[dim_x-1] * np.sqrt(pca.explained_variance_[dim_x-1])
                loadings_y = pca.components_[dim_y-1] * np.sqrt(pca.explained_variance_[dim_y-1])

                for c in sorted(df_vars['Cluster'].unique()):
                    color = colors[int(c) % len(colors)]
                    vars_in_c = df_vars[df_vars['Cluster'] == c]['Variable'].tolist()
                    idx_in_c = [vars_pca_actives.index(v) for v in vars_in_c]

                    x_c = loadings_x[idx_in_c]
                    y_c = loadings_y[idx_in_c]

                    for i in range(len(vars_in_c)):
                         fig_circle.add_shape(type='line', x0=0, y0=0, x1=x_c[i], y1=y_c[i], line=dict(color=color, width=2.5))

                    fig_circle.add_trace(go.Scatter(
                        x=x_c, y=y_c, mode='markers+text', text=vars_in_c, textposition="top center",
                        marker=dict(size=12, color=color, symbol='diamond', line=dict(width=1, color='white')), name=f"Groupe {c}",
                        hovertemplate='<b>%{text}</b><br>X: %{x:.2f}<br>Y: %{y:.2f}<extra></extra>'
                    ))

                if vars_sup_quant:
                    sup_x, sup_y, sup_names = [], [], []
                    s_cx = pd.Series(pca_result[:, dim_x - 1])
                    s_cy = pd.Series(pca_result[:, dim_y - 1])
                    for v in vars_sup_quant:
                        s_v = df_analyse[v]
                        cx = s_v.corr(s_cx)
                        cy = s_v.corr(s_cy)
                        if pd.notna(cx) and pd.notna(cy):
                            sup_x.append(cx)
                            sup_y.append(cy)
                            sup_names.append(v)
                            fig_circle.add_shape(type='line', x0=0, y0=0, x1=cx, y1=cy, line=dict(color='rgba(150, 150, 150, 0.5)', width=2, dash='dash'))

                    if sup_x:
                        fig_circle.add_trace(go.Scatter(
                            x=sup_x, y=sup_y, mode='markers+text', text=sup_names, textposition="top center",
                            marker=dict(size=9, color="#999999", symbol='circle-open', line=dict(width=2)), name='Variables Supplémentaires',
                            hovertemplate='<b>%{text} (Sup)</b><br>X: %{x:.2f}<br>Y: %{y:.2f}<extra></extra>'
                        ))

                fig_circle.update_layout(
                    xaxis=dict(range=[-1.2, 1.2], scaleanchor="y", scaleratio=1, zeroline=False),
                    yaxis=dict(range=[-1.2, 1.2], zeroline=False),
                    height=600, template="plotly_white", showlegend=True,
                    legend=dict(title="Clusters K-Means", orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_circle, width='stretch')

                _explain("Comment lire ce cercle des corrélations ?", """
Même principe que le cercle en mode "Profilage Joueurs" (une flèche = un
test, sa longueur indique s'il est bien représenté sur ce plan), mais ici
la COULEUR de chaque flèche indique à quel groupe de tests elle appartient
d'après le clustering ci-dessus. Des flèches de même couleur, proches les
unes des autres et pointant dans la même direction, sont des tests qui se
comportent statistiquement de façon très semblable dans cette cohorte.
                """)

        st.markdown("---")
        st.markdown(f"<h3 style='color:{SDR_RED};'>Histogramme des Valeurs Propres</h3>", unsafe_allow_html=True)
        var_exp = pd.DataFrame({'Composante': [f"CP {i+1}" for i in range(n_comp)], 'Variance (%)': pca.explained_variance_ratio_ * 100})
        fig_var = px.bar(var_exp, x='Composante', y='Variance (%)', text_auto='.1f', color='Variance (%)', color_continuous_scale=['#D71920', '#111111'])
        fig_var.update_traces(textposition="outside", cliponaxis=False)
        fig_var.update_layout(coloraxis_showscale=False, template="plotly_white", height=350)
        st.plotly_chart(fig_var, width='stretch')

        cum_2 = pca.explained_variance_ratio_[:2].sum() * 100 if n_comp >= 2 else pca.explained_variance_ratio_[0] * 100
        _explain("Comment lire ce graphique (« scree plot ») ?", f"""
Chaque barre est un axe (composante principale) créé par l'ACP, et sa
hauteur indique quelle part de la variabilité TOTALE entre joueurs (ou
tests) cet axe résume à lui seul. CP 1 capture toujours le plus, puis CP 2,
etc. — les cartes affichées plus haut n'utilisent que 2 de ces axes (souvent
CP 1 et CP 2), donc {cum_2:.0f}% de l'information est visible sur ces
graphiques ; le reste ({100 - cum_2:.0f}%) existe dans les données mais
n'apparaît pas sur ces vues 2D. Si les 2-3 premières barres sont hautes et
les suivantes très basses, ça veut dire que peu de dimensions "réelles"
sous-tendent tes tests (beaucoup de redondance) ; si la hauteur diminue très
progressivement, c'est que chaque test apporte une information plus
indépendante des autres.
        """)

        st.markdown("---")
        st.markdown(f"<h3 style='color:{SDR_RED};'>Matrice de contribution des variables</h3>", unsafe_allow_html=True)
        loadings_full = pca.components_.T * np.sqrt(pca.explained_variance_)
        cos2_matrix = loadings_full**2
        dim_names = [f"CP {i+1}" for i in range(n_comp)]

        df_cos2 = pd.DataFrame(cos2_matrix, index=vars_pca_actives, columns=dim_names)
        df_cos2_melted = df_cos2.reset_index().melt(id_vars='index', var_name='Composante', value_name='cos2')
        df_cos2_melted.rename(columns={'index': 'Variable'}, inplace=True)

        fig_contrib = px.scatter(
            df_cos2_melted, x='Composante', y='Variable', size='cos2', color='cos2',
            color_continuous_scale=['#eeeeee', SDR_RED], size_max=25
        )
        fig_contrib.update_layout(
            coloraxis_showscale=False, template="plotly_white", height=max(400, len(vars_pca_actives)*35),
            xaxis=dict(showgrid=True, gridcolor='#eee'), yaxis=dict(showgrid=True, gridcolor='#eee')
        )
        st.plotly_chart(fig_contrib, width='stretch')

        _explain("Comment lire cette matrice de contribution (cos²) ?", """
Un point gros et rouge à l'intersection d'une variable et d'un axe (CP)
signifie que cette variable est bien expliquée par cet axe précis — c'est
le complément numérique du cercle des corrélations plus haut (une flèche
longue dans le cercle = un gros point ici). Utile pour repérer d'un coup
d'œil : (1) les variables qui pèsent le plus dans la construction de CP 1 et
CP 2 (donc dans la carte des joueurs affichée en haut de page), et (2) les
variables qui ne s'expriment pleinement que sur un axe plus profond (CP 3,
CP 4...), donc invisibles sur les graphiques 2D de cette page.
        """)
