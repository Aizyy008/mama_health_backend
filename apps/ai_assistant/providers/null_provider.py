from apps.ai_assistant.exceptions import AIAssistantUnavailable
from apps.ai_assistant.providers.base import AIProviderAdapter


class NullAIProvider(AIProviderAdapter):
    """Used when AI_PROVIDER/AI_API_KEY aren't set — the Flutter dev can
    still build and test the chat UI against a stable 503 contract before
    the client supplies real credentials."""

    def generate_reply(self, messages, language):
        raise AIAssistantUnavailable()
