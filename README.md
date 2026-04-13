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

### CLI

```bash
timer pomo-merge                                      # merge Pomofocus CSV exports
timer report --days 7 --view table                    # text report for the last 7 days
timer report --days 30 --project colibri --view project
timer report --days 30 --view project-logs            # monthly issue log (CSV output)
timer day-bars --from 20250101 --to 20250131 --view plot
```

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
