from django.conf import settings


def get_ai_provider():
    if settings.AI_PROVIDER == "openai" and settings.AI_API_KEY:
        from apps.ai_assistant.providers.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if settings.AI_PROVIDER == "gemini" and settings.AI_API_KEY:
        from apps.ai_assistant.providers.gemini_provider import GeminiProvider

        return GeminiProvider()
    from apps.ai_assistant.providers.null_provider import NullAIProvider

    return NullAIProvider()
