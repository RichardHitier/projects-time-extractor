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

### Pomofocus workflow

1. Export the report from [pomofocus.io](https://pomofocus.io) → save `report.csv` into the `DATA/` folder
2. Merge into the main history:

```bash
timer pomo-merge
```

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

### Web dashboard

```bash
python analysis_web.py    # Flask dev server at http://localhost:5000
```

Routes:
- `/projects` — overview across all projects
- `/commits/<project>` — detail view for a single project

## Tests

```bash
pytest tests/
pytest tests/test_tools.py::test_project_to_df -v    # single test
```

Tests rely on local data files and git repositories configured in `projects-config.yml`.
