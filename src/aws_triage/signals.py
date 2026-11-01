"""Classify log observations without treating every keyword as a failure."""

import json
import re

PATTERNS = {
    "access_denied": re.compile(r"AccessDenied(?:Exception)?|not authorized to perform", re.I),
    "timeout": re.compile(r"timed?\s*out|ETIMEDOUT|TimeoutError", re.I),
    "resource_missing": re.compile(r"ResourceNotFoundException"),
    "exception": re.compile(r"Traceback \(most recent call last\)|Unhandled\s+exception", re.I),
}
ERROR_CODES = {"AccessDenied": "access_denied", "AccessDeniedException": "access_denied",
               "ResourceNotFoundException": "resource_missing", "TimeoutError": "timeout",
               "ETIMEDOUT": "timeout"}


def classify(message):
    """Return verified-context signal names, safe details, and a mention flag.

    'Verified context' means a structured failure event or an error-level log,
    not proof that the application failed or that a particular policy denied it.
    """
    try:
        structured = json.loads(message[message.index("{"):])
    except (ValueError, TypeError):
        structured = {}
    if not isinstance(structured, dict):
        structured = {}
    level = str(structured.get("level", structured.get("levelname", ""))).upper()
    prefix = re.match(r"^\s*\[?(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\b", message, re.I)
    if prefix:
        level = prefix.group(1).upper()
    matches = {name for name, pattern in PATTERNS.items() if pattern.search(message)}
    event = structured.get("event")
    signals = set()
    if level not in {"INFO", "DEBUG", "WARN", "WARNING"}:
        if event == "application_exception":
            signals.add("exception")
        elif event == "dependency_failure":
            code = structured.get("error_code")
            name = ERROR_CODES.get(code) if isinstance(code, str) else None
            if name:
                signals.add(name)
        if level in {"ERROR", "CRITICAL", "FATAL"}:
            signals.update(matches)
        elif not structured and message.lstrip().startswith("Traceback (most recent call last)"):
            signals.add("exception")
    details = {}
    for field, pattern in {"request_id": r"[A-Za-z0-9-]{1,64}", "target": r"[A-Za-z0-9_.-]{3,255}",
                           "operation": r"PutItem", "error_code": r"[A-Za-z]{1,64}",
                           "trace_id": r"1-[0-9a-f]{8}-[0-9a-f]{24}"}.items():
        value = structured.get(field)
        if isinstance(value, str) and re.fullmatch(pattern, value):
            details[field] = value
    return signals, details, bool(matches and not signals)
