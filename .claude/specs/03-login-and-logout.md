# Spec: Login and Logout

## Overview
Wire up the existing `/login` and `/logout` routes so users can sign into and out of Spendly. The `/login` route currently only renders the form; this step adds the POST handler that validates credentials, verifies the password hash with werkzeug, starts a session, and redirects to the landing page. The `/logout` route replaces its "coming in Step 3" placeholder with a handler that clears the session and sends the user back to the landing page. The `/login` and `/register` routes also gain a small auth gate: signed-in users are bounced to `/` rather than seeing the auth forms again. This is the third step of the course and completes the minimal auth loop (register → login → logout) that all later logged-in features depend on.

## Depends on
- Step 1 — Database setup (the `users` table with `id`, `name`, `email`, `password_hash` must exist; `get_db()` must be available)
- Step 2 — Registration (the `/register` POST handler must be wired so accounts actually exist in `users` and `werkzeug.security.check_password_hash` is already imported in `app.py`)

## Routes
- `POST /login` — verify email + password, start a session, redirect to `/` — public
- `GET /login` — renders the sign-in form when signed out; redirects to `/` when already signed in — public
- `GET /register` — renders the registration form when signed out; redirects to `/` when already signed in — public (POST handler from Step 2 is unchanged and still creates accounts)
- `GET /logout` — clear the session and redirect to the landing page — public (safe to call when already logged out)

## Database changes
No database changes. The `users` table from Step 1 already has every column needed (`id`, `name`, `email`, `password_hash`).

## Templates
- **Modify:** `templates/login.html` — small, optional touch-ups only. The form already posts to `/login`, renders `{{ error }}` inside `.auth-error`, and uses `.form-input` / `.btn-submit`. If a previous failed email is passed back via the template (e.g. `email` context variable), pre-fill the email field so the user only has to retype the password. No structural rewrite.
- **Modify:** `templates/base.html` — make the nav reflect login state. When `session.get("user_id")` is set, show the user's name and a "Log out" link in place of "Sign in" / "Get started". Keep the `.navbar`, `.nav-links`, `.nav-brand` markup; only swap the right-hand links.

## Files to change
- `app.py` — add `POST` handler to `/login` (success redirects to `/`); add an auth gate to `GET /login` and `GET /register` that redirects signed-in users to `/`; replace the `/logout` placeholder with a real handler that calls `session.clear()` and redirects to `landing`; update `base.html` to be session-aware (handled via the template change below)
- `templates/login.html` — pre-fill the email field on failed login attempt (optional, but matches the form's `placeholder` style)
- `templates/base.html` — swap the "Sign in / Get started" links for "Hi, {{ name }} / Log out" when a user is logged in

## Files to create
None

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` is already imported in `app.py` (added in Step 2). `sqlite3` is the standard library.

## Rules for implementation
- No SQLAlchemy or any ORM — use raw `sqlite3` via `database.db.get_db()`
- Parameterized queries only — never build SQL with f-strings or `%` formatting
- Use `werkzeug.security.check_password_hash(stored_hash, provided_password)` — never compare hashes or passwords with `==`
- Email lookup must be case-insensitive: lowercase the submitted email before querying (mirrors the Step 2 convention)
- On login success: store `user_id` and `user_name` in `session` (mirrors what `register` already does), then redirect to `url_for("landing")` (the user lands on the marketing page; the navbar's "Log out" is what tells them they're signed in)
- On failure: re-render `login.html` with a generic error ("Invalid email or password" — do not reveal whether the email exists) and HTTP `200` so the form is reusable
- `/login` (GET) and `/register` (GET) must both check `session.get("user_id")` first; if a user is signed in, redirect to `url_for("landing")` instead of rendering the form. `POST /register` is NOT gated — a signed-in user can still register a new account if they POST to it (matches how most apps work and keeps Step 2's behavior intact).
- `/logout` must be a `GET` (the nav is a plain link) and must be safe to call when nobody is logged in — just call `session.clear()` and redirect regardless
- `session["user_name"]` is already populated by the `/register` route; read it in `base.html` to greet the user — do not query the DB from the layout on every request
- Use CSS variables from `static/css/style.css` for any new styles — never hardcode hex values
- The existing `login.html` and `base.html` already extend / contain the right blocks; do not introduce new CSS classes unless necessary
- Do not touch the SQLite file (`spendly.db`) directly; let `init_db()` and `seed_db()` run on startup as already wired in `app.py`
- The session already works because Step 2 set `app.secret_key` — no changes to app config are required for this step

## Definition of done
- [ ] `GET /login` while signed out renders the sign-in form
- [ ] `GET /login` while signed in redirects to `/`
- [ ] `GET /register` while signed out renders the registration form
- [ ] `GET /register` while signed in redirects to `/`
- [ ] Submitting `/login` with valid credentials (e.g. `demo@spendly.com` / `demo123` from the seed user) sets `session["user_id"]` and `session["user_name"]` and redirects to `/`
- [ ] Submitting `/login` with a valid email but wrong password re-renders the form with the error "Invalid email or password" and does not set any session keys
- [ ] Submitting `/login` with an email that does not exist re-renders the form with the same generic error (no user-enumeration leak)
- [ ] Email matching is case-insensitive (`DEMO@spendly.com` works the same as `demo@spendly.com`)
- [ ] After a failed login, the email field is pre-filled with the value the user typed (optional but matches the form's UX)
- [ ] `GET /logout` clears the session (verifiable: `session` is empty in subsequent requests) and redirects to `/`
- [ ] `GET /logout` while already logged out does not error — it clears the (empty) session and redirects to `/`
- [ ] When logged in, the nav shows the user's name and a "Log out" link instead of "Sign in" / "Get started"
- [ ] When logged out, the nav shows "Sign in" / "Get started" as before
- [ ] No password or hash ever appears in a response, log line, or template variable
- [ ] No new entries in `spendly.db` are required for this step to work end-to-end (the seed user is enough)
- [ ] App starts without errors; `spendly.db` is not committed to git (already gitignored)
- [ ] `git status` is clean after the change is committed
