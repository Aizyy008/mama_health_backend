from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.appointments.models import PatientDoctorAssignment
from apps.core.permissions import IsAdmin, IsDoctor
from apps.core.serializers import DetailResponseSerializer
from apps.notifications import services
from apps.notifications.models import Notification
from apps.notifications.serializers import BroadcastSerializer, DoctorMessageSerializer, NotificationSerializer
from apps.notifications.tasks import broadcast_notification

TAG = "Notifications"

_NOTIFICATION_RESPONSE_EXAMPLE = {
    "id": 42,
    "notification_type": "appointment",
    "title": "Upcoming appointment",
    "body": "You have an appointment with Dr. Ayesha Malik at 10:30.",
    "data": {"appointment_id": 15},
    "is_read": False,
    "channel_push_sent": True,
    "channel_whatsapp_sent": False,
    "created_at": "2026-07-29T09:30:00Z",
}


@extend_schema_view(
    list=extend_schema(
        tags=[TAG],
        summary="List my notifications (inbox)",
        description=(
            "Own inbox only, newest first. `notification_type` is one of `appointment`, "
            "`medicine`, `diet`, `doctor_message`, `weekly_update`, `emergency`, `broadcast` — "
            "use it to pick an icon/route in the app. `data` is a free-form JSON payload for "
            "deep-linking (e.g. `{\"appointment_id\": 15}` — navigate to that appointment on tap). "
            "`channel_push_sent`/`channel_whatsapp_sent` reflect whether those side-channels also "
            "succeeded — this row itself is always the source of truth regardless."
        ),
        examples=[OpenApiExample("200 OK (one entry)", value=_NOTIFICATION_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"])],
    ),
    retrieve=extend_schema(tags=[TAG], summary="Get a single notification", examples=[OpenApiExample("200 OK", value=_NOTIFICATION_RESPONSE_EXAMPLE, response_only=True, status_codes=["200"])]),
)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()  # for schema introspection only; get_queryset() scopes at runtime
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @extend_schema(
        tags=[TAG],
        summary="Mark one notification as read",
        examples=[OpenApiExample("Request", value={}, request_only=True), OpenApiExample("200 OK", value={**_NOTIFICATION_RESPONSE_EXAMPLE, "is_read": True}, response_only=True, status_codes=["200"])],
    )
    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)

    @extend_schema(
        tags=[TAG],
        summary="Mark all my notifications as read",
        examples=[OpenApiExample("Request", value={}, request_only=True), OpenApiExample("200 OK", value={"detail": "3 notification(s) marked as read."}, response_only=True, status_codes=["200"])],
    )
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"detail": f"{updated} notification(s) marked as read."})


@extend_schema(
    tags=[TAG],
    summary="Broadcast a notification (admin only)",
    description=(
        "Admin-only. Fans out asynchronously via Celery — this endpoint returns `202 Accepted` "
        "immediately, before delivery actually happens, so don't expect the notifications to "
        "exist yet the instant this call returns. `target_role` is optional: omit it (or send "
        "`null`) to reach both patients and doctors; set `\"patient\"` or `\"doctor\"` to target "
        "just one role. Admins themselves are never included."
    ),
    responses={202: DetailResponseSerializer},
    examples=[
        OpenApiExample("Request — everyone", value={"title": "Scheduled maintenance", "body": "The app will be briefly unavailable tonight at 11 PM."}, request_only=True),
        OpenApiExample("Request — patients only", value={"title": "New feature: AI Assistant", "body": "You can now chat with our AI pregnancy assistant!", "target_role": "patient"}, request_only=True),
        OpenApiExample("202 Accepted", value={"detail": "Broadcast queued."}, response_only=True, status_codes=["202"]),
    ],
)
class BroadcastView(generics.GenericAPIView):
    serializer_class = BroadcastSerializer
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        broadcast_notification.delay(**serializer.validated_data)
        return Response({"detail": "Broadcast queued."}, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    tags=[TAG],
    summary="Send an ad-hoc message to a patient (doctor only)",
    description="Doctor-only, and only to a patient they're assigned to (403 otherwise). This is the backend for the doc's 'doctor messages' notification type — there is no separate chat/thread model, just one-off notifications.",
    responses={201: NotificationSerializer, 403: DetailResponseSerializer},
    examples=[
        OpenApiExample("Request", value={"patient_id": 2, "title": "Lab results", "body": "Your recent lab results look good — no action needed. See you at your next appointment."}, request_only=True),
        OpenApiExample("201 Created", value={**_NOTIFICATION_RESPONSE_EXAMPLE, "notification_type": "doctor_message", "title": "Lab results", "body": "Your recent lab results look good — no action needed. See you at your next appointment.", "data": {"from_doctor_id": 4}}, response_only=True, status_codes=["201"]),
        OpenApiExample("403 Not assigned", value={"detail": "You are not assigned to this patient.", "errors": None}, response_only=True, status_codes=["403"]),
    ],
)
class SendDoctorMessageView(generics.GenericAPIView):
    serializer_class = DoctorMessageSerializer
    permission_classes = [IsDoctor]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = serializer.validated_data["patient_id"]

        if not PatientDoctorAssignment.objects.filter(doctor=request.user, patient=patient).exists():
            return Response(
                {"detail": "You are not assigned to this patient."}, status=status.HTTP_403_FORBIDDEN
            )

        notification = services.notify(
            recipient=patient,
            notification_type="doctor_message",
            title=serializer.validated_data["title"],
            body=serializer.validated_data["body"],
            data={"from_doctor_id": request.user.id},
            channels=["push"],
        )
        return Response(NotificationSerializer(notification).data, status=status.HTTP_201_CREATED)
