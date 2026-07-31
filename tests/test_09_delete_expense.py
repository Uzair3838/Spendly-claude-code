"""
Tests for the "Delete expense" feature (Step 9).

These tests cover the spec in `.claude/specs/09-delete-expense.md`:
  - Auth guard on GET / POST /expenses/<id>/delete
  - GET renders the confirmation page showing the row's date, description,
    amount, category (chip); DB row is NOT deleted
  - POST deletes the row, redirects to /profile; the row is gone from
    `expenses`; profile stats reflect the deletion (total down, count down,
    category breakdown updated); recent-transactions no longer shows the row
  - 404 for non-existent ids (both GET and POST)
  - 404 for ids owned by another user (both GET and POST); POST must not
    silently delete the foreign row
  - If the session user has been deleted under an active session, both
    GET and POST drop the session and redirect to /login (no crash)
  - POST-redirect-GET: a successful POST returns 302 (not 200), so the
    browser back button does not re-trigger
  - The /profile page renders a "Delete" link per row pointing at the
    correct delete URL
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

    User 1 owns the row we'll delete across most tests. User 2 is a
    foreign user whose expense we use to assert cross-ownership is 404.
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


def _fetch_expense(expense_id):
    """Return the raw row for `expense_id` (dict-like) or None."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


def _count_expense_rows():
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()
        return row["n"]
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


def _delete_session_user(user_id):
    """Wipe a user from the DB while keeping their session cookie alive.

    Foreign-key cascade (if enabled) may also remove their expenses; the
    test that uses this fixture must be defensive about that.
    """
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 1. Auth guard — unauthenticated access redirects to /login
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_get_delete_without_session_redirects_to_login(
        self, client, seeded_with_one_expense
    ):
        response = client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        )
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_delete_without_session_redirects_to_login(
        self, client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(eid)
        response = client.post(f"/expenses/{eid}/delete")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        # The row must not have been touched.
        after = _fetch_expense(eid)
        assert before is not None
        assert after is not None
        assert float(before["amount"]) == float(after["amount"])


# ---------------------------------------------------------------------------
# 2. GET own row — confirmation page rendered, DB row NOT deleted
# ---------------------------------------------------------------------------

class TestGetOwnRow:
    def test_get_existing_own_row_returns_200(
        self, auth_client, seeded_with_one_expense
    ):
        response = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        )
        assert response.status_code == 200

    def test_get_renders_confirmation_header(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        assert "Delete expense" in html
        # The spec's subtitle is a short warning like "This cannot be undone".
        assert "cannot be undone" in html

    def test_get_renders_row_date(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        # Date is rendered in YYYY-MM-DD form.
        assert "2026-07-02" in html

    def test_get_renders_row_description(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        assert "Lunch at canteen" in html

    def test_get_renders_row_amount_formatted(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        # Spec: formatted as Rs{:,.2f} — 250.00 → Rs250.00.
        assert "Rs250.00" in html

    def test_get_renders_row_category_as_chip(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        # Category chip uses .cat-badge.cat-<name> classes — must match
        # the profile table styling.
        assert "cat-badge" in html
        assert "cat-food" in html
        assert "Food" in html

    def test_get_renders_confirm_form_post_to_same_url(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        html = auth_client.get(f"/expenses/{eid}/delete").data.decode()
        # The form is POST-only and points back at the same delete URL.
        assert '<form method="POST"' in html
        assert f'action="/expenses/{eid}/delete"' in html

    def test_get_renders_confirm_submit_button(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        assert "Yes, delete" in html
        assert 'type="submit"' in html

    def test_get_renders_cancel_link(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        # Cancel is an anchor, not a button — and must point at /profile.
        assert "Cancel" in html
        # Must include a link to /profile.
        assert 'href="/profile"' in html

    def test_get_renders_back_link_to_profile(
        self, auth_client, seeded_with_one_expense
    ):
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        assert "Back to profile" in html

    def test_get_uses_consistent_auth_styling(
        self, auth_client, seeded_with_one_expense
    ):
        # Spec: reuses .auth-section / .auth-container / .auth-card so
        # the page looks consistent with add/edit.
        html = auth_client.get(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        ).data.decode()
        assert "auth-section" in html
        assert "auth-card" in html

    def test_get_does_not_delete_row(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _count_expense_rows()
        auth_client.get(f"/expenses/{eid}/delete")
        # GET is render-only — must NOT delete.
        assert _count_expense_rows() == before
        row = _fetch_expense(eid)
        assert row is not None


# ---------------------------------------------------------------------------
# 3. GET non-existent id returns 404
# ---------------------------------------------------------------------------

class TestGetNonExistent:
    def test_get_nonexistent_id_returns_404(self, auth_client):
        response = auth_client.get("/expenses/99999/delete")
        assert response.status_code == 404

    def test_get_zero_id_returns_404(self, auth_client):
        # id 0 won't match any auto-incremented row.
        response = auth_client.get("/expenses/0/delete")
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
        response = client.get(f"/expenses/{foreign_id}/delete")
        # Must be 404 — NOT a 302 (would leak existence via redirect).
        assert response.status_code == 404
        # And definitely not 200.
        assert response.status_code != 200

    def test_get_foreign_owned_id_via_other_auth_client(
        self, other_auth_client, seeded_with_one_expense
    ):
        foreign_id = seeded_with_one_expense["expense_id"]
        response = other_auth_client.get(f"/expenses/{foreign_id}/delete")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 5. POST non-existent id returns 404
# ---------------------------------------------------------------------------

class TestPostNonExistent:
    def test_post_nonexistent_id_returns_404(self, auth_client):
        response = auth_client.post("/expenses/99999/delete")
        assert response.status_code == 404

    def test_post_zero_id_returns_404(self, auth_client):
        response = auth_client.post("/expenses/0/delete")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 6. POST foreign-owned id returns 404 AND row is untouched
# ---------------------------------------------------------------------------

class TestPostForeignOwned:
    """Belt-and-braces: a POST that *would* delete someone else's row must
    be refused. The DELETE in the implementation filters on user_id (defence
    in depth), but the GET's ownership check is the primary gate. We assert
    both: the response is 404 and the foreign row is unchanged."""

    def test_post_to_foreign_row_returns_404(
        self, client, seeded_with_one_expense
    ):
        foreign_id = seeded_with_one_expense["expense_id"]
        before = _fetch_expense(foreign_id)
        assert before is not None

        _login_session(
            client, seeded_with_one_expense["other_user_id"], "Other User"
        )
        response = client.post(f"/expenses/{foreign_id}/delete")
        # The spec mandates abort(404), not a redirect.
        assert response.status_code == 404

    def test_post_to_foreign_row_does_not_delete(
        self, client, seeded_with_one_expense
    ):
        foreign_id = seeded_with_one_expense["expense_id"]
        before_total = _count_expense_rows()

        _login_session(
            client, seeded_with_one_expense["other_user_id"], "Other User"
        )
        client.post(f"/expenses/{foreign_id}/delete")

        # The foreign row must still exist.
        after = _fetch_expense(foreign_id)
        assert after is not None, "POST to foreign row must not delete"
        # Total row count unchanged.
        assert _count_expense_rows() == before_total

    def test_post_to_foreign_row_via_other_auth_client(
        self, other_auth_client, seeded_with_one_expense
    ):
        foreign_id = seeded_with_one_expense["expense_id"]
        response = other_auth_client.post(f"/expenses/{foreign_id}/delete")
        assert response.status_code == 404
        assert _fetch_expense(foreign_id) is not None


# ---------------------------------------------------------------------------
# 7. Happy path — POST deletes the row and redirects to /profile
# ---------------------------------------------------------------------------

class TestPostHappyPath:
    def test_post_valid_redirects_to_profile(
        self, auth_client, seeded_with_one_expense
    ):
        response = auth_client.post(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        )
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_valid_redirect_location_ends_with_profile(
        self, auth_client, seeded_with_one_expense
    ):
        response = auth_client.post(
            f"/expenses/{seeded_with_one_expense['expense_id']}/delete"
        )
        # Spec: redirect to /profile (no query string).
        location = response.headers["Location"]
        assert location.endswith("/profile")
        assert "?" not in location

    def test_post_deletes_row_from_db(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        # Sanity check: row exists before delete.
        assert _fetch_expense(eid) is not None
        auth_client.post(f"/expenses/{eid}/delete")
        # After delete: row is gone.
        assert _fetch_expense(eid) is None

    def test_post_decrements_total_row_count(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _count_expense_rows()
        auth_client.post(f"/expenses/{eid}/delete")
        assert _count_expense_rows() == before - 1

    def test_post_decrements_user_row_count(
        self, auth_client, seeded_with_one_expense
    ):
        eid = seeded_with_one_expense["expense_id"]
        before = _count_expenses_for_user(
            seeded_with_one_expense["user_id"]
        )
        auth_client.post(f"/expenses/{eid}/delete")
        assert _count_expenses_for_user(
            seeded_with_one_expense["user_id"]
        ) == before - 1


# ---------------------------------------------------------------------------
# 8. Profile reflects the deletion — stats + recent-transactions
# ---------------------------------------------------------------------------

class TestProfileAfterDelete:
    """The profile page must refresh after a delete: total spent, count,
    category breakdown, and recent-transactions list all reflect the
    removal."""

    def _seed_multiple_expenses(self, user_id):
        ids = {}
        ids["food_100"] = _insert_expense(
            user_id, 100.00, "Food", "2026-07-01", "Breakfast"
        )
        ids["bills_500"] = _insert_expense(
            user_id, 500.00, "Bills", "2026-07-02", "Electricity"
        )
        ids["food_50"] = _insert_expense(
            user_id, 50.00, "Food", "2026-07-03", "Snack"
        )
        return ids

    def test_total_spent_decreases_after_delete(
        self, auth_client, seeded
    ):
        ids = self._seed_multiple_expenses(seeded["user_id"])

        # Baseline: 100 + 500 + 50 = Rs650.00.
        baseline_html = auth_client.get("/profile").data.decode()
        assert "Rs650.00" in baseline_html

        # Delete the Food/100 row — new total should be Rs550.00.
        auth_client.post(f"/expenses/{ids['food_100']}/delete")
        after_html = auth_client.get("/profile").data.decode()
        assert "Rs550.00" in after_html
        assert "Rs650.00" not in after_html

    def test_transaction_count_decreases_after_delete(
        self, auth_client, seeded
    ):
        ids = self._seed_multiple_expenses(seeded["user_id"])

        # Baseline: 3 transactions.
        baseline_html = auth_client.get("/profile").data.decode()
        assert '<p class="mock-tile-value">3</p>' in baseline_html

        auth_client.post(f"/expenses/{ids['bills_500']}/delete")
        after_html = auth_client.get("/profile").data.decode()
        assert '<p class="mock-tile-value">2</p>' in after_html

    def test_deleted_row_no_longer_in_recent_transactions(
        self, auth_client, seeded
    ):
        ids = self._seed_multiple_expenses(seeded["user_id"])

        baseline_html = auth_client.get("/profile").data.decode()
        # Baseline includes all three descriptions.
        assert "Breakfast" in baseline_html
        assert "Electricity" in baseline_html
        assert "Snack" in baseline_html

        # Delete the Electricity row.
        auth_client.post(f"/expenses/{ids['bills_500']}/delete")
        after_html = auth_client.get("/profile").data.decode()
        # The deleted row's description is gone.
        assert "Electricity" not in after_html
        # And the remaining two are still present.
        assert "Breakfast" in after_html
        assert "Snack" in after_html

    def test_category_breakdown_updates_after_delete(
        self, auth_client, seeded
    ):
        """Delete the only row in a category; the breakdown must no
        longer list that category."""
        ids = self._seed_multiple_expenses(seeded["user_id"])

        # Delete the only Bills row — Bills must disappear from the
        # breakdown; Food (100 + 50 = 150) remains.
        auth_client.post(f"/expenses/{ids['bills_500']}/delete")
        after_html = auth_client.get("/profile").data.decode()

        # The breakdown row for "Bills" is gone.
        # The remaining Food total (Rs150.00) still shows.
        assert "Rs150.00" in after_html
        assert "Rs500.00" not in after_html

    def test_top_category_updates_after_delete(
        self, auth_client, seeded
    ):
        """After deleting the largest category's only row, top_category
        must change to the next-largest category."""
        # Setup: Bills 500 (top), Food 100, Transport 50.
        bills_id = _insert_expense(
            seeded["user_id"], 500.00, "Bills", "2026-07-01", "Electricity"
        )
        _insert_expense(
            seeded["user_id"], 100.00, "Food", "2026-07-02", "Breakfast"
        )
        _insert_expense(
            seeded["user_id"], 50.00, "Transport", "2026-07-03", "Cab"
        )

        baseline_html = auth_client.get("/profile").data.decode()
        assert "Top category" in baseline_html

        auth_client.post(f"/expenses/{bills_id}/delete")
        # After delete, no crash on /profile.
        response = auth_client.get("/profile")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 9. POST-redirect-GET — back button does NOT re-delete
# ---------------------------------------------------------------------------

class TestPostRedirectGet:
    def test_successful_post_uses_302_redirect(
        self, auth_client, seeded_with_one_expense
    ):
        """A valid POST must return 302 — never 200 — so the browser
        follows up with a GET. This is what stops the browser-back
        button from re-triggering the delete."""
        eid = seeded_with_one_expense["expense_id"]
        response = auth_client.post(f"/expenses/{eid}/delete")
        assert response.status_code == 302

    def test_post_then_follow_redirect_to_profile(
        self, auth_client, seeded_with_one_expense
    ):
        """Simulating the browser: after a 302, the next request to
        /profile should be a 200 GET (not another POST)."""
        eid = seeded_with_one_expense["expense_id"]
        post_response = auth_client.post(f"/expenses/{eid}/delete")
        assert post_response.status_code == 302

        follow = auth_client.get(post_response.headers["Location"])
        assert follow.status_code == 200

    def test_double_post_does_not_error_after_first_delete(
        self, auth_client, seeded_with_one_expense
    ):
        """Second POST on the now-missing id should 404 (idempotent
        from a UX standpoint), not crash."""
        eid = seeded_with_one_expense["expense_id"]
        auth_client.post(f"/expenses/{eid}/delete")
        # The row is gone — a second POST should 404, not 500.
        second = auth_client.post(f"/expenses/{eid}/delete")
        assert second.status_code == 404


# ---------------------------------------------------------------------------
# 10. Session user deleted — drop session, redirect to /login
# ---------------------------------------------------------------------------

class TestSessionUserDeleted:
    """If a user is deleted while their session cookie is still alive,
    the delete route must drop the session and redirect to /login rather
    than crash on a foreign-key check or render a 500."""

    def test_get_delete_when_session_user_missing_redirects_to_login(
        self, client, seeded_with_one_expense, seeded
    ):
        eid = seeded_with_one_expense["expense_id"]
        # Login first so we have a session.
        _login_session(client, seeded["user_id"], "Demo User")
        # Then yank the user out from under the session.
        _delete_session_user(seeded["user_id"])

        response = client.get(f"/expenses/{eid}/delete")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_delete_when_session_user_missing_redirects_to_login(
        self, client, seeded_with_one_expense, seeded
    ):
        eid = seeded_with_one_expense["expense_id"]
        _login_session(client, seeded["user_id"], "Demo User")
        _delete_session_user(seeded["user_id"])

        response = client.post(f"/expenses/{eid}/delete")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# 11. The /profile page renders the Delete link per row pointing at the
#     correct delete URL.
# ---------------------------------------------------------------------------

class TestProfileActionsColumn:
    def _seed_user_with_multiple_expenses(self, user_id):
        ids = []
        ids.append(_insert_expense(user_id, 100.00, "Food",    "2026-07-01", "A"))
        ids.append(_insert_expense(user_id, 200.00, "Bills",   "2026-07-02", "B"))
        ids.append(_insert_expense(user_id, 300.00, "Health",  "2026-07-03", "C"))
        return ids

    def test_profile_has_delete_link_per_row(self, auth_client):
        self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        # Three rows → three Delete links.
        assert html.count("Delete") >= 3

    def test_profile_delete_link_points_at_correct_url(self, auth_client):
        ids = self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        for eid in ids:
            # Each row should carry an anchor to its own /delete URL.
            assert f"/expenses/{eid}/delete" in html, (
                f"Expected /expenses/{eid}/delete link on /profile, "
                f"but didn't find it"
            )

    def test_profile_delete_link_count_matches_row_count(self, auth_client):
        ids = self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        # Exactly one link per row (no duplicates).
        for eid in ids:
            count = html.count(f"/expenses/{eid}/delete")
            assert count == 1, (
                f"Expected exactly 1 link to /expenses/{eid}/delete, "
                f"found {count}"
            )

    def test_profile_has_both_edit_and_delete_links(self, auth_client):
        """Both actions are present in the Actions column per the spec."""
        self._seed_user_with_multiple_expenses(1)
        html = auth_client.get("/profile").data.decode()
        assert "Edit" in html
        assert "Delete" in html