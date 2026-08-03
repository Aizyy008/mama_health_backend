from django.utils import timezone
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.constants import Role


def has_active_subscription(patient_profile) -> bool:
    """Paid overrides everything; otherwise active while still inside the trial window."""
    if patient_profile.is_paid:
        return True
    if patient_profile.trial_ends_at is None:
        return False
    return timezone.now() < patient_profile.trial_ends_at


class IsPatientSubscriptionActive(BasePermission):
    """
    Soft lock: an expired, unpaid patient can still read everything (so
    their data stays visible with a "please pay" prompt) but can't create/
    update clinical records. Only applies to the PATIENT actor themselves —
    a doctor/admin acting on a patient's behalf is never blocked by that
    patient's subscription status. Emergency SOS is deliberately never
    gated by this (see EmergencySOSViewSet) — safety, not paywalled.
    """

    message = "Your free trial has ended. Please complete payment to continue using this feature."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not (user and user.is_authenticated) or user.role != Role.PATIENT:
            return True
        profile = getattr(user, "patient_profile", None)
        if profile is None:
            return True
        return has_active_subscription(profile)
