import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
DB_PATH = ROOT / "auriga.db"
STATIC = ROOT / "static"

RATE_ALIASES = {
    "compact": ("compact", "compact car", "mini", "small"),
    "standard": ("standard", "regular", "mid", "midsize"),
    "ev": ("ev", "electric", "charger", "electric vehicle"),
}


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(timespec="seconds")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + ":" + digest.hex()


def check_password(password, encoded):
    salt, digest = encoded.split(":", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
    return secrets.compare_digest(candidate.hex(), digest)


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
            [
                (garage_id, "compact", 80, 40, 240),
                (garage_id, "standard", 80, 40, 240),
                (garage_id, "ev", 80, 40, 240),
            ],
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


def calculate_fee(garage, start, end):
    total_seconds = max(0, (end - start).total_seconds())
    hours = max(1, math.ceil(total_seconds / 3600))
    full_days, remaining_hours = divmod(hours, 24)
    partial = garage["daily_cap"] if remaining_hours == 0 else min(
        garage["daily_cap"], garage["first_hour_rate"] + max(0, remaining_hours - 1) * garage["additional_hour_rate"]
    )
    return full_days * garage["daily_cap"] + partial, hours


def get_garage_rates(db, garage_id, vehicle_type):
    row = db.execute("SELECT * FROM spot_rate_cards WHERE garage_id = ? AND spot_type = ?", (garage_id, vehicle_type)).fetchone()
    if row:
        return {"first_hour_rate": row["first_hour_rate"], "additional_hour_rate": row["additional_hour_rate"], "daily_cap": row["daily_cap"]}
    garage = db.execute("SELECT * FROM garages WHERE id = ?", (garage_id,)).fetchone()
    return {"first_hour_rate": garage["first_hour_rate"], "additional_hour_rate": garage["additional_hour_rate"], "daily_cap": garage["daily_cap"]}


def calculate_fee_for_rates(rates, start, end):
    total_seconds = max(0, (end - start).total_seconds())
    hours = max(1, math.ceil(total_seconds / 3600))
    full_days, remaining_hours = divmod(hours, 24)
    if remaining_hours == 0:
        partial = rates["daily_cap"]
    else:
        partial = min(rates["daily_cap"], rates["first_hour_rate"] + max(0, remaining_hours - 1) * rates["additional_hour_rate"])
    return full_days * rates["daily_cap"] + partial, hours


def coerce_to_pence(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return int(round(float(raw_value)))
    text = str(raw_value).strip().lower()
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    amount = float(match.group())
    if any(token in text for token in ("p", "pence")):
        return int(round(amount))
    if any(token in text for token in ("£", ".", "eur", "gbp", "dollar", "$")):
        return int(round(amount * 100))
    return int(round(amount))


def clean_rate_card(raw_rates):
    cleaned = {}

    def add_entry(spot_type, raw_value):
        if not spot_type or raw_value is None:
            return
        value = coerce_to_pence(raw_value)
        if value is None:
            return
        cleaned[spot_type] = {
            "first_hour_rate": value,
            "additional_hour_rate": max(0, int(value * 0.5)),
            "daily_cap": max(value * 3, value),
        }

    if isinstance(raw_rates, dict):
        for key, value in raw_rates.items():
            normalized = str(key).strip().lower()
            for spot_type, aliases in RATE_ALIASES.items():
                if normalized in aliases or normalized == spot_type:
                    add_entry(spot_type, value)
                    break
        return cleaned

    if isinstance(raw_rates, (list, tuple)):
        for item in raw_rates:
            if isinstance(item, dict):
                for key, value in item.items():
                    if str(key).lower() in ("spot_type", "type"):
                        spot_type = str(value).strip().lower()
                        for candidate, aliases in RATE_ALIASES.items():
                            if spot_type == candidate or spot_type in aliases:
                                add_entry(candidate, item.get("first_hour_rate") or item.get("rate") or item.get("value"))
                                break
            elif isinstance(item, (str, int, float)):
                nested = clean_rate_card(str(item))
                if nested:
                    cleaned.update(nested)
        return cleaned

    if not isinstance(raw_rates, str):
        return cleaned

    text = str(raw_rates).lower()
    if not text:
        return cleaned

    segments = re.split(r"[\n|,;]+", text)
    for segment in segments:
        if not segment.strip():
            continue
        for spot_type, aliases in RATE_ALIASES.items():
            for alias in aliases:
                if alias in segment:
                    match = re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:p|£|\$)?", segment)
                    if match:
                        add_entry(spot_type, match.group(0))
                    break
            if spot_type in cleaned:
                break

    if not cleaned:
        for spot_type, aliases in RATE_ALIASES.items():
            pattern = r"(?:" + "|".join(re.escape(alias) for alias in aliases) + r")\s*[^0-9]*([-+]?\d+(?:\.\d+)?)\s*(?:p|£|\$)?"
            match = re.search(pattern, text)
            if match:
                add_entry(spot_type, match.group(1))
    return cleaned


class ApiError(Exception):
    def __init__(self, message, status=HTTPStatus.BAD_REQUEST):
        self.message = message
        self.status = status


def finalize_session(db, session, end=None):
    if end is None:
        end = utc_now()
    rates = get_garage_rates(db, session["garage_id"], session["vehicle_type"])
    fee, hours = calculate_fee_for_rates(rates, parse_time(session["checked_in_at"]), end)
    db.execute("UPDATE parking_sessions SET status = 'completed', checked_out_at = ?, fee = ? WHERE id = ?", (end.isoformat(timespec="seconds"), fee, session["id"]))
    db.execute("UPDATE spots SET status = 'available' WHERE id = ?", (session["spot_id"],))
    return fee, hours


def run_nightly_clock(db):
    now = utc_now()
    active_sessions = db.execute("SELECT * FROM parking_sessions WHERE status = 'active'").fetchall()
    updated = []
    for session in active_sessions:
        started = parse_time(session["checked_in_at"])
        if now - started >= timedelta(hours=24):
            fee, hours = finalize_session(db, session, now)
            updated.append({"id": session["id"], "plate": session["plate"], "fee": fee, "hours_charged": hours})
    db.commit()
    return {"closed": len(updated), "updated": updated, "message": f"Closed {len(updated)} overnight session(s)"}


class Handler(BaseHTTPRequestHandler):
    server_version = "AurigaParking/1.0"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, payload, status=HTTPStatus.OK, include_body=True):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            raise ApiError("Request body must be valid JSON")

    def authenticate(self, required=True):
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        db = connect()
        row = db.execute(
            "SELECT users.* FROM auth_tokens JOIN users ON users.id = auth_tokens.user_id WHERE auth_tokens.token = ?", (token,)
        ).fetchone()
        db.close()
        if not row and required:
            raise ApiError("Please log in to continue", HTTPStatus.UNAUTHORIZED)
        return row

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                return self.serve_static(parsed.path)
            self.route_get(parsed.path, parse_qs(parsed.query))
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            print("ERROR", repr(exc))
            self.send_json({"error": "Unexpected server error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_HEAD(self):
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                return self.serve_static(parsed.path, include_body=False)
            self.route_get(parsed.path, parse_qs(parsed.query), include_body=False)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status, include_body=False)
        except Exception as exc:
            print("ERROR", repr(exc))
            self.send_json({"error": "Unexpected server error"}, HTTPStatus.INTERNAL_SERVER_ERROR, include_body=False)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/") and parsed.path != "/clock":
                raise ApiError("Route not found", HTTPStatus.NOT_FOUND)
            self.route_post(parsed.path)
        except ApiError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            print("ERROR", repr(exc))
            self.send_json({"error": "Unexpected server error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static(self, path, include_body=True):
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC not in target.parents and target != STATIC / "index.html":
            raise ApiError("Not found", HTTPStatus.NOT_FOUND)
        if not target.exists() or not target.is_file():
            target = STATIC / "index.html"
        content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "text/css; charset=utf-8" if target.suffix == ".css" else "application/javascript; charset=utf-8"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def route_get(self, path, query, include_body=True):
        db = connect()
        if path == "/api/auth/me":
            user = self.authenticate(False)
            self.send_json({"user": row_dict(user) if user else None}, include_body=include_body)
        elif path == "/api/garages":
            self.authenticate()
            self.send_json({"garages": [row_dict(r) for r in db.execute("SELECT * FROM garages ORDER BY name")]}, include_body=include_body)
        elif path == "/api/dashboard":
            self.authenticate()
            garage = db.execute("SELECT * FROM garages ORDER BY id LIMIT 1").fetchone()
            counts = {r["spot_type"]: {"available": r["available"], "total": r["total"]} for r in db.execute("SELECT spot_type, COUNT(*) total, SUM(status = 'available') available FROM spots WHERE garage_id = ? GROUP BY spot_type", (garage["id"],))}
            active = db.execute("SELECT COUNT(*) FROM parking_sessions WHERE status = 'active'").fetchone()[0]
            overdue = db.execute("SELECT COUNT(*) FROM parking_sessions WHERE status = 'active' AND checked_in_at <= ?", ((utc_now() - timedelta(hours=24)).isoformat(timespec="seconds"),)).fetchone()[0]
            self.send_json({"garage": row_dict(garage), "counts": counts, "active_sessions": active, "overdue_sessions": overdue}, include_body=include_body)
        elif path == "/api/spots":
            self.authenticate()
            garage_id = query.get("garage_id", [None])[0]
            clauses, params = [], []
            if garage_id:
                clauses.append("garage_id = ?"); params.append(garage_id)
            if query.get("type", [""])[0] in ("compact", "standard", "ev"):
                clauses.append("spot_type = ?"); params.append(query["type"][0])
            if query.get("status", [""])[0] in ("available", "occupied"):
                clauses.append("status = ?"); params.append(query["status"][0])
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            self.send_json({"spots": [row_dict(r) for r in db.execute("SELECT * FROM spots" + where + " ORDER BY spot_type, spot_number", params)]}, include_body=include_body)
        elif path == "/api/sessions":
            self.authenticate()
            self.list_sessions(db, query, include_body=include_body)
        elif path == "/api/rates":
            self.authenticate()
            rows = db.execute("SELECT * FROM spot_rate_cards ORDER BY spot_type").fetchall()
            self.send_json({"rates": [row_dict(r) for r in rows]}, include_body=include_body)
        elif path == "/api/health":
            self.send_json({"ok": True, "status": "healthy", "service": "auriga-parking"}, include_body=include_body)
        else:
            raise ApiError("Route not found", HTTPStatus.NOT_FOUND)
        db.close()

    def list_sessions(self, db, query, include_body=True):
        search = query.get("search", [""])[0].strip().upper()
        status = query.get("status", [""])[0]
        sort = query.get("sort", ["checked_in_at"])[0]
        direction = "DESC" if query.get("direction", ["desc"])[0].lower() == "desc" else "ASC"
        sort_column = {"plate": "plate", "spot": "spot_number", "fee": "fee", "checked_in_at": "checked_in_at"}.get(sort, "checked_in_at")
        clauses, params = [], []
        if search:
            clauses.append("(UPPER(plate) LIKE ? OR UPPER(driver_name) LIKE ?)"); params += [f"%{search}%", f"%{search}%"]
        if status in ("active", "completed"):
            clauses.append("status = ?"); params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        page = max(1, int(query.get("page", ["1"])[0]))
        size = min(50, max(1, int(query.get("page_size", ["8"])[0])))
        total = db.execute("SELECT COUNT(*) FROM parking_sessions" + where, params).fetchone()[0]
        rows = db.execute(
            "SELECT parking_sessions.*, spots.spot_number FROM parking_sessions JOIN spots ON spots.id = parking_sessions.spot_id" + where + f" ORDER BY {sort_column} {direction} LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
        self.send_json({"sessions": [row_dict(r) for r in rows], "pagination": {"page": page, "page_size": size, "total": total, "pages": max(1, math.ceil(total / size))}}, include_body=include_body)

    def route_post(self, path):
        db = connect()
        if path in ("/clock", "/api/clock"):
            result = run_nightly_clock(db)
            self.send_json({"closed_sessions": result["closed"], "updated": result["updated"], "message": result["message"]}, HTTPStatus.OK)
            db.close(); return
        data = self.read_json()
        if path == "/api/auth/register":
            name, email, password = str(data.get("name", "")).strip(), str(data.get("email", "")).strip().lower(), str(data.get("password", ""))
            if not name or "@" not in email or len(password) < 6:
                raise ApiError("Name, valid email, and a 6+ character password are required")
            try:
                user_id = db.execute("INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)", (name, email, hash_password(password), iso_now())).lastrowid
                db.commit()
            except sqlite3.IntegrityError:
                raise ApiError("An account with that email already exists", HTTPStatus.CONFLICT)
            self.send_json({"user": row_dict(db.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone())}, HTTPStatus.CREATED)
        elif path == "/api/auth/login":
            email, password = str(data.get("email", "")).strip().lower(), str(data.get("password", ""))
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not user or not check_password(password, user["password_hash"]):
                raise ApiError("Email or password is incorrect", HTTPStatus.UNAUTHORIZED)
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO auth_tokens VALUES (?, ?, ?)", (token, user["id"], iso_now())); db.commit()
            self.send_json({"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}})
        elif path == "/api/auth/logout":
            token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            db.execute("DELETE FROM auth_tokens WHERE token = ?", (token,)); db.commit(); self.send_json({"ok": True})
        elif path == "/api/rates/import":
            self.authenticate()
            cleaned = clean_rate_card(data.get("rates") or data.get("rate_card") or data.get("raw_rates") or data)
            if not cleaned:
                raise ApiError("No valid rate data was found to import")
            garage_id = int(data.get("garage_id", 1))
            for spot_type, values in cleaned.items():
                db.execute(
                    "INSERT INTO spot_rate_cards (garage_id, spot_type, first_hour_rate, additional_hour_rate, daily_cap) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(garage_id, spot_type) DO UPDATE SET first_hour_rate = excluded.first_hour_rate, additional_hour_rate = excluded.additional_hour_rate, daily_cap = excluded.daily_cap",
                    (garage_id, spot_type, values["first_hour_rate"], values["additional_hour_rate"], values["daily_cap"]),
                )
            db.commit()
            self.send_json({"ok": True, "rates": cleaned})
        elif path == "/api/sessions/check-in":
            self.authenticate()
            self.check_in(db, data)
        elif path.startswith("/api/sessions/") and path.endswith("/check-out"):
            self.authenticate()
            session_id = path.split("/")[3]
            self.check_out(db, session_id)
        elif path.startswith("/api/sessions/") and path.endswith("/transfer"):
            self.authenticate()
            session_id = path.split("/")[3]
            self.transfer_session(db, session_id, data)
        else:
            raise ApiError("Route not found", HTTPStatus.NOT_FOUND)
        db.close()

    def check_in(self, db, data):
        plate = str(data.get("plate", "")).strip().upper()
        driver = str(data.get("driver_name", "")).strip()
        vehicle_type = str(data.get("vehicle_type", "standard")).lower()
        garage_id = int(data.get("garage_id", 1))
        if not plate or not driver or vehicle_type not in ("compact", "standard", "ev"):
            raise ApiError("Plate, driver name, and a valid vehicle type are required")
        if db.execute("SELECT 1 FROM parking_sessions WHERE plate = ? AND status = 'active'", (plate,)).fetchone():
            raise ApiError("That plate is already checked in", HTTPStatus.CONFLICT)
        compatible = "spot_type = 'ev'" if vehicle_type == "ev" else "spot_type IN ('compact', 'standard')"
        db.execute("BEGIN IMMEDIATE")
        spot = db.execute(f"SELECT * FROM spots WHERE garage_id = ? AND status = 'available' AND {compatible} ORDER BY CASE WHEN spot_type = ? THEN 0 ELSE 1 END, spot_number LIMIT 1", (garage_id, vehicle_type)).fetchone()
        if not spot:
            db.rollback(); raise ApiError(f"No available {vehicle_type} spot in this garage", HTTPStatus.CONFLICT)
        now = iso_now()
        db.execute("UPDATE spots SET status = 'occupied' WHERE id = ?", (spot["id"],))
        session_id = db.execute("INSERT INTO parking_sessions (garage_id, spot_id, plate, vehicle_type, driver_name, checked_in_at) VALUES (?, ?, ?, ?, ?, ?)", (garage_id, spot["id"], plate, vehicle_type, driver, now)).lastrowid
        db.commit()
        self.send_json({"session": row_dict(db.execute("SELECT parking_sessions.*, spots.spot_number FROM parking_sessions JOIN spots ON spots.id = parking_sessions.spot_id WHERE parking_sessions.id = ?", (session_id,)).fetchone())}, HTTPStatus.CREATED)

    def check_out(self, db, session_id):
        session = db.execute("SELECT * FROM parking_sessions WHERE id = ? AND status = 'active'", (session_id,)).fetchone()
        if not session:
            raise ApiError("Active parking session not found", HTTPStatus.NOT_FOUND)
        fee, hours = finalize_session(db, session, utc_now())
        self.send_json({"session": row_dict(db.execute("SELECT parking_sessions.*, spots.spot_number FROM parking_sessions JOIN spots ON spots.id = parking_sessions.spot_id WHERE parking_sessions.id = ?", (session_id,)).fetchone()), "hours_charged": hours, "fee": fee})

    def transfer_session(self, db, session_id, data):
        session = db.execute("SELECT * FROM parking_sessions WHERE id = ? AND status = 'active'", (session_id,)).fetchone()
        if not session:
            raise ApiError("Active parking session not found", HTTPStatus.NOT_FOUND)
        new_plate = str(data.get("plate", "")).strip().upper()
        if not new_plate:
            raise ApiError("A new plate is required")
        if db.execute("SELECT 1 FROM parking_sessions WHERE plate = ? AND status = 'active' AND id != ?", (new_plate, session_id)).fetchone():
            raise ApiError("That plate is already checked in", HTTPStatus.CONFLICT)
        updates = ["plate = ?"]
        params = [new_plate]
        driver = str(data.get("driver_name", "")).strip()
        if driver:
            updates.append("driver_name = ?")
            params.append(driver)
        params.append(session_id)
        db.execute(f"UPDATE parking_sessions SET {', '.join(updates)} WHERE id = ?", tuple(params))
        db.commit()
        updated = row_dict(db.execute("SELECT parking_sessions.*, spots.spot_number FROM parking_sessions JOIN spots ON spots.id = parking_sessions.spot_id WHERE parking_sessions.id = ?", (session_id,)).fetchone())
        self.send_json({"session": updated, "message": "Plate transfer completed"})


def main():
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Auriga Parking running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
