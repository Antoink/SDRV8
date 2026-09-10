import os
import sys

# Permet "from data_utils import ..." dans les tests, en ajoutant la racine
# du projet (le dossier parent de tests/) au chemin Python.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
