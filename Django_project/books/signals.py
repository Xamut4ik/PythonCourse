from django.conf import settings
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

DEFAULT_GROUP_NAME = 'Користувачі'


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def add_user_to_default_group(sender, instance, created, **kwargs):
    if created:
        group, _ = Group.objects.get_or_create(name=DEFAULT_GROUP_NAME)
        instance.groups.add(group)
