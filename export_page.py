# =============================================================================
# export_page.py — Export de données multi-indicateurs, multi-joueurs
# =============================================================================
# Demande (09/2026) : pouvoir exporter par exemple le poids de tous les
# joueurs, mais avec la possibilité de choisir plusieurs indicateurs à la
# fois (pas juste un seul comme dans l'onglet CLASSEMENT). Reprend les mêmes
# conventions que le reste de l'appli (find_column_in_df / last_valid_value /
# clean_numeric_value de data_utils, CSV ';' + utf-8-sig comme dans
# classement.py) pour rester cohérent avec l'existant.
# =============================================================================

import pandas as pd
import streamlit as st

from config_rapport import TEAM_STRUCTURE
from data_utils import clean_numeric_value, find_column_in_df, last_valid_value

SDR_RED = "#D71920"

# Informations "fixes" du joueur (pas des tests physiques) qu'on peut aussi
# vouloir exporter à côté des indicateurs -- ex: Poids, Poste...
BASE_FIELDS = [
    "Age", "Taille", "Poids", "Masse Grasse",
    "Poste", "Position", "PositionPrincipale", "PositionSecondaire",
    "Latéralité",
]


def show_export_page(df: pd.DataFrame):
    st.markdown(f"<h2 style='color:{SDR_RED};'>EXPORT DE DONNÉES</h2>", unsafe_allow_html=True)
    st.caption(
        "Choisis les joueurs et les indicateurs à exporter (plusieurs à la fois "
        "possible), puis télécharge le tableau obtenu."
    )

    if df is None or df.empty or "Joueur" not in df.columns:
        st.info("Aucune donnée disponible.")
        return

    # --- 1. Périmètre : équipes / joueurs / session ---
    toutes_equipes = sorted(df["Equipe"].dropna().astype(str).unique()) if "Equipe" in df.columns else []
    col1, col2 = st.columns(2)
    with col1:
        choix_equipes = st.multiselect(
            "Équipes à inclure :", toutes_equipes, default=toutes_equipes, key="export_equipes"
        )
    with col2:
        mode_valeur = st.selectbox(
            "Valeur à exporter :",
            ["Dernière valeur connue (recommandé)", "Une session précise"],
            key="export_mode_valeur",
            help="« Dernière valeur connue » prend, pour chaque joueur et "
                 "chaque indicateur, la valeur la plus récente renseignée -- "
                 "utile car tous les joueurs n'ont pas forcément été testés "
                 "à la même session sur chaque indicateur.",
        )

    df_scope = df[df["Equipe"].astype(str).isin(choix_equipes)].copy() if choix_equipes and "Equipe" in df.columns else df.copy()

    sel_session = None
    if mode_valeur == "Une session précise" and "Session" in df.columns:
        sessions_dispos = sorted(df_scope["Session"].dropna().astype(str).unique())
        if sessions_dispos:
            sel_session = st.selectbox("Session :", sessions_dispos, key="export_session")
        else:
            st.warning("Aucune session disponible pour ces équipes.")

    joueurs_dispo = sorted(df_scope["Joueur"].dropna().unique())
    choix_joueurs = st.multiselect(
        "Joueurs (laisser vide = tous les joueurs des équipes ci-dessus) :",
        joueurs_dispo, default=[], key="export_joueurs",
    )

    # --- 2. Indicateurs ---
    st.markdown("#### Indicateurs à exporter")
    choix_base = st.multiselect(
        "Informations générales :", BASE_FIELDS, default=["Poids"], key="export_base"
    )

    choix_indicateurs = []
    for categorie, indicateurs in TEAM_STRUCTURE.items():
        with st.expander(categorie, expanded=False):
            sel = st.multiselect(
                f"Indicateurs — {categorie}", indicateurs, default=[],
                key=f"export_cat_{categorie}", label_visibility="collapsed",
            )
            choix_indicateurs.extend(sel)

    labels_total = choix_base + choix_indicateurs
    if not labels_total:
        st.info("Sélectionne au moins un indicateur (ou une information générale) à exporter.")
        return

    joueurs_finaux = choix_joueurs if choix_joueurs else joueurs_dispo
    if not joueurs_finaux:
        st.warning("Aucun joueur à exporter avec ces filtres.")
        return

    # --- 3. Construction du tableau ---
    rows = []
    for joueur in joueurs_finaux:
        df_j = df_scope[df_scope["Joueur"] == joueur]
        if df_j.empty:
            continue

        if sel_session and "Session" in df_j.columns:
            df_j_val = df_j[df_j["Session"].astype(str) == sel_session]
            if df_j_val.empty:
                # Pas de données pour ce joueur sur la session choisie --
                # on retombe sur tout son historique plutôt que de le
                # faire disparaître silencieusement du tableau.
                df_j_val = df_j
        else:
            df_j_val = df_j

        row = {
            "Joueur": joueur,
            "Équipe": last_valid_value(df_j, "Equipe", "-"),
        }
        for label in labels_total:
            col = find_column_in_df(df_j_val, label)
            if not col:
                row[label] = None
                continue
            val = last_valid_value(df_j_val, col, None)
            if val is None:
                row[label] = None
                continue
            cleaned = clean_numeric_value(val)
            row[label] = cleaned if cleaned is not None else val
        rows.append(row)

    if not rows:
        st.warning("Aucune donnée trouvée pour ces filtres.")
        return

    df_export = pd.DataFrame(rows)

    st.markdown("#### Aperçu")
    st.dataframe(df_export, width="stretch", hide_index=True)
    st.caption(f"{len(df_export)} joueur(s) · {len(labels_total)} indicateur(s) sélectionné(s).")

    nom_fichier = "Export_Profilage" + (f"_{sel_session}" if sel_session else "")
    nom_fichier = nom_fichier.replace(" ", "_") + ".csv"

    st.download_button(
        "⬇️ Exporter (CSV)",
        data=df_export.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=nom_fichier,
        mime="text/csv",
        width="stretch",
    )

    _render_data_quality_diagnostic(df)


def _render_data_quality_diagnostic(df: pd.DataFrame):
    """
    Diagnostic qualité des données -- demande (09/2026) : repérer les trous
    (photo manquante, poste manquant...) sans avoir à tomber dessus par
    hasard au fil des rapports. Volontairement discret : replié par défaut,
    en bas de l'onglet le plus "technique" de l'appli -- pas un onglet dédié
    ni un indicateur mis en avant, l'appli n'ayant pas de vraie distinction
    de rôle (mot de passe unique partagé par tout le staff, cf. main.py).
    """
    with st.expander("🔧 Diagnostic technique (qualité des données)", expanded=False):
        st.caption(
            "Section discrète, pour le suivi technique -- repère les trous connus "
            "dans les données (pas destinée à un affichage large)."
        )
        import os
        from utils import get_best_photo_path

        joueurs = sorted(df["Joueur"].dropna().unique()) if "Joueur" in df.columns else []

        sans_photo = [j for j in joueurs if not get_best_photo_path(j)] if os.path.exists("Photos") else []

        col_poste = None
        for label in ["PositionPrincipale", "Position", "Poste"]:
            c = find_column_in_df(df, label)
            if c:
                col_poste = c
                break
        sans_poste = []
        if col_poste:
            for j in joueurs:
                vals = df.loc[df["Joueur"] == j, col_poste].dropna()
                vals = vals[vals.astype(str).str.strip().str.lower() != "nan"]
                if vals.empty:
                    sans_poste.append(j)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Sans photo** ({len(sans_photo)})")
            st.dataframe(pd.DataFrame({"Joueur": sans_photo}), hide_index=True, width="stretch") if sans_photo else st.caption("Aucun.")
        with c2:
            st.markdown(f"**Sans poste renseigné** ({len(sans_poste)})")
            st.dataframe(pd.DataFrame({"Joueur": sans_poste}), hide_index=True, width="stretch") if sans_poste else st.caption("Aucun.")
