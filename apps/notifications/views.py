from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.appointments.models import PatientDoctorAssignment
from apps.core.permissions import IsAdmin, IsDoctor
from apps.notifications import services
from apps.notifications.models import Notification
from apps.notifications.serializers import BroadcastSerializer, DoctorMessageSerializer, NotificationSerializer
from apps.notifications.tasks import broadcast_notification

TAG = "Notifications"


@extend_schema_view(
    list=extend_schema(tags=[TAG]),
    retrieve=extend_schema(tags=[TAG]),
)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()  # for schema introspection only; get_queryset() scopes at runtime
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @extend_schema(tags=[TAG])
    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)

    @extend_schema(tags=[TAG])
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"detail": f"{updated} notification(s) marked as read."})


@extend_schema(tags=[TAG])
class BroadcastView(generics.GenericAPIView):
    serializer_class = BroadcastSerializer
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        broadcast_notification.delay(**serializer.validated_data)
        return Response({"detail": "Broadcast queued."}, status=status.HTTP_202_ACCEPTED)


@extend_schema(tags=[TAG])
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
