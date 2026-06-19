import calendar
import math
from datetime import date

import matplotlib.pyplot as plt
plt.style.use("ggplot")
import matplotlib.dates as mdates
import pandas as pd

from config import load_config



def billing_export(df, period='month'):
    """Total billable days per period (week or month).

    Filters on BILLABLE_PROJECTS from config.yml.
    Project names are matched case-insensitively.
    """
    billable = [p.lower() for p in load_config().get("BILLABLE_PROJECTS", [])]
    df = df[df['PROJET'].str.lower().isin(billable)].copy()
    df['DATE'] = pd.to_datetime(df['DATE'])

    freq = 'W' if period == 'week' else 'M'
    df['PERIODE'] = df['DATE'].dt.to_period(freq)

    result = df.groupby('PERIODE')['JOURS'].sum().reset_index()
    return result


def billing_export_days(df, year=None, month=None):
    """Daily billable hours as CSV: J, D, S, H.

    J = French day letter (L/M/M/J/V/S/D)
    D = day of month
    S = ISO week number
    H = billable hours that day

    All days of the month are included, zero-filled.
    Defaults to current month if year/month are not provided.
    """
    DAY_LETTERS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']  # Mon=0 .. Sun=6

    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    billable = [p.lower() for p in load_config().get("BILLABLE_PROJECTS", [])]
    df = df[df['PROJET'].str.lower().isin(billable)].copy()
    df['DATE'] = pd.to_datetime(df['DATE'])
    df['hours'] = df['JOURS'] * 8

    daily = df.groupby('DATE')['hours'].sum()
    date_range = pd.date_range(
        start=pd.Timestamp(year=year, month=month, day=1),
        end=pd.Timestamp(year=year, month=month, day=calendar.monthrange(year, month)[1]),
        freq='D'
    )
    daily = daily.reindex(date_range, fill_value=0.0)

    # weekly totals indexed by the Sunday ending each week
    weekly = daily.resample('W').sum().round(2)
    weekly_dict = weekly.to_dict()

    result = pd.DataFrame({
        'J': [DAY_LETTERS[d] for d in daily.index.dayofweek],
        'D': daily.index.day,
        'S': daily.index.isocalendar().week.values,
        'H': daily.round(2),
        'T': [weekly_dict.get(d) if d.dayofweek == 6 else None for d in daily.index],
    })
    return result


def report(ods_path="./suivi_chantiers.ods"):

    xls = pd.read_excel(ods_path, engine="odf", sheet_name=None)

    # skip the first sheet (summary/cover)
    sheets = list(xls.keys())[1:]
    df = pd.concat([xls[s].dropna() for s in sheets],
                    ignore_index=True)

    df.columns = df.columns.str.strip()
    df['DATE'] = pd.to_datetime(df['DATE'])

    rapport = df.groupby(['PROJET', 'SS-PROJET'])['JOURS'].sum().reset_index()
    rapport = rapport.sort_values(['PROJET', 'SS-PROJET'])

    return rapport, df


def plot_all_projects(df, output="suivi_chantiers_all.png", show=False):
    d = df.groupby('DATE')['JOURS'].sum().reset_index()
    d['DATE'] = pd.to_datetime(d['DATE'])

    plt.figure(figsize=(24, 6))
    plt.bar(d['DATE'], d['JOURS'], color='steelblue')
    plt.xlabel("DATE", labelpad=15)
    plt.ylabel("JOURS")
    plt.title("Total JOURS par DATE")
    plt.grid(True, alpha=0.3)

    plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y%m%d'))

    plt.xticks(rotation=45)
    if show:
        plt.show()
    else:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"File {output} created")


def _cell_text(cell):
    from odf.text import P
    ps = cell.getElementsByType(P)
    return ps[0].firstChild.data if ps and ps[0].firstChild else ''


def _set_cell_text(cell, text):
    from odf.text import P
    for p in list(cell.getElementsByType(P)):
        cell.removeChild(p)
    if text is not None and str(text).strip():
        cell.addElement(P(text=str(text)))


def _find_cell(row, target_col):
    """Return (cell, col_start, repeat) for the cell covering target_col."""
    from odf.table import TableCell
    col = 0
    for cell in row.getElementsByType(TableCell):
        repeat = int(cell.getAttribute('numbercolumnsrepeated') or 1)
        if col <= target_col < col + repeat:
            return cell, col, repeat
        col += repeat
    return None, -1, 0


def _write_cell(row, target_col, text):
    from odf.table import TableCell
    from odf.text import P

    cell, col_start, repeat = _find_cell(row, target_col)
    if cell is None:
        return

    if repeat == 1:
        _set_cell_text(cell, text)
        return

    # Split the repeated cell at target_col
    offset = target_col - col_start
    after = repeat - offset - 1

    parent = cell.parentNode
    siblings = list(parent.childNodes)
    idx = siblings.index(cell)
    parent.removeChild(cell)

    insert_pos = idx

    def insert(new_cell):
        nonlocal insert_pos
        current = list(parent.childNodes)
        if insert_pos < len(current):
            parent.insertBefore(new_cell, current[insert_pos])
        else:
            parent.addElement(new_cell)
        insert_pos += 1

    if offset > 0:
        before = TableCell(numbercolumnsrepeated=str(offset))
        insert(before)

    data_cell = TableCell()
    if text is not None and str(text).strip():
        data_cell.addElement(P(text=str(text)))
    insert(data_cell)

    if after > 0:
        after_cell = TableCell(numbercolumnsrepeated=str(after))
        insert(after_cell)


def write_eighty_hours(ods_path, data, year, month):
    """Write billing_export_days() output into the eighty-hours sheet."""
    from odf.opendocument import load
    from odf.table import Table, TableRow, TableCell
    from odf.text import P

    doc = load(ods_path)
    sheets = doc.spreadsheet.getElementsByType(Table)
    sheet = next((s for s in sheets if s.getAttribute('name') == 'eighty-hours'), None)
    if sheet is None:
        raise ValueError("Sheet 'eighty-hours' not found")

    rows = sheet.getElementsByType(TableRow)

    # Row 3 contains month numbers (5, 6, 7…) at the real block_start column
    row3 = rows[2]
    block_start = None
    col = 0
    for cell in row3.getElementsByType(TableCell):
        repeat = int(cell.getAttribute('numbercolumnsrepeated') or 1)
        if _cell_text(cell) == str(month):
            block_start = col
            break
        col += repeat

    if block_start is None:
        raise ValueError(f"Month {month} not found in eighty-hours sheet (row 3)")

    # Write data rows (sheet rows 5–35, index 4–34)
    for i, (_, row_data) in enumerate(data.iterrows()):
        if i >= 31:
            break
        row = rows[4 + i]
        _write_cell(row, block_start,     str(row_data['J']))
        _write_cell(row, block_start + 1, str(int(row_data['D'])))
        _write_cell(row, block_start + 2, str(int(row_data['S'])))
        h_val = row_data['H']
        h_str = f"{h_val:.2f}".replace('.', ',') if h_val else '0'
        _write_cell(row, block_start + 3, h_str)
        t_val = row_data['T']
        if t_val is not None and not (isinstance(t_val, float) and math.isnan(t_val)):
            _write_cell(row, block_start + 4, f"{t_val:.2f}".replace('.', ','))
        else:
            _write_cell(row, block_start + 4, '')

    doc.save(ods_path)


def plot_by_projects(df, output="suivi_chantiers.png", show=False):
    projets = df['PROJET'].unique()
    n_projets = len(projets)

    colors = plt.cm.tab20.colors
    color_map = {p: colors[i % len(colors)] for i, p in enumerate(projets)}

    fig, axes = plt.subplots(
        n_projets, 1,
        figsize=(24, 3 * n_projets),
        sharex=True,
        sharey=True
    )

    if n_projets == 1:
        axes = [axes]

    for ax, projet in zip(axes, projets):
        d = df[df['PROJET'] == projet].copy()
        d = d.groupby('DATE')['JOURS'].sum().reset_index()
        d['DATE'] = pd.to_datetime(d['DATE'])

        ax.bar(d['DATE'], d['JOURS'], color=color_map[projet])
        ax.set_ylabel("JOURS")
        ax.grid(True, alpha=0.3)

        ax.text(
            0.01, 0.95,
            f"Projet : {projet}",
            transform=ax.transAxes,
            fontsize=10,
            fontweight='normal',
            va='top',
            ha='left'
        )

        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y%m%d'))

        ax.tick_params(axis='x', rotation=45, pad=12)
        ax.set_xlabel("DATE", labelpad=15)

    # hspace avoids subplot label overlap
    plt.subplots_adjust(hspace=1.5)

    plt.tight_layout()
    if show:
        plt.show()
    else:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"File {output} created")
