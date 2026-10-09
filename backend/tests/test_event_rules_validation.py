import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from event_rules_validation import validate_event, evaluate_rules, compute_stats


def good(**changes):
    event = {
        "event_id": "evt-1", "building": "Library-A", "room": "A203",
        "event_type": "temperature", "value": 22, "unit": "celsius",
        "timestamp": "2026-10-09T10:30:00Z",
    }
    event.update(changes)
    return event


def test_valid_event():
    clean, errors = validate_event(good())
    assert errors == []
    assert clean["building"] == "Library-A"

def test_missing_field():
    event = good()
    del event["building"]
    clean, errors = validate_event(event)
    assert clean is None and errors

def test_unknown_event_type():
    assert validate_event(good(event_type="banana"))[1]

def test_value_out_of_range():
    assert validate_event(good(value=500))[1]

def test_value_not_a_number():
    assert validate_event(good(value="hot"))[1]

def test_wrong_unit():
    assert validate_event(good(unit="fahrenheit"))[1]

def test_bad_timestamp():
    assert validate_event(good(timestamp="yesterday"))[1]

def test_client_severity_is_ignored():
    clean, errors = validate_event(good(severity="normal"))
    assert errors == [] and "severity" not in clean

def test_normal_temperature():
    assert evaluate_rules(good(value=22)) == ("normal", False)

def test_hot_room_is_alert():
    assert evaluate_rules(good(value=31)) == ("medium", True)

def test_overloaded_room():
    assert evaluate_rules(good(event_type="occupancy", value=80, unit="people")) == ("high", True)

def test_equipment_failure():
    assert evaluate_rules(good(event_type="equipment", value=1, unit="status")) == ("high", True)

def test_urgent_request():
    assert evaluate_rules(good(event_type="service_request", value=3, unit="priority")) == ("high", True)

def test_stats_basic():
    items = [
        {**good(value=20), "severity": "normal"},
        {**good(value=30), "severity": "medium", "alert": "1"},
        {**good(event_type="energy", value=40, unit="kwh"), "severity": "normal"},
        {**good(event_type="occupancy", value=12, unit="people", timestamp="2026-10-09T10:00:00Z"), "severity": "normal"},
        {**good(event_type="occupancy", value=30, unit="people", timestamp="2026-10-09T11:00:00Z"), "severity": "normal"},
    ]
    stats = compute_stats(items)
    assert stats["total_events"] == 5
    assert stats["by_type"]["temperature"] == 2
    assert stats["alert_count"] == 1
    assert stats["average_temperature"] == 25.0
    assert stats["energy_by_building"]["Library-A"] == 40
    assert stats["latest_occupancy"]["Library-A/A203"] == 30

def test_stats_empty():
    stats = compute_stats([])
    assert stats["total_events"] == 0
    assert stats["average_temperature"] is None