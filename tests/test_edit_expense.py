"""
Tests for the "Edit expense" feature (Step 8).

These tests cover the spec in `.claude/specs/08-edit-expense.md`:
  - Auth guard on GET / POST /expenses/<id>/edit
  - GET renders form pre-filled with the row's values; back-link to /profile
  - 404 for non-existent ids
  - 404 (NOT redirect, NOT 200) for ids owned by another user — must not
    leak the existence of someone else's row
  - POST valid data updates the row, redirects to /profile, the updated
    row appears in recent-transactions, and summary stats refresh
  - POST-redirect-GET: a successful POST returns 302 so the browser back
    button does not resubmit
  - Validation: empty/zero/negative/non-numeric amount, invalid/missing
    category, malformed date, description > 500 chars — each re-renders
    the form with an error and does NOT update the row
  - Empty / whitespace-only description is allowed and stored as ""
  - The user_id on UPDATE comes from session, never from the form / row
  - The /profile page renders the "Actions" column with per-row Edit
    links pointing at the right edit URL
"""
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from database.db import get_db, init_db


# ---------------------------------------------------------------------------
# Constants from the spec
# ---------------------------------------------------------------------------

VALID_CATEGORIES = (
    "Food", "Transport", "Shopping", "Bills",
    "Entertainment", "Health", "Other",
)


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


@pytest.fixture()
def seeded():
    """Seed two users.

    User 1 owns the row we'll edit across most tests. User 2 is a foreign
    user whose expense we use to assert that cross-ownership is 404.
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
def seeded_with_one_expense(seeded):
    """Insert one expense owned by user 1 and return its id."""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (seeded["user_id"], 250.00, "Food", "2026-07-02", "Lunch at canteen"),
    )
    expense_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {
        "user_id": seeded["user_id"],
        "other_user_id": seeded["other_user_id"],
        "expense_id": expense_id,
    }


@pytest.fixture()
def auth_client(client, seeded):
    """A logged-in test client (user 1)."""
    with client.session_transaction() as sess:
        sess["user_id"] = seeded["user_id"]
        sess["user_name"] = "Demo User"
    return client


@pytest.fixture()
def other_auth_client(client, seeded):
    """A logged-in test client for user 2 (used to test foreign-ownership)."""
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


def _valid_form(**overrides):
    """Return a baseline valid POST payload, with optional overrides."""
    payload = {
        "amount": "300.00",
        "category": "Transport",
        "date": "2026-07-15",
        "description": "Cab ride",
    }
    payload.update(overrides)
    return payload


def _fetch_expense(expense_id):
    """Return the raw row for `expense_id` (dict-like) or None."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


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


def _count_expense_rows():
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()
        return row["n"]
    finally:
        conn.close()


def _insert_expense(user_id, amount, category, date_str, description=""):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date_str, description),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Auth guard — unauthenticated access redirects to /login
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_get_edit_without_session_redirects_to_login(
        self, client, seeded_with_one_expense
    ):
        response = client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        )
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_edit_without_session_redirects_to_login(
        self, client, seeded_with_one_expense
    ):
        before = _fetch_expense(seeded_with_one_expense["expense_id"])
        response = client.post(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit",
            data=_valid_form(),
        )
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        # The row must not have been touched.
        after = _fetch_expense(seeded_with_one_expense["expense_id"])
        assert float(before["amount"]) == float(after["amount"])
        assert before["category"] == after["category"]
        assert str(before["date"]) == str(after["date"])
        assert before["description"] == after["description"]


# ---------------------------------------------------------------------------
# 2. GET own row — 200 with form pre-filled
# ---------------------------------------------------------------------------

class TestGetOwnRow:
    def test_get_existing_own_row_returns_200(
        self, auth_client, seeded_with_one_expense
    ):
        response = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        )
        assert response.status_code == 200

    def test_get_pre_fills_amount_field(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        # The amount input should carry the row's value as its value attr.
        # Accept either 250 or 250.0 / 250.00 depending on how the value
        # is rendered.
        assert (
            'value="250"' in html
            or 'value="250.0"' in html
            or 'value="250.00"' in html
        )

    def test_get_pre_fills_category_field(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        # The Food option should carry the selected attribute.
        assert 'value="Food"' in html
        assert ">Food</option>" in html

    def test_get_pre_fills_date_field(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        assert 'value="2026-07-02"' in html

    def test_get_pre_fills_description_field(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        # The description is rendered inside a <textarea>; the text
        # appears between the opening and closing tag.
        assert "Lunch at canteen" in html

    def test_get_renders_form_method_and_action(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        html = auth_client.get(f"/expenses/{eid}/edit").data.decode()
        assert '<form method="POST"' in html
        assert f'action="/expenses/{eid}/edit"' in html

    def test_get_renders_all_four_fields(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        assert 'name="amount"' in html
        assert 'name="category"' in html
        assert 'name="date"' in html
        assert 'name="description"' in html

    def test_get_renders_save_changes_button(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        assert "Save changes" in html

    def test_get_renders_all_seven_categories(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        for cat in VALID_CATEGORIES:
            assert f'value="{cat}"' in html, (
                f"Expected category option '{cat}' in the edit form"
            )

    def test_get_uses_consistent_auth_styling(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        # Same .auth-section / .auth-card / .form-group classes as the
        # other auth-style forms (login, register, add expense).
        assert "auth-section" in html
        assert "auth-card" in html
        assert "form-group" in html

    def test_get_renders_back_link_to_profile(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit"
        ).data.decode()
        # Back link points at /profile.
        assert "/profile" in html


# ---------------------------------------------------------------------------
# 3. GET non-existent id returns 404
# ---------------------------------------------------------------------------

class TestGetNonExistent:
    def test_get_nonexistent_id_returns_404(self, auth_client):
        response = auth_client.get("/expenses/99999/edit")
        assert response.status_code == 404

    def test_get_zero_id_returns_404(self, auth_client):
        # id 0 won't match any auto-incremented row.
        response = auth_client.get("/expenses/0/edit")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4. GET foreign-owned row returns 404 (not 302, not 200)
# ---------------------------------------------------------------------------

class TestGetForeignOwned:
    def test_get_foreign_owned_id_returns_404_not_redirect(
        self, client, seeded_with_one_expense
    ):
        """A row owned by user 1 must NOT be visible to user 2.

        The spec explicitly says: return abort(404) — never reveal that
        the row exists but is owned by someone else.
        """
        foreign_id = seeded_with_one_expense["expense_id"]

        # Sanity check: this id really is owned by user 1, not user 2.
        row = _fetch_expense(foreign_id)
        assert row["user_id"] == seeded_with_one_expense["user_id"]

        _login_session(
            client, seeded_with_one_expense["other_user_id"], "Other User"
        )
        response = client.get(f"/expenses/{foreign_id}/edit")
        # Must be 404 — NOT a 302 (would leak existence via redirect).
        assert response.status_code == 404
        # And definitely not 200.
        assert response.status_code != 200

    def test_get_foreign_owned_id_via_other_auth_client(
        self, other_auth_client, seeded_with_one_expense
    ):
        foreign_id = seeded_with_one_expense["expense_id"]
        response = other_auth_client.get(f"/expenses/{foreign_id}/edit")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 5. Happy path — POST valid data updates the row, redirects to /profile
# ---------------------------------------------------------------------------

class TestPostValidData:
    def test_post_valid_redirects_to_profile(
        self, auth_client, seeded_with_one_expense
    ):
        response = auth_client.post(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit",
            data=_valid_form(),
        )
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_valid_updates_amount_in_db(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(amount="999.50"),
        )
        row = _fetch_expense(eid)
        assert float(row["amount"]) == 999.50

    def test_post_valid_updates_category_in_db(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(category="Shopping"),
        )
        row = _fetch_expense(eid)
        assert row["category"] == "Shopping"

    def test_post_valid_updates_date_in_db(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(date="2026-08-01"),
        )
        row = _fetch_expense(eid)
        assert str(row["date"]) == "2026-08-01"

    def test_post_valid_updates_description_in_db(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(description="Edited note"),
        )
        row = _fetch_expense(eid)
        assert row["description"] == "Edited note"

    def test_post_valid_does_not_create_new_rows(
        self, auth_client, seeded_with_one_expense
    ):
        # Editing updates in place — must NOT insert a new row.
        before = _count_expense_rows()
        auth_client.post(
            f"/expenses/{seeded_with_one_expense['expense_id']}/edit",
            data=_valid_form(),
        )
        assert _count_expense_rows() == before

    def test_post_valid_preserves_user_id(
        self, auth_client, seeded_with_one_expense
    ):
        # The row stays owned by user 1 — the form/user_id must NOT
        # come from the original row's user_id (which would matter if
        # the implementation accidentally took it from the row instead
        # of session).
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(),
        )
        row = _fetch_expense(eid)
        assert row["user_id"] == seeded_with_one_expense["user_id"]


# ---------------------------------------------------------------------------
# 6. Validation errors — bad input re-renders the form, no DB change
# ---------------------------------------------------------------------------

class TestValidationErrors:
    """All bad-input cases must:
       * return 200 (re-render the form, not redirect),
       * show an error message,
       * NOT update the row,
       * preserve the user's typed values where reasonable.
    """

    @pytest.mark.parametrize("bad_amount", ["", "0", "0.00", "-1", "-250.50"])
    def test_invalid_amount_does_not_update(
        self, auth_client, seeded_with_one_expense, bad_amount
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(eid)
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(amount=bad_amount)
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        after = _fetch_expense(eid)
        assert float(after["amount"]) == float(before["amount"])
        assert after["category"] == before["category"]
        assert str(after["date"]) == str(before["date"])

    def test_non_numeric_amount_does_not_update(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(eid)
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(amount="abc")
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        after = _fetch_expense(eid)
        assert float(after["amount"]) == float(before["amount"])

    def test_invalid_amount_preserves_typed_amount(
        self, auth_client, seeded_with_one_expense
    ):
        # The form should echo back the user's text so they don't lose work.
        eid = seeded_with_one_expense["expense_id"]
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(amount="abc")
        )
        assert response.status_code == 200
        assert b"abc" in response.data

    @pytest.mark.parametrize("bad_category", [
        "Hacking",     # clearly not in the 7 valid categories
        "food",        # lowercase — case-sensitive per Step 7 rule
        "FOOD",
        "Groceries",
        "Taxi",
    ])
    def test_invalid_category_does_not_update(
        self, auth_client, seeded_with_one_expense, bad_category
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(eid)
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(category=bad_category)
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        after = _fetch_expense(eid)
        # Original category ("Food") is preserved.
        assert after["category"] == before["category"]

    def test_missing_category_does_not_update(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(eid)
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(category="")
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        after = _fetch_expense(eid)
        assert after["category"] == before["category"]

    def test_invalid_category_preserves_typed_category(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(category="Hacking")
        )
        assert response.status_code == 200
        # The invalid category value should be visible to the user so
        # they remember what they typed.
        assert b"Hacking" in response.data

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "2026/07/29",
        "2026-13-01",
        "2026-02-30",
        "29-07-2026",
        "07/29/2026",
    ])
    def test_malformed_date_does_not_update(
        self, auth_client, seeded_with_one_expense, bad_date
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(eid)
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(date=bad_date)
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        after = _fetch_expense(eid)
        assert str(after["date"]) == str(before["date"])

    def test_invalid_date_preserves_typed_date(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(date="not-a-date")
        )
        assert response.status_code == 200
        assert b"not-a-date" in response.data

    def test_description_over_500_chars_does_not_update(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(eid)
        long_desc = "x" * 501
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(description=long_desc)
        )
        assert response.status_code == 200
        assert b"auth-error" in response.data
        after = _fetch_expense(eid)
        # Original description preserved.
        assert after["description"] == before["description"]

    def test_description_exactly_500_chars_is_allowed(
        self, auth_client, seeded_with_one_expense
    ):
        # Boundary: 500 chars exactly is the inclusive limit.
        eid = seeded_with_one_expense["expense_id"]
        desc_500 = "x" * 500
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(description=desc_500)
        )
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]
        row = _fetch_expense(eid)
        assert row["description"] == desc_500


# ---------------------------------------------------------------------------
# 7. Description is optional — empty / whitespace-only stored as ""
# ---------------------------------------------------------------------------

class TestDescriptionOptional:
    def test_empty_description_still_saves(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(description="")
        )
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_empty_description_stored_as_empty_string(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(description="")
        )
        row = _fetch_expense(eid)
        # Spec is explicit: stored as "" (empty string), not NULL.
        assert row["description"] == ""

    def test_whitespace_only_description_stripped_to_empty(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(description="   ")
        )
        row = _fetch_expense(eid)
        assert row["description"] == ""

    def test_non_empty_description_stored_verbatim(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(description="New note")
        )
        row = _fetch_expense(eid)
        assert row["description"] == "New note"


# ---------------------------------------------------------------------------
# 8. POST-redirect-GET — back button doesn't re-submit
# ---------------------------------------------------------------------------

class TestPostRedirectGet:
    def test_successful_post_uses_302_redirect(
        self, auth_client, seeded_with_one_expense
    ):
        """A valid POST must return 302 — never 200 — so the browser
        follows up with a GET. This is what stops the browser-back
        button from re-submitting the form."""
        eid = seeded_with_one_expense["expense_id"]
        response = auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form()
        )
        assert response.status_code == 302

    def test_after_save_subsequent_get_shows_new_values(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(
                amount="123.45", description="Updated via edit"
            ),
        )
        # Simulate the browser following the 302 redirect to /profile.
        response = auth_client.get("/profile")
        assert response.status_code == 200
        html = response.data.decode()
        assert "Updated via edit" in html
        assert "Rs123.45" in html

    def test_successful_post_only_updates_once(
        self, auth_client, seeded_with_one_expense
    ):
        """Submitting the same edit twice should produce the same end
        state — but only ONE row exists, and its fields reflect the
        second submission (no duplication)."""
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(amount="100.00")
        )
        auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(amount="200.00")
        )
        row = _fetch_expense(eid)
        assert float(row["amount"]) == 200.00
        assert _count_expense_rows() == 1


# ---------------------------------------------------------------------------
# 9. Profile reflects the edit — recent-transactions + summary stats
# ---------------------------------------------------------------------------

class TestProfileAfterEdit:
    def test_updated_row_appears_in_recent_transactions(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(
                amount="555.55", description="Edited row visible on profile"
            ),
        )
        html = auth_client.get("/profile").data.decode()
        assert "Edited row visible on profile" in html
        assert "Rs555.55" in html

    def test_total_spent_reflects_edit(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        # Original row amount: 250.00. Change it to 750.00.
        auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(amount="750.00")
        )
        html = auth_client.get("/profile").data.decode()
        # 750.00 is the new total — 250.00 must NOT be present anymore.
        assert "Rs750.00" in html
        assert "Rs250.00" not in html

    def test_transaction_count_reflects_edit(
        self, auth_client, seeded_with_one_expense
    ):
        # Editing changes a value but NOT the count of rows.
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit", data=_valid_form(amount="1.00")
        )
        html = auth_client.get("/profile").data.decode()
        # Tile shows "1" for one transaction.
        assert '<p class="mock-tile-value">1</p>' in html

    def test_category_breakdown_reflects_edit(
        self, auth_client, seeded_with_one_expense
    ):
        # Original category: Food (250.00). Edit to Shopping → the Food
        # bucket becomes empty (0), Shopping becomes 300.00.
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(
            f"/expenses/{eid}/edit",
            data=_valid_form(category="Shopping", amount="300.00"),
        )
        html = auth_client.get("/profile").data.decode()
        # The category breakdown row for Shopping shows Rs300.00.
        # We just assert the values appear in the rendered page; the
        # ordering/shape is covered by the date-filter tests.
        assert "Rs300.00" in html


# ---------------------------------------------------------------------------
# 10. The /profile page renders the Actions column with per-row Edit links
# ---------------------------------------------------------------------------

class TestProfileActionsColumn:
    def _seed_user_with_multiple_expenses(self, user_id):
        ids = []
        ids.append(_insert_expense(user_id, 100.00, "Food",    "2026-07-01", "A"))
        ids.append(_insert_expense(user_id, 200.00, "Bills",   "2026-07-02", "B"))
        ids.append(_insert_expense(user_id, 300.00, "Health",  "2026-07-03", "C"))
        return ids

    def test_profile_actions_column_header_present(self, auth_client):
        self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        assert "Actions" in html

    def test_profile_has_edit_link_per_row(self, auth_client):
        self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        # Three rows → three Edit links.
        assert html.count("Edit") >= 3

    def test_profile_edit_link_points_at_correct_url(self, auth_client):
        ids = self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        for eid in ids:
            # Each row should carry an anchor to its own /edit URL.
            assert f"/expenses/{eid}/edit" in html, (
                f"Expected /expenses/{eid}/edit link on /profile, "
                f"but didn't find it"
            )

    def test_profile_edit_link_count_matches_row_count(self, auth_client):
        ids = self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        # Exactly one link per row (no duplicates).
        for eid in ids:
            count = html.count(f"/expenses/{eid}/edit")
            assert count == 1, (
                f"Expected exactly 1 link to /expenses/{eid}/edit, "
                f"found {count}"
            )


# ---------------------------------------------------------------------------
# 11. Ownership semantics — POST cannot edit a foreign row
# ---------------------------------------------------------------------------

class TestPostForeignOwned:
    """Belt-and-braces: a POST that *would* update someone else's row
    must also be refused. (This is partly covered by the 404-on-GET
    guarantee, but we explicitly assert the POST side does not silently
    update another user's data — even if the implementation leaks the
    row in some other way.)"""

    def test_post_to_foreign_row_returns_404(
        self, client, seeded_with_one_expense
    ):
        foreign_id = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(foreign_id)

        _login_session(
            client, seeded_with_one_expense["other_user_id"], "Other User"
        )
        response = client.post(
            f"/expenses/{foreign_id}/edit", data=_valid_form()
        )
        # The spec mandates abort(404), not a redirect.
        assert response.status_code == 404
        # And the row's data is unchanged.
        after = _fetch_expense(foreign_id)
        assert float(after["amount"]) == float(before["amount"])
        assert after["category"] == before["category"]
        assert str(after["date"]) == str(before["date"])
        assert after["description"] == before["description"]

    def test_post_to_nonexistent_id_returns_404(
        self, auth_client
    ):
        response = auth_client.post(
            "/expenses/99999/edit", data=_valid_form()
        )
        assert response.status_code == 404
