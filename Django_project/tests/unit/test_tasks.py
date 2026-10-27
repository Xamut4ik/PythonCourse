import csv
from datetime import timedelta
from decimal import Decimal
from smtplib import SMTPException

import pytest
from celery.exceptions import Retry
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError

from config.celery import app as celery_app
from orders.models import Order
from orders.tasks import clear_expired_sessions, generate_sales_report, send_order_confirmation_email
from tests.factories import BookFactory, OrderFactory, OrderItemFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_order_confirmation_email_is_sent(book):
    order = OrderItemFactory(order=OrderFactory(email='buyer@example.com'), book=book).order
    assert send_order_confirmation_email.delay(order.pk, 'uk').get() is True
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ['buyer@example.com']
    assert f'#{order.pk}' in mail.outbox[0].subject
    assert 'Кобзар' in mail.outbox[0].body


def test_order_confirmation_email_uses_given_language(book):
    order = OrderItemFactory(book=book).order
    send_order_confirmation_email(order.pk, 'en')
    assert mail.outbox[0].subject == f'Order #{order.pk} created'


def test_order_confirmation_email_for_missing_order():
    assert send_order_confirmation_email(999) is False
    assert mail.outbox == []


def test_order_confirmation_email_retries_on_smtp_error(mocker):
    order = OrderFactory()
    mocker.patch('orders.emails.send_mail', side_effect=SMTPException('smtp down'))
    retry = mocker.patch.object(send_order_confirmation_email, 'retry', side_effect=Retry())
    with pytest.raises(Retry):
        send_order_confirmation_email(order.pk)
    assert isinstance(retry.call_args.kwargs['exc'], SMTPException)


def test_order_confirmation_task_has_backoff():
    assert send_order_confirmation_email.retry_backoff is True
    assert send_order_confirmation_email.max_retries == 5
    assert SMTPException in send_order_confirmation_email.autoretry_for


def test_order_creation_queues_email_task(client, book, order_data, add_to_cart, mocker, django_capture_on_commit_callbacks):
    delay = mocker.patch('orders.services.send_order_confirmation_email.delay')
    add_to_cart(book, 1)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse('orders:order_create'), order_data)
    delay.assert_called_once_with(Order.objects.get().pk, 'uk')


def test_order_email_is_sent_synchronously_when_broker_is_down(
    client, book, order_data, add_to_cart, mocker, django_capture_on_commit_callbacks,
):
    mocker.patch('orders.services.send_order_confirmation_email.delay', side_effect=OperationalError('no broker'))
    add_to_cart(book, 1)
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(reverse('orders:order_create'), order_data).status_code == 302
    assert len(mail.outbox) == 1
    assert Order.objects.get().email == order_data['email']


@pytest.fixture
def report_orders():
    yesterday = timezone.now() - timedelta(days=1)
    paid = OrderFactory(status=Order.Status.PAID, email='paid@example.com')
    OrderItemFactory(order=paid, book=BookFactory(title='Кобзар'), price=Decimal('100.00'), quantity=2)
    OrderItemFactory(order=paid, book=BookFactory(title='Енеїда'), price=Decimal('50.00'), quantity=1)
    pending = OrderFactory()
    OrderItemFactory(order=pending, price=Decimal('10.00'), quantity=1)
    old = OrderFactory(status=Order.Status.PAID)
    OrderItemFactory(order=old, price=Decimal('10.00'), quantity=1)
    Order.objects.filter(pk__in=[paid.pk, pending.pk]).update(created=yesterday)
    Order.objects.filter(pk=old.pk).update(created=yesterday - timedelta(days=10))
    return paid


def read_report(path):
    with open(settings.REPORTS_ROOT / path, encoding='utf-8-sig', newline='') as f:
        return list(csv.reader(f))


def test_sales_report_for_yesterday(settings, tmp_path, report_orders):
    settings.REPORTS_ROOT = tmp_path
    settings.SALES_REPORT_RECIPIENTS = []
    result = generate_sales_report()
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    assert result == {
        'path': f'sales_{yesterday}_{yesterday}.csv', 'orders': 1, 'quantity': 3, 'total': '250.00',
    }
    rows = read_report(result['path'])
    assert rows[0] == ['order_id', 'created', 'email', 'book', 'quantity', 'price', 'cost']
    assert [row[3] for row in rows[1:3]] == ['Кобзар', 'Енеїда']
    assert rows[1][2] == 'paid@example.com' and rows[1][6] == '200.00'
    assert rows[-1] == ['', '', '', 'TOTAL', '3', '', '250.00']
    assert mail.outbox == []


def test_sales_report_for_period_is_emailed(settings, tmp_path, report_orders):
    settings.REPORTS_ROOT = tmp_path
    settings.SALES_REPORT_RECIPIENTS = ['admin@example.com']
    date_to = timezone.localdate()
    date_from = date_to - timedelta(days=30)
    result = generate_sales_report(date_from.isoformat(), date_to.isoformat())
    assert result['orders'] == 2
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ['admin@example.com']
    filename, content, mimetype = message.attachments[0]
    assert filename == f'sales_{date_from.isoformat()}_{date_to.isoformat()}.csv'
    assert mimetype == 'text/csv'
    assert 'TOTAL' in content


def test_sales_report_overwrites_existing_file(settings, tmp_path, report_orders):
    settings.REPORTS_ROOT = tmp_path
    settings.SALES_REPORT_RECIPIENTS = []
    first = generate_sales_report()
    second = generate_sales_report()
    assert first['path'] == second['path']
    assert len(list(tmp_path.iterdir())) == 1


def test_clear_expired_sessions(client, user):
    client.force_login(user)
    Session.objects.create(session_key='expired', session_data='', expire_date=timezone.now() - timedelta(days=1))
    assert clear_expired_sessions.delay().get() is True
    assert not Session.objects.filter(session_key='expired').exists()
    assert Session.objects.count() == 1


def test_periodic_tasks_are_scheduled():
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert schedule['clear-expired-sessions']['task'] == 'orders.tasks.clear_expired_sessions'
    assert schedule['daily-sales-report']['task'] == 'orders.tasks.generate_sales_report'
    assert settings.CELERY_BEAT_SCHEDULER == 'django_celery_beat.schedulers:DatabaseScheduler'
    celery_app.loader.import_default_modules()
    for entry in schedule.values():
        assert entry['task'] in celery_app.tasks


def test_sales_report_escapes_formulas(settings, tmp_path):
    settings.REPORTS_ROOT = tmp_path
    settings.SALES_REPORT_RECIPIENTS = []
    order = OrderFactory(status=Order.Status.PAID, email='=cmd@example.com')
    OrderItemFactory(order=order, book=BookFactory(title='=HYPERLINK("x")'))
    today = timezone.localdate().isoformat()
    rows = read_report(generate_sales_report(today, today)['path'])
    assert rows[1][2] == "'=cmd@example.com"
    assert rows[1][3] == '\'=HYPERLINK("x")'


def test_sales_report_is_not_stored_in_public_media(settings, tmp_path):
    settings.REPORTS_ROOT = tmp_path / 'private'
    settings.MEDIA_ROOT = tmp_path / 'media'
    settings.SALES_REPORT_RECIPIENTS = []
    path = generate_sales_report()['path']
    assert (tmp_path / 'private' / path).exists()
    assert not (tmp_path / 'media').exists()
