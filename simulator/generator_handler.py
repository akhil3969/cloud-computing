import os
import time

import boto3

import simulator

ssm = boto3.client("ssm")


def lambda_handler(event, context):
    event = event or {}
    count = min(int(event.get("count", 5)), 30)
    pause = float(event.get("interval", 1))
    abnormal_rate = 1.0 if event.get("abnormal") else float(event.get("abnormal_rate", 0.1))

    password = ssm.get_parameter(
        Name=os.environ["PASSWORD_PARAM"], WithDecryption=True
    )["Parameter"]["Value"]
    try:
        token = simulator.login(os.environ["CLIENT_ID"], os.environ.get("SIM_USER", "sim1"), password)
    except SystemExit:
        return {"error": "login failed"}

    statuses = {}
    for _ in range(count):
        status, _text = simulator.send_event(os.environ["API_URL"], token, simulator.make_event(abnormal_rate))
        statuses[str(status)] = statuses.get(str(status), 0) + 1
        time.sleep(pause)
    return {"sent": count, "statuses": statuses}