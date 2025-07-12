from django.apps import AppConfig
from django.db.utils import OperationalError


class SystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system'

    def ready(self):
        try:
            from .models import Feature
            Feature.objects.get_or_create(code='complete_appointment', defaults={'name': 'Complete Appointment'})
            Feature.objects.get_or_create(code='buy_product', defaults={'name': 'Buy Product'})
        except OperationalError:
            pass
        except Exception as e:
            pass
