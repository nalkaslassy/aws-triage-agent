"""Distinguish collection outcomes and bounded transient-read recovery."""

TRANSIENT_ERRORS = {
    "Throttling", "ThrottlingException", "ThrottledException", "TooManyRequestsException", "RequestLimitExceeded",
    "ServiceUnavailable", "ServiceUnavailableException", "InternalError", "InternalFailure", "InternalServerError",
    "EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError", "ConnectionClosedError",
}


def check_outcome(items):
    if not items:
        return "no_evidence"
    statuses = {item.status for item in items}
    if statuses == {"observed"}:
        return "successful"
    if statuses <= {"unavailable", "not_collected"}:
        return "unavailable"
    return "partial"


def retryable(items):
    failures = [e for e in items if e.status != "observed"]
    if not failures:
        return False
    for item in failures:
        codes = item.data.get("error_codes", [])
        if item.data.get("error_code"):
            codes = [*codes, item.data["error_code"]]
        # No retry for permission errors, deadlines, scope failures, pagination
        # limits, or mixtures that include an unknown/non-transient failure.
        if not codes or any(code not in TRANSIENT_ERRORS for code in codes):
            return False
    return True
