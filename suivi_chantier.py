import matplotlib.pyplot as plt
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


def billing_export_days(df):
    """Daily billable hours as CSV: J, D, S, H.

    J = French day letter (L/M/M/J/V/S/D)
    D = day of month
    S = ISO week number
    H = billable hours that day

    All days in range are included, zero-filled.
    """
    DAY_LETTERS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']  # Mon=0 .. Sun=6

    billable = [p.lower() for p in load_config().get("BILLABLE_PROJECTS", [])]
    df = df[df['PROJET'].str.lower().isin(billable)].copy()
    df['DATE'] = pd.to_datetime(df['DATE'])
    df['hours'] = df['JOURS'] * 8

    daily = df.groupby('DATE')['hours'].sum()
    date_range = pd.date_range(daily.index.min(), daily.index.max(), freq='D')
    daily = daily.reindex(date_range, fill_value=0.0)

    result = pd.DataFrame({
        'J': [DAY_LETTERS[d] for d in daily.index.dayofweek],
        'D': daily.index.day,
        'S': daily.index.isocalendar().week.values,
        'H': daily.round(2),
    })
    return result


def report():

    xls = pd.read_excel("./suivi_chantiers.ods", engine="odf", sheet_name=None)

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


if __name__ == "__main__":

    actions = ['txt_report', 'plot_by_project', 'plot_all_projects', 'export']

    import sys
    def givarg(actions):
        print(f"Giv arg in [{', '.join(actions)}]")
        sys.exit()

    if len(sys.argv) < 2 or sys.argv[1] not in actions:
        givarg(actions)

    my_report, suivi_df = report()
    if sys.argv[1] == 'txt_report':
        print(my_report)
    elif sys.argv[1] == 'plot_by_project':
        args = sys.argv[2:]
        show = '--show' in args
        output = next((a for a in args if not a.startswith('--')), "suivi_chantiers.png")
        plot_by_projects(suivi_df, output=output, show=show)
    elif sys.argv[1] == 'plot_all_projects':
        args = sys.argv[2:]
        show = '--show' in args
        output = next((a for a in args if not a.startswith('--')), "suivi_chantiers_all.png")
        plot_all_projects(suivi_df, output=output, show=show)
    elif sys.argv[1] == 'export':
        args = sys.argv[2:]
        period = next((a for a in args if a in ('week', 'month', 'days')), 'month')
        if period == 'days':
            print(billing_export_days(suivi_df).to_csv(index=False, sep=';', decimal=','))
        else:
            print(billing_export(suivi_df, period=period).to_string(index=False))
