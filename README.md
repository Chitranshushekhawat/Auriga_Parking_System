# Auriga Parking

Auriga is a small, practical parking operations app for busy attendant teams. It runs on plain Python, stores live garage data in SQLite, and serves a browser UI from the same process. The idea is simple: check vehicles in, assign the right space, calculate a fair fee, and keep the shift calm.

## What it does

- Tracks garage capacity and live session totals
- Enforces vehicle-to-spot compatibility, especially EV rules
- Prevents double-booking during check-in with an immediate SQLite transaction
- Calculates pricing using first-hour, additional-hour, and daily-cap logic
- Supports searching, sorting, and pagination for parking history
- Includes a nightly close job for sessions parked longer than 24 hours
- Lets attendants transfer an open session to a different plate for valet-style handoff
- Accepts messy rate-card imports and cleans them into valid garage rates

## Requirements

- Python 3.9+
- No external packages required

## Run it locally

```bash
cd /workspaces/Auriga_Parking_System
python3 server.py
```

Then open:

- http://127.0.0.1:8000

If port 8000 is already in use, run:

```bash
PORT=8001 python3 server.py
```

The first startup creates `auriga.db` and seeds a demo garage with compact, standard, and EV spots.

## Reset data

To reset the local database:

```bash
rm auriga.db
python3 server.py
```

## Useful API endpoints

Protected endpoints expect:

```http
Authorization: Bearer <token>
```

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create a user |
| POST | `/api/auth/login` | Log in and receive a token |
| POST | `/api/auth/logout` | Revoke the current token |
| GET | `/api/auth/me` | Get the signed-in user |
| GET | `/api/dashboard` | Garage capacity and session totals |
| GET | `/api/spots` | List spaces with filters |
| GET | `/api/sessions` | Search and paginate sessions |
| POST | `/api/sessions/check-in` | Assign a compatible spot |
| POST | `/api/sessions/:id/check-out` | Close a session and bill it |
| POST | `/api/sessions/:id/transfer` | Move an active session to a new plate |
| POST | `/api/rates/import` | Import a cleaned or messy rate card |
| POST | `/clock` | Close any session parked over 24 hours |

## Messy rate-card example

```json
{
  "garage_id": 1,
  "rates": "compact: £2.80\nstandard: 310p\nEV: 4.40 GBP\nnoise: junk"
}
```

The server cleans this input and stores valid first-hour, additional-hour, and daily-cap values per spot type.

## Notes

- The app stores the token in browser local storage.
- Errors come back as JSON like `{ "error": "..." }`.
- The server logs HTTP requests in the terminal for quick debugging.

## Project files

- `server.py` — server, SQLite schema, auth, pricing, and API routes
- `static/index.html` — landing page and dashboard UI
- `static/styles.css` — styling and layout
- `static/app.js` — browser logic for login, check-in, pricing tools, and operations
- `REASONING.md` — short decisions and notes
- `AI_LOGS.md` — project conversation log
