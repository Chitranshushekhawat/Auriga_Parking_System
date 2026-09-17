# Auriga Parking

Auriga is a small, practical parking operations app for busy attendant teams. It runs on plain Python, stores live garage data in SQLite, and serves a browser UI from the same process. The idea is simple: check vehicles in, assign the right space, calculate a fair fee, and keep the shift calm.

## Requirements

- Python 3.9 or newer
- A modern browser such as Chrome, Edge, Firefox, or Safari
- No external Python packages are required

SQLite is included with Python, so you do not need to install a separate database server.

## Download the project

### Option 1: Clone with Git

```bash
git clone <repository-url>
cd Auriga_Parking_System
```

Replace `<repository-url>` with the URL of this repository.

### Option 2: Download a ZIP file

1. Download the project ZIP from GitHub.
2. Extract it to a normal folder such as `Documents/Auriga_Parking_System`.
3. Open a terminal in that extracted folder.

The folder you open must contain `server.py` and the `static` folder.

## Check Python

Run one of these commands:

```bash
python --version
```

```bash
python3 --version
```

You should see Python 3.9 or a newer version. If neither command works, install Python from [python.org](https://www.python.org/downloads/) and enable **Add Python to PATH** on Windows during installation.

## Start the application

Open a terminal in the project folder and run the command for your system.

### Windows PowerShell

```powershell
cd "C:\path\to\Auriga_Parking_System"
python server.py
```

If `python` is not recognised, try:

```powershell
py server.py
```

### Windows Command Prompt

```bat
cd C:\path\to\Auriga_Parking_System
python server.py
```

### macOS or Linux

```bash
cd /path/to/Auriga_Parking_System
python3 server.py
```

When it starts successfully, the terminal displays:

```text
Auriga Parking running at http://127.0.0.1:8000
```

Keep this terminal open while using the application. Stop the server with `Ctrl+C`.

## Open the application

On the same computer where the server is running, open this address in your browser:

```text
http://127.0.0.1:8000
```

You can also use:

```text
http://localhost:8000
```

The first startup creates `auriga.db` and seeds a demo garage with compact, standard, and EV spots. Create an account on the page, sign in, and then use the dashboard.

## If you are using GitHub Codespaces

`127.0.0.1` is inside the Codespace, so it may not work in a browser on your personal computer.

1. Start the server in the Codespace terminal.
2. Open the **Ports** panel in VS Code.
3. Find port `8000` or the port you selected.
4. Click the globe icon or **Open in Browser**.
5. Use the generated forwarded URL.

Do not copy an `assets.github.dev` URL. If the forwarded URL returns `401`, sign in to GitHub in the browser or change the port visibility in the Ports panel.

## Use another port

Port `8000` may already be used by another program. Start Auriga on another port instead.

### Windows PowerShell

```powershell
$env:PORT = "8001"
python server.py
```

### Windows Command Prompt

```bat
set PORT=8001 && python server.py
```

### macOS or Linux

```bash
PORT=8001 python3 server.py
```

Then open `http://127.0.0.1:8001` and use the same port in the Codespaces Ports panel if applicable.

## Verify that it is running

Open this health endpoint in the browser:

```text
http://127.0.0.1:8000/api/health
```

You should see:

```json
{"ok": true, "status": "healthy", "service": "auriga-parking"}
```

If the health endpoint works but the page does not, refresh the browser and confirm that you are using the same port shown in the terminal.

## Reset local data

Stop the server first with `Ctrl+C`. Deleting `auriga.db` removes local accounts, sessions, and imported rates. The next startup creates a fresh demo database.

### Windows PowerShell

```powershell
Remove-Item auriga.db
python server.py
```

### Windows Command Prompt

```bat
del auriga.db
python server.py
```

### macOS or Linux

```bash
rm auriga.db
python3 server.py
```

Only reset the database when you are sure you do not need the stored parking history.

## Common problems

### `Address already in use`

Another server is already using port 8000. Stop that process or start Auriga on another port using the commands above.

### Browser says the page cannot be reached

Check that the Python server is still running, then confirm the browser URL uses the same port printed in the terminal. The server must remain running; closing the terminal stops the application.

### `python` or `python3` is not found

Install Python 3.9+ and reopen the terminal. On Windows, try `py server.py`.

### The browser shows a GitHub DNS or `assets.github.dev` error

That is not an Auriga server address. Open the forwarded URL from the VS Code Ports panel instead.

### The page loads but login fails

Create a new account from the registration tab. The password must contain at least six characters. If the database was copied from another computer, check that the server is running from the project folder containing the intended `auriga.db`.

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
