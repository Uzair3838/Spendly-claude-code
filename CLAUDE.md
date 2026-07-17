# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Spendly** is a personal expense tracking web app (rupee-currency), built as a step-by-step tutorial course project. The codebase is intentionally scaffolded: the landing page is finished, and most other routes return placeholders that students will implement in upcoming steps (database → auth → dashboard → CRUD).

Current state of the roadmap, as encoded in `app.py`:
- **Done:** landing, register/login pages (UI), terms, privacy
- **Step 1 — Database:** `database/db.py` is empty (just a comment describing `get_db`, `init_db`, `seed_db`)
- **Step 2+ — Auth wiring:** `register`/`login` routes currently have no POST handlers
- **Step 3 — Logout, Step 4 — Profile, Steps 7–9 — Expense CRUD:** placeholder routes only

## Common Commands

The dev server runs on **port 5001** (not the Flask default 5000):

```bash
# Activate the project's existing venv (Windows)
source claudevenv/Scripts/activate

# Run the dev server
python app.py
# → http://localhost:5001
```

```bash
# Install deps (only if setting up fresh)
pip install -r requirements.txt
```

There are no tests yet. `pytest` and `pytest-flask` are in `requirements.txt` for upcoming steps.

## Architecture

**Stack:** Flask 3.1 + Jinja templates + vanilla CSS/JS. No JS framework — modal and other interactions are hand-rolled.

**Layout:**
- `app.py` — Flask app, all routes. Implemented routes render templates; unimplemented ones return short "coming in Step N" strings. This is the roadmap index for the course.
- `templates/base.html` — Layout shell: nav, `<main>{% block content %}{% endblock %}</main>`, footer (with Terms/Privacy links), and a `{% block scripts %}` per-page JS hook. `static/css/style.css` and `static/js/main.js` are loaded globally.
- `templates/landing.html` — Hero, features, CTA, and the YouTube modal (with its own scoped `<style>` and `<script>` blocks — modal CSS lives inline in the template, not in `style.css`).
- `templates/{login,register,terms,privacy}.html` — Static-ish pages; auth pages have POST forms that point at routes not yet wired up.
- `static/css/style.css` — Single global stylesheet (~16 KB). Design uses DM Serif Display + DM Sans (Google Fonts), a dark/cream palette, and CSS custom properties (e.g. `var(--radius-md)`).
- `static/js/main.js` — Intentionally empty; placeholder for student additions.
- `database/db.py` — Empty scaffold for SQLite layer (see comment block).
- `prompts_file.txt` — Course author's prompt log, not part of the app. Useful for understanding the intended scope of each step.

## Conventions Specific to This Repo

- **Commit message style:** `area: short description` (e.g. `landing: add youtube modal on see how it works click`). Follow this format.
- **Each change gets its own commit** — one logical change per commit, as the course is built commit-by-commit.
- **Don't touch the venv or the SQLite file:** `claudevenv/`, `expense_tracker.db`, `__pycache__/`, `.env` are gitignored. `hero_image.png` is also gitignored (it's a design reference, not an asset).
- **Vanilla JS only.** No npm, no bundlers, no frameworks. Inline `<script>` blocks in templates are acceptable for page-specific behavior.
- **YouTube modal pattern:** the `landing.html` modal stops playback by detaching `iframe.src` on close (no YouTube IFrame API). Reuse this pattern rather than introducing the API.

## Working in This Repo

- `app.py` is the single source of truth for what's done vs. planned. Read it first to see which routes are live.
- When asked to add a feature, check whether a placeholder route already exists for it — extend that route rather than creating a new one.
- The design is in `static/css/style.css`; landing.html's modal CSS is the only notable inline exception. New pages should reuse the existing classes (`.btn-primary`, `.auth-section`, `.feature-card`, etc.) rather than introducing new ones.
- The footer Terms/Privacy links route to dedicated pages — keep legal pages updated as features that affect data collection are added.
</content>
</invoke>