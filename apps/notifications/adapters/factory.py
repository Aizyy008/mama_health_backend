from django.conf import settings


def get_push_adapter():
    if settings.FCM_CREDENTIALS_JSON:
        from apps.notifications.adapters.fcm import FCMPushAdapter

        return FCMPushAdapter()
    from apps.notifications.adapters.null import NullPushAdapter

    return NullPushAdapter()


def get_whatsapp_adapter():
    if settings.WHATSAPP_API_TOKEN:
        from apps.notifications.adapters.whatsapp_business import WhatsAppBusinessAPIAdapter

        return WhatsAppBusinessAPIAdapter()
    from apps.notifications.adapters.null import NullWhatsAppAdapter

    return NullWhatsAppAdapter()
