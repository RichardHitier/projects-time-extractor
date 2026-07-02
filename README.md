# time_tracking

Time tracking analytics that consolidates data from multiple sources into reports and visualizations.

**Data sources:**
- **Pomofocus** — CSV exports of pomodoro sessions
- **Super Productivity** — JSON exports
- **Git** — commit history across multiple repositories

Provides a CLI for text reports and a Flask web dashboard for visual exploration.

## Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the package and its dependencies
pip install -e .

# Install test dependencies (optional)
pip install -r requirements-tests.txt
```

## Configuration

Two YAML files control the behaviour:

**`config.yml`** — data directory paths, source filenames, list of projects to include in exports.

**`projects-config.yml`** — per-project metadata:
```yaml
myproject:
  git_dirs:
    - /path/to/repo/.git
  pom_project: myproject        # project name as it appears in Pomofocus CSV
  superprod_projects:
    - myproject                 # project name(s) in Super Productivity JSON
```

## Usage

### Quick help

`timer report` — rapport texte
- `--days N` — nombre de jours (défaut: 7)
- `--since YYYYMMDD` — date de début (remplace `--days`)
- `--project NAME` — filtrer par projet
- `--view` — format : `table` | `project` | `export` | `project-logs`

`timer day-bars` — barres journalières
- `--from YYYYMMDD` / `--to YYYYMMDD` — plage de dates
- `-p PROJECT` — filtrer par projet
- `-v` — format : `txt` | `plot`
- `-o OUTPUT` — fichier de sortie

`timer plot` — vue annuelle par projet
- `--year YEAR` — année (défaut: en cours)
- `--output OUTPUT` — fichier de sortie

`timer pomo-merge` — fusionne les exports Pomofocus CSV (pas d'options)

### Pipeline complet

1. Saisie des sessions sur [pomofocus.io](https://pomofocus.io)
2. Export → `report.csv` (téléchargé dans `~/Téléchargements/`)
3. `timer pomo-merge` → fusionne dans `DATA/pomofocus.csv` (les noms de projets restent tels quels, ex. `calipso`)
4. `timer report --view export` → CSV de facturation (filtre sur `EXPORT_PROJECTS` dans `config.yml`)
5. Édition manuelle dans `suivi_chantiers.ods` : copier-coller du CSV, renommer `calipso` en `calipso_a` / `calipso_b` / ... selon la commande en cours
6. `timer eighty-hours` → export facturation (filtre sur `BILLABLE_PROJECTS` dans `config.yml`)

### Capture webhook Pomofocus

But : observer le protocole HTTP réellement envoyé par Pomofocus avant d'écrire
le webhook d'ingestion définitif. Le receveur local journalise chaque requête
dans `DATA/webhook_log.jsonl` avec méthode, URL, query string, headers,
`Content-Type`, body brut, JSON parsé et données de formulaire si présentes.

```bash
python webhook_receiver.py
cloudflared tunnel --url http://localhost:5000
```

Cloudflare affiche une URL publique du type :

```text
https://xxxxx.trycloudflare.com
```

Configurer cette URL dans Pomofocus. Par défaut le receveur accepte `/`, donc
l'URL complète peut être `https://xxxxx.trycloudflare.com/`. Pour éviter une
route trop facile à deviner pendant les essais :

```bash
WEBHOOK_SECRET=pomofocus-essai python webhook_receiver.py
cloudflared tunnel --url http://localhost:5000
```

Dans ce cas, configurer Pomofocus avec :

```text
https://xxxxx.trycloudflare.com/pomofocus-essai
```

Pendant la capture, déclencher plusieurs événements Pomofocus : start, pause,
resume, finish, changement de tâche/projet, pomodoro et pauses. Les requêtes
sont affichées dans le terminal et appendées dans `DATA/webhook_log.jsonl`.

Une fois le protocole observé, convertir les événements exploitables en CSV
local :

```bash
python webhook_log_to_csv.py
```

Le script écrit `DATA/webhook.csv` au format `pomofocus.csv` : `date`,
`project`, `task`, `minutes`, `startTime`, `endTime`. Il ne conserve que les
segments de travail `round == "pomodoro"` et `type in {"finish", "pause"}`.

Avant d'ouvrir le tunnel, il peut aussi être utile de vérifier Pomofocus avec
les DevTools du navigateur : `F12` → `Network`, puis déclencher les mêmes
événements pour voir si l'application appelle déjà une API HTTP exploitable.

### Report views (`timer report`)

```bash
timer report --days 7 --view table
```
Raw table: `date | project | sub_project | task | minutes | hours | days`.
Useful for checking recent entries.

```bash
timer report --days 30 --project colibri --view project
```
Per-project view: daily durations aggregated, filterable by project.

```bash
timer report --days 30 --view export
```
CSV export (`;` separator): `date;project;sub_project;task;duration_d`.
Ready to paste into a spreadsheet or external report.

```bash
timer report --days 30 --view project-logs
```
Monthly issue log: parses the `#ID name : description` format and aggregates by month.
CSV output: `month;issue_id;issue_name;task_description;duration_d`.
**Primary view for project progress tracking.**

#### Task description format

Tasks entered in Pomofocus should follow this convention to enable issue-level grouping:

```
#<issue_id> <issue_name>: <description>
```

Example: `#42 auth-refactor: migrate sessions to JWT`

If the format is not matched, the full task string is kept as `task_description` with no issue grouping.

#### Producing a client report

```bash
timer report --project speasy --since 20250101 --view project-logs > speasy_logs.csv
```

Open `speasy_logs.csv` in LibreOffice Calc and save as `.ods` to produce the deliverable for the client.
The output uses `;` as separator and `,` as decimal — ready for French-locale spreadsheets.

### Web dashboard

```bash
FLASK_DEBUG=true FLASK_APP=analysis_web flask run --host=0.0.0.0
```

Routes:
- `/projects` — overview across all projects
- `/commits/<project>` — detail view for a single project

### Internal tracking (`suivi_chantiers.ods`)

`suivi_chantiers.ods` is a manually maintained LibreOffice Calc file with columns
`DATE`, `PROJET`, `SS-PROJET`, `JOURS`. Each sheet covers a period or worksite.

`suivi_chantier.py` reads it to produce summaries and charts:

```bash
python suivi_chantier.py txt_report        # total days per project/sub-project
python suivi_chantier.py plot_by_project   # one bar chart per project
python suivi_chantier.py plot_all_projects # aggregated daily bars
```

`timer report --view export` can be used as a source to fill this file manually.

## Tests

```bash
pytest tests/
pytest tests/test_tools.py::test_project_to_df -v    # single test
```

Tests rely on local data files and git repositories configured in `projects-config.yml`.
