# -*- coding: utf-8 -*-
"""
pitch_profiling.py
====================
Visuel "terrain" (façon Football Manager) montrant le(s) poste(s) qu'un
joueur peut occuper : poste principal en plein rouge, postes secondaires en
rouge plus clair/transparent (nuance, pas de pointillé -- demande explicite
du département performance pour coller au rendu Football Manager). Première
brique du futur "profilage technico-tactique" à côté du profilage physique.

SOURCE DES DONNÉES (Google Sheet principal)
--------------------------------------------
  - "PositionPrincipale" : code de poste PRÉCIS (ex: "DLG" = Défenseur
    Latéral Gauche, "MC" = Milieu Central, "ATC" = Attaquant Centre...) --
    G/D/C en fin de code = Gauche/Droite/Centre.
  - "PositionSecondaire" : même format, optionnel -- un 2e poste que le
    joueur peut aussi jouer (façon Football Manager : poste "acquis" en
    plein, postes "praticables" en plus clair).
  - "Poste" : catégorie LARGE (Gardien/Défenseur/Milieu/Attaquant), utilisée
    en dernier repli (via BROAD_TO_SLOT) si aucune position précise n'est
    renseignée pour ce joueur.
"""
from __future__ import annotations

import unicodedata

SDR_RED = "#D71920"

# Emplacement (x%, y%) de chaque poste sur un terrain vertical (but du
# joueur en bas, y=100 ; but adverse en haut, y=0). Les postes à 2
# emplacements (gauche/droite) sont résolus via le suffixe G/D du code
# (ex: "DLG", "EXCD") ou, à défaut, la Latéralité du joueur.
POSITION_SLOTS: dict[str, list[tuple[float, float]]] = {
    "GB":  [(50, 93)],
    "DC":  [(35, 78), (65, 78)],
    "DL":  [(12, 75), (88, 75)],
    "MD":  [(50, 58)],
    "MC":  [(30, 46), (70, 46)],
    "MO":  [(50, 32)],
    "EXC": [(12, 22), (88, 22)],
    "AT":  [(50, 10)],
}

POSITION_LABELS = {
    "GB": "Gardien", "DC": "Défenseur central", "DL": "Défenseur latéral",
    "MD": "Milieu défensif", "MC": "Milieu central", "MO": "Milieu offensif",
    "EXC": "Excentré / Ailier", "AT": "Attaquant",
}

# "Poste" (catégorie large, colonne du Google Sheet) -> code de poste précis
# utilisé par défaut pour le placer sur le terrain, tant qu'aucune position
# précise (PositionSecondaire) n'est connue. Voir le DOUTE en haut de fichier.
BROAD_TO_SLOT = {
    "GARDIEN": "GB",
    "DEFENSEUR": "DC",
    "MILIEU": "MC",
    "ATTAQUANT": "AT",
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _resolve_code(raw: str | None) -> tuple[str | None, str | None]:
    """
    Résout une valeur brute (catégorie large "Défenseur" OU code précis
    "DLG"/"EXCD"/"MC"...) en (code_pitch, cote) où `code_pitch` est une clé
    de POSITION_SLOTS et `cote` vaut "G", "D" ou None (extrait du suffixe du
    code précis s'il y en a un -- "C" = centre, traité comme None/générique).
    Renvoie (None, None) si rien n'est reconnu.
    """
    if not raw:
        return None, None
    clean = _strip_accents(str(raw)).strip().upper()
    if not clean:
        return None, None

    # Alias rencontrés dans les données mais absents de POSITION_SLOTS.
    clean = {"ML": "MC"}.get(clean, clean)

    # 1. Code précis direct (déjà une clé de POSITION_SLOTS, ex: "MC", "MO").
    if clean in POSITION_SLOTS:
        return clean, None

    # 2. Code précis avec suffixe de côté (ex: "DLG" -> "DL" + "G", "EXCD" ->
    #    "EXC" + "D", "ATC" -> "AT" + "C" -> côté générique).
    for pos_code in sorted(POSITION_SLOTS, key=len, reverse=True):
        if clean.startswith(pos_code) and len(clean) > len(pos_code):
            suffix = clean[len(pos_code):]
            cote = suffix[0] if suffix and suffix[0] in ("G", "D") else None
            return pos_code, cote

    # 3. Catégorie large (ex: "DÉFENSEUR", "MILIEU"...).
    broad_key = clean.replace(" ", "")
    if broad_key in BROAD_TO_SLOT:
        return BROAD_TO_SLOT[broad_key], None

    return None, None


def _resolve_slot(raw_code: str, lateralite: str | None):
    pos_code, cote = _resolve_code(raw_code)
    slots = POSITION_SLOTS.get(pos_code) if pos_code else None
    if not slots:
        return None, None
    if len(slots) == 1:
        return slots[0], pos_code
    side = cote or (str(lateralite or "").strip().upper()[:1] if lateralite else None)
    if side == "G":
        return slots[0], pos_code
    if side == "D":
        return slots[1], pos_code
    return slots[0], pos_code


def _label_for(raw_code: str, lateralite) -> str:
    """
    Libellé lisible d'un code de poste, avec le côté (Gauche/Droite) quand
    le poste en a un -- ex: "Excentré Gauche" plutôt que juste "Excentré /
    Ailier" pour EXCG, pour que le texte distingue bien un joueur excentré
    gauche d'un excentré droit, pas seulement sa position sur le dessin.
    """
    slot, pos_code = _resolve_slot(raw_code, lateralite)
    if not pos_code:
        return str(raw_code)
    base = POSITION_LABELS.get(pos_code, pos_code)
    slots = POSITION_SLOTS.get(pos_code, [])
    if len(slots) <= 1:
        return base
    side = "Gauche" if slot == slots[0] else "Droite"
    return f"{base} {side}"


def _marker_svg(raw_code: str, lateralite, fill: str, stroke: str, stroke_width: float,
                 radius: float, label_size: float) -> str:
    slot, pos_code = _resolve_slot(raw_code, lateralite)
    if not slot or not pos_code:
        return ""
    x, y = slot
    return (
        f'<g><circle cx="{x}" cy="{y}" r="{radius}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" />'
        f'<text x="{x}" y="{y + 1.2}" text-anchor="middle" font-size="{label_size}" '
        f'font-weight="900" fill="#fff" font-family="Arial, sans-serif">{pos_code}</text></g>'
    )


def render_position_pitch(poste_principal: str | None, postes_secondaires: list[str] | None = None,
                           lateralite: str | None = None, height: int = 380) -> str:
    """
    Terrain vertical stylisé (fond vert classique, marqueurs rouge SDR) :
    poste principal en plein rouge, postes secondaires en rouge clair/
    transparent (nuance façon Football Manager, pas de pointillé). Accepte
    aussi bien une catégorie large ("Défenseur") qu'un code précis ("DLG",
    "MC"...) pour `poste_principal` -- voir _resolve_code. Un poste non
    reconnu est silencieusement ignoré plutôt que de faire planter
    l'affichage.
    """
    postes_secondaires = [p for p in (postes_secondaires or []) if p]

    # Tous les postes possibles, en fond, pour donner le contexte du terrain.
    background_markers = "".join(
        f'<circle cx="{x}" cy="{y}" r="3.2" fill="#ffffff40" stroke="#ffffff80" stroke-width="0.5" />'
        for slots in POSITION_SLOTS.values() for (x, y) in slots
    )

    # Nuance façon Football Manager : même rouge, opacité plus faible pour
    # le(s) poste(s) secondaire(s) -- pas de pointillé, un vrai dégradé de
    # couleur entre "principal" (plein) et "secondaire" (clair).
    sec_html = "".join(
        _marker_svg(c, lateralite, "rgba(215,25,32,0.45)", "#ffffffcc", 0.8, 5.4, 4)
        for c in postes_secondaires
    )
    main_html = _marker_svg(poste_principal, lateralite, SDR_RED, "#ffffff", 1, 6, 4.5) if poste_principal else ""

    legend_parts = []
    if main_html:
        legend_parts.append(
            f'<span style="display:inline-flex; align-items:center; gap:5px; margin-right:14px;">'
            f'<span style="width:10px; height:10px; border-radius:50%; background:{SDR_RED}; display:inline-block;"></span>'
            f'Principal : <b>{_label_for(poste_principal, lateralite)}</b></span>'
        )
    elif poste_principal:
        legend_parts.append(f'<span style="color:#c0392b;">Poste "{poste_principal}" non reconnu sur le terrain.</span>')

    secs_reconnus = []
    for c in postes_secondaires:
        pos_code, _ = _resolve_code(c)
        if pos_code:
            secs_reconnus.append(_label_for(c, lateralite))
    if secs_reconnus:
        legend_parts.append(
            f'<span style="display:inline-flex; align-items:center; gap:5px;">'
            f'<span style="width:10px; height:10px; border-radius:50%; background:rgba(215,25,32,0.45); display:inline-block;"></span>'
            f'Secondaire(s) : <b>{", ".join(secs_reconnus)}</b></span>'
        )
    elif not postes_secondaires:
        legend_parts.append(
            '<span style="color:#999; font-style:italic;">Poste secondaire : non renseigné</span>'
        )
    legend = "".join(legend_parts)

    # AUCUNE indentation dans cette chaîne, volontairement : st.markdown()
    # passe le HTML par un parseur Markdown avant de l'afficher, et
    # Markdown interprète toute ligne indentée de 4+ espaces comme un BLOC
    # DE CODE -- ça coupait le SVG en plein milieu. D'où l'absence totale
    # d'indentation ci-dessous.
    return (
        '<div style="display:flex; flex-direction:column; align-items:center; width:100%;">'
        f'<svg viewBox="0 0 100 100" style="width:100%; max-width:300px; height:{height}px; '
        'background:linear-gradient(#2e7d4f,#245f3e); border-radius:10px; border:2px solid #1c4a30;">'
        '<rect x="4" y="4" width="92" height="92" fill="none" stroke="#ffffff80" stroke-width="0.6" />'
        '<line x1="4" y1="50" x2="96" y2="50" stroke="#ffffff80" stroke-width="0.5" />'
        '<circle cx="50" cy="50" r="9" fill="none" stroke="#ffffff80" stroke-width="0.5" />'
        '<rect x="26" y="4" width="48" height="14" fill="none" stroke="#ffffff80" stroke-width="0.5" />'
        '<rect x="26" y="82" width="48" height="14" fill="none" stroke="#ffffff80" stroke-width="0.5" />'
        f'{background_markers}{sec_html}{main_html}'
        '</svg>'
        f'<div style="margin-top:8px; font-size:11px; color:#555; text-align:center;">{legend}</div>'
        '</div>'
    )
