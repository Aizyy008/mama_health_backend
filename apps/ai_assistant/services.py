from apps.ai_assistant.models import ChatMessage
from apps.ai_assistant.providers.factory import get_ai_provider

HISTORY_WINDOW = 20


def send_message(*, session, content: str) -> ChatMessage:
    ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=content)

    recent = list(
        session.messages.order_by("-created_at").values("role", "content")[:HISTORY_WINDOW]
    )
    recent.reverse()

    reply_text = get_ai_provider().generate_reply(recent, session.language)
    return ChatMessage.objects.create(session=session, role=ChatMessage.Role.ASSISTANT, content=reply_text)
