# Auriga Parking

Auriga is a full-stack parking operations tool for attendants working busy multi-level garages. It persists garages, spots, users, sessions, and fees in SQLite; provides authenticated REST APIs; and serves a responsive browser UI from the same Python process.

## Requirements

- Python 3.9+
- No external packages required

## Setup and run

```powershell
py server.py
```

Open http://127.0.0.1:8000. The first startup creates `auriga.db` and seeds a demo garage with compact, standard, and EV spots. Set a different port with `$env:PORT=8080; py server.py`.

To reset local data, stop the server and delete `auriga.db`; it will be recreated on the next run.

## Debugging

The server logs each HTTP request in the terminal. API errors return JSON in the form `{ "error": "..." }`. The browser stores the bearer token in local storage. Use the browser developer console and Network panel to inspect API calls.

## Product behavior

- EV vehicles can only receive EV spots.
- Compact and standard vehicles receive a compatible compact or standard spot.
- Spot assignment happens inside an immediate SQLite transaction, preventing double assignment under concurrent check-ins.
- Billing rounds any part-hour up to the next hour.
- The first hour uses the first-hour rate, additional hours use the cheaper additional-hour rate, and every 24-hour period is capped at the daily cap.
- Default demo rates are 80 pence for the first hour, 40 pence per additional hour, and 240 pence daily maximum. Values are stored per garage.

## REST API

All endpoints below accept and return JSON. Protected endpoints require `Authorization: Bearer <token>`.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create a user account |
| POST | `/api/auth/login` | Authenticate and receive a bearer token |
| POST | `/api/auth/logout` | Revoke the current token |
| GET | `/api/auth/me` | Get the current user, if authenticated |
| GET | `/api/garages` | List garages |
| GET | `/api/dashboard` | Get garage capacity and live vehicle totals |
| GET | `/api/spots` | List spots; filter with `garage_id`, `type`, or `status` |
| GET | `/api/sessions` | Search and paginate parking sessions |
| POST | `/api/sessions/check-in` | Assign a compatible spot and create an active session |
| POST | `/api/sessions/:id/check-out` | Complete a session, calculate its fee, and free its spot |

`GET /api/sessions` supports `search`, `status`, `page`, `page_size`, `sort` (`checked_in_at`, `plate`, `spot`, `fee`), and `direction` (`asc` or `desc`).

## Project files

- `server.py` - standard-library HTTP server, SQLite schema, auth, fee calculation, and API routes.
- `static/index.html` - landing page and attendant dashboard markup.
- `static/styles.css` - responsive visual system.
- `static/app.js` - API client and dashboard interactions.
- `REASONING.md` - implementation decisions and testing notes.
- `AI_LOGS.md` - conversation record for this submission.
