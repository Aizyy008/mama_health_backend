from django.db import models

from apps.core.models import TimeStampedModel


class ChatSession(TimeStampedModel):
    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        URDU = "ur", "Urdu"

    patient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="ai_chat_sessions"
    )
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.ENGLISH)
    title = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ChatMessage(TimeStampedModel):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()

    class Meta:
        ordering = ["created_at"]
