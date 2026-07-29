from rest_framework.exceptions import APIException


class AIAssistantUnavailable(APIException):
    status_code = 503
    default_detail = "The AI assistant is temporarily unavailable. Please try again later."
    default_code = "ai_assistant_unavailable"
