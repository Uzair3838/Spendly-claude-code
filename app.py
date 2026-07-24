import os

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "dev-secret-change-me"


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

    conn = get_db()
    try:
        # Load the signed-in user's own row.
        user_row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        # Defensive: session references a user that no longer exists.
        if user_row is None:
            session.clear()
            return redirect(url_for("login"))

        # Total lifetime spend for this user only.
        total_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total_spent = total_row["total"] or 0

        # Total expense count for this user only.
        count_row = conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        expense_count = count_row["n"] or 0

        # Top category for this user only (by sum of amount).
        top_row = conn.execute(
            "SELECT category, SUM(amount) AS cat_total "
            "FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY cat_total DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        top_category = top_row["category"] if top_row else None

        # Per-category totals for this user only.
        cat_rows = conn.execute(
            "SELECT category, SUM(amount) AS cat_total "
            "FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY cat_total DESC",
            (user_id,),
        ).fetchall()

        # Recent transactions for this user only.
        tx_rows = conn.execute(
            "SELECT date, description, category, amount "
            "FROM expenses WHERE user_id = ? "
            "ORDER BY date DESC, id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    # Derive initials from the user's name.
    parts = (user_row["name"] or "").split()
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        initials = parts[0][0].upper()
    else:
        initials = "?"

    # Format member_since — "YYYY-MM-DD HH:MM:SS" → "15 March 2026".
    import datetime
    try:
        joined = datetime.datetime.strptime(user_row["created_at"], "%Y-%m-%d %H:%M:%S")
        member_since = f"{joined.day} {joined.strftime('%B %Y')}"
    except (TypeError, ValueError):
        member_since = (user_row["created_at"] or "")[:10]

    # Compute per-category percentages against the user's top category total.
    max_total = cat_rows[0]["cat_total"] if cat_rows else 0
    categories = [
        {
            "name": row["category"],
            "total": row["cat_total"],
            "pct": int(round((row["cat_total"] / max_total) * 100)) if max_total else 0,
        }
        for row in cat_rows
    ]

    summary = {
        "total_spent": total_spent,
        "expense_count": expense_count,
        "top_category": top_category,
    }

    transactions = [
        {
            "date": row["date"],
            "description": row["description"] or "",
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in tx_rows
    ]

    return render_template(
        "profile.html",
        user={"name": user_row["name"], "email": user_row["email"]},
        initials=initials,
        member_since=member_since,
        summary=summary,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


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
