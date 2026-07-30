import datetime
from datetime import date, timedelta

from database.db import get_db


RANGE_PRESETS = (
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("last_3_months", "Last 3 months"),
    ("this_year", "This year"),
)


def parse_date_range(range_key, from_str="", to_str=""):
    """Translate a range key into (start_date, end_date, label, error).

    All returned dates are `datetime.date` objects or `None`. SQLite binds
    `date` objects directly via parameterised queries, so callers do not
    need to convert to ISO strings.

    Returns ("all time", None, None) for unknown keys and valid-but-empty
    custom input. For malformed custom input, returns ("all time", None)
    with a short error message in the 4th position.
    """
    today = date.today()

    if range_key == "this_month":
        start = today.replace(day=1)
        return start, today, "this month", None

    if range_key == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start = last_prev.replace(day=1)
        return start, last_prev, last_prev.strftime("%b %Y"), None

    if range_key == "last_3_months":
        month = today.month - 2
        year = today.year
        while month < 1:
            month += 12
            year -= 1
        start = date(year, month, 1)
        return start, today, "last 3 months", None

    if range_key == "this_year":
        start = today.replace(month=1, day=1)
        return start, today, "this year", None

    if range_key == "custom":
        try:
            start = date.fromisoformat(from_str)
            end = date.fromisoformat(to_str)
        except ValueError:
            # Malformed input silently falls back to "all time" data, but
            # a short error message is returned so the UI can show it.
            return None, None, "all time", "Please enter valid dates (YYYY-MM-DD)."
        if start > end:
            return None, None, "all time", "From date is after To date."
        return start, end, "custom range", None

    return None, None, "all time", None


def get_user_by_id(user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            return None
        created_at = row["created_at"]
        try:
            joined = datetime.datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            member_since = f"{joined.day} {joined.strftime('%B %Y')}"
        except (TypeError, ValueError):
            member_since = (created_at or "")[:10]
        return {
            "name": row["name"],
            "email": row["email"],
            "member_since": member_since,
        }
    finally:
        db.close()


def get_expense_for_user(id, user_id):
    """Return the expense row only if it's owned by user_id. None otherwise.

    The `WHERE id = ? AND user_id = ?` filter is the ownership check — a
    row owned by another user simply doesn't match, so the route can
    treat both "doesn't exist" and "not yours" as the same 404 response
    without leaking ownership.
    """
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ? AND user_id = ?",
            (id, user_id),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "amount": row["amount"],
            "category": row["category"],
            # YYYY-MM-DD string — passes straight into <input type="date">
            "date": row["date"],
            "description": row["description"] or "",
        }
    finally:
        db.close()


def _date_clause(start_date, end_date):
    # Only add the clause when both bounds are real (not None). Empty strings,
    # empty tuples, and date objects all behave correctly under truthiness
    # checks — but a None start with a None end is what means "no filter".
    if start_date is not None and end_date is not None:
        return " AND date BETWEEN ? AND ?", (start_date, end_date)
    return "", ()


def get_summary_stats(user_id, start_date=None, end_date=None):
    db = get_db()
    try:
        date_sql, date_params = _date_clause(start_date, end_date)

        row = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ?" + date_sql,
            (user_id,) + date_params,
        ).fetchone()
        total_spent = row["total"] or 0

        row = db.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?" + date_sql,
            (user_id,) + date_params,
        ).fetchone()
        transaction_count = row["n"] or 0

        row = db.execute(
            "SELECT category, SUM(amount) AS cat_total FROM expenses WHERE user_id = ?" + date_sql + " GROUP BY category ORDER BY cat_total DESC LIMIT 1",
            (user_id,) + date_params,
        ).fetchone()
        top_category = row["category"] if row else "—"

        return {
            "total_spent": total_spent,
            "transaction_count": transaction_count,
            "top_category": top_category,
        }
    finally:
        db.close()


def get_recent_transactions(user_id, limit=10, start_date=None, end_date=None):
    db = get_db()
    try:
        date_sql, date_params = _date_clause(start_date, end_date)
        rows = db.execute(
            "SELECT id, date, description, category, amount FROM expenses WHERE user_id = ?" + date_sql + " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id,) + date_params + (limit,)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "date": row["date"],
                "description": row["description"] or "",
                "category": row["category"],
                "amount": row["amount"],
            }
            for row in rows
        ]
    finally:
        db.close()


def get_category_breakdown(user_id, start_date=None, end_date=None):
    db = get_db()
    try:
        date_sql, date_params = _date_clause(start_date, end_date)
        rows = db.execute(
            "SELECT category, SUM(amount) AS cat_total FROM expenses WHERE user_id = ?" + date_sql + " GROUP BY category ORDER BY cat_total DESC",
            (user_id,) + date_params,
        ).fetchall()
        if not rows:
            return []
        grand_total = sum(row["cat_total"] for row in rows)
        if grand_total == 0:
            return []
        result = []
        for row in rows:
            pct = round(row["cat_total"] / grand_total * 100)
            result.append({"name": row["category"], "amount": row["cat_total"], "pct": pct})
        remainder = 100 - sum(item["pct"] for item in result)
        result[0]["pct"] += remainder
        return result
    finally:
        db.close()
