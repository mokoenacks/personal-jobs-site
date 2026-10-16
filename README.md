# C.k.s Mokoena — personal jobs site

A PythonAnywhere-ready personal site: public brand landing, work experience, and GitHub projects, plus an admin area to manage content.

**Stack:** Flask · SQLite · Flask-Login · plain templates/CSS (no Node build step)

**UI:** Simple black + purple theme, Arial system font, minimal CSS/JS (no webfonts or heavy animation) for fast PythonAnywhere loads.

## Features

- **Public site** — brand-first landing, experience timeline, GitHub projects
- **Admin CMS** — sign in, edit profile and roles in your own words
- **Experience and skills** — add roles and skills in admin. The LinkedIn address on the profile is only a public link.
- **GitHub projects** — fetch public repos for a configurable username, cache display fields, mock fallback without a token
- **Empty / loading / error states** for experience and projects

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional
python run.py
```

Open [http://127.0.0.1:3847](http://127.0.0.1:3847) (port from `PORT`, default **3847**).

### Default admin login

| Field    | Default (change in `.env`) |
|----------|----------------------------|
| Username | `admin`                    |
| Password | `changeme`                 |

Seeded on first run if no users exist. Change `ADMIN_USERNAME` / `ADMIN_PASSWORD` before deploying.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session secret |
| `DATABASE_URL` | Defaults to SQLite under `instance/site.db` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Seeded admin credentials |
| `SITE_OWNER_NAME` | Display name (default: C.k.s Mokoena) |
| `GITHUB_USERNAME` | Public repos to sync |
| `GITHUB_TOKEN` | Optional; higher rate limits |
| `PORT` | Local dev port (default `3847`) |

See `.env.example`.

## Experience and skills

Add roles and skills in **Admin → Experience**. The LinkedIn address on the profile page is only a public link.

## Deploy on PythonAnywhere

1. Upload or `git clone` this repo into your home directory (e.g. `/home/<user>/personal-site`).
2. Create a virtualenv (Python 3.10+ recommended) and install:

   ```bash
   mkvirtualenv --python=python3.12 personal-site
   pip install -r requirements.txt
   ```

3. In the **Web** tab, add a new web app → **Manual configuration** → your Python version.
4. Set **Source code** to the project root and **Working directory** to the same path.
5. Edit the WSGI file (e.g. `/var/www/<user>_pythonanywhere_com_wsgi.py`):

   ```python
   import sys
   from pathlib import Path

   project = Path("/home/<user>/personal-site")
   if str(project) not in sys.path:
       sys.path.insert(0, str(project))

   # Optional: load .env from project root
   from dotenv import load_dotenv
   load_dotenv(project / ".env")

   from app import create_app
   application = create_app()
   ```

   Or point at the repo’s `wsgi.py` after adjusting `sys.path`.

6. Set env vars in the Web tab (**Environment variables**) or a `.env` file: at least `SECRET_KEY`, strong `ADMIN_PASSWORD`, and your `GITHUB_USERNAME`.
7. Ensure the app can write to `instance/` (SQLite). On PA, the project directory under your home is writable.
8. Reload the web app.

Static files are served by Flask in this small app; for heavier traffic you can map `/static` to `app/static` in the Web tab.

Production tip: run once under the web app so the DB seeds, then sign in and change the admin password / profile copy.

## Project layout

```
app/
  blueprints/     # public + admin routes
  services/       # GitHub sync, LinkedIn export sync
  templates/      # Jinja templates
  static/         # CSS + JS
  models.py       # SQLite models
  seed.py         # admin + sample content
config.py
run.py            # local server
wsgi.py           # WSGI entry
```

## License

Personal use — edit freely for your own portfolio.
