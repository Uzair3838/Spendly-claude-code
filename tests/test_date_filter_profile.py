"""
Tests for the date-filter feature on the /profile page (Step 6).

These tests cover:
  - No-filter (all-time) behaviour
  - Preset filters (this_month, last_month, last_3_months, this_year)
  - Custom date range
  - Invalid custom dates (silent fallback to all-time)
  - Auth guard on /profile
  - Empty-result handling (no expenses in the filtered period)
  - Filter-label text on the Total-spent tile
  - Active-state highlighting on the preset buttons
"""
import datetime
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from database.db import get_db, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    """Use a fresh temp SQLite file for every test."""
    db_path = str(tmp_path / "test.db")
    db_module.DB_PATH = db_path
    init_db()
    yield db_path
    db_module.DB_PATH = "spendly.db"


@pytest.fixture()
def app():
    from app import app
    app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "WTF_CSRF_ENABLED": False,
    })
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


# A second demo user with no expenses. Used for "empty result" tests.
EMPTY_USER_ID = 2


@pytest.fixture()
def seeded():
    """Seed two users — one with the 8 July 2026 expenses, one with none."""
    conn = get_db()
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "Demo User", "demo@spendly.com",
         generate_password_hash("demo123"), "2026-01-15 10:30:00"),
    )
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (EMPTY_USER_ID, "Empty User", "empty@spendly.com",
         generate_password_hash("demo123"), "2026-01-15 10:30:00"),
    )
    expenses = [
        (1, 250.00, "Food",          "2026-07-02", "Lunch at office canteen"),
        (1, 480.50, "Food",          "2026-07-05", "Groceries from local mart"),
        (1, 120.00, "Transport",     "2026-07-03", "Uber to airport"),
        (1, 1500.00, "Bills",        "2026-07-01", "Electricity bill"),
        (1, 350.00, "Health",        "2026-07-08", "Pharmacy restock"),
        (1, 600.00, "Entertainment", "2026-07-10", "Movie tickets"),
        (1, 1299.00, "Shopping",     "2026-07-12", "New running shoes"),
        (1, 80.00,  "Other",         "2026-07-15", "Misc cash spend"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()
    return {"user_id": 1, "empty_user_id": EMPTY_USER_ID}


@pytest.fixture()
def auth_client(client, seeded):
    """A logged-in test client (demo user with 8 July expenses)."""
    with client.session_transaction() as sess:
        sess["user_id"] = seeded["user_id"]
        sess["user_name"] = "Demo User"
    return client


@pytest.fixture()
def empty_auth_client(client, seeded):
    """A logged-in test client with NO expenses (used for empty-result tests)."""
    with client.session_transaction() as sess:
        sess["user_id"] = seeded["empty_user_id"]
        sess["user_name"] = "Empty User"
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login_session(client, user_id, name):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name


def _count_transactions(html):
    """Count transaction rows in the rendered profile page."""
    # Each transaction row contains one <span class="cat-badge ..."> which
    # appears nowhere else in the page, so counting these is reliable
    # regardless of template whitespace.
    return html.count('<span class="cat-badge')


def _category_names(html):
    """Extract category names from the By-Category section."""
    names = []
    marker = "profile-cat-label"
    for line in html.splitlines():
        if marker in line:
            start = line.find(">", line.find(marker)) + 1
            end = line.find("<", start)
            if start > 0 and end > start:
                names.append(line[start:end].strip())
    return names


def _total_amount_in_html(html):
    """Pull the Total-spent tile value out of the rendered page."""
    needle = '<p class="mock-tile-value">Rs'
    start = html.find(needle)
    if start == -1:
        return None
    end = html.find("</p>", start)
    raw = html[start + len(needle):end]
    return raw.replace(",", "").strip()


def _current_month_range():
    today = date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()
    return start, end


def _last_month_range():
    today = date.today()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    start = last_prev.replace(day=1).isoformat()
    end = last_prev.isoformat()
    return start, end


def _last_three_months_start():
    today = date.today()
    month = today.month - 2
    year = today.year
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1).isoformat()


def _this_year_range():
    today = date.today()
    return date(today.year, 1, 1).isoformat(), today.isoformat()


# ---------------------------------------------------------------------------
# 1. No filter (all-time) — baseline behaviour preserved
# ---------------------------------------------------------------------------

class TestNoFilterAllTime:
    def test_profile_no_params_returns_200(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200

    def test_profile_no_params_shows_all_eight_transactions(self, auth_client):
        html = auth_client.get("/profile").data.decode()
        # All 8 seed expenses should be rendered as table rows.
        assert _count_transactions(html) == 8

    def test_profile_no_params_total_is_full_sum(self, auth_client):
        # 250 + 480.50 + 120 + 1500 + 350 + 600 + 1299 + 80 = 4679.50
        html = auth_client.get("/profile").data.decode()
        assert "Rs4,679.50" in html

    def test_profile_no_params_includes_all_seven_categories(self, auth_client):
        html = auth_client.get("/profile").data.decode()
        names = _category_names(html)
        assert set(names) == {"Food", "Transport", "Bills", "Health",
                              "Entertainment", "Shopping", "Other"}

    def test_profile_no_params_filter_label_is_all_time(self, auth_client):
        html = auth_client.get("/profile").data.decode()
        # The Total-spent tile meta text reflects "all time" when no filter
        # is active.
        assert "all time" in html


# ---------------------------------------------------------------------------
# 2. Preset filters
# ---------------------------------------------------------------------------

class TestPresetFilters:
    def test_this_month_includes_all_seeded_expenses(self, auth_client):
        # All 8 seed expenses are in July 2026, the current month.
        response = auth_client.get("/profile?range=this_month")
        assert response.status_code == 200
        html = response.data.decode()
        assert _count_transactions(html) == 8
        assert "Rs4,679.50" in html
        assert len(_category_names(html)) == 7

    def test_last_month_returns_zero_for_demo_user(self, auth_client):
        # Seeded expenses are in July 2026; "last month" is June 2026 → empty.
        response = auth_client.get("/profile?range=last_month")
        assert response.status_code == 200
        html = response.data.decode()
        # No transactions, no categories, no total spent.
        assert "Rs0.00" in html
        assert _count_transactions(html) == 0
        assert _category_names(html) == []

    def test_last_three_months_includes_current_month(self, auth_client):
        # All seed expenses fall within the last 3 calendar months.
        response = auth_client.get("/profile?range=last_3_months")
        assert response.status_code == 200
        html = response.data.decode()
        assert _count_transactions(html) == 8
        assert "Rs4,679.50" in html

    def test_this_year_includes_all_seeded_expenses(self, auth_client):
        response = auth_client.get("/profile?range=this_year")
        assert response.status_code == 200
        html = response.data.decode()
        assert _count_transactions(html) == 8
        assert "Rs4,679.50" in html

    @pytest.mark.parametrize("preset", [
        "this_month",
        "last_month",
        "last_3_months",
        "this_year",
    ])
    def test_each_preset_loads_without_error(self, auth_client, preset):
        response = auth_client.get(f"/profile?range={preset}")
        assert response.status_code == 200
        # Page must always render the profile section.
        assert b"profile-section" in response.data


# ---------------------------------------------------------------------------
# 3. Custom date range
# ---------------------------------------------------------------------------

class TestCustomRange:
    def test_custom_range_matching_all_seeds_returns_eight(self, auth_client):
        start, end = _current_month_range()
        response = auth_client.get(
            f"/profile?range=custom&from={start}&to={end}"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert _count_transactions(html) == 8
        assert "Rs4,679.50" in html

    def test_custom_range_before_all_seeds_returns_zero(self, auth_client):
        # Range entirely before July 2026 → no matches.
        response = auth_client.get(
            "/profile?range=custom&from=2020-01-01&to=2020-12-31"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert "Rs0.00" in html
        assert _count_transactions(html) == 0
        assert _category_names(html) == []

    def test_custom_range_partial_window_filters_correctly(self, auth_client, seeded):
        # Insert an extra expense in August 2026 and one in March 2026, then
        # filter to a window that includes only August.
        conn = get_db()
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (seeded["user_id"], 999.00, "Food", "2026-08-05", "August lunch"),
        )
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (seeded["user_id"], 200.00, "Bills", "2026-03-10", "March bill"),
        )
        conn.commit()
        conn.close()

        response = auth_client.get(
            "/profile?range=custom&from=2026-08-01&to=2026-08-31"
        )
        assert response.status_code == 200
        html = response.data.decode()
        # Only the August row should appear.
        assert _count_transactions(html) == 1
        assert "Rs999.00" in html
        assert "August lunch" in html

    def test_custom_range_inclusive_endpoints(self, auth_client):
        # `from` and `to` should both be inclusive per spec.
        # Place a single expense on the boundary date.
        conn = get_db()
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 50.00, "Other", "2026-04-15", "Boundary day expense"),
        )
        conn.commit()
        conn.close()

        # Both from=to=2026-04-15 should still include the row.
        response = auth_client.get(
            "/profile?range=custom&from=2026-04-15&to=2026-04-15"
        )
        assert response.status_code == 200
        html = response.data.decode()
        # The boundary expense should match; nothing else in April 2026 exists.
        assert "Rs50.00" in html


# ---------------------------------------------------------------------------
# 4. Invalid custom dates — silent fallback to all-time
# ---------------------------------------------------------------------------

class TestInvalidCustomDates:
    @pytest.mark.parametrize("bad_from,bad_to", [
        ("not-a-date",     "2026-12-31"),
        ("2026-07-01",     "garbage"),
        ("2026/07/01",     "2026/07/31"),   # wrong separator
        ("2026-13-01",     "2026-12-31"),   # invalid month
        ("2026-02-30",     "2026-12-31"),   # invalid day
        ("",               ""),             # empty
        ("2026-07-15",     ""),             # only `from` provided
        ("",               "2026-07-15"),   # only `to` provided
    ])
    def test_invalid_custom_dates_fall_back_to_all_time(
        self, auth_client, bad_from, bad_to
    ):
        url = f"/profile?range=custom&from={bad_from}&to={bad_to}"
        response = auth_client.get(url)
        # No error — page renders successfully.
        assert response.status_code == 200
        html = response.data.decode()
        # Falls back to all-time data → all 8 expenses shown.
        assert _count_transactions(html) == 8
        assert "Rs4,679.50" in html
        # The filter-label should reflect "all time" when fallback occurred.
        assert "all time" in html

    def test_invalid_custom_dates_surface_error_message(self, auth_client):
        """Malformed custom input falls back to all-time data AND surfaces
        a short error so the user knows why nothing filtered."""
        response = auth_client.get(
            "/profile?range=custom&from=not-a-date&to=2026-12-31"
        )
        assert response.status_code == 200
        html = response.data.decode()
        # Still shows all-time data.
        assert _count_transactions(html) == 8
        # And surfaces a human-readable error.
        assert "filter-error" in html
        assert "valid dates" in html

    def test_inverted_custom_range_surfaces_error_message(self, auth_client):
        response = auth_client.get(
            "/profile?range=custom&from=2026-12-31&to=2026-01-01"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert _count_transactions(html) == 8
        assert "filter-error" in html
        assert "after" in html.lower()


# ---------------------------------------------------------------------------
# 5. Auth guard — unauthenticated access redirects to /login
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_profile_without_session_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    @pytest.mark.parametrize("query", [
        "",
        "?range=this_month",
        "?range=last_month",
        "?range=last_3_months",
        "?range=this_year",
        "?range=custom&from=2026-01-01&to=2026-12-31",
    ])
    def test_profile_all_filter_variants_require_auth(self, client, query):
        response = client.get(f"/profile{query}")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# 6. Empty results — no expenses in the filtered window
# ---------------------------------------------------------------------------

class TestEmptyResults:
    def test_no_expenses_in_filtered_period_shows_zero_total(self, empty_auth_client):
        response = empty_auth_client.get("/profile")
        html = response.data.decode()
        assert response.status_code == 200
        assert "Rs0.00" in html

    def test_no_expenses_shows_zero_transaction_count(self, empty_auth_client):
        html = empty_auth_client.get("/profile").data.decode()
        # Find the Transactions tile value (the bare "0").
        # The tile is structured: <p class="mock-tile-value">0</p>
        assert '<p class="mock-tile-value">0</p>' in html

    def test_no_expenses_shows_dash_for_top_category(self, empty_auth_client):
        html = empty_auth_client.get("/profile").data.decode()
        assert "—" in html

    def test_no_expenses_has_empty_transaction_list(self, empty_auth_client):
        html = empty_auth_client.get("/profile").data.decode()
        # No <tr> rows in tbody.
        assert _count_transactions(html) == 0

    def test_no_expenses_has_empty_category_list(self, empty_auth_client):
        html = empty_auth_client.get("/profile").data.decode()
        assert _category_names(html) == []
        # Empty-state copy is rendered.
        assert "No categories yet." in html

    def test_no_expenses_does_not_error_with_active_filter(self, empty_auth_client):
        # The same empty-state contract must hold under a preset filter too.
        for preset in ("this_month", "last_month", "last_3_months", "this_year"):
            response = empty_auth_client.get(f"/profile?range={preset}")
            assert response.status_code == 200
            html = response.data.decode()
            assert "Rs0.00" in html
            assert _count_transactions(html) == 0
            assert _category_names(html) == []


# ---------------------------------------------------------------------------
# 7. Filter label on the Total-spent tile
# ---------------------------------------------------------------------------

class TestFilterLabel:
    def test_all_time_label_for_no_filter(self, auth_client):
        html = auth_client.get("/profile").data.decode()
        assert "all time" in html

    def test_this_month_label(self, auth_client):
        html = auth_client.get("/profile?range=this_month").data.decode()
        assert "this month" in html

    def test_last_3_months_label(self, auth_client):
        html = auth_client.get("/profile?range=last_3_months").data.decode()
        assert "last 3 months" in html

    def test_this_year_label(self, auth_client):
        html = auth_client.get("/profile?range=this_year").data.decode()
        assert "this year" in html

    def test_custom_label(self, auth_client):
        html = auth_client.get(
            "/profile?range=custom&from=2026-01-01&to=2026-12-31"
        ).data.decode()
        assert "custom range" in html

    def test_last_month_label_is_month_year(self, auth_client):
        # Per spec example, the last-month label is formatted like "Jul 2026".
        # We only assert the format pattern (Mon YYYY) without hardcoding.
        html = auth_client.get("/profile?range=last_month").data.decode()
        # Find the meta-text under Total spent.
        import re
        match = re.search(
            r'<p class="mock-tile-meta">([A-Z][a-z]{2} \d{4})</p>', html
        )
        assert match is not None, (
            f"Expected a 'Mon YYYY' label on Total-spent tile, got HTML: {html[:2000]}"
        )


# ---------------------------------------------------------------------------
# 8. Active-state highlight on preset buttons
# ---------------------------------------------------------------------------

class TestActiveState:
    def _active_button_text(self, html, label):
        """Return True if the button with `label` is the one marked active.

        Preset buttons render as <a ... class="filter-btn{% if ... %} active{% endif %}">Label</a>;
        the "Custom" button is a <button> (it toggles a hidden form) and has
        an inline onclick between the class attribute and the label. We
        therefore search for the label inside any tag that carries both
        "filter-btn" and "active" in its class attribute.
        """
        # Find every tag whose class attribute contains both "filter-btn"
        # and "active", then check whether any of them wraps `label`.
        import re
        active_tag_re = re.compile(
            r'<[a-z]+[^>]*class="[^"]*\bfilter-btn\b[^"]*\bactive\b[^"]*"[^>]*>([^<]*)'
        )
        return any(label in m.group(1) for m in active_tag_re.finditer(html))

    def test_all_time_active_by_default(self, auth_client):
        html = auth_client.get("/profile").data.decode()
        assert self._active_button_text(html, "All time") is True

    def test_this_month_button_is_active_when_selected(self, auth_client):
        html = auth_client.get("/profile?range=this_month").data.decode()
        assert self._active_button_text(html, "This month") is True
        # No other preset should be active.
        for label in ("All time", "Last month", "Last 3 months", "This year", "Custom"):
            if label == "This month":
                continue
            assert self._active_button_text(html, label) is False, (
                f"'{label}' should not be active when this_month is selected"
            )

    def test_last_month_button_is_active_when_selected(self, auth_client):
        html = auth_client.get("/profile?range=last_month").data.decode()
        assert self._active_button_text(html, "Last month") is True
        assert self._active_button_text(html, "All time") is False

    def test_last_3_months_button_is_active_when_selected(self, auth_client):
        html = auth_client.get("/profile?range=last_3_months").data.decode()
        assert self._active_button_text(html, "Last 3 months") is True
        assert self._active_button_text(html, "All time") is False

    def test_this_year_button_is_active_when_selected(self, auth_client):
        html = auth_client.get("/profile?range=this_year").data.decode()
        assert self._active_button_text(html, "This year") is True
        assert self._active_button_text(html, "All time") is False

    def test_custom_button_is_active_when_custom_range_selected(self, auth_client):
        html = auth_client.get(
            "/profile?range=custom&from=2026-01-01&to=2026-12-31"
        ).data.decode()
        assert self._active_button_text(html, "Custom") is True
        assert self._active_button_text(html, "All time") is False

    def test_exactly_one_button_is_active_at_a_time(self, auth_client):
        # Walk through every preset and confirm only one button carries `active`.
        labels = ["All time", "This month", "Last month", "Last 3 months",
                  "This year", "Custom"]
        for preset in ("", "this_month", "last_month", "last_3_months",
                       "this_year", "custom"):
            url = "/profile" if preset == "" else (
                f"/profile?range={preset}"
                if preset != "custom"
                else "/profile?range=custom&from=2026-01-01&to=2026-12-31"
            )
            html = auth_client.get(url).data.decode()
            active_count = sum(
                1 for label in labels if self._active_button_text(html, label)
            )
            assert active_count == 1, (
                f"Expected exactly one active button for preset '{preset}', "
                f"found {active_count}"
            )