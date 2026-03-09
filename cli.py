import argparse
from glob import glob
from os import path
from pathlib import Path

import pandas as pd
from config import load_config

_config = load_config()

POMO_FILE = _config["POMOFOCUS_FILEPATH"]
DATA_DIR = Path(__file__).parent 
POMO_OUT = DATA_DIR / POMO_FILE
CSV_SEP = ","

def _read_pomo(pomo_file: str) -> pd.DataFrame:
    df = pd.read_csv(pomo_file, sep=CSV_SEP, encoding="utf-8-sig", dtype=str)
    df.columns = df.columns.str.strip()
    df["project"] = df["project"].str.strip().str.strip('"')
    df["task"]    = df["task"].str.strip().str.strip('"')
    return df

def cmd_pomo_merge(args):
    DEDUP_KEYS = ["date", "startTime", "endTime", "project", "task"]
    data_directory  = _config["PPT_DATA_DIR"]
    pomfiles = glob(f"{data_directory}/pomofocus*.csv")
    frames = []
    for f in pomfiles:
        df = _read_pomo(f)
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    len_before = len(merged)
    merged = merged.drop_duplicates(subset=DEDUP_KEYS)
    merged = merged.sort_values(["date", "startTime"])
    len_after = len(merged)
    merged.to_csv(POMO_OUT, sep=CSV_SEP, index=False)
    print(f"Files processed: {pomfiles}")
    print(f"Records before deduplication: {len_before}")
    print(f"Records after deduplication: {len_after}")

def _load_pomo_for_report(days, project):
    if not POMO_OUT.exists():
        print(f"Pomofocus export not found: {POMO_OUT}."
               " Run 'timer pomo-merge' first.")
        return
    df = _read_pomo(POMO_OUT)
    df['minutes'] = pd.to_numeric(df['minutes'], errors='coerce').fillna(0).astype(int)
    df['date'] = pd.to_datetime(df['date'], format='%Y%m%d', errors='coerce')

    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=days - 1)
    df = df[df["date"] >= cutoff]

    if project:
        df = df[df["project"] == project]

    return df


def _view_project(df):
    for project, grp in df.groupby("project"):
        print(f"\nProject: {project}")
        daily = grp.groupby("date")["minutes"].sum()
        for date, minutes in daily.items():
            print(
                f"  - {date.strftime('%Y-%m-%d')} :  duration = {minutes / 60:5.2f} h"
            )


def _view_table(df):
    daily = df.groupby(["date", "project", "task"])["minutes"].sum().reset_index()
    daily = daily.sort_values("date")
    print(type(daily))
    print(daily.head())
    daily["duration_h"] = daily["minutes"] / 60
    print(f"\n{'date':<12} {'project':<20} {'task':<25} {'duration_h':>10}")
    print("-" * 69)
    for _, row in daily.iterrows():
        print(
            f"{row['date'].strftime('%Y-%m-%d'):<12} {row['project']:<20} {row['task'][:20]:<20} {row['duration_h']:>10.2f}"
        )
def cmd_report(args):
    df = _load_pomo_for_report(args.days, args.project)
    if df is not None:
        if args.view == "table":
            _view_table(df)
        elif args.view == "project":
            _view_project(df)
        else:
            print(f"Unknown view: {args.view}")

def cmd_swimlane(args):
    raise NotImplementedError

def cmd_plot(args):
    raise NotImplementedError


def build_parser():
    parser = argparse.ArgumentParser(
        prog="timer",
        description="projects_timer — Time tracking & visualization for dev projects",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_merge = sub.add_parser("pomo-merge", help="Merge pomofocus exports → pomofocus.csv")
    p_merge.set_defaults(func=cmd_pomo_merge)

    p_report = sub.add_parser("report", help="Text report time/project/day")
    p_report.add_argument("--days", type=int, default=7, metavar="N",help="Number of days to report (default: 7)")
    p_report.add_argument("--view", default="table", choices=["table", "project"], help="Report format")
    p_report.add_argument("--project", default=None, metavar="NAME")
    p_report.set_defaults(func=cmd_report)

    p_swim = sub.add_parser("swimlane", help="Generate swimlane PNG")
    p_swim.add_argument("--output", default="swimlane.png")
    p_swim.add_argument("--from",   dest="date_from", metavar="YYYYMMDD")
    p_swim.add_argument("--to",     dest="date_to",   metavar="YYYYMMDD")
    p_swim.set_defaults(func=cmd_swimlane)

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
