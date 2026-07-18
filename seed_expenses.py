"""Seed a configurable number of random expenses for a user."""
import random
import sys
from datetime import date, timedelta

from database.db import get_db

# Reconfigure stdout for Windows consoles that default to cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CATEGORIES = {
    "Food": {
        "weight": 30,
        "min": 50,
        "max": 800,
        "descriptions": [
            "Lunch at office canteen",
            "Chai and samosa",
            "Dominos pizza order",
            "Street food — pav bhaji",
            "Groceries from local kirana",
            "Swiggy dinner order",
            "South Indian breakfast",
            "Mughlai dinner",
            "BigBasket monthly groceries",
            "Cold coffee and sandwich",
        ],
    },
    "Transport": {
        "weight": 22,
        "min": 20,
        "max": 500,
        "descriptions": [
            "Uber to office",
            "Ola auto rickshaw",
            "Rapido bike ride",
            "Metro card recharge",
            "Petrol refill",
            "Auto to station",
            "Cab to airport",
            "BMTC bus pass top-up",
            "Train ticket booking",
            "Ola Outstation trip",
        ],
    },
    "Bills": {
        "weight": 15,
        "min": 200,
        "max": 3000,
        "descriptions": [
            "Electricity bill",
            "Broadband bill",
            "Mobile postpaid bill",
            "Gas cylinder refill",
            "Water bill",
            "DTH recharge",
            "Society maintenance",
            "Credit card bill",
            "Piped gas bill",
            "Insurance premium",
        ],
    },
    "Health": {
        "weight": 5,
        "min": 100,
        "max": 2000,
        "descriptions": [
            "Pharmacy medicines",
            "Doctor consultation",
            "Lab tests",
            "Vitamins and supplements",
            "Dental checkup",
            "Eye checkup",
            "First-aid supplies",
            "Monthly medicines",
            "Blood test",
            "Physiotherapy session",
        ],
    },
    "Entertainment": {
        "weight": 8,
        "min": 100,
        "max": 1500,
        "descriptions": [
            "Movie tickets — PVR",
            "Netflix subscription",
            "Spotify Premium",
            "Book purchase",
            "Concert tickets",
            "Gaming top-up — Steam",
            "BookMyShow booking",
            "Disney+ Hotstar",
            "Amusement park entry",
            "Comedy show tickets",
        ],
    },
    "Shopping": {
        "weight": 12,
        "min": 200,
        "max": 5000,
        "descriptions": [
            "Amazon order — electronics",
            "Flipkart — clothes",
            "Myntra fashion haul",
            "New running shoes",
            "Mobile cover and accessories",
            "Kitchen appliances",
            "Festive clothing",
            "Meesho — home decor",
            "Smartwatch",
            "Laptop bag",
        ],
    },
    "Other": {
        "weight": 8,
        "min": 50,
        "max": 1000,
        "descriptions": [
            "Cash withdrawal",
            "Gift for friend",
            "Stationery",
            "Salon haircut",
            "Laundry",
            "Courier parcel",
            "Parking fee",
            "Toll charges",
            "Temple donation",
            "Misc cash spend",
        ],
    },
}


def weighted_category():
    names = list(CATEGORIES.keys())
    weights = [CATEGORIES[n]["weight"] for n in names]
    return random.choices(names, weights=weights, k=1)[0]


def random_date_in_window(months):
    today = date.today()
    start = today - timedelta(days=months * 30)
    span_days = (today - start).days
    offset = random.randint(0, span_days)
    return start + timedelta(days=offset)


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: /seed-expenses <user_id> <count> <months>\n"
            "Example: /seed-expenses 1 50 6"
        )
        sys.exit(1)

    try:
        user_id = int(sys.argv[1])
        count = int(sys.argv[2])
        months = int(sys.argv[3])
    except ValueError:
        print(
            "Usage: /seed-expenses <user_id> <count> <months>\n"
            "Example: /seed-expenses 1 50 6"
        )
        sys.exit(1)

    conn = get_db()
    try:
        user_row = conn.execute(
            "SELECT id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user_row is None:
            print(f"No user found with id {user_id}.")
            sys.exit(1)

        rows = []
        for _ in range(count):
            category = weighted_category()
            cfg = CATEGORIES[category]
            amount = round(random.uniform(cfg["min"], cfg["max"]), 2)
            expense_date = random_date_in_window(months).isoformat()
            description = random.choice(cfg["descriptions"])
            rows.append((user_id, amount, category, expense_date, description))

        try:
            conn.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()

    dates = sorted(r[3] for r in rows)
    print(f"Inserted {len(rows)} expenses for user_id={user_id}.")
    print(f"Date range: {dates[0]} to {dates[-1]}")
    print("Sample of 5 inserted records:")
    for r in random.sample(rows, k=min(5, len(rows))):
        amount, category, expense_date, description = r[1], r[2], r[3], r[4]
        print(f"  - {expense_date} | {category:<14} ₹{amount:>8.2f} | {description}")


if __name__ == "__main__":
    main()
