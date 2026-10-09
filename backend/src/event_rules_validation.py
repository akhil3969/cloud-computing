from datetime import datetime

REQUIRED = ["event_id", "building", "room", "event_type", "value", "unit", "timestamp"]

# event_type: (lowest value, highest value, expected unit)
LIMITS = {
    "occupancy": (0, 1000, "people"),
    "temperature": (-10, 60, "celsius"),
    "humidity": (0, 100, "percent"),
    "energy": (0, 100000, "kwh"),
    "equipment": (0, 1, "status"),
    "service_request": (1, 3, "priority"),
}

ROOM_CAPACITY = 50


def validate_event(event):
    """Returns (clean_event, errors). If errors is not empty, reject with 400."""
    if not isinstance(event, dict):
        return None, ["event must be a JSON object"]

    errors = []
    for field in REQUIRED:
        if field not in event or event[field] in (None, ""):
            errors.append("missing field: " + field)
    if errors:
        return None, errors

    for field in ["event_id", "building", "room", "event_type", "unit", "timestamp"]:
        if not isinstance(event[field], str):
            errors.append(field + " must be text")
        elif len(event[field]) > 50:
            errors.append(field + " is too long")
    if errors:
        return None, errors

    event_type = event["event_type"]
    if event_type not in LIMITS:
        return None, ["unknown event_type: " + event_type]

    low, high, unit = LIMITS[event_type]
    value = event["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, ["value must be a number"]
    if not low <= value <= high:
        errors.append("value must be between %s and %s" % (low, high))
    if event["unit"] != unit:
        errors.append("unit for %s must be %s" % (event_type, unit))
    try:
        datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        errors.append("timestamp must look like 2026-10-09T10:30:00Z")
    if errors:
        return None, errors

    # keep only known fields, so a sender cannot add its own "severity"
    clean = {field: event[field] for field in REQUIRED}
    return clean, []


def evaluate_rules(event):
    """Returns (severity, is_alert)."""
    kind = event["event_type"]
    value = event["value"]
    if kind == "occupancy" and value > ROOM_CAPACITY:
        return "high", True
    if kind == "temperature" and (value > 28 or value < 16):
        return "medium", True
    if kind == "humidity" and value > 70:
        return "medium", True
    if kind == "energy" and value > 100:
        return "high", True
    if kind == "equipment" and value == 1:
        return "high", True
    if kind == "service_request" and value == 3:
        return "high", True
    return "normal", False

def compute_stats(items):
    """Takes a list of stored events and returns summary numbers."""
    by_type = {}
    by_building = {}
    by_severity = {}
    energy_by_building = {}
    latest_occupancy = {}
    temperatures = []
    alert_count = 0

    for item in items:
        kind = item["event_type"]
        building = item["building"]
        severity = item.get("severity", "normal")
        value = float(item["value"])

        by_type[kind] = by_type.get(kind, 0) + 1
        by_building[building] = by_building.get(building, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1

        if item.get("alert"):
            alert_count += 1
        if kind == "temperature":
            temperatures.append(value)
        if kind == "energy":
            energy_by_building[building] = energy_by_building.get(building, 0) + value
        if kind == "occupancy":
            room_key = building + "/" + item["room"]
            newest = latest_occupancy.get(room_key)
            if newest is None or item["timestamp"] > newest[0]:
                latest_occupancy[room_key] = (item["timestamp"], value)

    average = round(sum(temperatures) / len(temperatures), 1) if temperatures else None
    return {
        "total_events": len(items),
        "by_type": by_type,
        "by_building": by_building,
        "by_severity": by_severity,
        "alert_count": alert_count,
        "average_temperature": average,
        "energy_by_building": energy_by_building,
        "latest_occupancy": {room: pair[1] for room, pair in latest_occupancy.items()},
    }