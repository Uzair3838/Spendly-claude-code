# Spec: Edit Expense

## Overview
Step 8 turns the `/expenses/<id>/edit` placeholder into a working edit flow.
A logged-in user can click "Edit" on any of their own recent transactions
on the profile page, change one or more fields (amount, category, date,
description), and save. On success the row in `expenses` is updated and the
user is redirected back to `/profile` where the updated transaction appears
in place. This is the second CRUD action in the app and pairs with Step 7
(add) and Step 9 (delete) to give the user full control over their records.

## Depends on
- Step 1: Database setup (`expenses` table exists with all required columns)
- Step 2: Registration (users can be created)
- Step 3: Login / Logout (session available so we know which user)
- Step 4: Profile page UI (where the Edit link lives and where users return)
- Step 5: Backend connection (query helpers exist for refresh)
- Step 7: Add expense (the `/expenses/add` form, validation pattern, and
  `_render_add_form` helper style are the template for this step)

## Routes
- `GET /expenses/<int:id>/edit` — render the edit-expense form pre-filled
  with the current row's values — logged-in only
- `POST /expenses/<int:id>/edit` — validate input, update the `expenses`
  row, redirect to `/profile` — logged-in only

The placeholder string in `app.py`
(`return "Edit expense — coming in Step 8"`) is replaced with the real
implementation. Both GET and POST require a session — if no `user_id`,
redirect to `/login` (same pattern as `/profile` and `/expenses/add`).

If the row does not exist OR belongs to a different user, return
`abort(404)` — never reveal that the row exists but is owned by someone else.

## Database changes
No database changes. The `expenses` table from Step 1 already supports
`UPDATE ... SET ... WHERE id = ?` with the same column set as the add flow:

```
id INTEGER PRIMARY KEY AUTOINCREMENT
user_id INTEGER NOT NULL REFERENCES users(id)
amount REAL NOT NULL
category TEXT NOT NULL
date TEXT NOT NULL                -- YYYY-MM-DD
description TEXT
created_at TEXT DEFAULT (datetime('now'))
```

## Templates
- **Create:** `templates/edit_expense.html`
  - Extends `base.html`
  - Title: "Edit expense — Spendly"
  - Form with `method="POST" action="{{ url_for('edit_expense', id=expense.id) }}"`
    containing the same four fields as `add_expense.html`:
    - `amount` — `<input type="number" step="0.01" min="0.01" required>`
      with label "Amount (Rs)"
    - `category` — `<select required>` with the same 7 fixed categories
      (Food, Transport, Shopping, Bills, Entertainment, Health, Other)
    - `date` — `<input type="date" required>` with label "Date"
    - `description` — `<textarea>` with label "Description (optional)"
  - Submit button: "Save changes"
  - All four fields are pre-filled with the current row's values when
    rendering GET. On POST validation failure, fields are re-filled with
    the user's submitted values (same pattern as `add_expense.html`).
  - Shows the current error message in `.auth-error` (same class as
    login/register/add_expense) if `error` is passed to the template
  - Back link to `/profile`

- **Modify:** `templates/profile.html`
  - Add an "Actions" column to the recent-transactions table header
    and body
  - Body cells contain a small "Edit" link pointing at
    `{{ url_for('edit_expense', id=tx.id) }}` for each row
  - The link is text-only with a small chevron (`›`) to keep the table
    visually quiet — no button styling needed
  - Use the existing column widths and `profile-amount-col` styling on
    the new Actions column so the table stays aligned

## Files to change
- `app.py` — replace the `edit_expense(id)` placeholder. Add a `GET` branch
  that loads the row (verifying ownership), renders `edit_expense.html`
  with the row's values. Add a `POST` branch that validates the same way
  as `add_expense` (reuse the validation logic where reasonable) and runs
  `UPDATE expenses SET ... WHERE id = ? AND user_id = ?`.
- `templates/profile.html` — add an "Actions" column with an "Edit" link
  per row. Note: `get_recent_transactions` in `database/queries.py` does
  not currently return `id` — see Files to change note in `queries.py`
  below if the helper needs a small update.
- `database/queries.py` — `get_recent_transactions` must include `id` in
  its `SELECT` and in the returned dicts so the profile template can
  link to the edit route. One-line change.
- `static/css/style.css` — minimal styles for the new Actions column:
  alignment (right) and hover state for the Edit link. Reuse existing
  classes where possible.

## Files to create
- `templates/edit_expense.html` — new edit-expense form template.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (not relevant here but kept as blanket rule)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Ownership check on every code path: the `UPDATE` must filter on
  `user_id = ?` AND the GET must look up `WHERE id = ? AND user_id = ?`
- If the row does not exist OR belongs to another user, return
  `abort(404)` — do not redirect with a flash message (avoids leaking
  the existence of someone else's expense)
- The `user_id` on `UPDATE` comes from `session["user_id"]`, never from
  the form — same pattern as `add_expense`
- Validation rules identical to Step 7:
  - `amount` must parse to a float > 0 and ≤ `MAX_AMOUNT`
  - `category` must be one of the 7 fixed values in `EXPENSE_CATEGORIES`
  - `date` must parse as `YYYY-MM-DD` via `date.fromisoformat`
  - `description` is optional but ≤ 500 characters
- On validation failure, re-render the form with the user's input
  preserved (so they don't lose what they typed)
- On success, redirect to `/profile` (POST-redirect-GET, no query string)
- Confirm the session user still exists before doing DB work — if a user
  was deleted while a session cookie is still alive, drop the session and
  redirect to `/login` (mirrors the pattern in `add_expense` and
  `profile`)
- Reuse the existing `_render_add_form(error, form, today_iso)` helper
  shape — either factor a shared `_render_expense_form` helper or write
  a parallel `_render_edit_form` for clarity (prefer factoring a single
  helper to avoid drift, but only if it doesn't entangle the two
  templates' differences)
- The categories `<option>` list lives in the template as a Jinja
  `{% for ... %}` loop over the `categories` tuple passed from the route
- Category colours are already wired up via `.cat-badge.cat-<name>` in
  the profile table — keep the 7 names identical so badges match

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for a non-existent id returns 404
- [ ] Visiting `/expenses/<id>/edit` for an id owned by a different user
      returns 404 (not a redirect)
- [ ] Visiting `/expenses/<id>/edit` for one of my own rows shows the form
      with all four fields pre-filled with the row's current values
- [ ] Submitting the form with valid values updates the row in `expenses`
      and redirects to `/profile`
- [ ] The updated transaction appears in the recent-transactions table
      on `/profile` with the new values
- [ ] The total-spent, transaction-count, and category breakdown on
      `/profile` update to reflect the edited row
- [ ] Submitting with `amount` empty, zero, or negative re-renders the
      form with an error message and does NOT update the row
- [ ] Submitting with an invalid category re-renders the form with an
      error and does NOT update the row
- [ ] Submitting with a malformed date re-renders the form with an error
      and does NOT update the row
- [ ] Submitting with `description` empty still saves the row (description
      stored as `""` or NULL — pick one and stay consistent with Step 7)
- [ ] Submitting with `description` over 500 characters re-renders the
      form with an error and does NOT update the row
- [ ] After a successful save, hitting the browser back button does NOT
      re-submit the form (POST-redirect-GET)
- [ ] The "Actions" column appears in the recent-transactions table on
      `/profile`, and each row has an "Edit" link pointing at the
      correct edit URL
- [ ] The edit form looks consistent with `/expenses/add` (same
      `.auth-section` / `.auth-card` styling)