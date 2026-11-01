"""Disposable Orders API. Fault selection is deployment configuration, never request input."""

import json
import logging
import os
import re
import time
import uuid

LOG = logging.getLogger("triage_sandbox")
LOG.setLevel(logging.INFO)
_client = None


def emit(level, fields):
    header = os.environ.get("_X_AMZN_TRACE_ID", "")
    match = re.search(r"(?:^|;)Root=(1-[0-9a-f]{8}-[0-9a-f]{24})(?:;|$)", header)
    if match:
        fields = {**fields, "trace_id": match.group(1)}
    LOG.log(level, json.dumps(fields))


def dynamodb():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client("dynamodb", config=Config(
            connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1}))
    return _client


def response(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def handler(event, context):
    request_id = context.aws_request_id
    try:
        if event.get("isBase64Encoded"):
            return response(400, {"error": "Send an unencoded JSON body"})
        body = json.loads(event.get("body") or "{}")
        if (not isinstance(body, dict) or not isinstance(body.get("sku"), str)
                or not 1 <= len(body["sku"]) <= 64
                or type(body.get("quantity")) is not int or not 1 <= body["quantity"] <= 10):
            return response(400, {"error": "Expected sku and integer quantity from 1 to 10"})
    except (ValueError, TypeError):
        return response(400, {"error": "Invalid JSON"})

    try:
        if os.environ.get("FAULT_MODE") == "code_exception":
            raise RuntimeError("Controlled sandbox code regression")
        table = os.environ["ORDERS_TABLE"]
        order_id = str(uuid.uuid4())
        try:
            dynamodb().put_item(TableName=table, Item={
                "order_id": {"S": order_id}, "sku": {"S": body["sku"]},
                "quantity": {"N": str(body["quantity"])},
                "expires_at": {"N": str(int(time.time()) + 3600)},
            })
        except Exception as error:
            code = getattr(error, "response", {}).get("Error", {}).get("Code", type(error).__name__)
            # Exclude the request body, credentials, and SDK error text.
            emit(logging.ERROR, {"event": "dependency_failure", "request_id": request_id,
                                  "dependency": "dynamodb", "operation": "PutItem",
                                  "target": table, "error_code": code})
            return response(502, {"error": "Order storage unavailable", "request_id": request_id})
        emit(logging.INFO, {"event": "order_created", "request_id": request_id})
        return response(201, {"order_id": order_id, "request_id": request_id})
    except Exception as error:
        emit(logging.ERROR, {"event": "application_exception", "request_id": request_id,
                              "error_code": type(error).__name__})
        return response(500, {"error": "Order creation failed", "request_id": request_id})
