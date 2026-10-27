import logging
import smtplib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import BadHeaderError, send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class PinEmailError(Exception):
    """Error controlado al enviar el correo de recuperación."""


def send_recovery_pin_email(recipient_email: str, pin: str) -> None:
    """
    Envía el PIN recibido del flujo de recuperación.
    No genera, valida ni modifica el PIN.
    """
    if not isinstance(recipient_email, str) or not recipient_email.strip():
        raise ValueError("El correo destinatario es obligatorio.")

    try:
        validate_email(recipient_email)
    except ValidationError as exc:
        raise ValueError("El correo destinatario no es válido.") from exc

    if not isinstance(pin, str) or not pin.strip():
        raise ValueError("El PIN de recuperación es obligatorio.")

    if not settings.EMAIL_HOST_PASSWORD or not settings.EMAIL_HOST_USER:
        raise ImproperlyConfigured(
            "La configuración SMTP está incompleta."
        )

    if not settings.DEFAULT_FROM_EMAIL:
        raise ImproperlyConfigured(
            "No se ha configurado el remitente del correo."
        )

    subject = "SIGECI - Recuperación de cuenta"
    message = (
        "Hola,\n\n"
        f"Tu PIN para continuar con la recuperación de tu cuenta es: {pin}\n\n"
        "Si no solicitaste esta recuperación, puedes ignorar este mensaje.\n"
        "Utiliza el PIN únicamente dentro del proceso de recuperación de SIGECI."
    )

    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
    except (BadHeaderError, smtplib.SMTPException, OSError) as exc:
        logger.warning(
            "Falló el envío del correo de recuperación (tipo=%s).",
            type(exc).__name__,
        )
        raise PinEmailError(
            "No fue posible enviar el correo de recuperación."
        ) from exc
    except Exception as exc:
        # Evita exponer detalles internos del proveedor al consumidor.
        logger.error(
            "Error inesperado en el servicio de correo (tipo=%s).",
            type(exc).__name__,
        )
        raise PinEmailError(
            "No fue posible enviar el correo de recuperación."
        ) from exc

    if sent_count != 1:
        logger.warning("El servicio de correo no confirmó el envío.")
        raise PinEmailError(
            "No fue posible confirmar el envío del correo."
        )
        
    logger.info("Correo de recuperación enviado correctamente.")