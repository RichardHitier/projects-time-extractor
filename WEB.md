# Web dashboard

Flask app that consolidates time-tracking data from three sources and displays
interactive charts per project.

## Launch

```bash
FLASK_DEBUG=true FLASK_APP=analysis_web flask run --host=0.0.0.0
```

## Routes

| Route | Description |
|-------|-------------|
| `/projects` | Overview — one subplot per project, all sources overlaid |
| `/commits/<project>` | Detail — 4-panel chart + data table for one project |

Both routes accept optional `not_before` / `not_after` query parameters (ISO dates)
to restrict the date range. Default window: last 120 days + 10 days forward.

## Data pipeline

Three sources are parsed, merged per project, and cached in a Parquet file.

```
Pomofocus CSV          → pomofocus_to_df()   → pomo_minutes / day
Super Productivity JSON → superprod_to_df()  → super_hours / day
Web Productivity JSON  → webprod_to_df()     → web_hours / day
Git .git dirs          → repo_to_df()        → git_commits, git_hours / day
                                    ↓
                         merge_all_histories()
                                    ↓
                         DATA/histories.parquet  (cache)
```

**Cache:** `DATA/histories.parquet` is created on first request and reused on
subsequent ones. Delete it manually to force a re-parse when source data changes.

## Charts

### `/projects` — multi-project overview (`all_plot`)

One subplot per project, sharing the time axis. Each subplot shows:
- **Left axis (minutes):** Pomofocus bars (blue), Super Productivity bars (yellow), Web bars (pink)
- **Right axis (commits):** Git commit spline + scatter (red)

### `/commits/<project>` — single-project detail (`plot_df`)

Four stacked subplots:
1. **Git commits/day** — spline + scatter
2. **Git hours/day** — bar chart
3. **Pomofocus minutes/day** — bar chart
4. **Super Productivity + Web hours/day** — stacked bars

## File structure

```
analysis_web.py              Entry point
web/
  __init__.py                App factory (create_app)
  main/
    routes.py                Routes: /, /projects, /commits/<project>
    templates/
      projects.html          Overview page
      commits.html           Detail page
  templates/
    base_page.html           Base HTML layout
  tools/
    histories.py             Data parsers and merge logic
    data_cache.py            Parquet cache (get_cached_histories)
    plots.py                 Matplotlib figures (all_plot, plot_df)
  static/css/main.css        Stylesheet
```

## Adding a new project

1. Add an entry to `projects-config.yml` with `git_dirs`, `pom_project`,
   and `superprod_projects`.
2. Delete `DATA/histories.parquet` to invalidate the cache.
3. Reload the app.
