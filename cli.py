import argparse
import os
import shutil
from datetime import datetime

import pandas as pd
from config import load_config

from core.suivi_chantier import report as suivi_report, billing_export_days, write_eighty_hours
from core.services import (
    load_pomo_for_report,
    load_pomo_for_day_bars,
    load_pomo_for_swimlane,
    merge_pomo_exports,
)
from core.plots import (
    report_view_table,
    report_view_project,
    report_view_export,
    report_view_projectlogs,
    report_view_ods,
    yyyymm_to_sheet_name,
    plot_day_bars,
    plot_swimlane,
)

_config = load_config()

POMO_FILE = _config["POMOFOCUS_FILEPATH"]
DATA_DIR = _config["DATA_DIR"]
BCKP_DIR = os.path.join(_config["DATA_DIR"], "bckp")
ODS_FILE = _config["ODS_FILEPATH"]


POMO_RECORDS_LOG = os.path.join(DATA_DIR, "pomo_records.csv")


def _read_last_record_count():
    if not os.path.exists(POMO_RECORDS_LOG):
        return None, None
    df = pd.read_csv(POMO_RECORDS_LOG, parse_dates=["date"])
    if df.empty:
        return None, None
    last = df.iloc[-1]
    return last["date"], int(last["num_records"])


def _append_record_count(num_records):
    today = datetime.now().strftime("%Y-%m-%d")
    row = f"{today},{num_records}\n"
    if not os.path.exists(POMO_RECORDS_LOG):
        with open(POMO_RECORDS_LOG, "w") as f:
            f.write("date,num_records\n")
    with open(POMO_RECORDS_LOG, "a") as f:
        f.write(row)


def cmd_pomo_merge(args):
    print("Merging Pomofocus exports...")
    last_date, last_count = _read_last_record_count()
    pomfiles, len_before, len_after = merge_pomo_exports(
        POMO_FILE, _config["HOME_DIR"], DATA_DIR, BCKP_DIR
    )
    print(f"Files processed: {pomfiles}")
    print(f"Records before deduplication: {len_before}")
    print(f"Records after deduplication: {len_after}")
    if last_count is not None:
        added = len_after - last_count
        print(f"Records added since {last_date.date()}: {added:+d}")
    _append_record_count(len_after)


def cmd_report(args):
    if args.view == "ods":
        if args.month:
            first_month = min(args.month)
            cutoff = pd.Timestamp(f"{first_month[:4]}-{first_month[4:]}-01")
        else:
            today = pd.Timestamp.today()
            cutoff = pd.Timestamp(today.year, today.month, 1)
    elif args.since:
        cutoff = pd.to_datetime(args.since, format="%Y%m%d")
    else:
        cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=args.days - 1)
    df = load_pomo_for_report(cutoff, args.project, all_projects=args.all_projects)
    if df is not None:
        if args.view == "table":
            report_view_table(df)
        elif args.view == "project":
            report_view_project(df)
        elif args.view == "export":
            report_view_export(df, quantize=args.quantize)
        elif args.view == "project-logs":
            report_view_projectlogs(df)
        elif args.view == "ods":
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bckp_path = os.path.join(BCKP_DIR, f"suivi_chantiers_{stamp}.ods")
            shutil.copy2(ODS_FILE, bckp_path)
            print(f"Backup: {bckp_path}")
            months = [yyyymm_to_sheet_name(m) for m in args.month] if args.month else None
            report_view_ods(df, ODS_FILE, only_months=months)
        else:
            print(f"Unknown view: {args.view}")


def cmd_day_bars(args):
    df = load_pomo_for_day_bars(args.date_from, args.date_to, args.project)
    print(df)

    # Weekly aggregation
    df_copy = df.copy()
    df_copy["date"] = pd.to_datetime(df["date"])
    df_copy["days"] = df_copy["hours"] / 8
    weekly = (
        df_copy.groupby(df["date"].dt.to_period("W"))["days"]
        .sum()
        .reset_index()
    )
    print(weekly)

    df_plot = df.pivot(index="date", columns="project", values="hours").fillna(
        0
    )
    date_range = pd.date_range(
        df_plot.index.min(), df_plot.index.max(), freq="D"
    )
    df_plot = df_plot.reindex(date_range, fill_value=0)

    if args.view == "txt":
        print(df_plot)
        return

    plot_day_bars(df_plot, output=args.output, show=args.show)


def cmd_swimlane(args):
    df = load_pomo_for_swimlane(args.date_from, args.date_to, args.project)
    plot_swimlane(df, output=args.output, show=args.show)


def cmd_eighty_hours(args):
    _, suivi_df = suivi_report(ODS_FILE)
    year, month = None, None
    if args.month:
        year, month = map(int, args.month.split("-"))
    result = billing_export_days(suivi_df, year=year, month=month)
    if args.write_ods:
        if year is None:
            from datetime import date as _date
            year, month = _date.today().year, _date.today().month
        write_eighty_hours(ODS_FILE, result, year, month)
        print(f"Written to {ODS_FILE} (eighty-hours, month {year}-{month:02d})")
    else:
        print(result.to_csv(index=False, sep=";", decimal=",", na_rep=""), end="")
        total = f"{result['H'].sum():.2f}".replace(".", ",")
        print(f";;TOTAL;{total};")


def cmd_plot(args):
    raise NotImplementedError


def build_parser():
    parser = argparse.ArgumentParser(
        prog="timer",
        description=(
            "projects_timer — Time tracking & visualization for dev projects"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_merge = sub.add_parser(
        "pomo-merge", help="Merge pomofocus exports → pomofocus.csv"
    )
    p_merge.set_defaults(func=cmd_pomo_merge)

    p_report = sub.add_parser("report", help="Text report time/project/day")
    p_report.add_argument(
        "--days",
        type=int,
        default=7,
        metavar="N",
        help="Number of days to report (default: 7)",
    )
    p_report.add_argument(
        "--view",
        default="table",
        choices=["table", "project", "export", "project-logs", "ods"],
        help="Report format",
    )
    p_report.add_argument(
        "--since",
        default=None,
        metavar="YYYYMMDD",
        help="Start date (overrides --days)",
    )
    p_report.add_argument("--project", default=None, metavar="NAME")
    p_report.add_argument(
        "--quantize",
        action="store_true",
        default=False,
        help="Round durations to nearest 1/32 day (15 min) in export view",
    )
    p_report.add_argument(
        "--all-projects",
        dest="all_projects",
        action="store_true",
        help="Include all projects, bypassing EXPORT_PROJECTS filter",
    )
    p_report.add_argument(
        "--month",
        action="append",
        metavar="YYYYMM",
        help="ODS month(s) to write (default: current month). Repeatable.",
    )
    p_report.set_defaults(func=cmd_report)

    p_day_bars = sub.add_parser("day-bars", help="Generate day bars PNG")
    p_day_bars.add_argument(
        "-v", "--view", default="plot", choices=["txt", "plot"]
    )
    p_day_bars.add_argument("-o", "--output", default="day_bars.png")
    p_day_bars.add_argument("--from", dest="date_from", metavar="YYYYMMDD")
    p_day_bars.add_argument("--to", dest="date_to", metavar="YYYYMMDD")
    p_day_bars.add_argument("-p", "--project", dest="project")
    p_day_bars.add_argument(
        "--show",
        action="store_true",
        help="Display chart on screen instead of saving to file",
    )
    p_day_bars.set_defaults(func=cmd_day_bars)

    p_swimlane = sub.add_parser("swimlane", help="Gantt-style activity chart per day")
    p_swimlane.add_argument("-o", "--output", default="swimlane.png")
    p_swimlane.add_argument("--from", dest="date_from", metavar="YYYYMMDD")
    p_swimlane.add_argument("--to", dest="date_to", metavar="YYYYMMDD")
    p_swimlane.add_argument("-p", "--project", dest="project")
    p_swimlane.add_argument(
        "--show",
        action="store_true",
        help="Display chart on screen instead of saving to file",
    )
    p_swimlane.set_defaults(func=cmd_swimlane)

    p_eighty = sub.add_parser("eighty-hours", help="Daily billable hours CSV for a month")
    p_eighty.add_argument(
        "--month", metavar="YYYY-MM", default=None,
        help="Month to report (default: current month)",
    )
    p_eighty.add_argument(
        "--write-ods", action="store_true",
        help="Write output into the eighty-hours sheet of the ODS file",
    )
    p_eighty.set_defaults(func=cmd_eighty_hours)

    p_plot = sub.add_parser("plot", help="Annual view by project")
    p_plot.add_argument("--year", type=int, help="Year (default: current)")
    p_plot.add_argument("--output", default="all_projects.png")
    p_plot.set_defaults(func=cmd_plot)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
