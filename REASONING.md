# Reasoning

## How I approached it

The workspace was empty, so I started by looking at the simplest way to deliver a complete product that another person could run without a long setup process. Python 3.11 was available, but Node.js and npm were not. I therefore used Python's standard library, SQLite, and a small static frontend. This keeps the project easy to inspect and means the application can be started with `py server.py`.

The most important part of the product is not the landing page; it is making sure a car gets the right spot and the right bill. I treated those as the core business rules and built the rest of the application around them.

## Data model

I used SQLite because it gives the application real persistence and transaction support without requiring a separate database server. The main tables are:

- `garages` stores the garage name, address, and its pricing rules.
- `spots` stores each numbered space, its type, and whether it is currently occupied.
- `parking_sessions` stores the vehicle, driver, assigned spot, check-in time, checkout time, and final fee.
- `users` and `auth_tokens` support registration and authenticated API access.

Garage-specific pricing and spot ownership are stored in the database instead of being constants in the code. The seeded garage makes the project immediately usable, but the structure is ready for more garages later.

## Check-in and spot safety

Spot allocation was the area where a small implementation mistake could cause the biggest operational problem. A simple “find a free spot, then update it” sequence can allow two requests to select the same space. To avoid that, check-in starts an `IMMEDIATE` SQLite transaction, selects a compatible available spot, marks it occupied, and creates the parking session before committing.

EVs are deliberately handled as a strict compatibility rule: an EV can only receive an EV spot. Compact and standard vehicles can use compact or standard spaces. If no compatible spot exists, the API returns a conflict instead of silently assigning an unsuitable space. The API also rejects a plate that already has an active session.

## Fee calculation

At checkout, the elapsed stay is converted into billable hours using a ceiling operation. That means a stay of 20 minutes is charged as one hour, while a stay of 1 hour and 5 minutes is charged as two hours. The first hour uses the garage's first-hour rate, later hours use the cheaper additional-hour rate, and each complete day is limited by the daily cap.

The final fee is written to the completed session. This preserves the original transaction even after the spot becomes available again and gives the attendant a useful history for searching and sorting.

## Interface choices

I combined the product landing page and the attendant dashboard into one application. The top of the page explains who Auriga is for and what it solves. After signing in, the attendant can see current capacity, including EV availability, check in a vehicle, search by plate or driver, sort the log, paginate through older records, and check vehicles out.

The dashboard does not use demo data after login. It reads its metrics and parking sessions from the REST API, which keeps the visible state tied to the database and makes the interface representative of the actual product.

## Testing

I first checked that the backend imported correctly and could create its schema:

```powershell
py -c "import server; server.init_db(); print('schema ok')"
```

Then I ran the server and tested the main workflow over HTTP with a fresh account. The test covered registration, login, dashboard loading, EV check-in, searching for the generated plate, and checkout. The EV was assigned an EV spot, the search returned one matching session, and checkout returned a one-hour fee of 80 pence.

I also ran `py -m py_compile server.py` and checked the backend for editor diagnostics. Both checks completed without errors.

## What I would improve next

For a production deployment, I would move the database to a managed service if multiple garage sites needed to write concurrently, add HTTPS and stronger session controls, add database migrations, and introduce structured logging and rate limiting. I would also add automated tests around fee boundaries, daily-cap behavior, concurrent check-ins, and a full browser test suite. Those improvements are valuable, but the current implementation keeps the submission compact and runnable with no external dependencies.
