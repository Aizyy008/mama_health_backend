from abc import ABC, abstractmethod


class PushNotificationAdapter(ABC):
    @abstractmethod
    def send(self, user, title: str, body: str, data: dict) -> bool:
        """Returns True if the push was successfully dispatched."""


class WhatsAppAdapter(ABC):
    @abstractmethod
    def send_message(self, phone_number: str, title: str, body: str) -> bool:
        """Returns True if the WhatsApp message was successfully dispatched."""
