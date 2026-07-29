import os
from datetime import date

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db
from database.queries import (
    RANGE_PRESETS,
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    parse_date_range,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "dev-secret-change-me"
# Reject oversized request bodies project-wide (16 KB). The form posts
# only four small fields, so this is plenty of headroom.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

# Fixed list of valid expense categories. Kept identical to the names used
# in database/db.py seed_db() and the .cat-<name> badge colours in
# static/css/style.css so the breakdown chart stays in sync.
EXPENSE_CATEGORIES = (
    "Food", "Transport", "Shopping", "Bills",
    "Entertainment", "Health", "Other",
)

# Upper bound on a single expense amount. Defends against accidental
# paste of huge numbers (1e308 etc.) corrupting the user's dashboard.
MAX_AMOUNT = 1_000_000_000


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Already signed in? Don't show the form again.
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("register.html")

    # POST: create a new user account.
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    # Server-side validation.
    if not name or not email or "@" not in email or len(password) < 8:
        return render_template("register.html", error="Please fill all fields correctly"), 200

    # Case-insensitive uniqueness: lowercase the email before lookup and insert.
    email = email.lower()

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            return render_template("register.html", error="Email already registered"), 200

        password_hash = generate_password_hash(password)
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        user_id = cur.lastrowid
    finally:
        conn.close()

    # Sign the user in and send them to the profile placeholder.
    session["user_id"] = user_id
    session["user_name"] = name
    return redirect(url_for("profile"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        # Already signed in? Don't show the form again.
        if session.get("user_id"):
            return redirect(url_for("landing"))
        return render_template("login.html")

    # POST: verify credentials and start a session.
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    # Same generic error on every failure path — don't leak whether the email exists.
    if not email or not password:
        return render_template(
            "login.html", error="Invalid email or password", email=email
        ), 200

    # Case-insensitive lookup, matching the convention from /register.
    email = email.lower()

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return render_template(
            "login.html", error="Invalid email or password", email=email
        ), 200

    session["user_id"] = row["id"]
    session["user_name"] = row["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    user_data = get_user_by_id(user_id)
    if user_data is None:
        session.clear()
        return redirect(url_for("login"))

    parts = (user_data["name"] or "").split()
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        initials = parts[0][0].upper()
    else:
        initials = "?"

    active_range = request.args.get("range", "")
    from_str = request.args.get("from", "")
    to_str = request.args.get("to", "")
    start_date, end_date, filter_label, filter_error = parse_date_range(
        active_range, from_str, to_str
    )
    # A malformed custom range falls back to "all time" data — keep the
    # form open so the user can correct the inputs without losing them.
    show_custom = active_range == "custom"

    summary = get_summary_stats(user_id, start_date=start_date, end_date=end_date)
    transactions = get_recent_transactions(user_id, start_date=start_date, end_date=end_date)
    categories = get_category_breakdown(user_id, start_date=start_date, end_date=end_date)

    return render_template(
        "profile.html",
        user={"name": user_data["name"], "email": user_data["email"]},
        initials=initials,
        member_since=user_data["member_since"],
        summary=summary,
        transactions=transactions,
        categories=categories,
        active_range=active_range,
        filter_label=filter_label,
        filter_error=filter_error,
        show_custom=show_custom,
        range_presets=RANGE_PRESETS,
        filter_from=from_str,
        filter_to=to_str,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today_iso = date.today().isoformat()

    # Confirm the session user still exists. If a user was deleted while a
    # session cookie is still alive, drop the session and force a re-login
    # rather than crashing on the foreign-key check later. Mirrors the
    # pattern in profile().
    user_row = get_user_by_id(session["user_id"])
    if user_row is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            today_iso=today_iso,
            categories=EXPENSE_CATEGORIES,
        )

    # POST: validate, insert, redirect (POST-redirect-GET).
    amount_raw = (request.form.get("amount") or "").strip()
    category = (request.form.get("category") or "").strip()
    date_str = (request.form.get("date") or "").strip()
    description = (request.form.get("description") or "").strip()

    # Hold the user's submitted values so the form can re-render them on
    # validation failure without losing what was typed.
    form = {
        "amount": amount_raw,
        "category": category,
        "date": date_str,
        "description": description,
    }

    # Reject obviously-too-long descriptions before any DB work. Keeps a
    # single request from ballooning the expenses table.
    if len(description) > 500:
        return _render_add_form(
            "Description must be 500 characters or fewer.",
            form, today_iso,
        )

    # Amount: must parse to a float > 0, and below an upper cap so an
    # accidental paste of a huge number doesn't corrupt the user's totals.
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return _render_add_form(
            "Please enter a valid amount greater than zero.",
            form, today_iso,
        )
    if amount <= 0:
        return _render_add_form(
            "Amount must be greater than zero.",
            form, today_iso,
        )
    if amount > MAX_AMOUNT:
        return _render_add_form(
            "Amount is too large.",
            form, today_iso,
        )

    # Category: must be one of the fixed 7 values.
    if category not in EXPENSE_CATEGORIES:
        return _render_add_form(
            "Please choose a valid category.",
            form, today_iso,
        )

    # Date: must parse as YYYY-MM-DD.
    try:
        parsed_date = date.fromisoformat(date_str)
    except ValueError:
        return _render_add_form(
            "Please enter a valid date.",
            form, today_iso,
        )

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (session["user_id"], amount, category, parsed_date, description),
        )
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("profile"))


def _render_add_form(error, form, today_iso):
    """Re-render the add-expense form with an error and the user's input."""
    return render_template(
        "add_expense.html",
        error=error,
        form=form,
        today_iso=today_iso,
        categories=EXPENSE_CATEGORIES,
    ), 200


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
