
import pandas as pd
import matplotlib.pyplot as plt

def report():

    # 1) Lire le fichier ods (toutes les feuilles)
    xls = pd.read_excel("./suivi_chantiers.ods", engine="odf", sheet_name=None)

    # 2) Concaténer toutes les feuilles sauf la première
    sheets = list(xls.keys())[1:]  # toutes sauf la première
    df = pd.concat([xls[s] for s in sheets], ignore_index=True)

    # 3) Nettoyer les colonnes si besoin
    df.columns = df.columns.str.strip()
    df['DATE'] = pd.to_datetime(df['DATE'])

    # 4) Rapport total jours par Projet/Sous-projet
    rapport = df.groupby(['PROJET', 'SS-PROJET'])['JOURS'].sum().reset_index()
    rapport = rapport.sort_values(['PROJET', 'SS-PROJET'])

    return rapport, df



import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

def plot(df):
    projets = df['PROJET'].unique()
    n_projets = len(projets)

    colors = plt.cm.tab20.colors
    color_map = {p: colors[i % len(colors)] for i, p in enumerate(projets)}

    fig, axes = plt.subplots(
        n_projets, 1,
        figsize=(16, 5 * n_projets),
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

        ax.tick_params(axis='x', rotation=0, pad=12)
        ax.set_xlabel("DATE", labelpad=15)

    # --- C'est ici que l'on ajoute de l'espace entre les plots ---
    plt.subplots_adjust(hspace=1.5)   # augmente l’espace entre les subplots

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":

    actions = ['report', 'plot']

    import sys
    def givarg(actions):
        print(f"Giv arg in [{', '.join(actions)}]")
        sys.exit()

    if len(sys.argv) < 2 or sys.argv[1] not in actions:
        givarg(actions)

    repont, suivi_df = report()
    if ( sys.argv[1] == 'report'):
        print(repont)
    elif ( sys.argv[1] == 'plot'):
        plot(suivi_df)
