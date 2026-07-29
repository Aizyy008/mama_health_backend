import logging

from django.conf import settings

from apps.ai_assistant.exceptions import AIAssistantUnavailable
from apps.ai_assistant.providers.base import AIProviderAdapter
from apps.ai_assistant.providers.prompts import build_system_prompt

logger = logging.getLogger(__name__)


class GeminiProvider(AIProviderAdapter):
    def __init__(self):
        from google import genai

        self.client = genai.Client(api_key=settings.AI_API_KEY)
        self.model = settings.AI_MODEL_NAME or "gemini-2.0-flash"

    def generate_reply(self, messages, language):
        from google.genai import types

        try:
            history = [
                types.Content(
                    role="user" if m["role"] == "user" else "model",
                    parts=[types.Part(text=m["content"])],
                )
                for m in messages[:-1]
            ]
            chat = self.client.chats.create(
                model=self.model,
                config=types.GenerateContentConfig(system_instruction=build_system_prompt(language)),
                history=history,
            )
            response = chat.send_message(messages[-1]["content"])
            return response.text
        except Exception as exc:
            logger.exception("Gemini request failed")
            raise AIAssistantUnavailable() from exc
