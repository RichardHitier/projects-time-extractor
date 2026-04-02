import os

import pandas as pd

from config import load_config

_config = load_config()

POMO_FILE = _config["POMOFOCUS_FILEPATH"]
CSV_SEP = ","


def read_pomo(pomo_file: str) -> pd.DataFrame:
    """Read a raw Pomofocus CSV export and return a cleaned DataFrame.

    Strips whitespace from column names, normalises project names (strips
    quotes, replaces '/' with '_', collapses whitespace) and task strings.

    Args:
        pomo_file: Path to the Pomofocus CSV file to read.

    Returns:
        DataFrame with columns:
          date, startTime, endTime, project, task, minutes.
    """
    if not os.path.exists(POMO_FILE):
        raise FileNotFoundError(
            f"Pomofocus export not found: {POMO_FILE}."
            f" Run 'timer pomo-merge' first."
        )
    df = pd.read_csv(pomo_file, sep=CSV_SEP, encoding="utf-8-sig", dtype=str)
    df.columns = df.columns.str.strip()
    df["project"] = (
        df["project"]
        .str.strip()
        .astype(str)
        .str.strip('"')
        .str.replace("/", "_", regex=False)
        .str.replace(r"\s+", " ", regex=True)
    )

    df["task"] = (
        df["task"]
        .str.strip()
        .astype(str)
        .str.strip('"')
        .str.replace(r"\s+", " ", regex=True)
    )
    return df


def load_all_pomo():
    """
    Load and transform the full Pomofocus dataset from the configured CSV file.

    Parses dates and times, computes duration columns (minutes, hours, days at
    8 h/day), and splits the project field on the first '_' into project and
    sub_project.

    Returns:
        DataFrame with columns: date, startTime, endTime, project, sub_project,
        task, duration_m, duration_h, duration_d.
    """  # noqa: E501
    df = read_pomo(POMO_FILE)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df["startTime"] = pd.to_datetime(df["startTime"], format="%H:%M").dt.time
    df["endTime"] = pd.to_datetime(df["endTime"], format="%H:%M").dt.time
    df["minutes"] = (
        pd.to_numeric(df["minutes"], errors="coerce").fillna(0).astype(int)
    )
    df["duration_m"] = df["minutes"]
    df["duration_h"] = df["minutes"] / 60
    df["duration_d"] = df["duration_h"] / 8
    df.drop(columns=["minutes"], inplace=True)
    df[["project", "sub_project"]] = (
        df["project"].str.split("_", n=1, expand=True).fillna("")
    )
    return df
