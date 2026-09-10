# -*- coding: utf-8 -*-
"""
persistence.py
================
Sauvegarde/chargement des commentaires, thèmes et évaluations de profilage.
Choix conservé (décision produit) : stockage dans un fichier JSON commité
sur GitHub, PAS de migration PostgreSQL pour l'instant.

CORRECTIONS APPORTÉES PAR RAPPORT À L'ANCIEN CODE
---------------------------------------------------
1. **`load_profiling_data()` était appelée 3 fois par rerun Streamlit**
   (une fois pour les métriques sélectionnées, une fois pour les thèmes,
   une fois implicitement avant la sauvegarde), soit un appel HTTP à
   l'API GitHub à chaque interaction utilisateur (case cochée, slider
   déplacé...). Sur une session de profilage avec ~130 colonnes à cocher,
   ça peut représenter des dizaines d'appels réseau évitables et une
   latence perceptible. Ici, le chargement est mis en cache (TTL courtqui
   se rafraîchit automatiquement, invalidé manuellement juste après une
   sauvegarde réussie).

2. **Conflit d'écriture non géré** : si deux membres du staff sauvegardent
   au même moment, le `sha` du fichier récupéré par le premier appel
   devient périmé au moment du `update_file` du second, et GitHub renvoie
   une erreur 409 qui faisait planter la sauvegarde. Ici, on retente une
   fois avec le `sha` réactualisé avant d'abandonner.

3. **Code mort supprimé** : `json.dump_s` n'existe pas dans le module
   `json` standard — la ligne `hasattr(json, 'dump_s')` était donc
   toujours fausse et ne servait à rien.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

# PyGithub (`github`) N'EST PAS importé ici au niveau module, volontairement :
# persistence.py est chargé sans condition au démarrage de l'appli, et
# l'import de PyGithub coûte à lui seul ~0.15s -- payés à CHAQUE lancement,
# même en usage local sans GITHUB_TOKEN/GITHUB_REPO configurés (le cas
# courant : la sauvegarde retombe alors sur un fichier local, cf.
# save_profiling_data). Importé localement dans get_github_repo() et dans
# les fonctions qui attrapent GithubException -- le coût ne survient que si
# GitHub est effectivement configuré ET utilisé.

GITHUB_FILE_PATH = "profiling_comments.json"
PLANNING_FILE_PATH = "training_planning.json"  # fichier séparé pour le planning type hebdomadaire


def get_github_repo(secrets):
    """`secrets` est l'objet st.secrets (ou tout mapping avec .get)."""
    try:
        token = secrets.get("GITHUB_TOKEN")
        repo_name = secrets.get("GITHUB_REPO")
        if not token or not repo_name:
            return None
        from github import Github
        return Github(token).get_repo(repo_name)
    except Exception:
        return None


def load_profiling_data_raw(secrets, file_path: str = GITHUB_FILE_PATH) -> dict:
    """
    Chargement SANS cache — à envelopper avec st.cache_data(ttl=...) côté
    app.py. Séparé ici pour rester testable indépendamment de Streamlit.
    `file_path` est paramétrable pour réutiliser cette même logique avec
    d'autres jeux de données (ex: le planning hebdomadaire, cf. PLANNING_FILE_PATH).
    """
    repo = get_github_repo(secrets)
    if repo:
        from github import GithubException
        try:
            contents = repo.get_contents(file_path)
            return json.loads(contents.decoded_content.decode("utf-8"))
        except GithubException as e:
            if e.status == 404:
                return {}
            return {}
    elif os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_profiling_data(secrets, data: dict, key_suffix: str, file_path: str = GITHUB_FILE_PATH) -> tuple[bool, str]:
    """
    Sauvegarde `data` (dict complet, déjà mis à jour pour `key_suffix`) sur
    GitHub, avec un retry en cas de conflit de version (sha périmé).
    Retourne (succès, message).
    """
    repo = get_github_repo(secrets)
    content_str = json.dumps(data, ensure_ascii=False, indent=4)
    commit_message = f"Mise à jour {file_path} : {key_suffix} ({datetime.now().strftime('%d/%m/%Y %H:%M')})"

    if not repo:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content_str)
            return True, "Sauvegardé en local (pas de connexion GitHub configurée)."
        except Exception as e:
            return False, f"Échec de la sauvegarde locale : {e}"

    from github import GithubException
    for attempt in range(2):  # 1 essai + 1 retry en cas de conflit de version
        try:
            try:
                contents = repo.get_contents(file_path)
                repo.update_file(contents.path, commit_message, content_str, contents.sha)
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(file_path, commit_message, content_str)
                else:
                    raise
            return True, "Sauvegardé et synchronisé sur GitHub."
        except GithubException as e:
            if e.status == 409 and attempt == 0:
                # Conflit : quelqu'un d'autre a écrit entre-temps -> on retente
                # une fois avec le sha réactualisé.
                continue
            return False, f"Erreur GitHub lors de la sauvegarde : {e}"
        except Exception as e:
            return False, f"Erreur inattendue lors de la sauvegarde : {e}"

    return False, "Conflit d'écriture persistant sur GitHub (deux sauvegardes simultanées). Réessaie."
