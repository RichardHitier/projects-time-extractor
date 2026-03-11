#!/usr/bin/env python3
"""
Swimlane / Gantt par projet à partir d'un export Pomofocus.
Usage : python swimlane.py pomofocus_report.csv [output.png]

- Une ligne par jour calendaire (du premier au dernier, sans trou)
- Tous les projets sur la même ligne, barres colorées par projet
- Axe X = heure de la journée (8h-20h)
"""

import sys
from datetime import datetime, timedelta

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker

from config import load_config

# ── Couleurs par projet ───────────────────────────────────────────────────────
PROJECT_COLORS = {
    "speasy_hapi":   "#00b4d8",
    "colibri_dev":   "#f77f00",
    "colibri_admin": "#06d6a0",
}
DEFAULT_COLOR = "#a0aec0"

def color_for(p):
    return PROJECT_COLORS.get(p, DEFAULT_COLOR)

# ── Chargement & parsing ──────────────────────────────────────────────────────
def load(path):
    df = pd.read_csv(path, sep=",", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    df["project"] = df["project"].str.strip().str.strip('"')
    df["task"]    = df["task"].str.strip().str.strip('"')
    df = df[df["minutes"] > 0].copy()

    def to_dt(row, col):
        return datetime.strptime(f"{int(row['date'])} {row[col]}", "%Y%m%d %H:%M")

    df["start"] = df.apply(lambda r: to_dt(r, "startTime"), axis=1)
    df["end"]   = df.apply(lambda r: to_dt(r, "endTime"),   axis=1)

    mask = df["end"] <= df["start"]
    df.loc[mask, "end"] = df.loc[mask, "start"] + pd.to_timedelta(df.loc[mask, "minutes"], unit="m")

    df["date_only"] = df["start"].dt.date
    return df

def to_h(dt):
    return dt.hour + dt.minute / 60

# ── Plot ──────────────────────────────────────────────────────────────────────
def plot(df, output="swimlane.png"):
    first = df["date_only"].min()
    last  = df["date_only"].max()
    all_dates = []
    d = first
    while d <= last:
        all_dates.append(d)
        d += timedelta(days=1)

    projects = sorted(df["project"].unique())
    n_days   = len(all_dates)
    X_MIN, X_MAX = 8, 20

    fig, ax = plt.subplots(figsize=(14, max(6, n_days * 0.55 + 2)), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    for sp in ax.spines.values():
        sp.set_visible(False)

    BAR_H = 0.65

    for yi, day in enumerate(all_dates):
        y = yi
        is_we = day.weekday() >= 5
        ax.barh(y, X_MAX - X_MIN, left=X_MIN, height=0.92,
                color="#111827" if not is_we else "#0a0f1a",
                zorder=1, linewidth=0)
        ax.axhline(y + 0.5, color="#1e2535", linewidth=0.5, zorder=2)

        day_df = df[df["date_only"] == day]
        for _, row in day_df.iterrows():
            x0 = max(to_h(row["start"]), X_MIN)
            x1 = min(to_h(row["end"]),   X_MAX)
            if x1 <= x0:
                continue
            ax.barh(y, x1 - x0, left=x0, height=BAR_H,
                    color=color_for(row["project"]),
                    alpha=0.9, zorder=3, linewidth=0)
            if (x1 - x0) > 0.33:
                ax.text((x0 + x1) / 2, y,
                        f"{row['minutes']}m",
                        ha="center", va="center",
                        fontsize=7, color="#ffffff", fontweight="bold",
                        zorder=4)

    ax.set_yticks(range(n_days))
    labels = [d.strftime("%a %d/%m") for d in all_dates]
    ax.set_yticklabels(labels, fontsize=9, fontfamily="monospace")
    for tick, day in zip(ax.get_yticklabels(), all_dates):
        tick.set_color("#3d4455" if day.weekday() >= 5 else "#9ca3af")

    ax.set_ylim(n_days - 0.5, -0.5)
    ax.tick_params(axis="y", length=0, pad=8)

    ax.set_xlim(X_MIN, X_MAX)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):02d}h"))
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", colors="#4a5568", labelsize=8, length=0)

    for h in range(X_MIN, X_MAX + 1):
        ax.axvline(h, color="#1e2535", linewidth=0.6, linestyle="--", zorder=0)

    patches = [mpatches.Patch(color=color_for(p), label=p) for p in projects]
    ax.legend(handles=patches, loc="lower right",
              framealpha=0.2, facecolor="#0d1117", edgecolor="#2d3748",
              labelcolor="#d1d5db", fontsize=9, borderpad=0.8)

    fig.text(0.005, 0.99, "Swimlane · activité par projet",
             color="#f9fafb", fontsize=13, fontweight="bold", va="top")

    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight", facecolor="#0d1117")
    print(f"Image generated : {output}")

if __name__ == "__main__":
    _config = load_config()
    pomofocus_file = _config["POMOFOCUS_FILEPATH"]
    csv_path = sys.argv[1] if len(sys.argv) > 1 else pomofocus_file
    output   = sys.argv[2] if len(sys.argv) > 2 else "swimlane.png"
    df = load(csv_path)
    df = df[df["date_only"] >= (datetime.now().date() - timedelta(days=30))]
    plot(df, output)
