# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

A time tracking analytics system that consolidates data from three sources —
**Pomofocus** (CSV), **Super Productivity** (JSON), and **Git commit history** —
into unified reports and visualizations. Provides both a CLI and a Flask web dashboard.

## Commands

### Setup
```bash
pip install -r requirements.txt
pip install -r requirements-tests.txt
```

### CLI
```bash
python cli.py pomo-merge                                    # merge Pomofocus CSV exports
python cli.py report --days 7 --view table                 # text report (views: table, project, export, project-logs)
python cli.py report --days 30 --project colibri --view project
python cli.py day-bars --from 20250101 --to 20250131 -p colibri --view plot
```

### Web app
```bash
python analysis_web.py   # Flask dev server at http://localhost:5000
```

### Tests
```bash
pytest tests/
pytest tests/test_tools.py::test_project_to_df -v   # single test
```

Most tests depend on actual data files and git repos on disk — they are not
fully self-contained and will fail without the local environment configured.

## Architecture

There are **two parallel data pipelines** sharing configuration but otherwise
separate: one for the CLI, one for the web app.

### CLI pipeline (`core/`)

```
Pomofocus CSV → core/data.py:read_pomo() / load_all_pomo()
                        ↓
             core/services.py:load_pomo_for_report() / load_pomo_for_day_bars()
                        ↓
             core/plots.py  →  stdout table / matplotlib PNG
```

### Web pipeline (`web/tools/`)

```
Pomofocus CSV      → web/tools/histories.py:pomofocus_to_df()
Super Productivity → web/tools/histories.py:superprod_to_df()
Git .git dirs      → web/tools/histories.py:repo_to_df()
                        ↓
             merge_all_histories() → DataFrame [git_commits, git_hours, pomo_minutes, super_hours, web_hours]
                        ↓
             web/tools/data_cache.py → DATA/histories.parquet (cache)
                        ↓
             web/tools/plots.py → matplotlib PNG → Flask templates
```

### Key modules

| File | Role |
|------|------|
| `config.py` | Loads `config.yml` and `projects-config.yml`, resolves absolute paths |
| `core/data.py` | Reads and cleans Pomofocus CSV; computes duration columns |
| `core/services.py` | CLI business logic: filtering, date windowing, CSV merge, task parsing |
| `core/plots.py` | CLI output: stdout table/export formatters and `plot_day_bars()` |
| `web/tools/histories.py` | Web data engine — parsers for all three sources, aggregation, merging |
| `web/tools/data_cache.py` | Parquet-based cache for merged histories |
| `web/tools/plots.py` | Matplotlib plots (single-project 4-panel, all-projects overview) |
| `web/main/routes.py` | Flask routes (`/projects`, `/commits/<project>`) |
| `cli.py` | CLI entry point using `argparse` |

### Configuration

`config.yml` — data directory paths, filenames, export project list (`EXPORT_PROJECTS`).

`projects-config.yml` — per-project metadata:
```yaml
speasy:
  git_dirs: [...]              # list of .git directories to analyze
  pom_project: speasy          # project name in Pomofocus CSV
  superprod_projects: [...]    # project names in Super Productivity JSON
```

### Task description format

CLI parses task descriptions in the form:
```
#<issue_id> <issue_name>: <description>
```

### Caching

The parquet cache (`DATA/histories.parquet`) must be deleted manually to force
a re-parse when source data changes. `get_cached_histories()` checks for its
existence before parsing.
