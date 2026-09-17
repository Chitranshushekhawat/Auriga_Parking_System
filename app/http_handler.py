import json
import math
import secrets
import sqlite3
from datetime import timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .auth import check_password, hash_password
from .config import STATIC
from .database import connect, iso_now, row_dict, utc_now
from .errors import ApiError
from .operations import finalize_session, run_nightly_clock
from .pricing import clean_rate_card


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
            "SELECT users.* FROM auth_tokens JOIN users ON users.id = auth_tokens.user_id WHERE auth_tokens.token = ?",
            (token,),
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
        content_type = (
            "text/html; charset=utf-8" if target.suffix == ".html"
            else "text/css; charset=utf-8" if target.suffix == ".css"
            else "application/javascript; charset=utf-8"
        )
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
            counts = {
                r["spot_type"]: {"available": r["available"], "total": r["total"]}
                for r in db.execute(
                    "SELECT spot_type, COUNT(*) total, SUM(status = 'available') available FROM spots WHERE garage_id = ? GROUP BY spot_type",
                    (garage["id"],),
                )
            }
            active = db.execute("SELECT COUNT(*) FROM parking_sessions WHERE status = 'active'").fetchone()[0]
            overdue = db.execute(
                "SELECT COUNT(*) FROM parking_sessions WHERE status = 'active' AND checked_in_at <= ?",
                ((utc_now() - timedelta(hours=24)).isoformat(timespec="seconds"),),
            ).fetchone()[0]
            self.send_json(
                {"garage": row_dict(garage), "counts": counts, "active_sessions": active, "overdue_sessions": overdue},
                include_body=include_body,
            )
        elif path == "/api/spots":
            self.authenticate()
            garage_id = query.get("garage_id", [None])[0]
            clauses, params = [], []
            if garage_id:
                clauses.append("garage_id = ?")
                params.append(garage_id)
            if query.get("type", [""])[0] in ("compact", "standard", "ev"):
                clauses.append("spot_type = ?")
                params.append(query["type"][0])
            if query.get("status", [""])[0] in ("available", "occupied"):
                clauses.append("status = ?")
                params.append(query["status"][0])
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            self.send_json(
                {"spots": [row_dict(r) for r in db.execute("SELECT * FROM spots" + where + " ORDER BY spot_type, spot_number", params)]},
                include_body=include_body,
            )
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
            clauses.append("(UPPER(plate) LIKE ? OR UPPER(driver_name) LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]
        if status in ("active", "completed"):
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        page = max(1, int(query.get("page", ["1"])[0]))
        size = min(50, max(1, int(query.get("page_size", ["8"])[0])))
        total = db.execute("SELECT COUNT(*) FROM parking_sessions" + where, params).fetchone()[0]
        rows = db.execute(
            "SELECT parking_sessions.*, spots.spot_number FROM parking_sessions JOIN spots ON spots.id = parking_sessions.spot_id"
            + where
            + f" ORDER BY {sort_column} {direction} LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
        self.send_json(
            {
                "sessions": [row_dict(r) for r in rows],
                "pagination": {"page": page, "page_size": size, "total": total, "pages": max(1, math.ceil(total / size))},
            },
            include_body=include_body,
        )

    def route_post(self, path):
        db = connect()
        if path in ("/clock", "/api/clock"):
            self.authenticate()
            result = run_nightly_clock(db)
            self.send_json({"closed_sessions": result["closed"], "updated": result["updated"], "message": result["message"]})
            db.close()
            return
        data = self.read_json()
        if path == "/api/auth/register":
            name = str(data.get("name", "")).strip()
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            if not name or "@" not in email or len(password) < 6:
                raise ApiError("Name, valid email, and a 6+ character password are required")
            try:
                user_id = db.execute(
                    "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (name, email, hash_password(password), iso_now()),
                ).lastrowid
                db.commit()
            except sqlite3.IntegrityError:
                raise ApiError("An account with that email already exists", HTTPStatus.CONFLICT)
            self.send_json(
                {"user": row_dict(db.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone())},
                HTTPStatus.CREATED,
            )
        elif path == "/api/auth/login":
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not user or not check_password(password, user["password_hash"]):
                raise ApiError("Email or password is incorrect", HTTPStatus.UNAUTHORIZED)
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO auth_tokens VALUES (?, ?, ?)", (token, user["id"], iso_now()))
            db.commit()
            self.send_json({"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}})
        elif path == "/api/auth/logout":
            token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            db.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            db.commit()
            self.send_json({"ok": True})
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
            self.check_out(db, path.split("/")[3])
        elif path.startswith("/api/sessions/") and path.endswith("/transfer"):
            self.authenticate()
            self.transfer_session(db, path.split("/")[3], data)
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
        spot = db.execute(
            f"SELECT * FROM spots WHERE garage_id = ? AND status = 'available' AND {compatible} ORDER BY CASE WHEN spot_type = ? THEN 0 ELSE 1 END, spot_number LIMIT 1",
            (garage_id, vehicle_type),
        ).fetchone()
        if not spot:
            db.rollback()
            raise ApiError(f"No available {vehicle_type} spot in this garage", HTTPStatus.CONFLICT)
        now = iso_now()
        db.execute("UPDATE spots SET status = 'occupied' WHERE id = ?", (spot["id"],))
        session_id = db.execute(
            "INSERT INTO parking_sessions (garage_id, spot_id, plate, vehicle_type, driver_name, checked_in_at) VALUES (?, ?, ?, ?, ?, ?)",
            (garage_id, spot["id"], plate, vehicle_type, driver, now),
        ).lastrowid
        db.commit()
        self.send_json(
            {"session": row_dict(db.execute("SELECT parking_sessions.*, spots.spot_number FROM parking_sessions JOIN spots ON spots.id = parking_sessions.spot_id WHERE parking_sessions.id = ?", (session_id,)).fetchone())},
            HTTPStatus.CREATED,
        )

    def check_out(self, db, session_id):
        session = db.execute("SELECT * FROM parking_sessions WHERE id = ? AND status = 'active'", (session_id,)).fetchone()
        if not session:
            raise ApiError("Active parking session not found", HTTPStatus.NOT_FOUND)
        fee, hours = finalize_session(db, session, utc_now())
        self.send_json(
            {
                "session": row_dict(db.execute("SELECT parking_sessions.*, spots.spot_number FROM parking_sessions JOIN spots ON spots.id = parking_sessions.spot_id WHERE parking_sessions.id = ?", (session_id,)).fetchone()),
                "hours_charged": hours,
                "fee": fee,
            }
        )

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
