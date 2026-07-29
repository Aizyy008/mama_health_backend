from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ai_assistant import services
from apps.ai_assistant.models import ChatSession
from apps.ai_assistant.serializers import ChatMessageSerializer, ChatSessionSerializer, SendMessageSerializer
from apps.core.permissions import IsPatient
from apps.core.serializers import DetailResponseSerializer

TAG = "AI Assistant"


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List my chat sessions",
        examples=[OpenApiExample("200 OK", value={"count": 1, "next": None, "previous": None, "results": [{"id": 6, "language": "en", "title": "Third trimester questions", "created_at": "2026-07-29T12:00:00Z"}]}, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(
        tags=[TAG],
        summary="Get a single chat session",
        examples=[OpenApiExample("200 OK", value={"id": 6, "language": "en", "title": "Third trimester questions", "created_at": "2026-07-29T12:00:00Z"}, response_only=True, status_codes=["200"])],
    ),
    create=extend_schema(
        tags=[TAG],
        summary="Start a new chat session",
        description="Patient-only (the AI Assistant is a Patient App feature). `language` (`en`|`ur`) is set once per session and passed to the AI provider as a system-prompt instruction — it is not a separate translation step, and cannot be changed mid-session (start a new session to switch).",
        examples=[
            OpenApiExample("Request", value={"language": "en", "title": "Third trimester questions"}, request_only=True),
            OpenApiExample("201 Created", value={"id": 6, "language": "en", "title": "Third trimester questions", "created_at": "2026-07-29T12:00:00Z"}, response_only=True, status_codes=["201"]),
        ],
    ),
)
class ChatSessionViewSet(viewsets.ModelViewSet):
    """Patient-only — the AI Pregnancy Assistant is a Patient App feature only."""

    serializer_class = ChatSessionSerializer
    queryset = ChatSession.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsPatient]
    http_method_names = ["get", "post", "head", "options"]
    throttle_scope = "ai_assistant"

    def get_queryset(self):
        return ChatSession.objects.filter(patient=self.request.user)

    def perform_create(self, serializer):
        serializer.save(patient=self.request.user)

    @extend_schema(
        tags=[TAG],
        summary="Get history / send a message",
        description=(
            "**GET**: full message history for this session, chronological. **POST**: send a "
            "patient message — persists it, calls the configured AI provider (OpenAI or Gemini, "
            "whichever `AI_PROVIDER` is set to) with recent context + the session's language, "
            "persists and returns the assistant's reply. Throttled at 20/hour (LLM calls cost "
            "money). Returns `503` (not a raw error) if no AI provider is configured yet — treat "
            "that as 'assistant temporarily unavailable' in the UI, not a bug. This is a general "
            "pregnancy-info assistant, not a diagnostic tool — for urgent symptoms the assistant "
            "itself is instructed to tell the user to contact their doctor or use Emergency SOS."
        ),
        request=SendMessageSerializer,
        responses={200: ChatMessageSerializer(many=True), 201: ChatMessageSerializer, 503: DetailResponseSerializer},
        examples=[
            OpenApiExample("POST request", value={"content": "Is it normal to feel more tired in the third trimester?"}, request_only=True),
            OpenApiExample(
                "201 Created (POST response — the assistant's reply)",
                value={"id": 23, "role": "assistant", "content": "Yes, increased fatigue in the third trimester is very common...", "created_at": "2026-07-29T12:05:00Z"},
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "200 OK (GET response — full history)",
                value=[
                    {"id": 22, "role": "user", "content": "Is it normal to feel more tired in the third trimester?", "created_at": "2026-07-29T12:04:55Z"},
                    {"id": 23, "role": "assistant", "content": "Yes, increased fatigue in the third trimester is very common...", "created_at": "2026-07-29T12:05:00Z"},
                ],
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample("503 AI provider not configured", value={"detail": "The AI assistant is temporarily unavailable. Please try again later.", "errors": None}, response_only=True, status_codes=["503"]),
        ],
    )
    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, pk=None):
        session = self.get_object()
        if request.method == "GET":
            return Response(ChatMessageSerializer(session.messages.all(), many=True).data)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assistant_message = services.send_message(session=session, content=serializer.validated_data["content"])
        return Response(ChatMessageSerializer(assistant_message).data, status=status.HTTP_201_CREATED)
