import csv
import io
import logging
from datetime import date, timedelta
from decimal import Decimal
from smtplib import SMTPException

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.utils import timezone, translation

from .emails import deliver_order_created_email
from .models import Order, OrderItem

logger = logging.getLogger(__name__)

EMAIL_RETRY_OPTIONS = {
    'autoretry_for': (SMTPException, OSError),
    'retry_backoff': True,
    'retry_backoff_max': 600,
    'retry_jitter': True,
    'max_retries': 5,
}

REPORT_HEADER = ['order_id', 'created', 'email', 'book', 'quantity', 'price', 'cost']
FORMULA_PREFIXES = ('=', '+', '-', '@', chr(9), chr(13))


def safe_cell(value):
    value = str(value)
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


@shared_task(**EMAIL_RETRY_OPTIONS)
def send_order_confirmation_email(order_id, language=None):
    with translation.override(language or settings.LANGUAGE_CODE):
        try:
            deliver_order_created_email(order_id)
        except Order.DoesNotExist:
            logger.warning('Замовлення #%s не знайдено, email не надіслано', order_id)
            return False
    return True


def parse_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


@shared_task(**EMAIL_RETRY_OPTIONS)
def generate_sales_report(date_from=None, date_to=None):
    date_to = parse_date(date_to) or timezone.localdate() - timedelta(days=1)
    date_from = parse_date(date_from) or date_to

    items = (
        OrderItem.objects
        .filter(
            order__status=Order.Status.PAID,
            order__created__date__gte=date_from,
            order__created__date__lte=date_to,
        )
        .select_related('order', 'book')
        .order_by('order__created', 'pk')
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(REPORT_HEADER)
    total_quantity, total_cost, order_ids = 0, Decimal('0'), set()
    for item in items:
        cost = item.get_cost()
        writer.writerow([
            item.order_id, item.order.created.isoformat(), safe_cell(item.order.email),
            safe_cell(item.book.title), item.quantity, item.price, cost,
        ])
        total_quantity += item.quantity
        total_cost += cost
        order_ids.add(item.order_id)
    writer.writerow(['', '', '', 'TOTAL', total_quantity, '', total_cost])
    content = buffer.getvalue()

    storage = FileSystemStorage(location=settings.REPORTS_ROOT)
    name = f'sales_{date_from.isoformat()}_{date_to.isoformat()}.csv'
    if storage.exists(name):
        storage.delete(name)
    path = storage.save(name, ContentFile(content.encode('utf-8-sig')))

    if settings.SALES_REPORT_RECIPIENTS:
        message = EmailMessage(
            subject=f'Sales report {date_from.isoformat()} - {date_to.isoformat()}',
            body=f'Orders: {len(order_ids)}\nCopies sold: {total_quantity}\nRevenue: {total_cost}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=settings.SALES_REPORT_RECIPIENTS,
        )
        message.attach(path, content, 'text/csv')
        message.send()

    logger.info('Звіт продажів %s – %s збережено у %s', date_from, date_to, path)
    return {'path': path, 'orders': len(order_ids), 'quantity': total_quantity, 'total': str(total_cost)}


@shared_task
def clear_expired_sessions():
    call_command('clearsessions')
    return True
