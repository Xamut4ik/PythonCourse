from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group, User
from django.contrib.auth import get_user_model

user_model = get_user_model()

@receiver(post_save, sender=User)
def add_user_(sender, instance, created, **kwargs):
    if created:
        is_created = Group.objects.get_or_create(name='Користувачі')
