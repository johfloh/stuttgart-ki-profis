"""
Database layer for the Stuttgart KI Profis platform.
SQLite-based, single-file, no external DB dependencies.

Schema:
  users           - Registered accounts (email + password)
  customers       - Handyman business profiles
  instances       - Agent deployment metadata
  payment_events  - Payment records
"""

import os
import sqlite3
import hashlib
import secrets
import time
from pathlib import Path
from datetime import datetime

DB_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DB_DIR / "platform.db"


def _ensure_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)


def _dict_factory(cursor, row):
    """Return rows as dictionaries."""
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def get_conn():
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS customers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            customer_id     TEXT UNIQUE NOT NULL,
            plan            TEXT DEFAULT 'basis',
            status          TEXT DEFAULT 'pending',
            company_name    TEXT NOT NULL DEFAULT '',
            street          TEXT DEFAULT '',
            zip_city        TEXT DEFAULT '',
            phone           TEXT DEFAULT '',
            email           TEXT DEFAULT '',
            vat_id          TEXT DEFAULT '',
            whatsapp_number TEXT DEFAULT '',
            hourly_rate     REAL DEFAULT 55.0,
            trade           TEXT DEFAULT '',
            employees       INTEGER DEFAULT 1,
            setup_token     TEXT DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS instances (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     INTEGER NOT NULL,
            port            INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'pending',
            pid             INTEGER DEFAULT 0,
            config_path     TEXT DEFAULT '',
            whatsapp_connected INTEGER DEFAULT 0,
            last_seen       TIMESTAMP,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS payment_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     INTEGER NOT NULL,
            amount          REAL NOT NULL,
            currency        TEXT DEFAULT 'EUR',
            provider        TEXT DEFAULT '',
            provider_event_id TEXT DEFAULT '',
            status          TEXT DEFAULT 'pending',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
    """)
    conn.commit()
    conn.close()


# ── User Operations ──────────────────────────────────────────────────


def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def create_user(email: str, password: str) -> dict | None:
    """Register a new user. Returns user dict on success, None if duplicate."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email.lower().strip(), hash_password(password)),
        )
        conn.commit()
        user_id = cur.lastrowid
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return user
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)
        ).fetchone()
    finally:
        conn.close()


# ── Customer Operations ──────────────────────────────────────────────


def create_customer(
    user_id: int,
    company_name: str,
    trade: str = "",
    street: str = "",
    zip_city: str = "",
    phone: str = "",
    email: str = "",
    whatsapp_number: str = "",
    hourly_rate: float = 55.0,
    employees: int = 1,
    vat_id: str = "",
    plan: str = "basis",
) -> dict | None:
    """Create a new customer record and generate a customer_id."""
    conn = get_conn()
    try:
        # Generate a URL-safe customer id from company name
        base_id = company_name.lower().replace(" ", "-").replace("ß", "ss")
        base_id = "".join(c for c in base_id if c.isalnum() or c == "-")
        if not base_id:
            base_id = "kunde"
        # Ensure uniqueness
        suffix = ""
        counter = 0
        while True:
            candidate = f"{base_id}{suffix}"
            existing = conn.execute(
                "SELECT id FROM customers WHERE customer_id=?", (candidate,)
            ).fetchone()
            if not existing:
                base_id = candidate
                break
            counter += 1
            suffix = f"-{counter}"

        setup_token = secrets.token_hex(16)

        cur = conn.execute(
            """INSERT INTO customers
               (user_id, customer_id, plan, status, company_name, street, zip_city,
                phone, email, vat_id, whatsapp_number, hourly_rate, trade, employees, setup_token)
               VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, base_id, plan, company_name, street, zip_city,
             phone, email, vat_id, whatsapp_number, hourly_rate, trade, employees, setup_token),
        )
        conn.commit()
        customer_id = cur.lastrowid
        customer = conn.execute(
            "SELECT * FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        return customer
    finally:
        conn.close()


def get_customer_by_id(customer_id: int) -> dict | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
    finally:
        conn.close()


def get_customer_by_customer_id(cid: str) -> dict | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM customers WHERE customer_id=?", (cid,)
        ).fetchone()
    finally:
        conn.close()


def get_customers_by_user(user_id: int) -> list[dict]:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM customers WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def update_customer(customer_id: int, **kwargs) -> bool:
    """Update customer fields. Only provided fields are updated."""
    allowed = {
        "company_name", "street", "zip_city", "phone", "email", "vat_id",
        "whatsapp_number", "hourly_rate", "trade", "employees", "plan", "status",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [customer_id]
    conn = get_conn()
    try:
        conn.execute(f"UPDATE customers SET {sets} WHERE id=?", values)
        conn.commit()
        return True
    finally:
        conn.close()


# ── Instance Operations ──────────────────────────────────────────────


def create_instance(customer_id: int) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO instances (customer_id, status) VALUES (?, 'pending')",
            (customer_id,),
        )
        conn.commit()
        inst = conn.execute(
            "SELECT * FROM instances WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return inst
    finally:
        conn.close()


def get_instance_by_customer(customer_id: int) -> dict | None:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM instances WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,),
        ).fetchone()
    finally:
        conn.close()


def update_instance(instance_id: int, **kwargs) -> bool:
    allowed = {"port", "status", "pid", "config_path", "whatsapp_connected", "last_seen"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [instance_id]
    conn = get_conn()
    try:
        conn.execute(f"UPDATE instances SET {sets} WHERE id=?", values)
        conn.commit()
        return True
    finally:
        conn.close()


# ── Payment Operations ───────────────────────────────────────────────


def record_payment(customer_id: int, amount: float, provider: str = "", provider_event_id: str = "") -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO payment_events (customer_id, amount, provider, provider_event_id, status) VALUES (?, ?, ?, ?, 'completed')",
            (customer_id, amount, provider, provider_event_id),
        )
        conn.commit()
        return conn.execute("SELECT * FROM payment_events WHERE id=?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()


# ── Utility ──────────────────────────────────────────────────────────


def find_next_free_port(start: int = 9000) -> int:
    """Find the next free port starting from `start`."""
    import socket
    for port in range(start, 65535):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def generate_jwt_token(user_id: int, secret: str, expiry_hours: int = 72) -> str:
    """Generate a JWT token for the user."""
    import jwt
    payload = {
        "user_id": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + expiry_hours * 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_jwt_token(token: str, secret: str) -> dict | None:
    """Verify JWT token and return payload, or None if invalid."""
    import jwt
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None


# ── Admin ─────────────────────────────────────────────────────────────


def admin_list_all() -> list[dict]:
    """
    List ALL customers across all users with instance and user info.
    For agency/owner dashboard.
    """
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT
                c.id as cid,
                c.customer_id,
                c.company_name,
                c.plan,
                c.status,
                c.whatsapp_number,
                c.trade,
                c.hourly_rate,
                c.employees,
                c.created_at as customer_created,
                u.email as user_email,
                u.id as user_id,
                i.id as instance_id,
                i.port,
                i.status as instance_status,
                i.whatsapp_connected,
                i.last_seen,
                i.created_at as instance_created
            FROM customers c
            JOIN users u ON u.id = c.user_id
            LEFT JOIN instances i ON i.customer_id = c.id
            ORDER BY c.created_at DESC
        """).fetchall()
        return rows
    finally:
        conn.close()


def admin_stats() -> dict:
    """Return aggregate platform statistics."""
    conn = get_conn()
    try:
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        total_customers = conn.execute("SELECT COUNT(*) as c FROM customers").fetchone()["c"]
        active_customers = conn.execute("SELECT COUNT(*) as c FROM customers WHERE status='active'").fetchone()["c"]
        running_instances = conn.execute("SELECT COUNT(*) as c FROM instances WHERE status='running'").fetchone()["c"]
        connected_whatsapp = conn.execute("SELECT COUNT(*) as c FROM instances WHERE whatsapp_connected=1").fetchone()["c"]
        total_payments = conn.execute("SELECT COUNT(*) as c FROM payment_events").fetchone()["c"]
        revenue = conn.execute("SELECT COALESCE(SUM(amount), 0) as s FROM payment_events").fetchone()["s"]
        return {
            "total_users": total_users,
            "total_customers": total_customers,
            "active_customers": active_customers,
            "running_instances": running_instances,
            "connected_whatsapp": connected_whatsapp,
            "total_payments": total_payments,
            "revenue": revenue,
        }
    finally:
        conn.close()