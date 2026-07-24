# Spec: Registration

## Overview
Wire up the existing `/register` route so users can actually create an account on Spendly. The route currently only renders the form template; this step adds the POST handler that validates input, hashes the password with werkzeug, inserts a new row into the `users` table, signs the user in, shows a success message on a successful login and redirects to the dashboard placeholder. This is the second step of the course and is the entry point for all logged-in functionality (login, profile, expense CRUD). 

## Depends on
- Step 1 — Database setup (the `users` table with `id`, `name`, `email`, `password_hash` must exist; `get_db()` and `generate_password_hash` must be available from `database/db.py`)

## Routes
- `POST /register` — create new user account, hash password, log the user in, redirect to `/profile` — public
- `GET /register` — already exists, renders the registration form — public (no change to behavior, will now accept flashed errors)

## Database changes
No database changes. The `users` table was created in Step 1 and has the exact columns needed (`name`, `email UNIQUE`, `password_hash`).

## Templates
- **Modify:** `templates/register.html` — no structural change required. The form already posts to `/register` and the template already renders `{{ error }}` inside `.auth-error`. No edits needed unless adding per-field validation errors.
- **Create:** none

## Files to change
- `app.py` — add `POST` method to the `/register` route; add imports for `request`, `redirect`, `session`, `generate_password_hash`, `check_password_hash` (only the first two strictly required for this step, but importing all four keeps login step tidy)

## Files to create
None

## New dependencies
No new dependencies. `werkzeug.security` is already in use via `database/db.py`.

## Rules for implementation
- No SQLAlchemy or any ORM — use raw `sqlite3` from `database.db.get_db()`
- Parameterized queries only — never build SQL with f-strings or `%` formatting
- Hash passwords with `werkzeug.security.generate_password_hash`
- Validate server-side: `name` non-empty, `email` non-empty and contains `@`, `password` length ≥ 8
- Email comparison for uniqueness must be case-insensitive (SQLite `COLLATE NOCASE` would require schema change; instead lowercase the email before insert/lookup)
- On success: insert user, store `user_id` in `session`, redirect to `url_for('profile')`
- On duplicate email or validation failure: re-render `register.html` with a generic error message ("Email already registered" / "Please fill all fields correctly") and `status=200` so the form is reusable
- Configure `app.secret_key` for `session` to work — read from environment variable `SECRET_KEY` with a development fallback so the dev server can boot
- Use CSS variables from `static/css/style.css` for any new styles — never hardcode hex values
- The existing `register.html` template already extends `base.html` and uses the `.auth-section`, `.auth-card`, `.auth-error`, `.form-group`, `.form-input`, `.btn-submit` classes — do not introduce new classes
- Do not touch the SQLite file (`spendly.db`) directly; let `init_db()` and `seed_db()` run on startup as already wired in `app.py`

## Definition of done
- [ ] Submitting `/register` with `name="Alice"`, `email="alice@example.com"`, `password="password123"` creates a row in `users` with a non-empty `password_hash`
- [ ] After successful registration, the user is redirected to `/profile` (currently a Step 4 placeholder) and `session["user_id"]` is set
- [ ] Submitting with an email that already exists in `users` re-renders the form with the error "Email already registered"
- [ ] Submitting with `password` shorter than 8 characters re-renders the form with a validation error
- [ ] Submitting with a missing `name`, `email`, or `password` re-renders the form with a validation error
- [ ] The stored `password_hash` is a werkzeug hash (starts with `pbkdf2:` or `scrypt:`), never plain text
- [ ] Two registrations with the same email differing only in case (e.g. `Alice@x.com` vs `alice@x.com`) are treated as the same email
- [ ] App starts without errors; `spendly.db` is not committed to git (already gitignored)
- [ ] `git status` is clean after the change is committed
