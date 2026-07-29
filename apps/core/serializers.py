from rest_framework import serializers

from apps.core.constants import Role


class PatientOwnedModelSerializer(serializers.ModelSerializer):
    """
    Base for any model with a `patient` FK, owned by a specific patient but
    writable by an assigned doctor/admin on the patient's behalf. Adds a
    read-only nested `patient` and a write-only `patient_id`, and requires
    patient_id whenever the actor isn't the patient themselves. Pairs with
    core.viewsets.PatientScopedQuerysetMixin / PatientOwnedCreateMixin.
    """

    def get_fields(self):
        # Lazy import: apps.accounts imports apps.core at module load time
        # (constants, models), so importing apps.accounts here at module
        # level would be circular.
        from apps.accounts.models import User
        from apps.accounts.serializers import BriefUserSerializer

        fields = super().get_fields()
        fields["patient"] = BriefUserSerializer(read_only=True)
        fields["patient_id"] = serializers.PrimaryKeyRelatedField(
            queryset=User.objects.filter(role=Role.PATIENT),
            source="patient",
            write_only=True,
            required=False,
        )
        return fields

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        if user.role != Role.PATIENT and "patient" not in attrs:
            raise serializers.ValidationError(
                {"patient_id": "Required when acting on behalf of a patient."}
            )
        if user.role == Role.DOCTOR and "patient" in attrs:
            # object-level permissions (IsOwnerPatientOrAssignedDoctorOrAdmin)
            # only run on retrieve/update/destroy, never on create — so the
            # assignment check has to happen here, or a doctor could write
            # clinical records for any patient globally.
            from apps.appointments.models import PatientDoctorAssignment

            if not PatientDoctorAssignment.objects.filter(doctor=user, patient=attrs["patient"]).exists():
                raise serializers.ValidationError(
                    {"patient_id": "You are not assigned to this patient."}
                )
        return super().validate(attrs)
