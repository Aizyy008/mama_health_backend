from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from apps.ai_assistant.models import ChatMessage, ChatSession

pytestmark = pytest.mark.django_db


class TestSessionAccess:
    def test_only_patient_can_create_session(self, patient_client, doctor_client, admin_client, patient_user):
        assert patient_client.post(reverse("chat-session-list"), {}, format="json").status_code == status.HTTP_201_CREATED
        assert doctor_client.post(reverse("chat-session-list"), {}, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert admin_client.post(reverse("chat-session-list"), {}, format="json").status_code == status.HTTP_403_FORBIDDEN

    def test_session_created_for_requesting_patient(self, patient_client, patient_user):
        resp = patient_client.post(reverse("chat-session-list"), {"language": "ur"}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        session = ChatSession.objects.get(id=resp.data["id"])
        assert session.patient_id == patient_user.id
        assert session.language == "ur"

    def test_patient_cannot_see_another_patients_sessions(self, patient_client, patient_user):
        from apps.accounts.tests.factories import PatientUserFactory

        ChatSession.objects.create(patient=patient_user)
        ChatSession.objects.create(patient=PatientUserFactory())
        resp = patient_client.get(reverse("chat-session-list"))
        assert resp.data["count"] == 1


class TestNullProviderWhenUnconfigured:
    def test_returns_503_when_ai_not_configured(self, patient_client, patient_user):
        # AI_PROVIDER / AI_API_KEY are blank in test settings by default
        session = ChatSession.objects.create(patient=patient_user)
        resp = patient_client.post(
            reverse("chat-session-messages", args=[session.id]), {"content": "Hello"}, format="json"
        )
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        # the user's message is still persisted even though the reply failed
        assert ChatMessage.objects.filter(session=session, role="user", content="Hello").exists()


class TestSendMessageWithMockedProvider:
    def test_persists_user_and_assistant_messages(self, patient_client, patient_user):
        session = ChatSession.objects.create(patient=patient_user)
        with patch("apps.ai_assistant.services.get_ai_provider") as mock_factory:
            mock_factory.return_value.generate_reply.return_value = "You're doing great!"
            resp = patient_client.post(
                reverse("chat-session-messages", args=[session.id]),
                {"content": "Is it normal to feel tired?"},
                format="json",
            )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["role"] == "assistant"
        assert resp.data["content"] == "You're doing great!"

        messages = list(session.messages.order_by("created_at"))
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_provider_receives_language_and_history(self, patient_client, patient_user):
        session = ChatSession.objects.create(patient=patient_user, language="ur")
        ChatMessage.objects.create(session=session, role="user", content="Earlier question")
        ChatMessage.objects.create(session=session, role="assistant", content="Earlier answer")

        with patch("apps.ai_assistant.services.get_ai_provider") as mock_factory:
            mock_factory.return_value.generate_reply.return_value = "New answer"
            patient_client.post(
                reverse("chat-session-messages", args=[session.id]), {"content": "New question"}, format="json"
            )

        call_args = mock_factory.return_value.generate_reply.call_args
        history, language = call_args[0]
        assert language == "ur"
        assert history[-1] == {"role": "user", "content": "New question"}
        assert history[0] == {"role": "user", "content": "Earlier question"}

    def test_list_messages_returns_full_history(self, patient_client, patient_user):
        session = ChatSession.objects.create(patient=patient_user)
        ChatMessage.objects.create(session=session, role="user", content="Hi")
        ChatMessage.objects.create(session=session, role="assistant", content="Hello!")
        resp = patient_client.get(reverse("chat-session-messages", args=[session.id]))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 2

    def test_cannot_send_message_to_another_patients_session(self, patient_client):
        from apps.accounts.tests.factories import PatientUserFactory

        other_session = ChatSession.objects.create(patient=PatientUserFactory())
        resp = patient_client.post(
            reverse("chat-session-messages", args=[other_session.id]), {"content": "Hi"}, format="json"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
