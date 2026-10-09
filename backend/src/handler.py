import json
import logging
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from event_rules_validation import validate_event, evaluate_rules, compute_stats

logger = logging.getLogger()
logger.setLevel(logging.INFO)

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

READ_ROLES = {"admin", "staff"}
ALL_ROLES = {"admin", "staff", "sensor"}


def to_json(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError("cannot convert " + str(type(value)))


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=to_json),
    }


def get_groups(event):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims") or {}
    raw = claims.get("cognito:groups", "")
    if isinstance(raw, list):
        return set(raw)
    return set(raw.strip("[]").replace(",", " ").split())


def scan_all():
    items = []
    kwargs = {}
    while True:
        result = table.scan(**kwargs)
        items.extend(result["Items"])
        if "LastEvaluatedKey" not in result:
            return items
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]


def post_event(event, groups):
    if not groups & ALL_ROLES:
        return respond(403, {"error": "no valid role"})
    try:
        body = json.loads(event.get("body") or "")
    except ValueError:
        return respond(400, {"error": "body must be valid JSON"})

    clean, errors = validate_event(body)
    if errors:
        return respond(400, {"errors": errors})

    is_request = clean["event_type"] == "service_request"
    allowed = (
        "admin" in groups
        or (is_request and "staff" in groups)
        or (not is_request and "sensor" in groups)
    )
    if not allowed:
        return respond(403, {"error": "your role may not send this event type"})

    severity, is_alert = evaluate_rules(clean)
    item = dict(clean)
    item["value"] = Decimal(str(clean["value"]))
    item["severity"] = severity
    item["ts_id"] = clean["timestamp"] + "#" + clean["event_id"]
    if is_alert:
        item["alert"] = "1"
    table.put_item(Item=item)
    return respond(201, {"message": "stored", "severity": severity, "alert": is_alert})


def get_events(event, groups):
    if not groups & READ_ROLES:
        return respond(403, {"error": "admin or staff only"})
    params = event.get("queryStringParameters") or {}
    building = params.get("building")
    if building:
        result = table.query(
            KeyConditionExpression=Key("building").eq(building),
            ScanIndexForward=False,
            Limit=50,
        )
        items = result["Items"]
    else:
        items = sorted(scan_all(), key=lambda i: i["ts_id"], reverse=True)[:50]
    return respond(200, {"count": len(items), "events": items})


def get_alerts(event, groups):
    if not groups & READ_ROLES:
        return respond(403, {"error": "admin or staff only"})
    result = table.query(
        IndexName="alerts",
        KeyConditionExpression=Key("alert").eq("1"),
        ScanIndexForward=False,
        Limit=50,
    )
    return respond(200, {"count": len(result["Items"]), "alerts": result["Items"]})


def get_stats(event, groups):
    if not groups & READ_ROLES:
        return respond(403, {"error": "admin or staff only"})
    return respond(200, compute_stats(scan_all()))


def lambda_handler(event, context):
    method = event.get("httpMethod")
    path = event.get("path", "")
    groups = get_groups(event)
    logger.info(json.dumps({"method": method, "path": path, "groups": sorted(groups)}))
    try:
        if method == "POST" and path.endswith("/events"):
            return post_event(event, groups)
        if method == "GET" and path.endswith("/events"):
            return get_events(event, groups)
        if method == "GET" and path.endswith("/alerts"):
            return get_alerts(event, groups)
        if method == "GET" and path.endswith("/stats"):
            return get_stats(event, groups)
        return respond(404, {"error": "not found"})
    except Exception:
        logger.exception("unexpected error")
        return respond(500, {"error": "internal error"})