# -*- coding: utf-8 -*-
"""
glossary.py
===========
Glossaire des sigles de tests physiques utilisés dans l'appli, pour les
utilisateurs non-spécialistes (direction, agents de joueurs...).

Volontairement limité aux sigles pour lesquels une définition claire et
fiable est disponible -- pas de définition approximative ajoutée juste
pour "remplir" le glossaire.
"""

GLOSSARY = {
    "CMJ": (
        "Counter Movement Jump (« saut avec contre-mouvement »)",
        "Test de saut vertical où le joueur fléchit les jambes avant de sauter. "
        "Mesure la détente et la puissance des membres inférieurs.",
    ),
    "RSI": (
        "Reactive Strength Index (« indice de force réactive »)",
        "Rapport entre la hauteur de saut et le temps de contact au sol. "
        "Reflète la capacité à réagir vite au sol (pliométrie, changements d'appui).",
    ),
    "RFD": (
        "Rate of Force Development (« taux de développement de la force »)",
        "Vitesse à laquelle la force musculaire est produite. "
        "Un RFD élevé traduit une bonne capacité d'explosivité.",
    ),
    "DSI": (
        "Dynamic Strength Index (« indice de force dynamique »)",
        "Rapport entre la force maximale produite en mouvement (ex. saut) et la force "
        "maximale produite à l'arrêt (isométrique). Aide à orienter le travail : "
        "plutôt force maximale, ou plutôt vitesse/explosivité.",
    ),
    "mRSI": (
        "Modified Reactive Strength Index (« indice de force réactive modifié »)",
        "Variante du RSI, calculée à partir du temps total du mouvement "
        "(montée + descente) plutôt que du seul temps de contact au sol.",
    ),
    "LSI": (
        "Limb Symmetry Index (« indice de symétrie des membres »)",
        "Compare la performance du côté gauche à celle du côté droit, en %. "
        "Un écart marqué peut signaler une asymétrie à surveiller "
        "(souvent utilisé en retour de blessure).",
    ),
}


import re


def annotate_glossary_terms(text: str) -> str:
    """
    Entoure les sigles connus (CMJ, RSI, RFD, DSI, mRSI, LSI) d'un
    <span class="glossary-term" data-tooltip="..." tabindex="0"> dans un
    texte donné (typiquement un label de carte KPI). Un seul appel ici
    suffit pour "généraliser ce qui marche déjà" (le ℹ️ existant par
    endroits) sans avoir à retoucher chaque carte une par une.

    `data-tooltip` + CSS (.glossary-term, voir utils.local_css) plutôt que
    l'attribut `title` : `title` ne s'affiche qu'au survol souris, donc
    invisible sur téléphone/tablette (agents, direction consultant l'app
    sur mobile). `tabindex="0"` rend le span focusable au tap, et la CSS
    affiche le tooltip aussi bien sur :hover que sur :focus.

    `(?<![>\\w])...(?!\\w)` : bordures de mot, ET on ne matche jamais juste
    après un '>' pour ne pas ré-emballer un sigle déjà entouré d'une balise
    si la fonction est appelée deux fois sur le même texte.
    """
    if not text:
        return text
    result = text
    for sigle, (nom_complet, definition) in GLOSSARY.items():
        pattern = re.compile(rf'(?<![>\w]){re.escape(sigle)}(?!\w)')
        tooltip = f"{nom_complet} — {definition}".replace('"', "'")
        replacement = f'<span class="glossary-term" tabindex="0" data-tooltip="{tooltip}">{sigle}</span>'
        result = pattern.sub(replacement, result)
    return result


def render_glossary_expander():
    """
    Affiche le glossaire dans un st.expander (fermé par défaut) -- pensé
    pour être appelé une fois dans la sidebar, donc visible sur toutes les
    pages sans jamais encombrer le contenu principal.
    """
    import streamlit as st

    with st.expander("📖 Glossaire des sigles"):
        for sigle, (nom_complet, definition) in GLOSSARY.items():
            st.markdown(f"**{sigle}** — *{nom_complet}*  \n{definition}")
