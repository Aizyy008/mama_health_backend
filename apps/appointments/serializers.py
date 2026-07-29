from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import BriefUserSerializer
from apps.appointments.models import Appointment
from apps.core.constants import Role


class AppointmentSerializer(serializers.ModelSerializer):
    patient = BriefUserSerializer(read_only=True)
    doctor = BriefUserSerializer(read_only=True)
    doctor_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=Role.DOCTOR), source="doctor", write_only=True
    )
    patient_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=Role.PATIENT),
        source="patient",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Appointment
        fields = [
            "id",
            "patient",
            "doctor",
            "doctor_id",
            "patient_id",
            "appointment_type",
            "scheduled_at",
            "duration_minutes",
            "status",
            "meeting_link",
            "reason",
            "doctor_notes",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "meeting_link", "cancellation_reason", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context["request"]
        if request.user.role != Role.PATIENT and "patient" not in attrs:
            raise serializers.ValidationError(
                {"patient_id": "Required when booking on behalf of a patient."}
            )
        return attrs

    def create(self, validated_data):
        from apps.appointments import services

        return services.book_appointment(**validated_data)


class AppointmentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Appointment.Status.choices)
    cancellation_reason = serializers.CharField(required=False, allow_blank=True, default="")


class AppointmentDoctorNotesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ["doctor_notes"]
