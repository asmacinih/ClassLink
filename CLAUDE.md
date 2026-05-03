# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ClassLink is a student social directory web app — think LinkedIn for students. Flask + PostgreSQL backend, plain HTML/CSS/JS frontend (no frameworks).

## Running locally

```bash
export DATABASE_URL="postgresql://user:password@host/dbname"  # use External URL from Render
python3 app.py
# Open http://127.0.0.1:5001
```

## Deploying

```bash
git push  # Render auto-deploys on push to main
```

Web service + PostgreSQL are configured in `render.yaml`. Environment variables (`DATABASE_URL`, `SECRET_KEY`) are set manually in the Render dashboard.

## Architecture

**Single-file backend** — all routes, DB logic, and helpers live in `app.py`.

**Database** — PostgreSQL in production (Render), configured via `DATABASE_URL` env var. All queries go through the `query(sql, params, one, write)` helper which handles connections and returns plain dicts. `init_db()` runs at startup via `with app.app_context()` and creates tables if they don't exist.

**Frontend** — HTML files sit at the project root (not in `static/`). Flask serves them via `send_from_directory(".", filename)`. Pages talk to the backend exclusively through `fetch()` calls to `/api/*` routes. No build step, no bundler.

**Auth** — Flask server-side sessions. `session["username"]` is set on sign-in/sign-up and checked at the top of every protected route.

**Password hashing** — SHA-256 via `hashlib` (no bcrypt).

## File layout

| File | Purpose |
|------|---------|
| `app.py` | Entire backend — DB helpers, all API routes, static file serving |
| `signin.html` | Sign in page (entry point, served at `/`) |
| `signup.html` | Step 1 of onboarding — pick username + password |
| `profile-setup.html` | Step 2 of onboarding — fill in profile info |
| `home.html` | Feed of students at your school + live search |
| `profile.html` | Individual profile page, loaded via `?u=username` |
| `render.yaml` | Render deployment config (web service + free PostgreSQL) |

## API routes

| Method | Route | Auth required |
|--------|-------|---------------|
| POST | `/api/signup` | No |
| POST | `/api/signin` | No |
| POST | `/api/signout` | Yes |
| POST | `/api/profile` | Yes |
| GET | `/api/me` | Yes |
| GET | `/api/user/<username>` | Yes |
| GET | `/api/feed` | Yes |
| GET | `/api/search?q=` | Yes |

## Key decisions

- Feed shows classmates from the same `school` field; falls back to all users if school is unset
- Usernames are lowercase, alphanumeric + underscores only (`^[a-z0-9_]+$`)
- No edit-profile page yet — profile can only be set during onboarding
