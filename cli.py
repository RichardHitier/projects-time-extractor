import argparse
import os
import shutil

from matplotlib import pyplot as plt
import pandas as pd
from config import load_config
import locale
locale.setlocale(locale.LC_NUMERIC, "fr_FR.UTF-8")

_config = load_config()

POMO_FILE = _config["POMOFOCUS_FILEPATH"]
DATA_DIR  = _config["DATA_DIR"]
BCKP_DIR  = os.path.join(_config["DATA_DIR"], "bckp")
CSV_SEP = ","

def _read_pomo(pomo_file: str) -> pd.DataFrame:
    if not os.path.exists(POMO_FILE):
        print(f"Pomofocus export not found: {POMO_FILE}."
               " Run 'timer pomo-merge' first.")
        return
    df = pd.read_csv(pomo_file, sep=CSV_SEP, encoding="utf-8-sig", dtype=str)
    df.columns = df.columns.str.strip()
    df["project"] = ( df["project"]
        .str.strip().astype(str)
        .str.strip('"')
        .str.replace("/", "_", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        )

    df["task"] = ( df["task"]
        .str.strip().astype(str)
        .str.strip('"')
        .str.replace(r"\s+", " ", regex=True)
    )
    return df

def _load_pomo_for_all():
    df = _read_pomo(POMO_FILE)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df["startTime"] = pd.to_datetime(df["startTime"], format="%H:%M").dt.time
    df["endTime"] = pd.to_datetime(df["endTime"], format="%H:%M").dt.time
    df["minutes"] = ( pd.to_numeric(df["minutes"], errors="coerce")
                      .fillna(0).astype(int) )
    df["duration_m"] = df["minutes"]
    df["duration_h"] = df["minutes"] / 60
    df["duration_d"] = df["duration_h"] / 8
    df.drop(columns=["minutes"], inplace=True)
    df[["project", "sub_project"]] = ( df["project"]
        .str.split("_", n=1, expand=True).fillna("")
    )
    return df


def _load_pomo_for_report( days, project):
    df = _load_pomo_for_all()
    df = df[df["project"].isin(_config["EXPORT_PROJECTS"])]

    df = df.sort_values("date")
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=days - 1)
    df = df[df["date"] >= cutoff]

    df = df.sort_values(["date", "project"])

    if project:
        df = df[df["project"] == project]

    df = ( df.groupby(["date", "project", "sub_project", "task"],
                       as_index=False)
                .sum( numeric_only=True)
    )

    return df

def cmd_pomo_merge(args):
    print("Merging Pomofocus exports...")
    DEDUP_KEYS = ["date", "startTime", "endTime", "project", "task"]
    report_file_name =  "report.csv"
    downloaded_report_path = os.path.join(_config["HOME_DIR"], report_file_name)
    data_report_path = os.path.join(DATA_DIR, report_file_name)
    pomfiles = [POMO_FILE]
    if os.path.exists(downloaded_report_path):
        print(f" Moving {downloaded_report_path} to data directory...")
        shutil.move(downloaded_report_path, data_report_path)
    else:
        print(f"No downloaded report found at {downloaded_report_path}.")
    if os.path.exists(data_report_path):
        print(f"Include {data_report_path} in the merge.")
        pomfiles.append(data_report_path)
    else:
        print(f"No report found at {data_report_path}.")
    frames = []
    for f in pomfiles:
        df = _read_pomo(f)
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    len_before = len(merged)
    merged = merged.drop_duplicates(subset=DEDUP_KEYS)
    merged = merged.sort_values(["date", "startTime"])
    len_after = len(merged)
    backup_path = os.path.join(BCKP_DIR, f"pomofocus_{pd.Timestamp.
                                                      now().
                                                      strftime('%Y%m%d_%H%M%S')}.csv")
    shutil.move(POMO_FILE, backup_path)
    merged.to_csv(POMO_FILE, sep=CSV_SEP, index=False)
    print(f"Files processed: {pomfiles}")
    print(f"Records before deduplication: {len_before}")
    print(f"Records after deduplication: {len_after}")

def _view_project(df):
    for project, grp in df.groupby("project"):
        print(f"\nProject: {project}")
        daily = grp.groupby("date")["duration_m"].sum()
        for date, minutes in daily.items():
            print(
                f"  - {date.strftime('%Y-%m-%d')} :  duration = {minutes / 60:5.2f} h"
            )


def _view_table(df):

    header_line = (
        f"\n{'date':<12}; {'project':<20}; {'sub_project':<20}; {'task':<35}; "
        f"{'duration_m':>10}; {'duration_d':>10}; {'duration_h':>10}"
    )
    print(header_line)
    print("-" * len(header_line))
    for _, row in df.iterrows():
        duration_m = locale.format_string("%3.2f", row['duration_m'])
        duration_h = locale.format_string("%3.2f", row['duration_h'])
        duration_d = locale.format_string("%3.2f", row['duration_d'])
        date_str = row['date'].strftime('%Y-%m-%d')
        project_str = row['project']
        task_str = row['task'][:35]
        sub_project_str = row['sub_project'][:20]
        print(
            f"{date_str:<12}; {project_str:<20}; {sub_project_str:<20}; "
            f"{task_str:<35}; {duration_m:>10}; {duration_d:>10}; {duration_h:>10}"
        )

def _view_export(df):

    header_line = (
        f"\n{'date'};{'project'};{'sub_project'};{'task'};{'duration_d'}"
    )
    print(header_line)
    for _, row in df.iterrows():
        duration_d = locale.format_string("%3.2f", row['duration_d'])
        date_str = row['date'].strftime('%Y-%m-%d')
        project_str = row['project']
        task_str = row['task'][:35]
        sub_project_str = row['sub_project'][:20]
        print(
            f"{date_str};{project_str};{sub_project_str};"
            f"{task_str};{duration_d}"
        )

def cmd_report(args):
    df = _load_pomo_for_report(args.days, args.project)
    if df is not None:
        if args.view == "table":
            _view_table(df)
        elif args.view == "project":
            _view_project(df)
        elif args.view == "export":
            _view_export(df)
        else:
            print(f"Unknown view: {args.view}")

def _load_pomo_for_day_bars(date_from, date_to):
    df = _load_pomo_for_all()
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    if date_from:
        date_from = pd.to_datetime(date_from, format='%Y%m%d', errors='coerce')
        df = df[df["date"] >= date_from]

    if date_to:
        date_to = pd.to_datetime(date_to, format='%Y%m%d', errors='coerce')
        df = df[df["date"] <= date_to]

    df["duration_m"] = pd.to_numeric(df["duration_m"])
    daily = df.groupby(["date", "project"], as_index=False).agg(hours=("duration_h", "sum"))

    return daily


def cmd_day_bars(args):
    df = _load_pomo_for_day_bars(args.date_from, args.date_to)
    df_plot =  df.set_index("date")
    df_plot = df.pivot(index="date", columns="project", values="hours").fillna(0)
    date_range = pd.date_range(df_plot.index.min(), df_plot.index.max(), freq="D")
    df_plot = df_plot.reindex(date_range, fill_value=0)

    if args.view == "txt":
        print(df_plot)
        return

    fig, ax = plt.subplots(figsize=(10, 6))


    df_plot.plot(
        ax=ax,
        kind="bar",
        stacked=True,
        colormap="tab20",   # couleurs plus lisibles
        width=0.8
    )


    plt.ylabel("Hours", fontsize=12)
    plt.xlabel("Date", fontsize=12)
    plt.title("Time spent per project per day", fontsize=14)

    labels = [d.strftime("%d %b") for d in df_plot.index]
    ax.set_xticklabels(labels, rotation=45, ha="right")

    plt.grid(axis="y", linestyle="--", alpha=0.4)

    plt.legend(title="Project", bbox_to_anchor=(1.02, 1), loc="upper left")

    plt.show()


def cmd_plot(args):
    raise NotImplementedError


def build_parser():
    parser = argparse.ArgumentParser(
        prog="timer",
        description="projects_timer — Time tracking & visualization for dev projects",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_merge = sub.add_parser("pomo-merge",
                             help="Merge pomofocus exports → pomofocus.csv")
    p_merge.set_defaults(func=cmd_pomo_merge)

    p_report = sub.add_parser("report", help="Text report time/project/day")
    p_report.add_argument("--days", type=int, default=7, metavar="N",
                          help="Number of days to report (default: 7)")
    p_report.add_argument("--view", default="table",
                          choices=["table", "project", "export"],
                          help="Report format")
    p_report.add_argument("--project", default=None, metavar="NAME")
    p_report.set_defaults(func=cmd_report)

    p_day_bars = sub.add_parser("day-bars", help="Generate day bars PNG")
    p_day_bars.add_argument("--view", default="plot", choices=["txt", "plot"])
    p_day_bars.add_argument("--output", default="day_bars.png")
    p_day_bars.add_argument("--from",   dest="date_from", metavar="YYYYMMDD")
    p_day_bars.add_argument("--to",     dest="date_to",   metavar="YYYYMMDD")
    p_day_bars.set_defaults(func=cmd_day_bars)

    p_plot = sub.add_parser("plot", help="Annual view by project")
    p_plot.add_argument("--year",   type=int, help="Year (default: current)")
    p_plot.add_argument("--output", default="all_projects.png")
    p_plot.set_defaults(func=cmd_plot)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
