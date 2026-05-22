import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def report():

    # 1) Lire le fichier ods (toutes les feuilles)
    xls = pd.read_excel("./suivi_chantiers.ods", engine="odf", sheet_name=None)

    # 2) Concaténer toutes les feuilles sauf la première
    sheets = list(xls.keys())[1:]  # toutes sauf la première
    df = pd.concat([xls[s].dropna() for s in sheets],
                    ignore_index=True)

    # 3) Nettoyer les colonnes si besoin
    df.columns = df.columns.str.strip()
    df['DATE'] = pd.to_datetime(df['DATE'])

    # 4) Rapport total jours par Projet/Sous-projet
    rapport = df.groupby(['PROJET', 'SS-PROJET'])['JOURS'].sum().reset_index()
    rapport = rapport.sort_values(['PROJET', 'SS-PROJET'])

    return rapport, df


def plot_all_projects(df):
    d = df.groupby('DATE')['JOURS'].sum().reset_index()
    d['DATE'] = pd.to_datetime(d['DATE'])

    plt.figure(figsize=(16, 6))
    plt.bar(d['DATE'], d['JOURS'], color='steelblue')
    plt.xlabel("DATE", labelpad=15)
    plt.ylabel("JOURS")
    plt.title("Total JOURS par DATE")
    plt.grid(True, alpha=0.3)

    # ticks réguliers
    plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y%m%d'))

    plt.xticks(rotation=45)
    # plt.tight_layout()
    # ax.tick_params(axis='x', rotation=45, pad=12)
    # ax.set_xlabel("DATE", labelpad=15)
    plt.show()


def plot_by_projects(df, output="suivi_chantiers.png", show=False):
    projets = df['PROJET'].unique()
    n_projets = len(projets)

    colors = plt.cm.tab20.colors
    color_map = {p: colors[i % len(colors)] for i, p in enumerate(projets)}

    fig, axes = plt.subplots(
        n_projets, 1,
        figsize=(16, 5 * n_projets),
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

        # --- Titre dans le plot ---
        ax.text(
            0.01, 0.95,
            f"Projet : {projet}",
            transform=ax.transAxes,
            fontsize=10,
            fontweight='normal',
            va='top',
            ha='left'
        )

        # ticks réguliers
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y%m%d'))

        ax.tick_params(axis='x', rotation=45, pad=12)
        ax.set_xlabel("DATE", labelpad=15)

    # --- C'est ici que l'on ajoute de l'espace entre les plots ---
    plt.subplots_adjust(hspace=1.5)

    plt.tight_layout()
    if show:
        plt.show()
    else:
        plt.savefig(output, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"File {output} created")


if __name__ == "__main__":

    actions = ['txt_report', 'plot_by_project', 'plot_all_projects']

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
        plot_all_projects(suivi_df)
