import argparse
from glob import glob

import pandas as pd
from config import load_config



def cmd_pomo_merge(args):
    DEDUP_KEYS = ["date", "startTime", "endTime", "project", "task"]
    CSV_SEP = ","
    _config = load_config()
    # pomofocus_filepath = _config["POMOFOCUS_FILEPATH"]
    pomofocus_filepath = "try-pomofocus.csv"
    data_directory  = _config["PPT_DATA_DIR"]
    pomfiles = glob(f"{data_directory}/pomofocus*.csv")
    frames = []
    for f in pomfiles:
        df = pd.read_csv(f, sep=CSV_SEP)
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    len_before = len(merged)
    merged = merged.drop_duplicates(subset=DEDUP_KEYS)
    merged = merged.sort_values(["date", "startTime"])
    len_after = len(merged)
    merged.to_csv(pomofocus_filepath, sep=CSV_SEP, index=False)
    print(f"Files processed: {pomfiles}")
    print(f"Records before deduplication: {len_before}")
    print(f"Records after deduplication: {len_after}")

def cmd_report(args):
    raise NotImplementedError

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

    p_report = sub.add_parser("report", help="Text report of time/project/day")
    p_report.add_argument("--week",  action="store_true", help="Current week")
    p_report.add_argument("--month", action="store_true", help="Current month")
    p_report.add_argument("--from",  dest="date_from", metavar="YYYYMMDD")
    p_report.add_argument("--to",    dest="date_to",   metavar="YYYYMMDD")
    p_report.add_argument("--project", metavar="NOM",  help="Filter by project")
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
