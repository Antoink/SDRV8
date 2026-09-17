import streamlit as st
from utils import load_data, load_data_postgres, local_css, SDR_RED
from glossary import render_glossary_expander
import profiling
import os
import concurrent.futures

st.set_page_config(
    page_title="SDR Performance",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="logo_sdr.png"
)

# PRÉ-CHARGEMENT DES DONNÉES DÈS L'OUVERTURE DE L'APPLI
# -------------------------------------------------------
# Avant, load_data() (fetch réseau du Google Sheets) n'était appelé qu'une
# fois le mot de passe validé -- la personne attendait donc le temps de ce
# fetch APRÈS avoir tapé son mot de passe. Ici on lance ce fetch dans un
# thread en arrière-plan dès le tout premier run du script (donc pendant que
# l'écran de mot de passe s'affiche et que la personne le saisit) : le
# temps de frappe du mot de passe "masque" le temps réseau. .result() plus
# bas ne bloque que si le thread n'a pas encore fini.
if "data_future" not in st.session_state:
    st.session_state["data_executor"] = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    st.session_state["data_future"] = st.session_state["data_executor"].submit(load_data)

# MOT DE PASSE
def check_password():
    """Retourne True si le mot de passe est correct."""
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        sub_col1, sub_col2, sub_col3 = st.columns([1, 1, 1])
        with sub_col2:
            if os.path.exists("logo_sdr.png"):
                st.image("logo_sdr.png", width=150)
            else:
                st.title("SDR")
        
        st.markdown("<h3 style='text-align:center;'>ACCÈS RESTREINT</h3>", unsafe_allow_html=True)
        
        pwd = st.text_input("Mot de passe", type="password", label_visibility="collapsed", placeholder="Entrez le mot de passe...")
        
        st.markdown("""
            <div style='text-align:center; margin-top:20px; font-size:11px; color:#666; font-weight:bold; letter-spacing:0.5px; border-top:1px solid #eee; padding-top:15px;'>
                DEPARTEMENT PERFORMANCE - STADE DE REIMS
            </div>
        """, unsafe_allow_html=True)

        if pwd:
            if pwd == "SDR":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")

    # Attribution discrète, ancrée en bas à GAUCHE de l'ÉCRAN (position
    # fixed, pas dans la colonne centrale étroite du formulaire) -- demande
    # 09/2026 : en bas à droite, le widget "Manage app" de Streamlit Cloud
    # passe par-dessus et le cache -- déplacé à gauche pour rester visible.
    st.markdown(
        "<div style='position:fixed; bottom:10px; left:16px; font-size:9px; "
        "color:#bbb; z-index:9999;'>développé par Antoine Kaczmarek</div>",
        unsafe_allow_html=True,
    )

    return False



# main.py

@st.fragment
def data_source_panel():
    """
    Panneau de la sidebar : choix de la source de données + bouton de
    synchronisation PostgreSQL.

    @st.fragment fait que cliquer sur "Synchroniser" ne recharge QUE ce
    petit panneau, pas toute la page de profilage (qui reste affichée telle
    quelle pendant ce temps) : c'est ça qui rend le clic rapide.
    """
    st.markdown("### 🗄️ Source de données")
    choice = st.radio(
        "Source de données",
        ["Google Sheets (par défaut)", "PostgreSQL (test)"],
        label_visibility="collapsed",
        key="data_source_choice",
    )

    if choice.startswith("PostgreSQL"):
        if st.button("🔄 Synchroniser depuis Google Sheets", width="stretch"):
            with st.status("Synchronisation en cours...") as status:
                try:
                    from database.sync_from_google_sheets import sync
                    sync()
                    load_data_postgres.clear()  # ne vide que le cache de cette fonction
                    status.update(label="✅ Base PostgreSQL à jour", state="complete")
                except Exception as e:
                    status.update(label=f"❌ Échec de la synchro : {e}", state="error")
            # scope="fragment" : seul ce panneau se recharge, pas toute l'app
            st.rerun(scope="fragment")

    return choice


if check_password():
    local_css()
    with st.sidebar:
        # Traçabilité minimale : le mot de passe "SDR" est partagé par tout
        # le staff, donc rien ne distinguait qui avait modifié/sauvegardé un
        # commentaire ou une stratégie de rapport. On demande simplement un
        # nom (pas un vrai compte utilisateur) et on le garde en session
        # pour l'attacher aux sauvegardes de rapport_page.py. Persisté aussi
        # en session_state pour ne pas le redemander à chaque interaction.
        st.markdown("### 👤 Intervenant")
        st.session_state["current_user_name"] = st.text_input(
            "Votre nom (pour la traçabilité des sauvegardes)",
            value=st.session_state.get("current_user_name", ""),
            placeholder="Ex : Antoine K.",
            label_visibility="collapsed",
            key="current_user_name_input",
        )
        # Glossaire des sigles (CMJ, RSI, RFD, DSI, mRSI, LSI...) -- replié
        # par défaut pour ne pas encombrer la sidebar, accessible partout.
        render_glossary_expander()
        source_choice = data_source_panel()

    if source_choice.startswith("PostgreSQL"):
        full_data, source = load_data_postgres()
        if full_data.empty:
            st.sidebar.warning(f"PostgreSQL indisponible ({source}) → retour à Google Sheets.")
            full_data, source = load_data()
    else:
        # Récupère le résultat du fetch lancé en arrière-plan dès l'ouverture
        # de l'appli (voir plus haut) -- ne bloque que si le mot de passe a
        # été tapé plus vite que le temps du fetch réseau.
        full_data, source = st.session_state["data_future"].result()

    # Alerte de fiabilité : si Google Sheets/PostgreSQL est injoignable, on ne
    # veut surtout pas laisser le staff consulter des pages vides ou
    # périmées sans le savoir -- contrairement au st.toast (discret, 4s puis
    # disparaît), ces bandeaux restent affichés en haut de page tant que la
    # source n'est pas fiable.
    if full_data.empty:
        st.error(
            "🚨 Aucune donnée chargée : Google Sheets est injoignable et aucun fichier "
            "de secours n'a été trouvé. Les pages ci-dessous seront vides tant que la "
            "source de données n'est pas rétablie.",
            icon="🚨",
        )
    elif source != "Google Sheets":
        st.warning(
            f"⚠️ Google Sheets injoignable : source de secours utilisée ({source}), "
            "les données affichées peuvent ne pas être à jour.",
            icon="⚠️",
        )
    else:
        st.toast(f"✅ Données chargées : {source}")

    profiling.show_profiling_page(full_data)



# streamlit run main.py
# ou 
# python -m streamlit run main.py
