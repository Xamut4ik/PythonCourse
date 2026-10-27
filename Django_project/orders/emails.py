import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from .models import Order

logger = logging.getLogger(__name__)


def deliver_order_created_email(order_id):
    order = Order.objects.prefetch_related('items__book').get(pk=order_id)
    send_mail(
        subject=_('Order #%(id)s created') % {'id': order.id},
        message=render_to_string('orders/emails/order_created.txt', {'order': order}),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.email],
    )
    logger.info('Email про замовлення #%s надіслано на %s', order.id, order.email)
    return order
