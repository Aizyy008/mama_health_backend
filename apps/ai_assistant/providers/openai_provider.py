import logging

from django.conf import settings

from apps.ai_assistant.exceptions import AIAssistantUnavailable
from apps.ai_assistant.providers.base import AIProviderAdapter
from apps.ai_assistant.providers.prompts import build_system_prompt

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProviderAdapter):
    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.AI_API_KEY)
        self.model = settings.AI_MODEL_NAME or "gpt-4o-mini"

    def generate_reply(self, messages, language):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": build_system_prompt(language)}, *messages],
            )
            return response.choices[0].message.content
        except Exception as exc:
            logger.exception("OpenAI request failed")
            raise AIAssistantUnavailable() from exc
