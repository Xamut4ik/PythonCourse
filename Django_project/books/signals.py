from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_books

DEFAULT_GROUP_NAME = 'Користувачі'


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def add_user_to_default_group(sender, instance, created, **kwargs):
    if created:
        group, _ = Group.objects.get_or_create(name=DEFAULT_GROUP_NAME)
        instance.groups.add(group)


def invalidate_now_and_on_commit(book_ids):
    book_ids = list(book_ids)
    invalidate_books(book_ids)
    transaction.on_commit(lambda: invalidate_books(book_ids))


@receiver(post_save, sender='books.Book')
@receiver(post_delete, sender='books.Book')
def invalidate_book_cache(sender, instance, **kwargs):
    invalidate_now_and_on_commit([instance.pk])


@receiver(post_save, sender='books.Category')
@receiver(post_delete, sender='books.Category')
def invalidate_category_cache(sender, instance, **kwargs):
    invalidate_now_and_on_commit(instance.book_set.values_list('pk', flat=True))
