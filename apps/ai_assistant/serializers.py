from rest_framework import serializers

from apps.ai_assistant.models import ChatMessage, ChatSession


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ["id", "language", "title", "created_at"]
        read_only_fields = ["created_at"]


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField()
