# -*- coding: utf-8 -*-
"""
pdf_export.py
==============
Conversion du rapport HTML (déjà généré et validé visuellement) en PDF via
WeasyPrint, pour un vrai fichier téléchargeable plutôt qu'un "imprimer
depuis le navigateur".

POURQUOI RÉUTILISER LE MÊME HTML/CSS QUE LA VERSION QUI MARCHE DÉJÀ
---------------------------------------------------------------------
Le HTML produit par report_prepa.py / report_kine.py est déjà pensé pour
l'impression (règles `@media print`, `page-break`, `no-break`). WeasyPrint
respecte ces mêmes règles CSS. On ne réinvente donc pas une mise en page :
on convertit directement ce qui fonctionne déjà à l'écran/à l'impression
navigateur, ce qui minimise le risque de régression visuelle.

DÉPLOIEMENT SUR STREAMLIT CLOUD
---------------------------------
WeasyPrint dépend de bibliothèques système (Pango, Cairo, GDK-Pixbuf) qui ne
sont PAS installées par défaut sur Streamlit Community Cloud. Il faut un
fichier `packages.txt` à la racine du repo (fourni à côté de ce module) avec :
    libpango-1.0-0
    libpangocairo-1.0-0
    libcairo2
    libgdk-pixbuf2.0-0
    libffi-dev
Sans ce fichier, l'import de weasyprint échoue au démarrage de l'app.
`is_pdf_export_available()` permet de le détecter proprement et de replier
sur le HTML sans planter l'application.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def is_pdf_export_available() -> bool:
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


def html_to_pdf_bytes(html_content: str) -> bytes:
    """
    Convertit une chaîne HTML en bytes PDF.
    Lève une exception explicite si WeasyPrint n'est pas disponible ou si
    la conversion échoue — à catcher côté app.py pour proposer le repli HTML.
    """
    from weasyprint import HTML

    if not is_pdf_export_available():
        raise RuntimeError(
            "WeasyPrint n'est pas disponible dans cet environnement "
            "(dépendances système manquantes : voir packages.txt)."
        )
    return HTML(string=html_content).write_pdf()
