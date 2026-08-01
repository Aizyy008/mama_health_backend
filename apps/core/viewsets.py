from apps.core.constants import Role


class PatientScopedQuerysetMixin:
    """
    Scopes a viewset's queryset by the requesting user's role, for any model
    with a FK to the patient (default field name "patient"):
      - PATIENT: only their own records
      - DOCTOR: only records of patients assigned to them (PatientDoctorAssignment)
      - ADMIN: unrestricted by default, or narrowed to one patient via
        `?patient_id=` (e.g. an admin dashboard viewing a single patient's
        full record — without this, admin would see every patient's rows
        mixed together with no way to filter to just one)
    """

    patient_field_name = "patient"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == Role.PATIENT:
            return qs.filter(**{self.patient_field_name: user})
        if user.role == Role.DOCTOR:
            from apps.appointments.models import PatientDoctorAssignment

            assigned_patient_ids = PatientDoctorAssignment.objects.filter(
                doctor=user
            ).values_list("patient_id", flat=True)
            return qs.filter(**{f"{self.patient_field_name}_id__in": assigned_patient_ids})

        patient_id = self.request.query_params.get("patient_id")
        if patient_id:
            return qs.filter(**{f"{self.patient_field_name}_id": patient_id})
        return qs


class PatientOwnedCreateMixin:
    """
    On create: patients may only create records for themselves (the `patient`
    field is forced, any client-supplied value ignored); doctors must supply
    a `patient` and are validated by the assignment-aware object permission.
    """

    patient_field_name = "patient"

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == Role.PATIENT:
            serializer.save(**{self.patient_field_name: user})
        else:
            serializer.save()
