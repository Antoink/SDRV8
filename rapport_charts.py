# -*- coding: utf-8 -*-
"""
charts.py
=========
Génération des visuels (radars, courbes d'évolution) en PNG base64,
directement intégrables dans le HTML du rapport (<img src="data:image/png;base64,...">).

POURQUOI matplotlib et pas Plotly pour les rapports ?
Plotly est utilisé dans l'app pour l'aperçu interactif (survol souris), mais
un graphique interactif n'a pas de sens dans un rapport HTML/PDF statique
imprimé. matplotlib produit un PNG léger, stable à l'impression et sans
dépendance JS — c'est ce qui est repris ici, identique à l'existant.
"""
from __future__ import annotations

import base64
from io import BytesIO
from math import pi

import matplotlib
matplotlib.use("Agg")  # backend sans interface graphique (obligatoire côté serveur)
import matplotlib.pyplot as plt

from config import SDR_RED, GREEN, ORANGE, BLUE_ELITE, DARK


def _fig_to_b64(fig, dpi: int = 200) -> str:
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", transparent=True, dpi=dpi)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return b64


def create_radar_chart(categories: list[str], values: list[float]) -> str:
    """Radar 'préparation physique' : % percentile par variable (0-100)."""
    if not categories:
        return ""
    N = len(categories)
    values_closed = values + values[:1]
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.fill_between(angles, 0, 33, color=SDR_RED, alpha=0.12)
    ax.fill_between(angles, 33, 66, color=ORANGE, alpha=0.12)
    ax.fill_between(angles, 66, 95, color=GREEN, alpha=0.12)
    ax.fill_between(angles, 95, 100, color=BLUE_ELITE, alpha=0.12)
    plt.xticks(angles[:-1], categories, color=DARK, size=10, weight="bold")
    ax.set_rlabel_position(0)
    plt.yticks([33, 66, 100], ["33", "66", ""], color="#888", size=8)
    plt.ylim(0, 100)
    ax.yaxis.grid(True, color="#ccc", linestyle="dashed")
    ax.xaxis.grid(True, color="#ccc")
    ax.spines["polar"].set_color("#ccc")
    ax.plot(angles, values_closed, linewidth=2, linestyle="solid", color=DARK, marker="o", markersize=6)
    ax.fill(angles, values_closed, color=DARK, alpha=0.35)
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    return _fig_to_b64(fig)


def create_radar_chart_kine(categories: list[str], vals_g: list[float], vals_d: list[float]) -> str:
    """Radar kiné G/D : % par rapport à l'objectif (échelle 50%-150%)."""
    if not categories:
        return ""
    N = len(categories)
    vg = vals_g + vals_g[:1]
    vd = vals_d + vals_d[:1]
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.fill_between(angles, 50, 80, color=SDR_RED, alpha=0.12)
    ax.fill_between(angles, 80, 100, color=ORANGE, alpha=0.12)
    ax.fill_between(angles, 100, 120, color=GREEN, alpha=0.12)
    ax.fill_between(angles, 120, 150, color=BLUE_ELITE, alpha=0.12)
    plt.xticks(angles[:-1], categories, color=DARK, size=10, weight="bold")
    ax.set_rlabel_position(0)
    plt.yticks([80, 100, 120], ["80%", "100%", "120%"], color="#888", size=8)
    plt.ylim(50, 150)
    ax.yaxis.grid(True, color="#ccc", linestyle="dashed")
    ax.xaxis.grid(True, color="#ccc")
    ax.spines["polar"].set_color("#ccc")
    ax.plot(angles, vg, linewidth=2, linestyle="solid", color="#3498DB", marker="o", markersize=6, label="Gauche")
    ax.plot(angles, vd, linewidth=2, linestyle="solid", color="#E74C3C", marker="o", markersize=6, label="Droite")
    ax.legend(loc="upper right", bbox_to_anchor=(1.2, 1.1))
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    return _fig_to_b64(fig)


def create_biodex_radar_matplotlib(cats: list[str], vals_l: list[float], vals_r: list[float], vals_norm: list[float]) -> str:
    """Radar Biodex (valeurs relatives N/kg) : Gauche / Droite / Objectif."""
    if not cats:
        return ""
    N = len(cats)
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]

    n_closed = vals_norm + [vals_norm[0]]
    l_closed = vals_l + [vals_l[0]]
    r_closed = vals_r + [vals_r[0]]

    fig, ax = plt.subplots(figsize=(5, 5), subplot_kw=dict(polar=True))
    plt.xticks(angles[:-1], cats, color=DARK, size=9, weight="bold")
    ax.set_rlabel_position(0)

    limit = max(max(vals_l + vals_r + vals_norm) * 1.1, 4.0)
    plt.ylim(0, limit)

    ax.plot(angles, n_closed, linewidth=2, linestyle="dashed", color="#2ECC71", label="Objectif")
    ax.fill(angles, n_closed, color="#2ECC71", alpha=0.1)
    ax.plot(angles, l_closed, linewidth=2, linestyle="solid", color="#1ABC9C", marker="o", label="Gauche")
    ax.fill(angles, l_closed, color="#1ABC9C", alpha=0.15)
    ax.plot(angles, r_closed, linewidth=2, linestyle="solid", color="#9B59B6", marker="o", label="Droite")
    ax.fill(angles, r_closed, color="#9B59B6", alpha=0.15)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    return _fig_to_b64(fig, dpi=150)


def create_evolution_chart(df, player: str, col_name: str, label: str, use_rel: bool = False) -> str:
    """Courbe d'évolution longitudinale d'une métrique pour un joueur (toutes sessions confondues)."""
    if "Session" not in df.columns or col_name not in df.columns:
        return ""
    player_data = df[df["Joueur"] == player].dropna(subset=[col_name, "Session"]).sort_values("Session")
    if len(player_data) < 2:
        return ""

    y_vals = player_data[col_name]
    if use_rel and "Poids (kg)" in player_data.columns:
        y_vals = y_vals / player_data["Poids (kg)"]

    fig, ax = plt.subplots(figsize=(5, 2.5))
    ax.plot(player_data["Session"].astype(str), y_vals, marker="o", color=SDR_RED, linewidth=2, markersize=5)
    ax.set_title(label.upper(), fontsize=9, color=DARK, weight="bold")
    ax.tick_params(axis="x", labelsize=7, colors="#666", rotation=30)
    ax.tick_params(axis="y", labelsize=7, colors="#666")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.yaxis.grid(True, color="#eee", linestyle="dashed")
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    return _fig_to_b64(fig, dpi=150)


def create_isak_radar(categories: list[str], values: list[float], max_scale: float = 15) -> str:
    """
    Radar du protocole ISAK (8 plis cutanés, valeurs brutes en mm).
    Contrairement aux autres radars de l'app, celui-ci n'est pas un
    percentile ni un %objectif : c'est la valeur mesurée telle quelle,
    sur une échelle fixe 0-`max_scale` mm (cohérente avec la plage
    généralement observée : ~1.5 à 14mm selon les sites et les joueurs).
    """
    if not categories:
        return ""
    N = len(categories)
    values_closed = values + values[:1]
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]

    scale = max(max_scale, max(values) * 1.1) if values else max_scale

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    plt.xticks(angles[:-1], categories, color=DARK, size=9, weight="bold")
    ax.set_rlabel_position(0)
    plt.yticks([scale / 3, 2 * scale / 3, scale], [f"{scale/3:.0f}", f"{2*scale/3:.0f}", f"{scale:.0f}"], color="#888", size=8)
    plt.ylim(0, scale)
    ax.yaxis.grid(True, color="#ccc", linestyle="dashed")
    ax.xaxis.grid(True, color="#ccc")
    ax.spines["polar"].set_color("#ccc")
    ax.plot(angles, values_closed, linewidth=2, linestyle="solid", color="#8E44AD", marker="o", markersize=6)
    ax.fill(angles, values_closed, color="#8E44AD", alpha=0.25)
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    return _fig_to_b64(fig)


def note_bruit_mesure() -> str:
    """Rappel méthodologique à afficher sous les courbes d'évolution."""
    return (
        "Note : les variations de faible amplitude peuvent relever du bruit de mesure "
        "inhérent aux tests (SNR limité sur des tests uniques). À interpréter avec prudence, "
        "idéalement en tendance sur plusieurs sessions plutôt que point à point."
    )
