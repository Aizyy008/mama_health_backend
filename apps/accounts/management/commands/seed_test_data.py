from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import DoctorProfile, PatientProfile, User
from apps.ai_assistant.models import ChatMessage, ChatSession
from apps.appointments import services as appointment_services
from apps.appointments.models import Appointment
from apps.core.constants import Role
from apps.diet import services as diet_services
from apps.diet.models import DietPlan
from apps.emergency.models import EmergencySOSEvent
from apps.health.models import (
    BloodPressureReading,
    BloodSugarReading,
    ExerciseVideo,
    KickCountSession,
    KickEvent,
    SurgicalProcedureRecord,
    SymptomLog,
    SymptomType,
    WaterIntakeEntry,
)
from apps.medicines.models import MedicineIntakeLog, MedicineReminder
from apps.notifications import services as notification_services

TEST_PASSWORD = "TestPass123!"


class Command(BaseCommand):
    help = (
        "Seeds local-dev test accounts (patient/doctor/admin, pre-verified) plus sample data "
        "across every app, so a frontend developer can start integrating immediately without "
        "the email verification flow. Refuses to run unless DEBUG=True."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_test_data only runs when DEBUG=True (local/dev) — refusing to run against production."
            )

        patient = self._seed_user(
            email="patient@test.com",
            role=Role.PATIENT,
            first_name="Sara",
            last_name="Ahmed",
            phone_number="+923001234567",
        )
        doctor = self._seed_user(
            email="doctor@test.com",
            role=Role.DOCTOR,
            first_name="Ayesha",
            last_name="Malik",
            phone_number="+923009876543",
        )
        self._seed_user(
            email="admin@test.com",
            role=Role.ADMIN,
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_superuser=True,
        )

        PatientProfile.objects.update_or_create(
            user=patient,
            defaults=dict(
                date_of_birth=date(1995, 6, 20),
                lmp_date=date.today() - timedelta(weeks=12),
                blood_group="O+",
                emergency_contact_name="Ahmed Khan",
                emergency_contact_phone="+923001112222",
                address="House 12, Street 5, Karachi",
                profile_complete=True,
            ),
        )
        DoctorProfile.objects.update_or_create(
            user=doctor,
            defaults=dict(
                specialization="OB-GYN",
                license_number="PMC-12345",
                years_of_experience=8,
                bio="Board-certified obstetrician with 8 years of experience.",
                is_accepting_patients=True,
            ),
        )

        self._seed_appointments(patient, doctor)
        self._seed_health_data(patient)
        self._seed_diet_plan(patient, doctor)
        self._seed_medicine_reminder(patient)
        self._seed_notifications(patient, doctor)
        self._seed_exercise_videos()
        self._seed_chat_session(patient)
        self._seed_emergency_event(patient)

        self.stdout.write(
            self.style.SUCCESS(
                "\nSeeded test accounts (same password for all): "
                f"{TEST_PASSWORD}\n"
                "  patient@test.com  (Sara Ahmed)\n"
                "  doctor@test.com   (Dr. Ayesha Malik)\n"
                "  admin@test.com    (Admin User)\n"
            )
        )

    def _seed_user(self, *, email, role, **extra):
        user, _ = User.objects.get_or_create(email=email, defaults={"role": role})
        user.role = role
        user.is_email_verified = True
        for key, value in extra.items():
            setattr(user, key, value)
        user.set_password(TEST_PASSWORD)
        user.save()
        return user

    def _seed_appointments(self, patient, doctor):
        if Appointment.objects.filter(patient=patient, doctor=doctor).exists():
            return

        upcoming = appointment_services.book_appointment(
            patient=patient,
            doctor=doctor,
            appointment_type="in_person",
            scheduled_at=timezone.now() + timedelta(days=3),
            reason="Routine 20-week checkup",
        )
        appointment_services.transition_status(appointment=upcoming, new_status="confirmed", actor=doctor)

        past = appointment_services.book_appointment(
            patient=patient,
            doctor=doctor,
            appointment_type="in_person",
            scheduled_at=timezone.now() - timedelta(days=10),
            reason="First trimester consultation",
        )
        appointment_services.transition_status(appointment=past, new_status="confirmed", actor=doctor)
        appointment_services.transition_status(appointment=past, new_status="completed", actor=doctor)

    def _seed_health_data(self, patient):
        if not BloodPressureReading.objects.filter(patient=patient).exists():
            BloodPressureReading.objects.create(patient=patient, systolic=118, diastolic=76, pulse=72, notes="Felt fine")
            BloodPressureReading.objects.create(
                patient=patient, systolic=122, diastolic=80, pulse=75, recorded_at=timezone.now() - timedelta(days=3)
            )

        if not BloodSugarReading.objects.filter(patient=patient).exists():
            BloodSugarReading.objects.create(patient=patient, value_mg_dl=95, reading_context="fasting")
            BloodSugarReading.objects.create(
                patient=patient,
                value_mg_dl=110,
                reading_context="post_meal",
                recorded_at=timezone.now() - timedelta(days=1),
            )

        nausea, _ = SymptomType.objects.get_or_create(name="Nausea")
        headache, _ = SymptomType.objects.get_or_create(name="Headache")
        symptom_log, _ = SymptomLog.objects.get_or_create(
            patient=patient, log_date=date.today(), defaults={"notes": "Mild headache in the evening"}
        )
        symptom_log.symptoms.set([nausea, headache])

        if not WaterIntakeEntry.objects.filter(patient=patient).exists():
            WaterIntakeEntry.objects.create(patient=patient, amount_ml=250)
            WaterIntakeEntry.objects.create(patient=patient, amount_ml=500)

        if not KickCountSession.objects.filter(patient=patient).exists():
            session = KickCountSession.objects.create(patient=patient, kick_count=8, ended_at=timezone.now())
            KickEvent.objects.bulk_create([KickEvent(session=session) for _ in range(8)])

        if not SurgicalProcedureRecord.objects.filter(patient=patient).exists():
            SurgicalProcedureRecord.objects.create(
                patient=patient,
                procedure_name="Cerclage",
                procedure_date=date.today() - timedelta(days=60),
                hospital_name="City Maternity Hospital",
                notes="Routine, no complications",
            )

    def _seed_diet_plan(self, patient, doctor):
        if DietPlan.objects.filter(patient=patient).exists():
            return
        diet_services.create_diet_plan(
            patient=patient,
            created_by=doctor,
            hydration_recommendation_ml=2500,
            notes="Increase iron-rich foods this trimester.",
            meals=[
                {"meal_type": "breakfast", "description": "Oatmeal with fruit and a boiled egg"},
                {"meal_type": "lunch", "description": "Grilled chicken, brown rice, steamed vegetables"},
                {"meal_type": "dinner", "description": "Lentil soup with whole-grain bread"},
            ],
            foods_to_avoid=[
                {"food_name": "Raw fish", "reason": "Food safety during pregnancy"},
                {"food_name": "Unpasteurized cheese", "reason": "Listeria risk"},
            ],
        )

    def _seed_medicine_reminder(self, patient):
        reminder, created = MedicineReminder.objects.get_or_create(
            patient=patient,
            medicine_name="Folic Acid",
            defaults=dict(
                dosage="5mg",
                times_per_day=1,
                reminder_times=["08:00"],
                start_date=date.today() - timedelta(days=14),
            ),
        )
        if created:
            MedicineIntakeLog.objects.create(
                reminder=reminder,
                scheduled_for=timezone.now() - timedelta(days=1),
                taken_at=timezone.now() - timedelta(days=1),
                status="taken",
            )
            MedicineIntakeLog.objects.create(
                reminder=reminder, scheduled_for=timezone.now() - timedelta(hours=6), status="skipped"
            )
            MedicineIntakeLog.objects.create(
                reminder=reminder, scheduled_for=timezone.now() + timedelta(hours=2), status="pending"
            )

    def _seed_notifications(self, patient, doctor):
        if patient.notifications.exists():
            return
        notification_services.notify(
            recipient=patient,
            notification_type="appointment",
            title="Upcoming appointment",
            body="You have an appointment with Dr. Ayesha Malik in 3 days.",
            channels=[],
        )
        notification_services.notify(
            recipient=patient,
            notification_type="diet",
            title="Your diet plan was updated",
            body="Your doctor has updated your diet plan.",
            channels=[],
        )
        notification_services.notify(
            recipient=doctor,
            notification_type="appointment",
            title="New appointment booked",
            body="Sara Ahmed booked an appointment with you.",
            channels=[],
        )

    def _seed_exercise_videos(self):
        ExerciseVideo.objects.get_or_create(
            title="Prenatal breathing basics",
            defaults=dict(
                description="A gentle 10-minute breathing routine safe for all trimesters. (placeholder link — replace with real content)",
                category=ExerciseVideo.Category.BREATHING,
                video_url="https://example.com/videos/breathing-basics",
                duration_minutes=10,
            ),
        )
        ExerciseVideo.objects.get_or_create(
            title="Second trimester stretching",
            defaults=dict(
                description="Light stretching routine for the second trimester. (placeholder link — replace with real content)",
                category=ExerciseVideo.Category.EXERCISE,
                video_url="https://example.com/videos/second-trimester-stretch",
                duration_minutes=15,
                trimester=2,
            ),
        )

    def _seed_chat_session(self, patient):
        session, created = ChatSession.objects.get_or_create(
            patient=patient, title="Third trimester questions", defaults={"language": "en"}
        )
        if created:
            ChatMessage.objects.create(
                session=session, role="user", content="Is it normal to feel more tired in the third trimester?"
            )
            ChatMessage.objects.create(
                session=session,
                role="assistant",
                content=(
                    "Yes, increased fatigue in the third trimester is very common. (sample placeholder reply — "
                    "real replies come from the configured AI provider once AI_PROVIDER/AI_API_KEY are set)"
                ),
            )

    def _seed_emergency_event(self, patient):
        EmergencySOSEvent.objects.get_or_create(
            patient=patient,
            notes="Test event — false alarm (seed data)",
            defaults=dict(
                status=EmergencySOSEvent.Status.FALSE_ALARM,
                latitude=24.8607,
                longitude=67.0099,
                resolved_at=timezone.now(),
            ),
        )
