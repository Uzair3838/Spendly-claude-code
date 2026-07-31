# Spec: Delete Expense

## Overview
Step 9 turns the `/expenses/<id>/delete` placeholder into a working delete
flow. A logged-in user can click "Delete" on any of their own recent
transactions on the profile page, confirm the action on a confirmation
page, and the row in `expenses` is permanently removed. After the delete,
the user is redirected back to `/profile` where the row no longer appears
and the totals update. This is the third CRUD action in the app and
completes the pair started by Step 7 (add) and Step 8 (edit), giving the
user full control over their records.

## Depends on
- Step 1: Database setup (`expenses` table exists with `id` PK and
  `user_id` FK)
- Step 2: Registration (users can be created)
- Step 3: Login / Logout (session available so we know which user)
- Step 4: Profile page UI (where the Delete link lives and where users
  return)
- Step 5: Backend connection (query helpers exist for refresh)
- Step 7: Add expense (the form, validation pattern, and helper style are
  the template for this step)
- Step 8: Edit expense (the ownership check pattern and the Actions
  column on the profile table are reused here)

## Routes
- `GET /expenses/<int:id>/delete` — render a small confirmation page
  showing the row's date, description, amount, and category, with a
  Confirm button and a Cancel link back to `/profile` — logged-in only
- `POST /expenses/<int:id>/delete` — verify ownership, delete the row,
  redirect to `/profile` (POST-redirect-GET) — logged-in only

The placeholder string in `app.py`
(`return "Delete expense — coming in Step 9"`) is replaced with the real
implementation. Both GET and POST require a session — if no `user_id`,
redirect to `/login` (same pattern as `/profile`, `/expenses/add`, and
`/expenses/<id>/edit`).

If the row does not exist OR belongs to a different user, return
`abort(404)` — never reveal that the row exists but is owned by someone
else. Same pattern as Step 8.

The GET branch must NOT perform the delete — it only renders the
confirmation page. Deletion only happens on POST. This is the standard
CSRF-defence posture for browser-driven deletes and means an accidental
URL visit (or a prefetcher) cannot wipe a row.

## Database changes
No database changes. The `expenses` table from Step 1 already supports
`DELETE FROM expenses WHERE id = ? AND user_id = ?`:

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
- **Create:** `templates/delete_expense.html`
  - Extends `base.html`
  - Title: "Delete expense — Spendly"
  - Reuses `.auth-section` / `.auth-container` / `.auth-card` so the
    page looks consistent with add/edit
  - Header: "Delete expense"
  - Subtitle: a short warning like "This cannot be undone"
  - Body: a small summary card showing the row's
    - date (YYYY-MM-DD)
    - description (or "—" if empty)
    - amount (formatted as `Rs{:,.2f}`)
    - category (rendered as a `.cat-badge.cat-<name>` chip so it matches
      the profile table)
  - A `<form method="POST" action="{{ url_for('delete_expense', id=expense.id) }}">`
    with a single submit button styled `.btn-submit` reading
    "Yes, delete"
  - A separate "Cancel" link next to the button, styled like the
    existing `.auth-switch` anchor pointing at `/profile`
  - Back link to `/profile` below the card (same as add/edit)

- **Modify:** `templates/profile.html`
  - Extend the existing "Actions" column (added in Step 8) so each row
    has both "Edit ›" and "Delete" links
  - The Delete link is text-only with no chevron, separated from Edit by
    a small gap (CSS handles the spacing — no inline styles)
  - Both links point at `{{ url_for('...', id=tx.id) }}` so the URLs are
    built server-side from the row id, never from any user-controlled
    value
  - Reuse the existing `.profile-actions-col` / `.profile-edit-link`
    styling; add a sibling `.profile-delete-link` class for the new
    link

## Files to change
- `app.py` — replace the `delete_expense(id)` placeholder. Add a `GET`
  branch that loads the row (verifying ownership via
  `get_expense_for_user`), renders `delete_expense.html`. Add a `POST`
  branch that verifies ownership the same way and runs
  `DELETE FROM expenses WHERE id = ? AND user_id = ?`. Both branches
  must 404 on missing or foreign rows, and confirm the session user
  still exists (mirror `edit_expense` and `add_expense`).
- `templates/profile.html` — add a Delete link next to the existing
  Edit link in the Actions column.
- `static/css/style.css` — add a `.profile-delete-link` rule. Mirror
  the existing `.profile-edit-link` styling but use a slightly muted
  colour so Edit and Delete are visually distinct. Add a small
  horizontal gap between the two links.

## Files to create
- `templates/delete_expense.html` — new confirmation template.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (not relevant here but kept as blanket rule)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Ownership check on every code path: the `DELETE` must filter on
  `user_id = ?` AND the GET must look up the row with
  `get_expense_for_user(id, session["user_id"])` (which already filters
  on `user_id`)
- If the row does not exist OR belongs to another user, return
  `abort(404)` — do not redirect with a flash message (avoids leaking
  the existence of someone else's expense)
- The `user_id` on `DELETE` comes from `session["user_id"]`, never from
  the URL or any form input
- Deletion only happens on POST — GET only renders the confirmation
- On successful delete, redirect to `/profile` (POST-redirect-GET, no
  query string) so the browser back button does NOT re-submit
- Confirm the session user still exists before doing DB work — if a user
  was deleted while a session cookie is still alive, drop the session and
  redirect to `/login` (mirrors the pattern in `add_expense`,
  `edit_expense`, and `profile`)
- The confirmation page must show enough info that the user knows
  exactly what they are deleting: date, description, amount, category
- Use the same `.cat-badge.cat-<name>` class for the category chip so
  the colour matches the profile table — keep the 7 category names
  identical to `EXPENSE_CATEGORIES` in `app.py`
- The Cancel link on the confirmation page goes to `/profile` (same as
  the "← Back to profile" link below the card)
- No new flash messages — the row simply disappearing from the
  profile table is feedback enough (matches the silent-success pattern
  from Step 7 and Step 8)
- No JS confirm() dialog — the dedicated confirmation page is the
  confirmation, which keeps the flow accessible and works without JS
- Reuse `get_expense_for_user` from `database/queries.py` rather than
  writing a new SELECT — it already returns the columns needed for
  the confirmation summary and applies the ownership filter

## Definition of done
- [ ] Visiting `/expenses/<id>/delete` while logged out redirects to
      `/login`
- [ ] Visiting `/expenses/<id>/delete` for a non-existent id returns
      404
- [ ] Visiting `/expenses/<id>/delete` for an id owned by a different
      user returns 404 (not a redirect)
- [ ] Visiting `/expenses/<id>/delete` for one of my own rows shows the
      confirmation page with the row's date, description, amount, and
      category
- [ ] Clicking "Cancel" returns to `/profile` without deleting
- [ ] Visiting `/expenses/<id>/delete` via GET does NOT delete the row
      (only the POST branch deletes — even if someone visits the URL
      directly)
- [ ] Clicking "Yes, delete" removes the row from `expenses` and
      redirects to `/profile`
- [ ] After deletion, the row no longer appears in the
      recent-transactions table on `/profile`
- [ ] The total-spent, transaction-count, top-category, and category
      breakdown on `/profile` update to reflect the deletion
- [ ] After a successful delete, hitting the browser back button does
      NOT re-delete (POST-redirect-GET)
- [ ] The "Actions" column in the recent-transactions table on
      `/profile` shows both "Edit ›" and "Delete" for each row
- [ ] The Delete link points at the correct delete URL
      (`/expenses/<id>/delete`)
- [ ] The confirmation page looks consistent with `/expenses/add` and
      `/expenses/<id>/edit` (same `.auth-section` / `.auth-card`
      styling)
- [ ] The category chip on the confirmation page matches the colour of
      the same category on the profile table