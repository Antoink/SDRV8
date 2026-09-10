# =============================================================================
# charts.py — Graphiques Plotly partagés (DA SDR)
# =============================================================================
# Point d'entrée unique pour les radar charts de l'app (comparateur, clustering,
# team profiling...). Le style est calqué sur les radars historiques de
# profiling.py (fond transparent, grille claire, légende horizontale centrée),
# qui sert de référence de direction artistique pour toute l'app.
#
# Le radar du rapport PDF (profiling_report.create_radar_chart) reste à part
# car WeasyPrint ne peut pas exécuter de JS Plotly : il est rendu en
# matplotlib, mais reprend la même palette de couleurs (SDR_RED).
# =============================================================================

import plotly.graph_objects as go

from config_rapport import SDR_RED

# Couleurs par défaut pour les séries d'un radar multi-joueurs (2e, 3e série...).
# À utiliser quand aucune couleur n'est fournie explicitement dans `series`.
SDR_BLUE = "#1E3A8A"
SDR_GREY = "#888888"


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convertit une couleur hex (#RGB ou #RRGGBB) en chaîne rgba() avec l'opacité donnée."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch * 2 for ch in hex_color)  # #RGB -> #RRGGBB
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def build_radar(
    categories,
    series,
    *,
    value_range=(0, 100),
    height=350,
    transparent_bg=True,
    show_radial_ticks=False,
    radial_tickvals=None,
    radial_ticktext=None,
    tick_font_size=12,
    grid_color="#eee",
    tick_color="#111",
    legend=True,
    margin=None,
    zones=None,
):
    """
    Construit un radar chart Plotly avec la DA SDR (rouge #D71920, fond
    transparent, grille claire) — cf. les radars de profiling.py qui servent
    de référence visuelle pour toute l'app.

    Paramètres
    ----------
    categories : list[str]
        Labels des axes (ex : liste des tests physiques).
    series : list[dict]
        Une entrée par courbe à tracer. Clés possibles :
            "name"          : str, nom affiché dans la légende (obligatoire)
            "values"        : list[float], valeurs dans `value_range` (obligatoire)
            "color"         : str, couleur hex de la ligne/du remplissage (def. SDR_RED)
            "raw_values"    : list | None, valeurs brutes pour le hover (optionnel)
            "unit"          : str, unité affichée dans le hover si raw_values fourni
            "hovertext"     : list[str] | None, un hover HTML pré-construit par point
                              (sans le point de fermeture) — prioritaire sur
                              raw_values/hovertemplate, pour un hover entièrement
                              custom (ex : plusieurs infos par test).
            "fill"          : bool, remplir la zone (def. True ; False pour une
                              courbe de référence type "Moyenne équipe")
            "fill_opacity"  : float, opacité du remplissage (def. 0.2)
            "dash"          : bool, ligne pointillée (def. False)
            "width"         : int, épaisseur de ligne (def. 2)
            "markers"       : bool, afficher des points sur les sommets (def. True)
            "hovertemplate" : str, pour surcharger le hover par défaut
    value_range : tuple, échelle de l'axe radial (def. (0, 100))
    height : int, hauteur du graphique en px (def. 350, comme profiling.py)
    transparent_bg : bool, fond transparent (def. True)
    show_radial_ticks : bool, afficher les graduations radiales (def. False)
    radial_tickvals, radial_ticktext : listes optionnelles pour des graduations
        radiales custom (ex : [33, 66, 100] / ["33", "66", ""]) ; implique
        show_radial_ticks=True.
    tick_font_size : taille de police des labels d'axes (def. 12)
    grid_color, tick_color : couleurs de la grille et des labels d'axes
    legend : bool, afficher la légende (horizontale, centrée sous le graphique)
    margin : dict | None, marges Plotly (def. l=40, r=40, t=20, b=20)
    zones : list[tuple[float, str | None]] | None
        Bandes de fond colorées par seuil de percentile, ex (radar principal
        de profiling.py) :
            [(33, "rgba(215,25,32,0.15)"), (66, None),
             (95, "rgba(39,174,96,0.15)"), (100, "rgba(0,229,255,0.15)")]
        Le "None" marque une limite sans couleur (juste une graduation).
        Nécessite value_range=(0, 100) pour rester lisible.

    Retourne
    --------
    go.Figure, prête pour st.plotly_chart(fig, config={'displayModeBar': False})
    (la toolbar Plotly est masquée partout dans profiling.py — à répliquer côté
    appelant pour rester cohérent avec la DA de référence).
    """
    if not categories or not series:
        return go.Figure()

    cats_closed = list(categories) + [categories[0]]
    fig = go.Figure()

    if zones:
        for i, (upto, color) in enumerate(zones):
            zone_fill = "none" if color is None else ("toself" if i == 0 else "tonext")
            fig.add_trace(go.Scatterpolar(
                r=[upto] * len(cats_closed), theta=cats_closed,
                mode="lines", line=dict(width=0),
                fill=zone_fill, fillcolor=color,
                hoverinfo="skip", showlegend=False,
            ))

    for s in series:
        values_closed = list(s["values"]) + [s["values"][0]]
        color = s.get("color", SDR_RED)
        do_fill = s.get("fill", True)
        do_markers = s.get("markers", True)
        raw_values = s.get("raw_values")
        hovertext = s.get("hovertext")

        trace_kwargs = {}
        if hovertext is not None:
            # Hover entièrement custom (une chaîne HTML déjà construite par point).
            trace_kwargs["hoverinfo"] = "text"
            trace_kwargs["hovertext"] = list(hovertext) + [hovertext[0]]
        elif raw_values is not None:
            raw_closed = list(raw_values) + [raw_values[0]]
            unit = s.get("unit", "")
            trace_kwargs["hovertemplate"] = s.get(
                "hovertemplate",
                "%{theta}<br>Valeur : <b>%{customdata}" + unit + "</b><br>Score : %{r:.0f}<extra></extra>",
            )
            trace_kwargs["customdata"] = raw_closed
        else:
            trace_kwargs["hovertemplate"] = s.get("hovertemplate", "%{theta}<br><b>%{r:.1f}</b><extra></extra>")

        fig.add_trace(go.Scatterpolar(
            r=values_closed,
            theta=cats_closed,
            name=s["name"],
            mode="lines+markers" if do_markers else "lines",
            fill="toself" if do_fill else "none",
            fillcolor=_hex_to_rgba(color, s.get("fill_opacity", 0.2)) if do_fill else None,
            line=dict(color=color, width=s.get("width", 2), dash="dash" if s.get("dash", False) else "solid"),
            marker=dict(size=7, color=color) if do_markers else None,
            **trace_kwargs,
        ))

    radialaxis = dict(
        visible=True,
        range=list(value_range),
        showticklabels=show_radial_ticks or radial_tickvals is not None,
        gridcolor=grid_color,
        linecolor=grid_color,
        layer="below traces",
    )
    if radial_tickvals is not None:
        radialaxis["tickvals"] = radial_tickvals
        radialaxis["tickfont"] = dict(color="#888", size=9)
        if radial_ticktext is not None:
            radialaxis["ticktext"] = radial_ticktext

    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=radialaxis,
            angularaxis=dict(
                tickfont=dict(size=tick_font_size, color=tick_color, weight="bold"),
                gridcolor=grid_color,
                linecolor=grid_color,
                layer="below traces",
            ),
        ),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5, font=dict(size=12, color=tick_color)),
        margin=margin or dict(l=40, r=40, t=20, b=20),
        height=height,
        paper_bgcolor="rgba(0,0,0,0)" if transparent_bg else "white",
        plot_bgcolor="rgba(0,0,0,0)" if transparent_bg else "white",
    )
    return fig
