import math
import re

RATE_ALIASES = {
    "compact": ("compact", "compact car", "mini", "small"),
    "standard": ("standard", "regular", "mid", "midsize"),
    "ev": ("ev", "electric", "charger", "electric vehicle"),
}


def calculate_fee_for_rates(rates, start, end):
    total_seconds = max(0, (end - start).total_seconds())
    hours = max(1, math.ceil(total_seconds / 3600))
    full_days, remaining_hours = divmod(hours, 24)
    if remaining_hours == 0:
        partial = rates["daily_cap"]
    else:
        partial = min(
            rates["daily_cap"],
            rates["first_hour_rate"]
            + max(0, remaining_hours - 1) * rates["additional_hour_rate"],
        )
    return full_days * rates["daily_cap"] + partial, hours


def calculate_fee(garage, start, end):
    return calculate_fee_for_rates(
        {
            "first_hour_rate": garage["first_hour_rate"],
            "additional_hour_rate": garage["additional_hour_rate"],
            "daily_cap": garage["daily_cap"],
        },
        start,
        end,
    )


def get_garage_rates(db, garage_id, vehicle_type):
    row = db.execute(
        "SELECT * FROM spot_rate_cards WHERE garage_id = ? AND spot_type = ?",
        (garage_id, vehicle_type),
    ).fetchone()
    if row:
        return {
            "first_hour_rate": row["first_hour_rate"],
            "additional_hour_rate": row["additional_hour_rate"],
            "daily_cap": row["daily_cap"],
        }
    garage = db.execute("SELECT * FROM garages WHERE id = ?", (garage_id,)).fetchone()
    return {
        "first_hour_rate": garage["first_hour_rate"],
        "additional_hour_rate": garage["additional_hour_rate"],
        "daily_cap": garage["daily_cap"],
    }


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
    text = raw_rates.lower()
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
