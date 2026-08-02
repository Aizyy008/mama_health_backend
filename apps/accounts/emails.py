from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_transactional_email(*, subject: str, template_name: str, context: dict, to: str, plain_message: str) -> None:
    """
    Sends a branded HTML transactional email with a plain-text fallback
    (required for deliverability/spam scoring and for text-only clients).
    `template_name` is a path under templates/emails/, e.g. "emails/verify_email.html".
    """
    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
    )
    email.attach_alternative(render_to_string(template_name, context), "text/html")
    email.send()
