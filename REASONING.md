# Reasoning

## Business need

A busy car park has to answer a few questions quickly: which spaces are free, where a vehicle is parked, how long it has stayed, and what it should pay. Handling this with paper notes or separate spreadsheets can cause double-booked spaces, lost vehicle details, incorrect fees, and a difficult shift handover.

Auriga is designed to give attendants one reliable place to manage those tasks. The system needs to be quick at the barrier, strict about parking rules, and clear enough that another person can understand the current state of the garage. It also needs to keep a history of completed sessions so the business has a useful record of vehicles and payments.

## Technology stack

This was built to stay simple and reliable. The technology stack is:

- **Python 3** for the backend because it is readable, dependable, and available without extra packages.
- **ThreadingHTTPServer** from Python's standard library to serve the API and frontend from one process.
- **SQLite** for storage because the app needs real persistence and safe transactions, but not a separate database server.
- **HTML, CSS, and vanilla JavaScript** for the frontend because the dashboard is small, fast, and does not need a large framework.
- **JSON REST endpoints** to connect the browser to the backend in a clear way.
- **Bearer tokens** for login sessions so protected parking operations require an authenticated user.

I chose this stack because it is easy to run, easy to explain, and easy to test. A new user can start the whole system with one Python command, while the structure is still strong enough for check-ins, billing, and daily operations. Avoiding external packages also makes the project easier to install on a small office computer or in a classroom environment.

## Users and workflow

The main user is a parking attendant. Their normal workflow is:

1. Sign in to protect garage operations from unauthorised users.
2. Check a vehicle in by entering its plate, driver name, and vehicle type.
3. Give the driver a compatible space number.
4. Search the parking log when a driver returns or asks where a vehicle is located.
5. Check the vehicle out and collect the calculated fee.
6. Use the overnight close, rate import, or plate transfer tools when the shift requires them.

The garage manager benefits from the same workflow because the dashboard shows capacity, active vehicles, overdue sessions, rates, and completed records without needing a separate reporting system.

## Business logic

### Space assignment

Every space has a type: compact, standard, or EV. EV vehicles can only use EV spaces because they may need a charger. Compact and standard vehicles can use either a compact or standard space. The system prefers the same type where possible, then uses another compatible space.

The plate is normalised to uppercase and an active plate cannot be checked in twice. If there is no compatible space, the operation fails with a clear error instead of assigning the wrong space.

### Preventing double booking

Finding a free space and marking it occupied must happen as one database operation. Check-in starts an immediate SQLite transaction, selects an available compatible space, marks it occupied, and creates the session before committing. This prevents two attendants or two browser requests from receiving the same space.

### Pricing and billing

Each garage has rates for the first hour, additional hours, and a daily maximum. Any part of an hour is rounded up, so a stay of 20 minutes is charged as one hour. Later hours use the additional-hour rate, and each 24-hour period is limited by the daily cap.

The fee is calculated at checkout and stored on the completed session. This is important because the record should keep the amount that was actually charged even after the space becomes available again.

### Checkout and capacity

Checkout only works for an active session. It calculates the fee, records the checkout time, changes the session to completed, and frees the assigned space. The dashboard then shows the updated capacity and active vehicle count.

### Nightly close

The nightly clock finds active sessions that have been parked for at least 24 hours. It calculates their fee using the same billing rules, completes them, and releases their spaces. This prevents forgotten sessions from remaining active forever and gives staff a clear way to close the previous day's work.

### Plate transfer

Sometimes a valet handoff or registration correction happens after check-in. A transfer updates the plate, and optionally the driver name, while keeping the same space and original check-in time. The new plate is checked against other active sessions so two live vehicles cannot share the same identifier.

### Rate-card cleaning

Rate cards do not always arrive in one clean format. The import accepts labels such as `compact`, `standard`, and `EV`, and values such as `£2.80`, `310p`, or `4.40 GBP`. The server extracts valid values, converts them to pence, derives additional-hour and daily-cap values, and stores the result per garage and vehicle type. Invalid lines are ignored rather than being written as unreliable prices.

## Data and API flow

The browser sends JSON requests to the Python server. The server authenticates the request, validates the input, applies the business rule, updates SQLite, and returns JSON for the dashboard to display.

SQLite stores users, login tokens, garages, spaces, rate cards, and parking sessions. The important relationships are that a garage owns its spaces and rates, and a parking session records the space used by one vehicle. Completed sessions remain in the database as history instead of being deleted.

This separation keeps the rules in the backend rather than trusting the browser. The frontend is responsible for collecting input and showing results, but the server remains responsible for authentication, space safety, pricing, and data consistency.

The main rules are the important part: compatible spot assignment, safe transactions, and fair billing. That’s why the app stores rates and spot ownership in SQLite, and why check-in uses an immediate transaction before marking a space occupied.

The extra twists fit the same pattern. A messy rate card gets cleaned before writing to the database, the nightly clock closes any session parked longer than a day, and a transfer keeps the same spot and check-in time while updating the plate.

## Why the interface is simple

The dashboard is intentionally thin and practical. An attendant is usually working quickly, so the main screen shows capacity, check-in, the parking log, and operational controls without unnecessary pages. Search, sorting, and pagination make older records easy to find without loading the whole history at once.

The landing page explains the product, while the protected dashboard handles real garage work. This keeps public information separate from private operational data.

## Limits and next steps

The current design is a good fit for one local garage or a small demonstration. For a larger production system, I would add database migrations, automated tests for billing boundaries and concurrent check-ins, HTTPS, stronger token expiry, user roles, audit logs, and support for multiple garages in the same account. Those changes would improve scale and security without changing the main business rules.

I kept the implementation small enough to read and debug in one sitting, but flexible enough to extend if the garage grows.
