# AI conversation log

## 1. Initial developer instruction

Developer: Build a complete full-stack parking garage product in the current workspace. Treat the attendant's workflow as the primary specification: an attendant must be able to check a car in, assign a valid spot, check it out, and charge the correct fee.

The submission must include all of the following:

- A real database with a sensible schema and persistent data.
- REST APIs for the core operations. List every endpoint in `README.md`.
- A usable UI that works over the APIs.
- User registration and login.
- Search, especially lookup by vehicle plate.
- Pagination and sorting for the growing parking log.
- A one-page landing page explaining the product, key features, target audience, how it helps, and three features planned next.
- `README.md`, `REASONING.md`, and `AI_LOGS.md` in the repository root.

Parking rules:

1. Rates are tiered: the first hour has one price, each additional hour is cheaper, and there is a daily cap.
2. Any part-hour must be rounded up.
3. Parking spots are limited and have types: compact, standard, and EV with a charger.
4. An EV must always be assigned an EV spot.
5. No spot may be double-parked, including during simultaneous check-ins.
6. The attendant needs to see whether EV spots are available.
7. The system should work for any garage, not just one hard-coded location.

Prioritize correct check-in, check-out, and fee calculation first. Then add spot types and lookups. Keep the implementation practical and easy to run locally.

## 2. Environment assessment

Assistant: I inspected the workspace and found it empty. I checked the available tools and found Python 3.11 and Git, but no Node.js or npm. I will use a dependency-free Python implementation so the project can be run with one command and does not depend on installing a frontend build toolchain.

Developer: Use a real SQLite database, not in-memory collections. Keep the API and UI in the same project so setup remains simple. Make the database schema support multiple garages even if the seeded demo starts with one garage.

Assistant: I will use Python's standard-library HTTP server, SQLite, JSON, and static files. The schema will separate users, authentication tokens, garages, spots, and parking sessions. Spot allocation will be protected by an immediate SQLite transaction so selecting and occupying a spot happen atomically.

## 3. Backend implementation instruction

Developer: Implement the backend first. Include registration, login, logout, authenticated routes, garage and spot queries, check-in, checkout, search, sorting, and pagination. EV check-in must fail when no EV space is available rather than falling back to another type.

Assistant: Added `server.py` with:

- SQLite initialization and a seeded demo garage.
- Users and PBKDF2 password hashing.
- Bearer-token authentication with token persistence.
- Garage and spot tables with compact, standard, and EV types.
- Parking session history with active and completed states.
- Transactional compatible spot assignment.
- Duplicate active-plate protection.
- Fee calculation using ceiling hours, a first-hour rate, a cheaper additional-hour rate, and a daily cap.
- Checkout logic that stores the final fee and releases the spot.
- Search by plate or driver, configurable sorting, and page metadata.

Developer: Use a clear API contract and make errors return JSON with useful HTTP status codes. Store rates per garage so the behavior is not tied to one city's prices.

Assistant: The API stores `first_hour_rate`, `additional_hour_rate`, and `daily_cap` on each garage. Protected operations require `Authorization: Bearer <token>`. Conflict responses are used for duplicate plates and unavailable compatible spots; checkout returns the charged hours and fee.

## 4. UI and product experience instruction

Developer: Build an actual usable interface, not just an API demo. The first page should communicate what the product is and who it helps, then let an attendant register or sign in and operate the garage. Show live capacity by spot type, especially EV availability. Include check-in, checkout, plate/driver search, sorting, and pagination.

Assistant: Added `static/index.html`, `static/styles.css`, and `static/app.js` with:

- A one-page landing section for city-centre parking attendants.
- Product features, target audience, benefits, and three roadmap items.
- Registration and sign-in forms.
- A live dashboard with active vehicle count and available compact, standard, and EV spaces.
- A check-in form that displays the assigned spot.
- A parking log with plate/driver search, sorting, pagination, and checkout actions.
- Responsive styling for desktop and mobile screens.

Developer: Keep the dashboard connected to the backend. Do not use mock records for the operational workflow.

Assistant: The browser uses `fetch` for every operational action, stores the login token locally, reloads dashboard metrics from `/api/dashboard`, and reloads the parking log from `/api/sessions` after check-in and checkout.

## 5. Documentation instruction

Developer: Add the required documentation in the repository root. `README.md` must explain setup, running, debugging, parking rules, and every REST endpoint. `REASONING.md` should explain the design decisions and how the implementation was tested. Keep `AI_LOGS.md` as this complete conversation record.

Assistant: Added `README.md` with the Python setup command, database behavior, debugging notes, fee rules, and the complete endpoint table. Added `REASONING.md` with the rationale for SQLite, transactional allocation, fee calculation, UI structure, security notes, and test steps.

## 6. Validation and fixes

Developer: Validate the highest-risk behavior against a running server. Test registration, login, dashboard data, EV allocation, plate search, pagination parameters, and checkout. Also run a syntax or diagnostics check on the backend.

Assistant: Initialized the SQLite schema successfully with:

```powershell
py -c "import server; server.init_db(); print('schema ok')"
```

Then I started the server with:

```powershell
py server.py
```

The live smoke test passed:

- A new user registered and logged in.
- The dashboard reported zero active vehicles before the test.
- An EV vehicle was assigned to `EV-01`, confirming EV compatibility.
- Searching for the generated plate returned exactly one result.
- Checkout returned a one-hour charge of 80 pence and released the session.
- The backend passed `py -m py_compile server.py`.
- Workspace diagnostics reported no errors for `server.py`.

Assistant: Removed generated local runtime artifacts from the submission directory and added `.gitignore` entries for `auriga.db`, `__pycache__/`, and compiled Python files. The temporary server used for testing was stopped after validation.

## 7. Final handoff

Assistant: The Auriga parking product is implemented in the empty workspace. Run it with:

```powershell
py server.py
```

Then open `http://127.0.0.1:8000`. The required root documentation files are present alongside the backend and `static/` UI files.
