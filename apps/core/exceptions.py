from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler to return a consistent error
    envelope: {"detail": <message>, "errors": <field errors, if any>}.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        response.data = {"detail": data["detail"], "errors": None}
    else:
        detail = data.get("detail") if isinstance(data, dict) else None
        response.data = {"detail": detail or "Validation failed.", "errors": data}
    return response
