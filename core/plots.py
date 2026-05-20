import locale
import re

import pandas as pd
from matplotlib import pyplot as plt

from core.services import parse_task

locale.setlocale(locale.LC_NUMERIC, "fr_FR.UTF-8")


def report_view_project(df):
    """Print a per-project daily duration summary to stdout.

    Args:
        df: DataFrame with columns date, project, duration_m.
    """
    for project, grp in df.groupby("project"):
        print(f"\nProject: {project}")
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
        f"{'minutes':>10} | {'hours':>10} | {'days':>10}"
    )
    print()
    print(header_line)
    separation_line = header_line.replace("|", "+")
    separation_line = re.sub(r"[^+]", "-", separation_line)
    print(separation_line)
    for _, row in df.iterrows():
        duration_m = locale.format_string("%3.2f", row["duration_m"])
        duration_h = locale.format_string("%3.2f", row["duration_h"])
        duration_d = locale.format_string("%3.2f", row["duration_d"])
        date_str = row["date"].strftime("%Y-%m-%d")
        project_str = row["project"]
        task_str = row["task"][:35]
        sub_project_str = row["sub_project"][:20]
        print(
            f"{date_str:<12}| {project_str:<20}| {sub_project_str:<20}| "
            f"{task_str:<35}| "
            f"{duration_m:>10} | {duration_h:>10} | {duration_d:>10}"
        )


def report_view_export(df):
    """Print a semicolon-delimited export of Pomofocus records to stdout.

    Args:
        df: DataFrame with columns:
          date, project, sub_project, task, duration_d.
    """
    header_line = (
        f"\n{'date'};{'project'};{'sub_project'};{'task'};{'duration_d'}"
    )
    print(header_line)
    for _, row in df.iterrows():
        duration_d = locale.format_string("%3.2f", row["duration_d"])
        date_str = row["date"].strftime("%Y-%m-%d")
        project_str = row["project"]
        task_str = row["task"]
        sub_project_str = row["sub_project"]
        print(
            f"{date_str};{project_str};{sub_project_str};"
            f"{task_str};{duration_d}"
        )


def plot_day_bars(df_plot):
    """Display a stacked bar chart of daily hours per project.

    X-axis ticks are placed on Mondays; vertical lines mark week boundaries.

    Args:
        df_plot: DataFrame indexed by date with one column per project,
                 values are hours worked.  Typically produced by pivoting
                 load_pomo_for_day_bars() output.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    df_plot.plot(
        ax=ax,
        kind="bar",
        stacked=True,
        colormap="tab20",
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
    plt.show()
