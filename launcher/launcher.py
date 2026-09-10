"""
Lanceur d'applis local — une petite page Streamlit "façon Streamlit Cloud"
pour démarrer/arrêter les applications de ce PC, sans taper de commande.

Lancement (une seule fois, garde le terminal ouvert) :
    venv\\Scripts\\streamlit run launcher\\launcher.py --server.port 8500

Puis ouvre http://localhost:8500 : un bouton Démarrer/Arrêter par appli.
Ajouter une nouvelle appli plus tard = ajouter une entrée dans APPS ci-dessous.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time

import streamlit as st

st.set_page_config(page_title="Lanceur d'applis SDR", page_icon="🚀", layout="centered")

LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(LAUNCHER_DIR)  # dossier appV3/
STATE_FILE = os.path.join(LAUNCHER_DIR, "state.json")

# ==========================================
# Liste des applications gérées par ce lanceur.
# Pour en ajouter une : copier une entrée et adapter script/port.
# ==========================================
APPS = [
    {
        "id": "profilage",
        "name": "SDR Profilage",
        "description": "Application de profilage physique des joueurs",
        "cwd": BASE_DIR,
        "python": os.path.join(BASE_DIR, "venv", "Scripts", "python.exe"),
        "script": "main.py",
        "port": 8501,
    },
]


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def is_port_open(port, host="127.0.0.1"):
    """Vraie source de vérité : le port répond-il, peu importe ce que dit l'état enregistré."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def get_local_ip():
    """IP de cette machine sur le réseau local (pour donner l'URL réseau)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def start_app(app):
    creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [app["python"], "-m", "streamlit", "run", app["script"], "--server.port", str(app["port"])],
        cwd=app["cwd"],
        creationflags=creationflags,
    )
    state = load_state()
    state[app["id"]] = {"pid": proc.pid}
    save_state(state)


def stop_app(app):
    state = load_state()
    info = state.get(app["id"])
    if info and info.get("pid"):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(info["pid"]), "/T", "/F"], capture_output=True)
            else:
                os.kill(info["pid"], signal.SIGTERM)
        except Exception:
            pass
    state.pop(app["id"], None)
    save_state(state)


st.title("🚀 Lanceur d'applis — SDR Performance")
st.caption("Démarre/arrête tes applications locales depuis cette page, sans terminal.")

local_ip = get_local_ip()

for app in APPS:
    running = is_port_open(app["port"])
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(app["name"])
            st.caption(app["description"])
            if running:
                st.success("✅ En cours d'exécution")
                st.code(
                    f"http://localhost:{app['port']}\n"
                    f"http://{local_ip}:{app['port']}  (réseau local)"
                )
            else:
                st.warning("⏸️ Arrêtée")
        with col2:
            st.write("")
            st.write("")
            if running:
                if st.button("⏹️ Arrêter", key=f"stop_{app['id']}", width="stretch"):
                    stop_app(app)
                    st.rerun()
            else:
                if st.button("▶️ Démarrer", key=f"start_{app['id']}", width="stretch"):
                    start_app(app)
                    with st.spinner("Démarrage en cours..."):
                        # On attend que le port réponde vraiment avant de
                        # rafraîchir, plutôt qu'une pause fixe qui pourrait
                        # être trop courte (l'appli met quelques secondes
                        # à démarrer).
                        for _ in range(20):  # jusqu'à ~10s
                            if is_port_open(app["port"]):
                                break
                            time.sleep(0.5)
                    st.rerun()

st.divider()
st.caption(
    "💡 Première utilisation en réseau local : Windows affichera une popup "
    "pare-feu la première fois qu'une appli démarre — clique **Autoriser l'accès**."
)
