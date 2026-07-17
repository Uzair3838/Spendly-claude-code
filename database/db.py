import sqlite3

from werkzeug.security import generate_password_hash


# Path to the SQLite database file at the project root.
DB_PATH = "spendly.db"


def get_db():
    """Open a SQLite connection with row factory and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables. Safe to call multiple times."""
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
    conn.close()


def seed_db():
    """Insert demo user and 8 sample expenses. No-op if already seeded."""
    conn = get_db()

    # Skip seeding if the users table already has data.
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing:
        conn.close()
        return

    # Demo user — password is "demo123".
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
    )

    user_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()["id"]

    # 8 expenses covering all 7 fixed categories, spread across the current month.
    expenses = [
        (user_id, 250.00, "Food",          "2026-07-02", "Lunch at office canteen"),
        (user_id, 480.50, "Food",          "2026-07-05", "Groceries from local mart"),
        (user_id, 120.00, "Transport",     "2026-07-03", "Uber to airport"),
        (user_id, 1500.00,"Bills",         "2026-07-01", "Electricity bill"),
        (user_id, 350.00, "Health",        "2026-07-08", "Pharmacy restock"),
        (user_id, 600.00, "Entertainment", "2026-07-10", "Movie tickets"),
        (user_id, 1299.00,"Shopping",      "2026-07-12", "New running shoes"),
        (user_id, 80.00,  "Other",         "2026-07-15", "Misc cash spend"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        expenses,
    )

    conn.commit()
    conn.close()
