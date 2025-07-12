from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Appointment

from twilio.rest import Client
from datetime import timedelta
from django.contrib.auth import get_user_model
from .models import Customer
import logging

logger = logging.getLogger(__name__)

@shared_task
def send_reminders():
    try:
        logger.warning("Starting send_reminders task")
        now_time = timezone.now()
        five_hours_later = now_time + timedelta(hours=5)
        appointments = Appointment.objects.filter(
            date_time__gt=five_hours_later,
            status='BOOKED'
        )
        twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        for appt in appointments:
            if appt.customer.email:
                try:
                    send_mail(
                        'Appointment Reminder',
                        f'Dear {appt.customer.name}, you have an appointment on {appt.date_time.strftime("%Y-%m-%d %H:%M")}.',
                        settings.DEFAULT_FROM_EMAIL,
                        [appt.customer.email],
                        fail_silently=False,
                    )
                except Exception as e:
                    logger.error(f"Reminder email error for {appt.customer.email}: {e}")

            if appt.customer.phone:
                try:
                    twilio_client.messages.create(
                        body=f"Reminder: You have a salon appointment on {appt.date_time.strftime('%Y-%m-%d %H:%M')}.",
                        messaging_service_sid=settings.TWILIO_MESSAGING_SERVICE_SID,
                        to=appt.customer.phone
                    )
                except Exception as e:
                    logger.error(f"Reminder SMS error for {appt.customer.phone}: {e}")

        logger.warning("Finished send_reminders task")
        return "Reminders sent"
    except Exception as e:
        logger.error(f"send_reminders task failed: {e}")
        return f"Failed: {e}"

@shared_task
def test_task():
    print("Test task ran!")
    return "OK"

@shared_task
def send_promotional_message(subject, message, sms_message=None):
    from django.core.mail import send_mail
    from django.conf import settings
    from twilio.rest import Client

    twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    customers = Customer.objects.all()
    email_count = 0
    sms_count = 0

    for customer in customers:
        # Send email
        if customer.email:
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [customer.email],
                    fail_silently=False,
                )
                email_count += 1
            except Exception as e:
                print(f"Promotional email error for {customer.email}: {e}")

        # Send SMS
        if sms_message and customer.phone:
            try:
                twilio_client.messages.create(
                    body=sms_message,
                    messaging_service_sid=settings.TWILIO_MESSAGING_SERVICE_SID,
                    to=customer.phone
                )
                sms_count += 1
            except Exception as e:
                print(f"Promotional SMS error for {customer.phone}: {e}")

    print(f"Promotional campaign sent: {email_count} emails, {sms_count} SMS")
    return f"Sent {email_count} emails, {sms_count} SMS"