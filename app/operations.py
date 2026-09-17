from datetime import timedelta

from .database import parse_time, utc_now
from .pricing import calculate_fee_for_rates, get_garage_rates


def finalize_session(db, session, end=None):
    end = end or utc_now()
    rates = get_garage_rates(db, session["garage_id"], session["vehicle_type"])
    fee, hours = calculate_fee_for_rates(rates, parse_time(session["checked_in_at"]), end)
    db.execute(
        "UPDATE parking_sessions SET status = 'completed', checked_out_at = ?, fee = ? WHERE id = ?",
        (end.isoformat(timespec="seconds"), fee, session["id"]),
    )
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
    return {
        "closed": len(updated),
        "updated": updated,
        "message": f"Closed {len(updated)} overnight session(s)",
    }
