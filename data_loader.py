# -*- coding: utf-8 -*-
"""
data_loader.py
===============
Chargement et nettoyage du fichier de profilage.

BUGS CORRIGÉS PAR RAPPORT À LA VERSION PRÉCÉDENTE
--------------------------------------------------
1. **Fichier introuvable (bug bloquant)** : l'ancien code cherchait en dur
   "Profilage 2026-2027.xlsx" (avec un espace) alors que ton fichier
   s'appelle "Profilage_2026-2027.xlsx" (avec un underscore). Sur Windows,
   selon la casse du système de fichiers, ça pouvait fonctionner par hasard
   en local mais planter dès le déploiement (Streamlit Cloud est sous Linux,
   sensible à la casse ET à l'orthographe exacte). Ici, on cherche
   automatiquement le premier fichier .xlsx du dossier de travail, avec un
   message d'erreur clair si aucun n'est trouvé, plutôt qu'un nom figé.

2. **Décimales à virgule perdues dans les statistiques de groupe** : de
   nombreuses colonnes (ex : "Somme ABD", "90/20 G (N/kg)") sont typées
   `object` dans le fichier Excel car certaines cellules utilisent la virgule
   comme séparateur décimal (`"12,5"`) ou contiennent des tirets ("-") pour
   les valeurs manquantes. L'ancienne fonction `get_column_series()`
   utilisée pour calculer moyenne / percentile / z-score appelait
   `pd.to_numeric(..., errors='coerce')` DIRECTEMENT sur ces colonnes.
   Résultat : `pd.to_numeric("12,5")` renvoie NaN (silencieusement), donc
   toutes les valeurs à virgule d'une colonne étaient exclues du calcul de
   la moyenne/écart-type de référence, alors que la valeur du joueur affichée
   sur sa fiche (elle, nettoyée via une fonction différente,
   `clean_numeric_value`) était correcte. Le joueur pouvait donc être comparé
   à une moyenne de groupe biaisée sans que rien ne le signale.
   → Correction : on nettoie TOUTES les colonnes numériques une seule fois
   au chargement, avec la même logique (gestion virgule + tiret), et on ne
   travaille plus jamais sur les colonnes brutes ensuite.

3. **Recalcul de colonne à chaque affichage** : l'ancien code nettoyait/
   convertissait des colonnes à la volée dans des boucles Streamlit
   (rejouées à chaque interaction). Ici, le nettoyage est fait une fois par
   session via `@st.cache_data`, et le reste du code réutilise le
   DataFrame déjà propre.
"""
from __future__ import annotations

import glob
import os
import re
import unicodedata

import numpy as np
import pandas as pd

from config import COL_MAPPING

# Mots-clés indiquant qu'une valeur de 0 est légitime (donc à ne PAS
# transformer en donnée manquante). Pour toutes les autres métriques, un 0
# signifie presque toujours "non testé" plutôt qu'une vraie performance nulle.
_ZERO_AUTORISE_KEYWORDS = ("knee", "sit", "symetrie", "velocity decrement")

# Mots-clés indiquant une métrique "inversée" : une valeur PLUS PETITE est
# meilleure (temps de sprint, masse grasse, plis cutanés ISAK...).
_INVERTED_KEYWORDS = ("temps", "chrono", "10m", "505", "agilité", "masse grasse", "1km", "isak")


def remove_accents(s) -> str:
    """Retire les accents d'une chaîne (utile pour matcher des noms de colonnes)."""
    if not isinstance(s, str):
        return str(s)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def safe_get(row, key: str, default="-"):
    """
    Comme row.get(key, default), mais traite aussi NaN et chaîne vide comme
    'manquant'. BUG CORRIGÉ : row.get(key, default) ne renvoie le défaut que
    si la CLÉ est absente — si la colonne existe mais que la cellule est
    vide (NaN), il renvoie NaN tel quel, qui s'affichait ensuite comme la
    chaîne "nan" dans les rapports (ex: "AT · NAN" pour un joueur sans
    latéralité renseignée). Utiliser cette fonction partout où une valeur
    d'identité/anthropométrie est lue pour l'affichage évite ce défaut.
    """
    val = row.get(key, default)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    if isinstance(val, str) and val.strip() == "":
        return default
    return val


def is_inverted(label: str) -> bool:
    """Une métrique est 'inversée' si une valeur plus basse = meilleure performance."""
    return any(k in str(label).lower() for k in _INVERTED_KEYWORDS)



# Une chaîne n'est acceptée comme "nombre habillé" (ex: "12.5 kg", "-", "12,5")
# que si, une fois le nombre retiré, il ne reste que des caractères d'unité
# courts (lettres, °, /, %, espace...). Ça évite d'extraire un nombre depuis
# du texte parasite (ex: une cellule qui contient par erreur le nom de la
# colonne, ou un message d'erreur Excel type "#DIV/0!").
_NUMERIC_LIKE_RE = re.compile(r"^[-+]?\d*\.?\d+\s*[a-zA-Zµ°/%]{0,6}$")


def clean_numeric_value(val, col_name: str = ""):
    """
    Convertit une valeur de cellule Excel en float, en gérant :
    - les virgules comme séparateur décimal ("12,5" -> 12.5)
    - les tirets ou textes parasites ("-", "N/A" -> None)
    - un nombre suivi d'une courte unité ("12.5 kg" -> 12.5)
    - les zéros non significatifs (non testé) sauf pour les métriques où 0
      est une vraie valeur possible (cf. _ZERO_AUTORISE_KEYWORDS).

    IMPORTANT (bug corrigé pendant les tests de cette refonte) : la version
    précédente de cette fonction utilisait une regex "trouve le premier
    nombre dans la chaîne", appliquée par erreur à des colonnes entières
    contenant parfois du texte parasite (ex: une cellule où le nom de la
    colonne avait été recopié par erreur, ou "#DIV/0!"). Résultat : un
    nombre était extrait au milieu de ce texte (ex: "240" dans
    "...240°/s (N/kg)"), ce qui faussait silencieusement la moyenne du
    groupe de référence. Désormais, on vérifie que la chaîne RESSEMBLE
    globalement à un nombre habillé d'une unité avant d'en extraire quoi
    que ce soit ; sinon on renvoie None (valeur manquante), comme le ferait
    un simple `pd.to_numeric`.
    """
    if pd.isna(val) or val == "" or val == "-":
        return None
    try:
        if isinstance(val, (int, float, np.floating, np.integer)):
            v = float(val)
        else:
            # Retire aussi les espaces internes (séparateur de milliers FR,
            # normal ou insécable -- ex: "1 463,62") avant validation par
            # regex : sans ça, une valeur >= 1000 ne matchait jamais
            # _NUMERIC_LIKE_RE (qui n'autorise des espaces qu'en fin de
            # chaîne, avant l'unité) et était silencieusement perdue.
            val_str = re.sub(r'\s+', '', str(val).strip()).replace(",", ".")
            if not _NUMERIC_LIKE_RE.match(val_str):
                return None
            m = re.search(r"[-+]?\d*\.\d+|\d+", val_str)
            if not m:
                return None
            v = float(m.group())

        if v == 0.0 and col_name and not any(k in str(col_name).lower() for k in _ZERO_AUTORISE_KEYWORDS):
            return None
        return v
    except Exception:
        return None


def find_column(df: pd.DataFrame, label: str):
    """
    Retrouve la vraie colonne Excel correspondant à un label lisible.
    Priorité au mapping explicite (COL_MAPPING), puis recherche floue
    (insensible aux accents/casse) si le nom a légèrement changé.
    """
    mapped = COL_MAPPING.get(label)
    if mapped and mapped in df.columns:
        return mapped
    label_clean = remove_accents(label).lower().strip().replace("(g)", "").replace("(d)", "").strip()
    for c in df.columns:
        if label_clean in remove_accents(str(c)).lower().strip():
            return c
    return None


def locate_excel_file(directory: str = ".", preferred_name: str | None = None) -> str | None:
    """
    Cherche le fichier Excel de profilage dans `directory`.
    - Si `preferred_name` est fourni et existe, il est utilisé tel quel.
    - Sinon, on prend le .xlsx le plus récemment modifié du dossier (en
      ignorant les fichiers temporaires Excel qui commencent par '~$').
    Pourquoi cette approche : plutôt que de figer un nom de fichier exact
    (source du bug historique), l'app reste utilisable même si le fichier
    est renommé d'une saison à l'autre (ex: "Profilage_2027-2028.xlsx").
    """
    if preferred_name:
        candidate = os.path.join(directory, preferred_name)
        if os.path.exists(candidate):
            return candidate

    candidates = [
        f for f in glob.glob(os.path.join(directory, "*.xlsx"))
        if not os.path.basename(f).startswith("~$")
    ]
    if not candidates:
        return None
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _clean_numeric_series(series: pd.Series, col_name: str) -> pd.Series:
    """Applique clean_numeric_value à toute une colonne, une bonne fois pour toutes."""
    return series.apply(lambda v: clean_numeric_value(v, col_name))


# Colonnes qu'on ne cherche jamais à convertir en numérique (identité/texte).
_NON_NUMERIC_COLUMNS = {
    "Joueur", "Latéralité", "Poste", "Position", "Equipe", "Session", "Session exact",
    "Date de Naissance", "Pied départ 1080",
}


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applique le nettoyage numérique (virgules, tirets, zéros non
    significatifs — voir le point 2 du docstring de module) à un DataFrame
    DÉJÀ chargé, quelle que soit sa source. Extrait de load_and_clean_excel()
    pour être réutilisable avec une source autre qu'un fichier Excel local
    (ex : le DataFrame Google Sheets déjà chargé par l'app de profilage
    principale — voir load_and_clean_from_dataframe() juste en dessous).
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    if "Session" in df.columns:
        df["Session"] = df["Session"].astype(str)

    for col in df.columns:
        if col in _NON_NUMERIC_COLUMNS:
            continue
        if df[col].dtype == object:
            # Colonne potentiellement numérique avec virgules/tirets : on
            # nettoie avec la même logique que pour une valeur individuelle.
            df[col] = _clean_numeric_series(df[col], col)
        elif np.issubdtype(df[col].dtype, np.number):
            # Déjà numérique : on retire quand même les zéros non
            # significatifs pour rester cohérent avec clean_numeric_value.
            if not any(k in col.lower() for k in _ZERO_AUTORISE_KEYWORDS):
                df[col] = df[col].replace(0.0, np.nan)

    return df


def load_and_clean_from_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Variante de load_and_clean_excel() pour une source de données déjà en
    mémoire (ex : le Google Sheet chargé par l'app de profilage principale,
    via utils.load_data()) plutôt qu'un fichier Excel local. Ajoutée pour
    l'intégration à appV3 — remplace la copie Excel locale qui devait être
    mise à jour à la main.
    """
    return clean_dataframe(df)


def load_and_clean_excel(file_path: str, sheet_name: str = "Feuil1") -> pd.DataFrame:
    """
    Charge la feuille de données et nettoie TOUTES les colonnes numériques
    une seule fois (voir le point 2 du docstring de module ci-dessus).

    Cette fonction est volontairement non décorée par st.cache_data ici :
    c'est app.py qui l'enveloppe avec le cache Streamlit, pour garder ce
    module testable indépendamment de Streamlit (ex: en notebook R/Python
    pour tes analyses de thèse).
    """
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return clean_dataframe(df)

    return df
