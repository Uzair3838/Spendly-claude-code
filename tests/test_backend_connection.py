import os
import tempfile
import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from database.db import init_db, get_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db_module.DB_PATH = db_path
    init_db()
    yield db_path
    db_module.DB_PATH = "spendly.db"


@pytest.fixture()
def seed_user():
    conn = get_db()
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (1, "Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:30:00"),
    )
    conn.commit()
    conn.close()
    return 1


@pytest.fixture()
def seed_expenses(seed_user):
    expenses = [
        (seed_user, 250.00, "Food", "2026-07-02", "Lunch"),
        (seed_user, 480.50, "Food", "2026-07-05", "Groceries"),
        (seed_user, 120.00, "Transport", "2026-07-03", "Uber"),
        (seed_user, 1500.00, "Bills", "2026-07-01", "Electricity"),
        (seed_user, 350.00, "Health", "2026-07-08", "Pharmacy"),
        (seed_user, 600.00, "Entertainment", "2026-07-10", "Movies"),
        (seed_user, 1299.00, "Shopping", "2026-07-12", "Shoes"),
        (seed_user, 80.00, "Other", "2026-07-15", None),
    ]
    conn = get_db()
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()
    return seed_user


# --- get_user_by_id ---

def test_get_user_by_id_valid(seed_user):
    result = get_user_by_id(seed_user)
    assert result is not None
    assert result["name"] == "Demo User"
    assert result["email"] == "demo@spendly.com"
    assert result["member_since"] == "15 January 2026"


def test_get_user_by_id_invalid():
    result = get_user_by_id(9999)
    assert result is None


# --- get_summary_stats ---

def test_get_summary_stats_with_expenses(seed_expenses):
    result = get_summary_stats(seed_expenses)
    assert result["total_spent"] == 4679.5
    assert result["transaction_count"] == 8
    assert result["top_category"] == "Bills"


def test_get_summary_stats_no_expenses(seed_user):
    result = get_summary_stats(seed_user)
    assert result["total_spent"] == 0
    assert result["transaction_count"] == 0
    assert result["top_category"] == "—"


# --- get_recent_transactions ---

def test_get_recent_transactions_with_expenses(seed_expenses):
    result = get_recent_transactions(seed_expenses)
    assert len(result) == 8
    assert result[0]["date"] == "2026-07-15"
    assert result[-1]["date"] == "2026-07-01"
    assert all(k in result[0] for k in ("date", "description", "category", "amount"))


def test_get_recent_transactions_no_expenses(seed_user):
    result = get_recent_transactions(seed_user)
    assert result == []


def test_get_recent_transactions_null_description(seed_expenses):
    result = get_recent_transactions(seed_expenses)
    last_entry = [t for t in result if t["date"] == "2026-07-15"][0]
    assert last_entry["description"] == ""


def test_get_recent_transactions_limit(seed_expenses):
    result = get_recent_transactions(seed_expenses, limit=3)
    assert len(result) == 3


# --- get_category_breakdown ---

def test_get_category_breakdown_with_expenses(seed_expenses):
    result = get_category_breakdown(seed_expenses)
    assert len(result) == 7
    assert result[0]["name"] == "Bills"
    assert all(k in result[0] for k in ("name", "amount", "pct"))


def test_get_category_breakdown_no_expenses(seed_user):
    result = get_category_breakdown(seed_user)
    assert result == []


def test_category_pct_sums_to_100(seed_expenses):
    result = get_category_breakdown(seed_expenses)
    total_pct = sum(cat["pct"] for cat in result)
    assert total_pct == 100


# --- Route tests ---

@pytest.fixture()
def app_client(seed_expenses):
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_profile_route_unauthenticated(app_client):
    response = app_client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_route_authenticated(app_client, seed_expenses):
    with app_client.session_transaction() as sess:
        sess["user_id"] = seed_expenses
        sess["user_name"] = "Demo User"
    response = app_client.get("/profile")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "Rs" in html
