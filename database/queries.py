import datetime
from database.db import get_db


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


def get_summary_stats(user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        total_spent = row["total"] or 0

        row = db.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        transaction_count = row["n"] or 0

        row = db.execute(
            "SELECT category, SUM(amount) AS cat_total FROM expenses WHERE user_id = ? GROUP BY category ORDER BY cat_total DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        top_category = row["category"] if row else "—"

        return {
            "total_spent": total_spent,
            "transaction_count": transaction_count,
            "top_category": top_category,
        }
    finally:
        db.close()


def get_recent_transactions(user_id, limit=10):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT date, description, category, amount FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [
            {
                "date": row["date"],
                "description": row["description"] or "",
                "category": row["category"],
                "amount": row["amount"],
            }
            for row in rows
        ]
    finally:
        db.close()


def get_category_breakdown(user_id):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT category, SUM(amount) AS cat_total FROM expenses WHERE user_id = ? GROUP BY category ORDER BY cat_total DESC",
            (user_id,)
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
