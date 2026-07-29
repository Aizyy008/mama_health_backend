import json
import logging

from django.conf import settings

from apps.notifications.adapters.base import PushNotificationAdapter

logger = logging.getLogger(__name__)


class FCMPushAdapter(PushNotificationAdapter):
    def __init__(self):
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(json.loads(settings.FCM_CREDENTIALS_JSON))
            firebase_admin.initialize_app(cred)

    def send(self, user, title, body, data):
        if not user.fcm_device_token:
            return False
        from firebase_admin import messaging

        try:
            messaging.send(
                messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    data={k: str(v) for k, v in (data or {}).items()},
                    token=user.fcm_device_token,
                )
            )
            return True
        except Exception:
            logger.exception("FCM push failed for user %s", user.id)
            return False
