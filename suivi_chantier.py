
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



def plot(df):
    # 5) Graphiques : histogramme par projet
    projets = df['PROJET'].unique()
    n_projets = len(projets)

    # une couleur par projet
    colors = plt.cm.tab20.colors  # palette
    color_map = {p: colors[i % len(colors)] for i, p in enumerate(projets)}

    fig, axes = plt.subplots(n_projets, 1, figsize=(14, 4*n_projets), sharex=True, sharey=True)

    if n_projets == 1:
        axes = [axes]

    for ax, projet in zip(axes, projets):
        d = df[df['PROJET'] == projet]
        d = d.groupby('DATE')['JOURS'].sum().reset_index()

        ax.bar(d['DATE'], d['JOURS'], color=color_map[projet])
        ax.set_title(f"Projet : {projet}")
        ax.set_ylabel("JOURS")
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("DATE")

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
