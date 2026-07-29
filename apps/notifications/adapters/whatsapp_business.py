import logging

import requests
from django.conf import settings

from apps.notifications.adapters.base import WhatsAppAdapter

logger = logging.getLogger(__name__)

WHATSAPP_API_URL = "https://graph.facebook.com/v19.0/{phone_number_id}/messages"


class WhatsAppBusinessAPIAdapter(WhatsAppAdapter):
    def send_message(self, phone_number, title, body):
        if not phone_number:
            return False
        url = WHATSAPP_API_URL.format(phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID)
        headers = {"Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": f"{title}\n\n{body}"},
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            return True
        except requests.RequestException:
            logger.exception("WhatsApp send failed for %s", phone_number)
            return False
