import os
import re
import shutil

import pandas as pd
from config import load_config
from core.data import read_pomo, load_all_pomo

_config = load_config()


def load_pomo_for_report(cutoff, project, all_projects=False):
    """Load and filter Pomofocus data for text reporting.

    Restricts to the configured EXPORT_PROJECTS (unless all_projects is True),
    keeps only records from `cutoff` onwards, optionally filters by project
    name, then aggregates (sum) by date / project / sub_project / task.

    Args:
        cutoff: pd.Timestamp — first date to include.
        project: If set, restrict output to this project name.
        all_projects: If True, bypass EXPORT_PROJECTS filter.

    Returns:
        Aggregated DataFrame sorted by date and project.
    """
    df = load_all_pomo()
    if not all_projects:
        df = df[df["project"].isin(_config["EXPORT_PROJECTS"])]
    df = df.sort_values("date")
    df = df[df["date"] >= cutoff]
    df = df.sort_values(["date", "project"])
    if project:
        df = df[df["project"] == project]
    df = (df.groupby(["date", "project", "sub_project", "task"], as_index=False)
          .sum(numeric_only=True))
    return df


def load_pomo_for_day_bars(date_from, date_to, project):
    """Load and filter Pomofocus data for the day-bars chart.

    Args:
        date_from: Start date as 'YYYYMMDD' string, or None for no lower bound.
        date_to: End date as 'YYYYMMDD' string, or None for no upper bound.
        project: If set, restrict to this project name.

    Returns:
        DataFrame with columns: date, project, hours — one row per
        (date, project) combination.
    """
    df = load_all_pomo()
    if project:
        df = df[df["project"] == project]
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    if date_from:
        date_from = pd.to_datetime(date_from, format="%Y%m%d", errors="coerce")
        df = df[df["date"] >= date_from]
    if date_to:
        date_to = pd.to_datetime(date_to, format="%Y%m%d", errors="coerce")
        df = df[df["date"] <= date_to]
    df["duration_m"] = pd.to_numeric(df["duration_m"])
    daily = df.groupby(["date", "project"], as_index=False).agg(
        hours=("duration_h", "sum"))
    return daily


def load_pomo_for_eighty_bars(date_from, date_to):
    """Load billable hours per day for the eighty-bars chart.

    Filters to BILLABLE_PROJECTS from config, sums hours per day.

    Returns:
        DataFrame with columns: date, hours.
    """
    billable = _config.get("BILLABLE_PROJECTS", [])
    df = load_all_pomo()
    df = df[df["project"].isin(billable)]
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    if date_from:
        df = df[df["date"] >= pd.to_datetime(date_from, format="%Y%m%d")]
    if date_to:
        df = df[df["date"] <= pd.to_datetime(date_to, format="%Y%m%d")]
    daily = df.groupby("date", as_index=False).agg(hours=("duration_h", "sum"))
    return daily


def load_pomo_for_swimlane(date_from, date_to, project):
    """Load Pomofocus data for the swimlane chart.

    Returns:
        DataFrame with columns: date_only, start, end, project,
        sub_project, task, duration_m — one row per session.
    """
    df = load_all_pomo()
    df["date"] = pd.to_datetime(df["date"])
    if date_from:
        df = df[df["date"] >= pd.to_datetime(date_from, format="%Y%m%d", errors="coerce")]
    if date_to:
        df = df[df["date"] <= pd.to_datetime(date_to, format="%Y%m%d", errors="coerce")]
    if project:
        df = df[df["project"] == project]
    df = df[df["duration_m"] > 0].copy()
    df["start"] = df.apply(
        lambda r: pd.Timestamp.combine(r["date"].date(), r["startTime"]), axis=1
    )
    df["end"] = df.apply(
        lambda r: pd.Timestamp.combine(r["date"].date(), r["endTime"]), axis=1
    )
    mask = df["end"] <= df["start"]
    df.loc[mask, "end"] = df.loc[mask, "start"] + pd.to_timedelta(
        df.loc[mask, "duration_m"], unit="m"
    )
    df["date_only"] = df["date"].dt.date
    return df


def parse_task(task_str):
    """Parse a task string in the format '#ISSUE_ID name : description'.

    Args:
        task_str: Raw task string from Pomofocus.

    Returns:
        Tuple (issue_id, issue_name, task_description).  issue_id is an int
        when matched, None otherwise.  issue_name is None when the pattern
        does not match.
    """
    m = re.match(r"^#(\d+)\s+(.+?)\s*:\s*(.+)$", task_str.strip())
    if m:
        issue_id = int(m.group(1))
        issue_name = m.group(2).strip()
        task_description = m.group(3).strip()
    else:
        issue_id = None
        issue_name = None
        task_description = task_str.strip()
    return issue_id, issue_name, task_description


def merge_pomo_exports(pomo_file, home_dir, data_dir, bckp_dir):
    """Merge a newly downloaded Pomofocus report into the main CSV.

    Moves 'report.csv' from home_dir to data_dir if present, then merges
    it with pomo_file, deduplicates on (date, startTime, endTime, project,
    task), backs up the original pomo_file, and writes the merged result
    back to pomo_file.

    Args:
        pomo_file: Path to the main Pomofocus CSV (destination of merge).
        home_dir: Directory where the browser download lands ('report.csv').
        data_dir: Data directory where 'report.csv' is staged before merge.
        bckp_dir: Directory for timestamped backups of pomo_file.

    Returns:
        Tuple (pomfiles, len_before, len_after) where pomfiles is the list
        of source files merged, and the two ints are row counts before/after
        deduplication.
    """
    DEDUP_KEYS = ["date", "startTime", "endTime", "project", "task"]
    report_file_name = "report.csv"
    downloaded_report_path = os.path.join(home_dir, report_file_name)
    data_report_path = os.path.join(data_dir, report_file_name)

    pomfiles = [pomo_file]
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

    frames = [read_pomo(f) for f in pomfiles]
    merged = pd.concat(frames, ignore_index=True)
    len_before = len(merged)
    merged = merged.drop_duplicates(subset=DEDUP_KEYS)
    # A session exported mid-run and again after completion has the same startTime
    # but different endTime/minutes; keep the most complete record (latest endTime).
    merged = merged.sort_values(
        ["date", "startTime", "endTime"], ascending=[True, True, False]
    )
    merged = merged.drop_duplicates(
        subset=["date", "startTime", "project", "task"], keep="first"
    )
    merged = merged.sort_values(["date", "startTime"])
    len_after = len(merged)

    backup_path = os.path.join(
        bckp_dir,
        f"pomofocus_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    shutil.move(pomo_file, backup_path)
    merged.to_csv(pomo_file, sep=",", index=False)

    return pomfiles, len_before, len_after
