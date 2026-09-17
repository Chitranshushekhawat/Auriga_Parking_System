import sqlite3
from datetime import datetime, timezone

from .config import DB_PATH


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(timespec="seconds")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    db = connect()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS garages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            first_hour_rate INTEGER NOT NULL DEFAULT 80,
            additional_hour_rate INTEGER NOT NULL DEFAULT 40,
            daily_cap INTEGER NOT NULL DEFAULT 240,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS spots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            garage_id INTEGER NOT NULL REFERENCES garages(id) ON DELETE CASCADE,
            spot_number TEXT NOT NULL,
            spot_type TEXT NOT NULL CHECK (spot_type IN ('compact', 'standard', 'ev')),
            status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'occupied')),
            UNIQUE(garage_id, spot_number)
        );
        CREATE TABLE IF NOT EXISTS parking_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            garage_id INTEGER NOT NULL REFERENCES garages(id),
            spot_id INTEGER NOT NULL REFERENCES spots(id),
            plate TEXT NOT NULL,
            vehicle_type TEXT NOT NULL CHECK (vehicle_type IN ('compact', 'standard', 'ev')),
            driver_name TEXT NOT NULL,
            checked_in_at TEXT NOT NULL,
            checked_out_at TEXT,
            fee INTEGER,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed'))
        );
        CREATE TABLE IF NOT EXISTS spot_rate_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            garage_id INTEGER NOT NULL REFERENCES garages(id) ON DELETE CASCADE,
            spot_type TEXT NOT NULL CHECK (spot_type IN ('compact', 'standard', 'ev')),
            first_hour_rate INTEGER NOT NULL,
            additional_hour_rate INTEGER NOT NULL,
            daily_cap INTEGER NOT NULL,
            UNIQUE(garage_id, spot_type)
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_plate ON parking_sessions(plate);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON parking_sessions(status);
        """
    )
    if db.execute("SELECT COUNT(*) FROM garages").fetchone()[0] == 0:
        now = iso_now()
        garage_id = db.execute(
            "INSERT INTO garages (name, address, created_at) VALUES (?, ?, ?)",
            ("Auriga Central Garage", "18 Market Street, City Centre", now),
        ).lastrowid
        spots = [(garage_id, f"C-{i:02}", "compact") for i in range(1, 7)]
        spots += [(garage_id, f"S-{i:02}", "standard") for i in range(1, 13)]
        spots += [(garage_id, f"EV-{i:02}", "ev") for i in range(1, 5)]
        db.executemany("INSERT INTO spots (garage_id, spot_number, spot_type) VALUES (?, ?, ?)", spots)
        db.executemany(
            "INSERT INTO spot_rate_cards (garage_id, spot_type, first_hour_rate, additional_hour_rate, daily_cap) VALUES (?, ?, ?, ?, ?)",
            [(garage_id, spot_type, 80, 40, 240) for spot_type in ("compact", "standard", "ev")],
        )
    else:
        garage_ids = [row[0] for row in db.execute("SELECT id FROM garages").fetchall()]
        for garage_id in garage_ids:
            for spot_type in ("compact", "standard", "ev"):
                exists = db.execute(
                    "SELECT 1 FROM spot_rate_cards WHERE garage_id = ? AND spot_type = ?",
                    (garage_id, spot_type),
                ).fetchone()
                if not exists:
                    db.execute(
                        "INSERT INTO spot_rate_cards (garage_id, spot_type, first_hour_rate, additional_hour_rate, daily_cap) VALUES (?, ?, ?, ?, ?)",
                        (garage_id, spot_type, 80, 40, 240),
                    )
    db.commit()
    db.close()


def row_dict(row):
    return dict(row) if row else None
