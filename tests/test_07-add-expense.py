"""
Tests for the "Add expense" feature (Step 7).

These tests cover the spec in `.claude/specs/07-add-expense.md`:
  - Auth guard on GET / POST /expenses/add (logged-out users redirected)
  - GET renders the form with today's date pre-filled and the 7 fixed
    categories, and the "Add expense" nav link is visible
  - POST with all 4 fields inserts a row tied to the session user, redirects
    to /profile, and the new row appears at the top of recent-transactions
    with updated summary stats (total + count)
  - Validation errors (empty / non-positive / non-numeric amount, invalid /
    missing category, malformed date) re-render the form with the user's
    input preserved and do NOT insert a row
  - Empty description is allowed and stored as ""
  - The user_id is taken from session, never from the form
  - The "Add expense" nav link only appears for logged-in users
"""
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from database.db import get_db, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CATEGORIES = (
    "Food", "Transport", "Shopping", "Bills",
    "Entertainment", "Health", "Other",
)


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


@pytest.fixture()
def seeded():
    """Seed two demo users.

    User 1 has no expenses (for clean "summary before vs. after" math).
    User 2 is an alternate user used to verify the row is tied to the
    SESSION user, not any form field.
    """
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
        (2, "Other User", "other@spendly.com",
         generate_password_hash("demo123"), "2026-01-15 10:30:00"),
    )
    conn.commit()
    conn.close()
    return {"user_id": 1, "other_user_id": 2}


@pytest.fixture()
def auth_client(client, seeded):
    """A logged-in test client (user 1, no expenses)."""
    with client.session_transaction() as sess:
        sess["user_id"] = seeded["user_id"]
        sess["user_name"] = "Demo User"
    return client


@pytest.fixture()
def other_auth_client(client, seeded):
    """A logged-in test client for the second user."""
    with client.session_transaction() as sess:
        sess["user_id"] = seeded["other_user_id"]
        sess["user_name"] = "Other User"
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login_session(client, user_id, name):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = name


def _count_expenses_for_user(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def _fetch_expense_by_any(user_id):
    """Return the most recently inserted expense for a user."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def _valid_form(**overrides):
    """Return a baseline valid POST payload, with optional overrides."""
    today = date.today().isoformat()
    payload = {
        "amount": "250.00",
        "category": "Food",
        "date": today,
        "description": "Lunch at canteen",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1. Auth guard — unauthenticated access redirects to /login
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_get_expenses_add_without_session_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_expenses_add_without_session_redirects_to_login(self, client, seeded):
        # No row should be inserted even though the body is "valid".
        before = _count_expenses_for_user(seeded["user_id"])
        response = client.post("/expenses/add", data=_valid_form())
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _count_expenses_for_user(seeded["user_id"]) == before


# ---------------------------------------------------------------------------
# 2. GET /expenses/add renders the form when logged in
# ---------------------------------------------------------------------------

class TestFormRendering:
    def test_get_returns_200_when_logged_in(self, auth_client):
        response = auth_client.get("/expenses/add")
        assert response.status_code == 200

    def test_get_renders_form(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode()
        assert '<form method="POST"' in html
        assert 'action="/expenses/add"' in html
        # All four fields are present.
        assert 'name="amount"' in html
        assert 'name="category"' in html
        assert 'name="date"' in html
        assert 'name="description"' in html

    def test_get_pre_fills_today_date(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode()
        today_iso = date.today().isoformat()
        # The date input must carry today's date as its value attribute.
        assert f'value="{today_iso}"' in html

    def test_get_renders_all_seven_categories(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode()
        for cat in VALID_CATEGORIES:
            # Categories are rendered as <option value="..."> inside the select.
            assert f'value="{cat}"' in html, (
                f"Expected category option '{cat}' in the form"
            )

    def test_get_does_not_contain_unknown_categories(self, auth_client):
        # Belt-and-braces: confirm a clearly bogus name is NOT in the form.
        html = auth_client.get("/expenses/add").data.decode()
        assert "Hacking" not in html
        assert "Insurance" not in html

    def test_get_has_save_expense_submit_button(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode()
        assert "Save expense" in html
        assert 'type="submit"' in html

    def test_get_renders_consistent_auth_styling(self, auth_client):
        # The form should reuse the same styling classes as login/register.
        html = auth_client.get("/expenses/add").data.decode()
        assert "auth-section" in html
        assert "auth-card" in html
        assert "form-group" in html

    def test_get_renders_back_link_to_profile(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode()
        assert "/profile" in html


# ---------------------------------------------------------------------------
# 3. Happy path — POST creates the row and redirects to /profile
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_post_with_all_fields_redirects_to_profile(self, auth_client, seeded):
        response = auth_client.post("/expenses/add", data=_valid_form())
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_inserts_row_in_db(self, auth_client, seeded):
        before = _count_expenses_for_user(seeded["user_id"])
        auth_client.post("/expenses/add", data=_valid_form())
        after = _count_expenses_for_user(seeded["user_id"])
        assert after == before + 1

    def test_post_inserted_row_has_correct_fields(self, auth_client, seeded):
        auth_client.post("/expenses/add", data=_valid_form(
            amount="999.50",
            category="Transport",
            date="2026-07-20",
            description="Cab ride to airport",
        ))
        row = _fetch_expense_by_any(seeded["user_id"])
        assert row is not None
        assert row["user_id"] == seeded["user_id"]
        assert float(row["amount"]) == 999.50
        assert row["category"] == "Transport"
        # SQLite stores date as TEXT in YYYY-MM-DD form.
        assert str(row["date"]) == "2026-07-20"
        assert row["description"] == "Cab ride to airport"

    def test_post_appears_at_top_of_recent_transactions(self, auth_client, seeded):
        auth_client.post("/expenses/add", data=_valid_form(
            amount="123.45",
            category="Food",
            date="2026-07-29",
            description="A new spend",
        ))
        html = auth_client.get("/profile").data.decode()
        # The new row should appear in the recent-transactions table.
        assert "A new spend" in html
        assert "Rs123.45" in html
        # Since we ordered by date DESC, id DESC, and no later-dated rows
        # exist, the new row is the first transaction row.
        # The description appears before the txn table closes — assert it
        # appears before the table closing tag.
        idx = html.find("A new spend")
        idx_close = html.find("</tbody>")
        assert idx != -1 and idx_close != -1 and idx < idx_close

    def test_post_summary_total_spent_increases(self, auth_client, seeded):
        # No expenses yet — baseline total is 0.00.
        before_html = auth_client.get("/profile").data.decode()
        assert "Rs0.00" in before_html

        auth_client.post("/expenses/add", data=_valid_form(amount="500.00"))
        after_html = auth_client.get("/profile").data.decode()
        assert "Rs500.00" in after_html

    def test_post_summary_transaction_count_increases(self, auth_client, seeded):
        # No expenses yet — transaction count is 0.
        before_html = auth_client.get("/profile").data.decode()
        assert '<p class="mock-tile-value">0</p>' in before_html

        auth_client.post("/expenses/add", data=_valid_form())
        after_html = auth_client.get("/profile").data.decode()
        # After insert, transaction count tile is 1.
        assert '<p class="mock-tile-value">1</p>' in after_html

    def test_post_two_expenses_sum_total(self, auth_client, seeded):
        # Baseline 0.00
        auth_client.post("/expenses/add", data=_valid_form(amount="100.00"))
        auth_client.post("/expenses/add", data=_valid_form(amount="250.50"))
        after_html = auth_client.get("/profile").data.decode()
        assert "Rs350.50" in after_html

    def test_post_redirect_uses_post_redirect_get(self, auth_client, seeded):
        """A valid POST must return 302, not 200, so the browser follows
        up with a GET — preventing the browser-back resubmit pitfall."""
        response = auth_client.post("/expenses/add", data=_valid_form())
        assert response.status_code == 302
        # And only ONE row was inserted.
        assert _count_expenses_for_user(seeded["user_id"]) == 1


# ---------------------------------------------------------------------------
# 4. Validation errors — bad input re-renders the form, inserts nothing
# ---------------------------------------------------------------------------

class TestValidationErrors:
    """All bad-input cases must:
       * return 200 (re-render the form, not redirect),
       * show an error message,
       * NOT insert a row,
       * preserve the user's typed values so they don't lose work.
    """

    def _assert_no_row_inserted(self, user_id):
        assert _count_expenses_for_user(user_id) == 0

    @pytest.mark.parametrize("bad_amount", ["", "0", "0.00", "-1", "-250.50"])
    def test_invalid_amount_does_not_insert(self, auth_client, seeded, bad_amount):
        response = auth_client.post("/expenses/add", data=_valid_form(amount=bad_amount))
        assert response.status_code == 200
        assert b"auth-error" in response.data
        self._assert_no_row_inserted(seeded["user_id"])

    def test_invalid_amount_preserves_amount_field(self, auth_client):
        # The form should echo back the user's text so they don't lose work.
        response = auth_client.post("/expenses/add", data=_valid_form(amount="abc"))
        assert response.status_code == 200
        assert b"abc" in response.data

    def test_non_numeric_amount_does_not_insert(self, auth_client, seeded):
        response = auth_client.post("/expenses/add", data=_valid_form(amount="abc"))
        assert response.status_code == 200
        assert b"auth-error" in response.data
        self._assert_no_row_inserted(seeded["user_id"])

    @pytest.mark.parametrize("bad_category", [
        "Hacking",     # clearly not in the 7 valid categories
        "food",        # lowercase — case-sensitive
        "FOOD",
        "Groceries",
        "Taxi",
    ])
    def test_invalid_category_does_not_insert(self, auth_client, seeded, bad_category):
        response = auth_client.post(
            "/expenses/add", data=_valid_form(category=bad_category)
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        self._assert_no_row_inserted(seeded["user_id"])

    def test_missing_category_does_not_insert(self, auth_client, seeded):
        # Empty string — must be rejected server-side, not just by the
        # HTML `required` attribute.
        response = auth_client.post(
            "/expenses/add", data=_valid_form(category="")
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        self._assert_no_row_inserted(seeded["user_id"])

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "2026/07/29",
        "2026-13-01",
        "2026-02-30",
        "29-07-2026",
        "07/29/2026",
    ])
    def test_malformed_date_does_not_insert(self, auth_client, seeded, bad_date):
        response = auth_client.post("/expenses/add", data=_valid_form(date=bad_date))
        assert response.status_code == 200
        assert b"auth-error" in response.data
        self._assert_no_row_inserted(seeded["user_id"])

    def test_invalid_input_preserves_date_field(self, auth_client):
        # If the user typed a bad date, the form re-renders must keep it.
        response = auth_client.post(
            "/expenses/add", data=_valid_form(date="not-a-date")
        )
        assert response.status_code == 200
        assert b"not-a-date" in response.data

    def test_invalid_input_preserves_description_field(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data=_valid_form(amount="0", description="preserve this note text"),
        )
        assert response.status_code == 200
        assert b"preserve this note text" in response.data

    def test_invalid_input_preserves_category_field(self, auth_client):
        response = auth_client.post(
            "/expenses/add", data=_valid_form(category="Hacking")
        )
        assert response.status_code == 200
        # The invalid category value should be re-rendered into the form.
        assert b"Hacking" in response.data


# ---------------------------------------------------------------------------
# 5. Description is optional — empty string is a valid submission
# ---------------------------------------------------------------------------

class TestDescriptionOptional:
    def test_empty_description_still_saves(self, auth_client, seeded):
        response = auth_client.post(
            "/expenses/add",
            data=_valid_form(description=""),
        )
        assert response.status_code == 302
        assert _count_expenses_for_user(seeded["user_id"]) == 1

    def test_empty_description_stored_as_empty_string(self, auth_client, seeded):
        auth_client.post(
            "/expenses/add",
            data=_valid_form(description=""),
        )
        row = _fetch_expense_by_any(seeded["user_id"])
        assert row is not None
        # Spec says: stored as "" (empty string), not NULL.
        assert row["description"] == ""

    def test_whitespace_only_description_is_stripped_to_empty(self, auth_client, seeded):
        """A description of only spaces is functionally empty and should
        be stored as an empty string."""
        auth_client.post(
            "/expenses/add",
            data=_valid_form(description="   "),
        )
        row = _fetch_expense_by_any(seeded["user_id"])
        assert row is not None
        assert row["description"] == ""

    def test_non_empty_description_stored_verbatim(self, auth_client, seeded):
        auth_client.post(
            "/expenses/add",
            data=_valid_form(description="Coffee with team"),
        )
        row = _fetch_expense_by_any(seeded["user_id"])
        assert row["description"] == "Coffee with team"


# ---------------------------------------------------------------------------
# 6. user_id is read from session, not from any form value
# ---------------------------------------------------------------------------

class TestSessionDrivenUserId:
    def test_logged_in_user_1_sees_own_row(self, auth_client, seeded):
        auth_client.post("/expenses/add", data=_valid_form(amount="100.00"))
        assert _count_expenses_for_user(seeded["user_id"]) == 1
        assert _count_expenses_for_user(seeded["other_user_id"]) == 0

    def test_logged_in_user_2_sees_own_row(self, other_auth_client, seeded):
        other_auth_client.post(
            "/expenses/add", data=_valid_form(amount="200.00")
        )
        assert _count_expenses_for_user(seeded["other_user_id"]) == 1
        assert _count_expenses_for_user(seeded["user_id"]) == 0

    def test_posted_row_user_id_matches_session(self, auth_client, seeded):
        auth_client.post("/expenses/add", data=_valid_form())
        row = _fetch_expense_by_any(seeded["user_id"])
        assert row["user_id"] == seeded["user_id"]

    def test_switching_session_user_inserts_under_new_user(self, client, seeded):
        """Same client, but two separate sessions — each POST is tied to
        the session user at the time of the request."""
        _login_session(client, seeded["user_id"], "Demo User")
        client.post("/expenses/add", data=_valid_form(amount="10.00"))

        _login_session(client, seeded["other_user_id"], "Other User")
        client.post("/expenses/add", data=_valid_form(amount="20.00"))

        assert _count_expenses_for_user(seeded["user_id"]) == 1
        assert _count_expenses_for_user(seeded["other_user_id"]) == 1

        # And the distribution by user is correct.
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT user_id, amount FROM expenses ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert rows[0]["user_id"] == seeded["user_id"]
        assert float(rows[0]["amount"]) == 10.00
        assert rows[1]["user_id"] == seeded["other_user_id"]
        assert float(rows[1]["amount"]) == 20.00


# ---------------------------------------------------------------------------
# 7. "Add expense" nav link is visible only for logged-in users
# ---------------------------------------------------------------------------

class TestNavLink:
    def test_nav_link_visible_for_logged_in_user(self, auth_client):
        html = auth_client.get("/profile").data.decode()
        assert "Add expense" in html
        # And it must actually link to the add-expense route.
        assert '/expenses/add' in html

    def test_nav_link_visible_on_add_expense_page(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode()
        assert "Add expense" in html
        assert '/expenses/add' in html

    def test_nav_link_absent_for_logged_out_user(self, client):
        html = client.get("/").data.decode()
        # Landing page when logged out — no Add expense link.
        assert "Add expense" not in html

    def test_nav_link_absent_on_login_page(self, client):
        html = client.get("/login").data.decode()
        assert "Add expense" not in html

    def test_nav_link_absent_on_register_page(self, client):
        html = client.get("/register").data.decode()
        assert "Add expense" not in html
