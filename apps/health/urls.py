from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.health.views import (
    BabySizeReferenceViewSet,
    BloodPressureReadingViewSet,
    BloodSugarReadingViewSet,
    ExerciseVideoViewSet,
    KickCountSessionViewSet,
    PregnancyProgressView,
    SurgicalProcedureRecordViewSet,
    SymptomLogViewSet,
    WaterIntakeEntryViewSet,
)

router = DefaultRouter()
router.register("blood-pressure", BloodPressureReadingViewSet, basename="blood-pressure")
router.register("blood-sugar", BloodSugarReadingViewSet, basename="blood-sugar")
router.register("symptoms", SymptomLogViewSet, basename="symptom-log")
router.register("water-intake", WaterIntakeEntryViewSet, basename="water-intake")
router.register("kick-sessions", KickCountSessionViewSet, basename="kick-session")
router.register("baby-size", BabySizeReferenceViewSet, basename="baby-size")
router.register("surgical-procedures", SurgicalProcedureRecordViewSet, basename="surgical-procedure")
router.register("exercise-videos", ExerciseVideoViewSet, basename="exercise-video")

urlpatterns = [
    path("pregnancy-progress/", PregnancyProgressView.as_view(), name="pregnancy-progress"),
    *router.urls,
]
