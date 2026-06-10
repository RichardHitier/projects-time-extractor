import hashlib
import locale
import math
import re
from datetime import timedelta

import matplotlib.cm as cm
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import pandas as pd
from matplotlib import pyplot as plt
from odf.opendocument import load as load_ods
from odf.table import Table, TableCell, TableRow
from odf.text import P

from config import load_projects
from core.services import parse_task

plt.style.use("ggplot")
locale.setlocale(locale.LC_NUMERIC, "fr_FR.UTF-8")


def report_view_project(df):
    """Print a per-project daily duration summary to stdout.

    Args:
        df: DataFrame with columns date, project, duration_m.
    """
    for project, grp in df.groupby("project"):
        total_h = grp["duration_m"].sum() / 60
        total_d = total_h / 8
        print(f"\nProject: {project}  Total: {total_d:.1f} d")
        daily = grp.groupby("date")["duration_m"].sum()
        for date, minutes in daily.items():
            print(
                f"  - {date.strftime('%Y-%m-%d')} :"
                f"  duration = {minutes / 60:5.2f} h"
            )


def report_view_projectlogs(df):
    """Print a monthly CSV log of tasks with parsed issue IDs to stdout.

    Parses each task string with parse_task(), groups by month and issue,
    sums duration_d, then prints CSV with ';' separator.

    Args:
        df: DataFrame with columns:
          date, project, sub_project, task, duration_d.
    """
    df_copy = df.copy()
    parsed = df_copy["task"].apply(parse_task)
    df_copy["issue_id"] = parsed.apply(lambda x: x[0])
    df_copy["issue_name"] = parsed.apply(lambda x: x[1])
    df_copy["task_description"] = parsed.apply(lambda x: x[2])
    df_copy["issue_id"] = (
        df_copy["issue_id"].astype("Int64").astype("string").fillna("")
    )
    for col in ["issue_name", "task_description"]:
        df_copy[col] = df_copy[col].str.strip().str.lower()
    df_copy = df_copy[
        [
            "date",
            "project",
            "sub_project",
            "issue_id",
            "issue_name",
            "task_description",
            "duration_d",
        ]
    ]
    df_copy["date"] = pd.to_datetime(df_copy["date"])
    df_copy["month"] = df_copy["date"].dt.to_period("M")
    locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
    df_copy["month_str"] = df_copy["date"].dt.strftime("%B")
    result = (
        df_copy.groupby(
            ["month_str", "issue_id", "issue_name", "task_description"],
            dropna=False,
        )["duration_d"]
        .sum()
        .reset_index()
    )
    result["duration_d"] = result["duration_d"].round(1)
    print(result.to_csv(sep=";", index=False, decimal=","))


def report_view_table(df):
    """Print a formatted table of Pomofocus records to stdout.

    Args:
        df: DataFrame with columns date, project, sub_project, task,
            duration_m, duration_h, duration_d.
    """
    header_line = (
        f"{'date':<12}| {'project':<20}| {'sub_project':<20}| {'task':<35}| "
        f"{'minutes':>10} | {'hours':>10} | {'days':>10} | {'cumul':>10}"
    )
    print()
    print(header_line)
    separation_line = header_line.replace("|", "+")
    separation_line = re.sub(r"[^+]", "-", separation_line)
    print(separation_line)
    cumul = 0.0
    for _, row in df.sort_values("date", ascending=True).iterrows():
        duration_m = locale.format_string("%3.2f", row["duration_m"])
        duration_h = locale.format_string("%3.2f", row["duration_h"])
        duration_d = locale.format_string("%3.2f", row["duration_d"])
        cumul += row["duration_d"]
        cumul_str = locale.format_string("%3.2f", cumul)
        date_str = row["date"].strftime("%Y-%m-%d")
        project_str = row["project"]
        task_str = row["task"][:35]
        sub_project_str = row["sub_project"][:20]
        print(
            f"{date_str:<12}| {project_str:<20}| {sub_project_str:<20}| "
            f"{task_str:<35}| "
            f"{duration_m:>10} | {duration_h:>10} | {duration_d:>10} | {cumul_str:>10}"
        )


def report_view_export(df, quantize=False):
    """Print a semicolon-delimited export of Pomofocus records to stdout.

    Args:
        df: DataFrame with columns:
          date, project, sub_project, task, duration_d.
        quantize: if True, round duration_d to nearest 1/16 (30 min).
    """
    projects = load_projects()
    export_name_map = {
        name: cfg["export_name"]
        for name, cfg in projects.items()
        if isinstance(cfg, dict) and "export_name" in cfg
    }
    header_line = (
        f"\n{'date'};{'project'};{'sub_project'};{'task'};{'duration_d'}"
    )
    print(header_line)
    for _, row in df.iterrows():
        if quantize:
            value = math.ceil(row["duration_d"] / 0.03125) * 0.03125
            duration_d = locale.format_string("%3.4f", value)
        else:
            duration_d = locale.format_string("%3.2f", row["duration_d"])
        date_str = row["date"].strftime("%Y-%m-%d")
        project_str = export_name_map.get(row["project"], row["project"])
        task_str = row["task"]
        sub_project_str = row["sub_project"]
        print(
            f"{date_str};{project_str};{sub_project_str};"
            f"{task_str};{duration_d}"
        )


_FRENCH_MONTHS = {
    1: "jan", 2: "fev", 3: "mar", 4: "avr", 5: "mai", 6: "juin",
    7: "juil", 8: "aout", 9: "sep", 10: "oct", 11: "nov", 12: "dec",
}


def _month_sheet_name(date):
    return f"{_FRENCH_MONTHS[date.month]}_{str(date.year)[2:]}"


def _ods_data_row(date, project, sub_project, task, duration_d):
    quantized = math.ceil(duration_d / 0.03125) * 0.03125
    row = TableRow()
    date_cell = TableCell(valuetype="date", datevalue=date.strftime("%Y-%m-%d"))
    date_cell.addElement(P(text=date.strftime("%Y-%m-%d")))
    row.addElement(date_cell)
    for text in (project, sub_project, task):
        cell = TableCell(valuetype="string")
        cell.addElement(P(text=str(text)))
        row.addElement(cell)
    num_cell = TableCell(valuetype="float", value=str(quantized))
    num_cell.addElement(P(text=str(quantized)))
    row.addElement(num_cell)
    return row


def yyyymm_to_sheet_name(yyyymm):
    """Convert '202606' → 'juin_26'."""
    year, month = int(yyyymm[:4]), int(yyyymm[4:])
    return f"{_FRENCH_MONTHS[month]}_{str(year)[2:]}"


def report_view_ods(df, ods_path, only_months=None):
    """Write export data to ODS month sheets.

    Args:
        only_months: list of sheet names to write (e.g. ['juin_26']).
                     Defaults to current month only.
    """
    if only_months is None:
        only_months = [_month_sheet_name(pd.Timestamp.today())]

    projects = load_projects()
    export_name_map = {
        name: cfg["export_name"]
        for name, cfg in projects.items()
        if isinstance(cfg, dict) and "export_name" in cfg
    }

    df = df.copy()
    df["project"] = df["project"].map(lambda p: export_name_map.get(p, p))
    df["_sheet"] = df["date"].apply(_month_sheet_name)
    df = df[df["_sheet"].isin(only_months)]

    doc = load_ods(ods_path)
    sheets = {
        s.getAttribute("name"): s
        for s in doc.spreadsheet.getElementsByType(Table)
    }

    written = {}
    for sheet_name, group in df.groupby("_sheet"):
        if sheet_name not in sheets:
            print(f"Warning: sheet '{sheet_name}' not found, skipping")
            continue
        target = sheets[sheet_name]
        rows = list(target.getElementsByType(TableRow))
        for row in rows[2:]:
            target.removeChild(row)
        for _, r in group.iterrows():
            target.addElement(
                _ods_data_row(r["date"], r["project"], r["sub_project"],
                              r["task"], r["duration_d"])
            )
        written[sheet_name] = len(group)

    doc.save(ods_path)
    for name, count in written.items():
        print(f"  {name}: {count} lignes écrites")


def _project_color_map(project_names):
    """Return a stable {project_name: color} dict.

    Uses the 'color' field from projects-config.yml when defined (keyed by
    pom_project name), otherwise derives a color by hashing the project name
    into a 40-slot palette (tab20 + tab20b).
    """
    projects_cfg = load_projects()
    palette = [cm.tab20(i / 20) for i in range(20)] + [cm.tab20b(i / 20) for i in range(20)]

    cfg_colors = {}
    for proj_data in (projects_cfg or {}).values():
        if not isinstance(proj_data, dict):
            continue
        color = proj_data.get("color")
        if not color:
            continue
        pom = proj_data.get("pom_project")
        for name in ([pom] if isinstance(pom, str) else (pom or [])):
            cfg_colors[name.lower()] = color

    result = {}
    for name in project_names:
        if name.lower() in cfg_colors:
            result[name] = cfg_colors[name.lower()]
        else:
            idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(palette)
            result[name] = palette[idx]
    return result


def plot_day_bars(df_plot, output="day_bars.png", show=False):
    """Render a stacked bar chart of daily hours per project.

    Saves to `output` by default; displays on screen instead when show=True.
    X-axis ticks are placed on Mondays; vertical lines mark week boundaries.

    Args:
        df_plot: DataFrame indexed by date with one column per project,
                 values are hours worked.  Typically produced by pivoting
                 load_pomo_for_day_bars() output.
        output: File path for the PNG (ignored when show=True).
        show: If True, call plt.show() instead of saving to file.
    """
    color_map = _project_color_map(df_plot.columns)
    colors = [color_map[col] for col in df_plot.columns]
    fig, ax = plt.subplots(figsize=(10, 6))
    df_plot.plot(
        ax=ax,
        kind="bar",
        stacked=True,
        color=colors,
        width=0.8,
        align="edge",
    )
    plt.ylabel("Hours", fontsize=12)
    plt.xlabel("Date", fontsize=12)
    plt.title("Time spent per project per day", fontsize=14)

    dates = df_plot.index
    monday_idx = [i for i, d in enumerate(dates) if d.weekday() == 0]
    ax.set_xticks(monday_idx)
    ax.set_xticklabels(
        [dates[i].strftime("%a %d/%m") for i in monday_idx],
        rotation=45,
        ha="right",
    )
    for x in monday_idx:
        ax.axvline(x=x, color="black", linewidth=0.8, alpha=0.6)
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.legend(title="Project", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    if show:
        plt.show()
    else:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")


def plot_swimlane(df, output="swimlane.png", show=False):
    """Render a Gantt-style swimlane of daily activity periods by project.

    X-axis: hour of day. Y-axis: calendar days (top = most recent).
    Bars are colored by project using the same color map as plot_day_bars.

    Args:
        df: DataFrame from load_pomo_for_swimlane().
        output: File path for the PNG (ignored when show=True).
        show: If True, call plt.show() instead of saving to file.
    """
    first = df["date_only"].min()
    last = df["date_only"].max()
    all_dates = []
    d = first
    while d <= last:
        all_dates.append(d)
        d += timedelta(days=1)

    projects = sorted(df["project"].unique())
    color_map = _project_color_map(projects)
    n_days = len(all_dates)
    X_MIN, X_MAX = 8, 20

    fig, ax = plt.subplots(figsize=(14, max(6, n_days * 0.55 + 2)))

    BAR_H = 0.65
    bg_normal = "white"
    bg_weekend = "#f0f0f0"
    for yi, day in enumerate(all_dates):
        is_we = day.weekday() >= 5
        ax.barh(yi, X_MAX - X_MIN, left=X_MIN, height=0.92,
                color=bg_weekend if is_we else bg_normal,
                zorder=1, linewidth=0)
        ax.axhline(yi + 0.5, color="#cccccc", linewidth=0.5, zorder=2)

        for _, row in df[df["date_only"] == day].iterrows():
            x0 = max(row["start"].hour + row["start"].minute / 60, X_MIN)
            x1 = min(row["end"].hour + row["end"].minute / 60, X_MAX)
            if x1 <= x0:
                continue
            ax.barh(yi, x1 - x0, left=x0, height=BAR_H,
                    color=color_map[row["project"]],
                    alpha=0.9, zorder=3, linewidth=0)
            if (x1 - x0) > 0.33:
                ax.text((x0 + x1) / 2, yi, f"{row['duration_m']}m",
                        ha="center", va="center",
                        fontsize=7, color="white", fontweight="bold",
                        zorder=4)

    ax.set_yticks(range(n_days))
    ax.set_yticklabels(
        [d.strftime("%a %d/%m") for d in all_dates],
        fontsize=9, fontfamily="monospace"
    )
    for tick, day in zip(ax.get_yticklabels(), all_dates):
        tick.set_alpha(0.4 if day.weekday() >= 5 else 1.0)
    ax.set_ylim(n_days - 0.5, -0.5)
    ax.tick_params(axis="y", length=0, pad=8)

    ax.set_xlim(X_MIN, X_MAX)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: f"{int(x):02d}h")
    )
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", labelsize=8, length=0)

    for h in range(X_MIN, X_MAX + 1):
        ax.axvline(h, color="#aaaaaa", linewidth=0.6, linestyle="--", zorder=2)

    patches = [mpatches.Patch(color=color_map[p], label=p) for p in projects]
    ax.legend(handles=patches, loc="lower right", fontsize=9, borderpad=0.8)
    ax.set_title("Activité par projet · swimlane", fontsize=13, fontweight="bold")
    fig.tight_layout()
    if show:
        plt.show()
    else:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        print(f"Saved: {output}")
