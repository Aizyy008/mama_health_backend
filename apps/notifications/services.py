import logging

from apps.notifications.adapters.factory import get_push_adapter, get_whatsapp_adapter
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


def notify(*, recipient, notification_type, title, body, data=None, channels=("push",)):
    """
    Single call site every other app uses to send a notification. Always
    creates the in-app Notification row first (source of truth for the
    Flutter notifications inbox); push/WhatsApp are best-effort side effects
    that never raise — a delivery failure never breaks the caller's primary
    action (e.g. booking an appointment still succeeds even if push fails).
    """
    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        data=data or {},
    )

    preference = getattr(recipient, "notification_preference", None)
    push_enabled = preference.push_enabled if preference else True
    whatsapp_enabled = preference.whatsapp_enabled if preference else True

    if "push" in channels and push_enabled:
        try:
            notification.channel_push_sent = get_push_adapter().send(recipient, title, body, data or {})
        except Exception:
            logger.exception("Push notification failed for user %s", recipient.id)

    if "whatsapp" in channels and whatsapp_enabled and recipient.phone_number:
        try:
            notification.channel_whatsapp_sent = get_whatsapp_adapter().send_message(
                recipient.phone_number, title, body
            )
        except Exception:
            logger.exception("WhatsApp notification failed for user %s", recipient.id)

    notification.save(update_fields=["channel_push_sent", "channel_whatsapp_sent"])
    return notification
