"""
Correspondance entre les noms de colonnes "identité" du fichier Excel /
Google Sheet et les noms de colonnes SQL de la table `joueurs`.

Avec le schéma v2 (voir schema_profilage.sql), seules ces colonnes
d'identité ont une colonne SQL dédiée. Toutes les autres colonnes (les
~100 tests) sont stockées de façon flexible dans la table `mesures`
(une ligne par test, avec son nom Excel/Sheet d'origine tel quel) —
il n'y a donc plus besoin d'un dictionnaire de correspondance pour elles :
ajouter un nouveau test dans le Google Sheet n'exige aucune modification ici.
"""

# Colonnes "identité" du joueur (peu ou pas de changement dans le temps)
# -> table `joueurs`
IDENTITY_COLUMNS = {
    'Joueur': 'nom',
    'N° GPS': 'n_gps',
    'Latéralité': 'lateralite',
    'Poste': 'poste',
    'Position': 'position',
    'Date de Naissance': 'date_de_naissance',
    'Equipe': 'equipe',
}

# Colonnes qui définissent la session (pas des tests) -> table `sessions`
SESSION_COLUMNS = {
    'Session': 'session_label',
    'Session exact': 'session_date',
}

IDENTITY_COLUMNS_REVERSE = {v: k for k, v in IDENTITY_COLUMNS.items()}
SESSION_COLUMNS_REVERSE = {v: k for k, v in SESSION_COLUMNS.items()}
