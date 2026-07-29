from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ai_assistant import services
from apps.ai_assistant.models import ChatSession
from apps.ai_assistant.serializers import ChatMessageSerializer, ChatSessionSerializer, SendMessageSerializer
from apps.core.permissions import IsPatient

TAG = "AI Assistant"


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
    create=extend_schema(tags=[TAG]),
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

    @extend_schema(tags=[TAG], request=SendMessageSerializer, responses=ChatMessageSerializer)
    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, pk=None):
        session = self.get_object()
        if request.method == "GET":
            return Response(ChatMessageSerializer(session.messages.all(), many=True).data)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assistant_message = services.send_message(session=session, content=serializer.validated_data["content"])
        return Response(ChatMessageSerializer(assistant_message).data, status=status.HTTP_201_CREATED)
