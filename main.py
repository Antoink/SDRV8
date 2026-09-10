import streamlit as st
from utils import load_data, load_data_postgres, local_css, SDR_RED
from glossary import render_glossary_expander
import profiling
import os

st.set_page_config(
    page_title="SDR Performance",
    layout="wide",
    initial_sidebar_state="collapsed", 
    page_icon="logo_sdr.png"
)

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
                Antoine Kaczmarek - DEPARTEMENT PERFORMANCE - STADE DE REIMS
            </div>
        """, unsafe_allow_html=True)
        
        if pwd:
            if pwd == "SDR":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")
                
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
        full_data, source = load_data()

    st.toast(f"✅ Données chargées : {source}")

    profiling.show_profiling_page(full_data)



# streamlit run main.py
# ou 
# python -m streamlit run main.py
