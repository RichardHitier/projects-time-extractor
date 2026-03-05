import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

CSV_PATH = "DATA/pomofocus_report.csv"
SEP = "\t"

# Lecture
df = pd.read_csv(CSV_PATH, sep=SEP)

# Conversion explicite date + heure
df["start_dt"] = pd.to_datetime(
    df["date"].astype(str) + " " + df["startTime"],
    format="%Y%m%d %H:%M"
)

df["end_dt"] = pd.to_datetime(
    df["date"].astype(str) + " " + df["endTime"],
    format="%Y%m%d %H:%M"
)

# Tri chronologique
df = df.sort_values("start_dt")

TASK_COLUMN = "project"
# Une ligne par tâche
tasks = df[TASK_COLUMN].unique()
task_to_y = {task: i for i, task in enumerate(tasks)}

plt.figure(figsize=(10, 6))

colors = plt.cm.tab20.colors
color_map = {t: colors[i % len(colors)] for i, t in enumerate(tasks)}

for _, row in df.iterrows():
    y = task_to_y[row[TASK_COLUMN]]
    duration = (row["end_dt"] - row["start_dt"]).total_seconds() / 3600
    print(row["start_dt"], row["end_dt"], row[TASK_COLUMN], duration)

    plt.barh(
        y=y,
        width=duration/24,
        left=row["start_dt"],
        height=0.6,
        # color=color_map[row[TASK_COLUMN]]
    )

ax = plt.gca()

# 1 tick par jour
ax.xaxis.set_major_locator(mdates.DayLocator())

# format dd/mm
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))

# rotation des labels
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

plt.yticks(range(len(tasks)), tasks)
plt.xlabel("Heure de la journée")
plt.ylabel("Tâches")
plt.title("Timeline journalière du travail")

plt.tight_layout()
plt.show()
