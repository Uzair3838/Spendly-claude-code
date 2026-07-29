# Spec: Add Expense

## Overview
Step 7 turns the `/expenses/add` placeholder into a working form that lets
a logged-in user record a new expense. The form has four fields — amount,
category, date, and description — and on submit the expense is inserted
into the `expenses` table tied to the current user. The user is then
redirected back to the profile page where the new entry appears at the
top of the recent-transactions list. This is the first CRUD action in the
app and lays the foundation for Steps 8 (edit) and 9 (delete).

## Depends on
- Step 1: Database setup (`expenses` table exists with `user_id` FK)
- Step 2: Registration (users can be created)
- Step 3: Login / Logout (session available so we know which user)
- Step 4: Profile page UI (where users end up after adding)
- Step 5: Backend connection (query helpers exist for refresh)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate input, insert into `expenses`, redirect
  to `/profile` — logged-in only

The placeholder string in `app.py` (`return "Add expense — coming in Step 7"`)
is replaced with the real implementation. Both GET and POST require a
session — if no `user_id`, redirect to `/login` (same pattern as `/profile`).

## Database changes
No database changes. The `expenses` table from Step 1 already has all the
columns needed:

```
id INTEGER PRIMARY KEY AUTOINCREMENT
user_id INTEGER NOT NULL REFERENCES users(id)
amount REAL NOT NULL
category TEXT NOT NULL
date TEXT NOT NULL                -- YYYY-MM-DD
description TEXT
created_at TEXT DEFAULT (datetime('now'))
```

A new row is inserted per form submission. No migration needed.

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - Title: "Add expense — Spendly"
  - Form with `method="POST" action="/expenses/add"` containing:
    - `amount` — `<input type="number" step="0.01" min="0.01" required>`
      with label "Amount (Rs)"
    - `category` — `<select required>` with the 7 fixed categories:
      Food, Transport, Shopping, Bills, Entertainment, Health, Other
    - `date` — `<input type="date" required>` with label "Date",
      default value = today
    - `description` — `<textarea>` with label "Description (optional)"
    - Submit button: "Save expense"
  - Shows the current error message in `.auth-error` (same class as
    login/register) if `error` is passed to the template
  - Back link to `/profile`

- **Modify:** `templates/base.html`
  - Add an "Add expense" link in the nav for logged-in users, sitting
    next to "Analytics". Same styling as the existing nav links.

## Files to change
- `app.py` — replace the `add_expense()` placeholder. Add a `GET` branch
  that renders `add_expense.html` with a default date of today. Add a
  `POST` branch that validates the fields and inserts a row.
- `templates/base.html` — add "Add expense" nav link for logged-in users.
- `static/css/style.css` — styles for the new form. Reuse existing classes
  (`.auth-section`, `.auth-container`, `.auth-card`, `.form-group`,
  `.form-input`, `.btn-submit`) so the page looks consistent with
  login/register. Add a `.form-textarea` rule (or just use `.form-input`
  with sizing) for the description box.

## Files to create
- `templates/add_expense.html` — new add-expense form template.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (not relevant here but kept as blanket rule)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- The `description` field is optional (empty string is fine) but the
  other three (`amount`, `category`, `date`) are required
- `amount` must be a positive number greater than zero
- `category` must be one of the 7 fixed values (reject anything else so
  we don't pollute the breakdown chart later)
- `date` must parse as `YYYY-MM-DD` via `date.fromisoformat`
- Re-render the form with the user's input preserved on validation failure
  (so they don't lose what they typed)
- On success, redirect to `/profile` with no query string — the user sees
  the new transaction at the top of the list
- The `user_id` comes from `session["user_id"]`, never from the form
- Both GET and POST must check the session and redirect to `/login` if
  missing — don't render the form for logged-out users
- The categories `<option>` list lives in the template as a Jinja
  `{% for ... %}` loop over a tuple defined at the top of the template
  (no JS, no DB lookup)
- Category colours are already wired up via `.cat-badge.cat-<name>` in
  the profile table — keep the 7 names identical so badges match
- The default date should be `date.today().isoformat()` rendered into
  the `<input type="date" value="...">` server-side so no JS is needed

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows the form with
      today's date pre-filled
- [ ] Submitting the form with all 4 fields filled creates a row in
      `expenses` and redirects to `/profile`
- [ ] The new transaction appears at the top of the recent-transactions
      table on `/profile`
- [ ] The total-spent, transaction-count, and category breakdown on
      `/profile` update to reflect the new row
- [ ] Submitting with `amount` empty, zero, or negative re-renders the
      form with an error message and does NOT insert a row
- [ ] Submitting with no category selected re-renders the form with an
      error (HTML `required` handles the dropdown, but server-side must
      also reject an invalid/missing value)
- [ ] Submitting with a malformed date re-renders the form with an error
      and does NOT insert a row
- [ ] Submitting with `description` empty still saves the row (description
      stored as `""` or NULL — pick one and stay consistent)
- [ ] After a successful save, hitting the browser back button does NOT
      re-submit the form (POST-redirect-GET)
- [ ] The "Add expense" nav link appears in the navbar for logged-in
      users only
- [ ] The form looks consistent with `/register` and `/login` (same
      `.auth-section` / `.auth-card` styling)
