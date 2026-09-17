import os
from http.server import ThreadingHTTPServer

from app.config import DB_PATH, ROOT, STATIC
from app.database import connect, init_db, iso_now, parse_time, row_dict, utc_now
from app.http_handler import Handler

# Keep these imports available for existing scripts that imported server helpers.
__all__ = [
    "DB_PATH",
    "ROOT",
    "STATIC",
    "connect",
    "init_db",
    "iso_now",
    "parse_time",
    "row_dict",
    "utc_now",
    "Handler",
]


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
