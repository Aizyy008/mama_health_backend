from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler to return a consistent, frontend-
    friendly error envelope: {"detail": <one clear sentence>, "errors": <per-field
    breakdown, or null>}. `detail` is always a specific, actionable message —
    never a generic "invalid input" placeholder — so a client can show it
    directly to the user, while `errors` still carries the full per-field
    breakdown for form highlighting.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and set(data.keys()) == {"detail"}:
        # Already a single clear message: auth failures, permission denials,
        # not-found, throttling, etc. are all phrased clearly at the point
        # they're raised — just normalize the envelope shape.
        response.data = {"detail": data["detail"], "errors": None}
        return response

    response.data = {"detail": _first_readable_message(data), "errors": data}
    return response


def _first_readable_message(data) -> str:
    message = _find_first_message(data)
    if not message:
        return "Please check your input and try again."
    message = str(message).strip()
    if message and message[-1] not in ".!?":
        message += "."
    return message


def _find_first_message(data):
    """Walk a (possibly nested) DRF error structure and return the first
    message string found — dicts and lists both appear for nested/many=True
    serializer errors."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        for item in data:
            found = _find_first_message(item)
            if found:
                return found
        return None
    if isinstance(data, dict):
        for value in data.values():
            found = _find_first_message(value)
            if found:
                return found
        return None
    return None
