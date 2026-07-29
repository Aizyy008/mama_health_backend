import logging

from apps.notifications.adapters.base import PushNotificationAdapter, WhatsAppAdapter

logger = logging.getLogger(__name__)


class NullPushAdapter(PushNotificationAdapter):
    """Used when FCM_CREDENTIALS_JSON isn't set — logs instead of sending,
    so the rest of the system runs end-to-end before real credentials arrive."""

    def send(self, user, title, body, data):
        logger.info("Push notification (no FCM credentials configured): to=%s title=%r", user.email, title)
        return False


class NullWhatsAppAdapter(WhatsAppAdapter):
    def send_message(self, phone_number, title, body):
        logger.info("WhatsApp message (no credentials configured): to=%s title=%r", phone_number, title)
        return False
