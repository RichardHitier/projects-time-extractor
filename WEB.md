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

## Webhook live view (`/live`) — local Docker dev

This is a **separate app** from the dashboard above: `webhook_receiver.py`
(the Pomofocus webhook receiver) also serves a live current-week page at
`/live`, reading `webhook-data/pomofocus_webhook.csv`. It ships as a Docker
image (`Dockerfile` + `docker-compose.yml`).

The committed `docker-compose.yml` is the **prod** config: it only `expose`s
port 5000 internally, behind nginx on `:80`, with a secret path
(`WEBHOOK_SECRET`). For local dev we add a git-ignored
`docker-compose.override.yml` (auto-merged by Compose) that publishes the port
directly, mounts the code as volumes (no rebuild on edit), and runs gunicorn
with `--reload`.

### Launch

```bash
docker compose up -d webhook        # base + override merged automatically
```

Then open **http://localhost:5000/live** (no secret needed in dev —
`WEBHOOK_SECRET` is empty, so `/live` answers at the root).

Editing `webhook_receiver.py` on the host triggers gunicorn `--reload`; no
rebuild needed. Only a change to `requirements-webhook.txt` requires
`docker compose build webhook`.

```bash
docker compose logs -f webhook      # follow logs / reloads
docker compose restart webhook      # force a restart
docker compose down                 # stop everything
```

### Data

`/live` reads `webhook-data/pomofocus_webhook.csv` (mounted at `/app/DATA` by
the base compose, exactly like prod). The file is re-read on every request, so
refreshing data needs no restart — just copy a recent version from the VPS:

```bash
scp ovh-vps:timer/webhook-data/pomofocus_webhook.csv webhook-data/pomofocus_webhook.csv
```

> `docker-compose.override.yml` is dev-only and git-ignored — do not deploy it.
