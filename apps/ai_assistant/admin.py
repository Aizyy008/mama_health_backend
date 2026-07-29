from django.contrib import admin

from apps.ai_assistant.models import ChatMessage, ChatSession


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ["patient", "language", "title", "created_at"]
    search_fields = ["patient__email"]
    inlines = [ChatMessageInline]
