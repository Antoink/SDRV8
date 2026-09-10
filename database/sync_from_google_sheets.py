"""
Synchronise la base PostgreSQL (`sdr-postgres` / base `profilage`) avec les
données actuelles du Google Sheet (ou, à défaut, le fichier Excel local) --
via utils.load_data(), déjà utilisée par l'application.

Schéma flexible (voir database/schema_profilage.sql) :
- Les colonnes d'identité (Joueur, Poste, Equipe, ...) vont dans `joueurs`.
- Les colonnes "Session" / "Session exact" vont dans `sessions`.
- TOUTES les autres colonnes (quel que soit leur nombre) deviennent des
  lignes dans `mesures` : (session, nom_test, valeur). Ajouter un test dans
  le Google Sheet n'exige donc aucune modification de ce script.

Relançable à tout moment : pour chaque session, les mesures existantes sont
remplacées par les valeurs actuelles du sheet (pas de doublons, pas de
valeurs périmées qui traînent).

Utilisation :
    python database/sync_from_google_sheets.py
"""

import os
import sys

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from column_mapping import IDENTITY_COLUMNS, SESSION_COLUMNS
from utils import load_data

DB_CONFIG = dict(
    host=os.environ.get("SDR_PG_HOST", "localhost"),
    port=os.environ.get("SDR_PG_PORT", "5432"),
    dbname=os.environ.get("SDR_PG_DB", "profilage"),
    user=os.environ.get("SDR_PG_USER", "sdr_admin"),
    password=os.environ.get("SDR_PG_PASSWORD", "sdr_dev_password"),
)


def to_number(value):
    """Essaie de convertir une valeur (souvent une chaîne, ex '75,6') en
    nombre. Renvoie None si ce n'est pas possible."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def to_date(value):
    ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(ts) else ts.date()


def sync():
    df, source = load_data()
    if df.empty:
        print(f"Aucune donnée chargée (source : {source}). Rien à synchroniser.")
        return

    print(f"Données chargées depuis : {source} ({len(df)} joueurs, {len(df.columns)} colonnes)")

    identity_cols_present = [c for c in IDENTITY_COLUMNS if c in df.columns]
    session_cols_present = [c for c in SESSION_COLUMNS if c in df.columns]
    test_cols = [
        c for c in df.columns
        if c not in identity_cols_present and c not in session_cols_present
    ]
    print(f"-> {len(test_cols)} colonnes détectées comme des tests (tout ce qui n'est pas identité/session).")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    n_joueurs = 0
    n_sessions = 0
    n_mesures = 0

    try:
        for _, row in df.iterrows():
            # ---- 1. Upsert joueur ----
            identity_values = {}
            for excel_col in identity_cols_present:
                sql_col = IDENTITY_COLUMNS[excel_col]
                identity_values[sql_col] = (
                    to_date(row[excel_col]) if sql_col == "date_de_naissance"
                    else (None if pd.isna(row[excel_col]) else str(row[excel_col]).strip())
                )

            cols = list(identity_values.keys())
            vals = [identity_values[c] for c in cols]
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "nom")

            cur.execute(
                f"""
                INSERT INTO joueurs ({", ".join(cols)})
                VALUES ({", ".join(["%s"] * len(cols))})
                ON CONFLICT (nom) DO UPDATE SET {set_clause}
                RETURNING id
                """,
                vals,
            )
            joueur_id = cur.fetchone()[0]
            n_joueurs += 1

            # ---- 2. Upsert session ----
            session_label = row.get("Session")
            session_date = to_date(row["Session exact"]) if "Session exact" in df.columns else None

            cur.execute(
                """
                INSERT INTO sessions (joueur_id, session_label, session_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (joueur_id, COALESCE(session_date, '0001-01-01'::date))
                DO UPDATE SET session_label = EXCLUDED.session_label
                RETURNING id
                """,
                [joueur_id, None if pd.isna(session_label) else str(session_label).strip(), session_date],
            )
            session_id = cur.fetchone()[0]
            n_sessions += 1

            # ---- 3. Remplace les mesures de cette session ----
            cur.execute("DELETE FROM mesures WHERE session_id = %s", [session_id])

            rows_to_insert = []
            for test_col in test_cols:
                raw_value = row[test_col]
                if pd.isna(raw_value):
                    continue
                num_value = to_number(raw_value)
                text_value = None if num_value is not None else str(raw_value).strip()
                rows_to_insert.append((session_id, test_col, num_value, text_value))

            if rows_to_insert:
                execute_values(
                    cur,
                    "INSERT INTO mesures (session_id, nom_test, valeur_num, valeur_texte) VALUES %s",
                    rows_to_insert,
                )
            n_mesures += len(rows_to_insert)

        conn.commit()
        print(f"Synchronisation terminée : {n_joueurs} joueurs, {n_sessions} sessions, {n_mesures} mesures.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sync()
