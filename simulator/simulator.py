import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

REGION = "eu-west-1"

BUILDINGS = {
    "Library-A": ["A101", "A203", "A305"],
    "Lab-B": ["B101", "B102", "B204"],
    "Admin-C": ["C001", "C102"],
}

UNITS = {
    "occupancy": "people",
    "temperature": "celsius",
    "humidity": "percent",
    "energy": "kwh",
    "equipment": "status",
}


def login(client_id, username, password):
    """Log in to Cognito and return the ID token."""
    body = json.dumps({
        "AuthFlow": "USER_PASSWORD_AUTH",
        "ClientId": client_id,
        "AuthParameters": {"USERNAME": username, "PASSWORD": password},
    }).encode()
    request = urllib.request.Request(
        "https://cognito-idp.%s.amazonaws.com/" % REGION,
        data=body,
        headers={
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())["AuthenticationResult"]["IdToken"]
    except urllib.error.HTTPError as error:
        print("Login failed:", error.read().decode())
        sys.exit(1)


def make_event(abnormal_rate):
    """Build one fake campus event. Some are abnormal on purpose."""
    kind = random.choice(list(UNITS))
    building = random.choice(list(BUILDINGS))
    room = random.choice(BUILDINGS[building])
    abnormal = random.random() < abnormal_rate

    if kind == "occupancy":
        value = random.randint(51, 120) if abnormal else random.randint(0, 45)
    elif kind == "temperature":
        if abnormal:
            value = round(random.choice([random.uniform(29, 40), random.uniform(5, 15)]), 1)
        else:
            value = round(random.uniform(18, 26), 1)
    elif kind == "humidity":
        value = random.randint(71, 95) if abnormal else random.randint(30, 60)
    elif kind == "energy":
        value = random.randint(101, 300) if abnormal else random.randint(20, 95)
    else:
        value = 1 if abnormal else 0

    return {
        "event_id": "evt-" + uuid.uuid4().hex[:12],
        "building": building,
        "room": room,
        "event_type": kind,
        "value": value,
        "unit": UNITS[kind],
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def send_event(api_url, token, event):
    """POST one event. Returns (status code, response text)."""
    request = urllib.request.Request(
        api_url.rstrip("/") + "/events",
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json", "Authorization": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except urllib.error.URLError as error:
        return 0, str(error.reason)


def main():
    parser = argparse.ArgumentParser(description="CampusPulse event simulator")
    parser.add_argument("--interval", type=float, default=2, help="seconds between events")
    parser.add_argument("--number-of-events", type=int, default=0, help="stop after N events (0 = run until Ctrl+C)")
    parser.add_argument("--abnormal-rate", type=float, default=0.1, help="share of abnormal events, 0 to 1")
    args = parser.parse_args()

    api_url = os.environ.get("API_URL")
    client_id = os.environ.get("CLIENT_ID")
    password = os.environ.get("SIM_PASSWORD")
    username = os.environ.get("SIM_USER", "sim1")
    if not (api_url and client_id and password):
        print("Set API_URL, CLIENT_ID and SIM_PASSWORD first.")
        sys.exit(1)

    token = login(client_id, username, password)
    print("Logged in as", username)

    sent = 0
    try:
        while args.number_of_events == 0 or sent < args.number_of_events:
            event = make_event(args.abnormal_rate)
            status, text = send_event(api_url, token, event)
            if status == 401:
                token = login(client_id, username, password)
                status, text = send_event(api_url, token, event)
            summary = "%s/%s %s=%s" % (event["building"], event["room"], event["event_type"], event["value"])
            print(status, summary, "->", text)
            sent += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped after", sent, "events")


if __name__ == "__main__":
    main()