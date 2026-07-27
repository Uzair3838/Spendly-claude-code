# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the profile page so users can narrow the
transaction list, summary stats, and category breakdown to a specific time
window. Currently all data shown is all-time; after this step a user can
pick "This month", "Last month", "Last 3 months", "This year", or a custom
date range and every section of the profile page updates accordingly.

## Depends on
- Step 1: Database setup (tables exist)
- Step 2: Registration (users stored)
- Step 3: Login / Logout (session available)
- Step 4: Profile page static UI (template exists)
- Step 5: Backend connection (query helpers return live data)

## Routes
No new routes. The existing `GET /profile` route is modified to accept
optional query-string parameters:

- `GET /profile?range=this_month` — filter to current calendar month
- `GET /profile?range=last_month` — filter to previous calendar month
- `GET /profile?range=last_3_months` — filter to last 3 calendar months
- `GET /profile?range=this_year` — filter to current calendar year
- `GET /profile?range=custom&from=YYYY-MM-DD&to=YYYY-MM-DD` — custom range
- `GET /profile` (no params) — all-time data (current behaviour, unchanged)

Access level: logged-in only (unchanged).

## Database changes
No database changes. The `expenses` table already has a `date TEXT` column
in `YYYY-MM-DD` format that can be filtered with `BETWEEN`.

## Templates
- **Modify:** `templates/profile.html`
  - Add a filter bar between the user-info card and the summary stats row.
  - The bar contains preset buttons (All time, This month, Last month,
    Last 3 months, This year) and a Custom toggle that reveals two
    `<input type="date">` fields (From / To) with an Apply button.
  - The active preset is visually highlighted.
  - When a custom range is active, the date inputs show the selected values.
  - Filters submit via GET (page reload) — no JS fetch required.
  - The "all time" label on the Total-spent tile changes to reflect the
    active filter (e.g. "this month", "Jul 2026", "custom range").

## Files to change
- `app.py` — update the `profile()` route to parse `range`, `from`, `to`
  query params, compute the actual `start_date` / `end_date`, and pass them
  to the query helpers.
- `database/queries.py` — update `get_summary_stats`,
  `get_recent_transactions`, and `get_category_breakdown` to accept optional
  `start_date` and `end_date` keyword arguments and add a
  `WHERE date BETWEEN ? AND ?` clause when provided.
- `templates/profile.html` — add filter bar UI and wire up the active state.
- `static/css/style.css` — styles for the filter bar, preset buttons, and
  custom date inputs.

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (not relevant here but kept as blanket rule)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Date parsing in `app.py` must validate the format (`YYYY-MM-DD`) and
  silently fall back to all-time if the values are invalid or missing
- `start_date` / `end_date` are inclusive on both ends
- When no filter is applied, queries must behave exactly as they do today
  (no date clause at all) to avoid regressions
- Preset ranges are computed server-side relative to `date.today()` so the
  page works without JavaScript
- Filter bar buttons are regular `<a>` tags with `href` — no JavaScript
  required for preset filters
- Custom range uses a `<form method="GET" action="/profile">` with a hidden
  `<input name="range" value="custom">` so the two date inputs submit as
  query params
- The filter bar must be responsive: wrap gracefully on narrow screens

## Definition of done
- [ ] Visiting `/profile` with no query params shows all-time data — same as before
- [ ] Clicking "This month" reloads the page with `?range=this_month` and
      stats/transactions/categories reflect only the current month's expenses
- [ ] Clicking "Last month" shows only the previous month's data
- [ ] Clicking "Last 3 months" shows the last 3 calendar months
- [ ] Clicking "This year" shows the current year's data
- [ ] Custom range with valid `from` and `to` dates filters correctly
- [ ] Custom range with invalid dates falls back to all-time silently
- [ ] The active filter preset is visually highlighted
- [ ] The Total-spent tile's sub-label reflects the active filter name
- [ ] The filter bar looks correct on both desktop and mobile widths
- [ ] A user with no expenses in the filtered period sees Rs0.00, 0 transactions, and empty category list — no errors
