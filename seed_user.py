"""Seed a single random Indian user into the users table."""
import random
import sys
from datetime import datetime

from database.db import get_db
from werkzeug.security import generate_password_hash

FIRST_NAMES = [
    # North
    "Aarav", "Arjun", "Rohan", "Rahul", "Amit", "Vikas", "Sandeep", "Nikhil",
    "Karan", "Manish", "Pooja", "Priya", "Neha", "Anjali", "Shruti", "Ritu",
    "Sakshi", "Kavita", "Ayesha", "Sneha",
    # South
    "Arun", "Karthik", "Vignesh", "Suresh", "Ramesh", "Ananya", "Divya",
    "Lakshmi", "Meenakshi", "Snehalatha", "Pavithra", "Srinivas",
    # West
    "Aditya", "Harsh", "Yash", "Ishaan", "Kunal", "Tanvi", "Aishwarya",
    "Riya", "Pranav", "Siddharth",
    # East / Central
    "Subhajit", "Debanjan", "Rajat", "Anwesha", "Saurav", "Bikash",
    "Moumita", "Pallabi", "Tushar", "Naveen",
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Agarwal", "Jain", "Bansal", "Mittal",
    "Patel", "Shah", "Mehta", "Desai", "Joshi", "Modi", "Trivedi", "Pandya",
    "Reddy", "Naidu", "Rao", "Iyer", "Iyengar", "Krishnan", "Menon",
    "Pillai", "Nair", "Kumar", "Mukherjee", "Banerjee", "Chatterjee",
    "Das", "Ghosh", "Bose", "Roy", "Saha", "Sinha", "Khan", "Ansari",
    "Siddiqui", "Qureshi", "Sheikh", "Patil", "Kulkarni", "Deshpande",
    "Joshi", "Bhatt", "Chauhan", "Rathore", "Singh", "Kaur", "Gill",
    "Dhillon",
]

DOMAINS = ["gmail.com", "yahoo.com", "outlook.com"]


def random_name():
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def random_email(first, last):
    suffix = random.randint(10, 999)
    return f"{first.lower()}.{last.lower()}{suffix}@{random.choice(DOMAINS)}"


def email_exists(conn, email):
    row = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
    return row is not None


def main():
    conn = get_db()
    try:
        # Regenerate until we get a unique email.
        attempts = 0
        while True:
            first, last = random_name()
            email = random_email(first, last)
            attempts += 1
            if not email_exists(conn, email):
                break
            if attempts > 50:
                print("Could not find a unique email after 50 attempts.", file=sys.stderr)
                sys.exit(1)

        name = f"{first} {last}"
        password_hash = generate_password_hash("password123")
        created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, password_hash, created_at),
        )
        conn.commit()
        user_id = cur.lastrowid
    finally:
        conn.close()

    print(f"id: {user_id}")
    print(f"name: {name}")
    print(f"email: {email}")


if __name__ == "__main__":
    main()
